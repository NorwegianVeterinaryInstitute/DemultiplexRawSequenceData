#!/usr/bin/python3.11

import hashlib
import logging
import os
import subprocess
import sys


"""

calculate the checksums module.

"""

########################################################################
# hash_file
########################################################################

def hash_file(filepath):
    """
    Calculate the md5 and the sha512 hash of an object and return
        filepath, md5sum, sha512sum
    """
    with open(filepath, 'rb') as filehandle:
        filetobehashed = filehandle.read()
    md5sum       = hashlib.md5(filetobehashed).hexdigest()
    sha512sum    = hashlib.sha512(filetobehashed).hexdigest()
    return filepath, md5sum, sha512sum


########################################################################
# write_checksum_files
########################################################################

def write_checksum_files(args):
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
# calcFileHash
########################################################################

def calc_file_hash( eitherRunIdDir ):
    """
    Calculate the md5 sum for files which are meant to be delivered:
        .tar
        .zip
        .fasta.gz

    INPUT
        '''eitherRunIdDir refers to either demux.demultiplexRunIdDir or demux.forTransferRunIdDir; we use this method more than once

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

    if demux.debug:
        demuxLogger.debug( f"for debug puproses, creating empty files {demux.demultiplexRunIdDir}/foo.tar and {demux.demultiplexRunIdDir}/bar.zip\n" )
        pathlib.Path( os.path.join( demux.demultiplexRunIdDir, demux.footarfile ) ).touch( )
        pathlib.Path( os.path.join( demux.demultiplexRunIdDir, demux.barzipfile ) ).touch( )


    # build the filetree
    demuxLogger.debug( f'= walk the file tree, {inspect.stack()[0][3]}() ======================')

    fileList = list( )
    for directoryRoot, dirnames, filenames, in os.walk( eitherRunIdDir, followlinks = False ):

        for file in filenames:
            if not any( var in file for var in [ demux.compressedFastqSuffix, demux.zipSuffix, demux.tarSuffix ] ): # grab only .zip, .fasta.gz and .tar files
                continue

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
