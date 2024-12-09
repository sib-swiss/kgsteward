# The code below was strongly inspired by
#    https://github.com/python/cpython/blob/3.12/Lib/http/server.py
# eventhough aI don't understand all the technical details

import http.server
import time
import multiprocessing

class MyServer( http.server.ThreadingHTTPServer ):

    def __init__( self, addr, HandlerClass, directory ): # an ad hoc constructor with the directory parameter
        super().__init__( addr, HandlerClass )
        self.directory = directory

    def finish_request(self, request, client_address):
        self.RequestHandlerClass( request, client_address, self, directory=self.directory )

def _expose_directory( directory, port = 8000 ):
    HandlerClass = http.server.SimpleHTTPRequestHandler
    httpd        = MyServer(( "", port ), HandlerClass, directory )
    httpd.serve_forever()

class LocalFileServer() :
    port      = None
    directory = None
    thread    = None

    def __init__( self, port = 8000 ) :
        self.port = port

    def expose( self, directory ) :
        if( self.thread and self.thread.is_alive() ):
            if( self.directory == directory ):
                return # directory is already exposed
            else :
                self.terminate()
        self.directory = directory
        mp_context = multiprocessing.get_context( 'fork' )
        self.thread = mp_context.Process(
            target=_expose_directory,
            args=( self.directory, self.port ),
            daemon=True
        )
        self.thread.start()
        print( f"# Directory {self.directory} is exposed on http://localhost:{self.port}" )
        time.sleep( 0.2 ) # leaves some time for the seerver to start

    def terminate( self ) :
        if( self.thread and self.thread.is_alive() ):
            self.thread.terminate();
        self.directory = None
        self.thread    = None

def test():
    lfs = LocalFileServer( 8000 )
    lfs.expose( "/Users/mpagni/github.com" )
    time.sleep( 2 )
    lfs.expose( "/Users/mpagni/gitlab.com" )
    time.sleep( 2 )
    lfs.terminate()

# test()


