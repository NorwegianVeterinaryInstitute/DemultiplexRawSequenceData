'''
This is a file with all the constant-constants: things that should be parametrized but they will never change

use by

from demux.config import constants as constants
'''

# directory names
DATA_ROOT_DIR           = "/data"
RAW_DATA_DIR_NAME       = "rawdata"
DEMULTIPLEX_DIR_NAME    = "demultiplex"
FOR_TRANSFER_DIR_NAME   = "for_transfer"
SAMPLESHEET_DIR_NAME    = "samplesheets"
LOG_DIR_NAME            = "log"
MULTIQC_DATA_DIR_NAME	= "multiqc_data"

# suffixes
CSV_SUFFIX 				= ".csv"
QC_SUFFIX               = "_qc"
DEMULTIPLEX_DIR_SUFFIX 	= "_demultiplex"
ZIP_SUFFIX              = '.zip'
COMPRESSED_FASTQ_SUFFIX = '.fastq.gz' 
TAR_SUFFIX              = '.tar'

MD5_SUFFIX              = ".md5"
MD5_LENGTH              = 16  # 128 bits
SHA512_SUFFIX           = ".sha512"
SHA512_LENGTH           = 64  # 512 bits

NIRD_MODE_SSH 			= "ssh"
NIRD_MODE_MOUNTED 		= "mounted"

SERIAL_COPYING  		= "serial"
PARALLEL_COPYING 		= "parallel"

