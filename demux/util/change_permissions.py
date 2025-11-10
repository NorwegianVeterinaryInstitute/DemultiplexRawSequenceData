
import inspect
import logging
import os
import stat
import sys
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

#######################################################################
# change_permissions
########################################################################

def change_permissions( demux ):
    """
    changePermissions: recursively walk down from {directoryRoot} and 
        change the owner to :sambagroup
        if directory
            change permissions to 755
        if file
            change permissions to 644

    INPUT
        input is a generic dir_to_chmod rather than demux.demultiplexRunID, because we use this method more than once
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Changing Permissions started ==", color="green", attrs=["bold"] ) )

    # Dynamic resolution of the absolute path to recursively chmod
    if( "demultiplexRunIDdir" == demux.state ):
        dir_to_chmod = demux.demultiplexRunIDdir
        demux.state = "42" # magic variable: sets the directory structure to hash/chmod. Set once per run, changes the first time change_permissions( ) is run
    else:
        dir_to_chmod = demux.forTransferRunIdDir

    demuxLogger.debug( termcolor.colored( f"= walk the file tree, {inspect.stack()[0][3]}() ======================", attrs=["bold"] ) )

    for directoryRoot, dirnames, filenames, in os.walk( dir_to_chmod, followlinks = False ):
    
        # change ownership and access mode of files
        for file in filenames:
            filepath = os.path.join( directoryRoot, file )
            demuxLogger.debug( " "*demux.spacing2 + f"chmod 664 {filepath}" ) # print chmod 664 {dirpath}

            if not os.path.isfile( filepath ):
                text = f"{filepath} is not a file. Exiting." 
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            try:
                # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
                os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH) # rw-rw-r-- / 664 / read-write owner, read-write group, read others
            except FileNotFoundError as err:                # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
                text = [    f"\tFileNotFoundError in {inspect.stack()[0][3]}()",
                            f"\terrno:\t{err.errno}",
                            f"\tstrerror:\t{err.strerror}",
                            f"\tfilename:\t{err.filename}",
                            f"\tfilename2:\t{err.filename2}"
                        ]
                text = '\n'.join( text )
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

    # change ownership and access mode of directories
    demuxLogger.debug( termcolor.colored( f"= walk the dir tree, {inspect.stack()[0][3]}() ======================", attrs=["bold"] ) )
    for directoryRoot, dirnames, filenames, in os.walk( dir_to_chmod, followlinks = False ):

        for name in dirnames:
            dirpath = os.path.join( directoryRoot, name )

            demuxLogger.debug( " "*demux.spacing2 + f"chmod 775 {dirpath}" ) # print chmod 755 {dirpath}

            if not os.path.isdir( dirpath ):
                text = f"{dirpath} is not a directory. Exiting."
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            try:
                # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
                os.chmod( dirpath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH ) # rwxrwxr-x / 775 / read-write-execute owner, read-write-execute group, read-execute others 
            except FileNotFoundError as err:                # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
                text = [
                        f"\tFileNotFoundError in {inspect.stack()[0][3]}()",
                        f"\terrno:\t{err.errno}",
                        f"\tstrerror:\t{err.strerror}",
                        f"\tfilename:\t{err.filename}",
                        f"\tfilename2:\t{err.filename2}"
                ]
                text = '\n'.join( text )
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Changing Permissions finished ==\n", color="red", attrs=["bold"] ) )