import os
import glob
import requests
import shutil
import time
import re
import dumper
import sys
import gzip
import bz2
import lzma

from termcolor import colored

RE_CATCH_ENV_VAR     = re.compile( r"\$\{([^\}]+)\}" )
RE_CATCH_BEGIN_SPACE = re.compile( r"^(\s*)" )
RE_CATCH_END_SPACE   = re.compile( r"(\s*)$" )
RE_CATCH_TAB         = re.compile( r"(\t)" )

def replace_env_var( txt ) :
    """ A helper sub with no magic """
    m = RE_CATCH_ENV_VAR.search( txt )
    if m:
        env_var = m.group( 1 )
        if env_var in os.environ:
            return replace_env_var( txt.replace( "${" + env_var + "}", os.getenv( env_var ))) # recursion
        else:
            stop_error(f"Environment variable not set: {env_var}")
    else:
        return txt

def update_path( path, default_dir, fatal = True  ):
    """Expand path environment variables"""
    dir, fn = os.path.split( os.path.normpath( replace_env_var( path ))) # handles ".." correctly
    if not dir.startswith( "/" ):
        dir = default_dir + "/" + dir
    filename = dir + "/" + fn
    if not os.path.isfile( filename ):
        stop_error( "File does not exists: " + filename )
    return filename

def expand_path( path, default_dir, fatal = True ):
    """Expand path on wildcard and environment variables"""
    dir, filename = os.path.split( os.path.normpath( replace_env_var( path ))) # handles ".." correctly
    res = []
    if not dir.startswith( "/" ):
        dir = default_dir + "/" + dir
    if "*" in dir or  "*" in filename:
        paths = glob.glob( dir + "/" + filename )
        if paths:
            for p in sorted( paths ):
                res.append( os.path.split( p ))
        else:
            if fatal:
                stop_error( "Not a single file found: " + dir + "/" + filename )
            else:
                print_warn( "Not a single file found: " + dir + "/" + filename )
    else:
        if os.path.isfile( dir + "/" + filename ):
            res.append([ dir, filename ])
        else:
            if fatal:
                stop_error( "File does not exists: " + dir + "/" + filename )
            else:
                print_warn( "File does not exists: " + dir + "/" + filename )
    return res

def http_call( request_args, status_code = [ 200 ], echo = True ):
    """A simple wrapper arround requests.request() which main purpose is to
    (1) validate status code
	(1) print elapsed time
    (2) print request parameters in case of an unexpected status code."""
    if echo :
        report( request_args['method'], request_args['url'] )
    start_time = time.time()
    r = requests.request( **request_args )
    end_time = time.time()
    if r.status_code not in status_code :
        # dumper.dump( request_args )
        print_warn( "Status code = " + str( r.status_code ))
        print_warn( r.text if not r.text is None else '' )
        raise RuntimeError( "HTTP request failed!" )
    report( "elapsed time", ( "%.3f" % ( end_time - start_time )))
    return r

def get_head_info( url, echo = True ):
    r = http_call({ 'method': 'HEAD', 'url': url }, echo = echo )
    str = url
    for key in sorted( r.headers ):
         if key.lower() in [ "last-modified",  "content-length" ]:
            str += " " + key + " " + r.headers[ key ]
    return str

def download_file( url, filename ):
    with requests.get(url, stream=True) as r:
        with open( filename, 'wb') as f:
            shutil.copyfileobj(r.raw, f)

def any_open( filename, mode = "rb"):
    if filename.endswith(".gz"):
        return gzip.open( filename, mode )
    elif filename.endswith(".bz2"):
        return bz2.open( filename, mode )
    elif filename.endswith(".xz"):
        return lzma.open( filename, mode )
    else:
        return open( filename, mode )

# FROM https://graphdb.ontotext.com/documentation/10.7/rdf-formats.html
def guess_mime_type( filename ):
    if re.search( r"\.ttl(|\.gz|\.bz2|\.xz)$", filename ):
       return "text/turtle"
    elif re.search( r"\.ttls(|\.gz|\.bz2|\.xz)$", filename ):
       return "text/x-turtlestar"
    elif re.search( r"\.(trig)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/trig"
    elif re.search( r"\.(trigs)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/x-trigstar"
    elif re.search( r"\.(n3)(|\.gz|\.bz2|\.xz)$", filename ):
        return "text/rdf+n3"
    elif re.search( r"\.(nt)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/n-triples"
    elif re.search( r"\.(nq)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/n-quads"
    elif re.search( r"\.(jsonld)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/ld+json"
    elif re.search( r"\.(ndjsonld|jsonl|ndjson)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/x-ld+ndjson"
    elif re.search( r"\.(rj)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/rdf+json"
    elif re.search( r"\.(rdf|rdfs|owl|xml)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/rdf+xml"
    elif re.search( r"\.(trix)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/trix"
    elif re.search( r"\.(brf)(|\.gz|\.bz2|\.xz)$", filename ):
        return "application/x-binary-rdf"
    else:
        stop_error( "cannot guess RDF mime-type from filename: " + filename )

def print_break():
    print( '# ----------------------------------------------------------------------------')

def print_strip( txt, color = 'black' ):
    """Print after removing leading/trailing spaces"""
    txt = RE_CATCH_TAB.sub( '    ', RE_CATCH_END_SPACE.sub( '', RE_CATCH_BEGIN_SPACE.sub( '', txt )))
    if color :
        print( colored( txt, color ), flush = True )
    else :
        print( txt , flush = True )

def report( key, value, color = "black" ) :
    print( '# ' + colored( f"{key:>12} : {value}" , color ), flush = True )

def print_task( txt ):
    report( 'TASK', txt, color = "black" )

def print_warn( txt ):
    report( 'warning', txt, color = "red" )

def stop_error( txt ):
    report( 'ERROR', txt, color = "red" )
    sys.exit( 1 )
