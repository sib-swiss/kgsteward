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
        report( request_args['method'], request_args['url'] )
    start_time = time.time()
    r = requests.request( **request_args )
    end_time = time.time() 
    if r.status_code not in status_code :
        dumper.dump( request_args )
        print( r.status_code, flush=True )
        print( r.text if not r.text is None else '', flush=True )
        raise RuntimeError( "HTTP request failed!" )
    report( "elapsed time", end_time - start_time ) 
    return r

def get_head_info( url ):
    r = http_call({ 'method': 'HEAD', 'url': url })
    str = ""
    for key in sorted( r.headers ):
         if key.lower() in [ "last-modified",  "content-length" ]:
            str += key + " " + r.headers[ key ] + " "
    return str

def print_break():
    # print()
# print( '# ------------------------------------------------------- #' )
    print( '# -----------------------------------------------------------------')


def print_strip( txt, color = None ):
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


