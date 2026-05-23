import gzip
import os
import shutil
import stat

from demux.config  import constants
from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# _decompress
########################################################################

def _decompress( demux ) -> None:
    """
    Decompress .fastq.gz files into a temporary directory so that
    sha256 hashes can be computed on the raw .fastq content.

    For each sample in demux.irida_samples:
        1. Create tmp_irida_upload/ under demux.demultiplexRunIDdir.
        2. Gunzip R1.fastq.gz and R2.fastq.gz into tmp/ to produce
           raw R1.fastq and R2.fastq.

    IRIDA does not perform server-side checksum verification on
    uploaded files. We hash the decompressed .fastq before upload,
    then compare against the uploadSha256 field in the IRIDA metadata
    response after upload to verify integrity.

    :param demux: demux object with irida_samples, demultiplexRunIDdir set.
    :raises FileNotFoundError: if a compressed file does not exist or decompression fails.

    Sets on demux:
        :attr demux.irida_tmp_dir:          path to the tmp/ directory.
        :attr demux.irida_decompressed_map: dict { sample_name: { 'r1_fastq': path, 'r2_fastq': path } }
    """

    demuxLogger.info( "IRIDA decompress: starting" )

    demux.irida_tmp_dir = os.path.join( demux.demultiplexRunIDdir, demux.irida_tmp_dir_name )
    os.makedirs( demux.irida_tmp_dir, mode = stat.S_IRWXU, exist_ok = True ) # rwx------ (owner only)

    demuxLogger.info( f"IRIDA decompress: tmp directory at {demux.irida_tmp_dir}" )

    decompressed_map:dict = { }
    for sample in demux.irida_samples:
        # populated by _get_vigasp_samples() and _resolve_fastq_paths() in step07_01_preflight
        sample_name:str = sample[ 'sample_name' ]
        r1_gz:str       = sample[ 'r1' ]
        r2_gz:str       = sample[ 'r2' ]

        for gz_path in ( r1_gz, r2_gz ):
            if not os.path.isfile( gz_path ):
                raise FileNotFoundError( f"Expected compressed file does not exist: {gz_path}" )

        # build decompressed .fastq paths: strip .gz from basename, place in tmp dir
        r1_basename:str    = os.path.basename( r1_gz )
        r2_basename:str    = os.path.basename( r2_gz )
        r1_fastq_name:str  = r1_basename.removesuffix( constants.GZ_SUFFIX )
        r2_fastq_name:str  = r2_basename.removesuffix( constants.GZ_SUFFIX )
        r1_fastq_path:str  = os.path.join( demux.irida_tmp_dir, r1_fastq_name )
        r2_fastq_path:str  = os.path.join( demux.irida_tmp_dir, r2_fastq_name )

        for gz_path, fastq_path in ( ( r1_gz, r1_fastq_path ), ( r2_gz, r2_fastq_path ) ):
            demuxLogger.debug( f"IRIDA decompress: gunzip {gz_path} -> {fastq_path}" )
            with gzip.open( gz_path, constants.READ_ONLY_BINARY ) as f_in:
                with open( fastq_path, constants.FILE_WRITE_BINARY ) as f_out:
                    shutil.copyfileobj( f_in, f_out )
            if not os.path.isfile( fastq_path ):
                raise FileNotFoundError( f"Decompressed file was not written to disk: {fastq_path}" )

        decompressed_map[ sample_name ] = { 'r1_fastq': r1_fastq_path, 'r2_fastq': r2_fastq_path }
        demuxLogger.debug( f"IRIDA decompress: {sample_name} R1={r1_fastq_path} R2={r2_fastq_path}" )

    demux.irida_decompressed_map = decompressed_map

    demuxLogger.info( f"IRIDA decompress: {len( decompressed_map )} sample(s) decompressed" )