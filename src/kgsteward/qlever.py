import configparser
import glob
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile

from dumper import dump
from .common import *
from .generic import GenericClient

# Natively supported qlever formats (without riot conversion), ± .gz
_QLEVER_NATIVE = { ".ttl": "ttl", ".nt": "nt" }

def _qlever_fmt( filename ):
    """Return qlever format token ("ttl"/"nt") or None if riot is needed."""
    name = filename.lower()
    if name.endswith( ".gz" ): name = name[ :-3 ]
    return _QLEVER_NATIVE.get( os.path.splitext( name )[1] )


def parse_qleverfile( qleverfile ):
    """Read a Qleverfile and return (location, repository, system, access_token)."""
    real_path = os.path.realpath( qleverfile )
    if not os.path.isfile( real_path ):
        stop_error( "Qleverfile not found: " + qleverfile )
    parser = configparser.ConfigParser( interpolation = None )
    parser.read( real_path )
    if "data" not in parser or "NAME" not in parser["data"]:
        stop_error( "Missing [data] NAME in Qleverfile: " + real_path )
    repository   = parser["data"]["NAME"]
    host         = parser.get( "server",  "HOST_NAME",    fallback = "localhost" )
    port         = parser.get( "server",  "PORT",         fallback = "7019" )
    system       = parser.get( "runtime", "SYSTEM",       fallback = "docker" )
    access_token = parser.get( "server",  "ACCESS_TOKEN", fallback = "" )
    return f"http://{host}:{port}", repository, system, access_token


class QleverClient( GenericClient ):

    def __init__( self, qleverfile, qleverdir, access_token = None, echo = True ):
        for tool in ("qlever", "riot"):
            if shutil.which( tool ) is None:
                stop_error( f"{tool} not found on PATH" )

        location, repository, system, access_token_from_file = parse_qleverfile( qleverfile )

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
        self.pending_files   = []   # multi_input_json entries staged for deferred index
        self.pending_updates = []   # SPARQL updates queued pre-index

        # Remove any leftover input/ directory from a previous crashed staging phase.
        # pending_files is always reset above, so orphaned staged files must be wiped.
        input_dir = os.path.join( qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            print_warn( f"Removed stale input/ from previous run: {input_dir}" )

        try:
            http_call( { 'method': 'GET', 'url': location }, [ 200, 404 ], echo = echo )
            self.is_running = True
        except:
            self.is_running = False
        report( "qlever server", "running" if self.is_running else "stopped" )

    @property
    def has_index( self ):
        """True if a qlever index exists in qleverdir (i.e. indexing has been run at least once)."""
        return bool( glob.glob( os.path.join( self.qleverdir, f"{self.repository}.index.*" ) ) )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _qlever( self, *args, echo = True ):
        """Run a qlever CLI sub-command in qleverdir; stop on non-zero exit."""
        r = run_system_cmd( self.qlever_cmd + list( args ), echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( f"qlever {args[0]} failed" )
        return r

    def _stage_file( self, filename, context_iri, void_iri = None, echo = True ):
        """Copy/convert *filename* into qleverdir/input/ and return multi_input_json entries.

        *void_iri* overrides the IRI recorded in the void:dataDump triple (defaults to file://<src>).
        Pass the original URL when staging a downloaded file so provenance points to the source.

        riot is invoked with ``--set jdk.xml.maxGeneralEntitySizeLimit=0`` to lift the
        JDK default cap on XML general entity sizes, which can be exceeded by large
        RDF/XML ontologies (e.g. OWL files with many datatype declarations).
        """
        input_dir = os.path.join( self.qleverdir, "input" )
        os.makedirs( input_dir, exist_ok = True )

        src  = os.path.abspath( filename )
        h8   = hashlib.sha1( src.encode() ).hexdigest()[:8]
        stem = os.path.splitext( re.sub( r"\.(gz|bz2|xz)$", "", os.path.basename( src ), flags = re.IGNORECASE ) )[0]

        fmt = _qlever_fmt( src )
        if fmt is not None:
            is_gz     = src.lower().endswith( ".gz" )
            ext_full  = f".{fmt}.gz" if is_gz else f".{fmt}"
            dest_name = f"{stem}_{h8}{ext_full}"
            dest_path = os.path.join( input_dir, dest_name )
            if os.path.lexists( dest_path ):
                os.remove( dest_path )
            try:
                os.link( src, dest_path ); report( "hard-link", dest_path )
            except OSError:
                shutil.copy2( src, dest_path ); report( "copy", dest_path )
            cmd = f"zcat input/{dest_name}" if is_gz else f"cat input/{dest_name}"
        else:
            dest_name = f"{stem}_{h8}.nt"
            dest_path = os.path.join( input_dir, dest_name )
            riot_cmd  = [ "riot", "--set", "jdk.xml.maxGeneralEntitySizeLimit=0",
                          "--output=ntriples", src ]
            if echo:
                print( colored( " ".join( riot_cmd ) + f" > {dest_path}", "cyan" ), flush = True )
            with open( dest_path, "wb" ) as nt_out:
                riot = subprocess.run( riot_cmd, stdout = nt_out )
            if riot.returncode != 0:
                stop_error( f"riot conversion failed for: {src}" )
            fmt, cmd = "nt", f"cat input/{dest_name}"
            report( "staged (riot→nt)", dest_path )

        # Bake void:dataDump triple into the index (avoids a separate INSERT + rebuild)
        actual_void_iri = void_iri if void_iri is not None else f"file://{src}"
        void_name = f"{stem}_{h8}.void.nt"
        void_path = os.path.join( input_dir, void_name )
        with open( void_path, "w" ) as vf:
            vf.write( f"<{context_iri}> <http://rdfs.org/ns/void#dataDump> <{actual_void_iri}> .\n" )

        report( "staged", f"input/{dest_name}  (+ void triple)" )
        return [
            { "cmd": cmd,                           "format": fmt,  "graph": context_iri },
            { "cmd": f"cat input/{void_name}",      "format": "nt", "graph": context_iri },
        ]

    def _patch_qleverfile( self, entries ):
        """Write MULTI_INPUT_JSON (and INPUT_FILES) into qleverdir/Qleverfile.

        Also ensures ``HOST_NAME = localhost`` is set in ``[server]``.  Without
        this, the qlever CLI falls back to ``socket.gethostname()`` as the host
        for its liveness check (``/ping``), which is usually a non-loopback
        name that does *not* route to the Docker-mapped port on localhost.  The
        server then appears unreachable to the CLI even though it is running
        fine, causing ``qlever start`` to spin in its alive-polling loop forever.
        """
        dest = os.path.join( self.qleverdir, "Qleverfile" )
        if not os.path.lexists( dest ):
            shutil.copy2( os.path.realpath( self.qleverfile ), dest )
            report( "copied Qleverfile", dest )
        parser = configparser.RawConfigParser()
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

        # Guarantee that the qlever CLI probes localhost, not socket.gethostname()
        if "server" not in parser:
            parser["server"] = {}
        if "HOST_NAME" not in parser["server"]:
            parser["server"]["HOST_NAME"] = "localhost"

        with open( dest, "w" ) as f:
            parser.write( f )
        report( "INPUT_FILES",      file_paths )
        report( "MULTI_INPUT_JSON", f"{len(entries)} stream(s)" )

    def _collect_checkpoint_entries( self ):
        """Return MULTI_INPUT_JSON entries for all completed checkpoints.

        Reads ``*.nt.gz.json`` sidecar files in qleverdir.  Each sidecar records the
        named-graph IRI so its checkpoint can be fed directly into ``qlever index`` via
        MULTI_INPUT_JSON — no re-downloading or re-converting of source files required.
        The sidecar's presence is an atomic completeness marker: ``dump_checkpoint``
        writes the ``.nt.gz`` data file first, then the sidecar; a crash between the
        two writes leaves an orphaned ``.nt.gz`` that is simply ignored here.
        """
        entries = []
        for sidecar in sorted( glob.glob( os.path.join( self.qleverdir, "*.nt.gz.json" ) ) ):
            try:
                with open( sidecar ) as f:
                    meta = json.load( f )
                context_iri = meta["graph"]
            except Exception as e:
                print_warn( f"Skipping unreadable checkpoint sidecar {sidecar}: {e}" )
                continue
            nt_gz = sidecar[ :-5 ]   # strip ".json" → the .nt.gz path
            fname = os.path.basename( nt_gz )
            entries.append( { "cmd": f"zcat {fname}", "format": "nt", "graph": context_iri } )
            report( "checkpoint → index", fname )
        return entries

    def _apply_pending_updates( self, echo = True ):
        """Execute all queued SPARQL updates; rebuild-index + checkpoint at each sentinel.

        ``pending_updates`` is a list of strings (SPARQL updates) interleaved with
        ``(context_iri,)`` tuples inserted by ``mark_rebuild()``.  Each tuple triggers:
          1. ``server_rebuild_index`` — persists all preceding in-memory updates, and
          2. ``dump_checkpoint(context_iri)`` — saves the named graph as a ``.nt.gz`` file.
        """
        if not self.pending_updates:
            return
        n_updates = sum( 1 for u in self.pending_updates if not isinstance( u, tuple ) )
        print_task( f"Apply {n_updates} queued SPARQL update(s) with per-dataset rebuild+checkpoint" )
        for item in self.pending_updates:
            if isinstance( item, tuple ):
                context_iri = item[0]
                self.server_rebuild_index( echo = echo )
                if context_iri:
                    self.dump_checkpoint( context_iri, echo = echo )
            else:
                self._do_sparql_update( item, echo = echo )
        self.pending_updates = []

    def _finalize_index( self, echo = True ):
        """Auto-collect checkpoints, patch Qleverfile, build index, start server, apply updates.

        Implements per-dataset sequential persistence — the same model as the GraphDB driver:

          1. All completed ``.nt.gz`` checkpoints are auto-included (via ``.nt.gz.json``
             sidecars) so the rebuilt index always contains the full dataset history.
          2. The newly staged ``pending_files`` (for the current dataset) are appended.
          3. ``qlever index`` is rebuilt from scratch, then the server is started.
          4. ``_apply_pending_updates`` executes queued SPARQL updates and, for each
             ``(context_iri,)`` sentinel produced by ``mark_rebuild()``, calls
             ``server_rebuild_index`` + ``dump_checkpoint`` to persist the dataset
             immediately before moving on to the next one.
        """
        checkpoint_entries = self._collect_checkpoint_entries()
        all_entries = checkpoint_entries + self.pending_files

        if not all_entries:
            print_warn( "_finalize_index called with no files (no pending files, no checkpoints) — nothing to do." )
            return

        print_task( "Write MULTI_INPUT_JSON to Qleverfile" )
        self._patch_qleverfile( all_entries )

        if self.is_running:
            self.server_stop( echo = echo )

        # --overwrite-existing is required when rebuilding an index that
        # already exists on disk (i.e. every dataset after the first one).
        self._qlever( "index", "--overwrite-existing", echo = echo )
        self._qlever( "start", echo = echo )
        self.is_running = True

        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "cleanup", input_dir )

        self.pending_files = []

        self._apply_pending_updates( echo = echo )

    # ------------------------------------------------------------------ #
    # Server lifecycle
    # ------------------------------------------------------------------ #

    def server_start( self, echo = True ):
        if self.pending_files:
            self._finalize_index( echo = echo )
        elif self.pending_updates:
            # Updates only (no new files to stage): start from the existing index,
            # then apply the queued SPARQL updates + rebuild+checkpoint markers.
            # Guard: if no index exists there is nothing to start from — this indicates
            # that file loading was accidentally routed through sparql_update (pending_updates)
            # instead of load_from_file (pending_files).
            if not self.has_index:
                stop_error(
                    "qlever server_start: pending SPARQL updates but no index exists.\n"
                    "This usually means a file was loaded via sparql_update instead of "
                    "load_from_file — qlever requires all file data to go through the index."
                )
            if not self.is_running:
                self._qlever( "start", echo = echo )
                self.is_running = True
            self._apply_pending_updates( echo = echo )
        else:
            self._qlever( "start", echo = echo )
            self.is_running = True

    def server_stop( self, echo = True ):
        self._qlever( "stop", echo = echo )
        self.is_running = False

    def server_rebuild_index( self, echo = True ):
        """Persist in-memory SPARQL updates by rebuilding the qlever index."""
        self._qlever( "rebuild-index", "--restart-when-finished", echo = echo )
        self.is_running = True

    # ------------------------------------------------------------------ #
    # Public data-loading API
    # ------------------------------------------------------------------ #

    def rewrite_repository( self, _config_file = None, echo = True ):
        """Reset staging area, wipe all dataset checkpoints, and copy user's Qleverfile."""
        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "wiped", input_dir )
        for ckpt in glob.glob( os.path.join( self.qleverdir, "*.nt.gz" ) ):
            os.remove( ckpt )
            report( "wiped checkpoint", os.path.basename( ckpt ) )
        for sidecar in glob.glob( os.path.join( self.qleverdir, "*.nt.gz.json" ) ):
            os.remove( sidecar )
            report( "wiped checkpoint sidecar", os.path.basename( sidecar ) )
        user_real = os.path.realpath( self.qleverfile )
        dest      = os.path.join( self.qleverdir, "Qleverfile" )
        if user_real != ( os.path.realpath( dest ) if os.path.lexists( dest ) else None ):
            shutil.copy2( user_real, dest )
            report( "copied Qleverfile", dest )
        self.pending_files   = []
        self.pending_updates = []

    def checkpoint_path( self, context_iri ):
        """Return the filesystem path for the N-Triples checkpoint of *context_iri*."""
        h8   = hashlib.sha1( context_iri.encode() ).hexdigest()[:8]
        safe = re.sub( r"[^a-zA-Z0-9_-]", "_", context_iri.rstrip( "/" ).split( "/" )[-1] )[:40]
        return os.path.join( self.qleverdir, f"{safe}_{h8}.nt.gz" )

    def has_checkpoint( self, context_iri ):
        """Return True if a *completed* checkpoint exists for *context_iri*.

        A checkpoint is considered complete only when its ``.nt.gz.json`` sidecar is
        present.  ``dump_checkpoint`` writes the ``.nt.gz`` data file first and the
        sidecar last, so the sidecar acts as an atomic completeness marker that
        survives crashes and partial writes mid-dump.
        """
        return os.path.isfile( self.checkpoint_path( context_iri ) + ".json" )

    def invalidate_checkpoint( self, context_iri ):
        """Remove the checkpoint files for *context_iri* to force reprocessing.

        Both the ``.nt.gz`` data file and its ``.nt.gz.json`` sidecar are removed so
        that ``_collect_checkpoint_entries`` no longer includes stale data and
        ``has_checkpoint`` returns False.
        """
        path    = self.checkpoint_path( context_iri )
        sidecar = path + ".json"
        for fn in ( path, sidecar ):
            if os.path.isfile( fn ):
                os.remove( fn )
                report( "invalidated checkpoint", os.path.basename( fn ) )

    def dump_checkpoint( self, context_iri, echo = True ):
        """Query the running server and save the named graph as a compressed N-Triples checkpoint.

        Writes ``<safe>_<h8>.nt.gz`` (the data) and ``<safe>_<h8>.nt.gz.json`` (sidecar
        recording the graph IRI).  The sidecar is written *after* the data file so its
        presence acts as an atomic completeness marker — a crash between the two writes
        leaves no sidecar and the partial ``.nt.gz`` is ignored on the next run.
        """
        path    = self.checkpoint_path( context_iri )
        fname   = os.path.basename( path )
        sidecar = path + ".json"
        sparql  = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{context_iri}> {{ ?s ?p ?o }} }}"
        if echo:
            print( colored( f"dump checkpoint → {fname}", "cyan" ), flush = True )
        r = http_call(
            { "method": "POST", "url": self.endpoint_query,
              "headers": { "Accept": "application/n-triples",
                           "Content-Type": "application/x-www-form-urlencoded" },
              "data": { "query": sparql } },
            [ 200 ], echo = False
        )
        with gzip.open( path, "wb" ) as f:
            f.write( r.content )
        with open( sidecar, "w" ) as f:
            json.dump( { "graph": context_iri }, f )
        report( "checkpoint saved", fname )

    def load_from_file( self, filename, context, headers = {}, echo = True ):
        """Stage *filename* for deferred indexing into graph *context*."""
        self.pending_files.extend( self._stage_file( filename, context, echo = echo ) )

    def load_url_as_file( self, url, context, echo = True ):
        """Download *url* immediately and stage it for deferred indexing into graph *context*.

        The void:dataDump triple records the original *url* (not the local temp path).
        This is the correct approach for qlever because a SPARQL LOAD cannot be deferred —
        the local file server may stop before the index is eventually built.
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
            if echo:
                print( colored( f"curl -L {url} -o {tmp_path}", "cyan" ), flush = True )
            r = subprocess.run( ["curl", "-L", "-o", tmp_path, url] )
            if r.returncode != 0:
                stop_error( f"curl download failed for: {url}" )
            self.pending_files.extend( self._stage_file( tmp_path, context, void_iri = url, echo = echo ) )
        finally:
            if os.path.exists( tmp_path ):
                os.unlink( tmp_path )

    def mark_rebuild( self, context_iri = None ):
        """Insert a rebuild-index+checkpoint sentinel into the pending_updates queue.

        *context_iri* is the named graph to dump as a ``.nt.gz`` checkpoint after the
        rebuild-index completes.  When ``_apply_pending_updates`` hits this sentinel it
        calls ``server_rebuild_index`` (persisting all preceding SPARQL updates) and then
        ``dump_checkpoint``, giving one rebuild-index + one checkpoint per dataset.
        """
        self.pending_updates.append( ( context_iri, ) )

    # ------------------------------------------------------------------ #
    # SPARQL
    # ------------------------------------------------------------------ #

    def get_endpoint_update( self ):
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
            status_code_ok, echo
        )
        if r.status_code in ( 400, 500 ) and r.text:
            print_warn( r.text ); return None
        if r.status_code != 200:
            dump( r ); stop_error( "Unknown error" )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        """Execute a SPARQL update; queue it if the server is not yet running."""
        # void:dataDump triples are already baked into staged files — skip
        if "void:dataDump" in sparql or "ns/void#dataDump" in sparql:
            return
        if not self.is_running:
            self.pending_updates.append( sparql )
            return
        self._do_sparql_update( sparql, status_code_ok = status_code_ok, echo = echo )

    def _do_sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        r = http_call(
            { 'method': 'POST', 'url': self.endpoint_query,
              'headers': { 'Content-Type': 'application/x-www-form-urlencoded' },
              'data': { 'update': sparql, 'access-token': self.access_token } },
            status_code_ok, echo
        )
        if r.status_code != 200 and r.text:
            print_warn( r.text )
        return r

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        if r is None:
            return set()
        return { rec["g"]["value"] for rec in r.json()["results"]["bindings"] if "g" in rec }

    def drop_context( self, context, echo = True ):
        # DROP GRAPH is not yet supported by qlever; use DELETE WHERE instead.
        # If the server is not running, the graph will be absent from the rebuilt index anyway.
        if self.is_running:
            self.sparql_update(
                f"DELETE WHERE {{ GRAPH <{context}> {{ ?s ?p ?o }} }}",
                echo = echo
            )
