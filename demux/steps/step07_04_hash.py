import concurrent.futures
import hashlib
import os

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _hash
########################################################################

def _hash_file_sha256( filepath: str ) -> str:
    """
    Compute SHA-256 hex digest of a file.

    Reads in HASH_CHUNK_SIZE chunks to avoid loading
    multi-gigabyte FASTQ files entirely into memory.

    :param filepath: absolute path to the file to hash.
    :returns: SHA-256 hex digest string.
    """
    sha256 = hashlib.sha256( )
    with open( filepath, constants.FILE_READ_BINARY ) as fh:
        while True:
            chunk:bytes = fh.read( constants.HASH_CHUNK_SIZE )
            if not chunk:
                break
            sha256.update( chunk )
    return sha256.hexdigest( )



def _hash( demux ) -> None:
    """
    Compute SHA-256 hashes for every decompressed .fastq file and
    store the results in memory for post-upload verification.

    All files are hashed in parallel with no worker limit.

    :param demux: demux object with irida_decompressed_map set by step07_03.
    :raises FileNotFoundError: if a decompressed file is missing.

    Sets on demux:
        :attr demux.irida_local_hashes: dict { sample_name: { 'r1_sha256': hex, 'r2_sha256': hex } }
    """
    demuxLogger.info( "IRIDA hash: starting" )

    # build a flat list of ( sample_name, label, filepath ) for parallel hashing
    hash_jobs:list = [ ]
    for sample_name, paths in demux.irida_decompressed_map.items():
        r1_fastq:str = paths[ 'r1_fastq' ]
        r2_fastq:str = paths[ 'r2_fastq' ]
        if not os.path.isfile( r1_fastq ):
            raise FileNotFoundError( f"Decompressed R1 file missing: {r1_fastq}" )
        if not os.path.isfile( r2_fastq ):
            raise FileNotFoundError( f"Decompressed R2 file missing: {r2_fastq}" )
        hash_jobs.append( ( sample_name, 'r1', r1_fastq ) )
        hash_jobs.append( ( sample_name, 'r2', r2_fastq ) )

    # hash all files in parallel; no worker limit - let it saturate all cores
    hash_results:dict = { }
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures:dict = { executor.submit( _hash_file_sha256, filepath ): ( sample_name, label, filepath ) for sample_name, label, filepath in hash_jobs }
        for future in concurrent.futures.as_completed( futures ):
            sample_name, label, filepath = futures[ future ]
            sha256_hex:str = future.result()
            file_size:int  = os.path.getsize( filepath )
            demuxLogger.debug( f"IRIDA hash: {sample_name} {label.upper()}={sha256_hex} ({file_size} bytes)" )
            if sample_name not in hash_results:
                hash_results[ sample_name ] = { }
            hash_results[ sample_name ][ f'{label}_sha256' ] = sha256_hex

    demux.irida_local_hashes = hash_results

    demuxLogger.info( f"IRIDA hash: {len( hash_results )} sample(s) hashed" )
