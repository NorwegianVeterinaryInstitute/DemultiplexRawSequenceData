#!/usr/bin/env python3.11

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
from demux.util.checksum                                        import hash_file, write_checksum_files, is_file_large, calc_file_hash # functions needed for checksum

from demux.envsetup.setup_environment                           import setup_environment
from demux.envsetup.create_demultiplex_directory_structure      import create_demultiplex_directory_structure
from demux.envsetup.prepare_fortransfer_directory_structure     import prepare_fortransfer_directory_structure
from demux.envsetup.copy_sample_sheet_into_demultiplex_runiddir import copy_sample_sheet_into_demultiplex_runiddir
from demux.envsetup.archive_sample_sheet                        import archive_sample_sheet

from demux.diagnostics.print_running_environment                import print_running_environment
from demux.diagnostics.check_running_environment                import check_running_environment

from demux.steps.step01_demultiplex                             import bcl2fastq
from demux.steps.step02_rename                                  import rename_files, rename_directories, rename_files_and_directories
from demux.steps.step03_quality_check                           import quality_check, fastqc, prepare_multiqc, multiqc

# do not uncomment the following line, it is here for copy-pasting into other modules
# from demux.loggers import demuxLogger, demuxFailureLogger

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

WHERE DO PROJECTS GET THEIR NEW {RunIDShort}.{project} NAME?
    In demux.getProjectName( ) . We are building the project names there, might as well put the compliance as well. (This might change)

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
    The QC tar file contains all the files under the {demux.RunIDShort}_QC and multiqc_data directories 
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
# tarProjectFiles
########################################################################

def tarProjectFiles( ):
    """

    """
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Adding files to tape archives started ==", color="yellow" ) )

#---------- Prepare a list of the projects to tar under /data/for_transfer ----------------------

    # this looks duplicated from demux.getProjects( ) and it is, but I am not sure how to resolve the duplication. Let's keep this for now as second check, as this is more complete than
    # the one found in demux.getProjects( )
    
    tarFile = ""
    projectsToProcessList = [ ]
    for project in demux.newProjectNameList:                                        # this loop is a check against project names which are not suppossed to be eventually tarred

        if any( var in project for var in [ demux.qcSuffix ] ):                     # skip anything that includes '_QC'
            demuxLogger.warning( f"{demux.qcSuffix} directory found in projects. Skipping." )
            continue
        elif any( var in project for var in [ demux.testProject ] ):                # skip the test project, 'FOO-blahblah-BAR'
            demuxLogger.warning( f"{demux.testProject} test project directory found in projects. Skipping." )
            continue
        elif any( var in project for var in demux.controlProjects ):                # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        elif demux.temp in project:                                                 # disregard the temp directory
            demuxLogger.warning( f"{demux.temp} directory found. Skipping." )
            continue
        elif demux.demultiplexLogDirPath in project: # disregard demultiplex_log
            demuxLogger.warning( f"{demux.demultiplexLogDirPath} directory found. Skipping." )
            continue

        if any( tag in project for tags in [ demux.nextSeq, demux.miSeq ] for tag in tags ):         # Make sure there is a nextseq or misqeq tag, before adding the directory to the projectsToProcessList
            projectsToProcessList.append( project )
            demuxLogger.debug( f"{project:{demux.spacing2}} added to projectsToProcessList." )

#---------- change the current working directory to demux.demultiplexRunIdDir, so we can get nice relative paths  ----------------------

    os.chdir( demux.demultiplexRunIdDir )

#---------- Use projectsToProcessList to tar files demux.demultiplexRunIdDir to demux.forTransferRunIdDir  ----------------------

    # this mean that while we are sitting in data.demultiplexRunIdDir, we are saving tar files under demux.forTransferRunIdDir
    counter = 0         # used in counting how many projects we have archived so far
    for project in projectsToProcessList:

        demuxLogger.debug( termcolor.colored( f"\n== walk the file tree, {inspect.stack()[0][3]}() , {demux.demultiplexRunIdDir}/{project} ======================", attrs=["bold"] ) )

        tarFile    = os.path.join(  demux.forTransferRunIdDir, project + demux.tarSuffix )

        if not os.path.isfile( tarFile ):                                   # Using absolute path to open the tar file
            tarFileHandle = tarfile.open( name = tarFile, mode = "w:" )     # Open a tar file under  demux.forTransferRunIdDir as project + demux.tarSuffix . example: /data/for_transfer/220603_M06578_0105_000000000-KB7MY/220603_M06578.42015-NORM-VET.tar
        else:
            text = f"{tarFile} exists. Please investigate or delete. Exiting."
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

#---------- Iterrate through demux.demultiplexRunIdDir/projectsToProcessList and make a single tar file for each project under data.forTransferRunIdDir   ----------------------

        counter = counter + 1
        demuxLogger.info( termcolor.colored( f"==> Archiving {project} ( {counter} out of { len( projectsToProcessList ) } projects ) ==================", color="yellow", attrs=["bold"] ) )
        text = "tarFile:"
        demuxLogger.debug( f"{text:{demux.spacing2}}" + os.path.join( demux.forTransferRunIdDir, tarFile ) )  # print the absolute path
        for directoryRoot, dirnames, filenames, in os.walk( project, followlinks = False ): 
             for file in filenames:
                # add one file at a time so we can give visual feedback to the user that the script is processing files
                # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
                # of output that make users uncomfortable
                filenameToTar = os.path.join( project, file )
                tarFileHandle.add( name = filenameToTar, recursive = False )
                text = "filenameToTar:"
                text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
                demuxLogger.info( text + filenameToTar )

        tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on

        demuxLogger.info( termcolor.colored( f'==< Archived {project} ({counter} out of { len( projectsToProcessList ) } projects ) ==================\n', color="yellow", attrs=["bold"] ) )

#---------- Finished taring   -----------------------------------------------------------------------------------------------------------------------------------------------------

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Adding files to tape archives finished ==", color="cyan" ) )



########################################################################
# createQcTarFile
########################################################################

def createQcTarFile( ):
    """
    create the qc.tar file by reading from /data/demultiplex/RunID/RunID_QC and writing the tar file to /data/for_transfer/RunID/demux.RunIDShort_qc.tar
    What to put inside the QC file: {demux.RunIDShort}_QC and multiqc_data

    """

    demuxLogger.info( termcolor.colored( f"==> Archiving {demux.demuxQCDirectoryFullPath} =================", color="yellow", attrs=["bold"] ) )

    if demux.verbosity == 2:
        text = "demuxQCDirectoryFullPath:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + demux.demuxQCDirectoryFullPath )
        text = "multiqc_data:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + demux.multiqc_data )

    if not os.path.isfile( demux.forTransferQCtarFile ): # exit if /data/for_transfer/RunID/qc.tar file exists.
        tarQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "w:" )
    else:
        text = f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    # paths are relative here, cuz we chdir( ) in tarProjectFiles( )
    for directoryRoot, dirnames, filenames, in os.walk( demux.demuxQCDirectoryName , followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the Archivinguser that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( demux.demuxQCDirectoryName, file ) # demux.demuxQCDirectoryName is relative, for example '220603_M06578_QC'
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            text = "filenameToTar:"
            text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
            demuxLogger.info( text + filenameToTar )

    tarQCFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on

    demuxLogger.info( termcolor.colored( f"==> Archived {demux.demuxQCDirectoryFullPath} ==================", color="yellow", attrs=["bold"] ) )




########################################################################
# createMultiQcTarFile
########################################################################

def createMultiQcTarFile( ):
    """
    Add the multiqc_data to the qc.tar under /data/for_transfer/RunID
    """
    demuxLogger.info( termcolor.colored( f"==> Archiving {demux.multiqc_data} ==================", color="yellow", attrs=["bold"] ) )

    if os.path.isfile( demux.forTransferQCtarFile ): # /data/for_transfer/RunID/qc.tar must exist before writi
        multiQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "a:" ) # "a:" for exclusive, uncompresed append.
    else:
        text = f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    # paths are relative here, cuz we chdir( ) in tarProjectFiles( )
    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.multiqc_data ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the user that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( demux.multiqc_data, file )
            multiQCFileHandle.add( name = filenameToTar, recursive = False )
            text = "filenameToTar"
            text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
            demuxLogger.info( text + filenameToTar )

    # bothisfiledemux.RunIDShort}_QC and multidata_qc go in the same tar file
    multiQCFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
    demuxLogger.info( termcolor.colored( f"==> Archived {demux.multiqc_data} ==================", color="yellow", attrs=["bold"] ) )    



########################################################################
# prepareDelivery
########################################################################

def prepareDelivery( ):
    """
    Prepare the appropriate tar files for transfer and write the appropirate .md5/.sha512 checksum files

    Preparing has the following steps:
        tar the entire DemultiplexRunIdDir
        tar the QC directory
        make the DemultiplexRunIdDir/temp directory
        copy all tar/md5/sha512 files into DemultiplexRunIdDir/temp
        md5/sha512 the DemultiplexRunIdDir tar file
        md5/sha512 the QC tar file
        make the /data/for_delivery/RunID directory
        copy the resulting Demux and QC tar files along with the associated .md5/.sha512 files to /data/for_transfer/RunID
        run clean up
            delete the DemultiplexRunIdDir/temp directory

    WHAT TO PUT INSIDE THE QC FILE
        {demux.RunIDShort}_QC/
        multiqc_data/

    WHAT TO IGNORE
        From time to time, if the library to be sequenced has extra space, the lab includes a control sample
        We are going to ignore them for the purpose of tarring and delivery and run QC separate.
        The name of the projects are stored in demux.ControlProjects
            would be a good idea to pull the control projects right out of irida or clarity.

    TRICK IN THIS FUNCTION:
        os.mkdir( forTransferRunIdDir )
        move all the tar files in there
            one directory per project
        calcFileHash( forTransferRunIdDir ) # use a temp dir to re-use the same function we used earlier, so I will not have to write a new function to do the same thing

    Original commands:
        EXAMPLE: /bin/tar -cvf tar_file -C DemultiplexDir folder 
        EXAMPLE: /bin/md5sum tar_file | sed_command > md5_file

    First, exclude:
        qcSuffix project
        test projects used by this software
        control projects inserted by the lab periodically
        demultiplex_log directory that stores all the logs for the run

    For the projects left, 
        create the directory projects under /data/for_transfer/RunID/{project_name}
        create the tar file
            by recursing down the /data/RunID_demultiplex
    
    Finally
        crete the _QC tar file

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for delivery started ==", color="green", attrs=["bold"] ) )


    if not os.path.isdir( demux.forTransferRunIdDir ): # we save each tar file into its own directory
        text = f"Error: {demux.forTransferRunIdDir} does not exist. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    # individual project directories are created in tarProjectFiles( )
    tarProjectFiles( )
    createQcTarFile( )
    createMultiQcTarFile( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for delivery finished ==", color="red", attrs=["bold"] ) )





########################################################################
# Water Control Negative report
########################################################################

def controlProjectsQC(  ):
    """
    This function creeates a report if any water 1 samples are submitted for sequence ( and subsequently, analysis )

    If there are no water control samples, no report is generated.

    If there are water control samples,
        create the full report ONLY if any amplicons are found
    Otherwise
        just mention in green text that no results are detected (and move on)
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Control Project QC for non-standard proejcts started ==", color="green", attrs=["bold"] ) )

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Control Project QC for non-standard proejcts finished ==", color="red", attrs=["bold"] ) )




########################################################################
# Perform a sha512 comparision
########################################################################

def sha512FileQualityCheck(  ):
    """
    re-perform (quietly) the sha512 calculation and compare that with the result on file for the specific file.
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: sha512 files check started ==", color="green", attrs=["bold"] ) )

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: sha512 files check finished ==", color="red", attrs=["bold"] ) )





########################################################################
# tarFileQualityCheck: verify tar files before upload
########################################################################

def tarFileQualityCheck(  ):
    """
    Perform a final quality check on the tar files before uploading them.
    If there are errors in the untarring or the sha512 check, halt.
    If there are no errors, go ahead with the uploading


    steps for completing this function:
        Step 1: create a /data/for_transfer/RunID/test directory
        Step 2: copy any tar file for relevant RunIDShort into the test directory
        Step 3: untar files under /data/for_transfer/RunID/test
        Step 4: recalculate sha512 hash for each file
        compare result with hash file on disk
            stuff result in sql database?
        delete {demux.forTransferRunIdDir}/{demux.forTransferRunIdDirTestName} and contents
        return True/false depending on answer

    INPUT
        Input is RunID rather than demux.RunID or some other variable because we can use this method later to check the tarFile quality of any fetched tar file from archive
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Tar files quaility check started ==", color="green", attrs=["bold"] ) )

    forTransferRunIdDirTestName = os.path.join( demux.forTransferRunIdDir,demux.forTransferRunIdDirTestName )

#---- Step 1: create a /data/for_transfer/RunID/test directory -------------------------------------------------------------------------------------------

    # ensure that demux.forTransferDir (/data/for_transfer) exists
    if not os. path. isdir( demux.forTransferDir ):
        text = f"{demux.forTransferDir} does not exist! Please re-run the ansible playbook! Exiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )    

    try: 
        os.mkdir( forTransferRunIdDirTestName )
    except Exception as err:
        text = f"{demux.forTransferRunIdDir} cannot be created: { str( err ) }\nExiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

# there is no point in making this complicated: tar files can be easily edited, they are just a simple container and any attacker can easily alter the file insitu,
# recalculate the hash and replace the hash again in situ
#
# So the only thing we can do is basically untar the file to ensure that it was packed correctly in this program,
# then delete the test_tar directory

# for file in $TARFILES; do printf '\n==== tar file: $file============================='; tar --verbose --compare --file=$file | grep -v 'Mod time differs'; done
#---- Step 2: untar all demux.tarFilesToTransferList in {demux.forTransferRunIdDir}/{demux.forTransferRunIdDirTestName} ------------------------------------------------------------
    for tarFile in demux.tarFilesToTransferList:
        try:
            text = "Now extracting tarfile:"
            demuxLogger.debug( f"{text:{demux.spacing3}}" + tarFile )
            tarFileHandle = tarfile.open( name = tarFile, mode = "r:" )     # Open a tar file under  demux.forTransferRunIdDir as project + demux.tarSuffix . example: /data/for_transfer/220603_M06578_0105_000000000-KB7MY/220603_M06578.42015-NORM-VET.tar
            tarFileHandle.extractall( path = forTransferRunIdDirTestName  )
            tarFileHandle.close( )
        except Exception as err:
            text = f"{forTransferRunIdDirTestName}/{tarFile} cannot be created: { str( err ) }\nExiting!"
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

#---- Step 3: delete {demux.forTransferRunIdDir}/{demux.forTransferRunIdDirTestName} and contents ------------------------------------------------------------
    # clean up
    text = "Cleanup up path:"
    demuxLogger.info( f"{text:{demux.spacing2}}" + forTransferRunIdDirTestName )
    shutil.rmtree( forTransferRunIdDirTestName )


    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Tar files quaility check finished ==", color="red", attrs=["bold"] ) )





########################################################################
# script_completion_file
########################################################################

def scriptComplete(  ):
    """
    Create the {DemultiplexDir}/{demux.DemultiplexCompleteFile} file to signal that this script has finished
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Finishing up script ==", color="green", attrs=["bold"] ) )

    try:
        file = os.path.join( demux.demultiplexRunIdDir, demux.demultiplexCompleteFile )
        pathlib.Path( file ).touch( mode=644, exist_ok=False)
    except Exception as e:  
        demuxLogger.critical( f"{file} already exists. Please delete it before running {__file__}.\n")
        sys.exit( )

    demuxLogger.debug( f"demux.demultiplexCompleteFile {file} created.")
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Finishing up script ==", color="red", attrs=["bold"] ) )



########################################################################
# deliverFilesToVIGASP
########################################################################

def deliverFilesToVIGASP(  ):
    """
    Write the uploader file needed to upload the data to VIGASP and then
        upload the relevant files.
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for uploading to VIGASP finished\n")




########################################################################
# deliverFilesToNIRD
########################################################################

def deliverFilesToNIRD(  ):
    """
    Make connection to NIRD and upload the data
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for archiving to NIRD finished\n")



########################################################################
# detectNewRuns
########################################################################

def detectNewRuns(  ):
    """
    Detect if a new run has been uploaded to /data/rawdata
    """

#########
# TODO TODO TODO
#
#   new feature: logging.info out all the new runs detected
#       mention which one is being processed
#       mention which one are remaining
#########
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Detecting if new runs exist started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Detecting if new runs exist finished\n")


#######################################################################
# checkRunningDirectoryStructure( )
########################################################################

def checkRunningDirectoryStructure( ):
    """
    Check if the runtime directory structure is ready for processing
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Check if the runtime directory structure is ready for processing ==\n", color="green", attrs=["bold"] ) )

    # init:

    #   check if sequencing run has completed, exit if not
    #       Completion of sequencing run is signaled by the existance of the file {demux.rtaCompleteFilePath} ( {demux.sequenceRunOriginDir}/{demux.rtaCompleteFile} )
    if not os.path.isfile( f"{demux.rtaCompleteFilePath}" ):
        text = f"{demux.RunID} is not finished sequencing yet!"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    #   check if {demux.demultiplexDirRoot} exists
    #       exit if not
    if not os.path.exists( demux.demultiplexDirRoot ):
        text = f"{demux.demultiplexDirRoot} is not present, please use the provided ansible file to create the root directory hierarchy"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    if not os.path.isdir( demux.demultiplexDirRoot ):
        text = f"{demux.demultiplexDirRoot} is not a directory! Cannot stored demultiplex data in a non-directory structure! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )
    if os.path.exists( demux.demultiplexDirRoot ):
        text = f"{demux.demultiplexRunIdDir} exists. Delete the demultiplex folder before re-running the script"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Check if the runtime directory structure is ready for processing ==\n", color="red" ) )



########################################################################
# MAIN
########################################################################

def main( RunID ):
    """
    Main function for the demultiplex script.
    All actions are coordinated through here
    """

    RunID = RunID.rstrip('/,.')                                                                         # Be forgiving any ',' '/' or '.' during copy-paste

    setup_event_and_log_handling( )                                                                     # setup the event and log handing, which we will use everywhere, sans file logging 
    setup_environment( RunID )                                                                          # set up variables needed in the running setupEnvironment # demux.RunID is set here
    # # displayNewRuns( )                                                                                 # show all the new runs that need demultiplexing
    # create_demultiplex_directory_structure( demux )                                                     # create the directory structure under {demux.demultiplexRunIdDir}
    # #####################################################################################################
    # # create_demultiplex_directory_structure( ) needs to be called before we start logging to file:
    # #   Cannot create a log *file* without having a specific *directory* structure, can we? 
    # #####################################################################################################s
    # setup_file_log_handling( demux )                                                                    # setup the file event and log handing, which we left out
    # print_running_environment( demux )                                                                  # print our running environment
    # check_running_environment( demux )                                                                  # check our running environment
    # copy_sample_sheet_into_demultiplex_runiddir( demux )                                                # copy SampleSheet.csv from {demux.sampleSheetFilePath} to {demux.demultiplexRunIdDir}
    # archive_sample_sheet( demux )                                                                       # make a copy of the Sample Sheet for future reference
    # bcl2fastq( demux )                                                                                  # use blc2fastq to convert .bcl files to fastq.gz
    # rename_files_and_directories( demux )                                                               # rename the *.fastq.gz files and the directory project to comply to the {RunIDShort}.{project} convention
    # quality_check( demux )                                                                              # execute QC on the incoming fastq files
    calc_file_hash( demux, "demultiplexRunIDdir" )                                                      # create .md5/.sha512 checksum files for every .fastqc.gz/.tar/.zip file under demultiplexRunIdDir
    change_permissions( demux, "demultiplexRunIDdir" )                                                  # change permissions for the files about to be included in the tar files 
    prepareForTransferDirectoryStructure( demux )                                                       # create /data/for_transfer/RunID and any required subdirectories
    prepareDelivery( )                                                                                  # prepare the delivery files
    calc_file_hash( demux, "forTransferRunIdDir" )                                                      # create .md5/.sha512 checksum files for the delivery .fastqc.gz/.tar/.zip files under demultiplexRunIdDir, but this 2nd fime do it for the new .tar files created by prepareDelivery( )
    change_permissions( demux, "forTransferRunIDdir" )                                                  # change permissions for all the delivery files, including QC
    controlProjectsQC( )                                                                                # check to see if we need to create the report for any control projects present
    tarFileQualityCheck( )                                                                              # QC for tarfiles: can we untar them? does untarring them keep match the sha512 written? have they been tampered with while in storage?
    deliverFilesToVIGASP( )                                                                             # Deliver the output files to VIGASP
    deliverFilesToNIRD( )                                                                               # deliver the output files to NIRD
    scriptComplete( )                                                                                   # mark the script as complete
    # shutdownEventAndLoggingHandling( )                                                                # shutdown logging before exiting.

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
