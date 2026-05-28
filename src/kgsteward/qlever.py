import configparser
import glob
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
            if echo:
                print( colored( f"riot --output=ntriples {src} > {dest_path}", "cyan" ), flush = True )
            with open( dest_path, "wb" ) as nt_out:
                riot = subprocess.run( ["riot", "--output=ntriples", src], stdout = nt_out )
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
        """Write MULTI_INPUT_JSON (and INPUT_FILES) into qleverdir/Qleverfile."""
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
        parser["index"]["INPUT_FILES"]     = file_paths
        parser["index"]["MULTI_INPUT_JSON"] = json.dumps( entries, separators = (",", ":") )

        with open( dest, "w" ) as f:
            parser.write( f )
        report( "INPUT_FILES",      file_paths )
        report( "MULTI_INPUT_JSON", f"{len(entries)} stream(s)" )

    def _finalize_index( self, echo = True ):
        """Patch Qleverfile, rebuild index, start server, apply queued updates.

        ``pending_updates`` may contain ``None`` sentinels inserted by ``mark_rebuild()``.
        Each sentinel triggers a ``rebuild-index`` at that point so that the preceding
        SPARQL updates are persisted before the next batch of updates is applied.
        """
        if not self.pending_files:
            print_warn( "_finalize_index called with no pending files — nothing to do." )
            return

        print_task( "Write MULTI_INPUT_JSON to Qleverfile" )
        self._patch_qleverfile( self.pending_files )

        if self.is_running:
            self.server_stop( echo = echo )

        print_task( "Run qlever index" )
        self._qlever( "index", echo = echo )

        print_task( "Start qlever server" )
        self._qlever( "start", echo = echo )
        self.is_running = True

        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "cleanup", input_dir )

        self.pending_files = []

        if self.pending_updates:
            n_updates = sum( 1 for u in self.pending_updates if u is not None )
            print_task( f"Apply {n_updates} queued SPARQL update(s) with per-dataset rebuild markers" )
            for item in self.pending_updates:
                if item is None:
                    self.server_rebuild_index( echo = echo )
                else:
                    self._do_sparql_update( item, echo = echo )
        self.pending_updates = []

    # ------------------------------------------------------------------ #
    # Server lifecycle
    # ------------------------------------------------------------------ #

    def server_start( self, echo = True ):
        if self.pending_files:
            self._finalize_index( echo = echo )
        else:
            self._qlever( "start", echo = echo )
            self.is_running = True

    def server_stop( self, echo = True ):
        self._qlever( "stop", echo = echo )
        self.is_running = False

    def server_rebuild_index( self, echo = True ):
        """Persist in-memory SPARQL updates by rebuilding the qlever index."""
        print_task( "Rebuild qlever index to persist SPARQL updates" )
        self._qlever( "rebuild-index", "--restart-when-finished", echo = echo )
        self.is_running = True

    # ------------------------------------------------------------------ #
    # Public data-loading API
    # ------------------------------------------------------------------ #

    def rewrite_repository( self, _config_file = None, echo = True ):
        """Reset staging area and copy user's Qleverfile into qleverdir."""
        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "wiped", input_dir )
        user_real = os.path.realpath( self.qleverfile )
        dest      = os.path.join( self.qleverdir, "Qleverfile" )
        if user_real != ( os.path.realpath( dest ) if os.path.lexists( dest ) else None ):
            shutil.copy2( user_real, dest )
            report( "copied Qleverfile", dest )
        self.pending_files   = []
        self.pending_updates = []

    def load_from_file( self, filename, context, headers = {}, echo = True ):
        """Stage *filename* for deferred indexing into graph *context*."""
        self.pending_files.extend( self._stage_file( filename, context, echo = echo ) )

    def load_url_as_file( self, url, context, echo = True ):
        """Download *url* immediately and stage it for deferred indexing into graph *context*.

        The void:dataDump triple records the original *url* (not the local temp path).
        This is the correct approach for qlever because a SPARQL LOAD cannot be deferred —
        the local file server may stop before the index is eventually built.
        """
        suffix = os.path.splitext( url.split( "?" )[0].split( "/" )[-1] )[1] or ".nt"
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

    def mark_rebuild( self ):
        """Insert a rebuild-index sentinel into the pending_updates queue.

        When ``_finalize_index`` processes the queue it will call ``server_rebuild_index``
        at each sentinel, persisting the preceding SPARQL updates before continuing.
        This gives one rebuild-index per dataset that has an ``update:`` section.
        """
        self.pending_updates.append( None )

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
            report( "queued update", sparql[:60].replace( "\n", " " ) + "…" )
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
