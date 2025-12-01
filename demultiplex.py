#!/usr/bin/env -S -- /usr/bin/python3.11 -X pycache_prefix=/tmp/demultiplex

########################################################################
# Demutliplex a MiSEQ or NextSEQ run, perform QC using FastQC and
# MultiQC and deliver files either to VIGASP for analysis or NIRD for
# archiving
#
# https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData
#
# Copyright: The Norwegian Veterinary Institute
# Licenced under the GNU Public License 3.0 of newer
#

import argparse
import ast
import pdb
import glob
import hashlib
import grp
import logging
import logging.handlers
import os
import pathlib
import re
import resource
import shutil
import socket
import stat
import string
import subprocess
import sys
import syslog
import tarfile
import termcolor

from inspect            import currentframe, getframeinfo

# Breaking down the script into more digestible chunks

from demux.loggers                                              import setup_event_and_log_handling, setup_file_log_handling
from demux.core                                                 import demux             # the demux object is where the whole initilization happens. read the top of demux/demux.py for more into

from demux.util.buffering_smtp_handler                          import BufferingSMTPHandler
from demux.util.checksum                                        import calc_file_hash
from demux.util.change_permissions                              import change_permissions

from demux.detect_new_runs                                      import detect_new_runs

from demux.envsetup.setup_environment                           import setup_environment
from demux.envsetup.create_demultiplex_directory_structure      import create_demultiplex_directory_structure
from demux.envsetup.prepare_fortransfer_directory_structure     import prepare_fortransfer_directory_structure
from demux.envsetup.copy_sample_sheet_into_demultiplex_runiddir import copy_sample_sheet_into_demultiplex_runiddir
from demux.envsetup.archive_sample_sheet                        import archive_sample_sheet

from demux.diagnostics.print_running_environment                import print_running_environment
from demux.diagnostics.check_running_environment                import check_running_environment

from demux.steps.step01_demultiplex                             import bcl2fastq
from demux.steps.step02_rename                                  import rename_files_and_directories
from demux.steps.step03_quality_check                           import quality_check
from demux.steps.step04_prepare_delivery                        import prepare_delivery
from demux.steps.step05_control_projects_qc                     import control_projects_qc
from demux.steps.step06_tar_file_quality_check                  import tar_file_quality_check
from demux.steps.step07_deliver_files_to_VIGASP                 import deliver_files_to_VIGASP
from demux.steps.step08_deliver_files_to_NIRD                   import deliver_files_to_NIRD
from demux.steps.step99_finalize                                import finalize

from demux.loggers import demuxLogger, demuxFailureLogger


"""
demultiplex.py:
    Demultiple Illumina bcl files and prepearing them for delivery to the individual NVI systems for subprocessing

    Module can run on its own, without needing to include in a library as such:

    /data/bin/demultiplex.py   200306_M06578_0015_000000000-CWLBG
    path to script           | RunID directory from /data/rawdata

INPUTS:
    - RunID directory from /data/rawdata

    SPECIFIC FILES WE CARE WITHIN /data/rawdata/RunID:
    - *.zip
    - *.fasta.gz
    - *.tar
    - *.html
    - *.jp[e]g
    - RtaComplexe.txt
    - SampleSheet.csv

    SPECIFIC FILES WE IGNORE WITHIN /data/rawdata/RunID:
    - *.txt

OUTPUTS:
    - fastq.gz files that are used by FastQC and MultiQC
    - MultiQC creates .zip files which are included in the QC tar file
    - .tar files for the fastq.gz and .md5/.sha512 hashes
    - [Future feature] Upload files to VIGASP
    - [Future feature] Archive files to NIRD

WHY DOES THIS PROGRAM EXIST
    Illumina does not provide a complete pipeline for what you want to do with your data. They provide the basics: bcl2fastq, a demultiplex tool written in C++ . 
    Everythinng else, including automation of processing and delivery is up to the end customer, and in this case NVI

    So, essentially, this script is an attempt at automation workflow:
        sequencing -> demultiplexing -> quality checking -> delivering the results of the demultiplexing and the QC to the appropriate places, in the case of NVI, VIGASP and NIRD

WHERE DO PROJECTS GET THEIR NEW {runIDShort}.{project} NAME?
    In demux.parse_sample_sheet( ) . We are building the project names there, might as well put the compliance as well.

WHAT DO THE FASTQ.GZ FILES CONTAIN
    The .fastq.gz contain all the fastq files from the blc2fastq demultiplexing

WHAT DO THE ZIP FILES CONTAIN
    The .zip files are the result of the qualitative analysis of the fastq.gz files. They contain the analysis in html and pictures and some fastqc files (qc files for fasta files)

WHAT DOES THE TAR FILE CONTAIN
    Each .tar file contains the files under each Sample_Project in each run.
    for example:
    221014_M06578_0118_000000000-KMYV8_demultiplex contains: 
        221014_M06578.12150-114-Utbrudd/
        221014_M06578.APEC-Nortura/
        221014_M06578.AMR-biofilm/
        221014_M06578.APEC-Samvirkekylling/
        221014_M06578.Norwegian-Airways/
        221014_M06578.Ringtest-listeria-EURL/
        221014_M06578.SEQ-TECH-Providencia/
        221014_M06578.Salmonella-overvaakning-NRL/

    Then under /data/for_transfer/221014_M06578_0118_000000000-KMYV8 , there should be
        221014_M06578.12150-114-Utbrudd.tar
        221014_M06578.12150-114-Utbrudd.md5
        221014_M06578.12150-114-Utbrudd.sha512
        221014_M06578.APEC-Nortura.tar
        221014_M06578.APEC-Nortura.md5
        221014_M06578.APEC-Nortura.sha512
        21014_M06578.AMR-biofilm.tar
        21014_M06578.AMR-biofilm.md5
        21014_M06578.AMR-biofilm.sha512
        221014_M06578.APEC-Samvirkekylling.tar
        221014_M06578.APEC-Samvirkekylling.md5
        221014_M06578.APEC-Samvirkekylling.sha512
        221014_M06578.Norwegian-Airways.tar
        221014_M06578.Norwegian-Airways.md5
        221014_M06578.Norwegian-Airways.sha512
        221014_M06578.Ringtest-listeria-EURL.tar
        221014_M06578.Ringtest-listeria-EURL.md5
        221014_M06578.Ringtest-listeria-EURL.sha512
        221014_M06578.SEQ-TECH-Providencia.tar
        221014_M06578.SEQ-TECH-Providencia.md5
        221014_M06578.SEQ-TECH-Providencia.sha512
        221014_M06578.Salmonella-overvaakning-NRL.tar
        221014_M06578.Salmonella-overvaakning-NRL.md5
        221014_M06578.Salmonella-overvaakning-NRL.sha512

    meaning, 
        - one tar file per Sample_Project
        - one md5 file for the tar file
        - additional sha512 file for extra assurance the file is unique

WHAT DOES THE QC TAR FILE CONTAIN
    The QC tar file contains all the files under the {demux.runIDShort}_QC and multiqc_data directories 
    It is named as
        RunIDshort_QC, eg: 200624_M06578_QC

WHERE ARE ALL THE VARIABLES CREATED
    In setupEnvironment( )

WHY NOT USE MD5 ANY MORE AND PREFER SHA512
    The md5 hash space is easy nowdays to be exausted. MD5 was proven to to be easily exaustible in 2002 with the then hardware. With the files available today and the faster, multicore hardware, md5 can easily have collision between two filenames that have nothing to do with each other.
    the sha512 hash has more items in its search space more than 100 billion times the atoms in our universe, practically guaranteeing that collisions (and therefore files with the shame sha512 signature) will be highly improbable to happen.

WHY THIS PROGRAM SHOULD EVENTUALLY BE A DAEMON
    To be discussed

WHAT DOES THIS SCRIPT DO
    This script does the following things
    - Demultiplex the raw BCL illumina files
    - Creates the hierarchy of the current run based on each Sample_Project included in Sample_Sheet.csv
    - Performs QC using FastQC
    - Performs QC using MultiQC
    - Hashes via md5/sha512 all the files that are supposed to be delivered
    - Packages output results into two files .tar and _QC.tar, ready to be archived.
    - [Future feature] Upload files to VIGASP
    - [Future feature] Archive files to NIRD


PREREQUISITES
    - uses Illumina's blc2fastq tool     ( https://emea.support.illumina.com/downloads/bcl2fastq-conversion-software-v2-20.html )
    - uses FastQ                         ( https://www.bioinformatics.babraham.ac.uk/projects/download.html#fastqc )
    - uses MultiQC                       ( as root, pip3 install multiqc )
    - hashing is done by the internal Python3 hashlib library (do not need any external or OS level packages)
        - hashing can be memory intensive as the entire file is read to memory
        - should be ok, unless we start sequencing large genomes
    - dnf install python3-termcolor python3-xtermcolor


LIMITATIONS
    - Can demultipex one directory at a time only
    - No sanity checking to see if a demultiplexed directory is correctly demux'ed
    - Relies only on output directory name and does not verify contents

"""



########################################################################
# MAIN
########################################################################

def main( RunID ):
    """
    Main function for the demultiplex script.
    All actions are coordinated through here
    """
    setup_event_and_log_handling( )                                                                     # setup the event and log handing, which we will use everywhere, sans file logging 

    if RunID != RunID.rstrip('/,.'):
        demuxLogger.info( "Warning: RunID contained trailing punctuation or slashes, cleaned automatically." )
    RunID = RunID.rstrip('/,.')                                                                         # Be forgiving any ',' '/' or '.' during copy-paste

    # # RunID = detect_new_runs( demux )                                                                  # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/122
    setup_environment( RunID )                                                                          # set up variables needed in the running setupEnvironment # demux.RunID is set here
    # # displayNewRuns( )                                                                                 # show all the new runs that need demultiplexing
    create_demultiplex_directory_structure( demux )                                                     # create the directory structure under {demux.demultiplexRunIDdir}
    # #####################################################################################################
    # # create_demultiplex_directory_structure( ) needs to be called before we start logging to file:
    # #   Cannot create a log *file* without having a specific *directory* structure, can we? 
    # #####################################################################################################s
    setup_file_log_handling( demux )                                                                    # setup the file event and log handing, which we left out
    print_running_environment( demux )                                                                  # print our running environment
    check_running_environment( demux )                                                                  # check our running environment
    copy_sample_sheet_into_demultiplex_runiddir( demux )                                                # copy SampleSheet.csv from {demux.sampleSheetFilePath} to {demux.demultiplexRunIDdir}
    archive_sample_sheet( demux )                                                                       # make a copy of the Sample Sheet for future reference
    bcl2fastq( demux )                                                                                  # use blc2fastq to convert .bcl files to fastq.gz
    rename_files_and_directories( demux )                                                               # rename the *.fastq.gz files and the directory project to comply to the {runIDShort}.{project} convention
    quality_check( demux )                                                                              # execute QC on the incoming fastq files
    calc_file_hash( demux )                                                                             # create .md5/.sha512 checksum files for every .fastqc.gz/.tar/.zip file under demultiplexRunIDdir
    change_permissions( demux )                                                                         # change permissions for the files about to be included in the tar files 
    prepare_fortransfer_directory_structure( demux )                                                    # create /data/for_transfer/RunID and any required subdirectories
    prepare_delivery( demux )                                                                           # prepare the delivery files
    calc_file_hash( demux )                                                                             # create .md5/.sha512 checksum files for the delivery .fastqc.gz/.tar/.zip files under demultiplexRunIDdir, but this 2nd fime do it for the new .tar files created by prepareDelivery( )
    change_permissions( demux )                                                                         # change permissions for all the delivery files, including QC
    control_projects_qc( demux )                                                                        # check to see if we need to create the report for any control projects present
    tar_file_quality_check( demux )                                                                     # QC for tarfiles: can we untar them? does untarring them keep match the sha512 written? have they been tampered with while in storage?
    if demux.transfer_to_vigas:
        demuxLogger.debug( f"{RunID} has to be uploaded to VIGASP" )
        deliver_files_to_VIGASP( demux )                                                                # Deliver the output files to VIGASP
    if demux.transfer_to_nird:
        demuxLogger.debug( f"{RunID} has to be uploaded to NIRD" )
        deliver_files_to_NIRD( demux )                                                                  # deliver the output files to NIRD
    # finalize( demux )                                                                                 # mark the script as complete
    # shutdownEventAndLoggingHandling( )                                                                # shutdown logging before exiting.

    if not ( demux.transfer_to_vigas and demux.transfer_to_nird ):
        demuxLogger.info( termcolor.colored( f"\n\nNo files uploaded.\n", color="light_cyan", attrs=["blink"] ) )
    demuxLogger.info( termcolor.colored( "\n====== All done! ======\n", attrs=["blink"] ) )
    logging.shutdown( )



########################################################################
# MAIN
########################################################################

if __name__ == '__main__':

    parser = argparse.ArgumentParser()

    if sys.hexversion < 51056112: # Require Python 3.11 or newer
        sys.exit( "Python 3.11 or newer is required to run this program." )

    # FIXMEFIXME add named arguments
    if len(sys.argv) == 1:
        sys.exit( "No RunID argument present. Exiting." )

    RunID                   = sys.argv[1]

    main( RunID )
