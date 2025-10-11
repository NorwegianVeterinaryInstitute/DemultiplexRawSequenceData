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
    md5sum       = hashlib.md5(filetobehashed).hexdigest( )
    sha512sum    = hashlib.sha512(filetobehashed).hexdigest( )
    return filepath, md5sum, sha512sum


########################################################################
# write_checksum_files
########################################################################

def write_checksum_files( args ):
    """
        Write the checksum files
    """
    filepath, md5sum, sha512sum = args

    def write_file(suffix, content):
        checksum_file = f"{filepath}{suffix}"
        if not os.path.isfile(checksum_file):
            with open(checksum_file, "w") as fh:
                fh.write(content)
            return f"{checksum_file}: written"
        return f"{checksum_file}: exists, skipped"

    twoMandatorySpaces = "  "
    write_file(demux.md5Suffix,    f"{md5sum}{twoMandatorySpaces}{os.path.basename( filepath )}\n")     # the two spaces are mandatory to be re-verified after uploading via 'md5sum -c FILE'
    write_file(demux.sha512Suffix, f"{sha512sum}{twoMandatorySpaces}{os.path.basename( filepath )}\n")  # the two spaces are mandatory to be re-verified after uploading via 'sha512sum -c FILE'
    demuxLogger.debug(f"md5sum: {md5sum:{demux.md5Length}} | sha512sum: {sha512sum:{demux.sha512Length}} | filepath: {filepath}") # print for the benetif of the user



########################################################################
# is_file_large
########################################################################

def is_file_large( filepath, max_size_kb = 2 ):
    """ Checks if a file exceeds the given size in KB. 
    This is a check to make sure we are writing the resulting digest to file and not the entire bloody hash
    """
    try:
        size_kb = os.path.getsize(filepath) / 1024  # Convert bytes to KB
        if size_kb > max_size_kb:
            demuxLogger.critical( termcolor.colored(  f"file {filepath} is over the kb range!", color="red", attrs=["bold"] ) )
    except FileNotFoundError:
        demuxLogger.critical( f"File not found: {filepath}" )


########################################################################
# calc_file_hash
########################################################################

def calc_file_hash( demux, dir_to_hash ):
    """
    Calculate the md5 sum for files which are meant to be delivered:
        .tar
        .zip
        .fasta.gz

    INPUT
        '''dir_to_hash refers to either demux.demultiplexRunIDdir or demux.forTransferRunIDdir; we use this method more than once

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

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files started ==", color="green", attrs=["bold"] ) )

    print( f"dir_to_hash: {dir_to_hash}")
    attr_name = dir_to_hash  # string key, e.g. "runOutputDir"
    if hasattr(demux, attr_name):
        dir_to_hash = getattr(demux, attr_name)
    else:
        raise AttributeError(f"demux has no attribute '{attr_name}'")
    print(f"dir_to_hash resolved to: {dir_to_hash}")

    sys.exit( )



    # build the filetree
    # demuxLogger.debug( f'= walk the file tree, {inspect.stack()[0][3]}() ======================')
    demuxLogger.debug( f'= walk the file tree dir_to_hash: {dir_to_hash} ======================')

    fileList = list( )
    for directoryRoot, dirnames, filenames, in os.walk( dir_to_hash, followlinks = False ):

        for file in filenames:
            if not any( var in file for var in [ demux.compressedFastqSuffix, demux.zipSuffix, demux.tarSuffix ] ): # grab only .zip, .fasta.gz and .tar files
                continue

            demuxLogger.debug( f'Working on file: ' )
            # Check if any filenames are .md5/.sha512 files
            if any( var in file for var in [ demux.sha512Suffix, demux.md5Suffix  ] ):
                text = f"{filepath} is already a sha512 file!."
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                continue

            filepath = os.path.join( directoryRoot, file )

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
        
    # joined = '\n\t'.join(fileList)
    # demuxLogger.debug( f"fileList:\n\t{joined}")
    # print( f"demux.debug: {demux.debug}")

    # since we got 96gb of ram, read all the files in and hash them in parallel
    with ProcessPoolExecutor( ) as executor:
        filePathAndHashesResults = list( executor.map( hash_file, fileList ) ) # hash_file( ) returns filepath, md5sum, sha512sum

    # write the checksums to disk, in parallel
    with ProcessPoolExecutor() as executor:
        executor.map( write_checksum_files, filePathAndHashesResults )

    # make sure we are writing files in the 2kb range and not abominations
    with ProcessPoolExecutor() as executor:
        executor.map( is_file_large, filePathAndHashesResults )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files finished ==\n", color="red", attrs=["bold"] ) )
