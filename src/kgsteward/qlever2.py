"""QLever *live* driver (brand: ``qlever2``) for kgsteward.

An alternative to the static-index :class:`~kgsteward.qlever.QleverClient`.
Instead of rebuilding the whole on-disk index from files on every run, it runs
QLever as a **live HTTP backend** -- loading each dataset into its named graph
over the SPARQL 1.1 Graph Store HTTP Protocol (GSP), exactly like the Fuseki
driver -- and folds the in-memory update *delta* back into a compact on-disk
index with ``qlever rebuild-index`` after each dataset (hot-swapped in with no
downtime).

See ``doc/drivers/qlever2-design.md`` for the full rationale, benchmarks and
trade-offs.  In short:

  * **Load path** -- GSP chunked POST per context (Fuseki model + the GSP
    machinery inherited from :class:`GenericClient`).  The only QLever-specific
    bit is the write auth (access token as a query param) and the
    ``application/n-triples`` content type.
  * **Server** -- a Docker/native QLever server managed through the ``qlever``
    CLI (Qleverfile), started once and kept up across the session (contrast the
    static driver's per-rebuild stop/index/start dance).
  * **Bootstrap** -- an EMPTY index (``qlever index`` over an empty input file),
    so the live server has something to serve before any data lands.  All real
    data arrives via GSP, never via the Qleverfile ``INPUT_FILES``.
  * **Compaction** -- ``qlever rebuild-index`` once per dataset (driven by the
    ``queue_persist`` / ``flush_pending`` hooks).  Cheap and hot-swapped; see
    the design note's benchmark for why per-dataset rebuild is fine at
    small/medium scale.

Because it is a live backend, most of the polymorphic workflow hooks
(``can_restamp``, ``refine_status``, ``update_set_offline`` ...) keep their
GenericClient live-backend defaults; only the server lifecycle and GSP writes
are overridden here.
"""

import configparser
import glob
import os
import shutil
import urllib

import requests   # for requests.exceptions.ConnectionError on a server crash

from .common  import *
from .generic import GenericClient
from .qlever  import parse_qleverfile   # reuse the Qleverfile reader verbatim

# Name of the empty input file kgsteward writes into qleverdir so `qlever index`
# can build the (empty) bootstrap index.  Real data never goes through
# INPUT_FILES -- it is loaded live over the Graph Store Protocol.
_EMPTY_INPUT = "_kgsteward_empty.nt"

# Compact (rebuild-index) the in-memory delta once this many triples have been
# loaded since the last compaction.  Bounds delta RAM *within* a single large
# dataset: without it, a big graph streamed over GSP grows the delta until the
# qlever-server process crashes (observed on ReconXKG's SwissProt_Human at
# ~20M triples).  Each rebuild costs ~O(total index size), so a higher value
# means fewer/cheaper-in-aggregate rebuilds -- keep it comfortably below the
# crash point (a 10M-triple delta is ~1.5 GB; the crash was ~20M).  Lower it on
# tight-RAM hosts; raise it when the Docker VM has plenty of memory.
_COMPACT_THRESHOLD_TRIPLES = 10_000_000


class Qlever2Client( GenericClient ):

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def __init__( self, qleverfile, qleverdir, access_token = None,
                  echo = True, managed_contexts = None ):
        for tool in ( "qlever", "riot" ):
            if shutil.which( tool ) is None:
                stop_error( f"{tool} not found on PATH" )

        location, repository, system, access_token_from_file, text_index = (
            parse_qleverfile( qleverfile )
        )

        if system in ( "docker", "podman" ):
            if run_system_cmd( [ system, "info" ], echo = echo, capture_output = True ).returncode != 0:
                stop_error( f"{system} daemon is not running" )
        elif system != "native":
            stop_error( f"Unknown [runtime] SYSTEM in Qleverfile: '{system}'" )

        if not os.path.isdir( qleverdir ):
            stop_error( f"qleverdir does not exist: {qleverdir}" )
        real_qf = os.path.realpath( qleverfile )
        real_qd = os.path.realpath( qleverdir )
        if os.path.commonpath( [ real_qf, real_qd ] ) == real_qd:
            stop_error( f"qleverfile must not be located inside qleverdir: {qleverfile}" )

        # QLever serves query, update AND the Graph Store Protocol at ONE URL,
        # differentiated by HTTP verb / query params -- so all three endpoints
        # are the same base location (simpler than Fuseki's three paths).
        super().__init__( location, location, location )
        self.repository       = repository
        self.qleverfile       = qleverfile
        self.qleverdir        = qleverdir
        self.system           = system
        self.access_token     = access_token if access_token is not None else access_token_from_file
        self.user_text_index  = text_index
        self.qlever_cmd       = [ "qlever" ]
        # Context IRIs of all datasets kgsteward manages (from the YAML).  Like
        # the static driver, list_context() returns this set instead of issuing
        # a SELECT DISTINCT ?g (which scans/sorts the whole index and can OOM).
        self.managed_contexts = set( managed_contexts ) if managed_contexts is not None else None
        # True once a text index has been built (finalize --qlever_complete), so
        # the next server start loads it; empty per-dataset rebuilds never make one.
        self._has_text        = False
        # Set by queue_persist, consumed by flush_pending: an uncompacted delta
        # is waiting for a rebuild-index.  Avoids a redundant rebuild on the
        # end-of-loop safety-net flush.
        self._pending_compaction = False
        # Triples loaded over GSP since the last rebuild-index; drives the
        # mid-load threshold compaction (see _flush_buf).
        self._delta_triples = 0

        # Best-effort probe -- does NOT distinguish "stopped" from "unreachable".
        self.is_running = self._probe_running( echo = echo )
        report( "qlever server", "running" if self.is_running else "stopped" )

    # ------------------------------------------------------------------ #
    # CLI / Qleverfile plumbing
    # ------------------------------------------------------------------ #

    def _qlever( self, *args, echo = True ):
        """Run a ``qlever`` sub-command in qleverdir; stop_error on non-zero exit."""
        if echo:
            r = run_system_cmd( self.qlever_cmd + list( args ), echo = True, cwd = self.qleverdir )
        else:
            r = run_system_cmd( self.qlever_cmd + list( args ), echo = False, cwd = self.qleverdir,
                                capture_output = True, text = True )
        if r.returncode != 0:
            if not echo:
                if r.stdout: print( r.stdout, flush = True )
                if r.stderr: print( r.stderr, flush = True )
            stop_error( f"qlever {args[0]} failed" )
        return r

    @property
    def has_index( self ):
        """True iff a qlever index exists in qleverdir (``qlever index`` ran)."""
        return bool( glob.glob( os.path.join( self.qleverdir, f"{self.repository}.index.*" ) ) )

    def _probe_running( self, echo = False ):
        try:
            http_call( { 'method': 'GET', 'url': self.endpoint_query }, [ 200, 404 ], echo )
            return True
        except Exception:
            return False

    def _sync_qleverfile( self, echo = True ):
        """Copy the user's Qleverfile into qleverdir (the CLI's cwd) and patch it
        for the live model:

          * ``[server] HOST_NAME = localhost`` -- otherwise the CLI's alive-check
            probes ``socket.gethostname()``, which does not route to the
            Docker-mapped port, and ``qlever start`` spins forever.
          * ``[data] DESCRIPTION`` -- the current qlever CLI requires one for
            ``start``; inject a default if the user did not set it.
          * ``[index] INPUT_FILES`` -> an empty file -- qlever2 loads everything
            over GSP, so the on-disk index only ever needs the empty bootstrap.
        """
        dest = os.path.join( self.qleverdir, "Qleverfile" )
        shutil.copy2( os.path.realpath( self.qleverfile ), dest )
        parser = configparser.RawConfigParser( inline_comment_prefixes = ( '#', ) )
        parser.optionxform = str    # preserve uppercase keys
        parser.read( dest )

        if "server" not in parser: parser["server"] = {}
        parser["server"]["HOST_NAME"] = "localhost"

        if "data" not in parser: parser["data"] = {}
        if not parser["data"].get( "DESCRIPTION", "" ).strip():
            parser["data"]["DESCRIPTION"] = "managed by kgsteward (qlever2)"

        # A [data] FORMAT (e.g. nq) would mis-type the empty bootstrap input;
        # drop it -- qlever2 never loads real data through INPUT_FILES.
        if parser.has_option( "data", "FORMAT" ):
            parser.remove_option( "data", "FORMAT" )

        if "index" not in parser: parser["index"] = {}
        parser["index"]["INPUT_FILES"]     = _EMPTY_INPUT
        parser["index"]["CAT_INPUT_FILES"] = "cat " + _EMPTY_INPUT
        if parser.has_option( "index", "MULTI_INPUT_JSON" ):
            parser.remove_option( "index", "MULTI_INPUT_JSON" )

        with open( dest, "w" ) as f:
            parser.write( f )
        open( os.path.join( self.qleverdir, _EMPTY_INPUT ), "w" ).close()
        if echo: report( "synced Qleverfile", dest )

    # ------------------------------------------------------------------ #
    # Server lifecycle
    # ------------------------------------------------------------------ #

    def _server_start( self, echo = True ):
        """Start the server, first clearing any leftover/stale container.

        A stopped-but-present ``qlever.server.<NAME>`` container (from a crash or
        ``docker kill``) makes ``qlever start`` fail with a cryptic "container
        name already in use"; a best-effort ``qlever stop`` clears it.  Text
        index is loaded only once ``build`` has produced one.
        """
        run_system_cmd( self.qlever_cmd + [ "stop" ], echo = False, cwd = self.qleverdir,
                        capture_output = True, text = True )
        # --persist-updates: write the located-triples delta to disk and replay
        # it on restart, so GSP-loaded data is durable (without it a server
        # restart silently drops everything not yet folded into the index).
        args = [ "start", "--persist-updates" ]
        if not self._has_text:
            args += [ "--use-text-index", "no" ]
        self._qlever( *args, echo = echo )
        self.is_running = True

    def _server_stop( self, echo = True ):
        run_system_cmd( self.qlever_cmd + [ "stop" ], echo = False, cwd = self.qleverdir,
                        capture_output = True, text = True )
        self.is_running = False

    def _ensure_up( self, echo = True ):
        """Guarantee a live server before any GSP / SPARQL operation.

        Lazily bootstraps: sync the Qleverfile if missing, build the empty index
        if none exists, then start.  Idempotent -- returns immediately once up.
        """
        if self.is_running:
            return
        if not os.path.isfile( os.path.join( self.qleverdir, "Qleverfile" ) ):
            self._sync_qleverfile( echo = echo )
        if not self.has_index:
            self._qlever( "index", echo = echo )   # empty bootstrap index
        self._server_start( echo = echo )

    def _http_write( self, request_args, status_code_ok, echo, what ):
        """http_call for a write op, turning a mid-op server crash into a clean stop.

        A ``RemoteDisconnected`` / ``ConnectionError`` means the qlever-server
        process died (typically delta/update pressure) and slammed the socket
        shut -- not an HTTP error.  Surface it with actionable guidance instead
        of letting a raw traceback escape (mirrors the static driver)."""
        try:
            return http_call( request_args, status_code_ok, echo )
        except requests.exceptions.ConnectionError:
            self.is_running = False
            print_warn(
                "qlever server closed the connection during " + what + ".\n"
                "The server process most likely crashed under delta/update pressure "
                "(a large graph loaded into the in-memory delta). Options:\n"
                "  - lower _COMPACT_THRESHOLD_TRIPLES (kgsteward compacts mid-load),\n"
                "  - give Docker Desktop more RAM, or\n"
                "  - use the static 'qlever' brand (index-from-files) for very large datasets."
            )
            stop_error( "qlever2: connection lost during " + what )

    def _rebuild_index( self, echo = True ):
        """Fold the in-memory delta into the on-disk index (hot-swap) and reset
        the delta counter.  No-op if the server is down or no token is set.

        NON-FATAL: compaction is an optimization, not a correctness requirement
        -- the data is safe and served from the persisted delta regardless.  A
        ``rebuild-index`` failure (e.g. an upstream QLever engine assertion in
        IndexRebuilder) therefore only warns and continues, leaving the data in
        the delta; it must never abort an otherwise-successful build.
        """
        if not self.is_running:
            return
        if not self.access_token:
            print_warn( "no ACCESS_TOKEN: skipping qlever rebuild-index (delta left uncompacted)" )
            self._delta_triples = 0
            return
        r = run_system_cmd(
            self.qlever_cmd + [ "rebuild-index", "--access-token", self.access_token ],
            echo = echo, cwd = self.qleverdir,
            capture_output = not echo, text = True,
        )
        if r.returncode != 0:
            if not echo:
                if r.stdout: print( r.stdout, flush = True )
                if r.stderr: print( r.stderr, flush = True )
            print_warn(
                "qlever rebuild-index FAILED -- continuing with the data left in the "
                "in-memory delta (queryable and persisted, just uncompacted).\n"
                "This is typically an upstream QLever engine bug (e.g. an assertion in "
                "IndexRebuilder); please report it to the QLever developers.\n"
                "If it recurs the delta keeps growing, so RAM pressure may eventually "
                "return -- give Docker more RAM, or use the static 'qlever' brand for the full build."
            )
        self._delta_triples = 0   # reset either way: retry only after the next threshold, not every chunk

    # ------------------------------------------------------------------ #
    # Repository lifecycle
    # ------------------------------------------------------------------ #

    def list_repository( self ):
        """qlever2 is bound to the single dataset named in the Qleverfile."""
        return [ self.repository ]

    def rewrite_repository( self, _server_config_filename = None, echo = True ):
        """Full reset (-I): tear down the server, wipe the index, rebuild an
        empty one and start fresh.  *_server_config_filename* is accepted for
        cross-backend signature parity and ignored (qlever has no equivalent).
        """
        self._server_stop( echo = echo )
        for path in sorted( glob.glob( os.path.join( self.qleverdir, f"{self.repository}.*" ) ) ):
            os.remove( path )
            if echo: report( "wiped index file", os.path.basename( path ) )
        for pattern in ( "previous.*", "rebuild.*" ):
            for path in glob.glob( os.path.join( self.qleverdir, pattern ) ):
                if os.path.isdir( path ):
                    shutil.rmtree( path )
                    if echo: report( "wiped rebuild dir", os.path.basename( path ) )
        self._sync_qleverfile( echo = echo )
        self._qlever( "index", echo = echo )   # empty bootstrap index
        self._server_start( echo = echo )
        self._pending_compaction = False

    # ------------------------------------------------------------------ #
    # Data loading  (Graph Store Protocol)
    # ------------------------------------------------------------------ #

    @property
    def supports_sparql_load( self ):
        # QLever's SPARQL ``LOAD <url> INTO GRAPH`` is not usable; data is
        # ingested over the Graph Store Protocol instead.
        return False

    def _gsp_url( self, context ):
        """GSP endpoint for *context*, with the write access token + a generous
        timeout (a big single graph can otherwise trip the operation timeout)."""
        url = self.endpoint_store + "?graph=" + urllib.parse.quote_plus( context )
        if self.access_token:
            url += "&access-token=" + urllib.parse.quote_plus( self.access_token )
        url += "&timeout=999999s"
        return url

    def load_from_file( self, file, context, headers = {}, echo = True ):
        """GSP POST a whole file into *context* (used by the ``file_store`` loader)."""
        self._ensure_up( echo = False )
        if echo:
            report( "load file (GSP)", file )
        with any_open( file, 'rb' ) as f:   # any_open handles decompression
            self._http_write(
                { 'method': 'POST', 'url': self._gsp_url( context ),
                  'headers': { **headers, 'Content-Type': guess_mime_type( file ) },
                  'data': f },
                [ 200, 201, 204 ], echo, "graph-store POST",
            )

    def load_from_file_using_riot( self, file, context, headers = {}, echo = True ):
        """GSP chunked load via riot (the recommended ``riot_chunk_store`` loader)."""
        self._ensure_up( echo = False )
        super().load_from_file_using_riot( file, context, headers = headers, echo = echo )

    def _flush_buf( self, context, data, headers = {}, echo = True ):
        """POST one N-Triples chunk (from ``load_from_file_using_riot``) over GSP.

        Overrides the GenericClient version: QLever needs the access token and
        ``application/n-triples`` (the base class hardcodes ``text/plain``,
        which QLever rejects).
        """
        n_triples = data.count( "\n" ) if isinstance( data, str ) else data.count( b"\n" )
        self._http_write(
            { 'method': 'POST', 'url': self._gsp_url( context ),
              'headers': { 'Content-Type': 'application/n-triples' },
              'data': data.encode( 'utf-8' ) if isinstance( data, str ) else data },
            [ 200, 201, 204 ], echo, "graph-store POST",
        )
        # Threshold compaction: drain the delta mid-load so a single large
        # dataset cannot grow it without bound (which crashes the server).
        self._delta_triples += n_triples
        if self._delta_triples >= _COMPACT_THRESHOLD_TRIPLES:
            report( "delta compaction", f"{self._delta_triples} triples loaded -> rebuild-index" )
            self._rebuild_index( echo = echo )

    def load_url( self, path, context, echo = True ):
        # QLever cannot LOAD a remote graph; a URL dataset must be downloaded
        # first -- configure ``url_loader: {method: curl_riot_chunk_store}`` so
        # kgsteward fetches it and hands the file to load_from_file_using_riot.
        stop_error(
            "qlever2 cannot load a URL directly (QLever has no working SPARQL LOAD).\n"
            "Use  url_loader:\\n    method: curl_riot_chunk_store  in the YAML so the\n"
            "file is downloaded and loaded over the Graph Store Protocol."
        )

    def drop_context( self, context, echo = True ):
        """GSP DELETE the named graph (idempotent).

        A DELETE of a large existing graph writes that many *deletion* markers
        into the delta, so it grows the delta just like a load -- count them
        toward the compaction threshold and drain if a big drop crosses it
        (a big drop alone could otherwise blow the delta before any load runs).
        """
        self._ensure_up( echo = False )
        r = self._http_write(
            { 'method': 'DELETE', 'url': self._gsp_url( context ) },
            [ 200, 204, 404 ], echo, "graph-store DELETE",   # 200/204: dropped, 404: absent
        )
        deleted = 0
        if r is not None and getattr( r, "status_code", None ) == 200:
            try:   # QLever returns {"operations":[{"delta-triples":{"difference":{"deleted":N}}}]}
                ops = r.json().get( "operations", [] )
                deleted = ops[0]["delta-triples"]["difference"]["deleted"] if ops else 0
            except Exception:
                deleted = 0
        self._delta_triples += deleted
        if self._delta_triples >= _COMPACT_THRESHOLD_TRIPLES:
            report( "delta compaction", f"{self._delta_triples} delta triples (post-delete) -> rebuild-index" )
            self._rebuild_index( echo = echo )

    # ------------------------------------------------------------------ #
    # SPARQL
    # ------------------------------------------------------------------ #

    def sparql_query( self, sparql, status_code_ok = [ 200, 400, 500 ], echo = True, timeout = None ):
        self._ensure_up( echo = False )
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        r = http_call(
            { 'method': 'POST', 'url': self.endpoint_query,
              'headers': { 'Accept': 'application/json',
                           'Content-Type': 'application/x-www-form-urlencoded' },
              'data': { 'query': sparql } },
            status_code_ok, echo,
        )
        if r.status_code in ( 400, 500 ) and r.text:
            print_warn( r.text )
            return None
        if r.status_code != 200:
            stop_error( f"SPARQL query failed with HTTP {r.status_code}: {r.text[:500]}" )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        """Execute a SPARQL update immediately against the live server.

        The token + a generous timeout go in the form body (QLever's update
        endpoint is the same base URL as query).  Shares the per-update
        query/timing logging with every backend via GenericClient.
        """
        self._ensure_up( echo = False )
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        tok = self._sparql_update_started( sparql )   # logs the query pre-execution
        # On a server crash _http_write stop_errors here: the query stays logged
        # with no timing row (the documented "in-flight / crashed" signature).
        r = self._http_write(
            { 'method': 'POST', 'url': self.endpoint_update,
              'headers': { 'Content-Type': 'application/x-www-form-urlencoded' },
              'data': { 'update': sparql,
                        'access-token': self.access_token,
                        'timeout': '999999s' } },
            status_code_ok, echo, "SPARQL update",
        )
        self._sparql_update_finished( tok, getattr( r, "status_code", None ) )
        return r

    def list_context( self, echo = True ):
        if self.managed_contexts is not None:
            return set( self.managed_contexts )
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        return {
            rec["g"]["value"]
            for rec in r.json()["results"]["bindings"]
            if "g" in rec
        }

    # ------------------------------------------------------------------ #
    # Compaction  (per-dataset rebuild-index)
    # ------------------------------------------------------------------ #

    def queue_persist( self, context, sha256 = None ):
        """Mark that a dataset just landed in the delta and needs compacting.

        The GSP writes are already durable (they live in the persisted delta);
        this only schedules the ``rebuild-index`` that flush_pending performs.
        """
        self._pending_compaction = True

    def flush_pending( self, echo = True ):
        """Compact the delta into the on-disk index once, if anything is pending.

        Fires per-dataset (the main loop calls queue_persist + flush_pending each
        iteration), so this is the per-dataset ``rebuild-index``.  The end-of-loop
        safety-net flush is a no-op because the flag was already cleared.
        """
        if not self._pending_compaction:
            return
        if echo and self.is_running and self.access_token:
            print_task( "compact qlever index (rebuild-index)" )
        self._rebuild_index( echo = echo )   # no-op if server down / no token
        self._pending_compaction = False

    def finalize( self, complete, echo = True ):
        """End-of-session finalisation: compact anything left, and build the text
        index when ``--qlever_complete`` is set and the Qleverfile requests one."""
        self.flush_pending( echo = echo )
        if complete and self.user_text_index and self.user_text_index.lower() != "none":
            print_break()
            print_task( "Build qlever text index" )
            self._server_stop( echo = echo )
            self._qlever( "add-text-index", "--text-index", self.user_text_index,
                          "--overwrite-existing", echo = echo )
            self._has_text = True
            self._server_start( echo = echo )

    def ensure_running( self, echo = True ):
        """Make sure the server is serving at end of session (start if stopped)."""
        if not self.is_running:
            print_break()
            print_task( "Start qlever server" )
            self._ensure_up( echo = echo )
