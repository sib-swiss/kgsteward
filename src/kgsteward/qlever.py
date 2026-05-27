import configparser
import hashlib
import json
import os
import re
import shutil
import subprocess

from dumper import dump
from .common import *
from .generic import GenericClient

# qlever-index format tokens for natively supported RDF formats (± .gz)
# Any format not listed here goes through riot → N-Triples conversion.
_QLEVER_NATIVE = { ".ttl": "ttl", ".nt": "nt" }

def _qlever_fmt( filename ):
    """Return the qlever format token ("ttl" or "nt") for a filename,
    or None if the format is not natively supported and needs riot.
    .gz suffix is stripped before checking the extension.
    """
    name = filename.lower()
    if name.endswith( ".gz" ):
        name = name[ :-3 ]
    _, ext = os.path.splitext( name )
    return _QLEVER_NATIVE.get( ext )


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
    # interpolation=None avoids errors on values containing '%' characters
    parser = configparser.ConfigParser( interpolation = None )
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

        # pending_files: list of multi_input_json entry dicts, one per staged file.
        # Populated by load_from_file(); consumed by _finalize_index().
        self.pending_files = []
        # pending_updates: real SPARQL updates queued while server is not yet running.
        # Applied by _finalize_index() after qlever start.
        self.pending_updates = []

        # Probe the server: it may legitimately be stopped (e.g. before qlever index).
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

        If files are pending they have not been indexed yet — delegate to
        _finalize_index(), which indexes all staged files and then starts
        the server.  Otherwise call 'qlever start' directly (re-using an
        existing index from a previous run).
        """
        if self.pending_files:
            self._finalize_index( echo = echo )
        else:
            r = run_system_cmd( self.qlever_cmd + ["start"], echo = echo, cwd = self.qleverdir )
            if r.returncode != 0:
                stop_error( "qlever start failed" )
            self.is_running = True

    def server_stop( self, echo = True ):
        """Stop the qlever server ('qlever stop' in qleverdir)."""
        r = run_system_cmd( self.qlever_cmd + ["stop"], echo = echo, cwd = self.qleverdir )
        if r.returncode != 0:
            stop_error( "qlever stop failed" )
        self.is_running = False

    def server_rebuild_index( self, echo = True ):
        """Persist in-memory SPARQL updates by re-building the qlever index.

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
        self.is_running = True

    # ------------------------------------------------------------------ #
    # Staging pipeline
    # ------------------------------------------------------------------ #

    def _stage_file( self, filename, context_iri, echo = True ):
        """Stage *filename* for deferred indexing into graph *context_iri*.

        Returns a list of multi_input_json entry dicts (one for the RDF data,
        one for a tiny void:dataDump N-Triple) to be included in the qlever
        index command.

        Natively supported formats (.ttl, .nt, ± .gz) are hard-linked (or
        copied) into qleverdir/input/ as-is and indexed directly.
        All other formats are converted to N-Triples via riot on the host and
        written to qleverdir/input/<stem>_<hash8>.nt.

        Named-graph assignment is done through the 'graph' key in
        multi_input_json — no N-Quads conversion is required.
        """
        input_dir = os.path.join( self.qleverdir, "input" )
        os.makedirs( input_dir, exist_ok = True )

        src  = os.path.abspath( filename )
        h8   = hashlib.sha1( src.encode() ).hexdigest()[:8]
        stem = os.path.basename( src )
        stem = re.sub( r"\.(gz|bz2|xz)$", "", stem, flags = re.IGNORECASE )
        stem = os.path.splitext( stem )[0]

        fmt = _qlever_fmt( src )

        if fmt is not None:
            # Natively supported format: hard-link (same fs) or copy into input/
            is_gz    = src.lower().endswith( ".gz" )
            ext_full = ".ttl.gz" if (fmt == "ttl" and is_gz) else \
                       ".nt.gz"  if (fmt == "nt"  and is_gz) else \
                       f".{fmt}"
            dest_name = f"{stem}_{h8}{ext_full}"
            dest_path = os.path.join( input_dir, dest_name )
            if os.path.lexists( dest_path ):
                os.remove( dest_path )
            try:
                os.link( src, dest_path )
                report( "hard-link", dest_path )
            except OSError:
                shutil.copy2( src, dest_path )
                report( "copy", dest_path )
            cmd = f"zcat input/{dest_name}" if is_gz else f"cat input/{dest_name}"
        else:
            # Non-native format: convert to N-Triples via riot on the host
            dest_name = f"{stem}_{h8}.nt"
            dest_path = os.path.join( input_dir, dest_name )
            if echo:
                print( colored( f"riot --output=ntriples {src} > {dest_path}", "cyan" ), flush = True )
            with open( dest_path, "wb" ) as nt_out:
                riot = subprocess.run(
                    ["riot", "--output=ntriples", src],
                    stdout = nt_out,
                    stderr = None      # let riot warnings reach the terminal
                )
            if riot.returncode != 0:
                stop_error( f"riot conversion failed for: {src}" )
            fmt = "nt"
            cmd = f"cat input/{dest_name}"
            report( "staged (riot→nt)", dest_path )

        entries = [
            { "cmd": cmd, "format": fmt, "graph": context_iri }
        ]

        # Bake the void:dataDump triple into the index so that no separate
        # SPARQL INSERT + rebuild-index is needed later.
        void_name = f"{stem}_{h8}.void.nt"
        void_path = os.path.join( input_dir, void_name )
        void_iri  = "http://rdfs.org/ns/void#dataDump"
        with open( void_path, "w" ) as vf:
            vf.write( f"<{context_iri}> <{void_iri}> <file://{src}> .\n" )
        entries.append(
            { "cmd": f"cat input/{void_name}", "format": "nt", "graph": context_iri }
        )

        report( "staged", f"input/{dest_name}  (+ void triple)" )
        return entries

    def _patch_qleverfile( self, entries ):
        """Write MULTI_INPUT_JSON into qleverdir/Qleverfile.

        Also removes INPUT_FILES, CAT_INPUT_FILES and FORMAT if they exist,
        because qlever requires exactly one of CAT_INPUT_FILES or
        MULTI_INPUT_JSON in the [index] section.

        Always writes to qleverdir/Qleverfile (the working copy), never to
        the user's original Qleverfile.

        configparser lowercases keys by default; we use RawConfigParser with
        optionxform = str to preserve the uppercase keys that qlever expects.
        """
        dest = os.path.join( self.qleverdir, "Qleverfile" )
        parser = configparser.RawConfigParser()
        parser.optionxform = str          # preserve key case
        parser.read( dest )

        if "index" not in parser:
            parser["index"] = {}

        # INPUT_FILES is always required by qlever (used for file-size
        # estimation and existence check, even when MULTI_INPUT_JSON is set).
        # Extract the file paths from the cmd fields of each entry.
        file_paths = " ".join( e["cmd"].split()[-1] for e in entries )
        parser["index"]["INPUT_FILES"] = file_paths

        # CAT_INPUT_FILES is mutually exclusive with MULTI_INPUT_JSON
        if "CAT_INPUT_FILES" in parser["index"]:
            parser.remove_option( "index", "CAT_INPUT_FILES" )

        # Remove FORMAT from [data] if set by a previous kgsteward run
        if "data" in parser and "FORMAT" in parser["data"]:
            parser.remove_option( "data", "FORMAT" )

        parser["index"]["MULTI_INPUT_JSON"] = json.dumps( entries, separators = (",", ":") )

        with open( dest, "w" ) as f:
            parser.write( f )
        report( "INPUT_FILES",     file_paths )
        report( "MULTI_INPUT_JSON", f"{len(entries)} stream(s)" )

    def _finalize_index( self, echo = True ):
        """Build the qlever index from all pending staged files and start the server.

        Steps:
          1. Write MULTI_INPUT_JSON to qleverdir/Qleverfile
          2. Stop the server if currently running
          3. Run 'qlever index'
          4. Start the server ('qlever start')
          5. Remove qleverdir/input/ (the index has absorbed all staged files)
          6. Clear self.pending_files
          7. Apply any queued SPARQL updates (self.pending_updates)
          8. If updates were applied, call server_rebuild_index() to persist them
          9. Clear self.pending_updates

        void:dataDump triples are already baked into the staged files by
        _stage_file(), so they do not appear in pending_updates — step 7/8
        execute only for real update: section statements.
        """
        if not self.pending_files:
            print_warn( "_finalize_index called with no pending files — nothing to do." )
            return

        # 1. Patch qleverdir/Qleverfile
        print_task( "Write MULTI_INPUT_JSON to Qleverfile" )
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

        # 7–8. Apply and persist real SPARQL updates (if any)
        if self.pending_updates:
            print_task( f"Apply {len(self.pending_updates)} queued SPARQL update(s)" )
            for sparql in self.pending_updates:
                self._do_sparql_update( sparql, echo = echo )
            self.server_rebuild_index( echo = echo )

        # 9. Clear pending updates
        self.pending_updates = []

    # ------------------------------------------------------------------ #
    # Public data-loading API
    # ------------------------------------------------------------------ #

    def rewrite_repository( self, _config_file = None, echo = True ):
        """Reset the qlever working directory for a fresh index.

        - Wipes qleverdir/input/ (previous staged files)
        - Copies the user's Qleverfile to qleverdir/Qleverfile so that
          all subsequent patches stay inside qleverdir and the user's
          original file is never modified
        - Resets pending_files and pending_updates
        """
        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "wiped", input_dir )

        # Copy user's Qleverfile to qleverdir (only if they differ)
        user_real = os.path.realpath( self.qleverfile )
        dest      = os.path.join( self.qleverdir, "Qleverfile" )
        dest_real = os.path.realpath( dest ) if os.path.lexists( dest ) else None
        if user_real != dest_real:
            shutil.copy2( user_real, dest )
            report( "copied Qleverfile", dest )

        self.pending_files   = []
        self.pending_updates = []

    def load_from_file( self, filename, context, headers = {}, echo = True ):
        """Stage *filename* for deferred indexing into graph *context*.

        Files are converted (if necessary) and written to qleverdir/input/.
        A tiny void:dataDump triple is baked in alongside the data so that
        no separate SPARQL INSERT + rebuild-index is needed.

        The actual 'qlever index' is deferred until server_start() is called
        or until the first real SPARQL update arrives.
        """
        entries = self._stage_file( filename, context, echo = echo )
        self.pending_files.extend( entries )

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
        if r.status_code in [ 400, 500 ] and r.text:
            print_warn( r.text )
            return None
        if r.status_code != 200:
            dump( r )
            stop_error( "Unknown error" )
        return r

    def sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        """Execute a SPARQL update statement.

        void:dataDump INSERTs are silently skipped because those triples are
        already baked into the staged N-Quads files by _stage_file(), so no
        second indexing pass is needed to persist them.

        For all other updates the behaviour depends on the server state:
          • Server running:   execute immediately via HTTP POST.
          • Server stopped + pending files (pre-index phase):
            queue the statement; _finalize_index() will apply it after the
            server starts and then call server_rebuild_index() once to persist.
          • Server stopped + no pending files (re-use existing index):
            restart the server with 'qlever start', then execute.
        """
        # void:dataDump triples are baked into staged files — skip the INSERT
        if "void:dataDump" in sparql or "ns/void#dataDump" in sparql:
            return

        if not self.is_running:
            if self.pending_files:
                # Still in staging phase; queue for after _finalize_index
                report( "queued update", sparql[:60].replace( "\n", " " ) + "…" )
                self.pending_updates.append( sparql )
                return
            else:
                # Existing index available — just restart the server
                r = run_system_cmd( self.qlever_cmd + ["start"], echo = echo, cwd = self.qleverdir )
                if r.returncode != 0:
                    stop_error( "qlever start failed" )
                self.is_running = True

        self._do_sparql_update( sparql, status_code_ok = status_code_ok, echo = echo )

    def _do_sparql_update( self, sparql, status_code_ok = [ 200 ], echo = True ):
        """POST a SPARQL update to the running qlever server with ACCESS_TOKEN."""
        if echo:
            print_strip( sparql.replace( "\t", "    " ), color = "green" )
        headers = { 'Content-Type': 'application/x-www-form-urlencoded' }
        params  = {
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

        kgsteward calls drop_context before loading each dataset to remove stale
        data.  For qlever this is handled at a higher level: rewrite_repository()
        wipes the staging area and _finalize_index() builds a fresh index from
        scratch, so there is nothing to drop at runtime.
        """
        pass
