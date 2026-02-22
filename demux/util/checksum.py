import hashlib
import inspect
import logging
import os
import pathlib
import subprocess
import sys
import termcolor

from concurrent.futures import ProcessPoolExecutor

from demux.loggers import demuxLogger, demuxFailureLogger

import demux.config.constants as constants

"""

calculate file checksums module.

"""

########################################################################
# hash_file
########################################################################

def hash_file( filepath ):
    """
    Calculate the md5 and the sha512 hash of an object and return
        filepath, md5sum, sha512sum
    """
    with open( filepath, 'rb' ) as filehandle:
        filetobehashed = filehandle.read( )
    md5sum       = hashlib.md5( filetobehashed ).hexdigest( )
    sha512sum    = hashlib.sha512( filetobehashed ).hexdigest( )
    return filepath, md5sum, sha512sum


########################################################################
# write_checksum_files
########################################################################

def write_checksum_files( args ):
    """
        Write the checksum files
    """
    filepath, md5sum, sha512sum = args

    def write_file( suffix, content ):
        checksum_file = f"{filepath}{suffix}"
        if not os.path.isfile( checksum_file ):
            with open( checksum_file, "w") as fh:
                fh.write( content )
            # print( f"{checksum_file}: written" )
            return checksum_file

        demuxLogger.critical( f"{checksum_file}: exists, skipped" )
        return checksum_file

    twoMandatorySpaces              = "  "
    write_file( constants.MD5_SUFFIX,    f"{md5sum}{twoMandatorySpaces}{os.path.basename( filepath )}\n" )     # the two spaces are mandatory to be re-verified after uploading via 'md5sum -c FILE'
    write_file( constants.SHA512_SUFFIX, f"{sha512sum}{twoMandatorySpaces}{os.path.basename( filepath )}\n" )  # the two spaces are mandatory to be re-verified after uploading via 'sha512sum -c FILE'
    demuxLogger.debug( f"md5sum: {md5sum:{constants.MD5_LENGTH}} | sha512sum: {sha512sum:{constants.SHA512_LENGTH}} | filepath: {filepath}" ) # print for the benefit of the user



########################################################################
# is_file_large
########################################################################

def is_file_large( args ):
    """ Checks if a hash file exceeds the given size in KB. 
    This is a check to make sure we are writing the resulting digest to file and not the entire bloody hash
    """
    filepath       = args[0]
    max_size_bytes = 512

    # see if there .md5 files written are over the 2k
    try:
        size_bytes = os.path.getsize( f"{filepath}{constants.MD5_SUFFIX}" )
        if size_bytes > max_size_bytes:
            demuxLogger.critical( termcolor.colored(  f"file {filepath}{constants.MD5_SUFFIX} is over the {max_size_bytes} byte range!", color="red", attrs=["bold"] ) )
    except FileNotFoundError:
        demuxLogger.critical( f"File not found: {filepath}{constants.MD5_SUFFIX}" )

    # see if there .sha512 files written are over the 2k
    try:
        size_bytes = os.path.getsize( f"{filepath}{constants.SHA512_SUFFIX}" )
        if size_bytes > max_size_bytes:
            demuxLogger.critical( termcolor.colored(  f"file {filepath}{constants.SHA512_SUFFIX} is over the {max_size_bytes} byte range!", color="red", attrs=["bold"] ) )
    except FileNotFoundError:
        demuxLogger.critical( f"File not found: {filepath}{constants.SHA512_SUFFIX}" )



########################################################################
# calc_file_hash
########################################################################

def calc_file_hash( demux ):
    """
    Calculate the md5 sum for files which are meant to be delivered:
        .tar
        .zip
        .fasta.gz

    INPUT
        the demux object. It has a self.state string property which we check to see what path to assign to dir_to_hash

    ORIGINAL EXAMPLE: /usr/bin/md5deep -r /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex | /usr/bin/sed s /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/  g | /usr/bin/grep -v md5sum | /usr/bin/grep -v script

    what we do here:
        walk the tree
        find relevant file
        check if the file already has an .md5 file related to it
        if not, hash it
    
    Disadvantages: this function is memory heavy, because it reads the contents of the files into memory

    ORIGINAL COMMAND: /usr/bin/md5deep -r {demux.DemultiplexRunIdDir} | /usr/bin/sed s {demux.DemultiplexRunIdDir}  g | /usr/bin/grep -v md5sum | /usr/bin/grep -v script
    EXAMPLE: /usr/bin/md5deep -r /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex | /usr/bin/sed s /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/  g | /usr/bin/grep -v md5sum | /usr/bin/grep -v script

    """

    dir_to_hash = str( )
    if( "demultiplexRunIDdir" == demux.state ):
        dir_to_hash = demux.demultiplexRunIDdir
    else:
        dir_to_hash = demux.forTransferRunIdDir

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files started ==", color="green", attrs=["bold"] ) )

    # build the filetree
    demuxLogger.debug( f'= walk the file tree dir_to_hash: {dir_to_hash} ======================')

    fileList = list( )
    for directoryRoot, dirnames, filenames, in os.walk( dir_to_hash, followlinks = False ):

        for file in filenames:
            if not any( var in file for var in [ demux.compressedFastqSuffix, demux.zipSuffix, demux.tarSuffix ] ): # grab only .zip, .fasta.gz and .tar files
                continue

            filepath = os.path.join( directoryRoot, file )

            # Check if any filenames are .md5/.sha512 files
            if any( var in file for var in [ demux.sha512Suffix, demux.md5Suffix ] ):
                text = f"{filepath} is already an sha512/md5 file!."
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                continue

            if not os.path.isfile( filepath ):
                text = f"{filepath} is not a file. Exiting."
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            if not any( filepath ): # make sure it's not a zero length file 
                demuxLogger.warning( termcolor.colored(  f"file {filepath} has zero length. Skipping.", color="purple", attrs=["bold"] ) )
                continue

            fileList.append( filepath )

    # DO NOT REMOVE list() on any of these executors!
    # executor.map() is lazy; it returns an iterator of results, not a list. Until you iterate over it, no tasks are dispatched to worker processes.
    # When the with block ends, the pool closes before launching any work. Wrapping it in list() forces full iteration so all tasks actually run.
    # So, we need that list( ) there, even if it returns nothing.

    # since we got 96gb of ram, read all the files in and hash them in parallel
    with ProcessPoolExecutor( ) as executor:
        filePathAndHashesResults = list( executor.map( hash_file, fileList ) ) # hash_file( ) returns filepath, md5sum, sha512sum

    # write the checksums to disk, in parallel
    with ProcessPoolExecutor() as executor:
        list( executor.map( write_checksum_files, filePathAndHashesResults ) )

    # make sure we are writing hash files in the 2kb range and not abominations
    with ProcessPoolExecutor() as executor:
        list( executor.map( is_file_large, filePathAndHashesResults ) )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files finished ==\n", color="red", attrs=["bold"] ) )
