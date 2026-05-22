'''
This is a file with all the constant-constants: things that should be parametrized but they will never change

use by

from demux.config import constants as constants
'''

import re

# directory names
DATA_ROOT_DIR:str           = "/data"
RAW_DATA_DIR_NAME:str       = "rawdata"
DEMULTIPLEX_DIR_NAME:str    = "demultiplex"
FOR_TRANSFER_DIR_NAME:str   = "for_transfer"
SAMPLESHEET_DIR_NAME:str    = "samplesheets"
LOG_DIR_NAME:str            = "log"
MULTIQC_DATA_DIR_NAME:str   = "multiqc_data"

# suffixes
CSV_SUFFIX:str              = ".csv"
QC_SUFFIX:str               = "_qc"
DEMULTIPLEX_DIR_SUFFIX:str  = "_demultiplex"
ZIP_SUFFIX:str              = '.zip'
COMPRESSED_FASTQ_SUFFIX:str = '.fastq.gz' 
TAR_SUFFIX:str              = '.tar'

MD5_SUFFIX:str              = ".md5"
MD5_LENGTH:int              = 16  # 128 bits
SHA512_SUFFIX:str           = ".sha512"
SHA512_LENGTH:int           = 64  # 512 bits

NIRD_MODE_SSH:str           = "ssh"
NIRD_MODE_SSH_2FA:str       = "ssh2fa"
NIRD_MODE_MOUNTED:str       = "mounted"

SERIAL_COPYING:str          = "serial"
PARALLEL_COPYING:str        = "parallel"

BITWARDEN_CLI_PATH:str      = "/usr/local/bin/bw"
# CURL_CLI_PATH:str           = "/usr/bin/curl" # we do not need curl, we are making the API calls using urllib of python

READ_ONLY_BINARY:str        = "rb"
READ_ONLY_TEXT:str          = "r"


USER_SSH_CONFIG_PATH: str       = "~/.ssh/config"
USER_SSH_KNOWN_HOSTS_PATH: str  = "~/.ssh/known_hosts"

BW_IP                       = '127.0.0.1'
BW_BASE_URL: str            = f'http://{BW_IP}'
BW_PORT:int                 = 8087

RUNID_PATTERN               = re.compile(r'^\d{6}_[A-Z0-9]+_\d{4}_\d{9}-[A-Z0-9]{5}$') # make sure that the RunID we get passed follows a pattern

MISEQ_TAGS                  = ['M06578', 'M09180']  # array of serial numbers for miseq. Change to read from config, or read from illumina
NEXTSEQ_TAGS                = ['NB552450']          # array of serial numbers for nextseq. Change to read from config, or read from illumina

VERSION                     = '1.6.1'

IRIDA_TIMEOUT_MULTIPLIER:int = 10
IRIDA_MAX_IN_FLIGHT:int      = 4
IRIDA_RATE_LIMIT_DELAY:float = 0.5