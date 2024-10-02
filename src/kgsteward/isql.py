import subprocess

class IsqlProcess():

    def __init__( self, username = "dba", password = "dba", echo = True ):
        self.isql = subprocess.Popen(
            [ "isql", "-U " + username, "-P " + password ],
            shell  = True,
            stdin  = subprocess.PIPE,
            stdout = subprocess.PIPE,
            text = True
        )
        line = self.isql.stdout.readline()
        while not line.startswith( 'Type HELP' ):
            if echo:
                print( line.rstrip('\n'))
            line = self.isql.stdout.readline()
        if echo:
            print( line.rstrip('\n'))

    def call( self, cmd ):
        if not cmd.endswith( "\n" ):
            cmd = cmd + "\n"
        self.isql.stdin.write( cmd + "\n" )
        line = self.isql.stdout.readline()
        print( line )

isql = IsqlProcess()
isql.call( "STATUS();")
