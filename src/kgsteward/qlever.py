from dumper import dump
import configparser
import hashlib
import os
import re
import shutil
import subprocess

from .common import *
from .generic import GenericClient

# RDF formats and compression schemes that qlever can read natively (no riot needed)
QLEVER_NATIVE_FORMATS      = { ".nt", ".ttl", ".nq", ".trig" }
QLEVER_NATIVE_COMPRESSIONS = { "", ".gz" }

def _is_qlever_native( filename ):
    """Return True if qlever can read the file directly without riot conversion."""
    name = filename.lower()
    for comp in QLEVER_NATIVE_COMPRESSIONS:
        if comp and name.endswith( comp ):
            name = name[ :-len( comp ) ]
            break
    _, ext = os.path.splitext( name )
    return ext in QLEVER_NATIVE_FORMATS

def parse_qleverfile( qleverfile ):
    """Read a Qleverfile (following symlinks) and return
    (location, repository, system, access_token).

    The Qleverfile is an INI-style file with at minimum:
      [data]
      NAME          = <dataset-name>   # used as the repository identifier
      [server]
      HOST_NAME     = localhost         # optional, defaults to localhost
      PORT          = 7019              # optional, defaults to 7019
      ACCESS_TOKEN  = <token>           # optional, defaults to ""
      [runtime]
      SYSTEM        = docker            # optional: docker | podman | native
    """
    real_path = os.path.realpath( qleverfile )
    if not os.path.isfile( real_path ):
        stop_error( "Qleverfile not found: " + qleverfile )
    parser = configparser.ConfigParser()
    parser.read( real_path )
    if "data" not in parser or "NAME" not in parser["data"]:
        stop_error( "Missing [data] NAME in Qleverfile: " + real_path )
    repository   = parser["data"]["NAME"]
    host         = parser.get( "server",  "HOST_NAME",    fallback = "localhost" )
    port         = parser.get( "server",  "PORT",         fallback = "7019" )
    system       = parser.get( "runtime", "SYSTEM",       fallback = "docker" )
    access_token = parser.get( "server",  "ACCESS_TOKEN", fallback = "" )
    location = f"http://{host}:{port}"
    return location, repository, system, access_token


class QleverClient( GenericClient ):

    def __init__( self, qleverfile, qleverdir, echo = True ):

        # Check that the qlever CLI tool is installed and on PATH
        if shutil.which( "qlever" ) is None:
            stop_error( "qlever CLI not found. Please install it with: uv tool install qlever" )

        # Check that riot (Apache Jena) is installed and on PATH
        if shutil.which( "riot" ) is None:
            stop_error( "riot not found. Please install Apache Jena and make sure riot is on PATH." )

        # Derive location, repository, container system and access_token from Qleverfile
        location, repository, system, access_token = parse_qleverfile( qleverfile )

        # Check the container runtime required by the Qleverfile
        if system in ( "docker", "podman" ):
            if run_system_cmd( [system, "info"], echo = echo, capture_output=True ).returncode != 0:
                stop_error( f"{system} daemon is not running. Please start it before using qlever." )
        elif system != "native":
            stop_error( f"Unknown [runtime] SYSTEM in Qleverfile: '{system}'. Expected docker, podman or native." )

        super().__init__( location, None, None )
        self.repository   = repository    # qlever has no repository concept; used as a label
        self.qleverfile   = qleverfile
        self.qleverdir    = qleverdir
        self.system       = system        # docker | podman | native
        self.access_token = access_token
        self.qlever_cmd   = ["qlever"]    # prefix for all qlever CLI calls
        self.pending_files   = []         # staged (relative) paths not yet indexed
        self.pending_updates = []         # SPARQL update strings queued before first index

        # Probe the server: it may legitimately be stopped (e.g. before qlever index).
        # Record the state; do NOT treat a stopped server as a fatal error here.
        try:
            http_call( { 'method': 'GET', 'url': location }, [ 200, 404 ], echo = echo )
            self.is_running = True
        except:
            self.is_running = False
        report( "qlever server", "running" if self.is_running else "stopped" )

    # ------------------------------------------------------------------ #
    # Server lifecycle
    # ------------------------------------------------------------------ #

    def server_start( self, echo = True ):
        """Start the qlever server.

        If there are staged (pending) files they have not been indexed yet —
        delegate to _finalize_index() which indexes and then starts the server.
        Otherwise run 'qlever start' directly.
        """
        if self.pending_files:
            self._finalize_index( echo = echo )
        else:
            r = run_system_cmd( self.qlever_cmd + ["start"], echo = echo, cwd = self.qleverdir )
            if r.returncode != 0:
                stop_error( "qlever start failed" )
            self.is_running = True

    def server_stop( self, echo = True ):
        """Stop the qlever server (runs 'qlever stop' in qleverdir)."""
        r = run_system_cmd( self.qlever_cmd + ["stop"], echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( "qlever stop failed" )
        self.is_running = False

    def server_rebuild_index( self, echo = True ):
        """Persist in-memory SPARQL updates by rebuilding the qlever index.

        Runs 'qlever rebuild-index --restart-when-finished' in qleverdir.
        This is the only way to make SPARQL UPDATE statements durable across
        server restarts in qlever.
        """
        print_task( "Rebuild qlever index to persist SPARQL updates" )
        r = run_system_cmd(
            self.qlever_cmd + ["rebuild-index", "--restart-when-finished"],
            echo = echo,
            cwd  = self.qleverdir
        )
        if r.returncode != 0:
            stop_error( "qlever rebuild-index failed" )
        # server is restarted by --restart-when-finished
        self.is_running = True

    # ------------------------------------------------------------------ #
    # Indexing pipeline
    # ------------------------------------------------------------------ #

    # Pre-compiled pattern matching a non-comment N-Triples data line (ends with " .")
    _NT_LINE_RE = re.compile( rb"^(.+)\s+\.\s*$" )

    def _nt_to_nq( self, nt_stream, gz_out, graph_iri_bytes ):
        """Read N-Triples lines from *nt_stream* and write N-Quads to *gz_out*.

        riot does not support a --graph flag, so we pipe its N-Triples output
        through this filter: each data line  «s p o .»  becomes  «s p o <g> .».
        Comment lines and blank lines are silently skipped.
        """
        for raw in nt_stream:
            stripped = raw.strip()
            if not stripped or stripped.startswith( b"#" ):
                continue
            m = self._NT_LINE_RE.match( stripped )
            if m:
                gz_out.write( m.group(1) + b" <" + graph_iri_bytes + b"> .\n" )

    def _stage_file( self, filename, context_iri, echo = True ):
        """Convert *filename* to N-Quads with *context_iri* as the graph IRI,
        compress with gzip, and write to <qleverdir>/input/<stem>_<hash8>.nq.gz.

        Returns the path **relative to qleverdir** (e.g. "input/foaf_abc12345.nq.gz").
        Using N-Quads ensures every triple is placed in the named graph at index time.

        riot is used to parse any RDF format to N-Triples; a lightweight in-process
        filter then appends the graph IRI to produce N-Quads (riot has no --graph flag).
        """
        input_dir = os.path.join( self.qleverdir, "input" )
        os.makedirs( input_dir, exist_ok = True )

        src = os.path.abspath( filename )

        # Build a short, deterministic suffix from the full source path
        h8 = hashlib.sha1( src.encode() ).hexdigest()[:8]

        # Strip any compression extension first, then the RDF extension
        stem = os.path.basename( src )
        stem = re.sub( r"\.(gz|bz2|xz)$", "", stem, flags = re.IGNORECASE )
        stem = os.path.splitext( stem )[0]

        out_name = f"{stem}_{h8}.nq.gz"
        out_path = os.path.join( input_dir, out_name )

        if echo:
            print( colored(
                f"riot --output=ntriples {src}  # → nquads with graph <{context_iri}> → {out_path}",
                "cyan"
            ), flush = True )

        riot = subprocess.Popen(
            ["riot", "--output=ntriples", src],
            stdout = subprocess.PIPE,
            stderr = None        # let riot warnings reach the terminal
        )
        with gzip.open( out_path, "wb" ) as gz_out:
            self._nt_to_nq( riot.stdout, gz_out, context_iri.encode() )
        riot.wait()
        if riot.returncode != 0:
            stop_error( f"riot conversion failed for: {src}" )

        rel_path = os.path.join( "input", out_name )
        report( "staged", rel_path )
        return rel_path

    def _patch_qleverfile( self, staged_files ):
        """Overwrite INPUT_FILES and CAT_INPUT_FILES in the [index] section
        of the Qleverfile.

        All staged files are .nq.gz, so CAT_INPUT_FILES is always
        'zcat ${INPUT_FILES}'.

        configparser lowercases keys by default; we use RawConfigParser with
        optionxform = str to preserve the uppercase keys that qlever expects.
        """
        real_path = os.path.realpath( self.qleverfile )
        parser = configparser.RawConfigParser()
        parser.optionxform = str          # preserve key case
        parser.read( real_path )
        if "index" not in parser:
            parser["index"] = {}
        parser["index"]["INPUT_FILES"]     = " ".join( staged_files )
        parser["index"]["CAT_INPUT_FILES"] = "zcat ${INPUT_FILES}"
        # qlever derives the index format from [data] FORMAT (default: ttl).
        # All staged files are N-Quads, so we must set it to "nq".
        if "data" not in parser:
            parser["data"] = {}
        parser["data"]["FORMAT"] = "nq"
        with open( real_path, "w" ) as f:
            parser.write( f )
        report( "INPUT_FILES",     " ".join( staged_files ) )
        report( "CAT_INPUT_FILES", "zcat ${INPUT_FILES}" )
        report( "[data] FORMAT",   "nq" )

    def _finalize_index( self, echo = True ):
        """Index all pending staged files and start the server.

        Steps:
          1. Patch [index] INPUT_FILES in the Qleverfile
          2. Stop the server if it is currently running
          3. Run 'qlever index'
          4. Start the server  ('qlever start')
          5. Remove the entire input/ directory (files are now in the index)
          6. Clear self.pending_files
          7. If self.pending_updates is non-empty, apply each SPARQL update
             and then call server_rebuild_index() to persist them
          8. Clear self.pending_updates
        """
        if not self.pending_files:
            print_warn( "_finalize_index called with no pending files — nothing to do." )
            return

        # 1. Patch Qleverfile
        print_task( "Patch Qleverfile INPUT_FILES" )
        self._patch_qleverfile( self.pending_files )

        # 2. Stop server if needed
        if self.is_running:
            print_task( "Stop qlever server before indexing" )
            self.server_stop( echo = echo )

        # 3. Index
        print_task( "Run qlever index" )
        r = run_system_cmd( self.qlever_cmd + ["index"], echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( "qlever index failed" )

        # 4. Start server
        print_task( "Start qlever server" )
        r = run_system_cmd( self.qlever_cmd + ["start"], echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( "qlever start failed" )
        self.is_running = True

        # 5. Remove the input directory (index has absorbed all staged files)
        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "cleanup", input_dir )

        # 6. Clear pending files
        self.pending_files = []

        # 7. Apply queued SPARQL updates (if any)
        if self.pending_updates:
            print_task( f"Apply {len(self.pending_updates)} queued SPARQL update(s)" )
            for sparql in self.pending_updates:
                self._do_sparql_update( sparql, echo = echo )
            # 8. Persist via rebuild-index
            self.server_rebuild_index( echo = echo )

        # 8. Clear pending updates
        self.pending_updates = []

    # ------------------------------------------------------------------ #
    # Public data-loading API
    # ------------------------------------------------------------------ #

    def rewrite_repository( self, _config_file = None, echo = True ):
        """Reset the qlever working directory for a fresh index.

        - Wipes the input/ staging area (if it exists)
        - Creates a symlink <qleverdir>/Qleverfile → self.qleverfile
          so 'qlever index / start / stop' can be run from qleverdir
          without specifying --qleverfile on every call
        - Resets the pending queues
        """
        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "wiped", input_dir )

        # Ensure qleverdir/Qleverfile points to the canonical Qleverfile
        link_path   = os.path.join( self.qleverdir, "Qleverfile" )
        target_real = os.path.realpath( self.qleverfile )
        link_real   = os.path.realpath( link_path ) if os.path.lexists( link_path ) else None
        if link_real != target_real:
            if os.path.lexists( link_path ):
                os.remove( link_path )
            os.symlink( target_real, link_path )
            report( "symlink", f"{link_path} → {target_real}" )

        self.pending_files   = []
        self.pending_updates = []

    def load_from_file( self, filename, context, headers = {}, echo = True ):
        """Stage *filename* for indexing into graph *context*.

        Converts the file to N-Quads (with the graph IRI embedded) via riot,
        compresses to .nq.gz, and records the relative path in self.pending_files.
        The actual 'qlever index' call is deferred until server_start() is invoked.
        """
        rel = self._stage_file( filename, context, echo = echo )
        self.pending_files.append( rel )

    # ------------------------------------------------------------------ #
    # SPARQL
    # ------------------------------------------------------------------ #

    def get_endpoint_update( self ):
        return ""

    def list_repository( self ):
        return [ self.repository ]

    def sparql_query( self, sparql, status_code_ok = [ 200, 400, 500 ], echo = True, timeout = None ):
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = {
            'Accept'       : 'application/json',
            'Content-Type' : 'application/x-www-form-urlencoded'
        }
        params = { 'query': sparql }
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_query,
                'headers' : headers,
                'data'    : params,
            },
            status_code_ok,
            echo
        )
        # qlever may return 500 for execution errors
        if r.status_code in [ 400, 500 ] and r.text:
            print_warn( r.text )
            return None
        if r.status_code != 200:
            dump( r )
            stop_error( "Unknown error" )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        """Execute a SPARQL update statement.

        Behaviour depends on the current server state:
          - Server running:  execute immediately via HTTP POST with ACCESS_TOKEN.
          - Server stopped but files are pending (pre-index phase):
            queue the statement in self.pending_updates so _finalize_index
            can apply it once the server is up.
          - Server stopped and no pending files (unexpected):
            raise an error.
        """
        if not self.is_running:
            if self.pending_files:
                # Deferred mode: server not yet started; queue for later
                report( "queued update", sparql[:60].replace( "\n", " " ) + "…" )
                self.pending_updates.append( sparql )
                return
            else:
                stop_error( "qlever server is not running and there are no pending files to index." )
        self._do_sparql_update( sparql, status_code_ok = status_code_ok, echo = echo )

    def _do_sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        """POST a SPARQL update to the qlever server with ACCESS_TOKEN."""
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = {
            'Content-Type' : 'application/x-www-form-urlencoded'
        }
        params = {
            'update'       : sparql,
            'access-token' : self.access_token,
        }
        r = http_call(
            {
                'method'  : 'POST',
                'url'     : self.endpoint_query,
                'headers' : headers,
                'data'    : params,
            },
            status_code_ok,
            echo
        )
        if r.status_code != 200 and r.text:
            print_warn( r.text )
        return r

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        contexts = set()
        for rec in r.json()["results"]["bindings"]:
            if "g" in rec:
                contexts.add( rec["g"]["value"] )
        return contexts

    def drop_context( self, context, echo = True ):
        """No-op for qlever: named graphs are fixed at index time.

        In the deferred-indexing model kgsteward calls drop_context before
        loading a dataset so that stale data is removed.  For qlever this is
        handled implicitly: rewrite_repository() wipes the staging area and
        _finalize_index() builds a fresh index from scratch, so there is
        nothing to drop at runtime.
        """
        pass
