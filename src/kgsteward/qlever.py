"""qlever driver for kgsteward.

Architecture
------------
qlever is a *static-index* triplestore: every ``qlever index`` invocation
rebuilds the entire index from scratch from a ``MULTI_INPUT_JSON`` manifest.
It does NOT ingest data incrementally.  SPARQL ``INSERT``/``DELETE`` only
modify an in-memory delta that is lost when the server stops, unless that
delta is persisted by another mechanism.

This driver mimics the GraphDB-style "process each dataset eagerly" model
on top of qlever's static index by maintaining one ``.nt.gz`` *checkpoint*
per dataset in ``qleverdir``, alongside a ``.nt.gz.json`` *sidecar* that
records the dataset's named-graph IRI.  The sidecar is written **after**
the ``.nt.gz`` and acts as an atomic completeness marker — its presence
means the checkpoint is good; its absence means an in-progress / crashed
dump and the ``.nt.gz`` is ignored.

Per-dataset flow driven by kgsteward.py
---------------------------------------
For each dataset that kgsteward decides to (re)process:

    drop_context(ctx)            # no-op for qlever
    load_from_file / load_url_as_file(...)  # -> self.pending_files
    sparql_update(s) for each "update:" SPARQL  # -> self.pending_updates
    update_dataset_info(...)     # also sparql_update -> pending_updates
    mark_rebuild(ctx)            # appends (ctx,) sentinel to pending_updates
    server_start()               # triggers _finalize_index

``_finalize_index`` is the heart of the driver:

  1. Collect all completed checkpoints (excluding any whose IRI is being
     re-processed — its fresh files are already in pending_files).
  2. Patch ``qleverdir/Qleverfile`` with the resulting MULTI_INPUT_JSON.
  3. Stop the server.
  4. ``qlever index --text-index none --overwrite-existing``.
  5. ``qlever start --use-text-index no``.
  6. Wipe ``input/``, reset ``pending_files``.
  7. ``_apply_pending_updates``: replay queued SPARQL strings against the
     freshly-started server, then ``dump_checkpoint(ctx)`` at the sentinel
     — which captures index + in-memory delta into the new ``.nt.gz``.

Key properties
--------------
**Transactional checkpoints.**  ``dump_checkpoint`` writes to a ``.tmp``
file and atomically renames over the old ``.nt.gz``.  The sidecar is
written last.  A crash anywhere mid-processing leaves the previous
checkpoint intact.

**Text index opt-in.**  Per-dataset rebuilds always pass
``--text-index none`` (rebuilding a multi-GB text index N times for N
datasets is wasteful), and ``qlever start`` is invoked with
``--use-text-index no`` so the server doesn't try to load text files
that aren't there.  ``complete_index()`` runs ``qlever add-text-index``
once at session end iff ``--qlever_complete`` was passed.

**Update timeout disabled.**  Every ``sparql_update`` sends
``timeout=999999s`` along with the access token, overriding the
Qleverfile's ``TIMEOUT`` (which is appropriate for interactive queries,
not bulk ingestion).

**Always-queue SPARQL updates.**  ``sparql_update`` appends to
``pending_updates`` even when the server is running; updates execute
against the rebuilt server during ``_apply_pending_updates``, so their
effect survives the rebuild and lands in the next checkpoint dump.
"""

import configparser
import glob
import gzip
import hashlib
import json
import os
import re
import requests
import shutil
import subprocess
import tempfile
import time

from .common import *
from .generic import GenericClient


# Natively supported qlever formats (without riot conversion), ± .gz
_QLEVER_NATIVE = { ".ttl": "ttl", ".nt": "nt" }

# JVM system properties that lift JDK XML parser caps.  riot trips these
# on big RDF/XML ontologies (RHEA, ChEBI, GO, …).  Set to 0 = unlimited.
# Set via JAVA_TOOL_OPTIONS in the riot subprocess env — `riot --set ...`
# only changes ARQ context, NOT JVM system properties.
_JDK_XML_UNLIMITED = " ".join((
    "-Djdk.xml.maxGeneralEntitySizeLimit=0",    # JAXP00010003
    "-Djdk.xml.totalEntitySizeLimit=0",         # JAXP00010004
    "-Djdk.xml.entityExpansionLimit=0",         # JAXP00010001
    "-Djdk.xml.maxParameterEntitySizeLimit=0",  # JAXP00010002
    "-Djdk.xml.elementAttributeLimit=0",
    "-Djdk.xml.maxElementDepth=0",
))


def _first_meaningful_sparql_line( sparql ):
    """Return the first non-empty, non-comment, non-PREFIX/BASE line of *sparql*.

    Used in the sparql_update stats TSV so each row has a human-readable identifier.
    """
    for line in sparql.splitlines():
        s = line.strip()
        if not s:                             continue
        if s.startswith( "#" ):               continue
        if s.upper().startswith( "PREFIX " ): continue
        if s.upper().startswith( "BASE " ):   continue
        return s[:120]
    return ""


def _qlever_fmt( filename ):
    """Return qlever format token ('ttl'/'nt') or None if riot conversion is needed."""
    name = filename.lower()
    if name.endswith( ".gz" ): name = name[ :-3 ]
    return _QLEVER_NATIVE.get( os.path.splitext( name )[1] )


def _ttl_has_multiline_literal( path ):
    """Cheap scan: does *path* (.ttl or .ttl.gz) contain a triple-quoted literal?

    qlever's parallel parser splits on newlines and chokes on ``\"\"\"...\"\"\"``
    or ``'''...'''`` literals with::

        Parse error at byte position N: Found a multiline string literal
        with the parallel parser. This is not supported.

    Scanning the file once at staging time is much cheaper than retrying the
    full index build after a parser crash, and lets us safely keep
    ``parallel: true`` for the vast majority of TTL inputs that have no such
    literals (or only carry them in comments -- a false positive there just
    falls back to sequential parsing, the data still loads correctly).
    """
    opener = gzip.open if path.lower().endswith( ".gz" ) else open
    with opener( path, "rb" ) as f:
        carry = b""
        while True:
            buf = f.read( 1 << 20 )   # 1 MiB
            if not buf:
                return False
            window = carry + buf
            if b'"""' in window or b"'''" in window:
                return True
            carry = buf[-2:]   # so a triple-quote straddling a 1 MiB boundary still matches


def parse_qleverfile( qleverfile ):
    """Read a Qleverfile and return (location, repository, system, access_token, text_index).

    Only sufficient parsing to bootstrap the QleverClient — qlever-control reads
    the full Qleverfile itself when invoked.
    """
    real_path = os.path.realpath( qleverfile )
    if not os.path.isfile( real_path ):
        stop_error( "Qleverfile not found: " + qleverfile )
    # inline_comment_prefixes=('#',) strips trailing "# ..." comments from
    # values (qlever-control's own parser does too); without it a line like
    # `TEXT_INDEX = ... # keep your preference` would leak the comment into the
    # value and corrupt the `--text-index` argument passed to add-text-index.
    parser = configparser.ConfigParser( interpolation = None, inline_comment_prefixes = ( '#', ) )
    parser.read( real_path )
    if "data" not in parser or "NAME" not in parser["data"]:
        stop_error( "Missing [data] NAME in Qleverfile: " + real_path )
    repository   = parser["data"]["NAME"].strip()
    host         = parser.get( "server",  "HOST_NAME",    fallback = "localhost" ).strip()
    port         = parser.get( "server",  "PORT",         fallback = "7019" ).strip()
    system       = parser.get( "runtime", "SYSTEM",       fallback = "docker" ).strip()
    access_token = parser.get( "server",  "ACCESS_TOKEN", fallback = "" ).strip()
    text_index   = parser.get( "index",   "TEXT_INDEX",   fallback = "none" ).strip()
    return f"http://{host}:{port}", repository, system, access_token, text_index


class QleverClient( GenericClient ):

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def __init__( self, qleverfile, qleverdir, access_token = None, echo = True ):
        for tool in ( "qlever", "riot" ):
            if shutil.which( tool ) is None:
                stop_error( f"{tool} not found on PATH" )

        location, repository, system, access_token_from_file, text_index = (
            parse_qleverfile( qleverfile )
        )

        if system in ( "docker", "podman" ):
            if run_system_cmd( [system, "info"], echo = echo, capture_output = True ).returncode != 0:
                stop_error( f"{system} daemon is not running" )
        elif system != "native":
            stop_error( f"Unknown [runtime] SYSTEM in Qleverfile: '{system}'" )

        if not os.path.isdir( qleverdir ):
            stop_error( f"qleverdir does not exist: {qleverdir}" )
        real_qf = os.path.realpath( qleverfile )
        real_qd = os.path.realpath( qleverdir )
        if os.path.commonpath( [ real_qf, real_qd ] ) == real_qd:
            stop_error( f"qleverfile must not be located inside qleverdir: {qleverfile}" )

        super().__init__( location, None, None )
        self.repository      = repository
        self.qleverfile      = qleverfile
        self.qleverdir       = qleverdir
        self.system          = system
        self.access_token    = access_token if access_token is not None else access_token_from_file
        self.qlever_cmd      = ["qlever"]
        self.user_text_index = text_index   # original [index] TEXT_INDEX from user's source
        # MULTI_INPUT_JSON entries staged for the next _finalize_index rebuild.
        self.pending_files   = []
        # SPARQL updates queued for the next _apply_pending_updates flush;
        # may include (context_iri,) sentinels from mark_rebuild().
        self.pending_updates = []
        # Optional set of context IRIs that incremental _finalize_index rebuilds
        # are restricted to (the dependency closure of the datasets being
        # processed).  None means "include every checkpoint" (the full index).
        # complete_index() ignores this and always assembles all checkpoints.
        self.index_scope     = None
        # True iff build_text_index() has just produced a current text index
        # on disk and the next server start should load it.  _finalize_index
        # always resets this to False.
        self._has_current_text_index = False
        # Per-call timing recorded by _do_sparql_update; flushed at session
        # end by dump_sparql_update_stats() to a TSV file.
        self.sparql_update_stats    = []
        self._sparql_update_counter = 0

        # Remove any leftover input/ from a previous crashed staging phase.
        # pending_files starts empty, so any files on disk are orphans.
        input_dir = os.path.join( qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            print_warn( f"Removed stale input/ from previous run: {input_dir}" )

        # Best-effort probe — does NOT distinguish "stopped" from "unreachable".
        try:
            http_call( { 'method': 'GET', 'url': location }, [ 200, 404 ], echo = echo )
            self.is_running = True
        except Exception:
            self.is_running = False
        report( "qlever server", "running" if self.is_running else "stopped" )

        # A leftover server container from a previous crash/kill stays in an
        # exited state and makes the next `qlever start` fail with a cryptic
        # "container name already in use" docker conflict.  Fail fast with an
        # actionable message instead.
        if not self.is_running:
            stale = self._stale_server_container()
            if stale:
                stop_error(
                    "Leftover qlever server container '" + stale + "' exists but is not "
                    "serving\n(most likely from a previous crash or `docker kill`). A new "
                    "`qlever start`\nwould fail with a 'container name already in use' conflict.\n"
                    "Remove the stale container, then re-run kgsteward:\n"
                    "    " + self.system + " rm -f " + stale
                )

    @property
    def has_index( self ):
        """True iff a qlever index exists in qleverdir (i.e. ``qlever index`` ran at least once)."""
        return bool( glob.glob( os.path.join( self.qleverdir, f"{self.repository}.index.*" ) ) )

    # ------------------------------------------------------------------ #
    # Low-level invocation helpers
    # ------------------------------------------------------------------ #

    def _stale_server_container( self ):
        """Return the name of a leftover, non-serving qlever server container, or None.

        qlever-control names its container ``qlever.server.<NAME>``.  After a crash
        or ``docker kill`` the container lingers in an *exited* state and the next
        ``qlever start`` fails with a cryptic ``container name ... already in use``
        (``docker run --name`` refuses to reuse the name).  Only meaningful for
        docker/podman; returns None for native.
        """
        if self.system not in ( "docker", "podman" ):
            return None
        name = "qlever.server." + self.repository
        r = run_system_cmd(
            [ self.system, "ps", "-a", "--filter", "name=" + name, "--format", "{{.Names}}" ],
            echo = False, capture_output = True, text = True,
        )
        if r.returncode == 0 and name in r.stdout.split():
            return name
        return None

    def _qlever( self, *args, echo = True ):
        """Run a qlever CLI sub-command in qleverdir; stop_error on non-zero exit.

        With echo (``-v``) the child's stdout/stderr stream live to the terminal
        -- useful for watching index builds and debugging.  Without it the output
        is captured and printed only if the command fails, keeping normal runs
        quiet like the HTTP drivers (whose verbosity is gated the same way).
        """
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

    def _start_args( self ):
        """argv for ``qlever start``, honouring whether a text index is currently live.

        qlever auto-derives ``USE_TEXT_INDEX = yes`` from ``TEXT_INDEX != none``,
        which would cause ``qlever-server`` to ``-t`` and try to load
        ``<NAME>.text.vocabulary``.  Per-dataset rebuilds never produce text-index
        files, so we override with ``--use-text-index no`` until ``build_text_index``
        flips ``_has_current_text_index`` to True.
        """
        if self._has_current_text_index:
            return ( "start", )
        return ( "start", "--use-text-index", "no" )

    # ------------------------------------------------------------------ #
    # Qleverfile management
    # ------------------------------------------------------------------ #

    def _ensure_host_name_localhost( self ):
        """Ensure ``[server] HOST_NAME = localhost`` is set in qleverdir/Qleverfile.

        Without this, the qlever CLI falls back to ``socket.gethostname()`` for
        its alive-check (``/ping``), which doesn't route to the Docker-mapped
        port on 127.0.0.1, and ``qlever start`` spins forever.
        """
        dest = os.path.join( self.qleverdir, "Qleverfile" )
        if not os.path.lexists( dest ):
            return
        parser = configparser.RawConfigParser( inline_comment_prefixes = ('#',) )
        parser.optionxform = str
        parser.read( dest )
        if "server" not in parser:
            parser["server"] = {}
        if parser["server"].get( "HOST_NAME" ) != "localhost":
            parser["server"]["HOST_NAME"] = "localhost"
            with open( dest, "w" ) as f:
                parser.write( f )
            report( "forced", "[server] HOST_NAME = localhost" )

    def _patch_qleverfile( self, entries, echo = True ):
        """Re-sync qleverdir/Qleverfile from the user's source, then patch INPUT_FILES + MULTI_INPUT_JSON.

        Always re-copies from the user's source so edits to SETTINGS_JSON /
        STXXL_MEMORY / PARALLEL_PARSING / TEXT_INDEX take effect on the next
        per-dataset rebuild.  The patch overrides only the keys we own
        (MULTI_INPUT_JSON, INPUT_FILES, HOST_NAME), everything else from the
        user's source is preserved.

        ``inline_comment_prefixes=('#',)`` strips trailing ``# ...`` comments
        from values; qlever-control's own parser does NOT strip them and would
        otherwise emit them verbatim into the docker -c argument, with bash
        treating ``#`` as a comment introducer and silently truncating the
        rest of the command (e.g. dropping ``2>&1 | tee ...``).
        """
        dest = os.path.join( self.qleverdir, "Qleverfile" )
        shutil.copy2( os.path.realpath( self.qleverfile ), dest )
        if echo: report( "synced Qleverfile from user source", dest )

        parser = configparser.RawConfigParser( inline_comment_prefixes = ('#',) )
        parser.optionxform = str    # preserve uppercase keys
        parser.read( dest )

        if "index" not in parser:
            parser["index"] = {}
        parser.remove_option( "index", "CAT_INPUT_FILES" )
        if "data" in parser:
            parser.remove_option( "data", "FORMAT" )

        file_paths = " ".join( e["cmd"].split()[-1] for e in entries )
        parser["index"]["INPUT_FILES"]      = file_paths
        parser["index"]["MULTI_INPUT_JSON"] = json.dumps( entries, separators = (",", ":") )

        if "server" not in parser:
            parser["server"] = {}
        if "HOST_NAME" not in parser["server"]:
            parser["server"]["HOST_NAME"] = "localhost"

        with open( dest, "w" ) as f:
            parser.write( f )
        if echo:
            report( "INPUT_FILES",      file_paths )
            report( "MULTI_INPUT_JSON", f"{len(entries)} stream(s)" )

    # ------------------------------------------------------------------ #
    # Input staging
    # ------------------------------------------------------------------ #

    def _stage_file( self, filename, context_iri, void_iri = None, echo = True ):
        """Copy/convert *filename* into qleverdir/input/ and return MULTI_INPUT_JSON entries.

        *void_iri* overrides the IRI recorded in the void:dataDump triple.
        Pass the original URL when staging a downloaded file so provenance points to the source.

        For RDF/XML / OWL / etc. that qlever can't parse natively, the file is
        converted by ``riot`` in a subprocess whose env has the JDK XML parser
        caps lifted (see ``_JDK_XML_UNLIMITED``).
        """
        input_dir = os.path.join( self.qleverdir, "input" )
        os.makedirs( input_dir, exist_ok = True )

        src  = os.path.abspath( filename )
        h8   = hashlib.sha1( src.encode() ).hexdigest()[:8]
        stem = os.path.splitext( re.sub( r"\.(gz|bz2|xz)$", "", os.path.basename( src ), flags = re.IGNORECASE ) )[0]

        fmt = _qlever_fmt( src )
        if fmt is not None:
            # Native qlever format — hard-link or copy into input/.
            is_gz     = src.lower().endswith( ".gz" )
            ext_full  = f".{fmt}.gz" if is_gz else f".{fmt}"
            dest_name = f"{stem}_{h8}{ext_full}"
            dest_path = os.path.join( input_dir, dest_name )
            if os.path.lexists( dest_path ):
                os.remove( dest_path )
            try:
                os.link( src, dest_path )
                if echo: report( "hard-link", dest_path )
            except OSError:
                shutil.copy2( src, dest_path )
                if echo: report( "copy", dest_path )
            cmd = f"zcat input/{dest_name}" if is_gz else f"cat input/{dest_name}"
        else:
            # Non-native (RDF/XML, OWL, …) — convert via riot to .nt.
            dest_name = f"{stem}_{h8}.nt"
            dest_path = os.path.join( input_dir, dest_name )
            riot_cmd  = [ "riot", "--output=ntriples", src ]
            riot_env  = os.environ.copy()
            riot_env["JAVA_TOOL_OPTIONS"] = (
                ( riot_env.get( "JAVA_TOOL_OPTIONS", "" ) + " " + _JDK_XML_UNLIMITED ).strip()
            )
            if echo:
                print( colored(
                    f"JAVA_TOOL_OPTIONS=\"{riot_env['JAVA_TOOL_OPTIONS']}\" "
                    + " ".join( riot_cmd ) + f" > {dest_path}",
                    "cyan",
                ), flush = True )
            # stdout always goes to the .nt file; capture stderr when quiet so a
            # successful conversion stays silent but a failure can still be shown.
            with open( dest_path, "wb" ) as nt_out:
                riot = subprocess.run(
                    riot_cmd, stdout = nt_out, env = riot_env,
                    stderr = None if echo else subprocess.PIPE, text = True,
                )
            if riot.returncode != 0:
                if not echo and riot.stderr:
                    print( riot.stderr, flush = True )
                stop_error( f"riot conversion failed for: {src}" )
            fmt, cmd = "nt", f"cat input/{dest_name}"
            if echo: report( "staged (riot→nt)", dest_path )

        # Bake the void:dataDump triple into the index as a sibling .nt file —
        # avoids a separate INSERT + rebuild.
        actual_void_iri = void_iri if void_iri is not None else f"file://{src}"
        void_name = f"{stem}_{h8}.void.nt"
        void_path = os.path.join( input_dir, void_name )
        with open( void_path, "w" ) as vf:
            vf.write( f"<{context_iri}> <http://rdfs.org/ns/void#dataDump> <{actual_void_iri}> .\n" )

        # ``"parallel"`` is set per-input (top-level PARALLEL_PARSING does NOT
        # propagate through MULTI_INPUT_JSON) and must be the string "true"
        # or "false" (qlever-control compares with == "true").
        #
        # parallel="true" is unsafe for .ttl files containing triple-quoted
        # multiline string literals -- a single scan via _ttl_has_multiline_literal
        # picks them out at staging time so most TTL files still parse in
        # parallel.  .nt cannot have them by spec; riot-converted files come out
        # as .nt; the void file we emit ourselves is single-line .nt -- all safe.
        if fmt == "ttl" and _ttl_has_multiline_literal( src ):
            data_parallel = "false"
            if echo: report( "multiline literal", f"disabling parallel parsing for {os.path.basename(src)}" )
        else:
            data_parallel = "true"

        if echo: report( "staged", f"input/{dest_name}  (+ void triple)" )
        return [
            { "cmd": cmd,                       "format": fmt,  "graph": context_iri, "parallel": data_parallel },
            { "cmd": f"cat input/{void_name}",  "format": "nt", "graph": context_iri, "parallel": "true"        },
        ]

    # ------------------------------------------------------------------ #
    # Index lifecycle
    # ------------------------------------------------------------------ #

    def _collect_checkpoint_entries( self, exclude_iris = None, include_iris = None, echo = True ):
        """MULTI_INPUT_JSON entries for every completed checkpoint in qleverdir.

        Reads ``*.nt.gz.json`` sidecar files (the atomic completeness marker),
        builds one ``zcat <fname>`` entry per graph.

        *exclude_iris*: optional set of context IRIs to skip — typically the
        IRIs of datasets being re-processed in this run (their fresh files
        are already in ``pending_files``).  The stale checkpoint stays on
        disk and is overwritten atomically by the subsequent
        ``dump_checkpoint``.

        *include_iris*: optional set of context IRIs to restrict to (the
        dependency-closure scope of an incremental run).  ``None`` means no
        restriction — every checkpoint is included (the full index).
        """
        exclude = set( exclude_iris ) if exclude_iris else set()
        include = set( include_iris ) if include_iris is not None else None
        entries = []
        for sidecar in sorted( glob.glob( os.path.join( self.qleverdir, "*.nt.gz.json" ) ) ):
            try:
                with open( sidecar ) as f:
                    meta = json.load( f )
                context_iri = meta["graph"]
            except Exception as e:
                print_warn( f"Skipping unreadable checkpoint sidecar {sidecar}: {e}" )
                continue
            fname = os.path.basename( sidecar[ :-5 ] )   # strip ".json"
            if context_iri in exclude:
                if echo: report( "checkpoint superseded by pending data", fname )
                continue
            if include is not None and context_iri not in include:
                if echo: report( "checkpoint outside index scope (skipped)", fname )
                continue
            entries.append( { "cmd": f"zcat {fname}", "format": "nt", "graph": context_iri, "parallel": "true" } )
            if echo: report( "checkpoint → index", fname )
        return entries

    def _abort_if_index_log_has_error( self ):
        """stop_error if ``<repository>.index-log.txt`` contains any ERROR lines.

        qlever-index runs as ``qlever-index ... | tee <log>`` inside the
        container.  The pipe masks qlever-index's non-zero exit on parse
        errors / runtime exceptions because bash doesn't enable pipefail.
        Inspect the log file directly and fail loudly — otherwise the next
        dump_checkpoint would silently produce an empty .nt.gz.
        """
        log_path = os.path.join( self.qleverdir, f"{self.repository}.index-log.txt" )
        if not os.path.isfile( log_path ):
            return
        with open( log_path, errors = "replace" ) as f:
            bad = [ line for line in f if " - ERROR:" in line ]
        if not bad:
            return
        print_warn( "qlever index reported ERROR(s) — refusing to proceed:" )
        for line in bad[:5]:
            print_warn( "  " + line.strip() )
        stop_error(
            "qlever index failed (silent in exit code due to internal tee pipe). "
            "Inspect " + log_path + " for full details; "
            "after fixing the input, manually remove any empty "
            "<dataset>_<hash>.nt.gz / .nt.gz.json checkpoints created by previous "
            "runs before re-running."
        )

    def _finalize_index( self, echo = True ):
        """Build the index, start the server, apply queued updates, dump the new checkpoint.

        See the module-level docstring for the full per-dataset flow.  This is
        the only method that calls ``qlever index``.
        """
        # Re-processed datasets have their fresh files in pending_files; their
        # stale checkpoints must be excluded so we don't load old + new for
        # the same graph.
        pending_iris       = { e["graph"] for e in self.pending_files }
        # Restrict to the dependency-closure scope of this run (if set); the
        # pending files (the dataset(s) being processed) are always included.
        checkpoint_entries = self._collect_checkpoint_entries( exclude_iris = pending_iris, include_iris = self.index_scope, echo = echo )
        all_entries        = checkpoint_entries + self.pending_files

        if not all_entries:
            print_warn( "_finalize_index called with no files (no pending files, no checkpoints) — nothing to do." )
            return

        if echo: print_task( "Write MULTI_INPUT_JSON to Qleverfile" )
        self._patch_qleverfile( all_entries, echo = echo )

        if self.is_running:
            self.server_stop( echo = echo )

        # Wipe any stale <NAME>.text.* files left over from a previous
        # build_text_index — they would otherwise mismatch the rebuilt
        # main index, and the next server start would either refuse to
        # load them or serve inconsistent data.
        stale_text_files = glob.glob( os.path.join( self.qleverdir, f"{self.repository}.text.*" ) )
        for f in stale_text_files:
            os.remove( f )
            if echo: report( "wiped stale text index", os.path.basename( f ) )
        # A partial/scoped rebuild is no longer the complete production index.
        self._clear_index_complete()
        if echo and self.user_text_index and self.user_text_index.lower() != "none":
            extra = " ; wiped " + str( len( stale_text_files ) ) + " stale text-index file(s)" if stale_text_files else ""
            print_warn(
                "Qleverfile has TEXT_INDEX = " + self.user_text_index
                + " but per-dataset rebuild will skip it (`qlever index --text-index none`)"
                + extra
                + ". Pass --qlever_complete to (re)build it once at the session end."
            )
        self._has_current_text_index = False

        self._qlever( "index", "--text-index", "none", "--overwrite-existing", echo = echo )
        self._abort_if_index_log_has_error()
        self._qlever( *self._start_args(), echo = echo )
        self.is_running = True

        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            if echo: report( "cleanup", input_dir )

        self.pending_files = []
        self._apply_pending_updates( echo = echo )

    def _apply_pending_updates( self, echo = True ):
        """Replay every queued SPARQL update; dump a checkpoint at each sentinel.

        ``pending_updates`` is a list of SPARQL strings interleaved with
        ``(context_iri, sha256)`` sentinels from ``mark_rebuild()``.  Each
        sentinel triggers ``dump_checkpoint(context_iri, sha256)``, whose
        CONSTRUCT query against the running server transparently merges the
        on-disk index with the in-memory delta produced by the preceding
        updates — so the new ``.nt.gz`` captures the complete post-update state.
        """
        if not self.pending_updates:
            return
        n_updates = sum( 1 for u in self.pending_updates if not isinstance( u, tuple ) )
        if echo: print_task( f"Apply {n_updates} queued SPARQL update(s) with per-dataset checkpoint" )
        for item in self.pending_updates:
            if isinstance( item, tuple ):
                context_iri = item[0]
                sha256      = item[1] if len( item ) > 1 else None
                if context_iri:
                    self.dump_checkpoint( context_iri, sha256 = sha256, echo = echo )
            else:
                self._do_sparql_update( item, echo = echo )
        self.pending_updates = []

    # ------------------------------------------------------------------ #
    # Server lifecycle
    # ------------------------------------------------------------------ #

    def server_start( self, echo = True ):
        """Bring the server to a state consistent with pending_files / pending_updates.

        Three cases:

          * pending_files non-empty → ``_finalize_index`` (rebuild + flush).
          * pending_files empty, pending_updates non-empty → start the server
            from the existing index (if not already running) and flush the
            updates against it.
          * both empty → just start the server.
        """
        if self.pending_files:
            self._finalize_index( echo = echo )
            return
        if self.pending_updates:
            if not self.has_index:
                stop_error(
                    "qlever server_start: pending SPARQL updates but no index exists.\n"
                    "This usually means a file was loaded via sparql_update instead of "
                    "load_from_file — qlever requires all file data to go through the index."
                )
            if not self.is_running:
                self._qlever( *self._start_args(), echo = echo )
                self.is_running = True
            self._apply_pending_updates( echo = echo )
            return
        self._qlever( *self._start_args(), echo = echo )
        self.is_running = True

    def server_stop( self, echo = True ):
        self._qlever( "stop", echo = echo )
        self.is_running = False

    def build_text_index( self, echo = True ):
        """Build the text index once over the current on-disk index, then restart.

        The text index is *opt-in*: per-dataset rebuilds never produce it
        (rebuilding once per dataset is wasteful), so this method is the only
        way to get one from kgsteward.  Reads the original ``TEXT_INDEX``
        value from the user's Qleverfile (captured at ``__init__`` time).
        If that value is ``none``, this is a no-op.
        """
        if not self.user_text_index or self.user_text_index.lower() == "none":
            print_warn( "user's Qleverfile has TEXT_INDEX = none — nothing to build" )
            return
        if self.is_running:
            self.server_stop( echo = echo )
        self._qlever(
            "add-text-index",
            "--text-index", self.user_text_index,
            "--overwrite-existing",
            echo = echo,
        )
        # Text index now on disk — restart so the server loads it.
        self._has_current_text_index = True
        self._qlever( *self._start_args(), echo = echo )
        self.is_running = True

    def complete_index( self, echo = True ):
        """Assemble the complete index from ALL checkpoints, plus the text index.

        Unlike the incremental ``_finalize_index`` (which may be restricted to a
        dependency-closure ``index_scope`` and always skips the text index),
        this ignores ``index_scope``, includes *every* on-disk checkpoint, and
        -- if the user's Qleverfile sets ``TEXT_INDEX`` -- builds the text index
        too.  This is the only path that guarantees a complete, queryable,
        text-indexed server.
        """
        entries = self._collect_checkpoint_entries( echo = echo )   # all checkpoints, full scope
        if not entries:
            stop_error( "--qlever_complete: no checkpoints found to assemble into an index." )
        print_task( "Assemble complete qlever index from all checkpoints" )
        self._patch_qleverfile( entries, echo = echo )
        if self.is_running:
            self.server_stop( echo = echo )
        # Clear the complete-marker BEFORE mutating the index: it must exist only
        # when a complete build has fully succeeded, otherwise a crash mid-rebuild
        # would leave a stale marker and report a broken index as 'ok'.
        self._clear_index_complete()
        # Wipe stale text-index files so they cannot mismatch the rebuilt main index.
        for f in glob.glob( os.path.join( self.qleverdir, f"{self.repository}.text.*" ) ):
            os.remove( f )
            if echo: report( "wiped stale text index", os.path.basename( f ) )
        self._has_current_text_index = False
        self._qlever( "index", "--text-index", "none", "--overwrite-existing", echo = echo )
        self._abort_if_index_log_has_error()
        if self.user_text_index and self.user_text_index.lower() != "none":
            self._qlever( "add-text-index", "--text-index", self.user_text_index, "--overwrite-existing", echo = echo )
            self._has_current_text_index = True
        else:
            print_warn( "Qleverfile has TEXT_INDEX = none — building complete index without a text index" )
        self._qlever( *self._start_args(), echo = echo )
        self.is_running = True
        # The complete production index is now in sync: mark it so refine_status
        # reports its datasets as 'ok' rather than 'READY'.
        self._mark_index_complete()

    # ------------------------------------------------------------------ #
    # Polymorphic workflow hooks (see GenericClient for the contracts)
    #
    # qlever is a static-index backend: data is ingested by staging files into
    # an offline index build, SPARQL updates live in an in-memory delta lost on
    # rebuild/restart, and per-dataset state is persisted as .nt.gz checkpoints.
    # These overrides keep all of that off the generic kgsteward workflow.
    # ------------------------------------------------------------------ #

    @property
    def supports_sparql_load( self ):
        return False   # static index: stage files, never SPARQL LOAD

    def load_url( self, path, context, echo = True ):
        # qlever cannot defer LOAD -- download immediately and stage for indexing
        # (void:dataDump is baked in by _stage_file).
        self.load_url_as_file( path, context, echo = echo )

    def update_set_offline( self, names, config, name2context, sha_of ):
        """When the server is stopped, the SPARQL status query would return
        all-EMPTY, so use the .nt.gz checkpoints as the source of truth:
        a dataset needs (re)processing unless a *current* checkpoint exists.
        Frozen datasets are never touched by -C.  Returns None when the server
        is running (kgsteward then uses the online status query)."""
        if self.is_running:
            return None
        report( "qlever server stopped", "using checkpoints to determine update set" )
        frozen_of = { t["name"]: bool( t.get( "frozen", False ) ) for t in config["dataset"] }
        update = set()
        for name in names:
            if frozen_of.get( name ):
                continue   # -C has no effect on frozen datasets (yaml 'frozen' contract)
            if not self.has_checkpoint( name2context[ name ], sha_of( name ) ):
                update.add( name )
        return update

    def plan_index_scope( self, update_names, config, name2context, echo = True ):
        """Restrict the rebuilt index to the dependency closure of the datasets
        being processed (update set + transitive parents).  Unrelated datasets
        keep their checkpoints on disk but stay out of the rebuilt index until a
        --qlever_complete run reassembles everything."""
        if not update_names:
            return
        parents_of = { t["name"]: list( t.get( "parent", [] ) or [] ) for t in config["dataset"] }
        frozen_of  = { t["name"]: bool( t.get( "frozen", False ) )     for t in config["dataset"] }
        scope = set()
        stack = list( update_names )
        while stack:
            n = stack.pop()
            if n in scope:
                continue
            scope.add( n )
            stack.extend( parents_of.get( n, [] ) )
        # A required parent that is NOT being processed this run must already
        # have a checkpoint, otherwise the scoped index would silently miss data
        # that the updates query.  A *frozen* parent without one is an
        # intentional exclusion (its dependants are rebuilt without its data).
        for n in scope:
            if n not in update_names and not self.has_checkpoint( name2context[ n ] ):
                if frozen_of.get( n ):
                    print_warn(
                        "Frozen parent '" + n + "' has no checkpoint; excluded from the index, so "
                        "its dependants are rebuilt WITHOUT its data. Load it explicitly with -d " + n + "."
                    )
                    continue
                stop_error(
                    "Dataset '" + n + "' is a required parent in the dependency scope but has "
                    "no checkpoint. Include it in the run (e.g. add it to -d) or build it first."
                )
        self.index_scope = { name2context[ n ] for n in scope }
        report( "qlever index scope (datasets)", ", ".join( sorted( scope ) ) )

    def warn_if_unindexed( self, name, context ):
        if not self.has_checkpoint( context ) and self.has_index:
            print_warn( f"No checkpoint for skipped dataset '{name}'; it will be absent from the index." )

    def queue_persist( self, context, sha256 = None ):
        self.mark_rebuild( context, sha256 )

    def flush_pending( self, echo = True ):
        if self.pending_files or self.pending_updates:
            self.server_start( echo = echo )

    def finalize( self, complete, echo = True ):
        if complete:
            print_break()
            print_task( "Assemble complete qlever index (all checkpoints + text index)" )
            self.complete_index( echo = echo )

    def ensure_running( self, echo = True ):
        if not self.is_running and self.has_index:
            print_break()
            print_task( "Start qlever server" )
            self.server_start( echo = echo )

    def can_restamp( self, context ):
        return self.has_checkpoint( context )

    def refine_status( self, config, echo = False ):
        """Mark current-but-unassembled checkpoints as READY.

        qlever lifecycle (per dataset):

            EMPTY / UPDATE  --(-C / -d / --qlever_upload_quads)-->  READY
            READY           --(--qlever_complete)----------------->  ok

        A dataset is READY when a *current* checkpoint exists on disk (currency
        is verified against the input checksum stashed in ``target_sha256``) but
        the complete production index -- the one ``--qlever_complete`` assembles
        from every checkpoint, including the text index -- is not in sync.  Only
        once that complete index has been built does the dataset become ``ok``.

        Frozen datasets are intentionally left untouched (their status handling
        is a separate, future concern).
        """
        complete = self._complete_index_in_sync()
        for item in config["dataset"]:
            if item.get( "frozen" ):
                continue
            context = item["context"]
            if not self.has_checkpoint( context, item.get( "target_sha256" ) ):
                continue   # no current checkpoint -> leave the base EMPTY/UPDATE status
            item["status"] = "ok" if complete else "READY"

    # ------------------------------------------------------------------ #
    # Public data-loading API
    # ------------------------------------------------------------------ #

    def load_from_file( self, filename, context, headers = {}, echo = True ):
        """Stage *filename* for deferred indexing into graph *context*."""
        self.pending_files.extend( self._stage_file( filename, context, echo = echo ) )

    def load_url_as_file( self, url, context, echo = True ):
        """Download *url* immediately and stage it for deferred indexing into graph *context*.

        ``void:dataDump`` records the original *url* (not the local temp path).
        Hardened curl flags fail fast on upstream throttling / dropped connections:

          --connect-timeout 30           give up if no TCP handshake in 30s
          --speed-time 60 --speed-limit 1024
                                         abort if avg < 1 KB/s for 60s
          --retry 3 --retry-delay 5      transient blip → quick retry
        """
        basename = url.split( "?" )[0].split( "/" )[-1]
        _name, _ext = os.path.splitext( basename )
        if _ext.lower() in ( ".gz", ".bz2", ".xz" ):
            # Preserve compound extensions such as .ttl.gz, .nt.gz, .rdf.xz
            _, _inner = os.path.splitext( _name )
            suffix = ( _inner + _ext ) if _inner else _ext
        else:
            suffix = _ext
        suffix = suffix or ".nt"

        with tempfile.NamedTemporaryFile( delete = False, suffix = suffix ) as tmp:
            tmp_path = tmp.name
        try:
            curl_cmd = [
                "curl", "-L",
                "--connect-timeout", "30",
                "--speed-time", "60", "--speed-limit", "1024",
                "--retry", "3", "--retry-delay", "5",
                "-o", tmp_path, url,
            ]
            # Quiet the progress meter unless verbose; keep errors visible.
            if not echo:
                curl_cmd[ 1:1 ] = [ "--silent", "--show-error" ]
            if echo:
                print( colored( " ".join( curl_cmd ), "cyan" ), flush = True )
            r = subprocess.run( curl_cmd )
            if r.returncode != 0:
                stop_error( f"curl download failed for: {url}  (exit {r.returncode})" )
            self.pending_files.extend( self._stage_file( tmp_path, context, void_iri = url, echo = echo ) )
        finally:
            if os.path.exists( tmp_path ):
                os.unlink( tmp_path )

    def mark_rebuild( self, context_iri, sha256 = None ):
        """Queue a checkpoint-dump sentinel for *context_iri* in pending_updates.

        When ``_apply_pending_updates`` hits the ``(context_iri, sha256)`` tuple
        it calls ``dump_checkpoint`` — the CONSTRUCT query against the running
        server returns the on-disk index merged with the in-memory delta from
        the preceding updates, so the checkpoint captures the complete
        post-update state.  No ``qlever rebuild-index`` is needed because the
        next ``_finalize_index`` rebuilds the on-disk index from scratch
        using every checkpoint + the new dataset's staged files.

        *sha256* (the dataset's kgsteward checksum, if known) is recorded in the
        checkpoint sidecar so ``has_checkpoint`` can judge currency offline.
        """
        self.pending_updates.append( ( context_iri, sha256 ) )

    # ------------------------------------------------------------------ #
    # Public SPARQL API
    # ------------------------------------------------------------------ #

    def get_endpoint_update( self ):
        # qlever exposes update on the same endpoint as query — kgsteward keeps
        # the two endpoints separate generically, but for qlever the "update"
        # endpoint is unused (we POST `update=` to the query URL).
        return ""

    def list_repository( self ):
        return [ self.repository ]

    def sparql_query( self, sparql, status_code_ok = [ 200, 400, 500 ], echo = True, timeout = None ):
        if not self.is_running:
            return None
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
        """Queue a SPARQL update for execution at the next ``_apply_pending_updates``.

        Always queues, even when the server is running.  Rationale: the
        per-dataset loop ends each iteration with ``server_start`` →
        ``_finalize_index`` → rebuild → ``_apply_pending_updates``.  Executing
        updates immediately against an in-place running server would let the
        rebuild wipe their in-memory effect before ``dump_checkpoint`` could
        capture it — the silent metadata-loss bug we hit in production.

        ``void:dataDump`` triples are dropped here — they are already baked
        into the staged files by ``_stage_file``.
        """
        if "void:dataDump" in sparql or "ns/void#dataDump" in sparql:
            return
        self.pending_updates.append( sparql )

    def _do_sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        """POST a SPARQL update to the running server and record timing stats.

        Called only from ``_apply_pending_updates``; not part of the public API.
        Adds ``timeout=999999s`` plus the access token to the form data so the
        per-query timeout in the Qleverfile (appropriate for interactive
        queries) doesn't abort long-running bulk updates.
        """
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        self._sparql_update_counter += 1
        sha = hashlib.sha1( sparql.encode() ).hexdigest()[:8]
        t_start = time.time()
        try:
            r = http_call(
                { 'method': 'POST', 'url': self.endpoint_query,
                  'headers': { 'Content-Type': 'application/x-www-form-urlencoded' },
                  'data': {
                      'update':       sparql,
                      'access-token': self.access_token,
                      'timeout':      '999999s',
                  } },
                status_code_ok, echo,
            )
        except requests.exceptions.ConnectionError as exc:
            # The server slammed the socket shut without sending an HTTP response.
            # This is NOT a SPARQL error -- those come back as HTTP 200 with a
            # body status of "ERROR".  It means the qlever-server *process* died
            # mid-update, almost always an out-of-memory kill while materializing
            # the INSERT/DELETE result.  MEMORY_FOR_QUERIES bounds queries, NOT
            # update materialization, so lowering it does not prevent this.
            #
            # A retry is unsafe: qlever updates live in an in-memory delta, so a
            # crash (and the docker auto-restart that follows) discards the delta
            # from THIS dataset's earlier updates too -- replaying just this one
            # against the restarted server would build inconsistent data.  Fail
            # loudly instead; transactional checkpoints keep prior datasets safe.
            self.is_running = False
            self.sparql_update_stats.append( {
                "n":               self._sparql_update_counter,
                "ts":              time.strftime( "%Y-%m-%dT%H:%M:%S" ),
                "elapsed_ms":      int( ( time.time() - t_start ) * 1000 ),
                "qlever_total_ms": None,
                "http_status":     "CONNECTION_LOST",
                "size_chars":      len( sparql ),
                "sha1_8":          sha,
                "first_line":      _first_meaningful_sparql_line( sparql ),
                "error":           "server closed connection mid-update (likely OOM crash)",
            } )
            stop_error(
                "qlever server closed the connection without responding while applying "
                f"SPARQL update #{self._sparql_update_counter} "
                f"(sha1 {sha}, {len( sparql )} chars):\n"
                f"    {_first_meaningful_sparql_line( sparql )}\n"
                "The server process crashed mid-update -- this is a hard crash, not a SPARQL "
                "error, and is almost always an out-of-memory kill: the INSERT/DELETE result "
                "materialization exceeded available RAM.  Note MEMORY_FOR_QUERIES limits queries, "
                "NOT update materialization, so lowering it does not help.\n"
                "  -> give Docker more RAM, or split/simplify this update so its intermediate "
                "result is smaller;\n"
                "  -> checkpoints are transactional, so already-loaded datasets are intact; this "
                "dataset has no checkpoint and will be reprocessed on the next run.\n"
                f"  -> underlying error: {exc}"
            )
        elapsed_ms = int( ( time.time() - t_start ) * 1000 )

        # Best-effort extraction of qlever's server-side timing + error.
        qlever_total_ms = None
        qlever_error    = None
        try:
            body = r.json()
            if isinstance( body, dict ):
                t = body.get( "time" )
                if isinstance( t, dict ):
                    qlever_total_ms = t.get( "total" )
                if body.get( "status" ) == "ERROR":
                    qlever_error = body.get( "exception" )
                elif isinstance( body.get( "operations" ), list ) and body["operations"]:
                    op_t = body["operations"][0].get( "time" )
                    if isinstance( op_t, dict ) and qlever_total_ms is None:
                        qlever_total_ms = op_t.get( "total" )
        except Exception:
            pass

        self.sparql_update_stats.append( {
            "n":               self._sparql_update_counter,
            "ts":              time.strftime( "%Y-%m-%dT%H:%M:%S" ),
            "elapsed_ms":      elapsed_ms,
            "qlever_total_ms": qlever_total_ms,
            "http_status":     r.status_code,
            "size_chars":      len( sparql ),
            "sha1_8":          sha,
            "first_line":      _first_meaningful_sparql_line( sparql ),
            "error":           ( qlever_error[:200] if qlever_error else "" ),
        } )

        if r.status_code != 200 and r.text:
            print_warn( r.text )
        return r

    def dump_sparql_update_stats( self, filepath ):
        """Write per-call sparql_update timings to *filepath* as TSV.

        Useful for diagnosing slow updates in a single backend and for benchmark
        comparison between backends (run with each backend, then join the TSVs
        on ``sha1_8`` — same SPARQL → same hash → same row).
        """
        if not self.sparql_update_stats:
            report( "sparql update stats", "(empty — nothing to dump)" )
            return
        cols = [ "n", "ts", "elapsed_ms", "qlever_total_ms", "http_status",
                 "size_chars", "sha1_8", "first_line", "error" ]
        with open( filepath, "w" ) as f:
            f.write( "\t".join( cols ) + "\n" )
            for s in self.sparql_update_stats:
                f.write( "\t".join(
                    str( s[c] ) if s.get( c ) is not None else ""
                    for c in cols
                ) + "\n" )
        report( "dumped sparql update stats", f"{filepath}  ({len(self.sparql_update_stats)} entries)" )

    def list_context( self, echo = True ):
        # qlever does not enumerate graphs via GRAPH ?g {} (empty body); the
        # full triple pattern is required.
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g { ?s ?p ?o }}", echo = echo )
        if r is None:
            return set()
        return { rec["g"]["value"] for rec in r.json()["results"]["bindings"] if "g" in rec }

    def drop_context( self, context, echo = True ):
        """No-op for qlever.

        Removal happens through ``invalidate_checkpoint`` + the next
        ``_finalize_index`` rebuild excluding the dropped context.  A SPARQL
        ``DELETE WHERE { GRAPH <ctx> { ?s ?p ?o } }`` on a large graph can
        OOM-kill qlever-server with ``RemoteDisconnected`` — kgsteward
        used to send one here and we removed it.
        """
        if echo: report( "drop_context", f"no-op for qlever (will be excluded from next index rebuild): {context}" )

    # ------------------------------------------------------------------ #
    # Checkpoint management
    # ------------------------------------------------------------------ #

    def checkpoint_path( self, context_iri ):
        """Filesystem path of the .nt.gz checkpoint for *context_iri*."""
        h8   = hashlib.sha1( context_iri.encode() ).hexdigest()[:8]
        safe = re.sub( r"[^a-zA-Z0-9_-]", "_", context_iri.rstrip( "/" ).split( "/" )[-1] )[:40]
        return os.path.join( self.qleverdir, f"{safe}_{h8}.nt.gz" )

    def _complete_marker_path( self ):
        """Path of the sentinel that records 'the complete index is in sync'.

        Written by ``complete_index`` after a successful full (all-checkpoints +
        text-index) build; cleared by any partial/bootstrap rebuild that
        invalidates that completeness (``_finalize_index``, and -- via the
        ``<repository>.*`` wipe -- ``rewrite_repository`` / ``upload_quads``).
        Named ``<repository>.*`` so rewrite_repository removes it automatically.
        """
        return os.path.join( self.qleverdir, f"{self.repository}.kgsteward-complete" )

    def _mark_index_complete( self ):
        with open( self._complete_marker_path(), "w" ) as f:
            f.write( "complete\n" )

    def _clear_index_complete( self ):
        marker = self._complete_marker_path()
        if os.path.isfile( marker ):
            os.remove( marker )

    def _complete_index_in_sync( self ):
        """True iff the on-disk index is the complete one assembled from every
        checkpoint (so all current checkpoints are served and, if configured,
        the text index is built).  Any per-dataset/scoped rebuild or bootstrap
        clears the marker, so this stays False until the next --qlever_complete."""
        return self.has_index and os.path.isfile( self._complete_marker_path() )

    def has_checkpoint( self, context_iri, sha256 = None ):
        """True iff a completed checkpoint exists for *context_iri*.

        Completeness is the presence of the ``.nt.gz.json`` sidecar, which is
        written *after* the ``.nt.gz`` and acts as the atomic completeness
        marker.

        When *sha256* (the dataset's current kgsteward checksum) is supplied the
        check is also *currency-aware*: the checksum recorded in the sidecar
        must match.  This lets the stopped-server ``-C`` resume tell an
        out-of-date checkpoint from a current one without querying the index.
        A sidecar written before checksums were recorded (no ``sha256`` field)
        is accepted on presence alone, so pre-existing checkpoints stay valid.
        """
        sidecar = self.checkpoint_path( context_iri ) + ".json"
        if not os.path.isfile( sidecar ):
            return False
        if sha256 is None:
            return True
        try:
            with open( sidecar ) as f:
                stored = json.load( f ).get( "sha256" )
        except Exception:
            return False
        if stored is None:
            return True
        return stored == sha256

    def invalidate_checkpoint( self, context_iri ):
        """Delete the checkpoint files for *context_iri* (both ``.nt.gz`` and sidecar).

        Not used by the normal per-dataset flow (which keeps the old
        checkpoint as a transactional fallback).  Retained as a public API
        for explicit administrative use: drop a dataset from the managed
        set by removing its checkpoint, then trigger any rebuild — the
        next ``_finalize_index`` will exclude this context.
        """
        path    = self.checkpoint_path( context_iri )
        sidecar = path + ".json"
        for fn in ( path, sidecar ):
            if os.path.isfile( fn ):
                os.remove( fn )
                report( "invalidated checkpoint", os.path.basename( fn ) )

    def dump_checkpoint( self, context_iri, sha256 = None, echo = True ):
        """Save the named graph as ``<safe>_<h8>.nt.gz`` + ``.nt.gz.json`` sidecar.

        Two-step atomic write:

          1. Dump CONSTRUCT response to ``<path>.tmp``, then
             ``os.replace(tmp, path)`` — the .nt.gz is either the OLD or the
             NEW content, never partial.
          2. Write the sidecar last; its presence is the completeness marker.
             It records the named-graph IRI and, when known, the dataset's
             kgsteward checksum (*sha256*) so ``has_checkpoint`` can judge
             currency offline.

        Makes checkpointing transactional: until the new dump completes, the
        old checkpoint stays on disk as a fallback.
        """
        path     = self.checkpoint_path( context_iri )
        fname    = os.path.basename( path )
        sidecar  = path + ".json"
        tmp_path = path + ".tmp"
        sparql   = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{context_iri}> {{ ?s ?p ?o }} }}"
        if echo:
            print( colored( f"dump checkpoint → {fname}", "cyan" ), flush = True )
        r = http_call(
            { "method": "POST", "url": self.endpoint_query,
              "headers": { "Accept": "application/n-triples",
                           "Content-Type": "application/x-www-form-urlencoded" },
              "data": { "query": sparql } },
            [ 200 ], echo = False,
        )
        with gzip.open( tmp_path, "wb" ) as f:
            f.write( r.content )
        os.replace( tmp_path, path )    # atomic on POSIX
        with open( sidecar, "w" ) as f:
            json.dump( { "graph": context_iri, "sha256": sha256 }, f )
        if echo: report( "checkpoint saved", fname )

    # ------------------------------------------------------------------ #
    # Repository / bulk-adoption operations
    # ------------------------------------------------------------------ #

    def rewrite_repository( self, _server_config_filename = None, echo = True ):
        """Full reset of qleverdir: stop server, wipe everything kgsteward and qlever own, restore Qleverfile.

        After this returns the qleverdir contains only the freshly-copied
        Qleverfile.  The next ``_finalize_index`` rebuilds the index from
        scratch -- which, immediately after ``-I``, means rebuilding from
        whatever new datasets get staged (no checkpoints survived).

        What gets removed:

          - the running server (Docker container or native process)
          - ``input/``                           transient staging area
          - ``*.nt.gz``                          kgsteward checkpoints
          - ``*.nt.gz.json``                     atomic-completion sidecars
          - ``<NAME>.index.*``                   main index permutations
          - ``<NAME>.internal.index.*``          ql:has-pattern internal index
          - ``<NAME>.text.*``                    optional text index files
          - ``<NAME>.vocabulary.*``              external on-disk vocabulary
          - ``<NAME>.meta-data.json``            server bootstrap metadata
          - ``<NAME>.settings.json``             parsed SETTINGS_JSON
          - ``<NAME>.index-log.txt``             last index build log
          - ``<NAME>.server-log.txt``            last server start log
          - ``previous.*`` / ``rebuild.*``       leftover rebuild-index snapshots

        *_server_config_filename* is accepted for cross-backend signature
        parity (GraphDB et al. recreate the repository from a config file);
        qlever has nothing equivalent, so the argument is ignored.
        """
        if self.is_running:
            self.server_stop( echo = echo )

        # Transient staging area
        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            if echo: report( "wiped", input_dir )

        # kgsteward-managed checkpoints + their atomic-completion sidecars
        for path in sorted( glob.glob( os.path.join( self.qleverdir, "*.nt.gz" ) ) ):
            os.remove( path )
            if echo: report( "wiped checkpoint", os.path.basename( path ) )
        for path in sorted( glob.glob( os.path.join( self.qleverdir, "*.nt.gz.json" ) ) ):
            os.remove( path )
            if echo: report( "wiped checkpoint sidecar", os.path.basename( path ) )

        # On-disk qlever index for this repository (everything named <NAME>.*)
        for path in sorted( glob.glob( os.path.join( self.qleverdir, f"{self.repository}.*" ) ) ):
            os.remove( path )
            if echo: report( "wiped index file", os.path.basename( path ) )

        # Leftover snapshot directories from a prior `qlever rebuild-index`
        for path in sorted(
            glob.glob( os.path.join( self.qleverdir, "previous.*" ) )
            + glob.glob( os.path.join( self.qleverdir, "rebuild.*" ) )
        ):
            if os.path.isdir( path ):
                shutil.rmtree( path )
                if echo: report( "wiped rebuild dir", os.path.basename( path ) )

        # Restore the user's Qleverfile (verbatim -- _patch_qleverfile will
        # re-sync + patch when the next _finalize_index runs).
        user_real = os.path.realpath( self.qleverfile )
        dest      = os.path.join( self.qleverdir, "Qleverfile" )
        if user_real != ( os.path.realpath( dest ) if os.path.lexists( dest ) else None ):
            shutil.copy2( user_real, dest )
            if echo: report( "copied Qleverfile", dest )

        self.pending_files           = []
        self.pending_updates         = []
        self._has_current_text_index = False

    def upload_quads( self, name2context, echo = True ):
        """Bootstrap a qlever index from a quad dump, verify it, dump per-graph checkpoints.

        End-to-end "adoption" operation triggered by ``--qlever_upload_quads``.
        WARNING: wipes the entire content of qleverdir before proceeding.
        Use case: the user has a big ``.nq.gz`` (or any qlever-loadable) dump
        produced outside kgsteward and wants to bring its content under
        kgsteward management.  Bulk-loading with ``qlever index`` is much
        faster than ingesting dataset-by-dataset, so we let qlever do it
        natively and then capture the result as per-graph checkpoints.

        Returns the sorted list of dumped graph IRIs.
        """
        if self.is_running:
            self.server_stop( echo = echo )

        print_task( "Reset qleverdir to user's Qleverfile (wipe checkpoints, input/)" )
        self.rewrite_repository( echo = echo )
        self._ensure_host_name_localhost()

        print_task( "Build qlever index from the configured INPUT_FILES (bulk load)" )
        self._qlever( "index", "--overwrite-existing", echo = echo )

        print_task( "Start qlever server from the freshly-built index" )
        self._qlever( *self._start_args(), echo = echo )
        self.is_running = True

        print_task( "Verify graphs in the loaded index against the YAML datasets" )
        graphs_in_server = self.list_context( echo = False )
        if not graphs_in_server:
            stop_error( "No named graphs found in the loaded index — refusing to proceed.\n"
                        "Check INPUT_FILES / CAT_INPUT_FILES in the Qleverfile and that the dump "
                        "contains quads (e.g. .nq, .nq.gz, .trig)." )

        contexts_in_yaml = set( name2context.values() )
        matched = sorted( graphs_in_server & contexts_in_yaml )
        orphan  = sorted( graphs_in_server - contexts_in_yaml )
        missing = sorted( contexts_in_yaml - graphs_in_server )

        context2name = { c: n for n, c in name2context.items() }
        for g in matched:
            report( "matched", f"{context2name[g]} ← {g}" )
        for g in orphan:
            print_warn( f"Graph in dump but no matching dataset in YAML: {g}  (kept as orphan-but-preserved checkpoint)" )
        for c in missing:
            print_warn( f"Dataset '{context2name[c]}' in YAML but no data found in the loaded index ({c})" )

        print_task( f"Dump {len( graphs_in_server )} named graph(s) as checkpoints" )
        for g in sorted( graphs_in_server ):
            self.dump_checkpoint( g, echo = echo )

        # The bulk index built here is NOT the complete production index: it has
        # no text index and was assembled from the dump, not from the checkpoints.
        # rewrite_repository above already cleared the complete-marker, so these
        # datasets report READY.  Point the user at the assembling step.
        wants_text = bool( self.user_text_index ) and self.user_text_index.lower() != "none"
        print_warn(
            "Datasets are READY (checkpoints captured) but not yet in production"
            + ( " and the text index is NOT built" if wants_text else "" )
            + ". Run with --qlever_complete to assemble the complete index"
            + ( " + text index" if wants_text else "" )
            + " from all checkpoints (READY -> ok)."
        )
        return sorted( graphs_in_server )
