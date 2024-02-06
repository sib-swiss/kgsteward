import requests
import time
import re
import dumper

from termcolor import colored

RE_CATCH_BEGIN_SPACE = re.compile( "^(\\s*)" )
RE_CATCH_END_SPACE   = re.compile( "(\\s*)$" )
RE_CATCH_TAB         = re.compile( "(\\t)" )

def http_call( request_args, status_code=[200], echo=True ):
    """A simple wrapper function arround requests.request() which 
main purpose is to
    (1) validate status code
	(1) print elapsed time
    (2) print query parameters in case of an unexpected status code."""     
    if echo :   
        print( '#', request_args['method'], request_args['url'], flush=True )
    start_time = time.time()
    r = requests.request( **request_args )
    end_time = time.time() 
    if r.status_code not in status_code :
        dumper.dump( request_args )
        print( r.status_code, flush=True )
        print( r.text if not r.text is None else '', flush=True )
        raise RuntimeError( "HTTP request failed!" )
    print( "# Elapsed time:", end_time - start_time, flush=True ) 
    return r

def print_break():
	print()
	print( '# ------------------------------------------------------- #' )

def print_strip( txt, color = None ):
    """Print after removing leading/trailing spaces"""
    txt = RE_CATCH_TAB.sub( '    ', RE_CATCH_END_SPACE.sub( '', RE_CATCH_BEGIN_SPACE.sub( '', txt )))
    if color :
        print( colored( txt, color ), flush = True )
    else :
        print( txt , flush = True )

