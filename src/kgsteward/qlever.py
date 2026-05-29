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
import time

from dumper import dump
from .common import *
from .generic import GenericClient

# Natively supported qlever formats (without riot conversion), ± .gz
_QLEVER_NATIVE = { ".ttl": "ttl", ".nt": "nt" }


def _first_meaningful_sparql_line( sparql ):
    """Return the first non-empty, non-comment, non-PREFIX/BASE line — for human ID."""
    for line in sparql.splitlines():
        s = line.strip()
        if not s:                          continue
        if s.startswith( "#" ):            continue
        if s.upper().startswith( "PREFIX " ): continue
        if s.upper().startswith( "BASE " ):   continue
        return s[:120]
    return ""

def _qlever_fmt( filename ):
    """Return qlever format token ("ttl"/"nt") or None if riot is needed."""
    name = filename.lower()
    if name.endswith( ".gz" ): name = name[ :-3 ]
    return _QLEVER_NATIVE.get( os.path.splitext( name )[1] )


def parse_qleverfile( qleverfile ):
    """Read a Qleverfile and return (location, repository, system, access_token, text_index)."""
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
    text_index   = parser.get( "index",   "TEXT_INDEX",   fallback = "none" )
    return f"http://{host}:{port}", repository, system, access_token, text_index


class QleverClient( GenericClient ):

    def __init__( self, qleverfile, qleverdir, access_token = None, echo = True ):
        for tool in ("qlever", "riot"):
            if shutil.which( tool ) is None:
                stop_error( f"{tool} not found on PATH" )

        location, repository, system, access_token_from_file, text_index = parse_qleverfile( qleverfile )

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
        # Per-call timing for sparql_update — appended in _do_sparql_update and
        # written to a TSV at session end via dump_sparql_update_stats().
        # Useful both for diagnosing slow updates in a single backend and for
        # GraphDB-vs-qlever benchmark comparison (same dataset YAML, same .rq
        # files, run against both backends → diff the TSVs).
        self.sparql_update_stats = []
        self._sparql_update_counter = 0
        self.user_text_index = text_index   # original TEXT_INDEX from user's Qleverfile
        # qlever's text index is *always* skipped during per-dataset rebuilds
        # (rebuilding it once per dataset is grossly wasteful).  It is built only
        # when the user explicitly invokes --qlever_build_text_indexes, which
        # calls build_text_index() once at the end of the session.  This flag
        # tracks whether such a fresh text index is now on disk and the server
        # should load it; any subsequent _finalize_index invalidates it.
        self._has_current_text_index = False

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

    def _start_args( self ):
        """Return argv for ``qlever start`` honouring text-index state.

        qlever auto-derives USE_TEXT_INDEX = yes when TEXT_INDEX != none in the
        Qleverfile.  Per-dataset rebuilds never produce text-index files (we
        always pass ``--text-index none`` to ``qlever index`` and wipe any
        stale ``<NAME>.text.*`` from prior runs), so the auto-derived ``-t``
        flag would make qlever-server crash with ``ERROR opening file
        "<NAME>.text.vocabulary"`` and then Docker (--restart=unless-stopped)
        spins it into an endless restart loop.  Force ``--use-text-index no``
        unless build_text_index() has just produced a fresh text index.
        """
        if self._has_current_text_index:
            return ( "start", )
        return ( "start", "--use-text-index", "no" )

    def _stage_file( self, filename, context_iri, void_iri = None, echo = True ):
        """Copy/convert *filename* into qleverdir/input/ and return multi_input_json entries.

        *void_iri* overrides the IRI recorded in the void:dataDump triple (defaults to file://<src>).
        Pass the original URL when staging a downloaded file so provenance points to the source.

        When riot is invoked (for RDF/XML, OWL, etc. that qlever can't parse natively),
        the subprocess gets ``JAVA_TOOL_OPTIONS=-Djdk.xml.maxGeneralEntitySizeLimit=0``
        in its environment so that the JDK XML parser doesn't reject long literals /
        long entity contents.  The default JDK cap (100 000 chars) is hit by e.g.
        the RHEA ontology's RDF/XML descriptions.  We previously used ``riot --set
        jdk.xml.maxGeneralEntitySizeLimit=0`` which is wrong — ``--set`` sets ARQ
        context, not a JVM system property — so the cap was silently still in effect.
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
            riot_cmd  = [ "riot", "--output=ntriples", src ]
            # JVM system property must be set via env (-D), NOT via riot's
            # --set (which only sets ARQ context).  Lifts the 100 000-char
            # default cap on XML general entity sizes that otherwise rejects
            # long literals in RDF/XML ontologies such as RHEA / ChEBI / GO.
            riot_env = os.environ.copy()
            extra    = "-Djdk.xml.maxGeneralEntitySizeLimit=0"
            riot_env["JAVA_TOOL_OPTIONS"] = (
                ( riot_env.get( "JAVA_TOOL_OPTIONS", "" ) + " " + extra ).strip()
            )
            if echo:
                print( colored(
                    f"JAVA_TOOL_OPTIONS=\"{riot_env['JAVA_TOOL_OPTIONS']}\" "
                    + " ".join( riot_cmd ) + f" > {dest_path}",
                    "cyan",
                ), flush = True )
            with open( dest_path, "wb" ) as nt_out:
                riot = subprocess.run( riot_cmd, stdout = nt_out, env = riot_env )
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

        # ``"parallel": true`` is set per-input on every entry — with
        # MULTI_INPUT_JSON, the top-level PARALLEL_PARSING in the Qleverfile
        # does NOT propagate, parallelism is decided per stream.  qlever's
        # docs: "recommended for large files, but requires that all prefix
        # declarations are at the beginning of the file", which is the case
        # for every input format kgsteward produces (.nt, .nt.gz, .ttl from
        # riot, void.nt) and for the .nt.gz checkpoints.
        report( "staged", f"input/{dest_name}  (+ void triple)" )
        return [
            { "cmd": cmd,                       "format": fmt,  "graph": context_iri, "parallel": True },
            { "cmd": f"cat input/{void_name}",  "format": "nt", "graph": context_iri, "parallel": True },
        ]

    def _ensure_host_name_localhost( self ):
        """Make sure [server] HOST_NAME = localhost is set in qleverdir/Qleverfile.

        Without this, the qlever CLI falls back to ``socket.gethostname()`` for
        its alive-check (``/ping``), which doesn't route to the Docker-mapped
        port on 127.0.0.1, and ``qlever start`` then spins forever.
        """
        dest = os.path.join( self.qleverdir, "Qleverfile" )
        if not os.path.lexists( dest ):
            return
        parser = configparser.RawConfigParser()
        parser.optionxform = str
        parser.read( dest )
        if "server" not in parser:
            parser["server"] = {}
        if parser["server"].get( "HOST_NAME" ) != "localhost":
            parser["server"]["HOST_NAME"] = "localhost"
            with open( dest, "w" ) as f:
                parser.write( f )
            report( "forced", "[server] HOST_NAME = localhost" )

    def _patch_qleverfile( self, entries ):
        """Refresh qleverdir/Qleverfile from the user's source, then patch it.

        Always re-copy the user's Qleverfile each time so any tuning changes
        (SETTINGS_JSON, STXXL_MEMORY, PARALLEL_PARSING, TEXT_INDEX, …) take
        effect on the next per-dataset rebuild — previously we only copied
        when qleverdir/Qleverfile was *missing*, which meant edits to the
        source after the first run were silently ignored.  The patch below
        then overrides only the keys we own (MULTI_INPUT_JSON, INPUT_FILES,
        HOST_NAME), leaving everything else from the user's source intact.
        """
        dest = os.path.join( self.qleverdir, "Qleverfile" )
        shutil.copy2( os.path.realpath( self.qleverfile ), dest )
        report( "synced Qleverfile from user source", dest )
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

    def _collect_checkpoint_entries( self, exclude_iris = None ):
        """Return MULTI_INPUT_JSON entries for all completed checkpoints.

        Reads ``*.nt.gz.json`` sidecar files in qleverdir.  Each sidecar records the
        named-graph IRI so its checkpoint can be fed directly into ``qlever index`` via
        MULTI_INPUT_JSON — no re-downloading or re-converting of source files required.
        The sidecar's presence is an atomic completeness marker: ``dump_checkpoint``
        writes the ``.nt.gz`` data file first (via a temporary file + ``os.replace``),
        then the sidecar; a crash between the two writes leaves an orphaned ``.nt.gz``
        that is simply ignored here.

        *exclude_iris* is an optional iterable of context IRIs to skip.  ``_finalize_index``
        passes the set of IRIs present in ``pending_files`` so that a dataset being
        re-processed is not loaded from its stale checkpoint at the same time its fresh
        files are being indexed — which would either duplicate the graph or mix old and
        new triples.  The stale checkpoint stays on disk and is overwritten atomically by
        the subsequent ``dump_checkpoint``.
        """
        exclude = set( exclude_iris ) if exclude_iris else set()
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
            if context_iri in exclude:
                report( "checkpoint superseded by pending data", fname )
                continue
            entries.append( { "cmd": f"zcat {fname}", "format": "nt", "graph": context_iri, "parallel": True } )
            report( "checkpoint → index", fname )
        return entries

    def _apply_pending_updates( self, echo = True ):
        """Execute all queued SPARQL updates; dump a checkpoint at each sentinel.

        ``pending_updates`` is a list of strings (SPARQL updates) interleaved with
        ``(context_iri,)`` tuples inserted by ``mark_rebuild()``.  Each tuple triggers
        ``dump_checkpoint(context_iri)``, which issues a CONSTRUCT against the running
        server — the server transparently merges the on-disk index with the in-memory
        delta produced by the preceding updates, so the dumped ``.nt.gz`` captures the
        complete post-update state of the graph.

        No explicit ``qlever rebuild-index`` is needed: the next dataset's
        ``_finalize_index`` rebuilds the on-disk index *from scratch* using every
        checkpoint + the new staged files, so the delta lives only as long as the
        current dataset's checkpoint dump.
        """
        if not self.pending_updates:
            return
        n_updates = sum( 1 for u in self.pending_updates if not isinstance( u, tuple ) )
        print_task( f"Apply {n_updates} queued SPARQL update(s) with per-dataset checkpoint" )
        for item in self.pending_updates:
            if isinstance( item, tuple ):
                context_iri = item[0]
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
        # Datasets being re-processed have their fresh files in pending_files; their
        # stale checkpoints must be excluded so we don't load old + new for the same graph.
        pending_iris = { e["graph"] for e in self.pending_files }
        checkpoint_entries = self._collect_checkpoint_entries( exclude_iris = pending_iris )
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
        # The text index is *always* skipped during per-dataset rebuilds —
        # rebuilding it once per dataset is grossly wasteful and qlever-index
        # rebuilds it from scratch anyway.  Users who want a text index opt in
        # with --qlever_build_text_indexes, which calls build_text_index()
        # once at the end of the session.  Any stale <NAME>.text.* files left
        # over from a previous build_text_index are wiped here so the next
        # server restart can't try to load text that doesn't match the new
        # main index.
        stale_text_files = glob.glob( os.path.join( self.qleverdir, f"{self.repository}.text.*" ) )
        for f in stale_text_files:
            os.remove( f )
            report( "wiped stale text index", os.path.basename( f ) )
        if self.user_text_index and self.user_text_index.lower() != "none":
            extra = " ; wiped " + str( len( stale_text_files ) ) + " stale text-index file(s)" if stale_text_files else ""
            print_warn(
                "Qleverfile has TEXT_INDEX = " + self.user_text_index
                + " but per-dataset rebuild will skip it (`qlever index --text-index none`)"
                + extra
                + ". Pass --qlever_build_text_indexes to (re)build it once at the session end."
            )
        self._has_current_text_index = False
        self._qlever( "index", "--text-index", "none", "--overwrite-existing", echo = echo )
        # Defensive: qlever-index runs as `qlever-index ... | tee <log>` inside
        # the container, and the pipe masks qlever-index's non-zero exit on
        # parse errors / runtime exceptions.  Bash's pipefail isn't set, so
        # the wrapper sees exit 0 even when the index build aborted halfway
        # through.  Inspect the log file directly and fail loudly if any
        # ERROR line is present — otherwise the next dump_checkpoint will
        # silently produce an empty .nt.gz for the dataset (since the new
        # data was never loaded into the index).
        self._abort_if_index_log_has_error()
        self._qlever( *self._start_args(), echo = echo )
        self.is_running = True

        input_dir = os.path.join( self.qleverdir, "input" )
        if os.path.isdir( input_dir ):
            shutil.rmtree( input_dir )
            report( "cleanup", input_dir )

        self.pending_files = []

        self._apply_pending_updates( echo = echo )

    def _abort_if_index_log_has_error( self ):
        """Scan ``<repository>.index-log.txt`` for ERROR lines and stop_error if any.

        qlever-index runs as `qlever-index ... | tee <log>` inside the
        container, and the pipe masks qlever-index's non-zero exit on parse
        errors / runtime exceptions (bash's pipefail isn't set), so the
        wrapper sees exit 0 even when the build aborted halfway through.
        Inspect the log file directly and fail loudly — otherwise the next
        dump_checkpoint silently produces an empty .nt.gz for the dataset.
        """
        log_path = os.path.join( self.qleverdir, f"{self.repository}.index-log.txt" )
        if not os.path.isfile( log_path ):
            return
        with open( log_path, errors = "replace" ) as f:
            log_text = f.read()
        bad = [ line for line in log_text.splitlines() if " - ERROR:" in line ]
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
                self._qlever( *self._start_args(), echo = echo )
                self.is_running = True
            self._apply_pending_updates( echo = echo )
        else:
            self._qlever( *self._start_args(), echo = echo )
            self.is_running = True

    def server_stop( self, echo = True ):
        self._qlever( "stop", echo = echo )
        self.is_running = False

    def server_rebuild_index( self, echo = True ):
        """Persist in-memory SPARQL updates by rebuilding the qlever index."""
        self._qlever( "rebuild-index", "--restart-when-finished", echo = echo )
        self.is_running = True

    def build_text_index( self, echo = True ):
        """Build the text index once over the existing on-disk index.

        The text index is *opt-in*: per-dataset rebuilds never produce it
        (rebuilding once per dataset is wasteful), so calling this method is
        the only way to get a text index from kgsteward.  Reads the original
        ``TEXT_INDEX`` value from the user's Qleverfile (captured at
        ``__init__`` time as ``self.user_text_index``).  If that value is
        ``none``, this is a no-op — there is nothing to build.

        Otherwise the server is stopped (so qlever-index can write the text
        files without contention), ``qlever add-text-index --text-index
        <user> --overwrite-existing`` runs, ``_has_current_text_index`` is
        flipped to True (so the subsequent server start does load the text
        index), and the server is restarted.
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
        # Text index now on disk — let the restart load it.
        self._has_current_text_index = True
        self._qlever( *self._start_args(), echo = echo )
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

        Not called by the normal kgsteward processing loop (which keeps the old
        checkpoint as a transactional fallback) — retained as a public API for
        explicit administrative use, e.g. forcibly dropping a dataset from the
        managed set without going through the full update path.
        """
        path    = self.checkpoint_path( context_iri )
        sidecar = path + ".json"
        for fn in ( path, sidecar ):
            if os.path.isfile( fn ):
                os.remove( fn )
                report( "invalidated checkpoint", os.path.basename( fn ) )

    def upload_quad_and_dump_checkpoints( self, name2context, echo = True ):
        """Bootstrap a qlever index from a quad dump, verify it, and dump checkpoints.

        Single end-to-end "adoption" operation.  Use case: the user has a big
        ``.nq.gz`` (or any qlever-loadable) dump produced outside kgsteward and
        wants to bring its content under kgsteward management.  Doing the bulk
        load with ``qlever index`` is *much* faster than ingesting dataset-by-
        dataset through kgsteward, so we let qlever do it natively and then
        capture the result as per-graph checkpoints.

        Steps:

          1. Stop the server if running.
          2. ``rewrite_repository`` — wipes ``input/``, all ``.nt.gz`` checkpoints
             and ``.nt.gz.json`` sidecars, and restores the user's original
             Qleverfile (overwriting any MULTI_INPUT_JSON-patched version).
          3. Force ``HOST_NAME = localhost`` so the CLI alive-check works.
          4. ``qlever index --overwrite-existing`` — builds from the user's
             configured ``INPUT_FILES`` / ``CAT_INPUT_FILES``.
          5. ``qlever start``.
          6. Verify: compare the named graphs found in the running server
             against the YAML dataset contexts.  Report mismatches both ways
             (graph in dump but not in YAML; dataset in YAML but no data in
             dump).
          7. Dump every named graph as an ``.nt.gz`` + sidecar checkpoint.

        After step 7, kgsteward's per-dataset architecture is fully bootstrapped:
        all subsequent ``_finalize_index`` rebuilds will include this data, and
        ``-C`` / ``-d`` work as usual.

        Returns the sorted list of dumped graph IRIs.
        """
        # 1. Stop server
        if self.is_running:
            self.server_stop( echo = echo )

        # 2. Reset to the user's Qleverfile (also wipes old checkpoints + input/)
        print_task( "Reset qleverdir to user's Qleverfile (wipe checkpoints, input/)" )
        self.rewrite_repository( echo = echo )

        # 3. HOST_NAME=localhost — needed for the CLI alive-check loop
        self._ensure_host_name_localhost()

        # 4. Build the qlever index from the quad dump
        print_task( "Build qlever index from the configured INPUT_FILES (bulk load)" )
        self._qlever( "index", "--overwrite-existing", echo = echo )

        # 5. Start the server
        print_task( "Start qlever server from the freshly-built index" )
        self._qlever( *self._start_args(), echo = echo )
        self.is_running = True

        # 6. Verify named graphs against YAML
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

        for g in matched:
            name = next( n for n, c in name2context.items() if c == g )
            report( "matched", f"{name} ← {g}" )
        for g in orphan:
            print_warn( f"Graph in dump but no matching dataset in YAML: {g}  (kept as orphan-but-preserved checkpoint)" )
        for c in missing:
            name = next( n for n, x in name2context.items() if x == c )
            print_warn( f"Dataset '{name}' in YAML but no data found in the loaded index ({c})" )

        # 7. Dump checkpoints for all named graphs
        print_task( f"Dump {len( graphs_in_server )} named graph(s) as checkpoints" )
        for g in sorted( graphs_in_server ):
            self.dump_checkpoint( g, echo = echo )

        return sorted( graphs_in_server )

    def dump_checkpoint( self, context_iri, echo = True ):
        """Query the running server and save the named graph as a compressed N-Triples checkpoint.

        Writes ``<safe>_<h8>.nt.gz`` (the data) and ``<safe>_<h8>.nt.gz.json`` (sidecar
        recording the graph IRI).  Two-step atomic write:

          1. Dump to ``<path>.tmp``, then ``os.replace(tmp, path)`` — guarantees the
             ``.nt.gz`` is either the OLD content or the NEW content, never partial.
          2. Write the sidecar last; its presence is the completeness marker.

        This makes checkpointing transactional: until the new dump completes, the OLD
        checkpoint remains on disk as a fallback.  A crash mid-processing therefore
        cannot leave a previously-checkpointed dataset un-checkpointed.
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
            [ 200 ], echo = False
        )
        with gzip.open( tmp_path, "wb" ) as f:
            f.write( r.content )
        os.replace( tmp_path, path )    # atomic on POSIX
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
            # --connect-timeout 30 : give up if no TCP handshake in 30s.
            # --speed-time 60 --speed-limit 1024 : abort if the transfer
            #     stays under 1 KB/s for 60 consecutive seconds.  This catches
            #     the "upstream throttled us to a trickle" failure mode
            #     (otherwise curl hangs forever on a half-dead connection).
            # --retry 3 --retry-delay 5 : transient blip → quick retry.
            curl_cmd = [
                "curl", "-L",
                "--connect-timeout", "30",
                "--speed-time", "60", "--speed-limit", "1024",
                "--retry", "3", "--retry-delay", "5",
                "-o", tmp_path, url,
            ]
            if echo:
                print( colored( " ".join( curl_cmd ), "cyan" ), flush = True )
            r = subprocess.run( curl_cmd )
            if r.returncode != 0:
                stop_error( f"curl download failed for: {url}  (exit {r.returncode})" )
            self.pending_files.extend( self._stage_file( tmp_path, context, void_iri = url, echo = echo ) )
        finally:
            if os.path.exists( tmp_path ):
                os.unlink( tmp_path )

    def mark_rebuild( self, context_iri = None ):
        """Insert a checkpoint sentinel into the pending_updates queue.

        *context_iri* is the named graph to dump as a ``.nt.gz`` checkpoint after all
        preceding SPARQL updates for this dataset have been applied.  When
        ``_apply_pending_updates`` hits the ``(context_iri,)`` tuple it calls
        ``dump_checkpoint`` — the CONSTRUCT query against the running server returns
        the on-disk index merged with the in-memory delta, so the checkpoint captures
        the complete post-update state.  No ``qlever rebuild-index`` is needed because
        the next ``_finalize_index`` rebuilds the on-disk index from scratch using
        every checkpoint + the new dataset's staged files.
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
        self._sparql_update_counter += 1
        t_start = time.time()
        # Updates from kgsteward (large INSERT/DELETE WHERE, multi-step graph
        # computations, etc.) routinely exceed the per-query timeout set by
        # TIMEOUT in the Qleverfile — and that timeout is sensible for
        # interactive queries, not bulk ingestion.  Per-request override
        # ``timeout=`` is honoured by qlever above the server default ONLY when
        # an access token is supplied (and ours always is).  qlever has no
        # "unlimited" value; 999999s (~11.6 days) is effectively never going
        # to be reached in a session and is well above any plausible single
        # update's runtime.
        r = http_call(
            { 'method': 'POST', 'url': self.endpoint_query,
              'headers': { 'Content-Type': 'application/x-www-form-urlencoded' },
              'data': {
                  'update':       sparql,
                  'access-token': self.access_token,
                  'timeout':      '999999s',
              } },
            status_code_ok, echo
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
                    op0 = body["operations"][0]
                    op_t = op0.get( "time" )
                    if isinstance( op_t, dict ) and qlever_total_ms is None:
                        qlever_total_ms = op_t.get( "total" )
        except Exception:
            pass

        self.sparql_update_stats.append({
            "n":               self._sparql_update_counter,
            "ts":              time.strftime( "%Y-%m-%dT%H:%M:%S" ),
            "elapsed_ms":      elapsed_ms,
            "qlever_total_ms": qlever_total_ms,
            "http_status":     r.status_code,
            "size_chars":      len( sparql ),
            "sha1_8":          hashlib.sha1( sparql.encode() ).hexdigest()[:8],
            "first_line":      _first_meaningful_sparql_line( sparql ),
            "error":           ( qlever_error[:200] if qlever_error else "" ),
        })

        if r.status_code != 200 and r.text:
            print_warn( r.text )
        return r

    def dump_sparql_update_stats( self, filepath ):
        """Write the per-call sparql_update stats to *filepath* as TSV.

        One row per SPARQL update issued via ``_do_sparql_update`` during this
        session, including:

          - ``n``               : sequence number within the session
          - ``ts``              : wall-clock timestamp the update started
          - ``elapsed_ms``      : full round-trip wall-clock (kgsteward side)
          - ``qlever_total_ms`` : qlever's server-side total time (if reported)
          - ``http_status``     : HTTP status code
          - ``size_chars``      : length of the SPARQL string (rough complexity)
          - ``sha1_8``          : 8-char hash, stable across runs / backends
          - ``first_line``      : first non-PREFIX/-comment line (human-readable)
          - ``error``           : truncated qlever exception, if any

        Cross-backend benchmark hint: run kgsteward against GraphDB and qlever
        with the same YAML config, dump each backend's stats, then join on
        ``sha1_8`` (or ``n`` if the execution order is deterministic) to compare
        per-update timings between engines.
        """
        if not self.sparql_update_stats:
            report( "sparql update stats", "(empty — nothing to dump)" )
            return
        cols = ["n", "ts", "elapsed_ms", "qlever_total_ms", "http_status",
                "size_chars", "sha1_8", "first_line", "error"]
        with open( filepath, "w" ) as f:
            f.write( "\t".join( cols ) + "\n" )
            for s in self.sparql_update_stats:
                f.write( "\t".join( str( s.get( c, "" ) if s.get( c ) is not None else "" ) for c in cols ) + "\n" )
        report( "dumped sparql update stats", f"{filepath}  ({len(self.sparql_update_stats)} entries)" )

    def list_context( self, echo = True ):
        r = self.sparql_query( "SELECT DISTINCT ?g WHERE{ GRAPH ?g {}}", echo = echo )
        if r is None:
            return set()
        return { rec["g"]["value"] for rec in r.json()["results"]["bindings"] if "g" in rec }

    def drop_context( self, context, echo = True ):
        """No-op for qlever — checkpoint invalidation + index rebuild handle removal.

        In the per-dataset architecture, ``kgsteward`` calls ``invalidate_checkpoint``
        immediately before ``drop_context`` for the dataset being reprocessed.  The next
        ``_finalize_index`` then rebuilds the on-disk index from scratch using every
        remaining checkpoint + the freshly-staged files — the old graph is simply not
        included.  No SPARQL DELETE is needed, and sending one is actively harmful: a
        ``DELETE WHERE { GRAPH <ctx> { ?s ?p ?o } }`` on a large graph (tens of millions
        of triples) can crash the qlever server with a ``RemoteDisconnected``.
        """
        report( "drop_context", f"no-op for qlever (will be excluded from next index rebuild): {context}" )
