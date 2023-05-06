#!/bin/env /bin/python3.11

import argparse
import ast
import pdb
import glob
import hashlib
import inspect
import logging
import logging.handlers
import os
import pathlib
import re
import shutil
import socket
import stat
import string
import subprocess
import sys
import syslog
import tarfile
import termcolor

from inspect import currentframe, getframeinfo


"""
demux module:
    A "pythonized" Obj-Oriented approach to demultiplexing Illumina bcl files and prepearing them for delivery to the individual NVI systems for subprocessing

    Module can run on its own, without needing to include in a library as such:

    /usr/bin/python3     /data/bin/demultiplex_script.py  200306_M06578_0015_000000000-CWLBG

    python interpreter | path to script                 | RunID directory from /data/rawdata

INPUTS
    - RunID directory from /data/rawdata

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
    To be discussed


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


class demux:
    """
    demux: make an object of the entire demultiplex process.
    """

    ######################################################
    debug     = True
    verbosity = 2
    ######################################################
    dataRootDirPath                 = '/data'
    rawDataDirName                  = 'rawdata'
    rawDataDir                      =  os.path.join( dataRootDirPath, rawDataDirName )
    demultiplexDirName              = "demultiplex"
    demultiplexDir                  = os.path.join( dataRootDirPath, demultiplexDirName )
    forTransferDirName              = 'for_transfer'
    forTransferDir                  = os.path.join( dataRootDirPath, forTransferDirName )
    sampleSheetDirName              = 'samplesheets'
    sampleSheetDirPath              = os.path.join( dataRootDirPath, sampleSheetDirName )
    logDirName                      = "log"
    logDirPath                      = os.path.join( dataRootDirPath, logDirName )
    ######################################################
    compressedFastqSuffix           = '.fastq.gz' 
    csvSuffix                       = '.csv'
    demultiplexDirSuffix            = '_demultiplex'
    multiqc_data                    = 'multiqc_data'
    md5Suffix                       = '.md5'
    qcSuffix                        = '_QC'
    sha512Suffix                    = '.sha512'
    tarSuffix                       = '.tar'
    temp                            = 'temp'
    zipSuffix                       = '.zip'
    htmlSuffix                      = '.html'
    logSuffix                       = '.log'
    ######################################################
    bcl2fastq_bin                   = f"{dataRootDirPath}/bin/bcl2fastq"
    fastqc_bin                      = f"{dataRootDirPath}/bin/fastqc"
    mutliqc_bin                     = f"{dataRootDirPath}/bin/multiqc"
    python3_bin                     = f"/usr/bin/python3"
    scriptFilePath                  = __file__
    ######################################################
    rtaCompleteFile                 = 'RTAComplete.txt'
    sampleSheetFileName             = 'SampleSheet.csv'
    testProject                     = 'FOO-blahblah-BAR'
    Sample_Project                  = 'Sample_Project'
    demultiplexCompleteFile         = 'DemultiplexComplete.txt'
    vannControlNegativReport        = 'Negativ'
    forTransferRunIdDirTestName     = 'test_tar'
    md5File                         = 'md5sum.txt'
    miSeq                           = 'M06578'   # if we get more than one, turn this into an array, or read from config, or read from illumina
    nextSeq                         = 'NB552450' # if we get more than one, turn this into an array, or read from config, or read from illumina
    decodeScheme                    = "utf-8"
    footarfile                      = f"foo{tarSuffix}"      # class variable shared by all instances
    barzipfile                      = f"zip{zipSuffix}"
    totalTasks                      = 0
    tabSpace                        = 8 
    spacing1                        = 40
    spacing2                        = spacing1 + tabSpace
    spacing3                        = spacing2 + tabSpace
    spacing4                        = spacing3 + tabSpace
    spacing5                        = spacing4 + tabSpace
    spacing6                        = spacing5 + tabSpace
    spacing6                        = spacing6 + tabSpace

    ######################################################
    RunID                           = ""
    runIDShort                      = ""
    rawDataRunIDdir                 = ""
    demultiplexRunIDdir             = ""
    demultiplexLogDirPath           = ""
    demultiplexScriptLogFilePath    = ""
    demuxQCDirectoryName            = ""
    demuxQCDirectoryPath            = ""
    forTransferRunIDdir             = ""
    forTransferQCtarFile            = ""
    sampleSheetFilePath             = os.path.join( sampleSheetDirPath, sampleSheetFileName )
    sampleSheetArchiveFilePath      = ""
    ######################################################
    projectList                     = [ ]
    newProjectNameList              = [ ]
    newProjectFileList              = [ ]
    tarFileStack                    = [ ]
    globalDictionary                = dict( )
    ######################################################
    controlProjects                 = [ "Negativ" ]
    ######################################################
    forTransferRunIdDir             = ""
    forTransferQCtarFile            = ""
    ######################################################
    demuxCumulativeLogFileName      = 'demultiplex.log'
    demultiplexLogDirName           = 'demultiplex_log'
    scriptRunLogFileName            = '00_script.log'
    bcl2FastqLogFileName            = '01_demultiplex.log'
    fastqcLogFileName               = '02_fastqcLogFile.log'
    multiqcLogFileName              = '03_multiqcLogFile.log'
    loggingLevel                    = logging.DEBUG
    ######################################################
    demuxCumulativeLogFilePath      = ""
    bcl2FastqLogFile                = ""
    fastQCLogFilePath               = ""
    logFilePath                     = ""
    multiQCLogFilePath              = ""
    scriptRunLogFile                = ""
    forTransferDirRoot              = ""
    ######################################################
    # mailhost                        = 'seqtech00.vetinst.no'
    mailhost                        = 'localhost'
    fromAddress                     = f"demultiplex@{ socket.getfqdn( ) }"
    toAddress                       = 'gmarselis@localhost'
    subjectFailure                  = 'Demultiplexing has failed'
    subjectSuccess                  = 'Demultiplexing has finished successfuly'
    ######################################################
    httpsHandlerHost                = 'veterinaerinstituttet307.workplace.com'
    httpsHandlerUrl                 = 'https://veterinaerinstituttet307.workplace.com/chat/t/4997584600311554'
    ######################################################
    threadsToUse                    = 12                        # the amount of threads FastQC and other programs can utilize
    ######################################################
    with open( __file__ ) as f:     # little trick from openstack: read the current script and count the functions and initialize totalTasks to it
        tree = ast.parse( f.read( ) )
        totalTasks = sum( isinstance( exp, ast.FunctionDef ) for exp in tree.body ) + 2 # + 2 adjust as needed
    n = 0 # counter for keeping track of the number of the current task



    def __init__( self, RunID ):
        """
        __init__
            Check for existance of RunID
                Complain if not
            Checks to see if debug or not is set
        """
        self.RunID = RunID # variables in __init___ are unique to each instance
        self.debug = True


    ########################################################################
    # getProjectName
    ########################################################################
    def getProjectName( ):
        """
        Get the associated project name from SampleSheet.csv

        Requires:
           /data/rawdata/RunID/SampleSheet.csv

        Returns:
            List of included Sample Projects. 
                Example of returned projectList:     {'SAV-amplicon-MJH'}

        Parsing is simple:
            go line-by-line
            ignore all the we do not need until
                we hit the line that contains 'Sample_Project'
                if 'Sample_Project' found
                    split the line and 
                        save the value of 'Sample_Project'
            return an set of the values of all values of 'Sample_Project' and 'Analysis'

        # DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'
        """

        demux.n = demux.n + 1
        if 'demuxLogger' in logging.Logger.manager.loggerDict.keys():
            demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} started ==\n", color="green", attrs=["bold"] ) )
        else:
            print( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} started ==\n", color="green", attrs=["bold"] ) )

        projectLineCheck    = False
        projectIndex        = 0
        projectList         = [ ]
        sampleSheetContents = [ ]
        newProjectNameList  = [ ]
        loggerName          = 'demuxLogger'

        sampleSheetFileHandle = open( demux.sampleSheetFilePath, 'r', encoding= demux.decodeScheme )
        sampleSheetContent    = sampleSheetFileHandle.read( )     # read the contents of the SampleSheet here

        if demux.verbosity == 2:
            if loggerName in logging.Logger.manager.loggerDict.keys():
                demuxLogger.debug( f"sampleSheetContent:\n{sampleSheetContent }" ) # logging.debug it
            else:
                print( f"sampleSheetContent:\n{sampleSheetContent }" )

        sampleSheetContents   = sampleSheetContent.split( '\n' )  # then split it in lines


        for line in sampleSheetContents:

            if demux.verbosity == 2:
                text = f"procesing line '{line}'"
                if loggerName in logging.Logger.manager.loggerDict.keys():
                    demuxLogger.debug( text )
                else:
                    print( text )

            if len( line ): # line != '' is not the same as 'not line'
                line = line.rstrip()
                if demux.verbosity == 2:
                    text = f"projectIndex: {projectIndex}" 
                    if loggerName in logging.Logger.manager.loggerDict.keys():
                        demuxLogger.debug( text )
                    else:
                        print( text )
                item = line.split(',')[projectIndex]
            else:
                continue

            if projectLineCheck == True and item not in projectList:
                if demux.verbosity == 2:
                    text = f"{'item:':{demux.spacing1}}{item}"
                    if loggerName in logging.Logger.manager.loggerDict.keys():
                        demuxLogger.debug( text )
                    else:
                        print( text )
                projectList.append( item )                                 # + '.' + line.split(',')[analysis_index]) # this is the part where .x shows up. Removed.
                newProjectNameList.append( f"{demux.RunIDShort}.{item}" )  #  since we are here, we might construct the new name list.

            elif demux.Sample_Project in line: ### DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'

                projectIndex     = line.split(',').index( demux.Sample_Project ) # DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'
                if demux.verbosity == 2:
                    text = f"{'projectIndex:':{demux.spacing1}}{projectIndex}"
                    if loggerName in logging.Logger.manager.loggerDict.keys():
                        demuxLogger.debug( text )
                    else:
                        print( text )

                projectLineCheck = True
            else:
                continue

        # Let's make sure that projectList and newProjectNameList are not empty
        if len( projectList ) == 0:
            text = f"line {getframeinfo( currentframe( ) ).lineno} projectList is empty! Exiting!"
            if loggerName in logging.Logger.manager.loggerDict.keys():
                demuxFailureLogger.critical( text  )
                demuxLogger.critical( text )
                logging.shutdown( )
            else:
                print( text )
            sys.exit( )
        elif len( newProjectNameList ) == 0:
            text = f"line {getframeinfo( currentframe( ) ).lineno}: newProjectNameList is empty! Exiting!"
            if loggerName in logging.Logger.manager.loggerDict.keys():
                demuxFailureLogger.critical( text  )
                demuxLogger.critical( text )
                logging.shutdown( )
            else:
                print( text )
            sys.exit( )
        else:
            text1 = f"projectList:"
            text1 = f"{text1:{demux.spacing2}}{projectList}"
            text2 = f"newProjectNameList:"
            text2 = f"{text2:{demux.spacing2}}{newProjectNameList}\n"
            demuxLogger.debug( text1 )
            demuxLogger.debug( text2 )

        demux.projectList        = projectList          # no need to return anything, save everything in the object space
        demux.newProjectNameList = newProjectNameList

        signOutText = termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} finished ==\n", color="red", attrs=["bold"] )
        if loggerName in logging.Logger.manager.loggerDict.keys():
            demuxLogger.info( signOutText )
        else:
            print( signOutText )




    ########################################################################
    # listTarFiles( )
    ########################################################################
    def listTarFiles ( listOfTarFilesToCheck ):
        """
        Check to see if the tar files created for delivery can be listed with no errors
        use
            TarFile.list(verbose=True, *, members=None)
                    Print a table of contents to sys.stdout. If verbose is False, only the names of the members are logging.infoed. If it is True, output similar to that of ls -l is produced. If optional members is given, it must be a subset of the list returned by getmembers(). 

            https://docs.python.org/3/library/tarfile.html

        But do it quietly, no need for output other than an OK/FAIL
        """

        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Verify that the tar files produced are actually untarrable started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Verify that the tar files produced are actually untarrable finished ==\n", color="red", attrs=["bold"] ) )



    ########################################################################
    # hasBeenDemultiplexed( )
    ########################################################################
    def hasBeenDemultiplexed( RunID ):
        """
        Check if run has been demultiplexed before

        Steps:
            Check if SampleSheet has been changed
                point out which fields have been changed
                    write to log

        Returs
            *True* if RudID_demultiplex exists
        """
        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed finished ==\n", color="red", attrs=["bold"] ) )



    ########################################################################
    # reDemultiplex( )
    ########################################################################
    def reDemultiplex( RunID ):
        """
        setup nessecary paths:
            RunID_demupltiplex-ISODATETIME
        Copy modified samplesheet to /data/SampleSheets as RunID-ISODATETIME.csv
        Demultiplex RunID again
        """
        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed finished ==\n", color="red", attrs=["bold"] ) )



    ########################################################################
    # checkSampleSheetForMistakes( )
    ########################################################################
    def checkSampleSheetForMistakes( RunID ):
        """
        Check SampleSheet.csv for common human mistakes

        common errors of SampleSheets
            1.       Space in sample name or project name. Especially hard to grasp if they occur at the end of the name. I replace the spaces with a “-“ if in middle of name. I erase the space if it is at the end.
            2.       Æ, Ø or Å in sample name or project names.
            3.       Extra lines in SampleSheet with no sample info in them. Will appear as a bunch of commas for each line which is empty. They need to be deleted or demuxing fails.
            4.       Forget to put ekstra column called “Analysis” and set an “x” in that column for all samples (I don’t know if we will keep this feature for the future)
            5.       . in sample names

        point any mistakes out to log
        """
        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Check SampleSheet.csv for common human mistakes started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Check SampleSheet.csv for common human mistakes finished ==\n", color="red", attrs=["bold"] ) )




########################################################################
# BufferingSMTPHandlerft3
########################################################################

class BufferingSMTPHandler( logging.handlers.BufferingHandler ):
    """
    Instead of immediatelly sending email for notifications, buffer the ouput and send it at the end.
    That way, you send one email instead of a multitude.
    """
    def __init__( self, mailhost, fromaddr, toaddrs, subject ):
        logging.handlers.BufferingHandler.__init__( self, capacity = 9999999 )
        self.mailhost = mailhost
        self.mailport = None
        self.fromaddr = fromaddr
        self.toaddrs = toaddrs
        self.subject = subject
        self.setFormatter( logging.Formatter( "%(asctime)s %(dns)s %(filename)s %(levelname)s %(message)s", datefmt = '%Y-%m-%d %H:%M:%S', defaults = { "dns": socket.gethostname( ) } ) )

    def flush(self):
        if len(self.buffer) > 0:
            import smtplib
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP( self.mailhost, port )
            msg = f"From: {self.fromaddr}\r\nTo: {self.toaddrs}\r\nSubject: {self.subject}\r\n\r\n"
            for record in self.buffer:
                s = self.format( record )
                print( s )
                msg = msg + s + '\r\n'
            msg = msg + '\r\n\r\n'
            smtp.sendmail( self.fromaddr, self.toaddrs, msg )
            smtp.quit( )
            self.buffer = []



########################################################################
# createDirectory
########################################################################

def createDemultiplexDirectoryStructure(  ):
    """
    If the Demultiplexing directory or any relevant directory does not exist, create it
        demux.RunIDShort format is in the pattern of (date +%y%m%d)_SEQUENCERSERIALNUMBER Example: 220314_M06578
        {demultiplexDirRoot} == "/data/demultiplex" # default

        {demultiplexDirRoot}/{demux.RunID}_{demultiplexDirSuffix}/
        {demultiplexDirRoot}/{demux.RunID}_{demultiplexDirSuffix}/projectList[0]
        {demultiplexDirRoot}/{demux.RunID}_{demultiplexDirSuffix}/projectList[1]
        .
        .
        .
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/projectList[ len( projectList ) -1 ]
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/{demultiplexLogDir}
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/{demux.RunIDShort}{demux.qcSuffix}
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/Reports      # created by bcl2fastq
        {demultiplexDirRoot}{demux.RunID}_{demultiplexDirSuffix}/Stats        # created by bcl2fastq
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Create directory structure started ==", color="green", attrs=["bold"] ) )

    demuxLogger.debug( f"demultiplexRunIdDir\t\t\t{demux.demultiplexRunIdDir}" )
    demuxLogger.debug( f"demultiplexRunIdDir/demultiplexLogDir:\t\t{demux.demultiplexLogDirPath}" )
    demuxLogger.debug( f"demultiplexRunIdDir/demuxQCDirectory:\t\t{demux.demuxQCDirectoryPath}" )

    try:
        os.mkdir( demux.demultiplexRunIdDir )   # root directory for run
        os.mkdir( demux.demultiplexLogDirPath ) # log directory  for run
        os.mkdir( demux.demuxQCDirectoryPath )  # QC directory   for run
    except FileExistsError as err:
        demuxFailureLogger.critical( f"File already exists! Exiting!\n{err}" )
        demuxLogger.critical( f"File already exists! Exiting!\n{err}" )
        logging.shutdown( )
        sys.exit( )
    except FileNotFoundError as err:
        demuxFailureLogger.critical( f"A component of the passed path is missing! Exiting!\n{err}" )
        demuxLogger.critical( f"A component of the passed path is missing! Exiting!\n{err}" )
        logging.shutdown( )
        sys.exit( )


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Create directory structure finished ==\n", color="red", attrs=["bold"] ) )




########################################################################
# demultiplex
########################################################################

def prepareForTransferDirectoryStructure( ):
    """
    create /data/for_transfer/RunID and any required subdirectories
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Create delivery directory structure under {demux.forTransferRunIdDir} started ==", color="green", attrs=["bold"] ) )


    # ensure that demux.forTransferDir (/data/for_transfer) exists
    if not os. path. isdir( demux.forTransferDir ):
        text = f"{demux.forTransferDir} does not exist! Please re-run the ansible playbook! Exiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )    

    try:
        os.mkdir( demux.forTransferRunIdDir )       # try to create the demux.forTransferRunIdDir directory ( /data/for_transfer/220603_M06578_0105_000000000-KB7MY )
    except e as err:
        text = f"{demux.forTransferRunIdDir} cannot be created: { str( err ) }\nExiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks:  Create delivery directory structure under {demux.forTransferRunIdDir} ==\n", color="red", attrs=["bold"] ) )



########################################################################
# demultiplex
########################################################################

def demultiplex( ):
    """
    Use Illumina's blc2fastq linux command-line tool to demultiplex each lane into an appropriate fastq file

    bcl2fastq is available here https://emea.support.illumina.com/sequencing/sequencing_software/bcl2fastq-conversion-software/downloads.html
        and you will have to have an account with Illumina to download it.
        Account is setup automatically, but needs manual approval from representative in Illumina, which means you need a contract with Illumina
        in order to access the software.

    CAREFUL: when trying to execute this array, please break all arguments that include a space into their own array element. Otherwise it will execute as '--runfolder-dir {SequenceRunOriginDir}'
         the space will be considered part of the argument: While you will scratch your head that you are passing argument and option, subprocess.run() will report that as a single
         argument with no options

        blc2fastq accepts just *fine* absolute paths when run from the command-line
        example: /data/bin/bcl2fastq --no-lane-splitting --runfolder-dir /data/rawdata/220314_M06578_0091_000000000-DFM6K --output-dir /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex

    CAREFUL: if you run blc2fastq with only --runfolder-dir {demux.RawDataRunIDdir} , bcl2fastq will create all the files within the {demux.RawDataRunIDdir} rawdata directory

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Demultiplexing started ==\n", color="green", attrs=["bold"] ) )

    argv = [ demux.bcl2fastq_bin,
         "--no-lane-splitting",
         "--runfolder-dir",
        f"{demux.rawDataRunIDdir}",
         "--output-dir",
        f"{demux.demultiplexRunIdDir}"
    ]

    text = f"Command to execute:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + " ".join( argv ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + demux.rawDataRunIDdir + ' --output-dir ' + demux.demultiplexDir + ' 2> ' + demux.demultiplexDir + '/demultiplex_log/02_demultiplex.log'
        result =  subprocess.run( argv, capture_output = True, cwd = demux.rawDataRunIDdir, check = True, encoding = demux.decodeScheme )
    except ChildProcessError as err: 
        text = [    f"Caught exception!",
                    f"Command: {err.cmd}", # interpolated strings
                    f"Return code: {err.returncode}"
                    f"Process output: {err.stdout}",
                    f"Process error:  {err.stderr}",
                    f"Exiting."
                 ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( text )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    if not result.stderr:
        demuxLogger.critical( f"result.stderr has zero lenth. exiting at {inspect.currentframe().f_code.co_name}()" )
        demuxFailureLogger.critical( f"result.stderr has zero lenth. exiting at {inspect.currentframe().f_code.co_name}()" )
        logging.shutdown( )
        sys.exit( )

    try: 
        file = open( demux.bcl2FastqLogFile, "w" )
        file.write( result.stderr )
        file.close( )
    except OSError as err:
        text = [    f"Caught exception!",
                    f"Command: {err.cmd}", # interpolated strings
                    f"Return code: {err.returncode}"
                    f"Process output: {err.stdout}",
                    f"Process error:  {err.stderr}",
                    f"Exiting."
                 ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( text )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )


    if not os.path.isfile( demux.bcl2FastqLogFile ):
        demuxFailureLogger.critical( f"{demux.bcl2FastqLogFile} did not get written to disk. Exiting." )
        demuxLogger.critical( f"{demux.bcl2FastqLogFile} did not get written to disk. Exiting." )
        logging.shutdown( )
        sys.exit( )
    else:
        filesize = os.path.getsize( demux.bcl2FastqLogFile )
        text = "bcl2FastqLogFile:"
        demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{demux.bcl2FastqLogFile} is {filesize} bytes.\n")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Demultiplexing finished ==\n", color="red", attrs=["bold"] ) )




########################################################################
# renameDirectories( )
########################################################################

def renameDirectories( ):
    """
        For each project directory in demux.projectList
            rename the project directory  to conform from the {demux.demultiplexRunIdDir}/{project} pattern to the {demux.demultiplexRunIdDir}/{demux.RunIDShort}.{project}

        Why you ask?
            That's how the original script does it (TRADITION!)

            One good reason is, of course to keep track of the file, if something goes wrong.
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Renaming project directories from project_name to RunIDShort.project_name ==\n", color="green", attrs=["bold"] ) )


    for project in demux.projectList: # rename the project directories

        oldname = os.path.join( demux.demultiplexRunIdDir, project )
        newname = os.path.join( demux.demultiplexRunIdDir, demux.RunIDShort + '.' + project )
        olddirExists = os.path.isdir( oldname )
        newdirExists = os.path.isdir( newname )

        # make sure oldname dir exists
        # make sure newname dir name does not exist
        if olddirExists and not newdirExists: # rename directory

            try: 
                os.rename( oldname, newname )
            except FileNotFoundError as err:
                text = [    f"Error during renaming {oldname}:", 
                            f"oldname: {oldname}",
                            f"oldfileExists: {oldfileExists}",
                            f"newfile: {newname}",
                            f"newfileExists: {newfileExists}",
                            f"err.filename:  {err.filename}",
                            f"err.filename2: {err.filename2}",
                            f"Exiting!"
                        ]
                text = '\n'.join( text )
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            demuxLogger.debug( f"Renaming " + termcolor.colored(  f"{oldname:92}", color="cyan", attrs=["reverse"] ) + " to " + termcolor.colored(  f"{newname:106}", color="yellow", attrs=["reverse"] ) )

    for index, item in enumerate( demux.newProjectFileList ):
        text = f"demux.newProjectFileList[{index}]:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + item) # make sure the debugging output is all lined up.

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Renaming project directories from project_name to RunIDShort.project_name ==\n", color="red", attrs=["bold"] ) )




def renameFiles( ):
    """
    Rename the files within each {project} to conform to the {RunIDShort}.{filename}.fastq.gz pattern

    Why? see above? it's always been done that way.
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Rename files ==\n", color="green" ) )

    oldname            = ""
    newname            = ""
    for project in demux.projectList: # rename files in each project directory

        if any( var in project for var in demux.controlProjects ):      # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        elif project == demux.testProject:                              # ignore the test project
            demuxLogger.debug( f"Test project '{demux.testProject}' detected. Skipping." )
            continue

        compressedFastQfilesDir = os.path.join( demux.demultiplexRunIdDir, project )
        # text1 = termcolor.colored( "Now working on project:", color="cyan", attrs=["reverse"] )
        text1 = "Now working on project:"
        text2 = "compressedFastQfilesDir:"
        demuxLogger.debug( termcolor.colored( f"{text1:{demux.spacing2 - 1}}", color="cyan", attrs=["reverse"] ) + " " + termcolor.colored( f"{project}", color="cyan", attrs=["reverse"] ) )
        demuxLogger.debug( f"{text2:{demux.spacing2}}{compressedFastQfilesDir}")

        filesToSearchFor     = os.path.join( compressedFastQfilesDir, '*' + demux.compressedFastqSuffix )
        compressedFastQfiles = glob.glob( filesToSearchFor )            # example: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/sample*fastq.gz

        if not len( compressedFastQfiles ): # if array is empty
            text = f"\n\nProject {project} does not contain any .fastq.gz entries"
            text = f"{text} | method {inspect.stack()[0][3]}() ]"
            text = f"{text}\n\n"

            demuxFailureLogger.critical( text )
            demuxLogger.critical( text )
            sys.exit( )

        text = "fastq files for '" + project + "':"
        demuxLogger.debug( f"{text:{demux.spacing2}}{filesToSearchFor}" )

        for index, item in enumerate( compressedFastQfiles ):
            text1 = "compressedFastQfiles[" + str(index) + "]:"
            demuxLogger.debug( f"{text1:{demux.spacing3}}{item}" )


        demuxLogger.debug( "-----------------")
        demuxLogger.debug( f"Move commands to execute:" )
        for file in compressedFastQfiles: # compressedFastQfiles is already in absolute path format
    
            # get the base filename. We picked up sample*.{CompressedFastqSuffix} and we have to rename it to {demux.RunIDShort}sample*.{CompressedFastqSuffix}
            baseFileName = os.path.basename( file )

            oldname     = file
            newname     = os.path.join( demux.demultiplexRunIdDir, project, demux.RunIDShort + baseFileName )
            renamedFile = os.path.join( demux.demultiplexRunIdDir, demux.RunIDShort + '.' + project, demux.RunIDShort + baseFileName ) # saving this var to use later when renaming directories

            if renamedFile not in demux.newProjectFileList:
                demux.newProjectFileList.append( renamedFile ) # demux.newProjectFileList is used in fastQC( )

            text  = f"/usr/bin/mv {oldname} {newname}"
            demuxLogger.debug( " "*demux.spacing1 + text )
            
            # make sure oldname files exist
            # make sure newname files do not exist
            oldfileExists = os.path.isfile( oldname )
            newfileExists = os.path.isfile( newname )

            if oldfileExists and not newfileExists:
                try: 
                    os.rename( oldname, newname )
                except FileNotFoundError as err:
                    text = [    f"Error during renaming {oldname}:",
                                f"oldname: {oldname}\noldfileExists: {oldfileExists}",
                                f"newname: {newname}\nnewfileExists: {newfileExists}",
                                f"err.filename:  {err.filename}",
                                f"err.filename2: {err.filename2}",
                                f"Exiting!"
                         ]
                    text = '\n'.join( text )
                    demuxFailureLogger.critical( f"{ text }" )
                    demuxLogger.critical( f"{ text }" )
                    logging.shutdown( )
                    sys.exit( )
        demuxLogger.debug( "-----------------")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIdDir} ==\n", color="red" ) )



########################################################################
# renameFilesAndDirectories( )
########################################################################

def renameFilesAndDirectories( ):
    """
    Rename any [sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ] files inside 
        {demux.demultiplexRunIdDir}/{demux.RunIDShort}/[ { projectList[0] }, .. , { projectList[n] } ] to match the pattern
        {demux.RunIDShort}.[sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ]
    
    Then rename the 
        {demux.demultiplexRunIdDir}/{demux.RunIDShort}/[ { projectList[0] }, .. , { projectList[n] } ] to match the pattern
        {demux.demultiplexRunIdDir}/{demux.RunIDShort}/{demux.RunIDShort}.[ {projectList[0] }, .. , { projectList[n] } ] to match the pattern
        
    Examples:
    
        demultiplexRunIdDir: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/
        Sample_Project:      SAV-amplicon-MJH              ### DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'
        demux.RunIDShort:    220314_M06578

        1. Rename the files:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R1_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R1_001.fastq.gz
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R2_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R2_001.fastq.gz

        2. Rename the base directory, for each project:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Renaming started ==", color="green", attrs=["bold"] ) )


    text = f"demultiplexRunIdDir:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.demultiplexRunIdDir )    # tabulation error
    text = f"RunIDShort:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.RunIDShort )
    if demux.verbosity == 2:
        text = "demux.projectList:"
        demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{demux.projectList}" )

    renameFiles( )
    renameDirectories( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Renaming finished ==", color="red", attrs=["bold"] ) )



########################################################################
# fastQC
########################################################################

def fastQC( ):
    """
    fastQC: Run /data/bin/fastqc (which is a symlink to the real qc)
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: fastQC started ==", color="yellow" ) )

    command             = demux.fastqc_bin
    argv                = [ command, '-t', str(demux.threadsToUse), *demux.newProjectFileList ]  # the * operator on a list/array "splats" (flattens) the values in the array, breaking them down to individual arguemtns

    arguments = " ".join( argv[1:] )
    text = "Command to execute:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{command} {arguments}")     # exclude the first element of the array # example for filename: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/

    try:
        # EXAMPLE: /usr/local/bin/fastqc -t 4 {demux.demultiplexRunIdDir}/{project}/*fastq.gz > demultiplexRunIdDir/demultiplex_log/04_fastqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demux.demultiplexRunIdDir, check = True, encoding = demux.decodeScheme )
    except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: {err.cmd}", # interpolated strings
                     f"Return code: {err.returncode}"
                     f"Process output: {err.output}",
                     f"Exiting."
                ]
            text = '\n'.join( text )
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

    # log FastQC output
    try: 
        fastQCLogFileHandle = open( demux.fastQCLogFilePath, "x" ) # fail if file exists
        if demux.verbosity == 2:
            text = f"fastQCLogFilePath:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.fastQCLogFilePath )
        fastQCLogFileHandle.write( result.stdout ) 
        fastQCLogFileHandle.close( )
    except FileNotFoundError as err:
        text = [    f"Error opening fastQCLogFilePath: {demux.fastQCLogFilePath} does not exist",
                    f"err.filename:  {err.filename}",
                    f"Exiting!"
                ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: FastQC complete ==\n", color="cyan" )  )



########################################################################
# prepareMultiQC
########################################################################

def prepareMultiQC( ):
    """
    Preperation to run MultiQC:
        copy *.zip and *.html from individual {demux.demultiplexRunIdDir}/{demux.RunIDShort}.{project} directories to the {demultiplexRunIdDirNewNamel}/{demux.RunIDShort}_QC directory
  
    INPUT
        the renamed project list
            does not include demux.TestProject
            deos nto include any demux.ControlProjects

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for MultiQC started ==", color="yellow" ) )

    zipFiles       = [ ]
    HTMLfiles      = [ ]
    sourcefiles    = [ ]
    countZipFiles  = 0
    countHTMLFiles = 0
    totalZipFiles  = 0
    totalHTMLFiles = 0

    demuxLogger.debug( "-----------------")

    for project in demux.newProjectNameList:

        if any( var in project for var in [ demux.testProject ] ):                # skip the test project, 'FOO-blahblah-BAR'
            demuxLogger.warning( termcolor.colored( f"{demux.testProject} test project directory found in projects. Skipping.", color="magenta" ) )
            continue
        elif any( var in project for var in demux.controlProjects ):                # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        else:
            zipFilesPath   = os.path.join( demux.demultiplexRunIdDir, project ,'*' + demux.zipSuffix  ) # {project} here is already in the {RunIDShort}.{project_name} format
            htmlFilesPath  = os.path.join( demux.demultiplexRunIdDir, project, '*' + demux.htmlSuffix ) # {project} here is already in the {RunIDShort}.{project_name} format
            globZipFiles   = glob.glob( zipFilesPath )
            globHTMLFiles  = glob.glob( htmlFilesPath )
            countZipFiles  = len( globZipFiles )
            countHTMLFiles = len( globHTMLFiles )
            totalZipFiles  = totalZipFiles + countZipFiles
            totalHTMLFiles = totalHTMLFiles + countHTMLFiles
        
        if not globZipFiles or not globHTMLFiles:
            demuxLogger.debug( f"globZipFiles or globHTMLFiles came back empty on project {project}" )
            text = "DemultiplexRunIdDir/project:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{demux.demultiplexRunIdDir}/{project}" )
            text = "globZipFiles:"
            demuxLogger.debug( f"{text:{demux.spacing3}}" + f"{ ' '.join( globZipFiles  ) }"         )
            text = "globHTMLFiles:"
            demuxLogger.debug( f"{text:{demux.spacing3}}" + f"{ ' '.join( globHTMLFiles ) }"         )
            continue
        else:
            zipFiles  = zipFiles  + globZipFiles  # source zip files
            HTMLfiles = HTMLfiles + globHTMLFiles # source html files

        text  = termcolor.colored( f"Now working on project:", color="cyan", attrs=["reverse"]      ) 
        demuxLogger.debug( f"{text:{demux.spacing3}}" + project                                     )
        if demux.verbosity == 2:
            text = "added"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( countZipFiles  ) + " zip files"  )
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( countHTMLFiles ) + " HTML files" )
            text = "totalZipFiles:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( totalZipFiles  )                )
            text = "totalHTMLFiles:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( totalHTMLFiles )                )
            text  = f"zipFiles:"
            # text1 = " ".join( zipFiles[ counter ] )
            text1 = " ".join( zipFiles )
            demuxLogger.debug( f"{text:{demux.spacing3}}" + text1                                   )
            text  = f"HTMLfiles:"
            # text1 = " ".join( HTMLfiles[ counter ] )
            text1 = " ".join( HTMLfiles )
            demuxLogger.debug( f"{text:{demux.spacing3}}" + text1                                   )
        demuxLogger.debug( "-----------------")


    if ( not zipFiles[0] or not HTMLfiles[0] ):
        demuxLogger.critical( f"zipFiles or HTMLfiles in {inspect.stack()[0][3]} came up empty! Please investigate {demux.demultiplexRunIdDir}. Exiting.")
        logging.shutdown( )
        sys.exit( )

    demuxLogger.debug( "-----------------")
    sourcefiles = zipFiles + HTMLfiles
    destination = os.path.join( demux.demultiplexRunIdDir, demux.RunIDShort + demux.qcSuffix )     # QC folder eg /data/demultiplex/220603_M06578_0105_000000000-KB7MY_demultiplex/220603_M06578_QC/
    if demux.verbosity == 2:
        text        = "sourcefiles:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + str( ' '.join( sourcefiles ) ) + '\n' )
    demuxLogger.debug( "-----------------")

    if len( sourcefiles ) != totalZipFiles + totalHTMLFiles:
        text =  f"len(sourcefiles) {len(sourcefiles)} not equal to totalZipFiles ({totalZipFiles}) plus totalHTMLFiles ({totalHTMLFiles}) == {totalZipFiles + totalHTMLFiles }"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    if not os.path.isdir( destination ) :
        text =  f"Directory {destination} does not exist. Please check the logs. You can also just delete {demux.demultiplexRunIdDir} and try again."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    try:
        # EXAMPLE: /usr/bin/cp project/*zip project/*html DemultiplexDir/demux.RunIDShort.short_QC # (destination is a directory)
        for source  in sourcefiles :
            text    = "Command to execute:"
            command = f"/usr/bin/cp {source} {destination}"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + command )
            shutil.copy2( source, destination )     # destination has to be a directory
    except FileNotFoundError as err:                # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
        text = [ f"\tFileNotFoundError in {inspect.stack()[0][3]}()" ,
                 f"\terrno:\t{err.errno}",
                 f"\tstrerror:\t{err.strerror}",
                 f"\tfilename:\t{err.filename}",
                 f"\tfilename2:\t{err.filename2}",
                 f"Exiting."
               ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for multiQC finished ==\n", color="cyan" ) )



########################################################################
# multiQC
########################################################################

def multiQC( ):
    """
    Run /data/bin/multiqc against the project list.

    Result are zip files in the individual project directories
    """ 

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: multiQC started ==", color="yellow" ) )

    command = demux.mutliqc_bin
    argv    = [ command, demux.demultiplexRunIdDir,
               '-o', demux.demultiplexRunIdDir 
              ]
    args    = " ".join(argv[1:]) # ignore the command part so we can logging.debug this string below, fresh all the time, in case we change tool command name

    text = "Command to execute:"
    demuxLogger.debug( f"{text:{demux.spacing2}}{command} {args}" )

    try:
        # EXAMPLE: /usr/local/bin/multiqc {demux.demultiplexRunIdDir} -o {demux.demultiplexRunIdDir} 2> {demux.demultiplexRunIdDir}/demultiplex_log/05_multiqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demux.demultiplexRunIdDir, check = True, encoding = demux.decodeScheme )
    except ChildProcessError as err: 
        text = [    f"Caught exception!",
                    f"Command:\t{err.cmd}", # interpolated strings
                    f"Return code:\t{err.returncode}"
                    f"Process output: {err.output}",
                    f"Exiting."
                ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    # log multiqc output
    demux.multiQCLogFilePath  = os.path.join( demux.demultiplexLogDirPath, demux.multiqcLogFileName ) ############# FIXME FIXME FIXME FIXME take out
    try: 
        multiQCLogFileHandle      = open( demux.multiQCLogFilePath, "x" ) # fail if file exists
        if demux.verbosity == 2:
            text = "multiQCLogFilePath"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.multiQCLogFilePath )
        multiQCLogFileHandle.write( result.stderr ) # The MultiQC people are special: They write output to stderr
        multiQCLogFileHandle.close( )
    except OSError as err:
        text = [    f"Caught exception!",
                    f"Command: {err.cmd}", # interpolated strings
                    f"Return code: {err.returncode}"
                    f"Process output: {err.stdout}",
                    f"Process error:  {err.stderr}",
                    f"Exiting."
                 ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( text )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )    


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: multiQC finished ==\n", color="cyan" ) )


########################################################################
# qualityCheck
########################################################################

def qualityCheck( ):
    """
    Run QC on the sequence run files

        FastQC takes the fastq.gz R1 and R2 of each sample sub-project and performs some Quality Checking on them
            The result of running FastQC is html and .zip files, one for each input fastq.gz file. The .zip file contails a directory with the complete analysis of the sample. The .html file is the entry point for all the stuff in the subdirectory

        MultiQC takes {EXPLAIN INPUT HERE}
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Quality Check started ==", color="green", attrs=["bold"] ) )

    fastQC( )
    prepareMultiQC( )
    multiQC( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Quality Check finished ==\n", color="red", attrs=["bold"] ) )




########################################################################
# calcFileHash
########################################################################

def calcFileHash( eitherRunIdDir ):
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
    for directoryRoot, dirnames, filenames, in os.walk( eitherRunIdDir, followlinks = False ):

        for file in filenames:
            if not any( var in file for var in [ demux.compressedFastqSuffix, demux.zipSuffix, demux.tarSuffix ] ): # grab only .zip, .fasta.gz and .tar files
                continue

            filepath = os.path.join( directoryRoot, file )

            if not os.path.isfile( filepath ):
                text = f"{filepath} is not a file. Exiting."
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            if os.path.getsize( filepath ) == 0 : # make sure it's not a zero length file 
                demuxLogger.warning( f"file {filepath} has zero length. Skipping." )
                continue
        
            filehandle     = open( filepath, 'rb' )
            filetobehashed = filehandle.read( )
            md5sum         = hashlib.md5( filetobehashed ).hexdigest( )
            sha512sum      = hashlib.sha256( filetobehashed ).hexdigest( )
            md5Length      = 16 # 128 bytes
            sha512Length   = 64 # 512 bytes
            demuxLogger.debug( f"md5sum: {md5sum:{md5Length}} | sha512sum: {sha512sum:{sha512Length}} | filepath: {filepath}" )


            if not os.path.isfile( f"{filepath}{demux.md5Suffix}" ):
                fh = open( f"{filepath}{demux.md5Suffix}", "w" )
                fh.write( f"{md5sum}\n" )
                fh.close( )
            else:
                demuxLogger.warning( f"{filepath}{demux.md5Suffix} exists, skipping" )
                continue
            if not os.path.isfile( f"{filepath}{demux.sha512Suffix}" ):
                try: 
                    fh = open( f"{filepath}{demux.sha512Suffix}", "w" )
                    fh.write( f"{sha512sum}\n" )
                    fh.close( )  
                except FileNotFoundError as err:
                    text = [    f"Error writing sha512 sum file {filepath}{demux.sha512Suffix}:", 
                                f"Exiting!"
                            ]
                    text = '\n'.join( text )
                    demuxFailureLogger.critical( f"{ text }" )
                    demuxLogger.critical( f"{ text }" )
                    logging.shutdown( )
                    sys.exit( )
            else:
                continue

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files finished ==\n", color="red", attrs=["bold"] ) )



#######################################################################
# changePermissions
########################################################################

def changePermissions( path ):
    """
    changePermissions: recursively walk down from {directoryRoot} and 
        change the owner to :sambagroup
        if directory
            change permissions to 755
        if file
            change permissions to 644

    INPUT
        input is a generic path rather than demux.demultiplexRunID, because we use this method more than once
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Changing Permissions started ==", color="green", attrs=["bold"] ) )

    demuxLogger.debug( termcolor.colored( f"= walk the file tree, {inspect.stack()[0][3]}() ======================", attrs=["bold"] ) )

    for directoryRoot, dirnames, filenames, in os.walk( path, followlinks = False ):
    
        # change ownership and access mode of files
        for file in filenames:
            filepath = os.path.join( directoryRoot, file )
            demuxLogger.debug( " "*demux.spacing1 + f"chmod 644 {filepath}" ) # print chmod 644 {dirpath}

            if not os.path.isfile( filepath ):
                text = f"{filepath} is not a file. Exiting." 
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            try:
                # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
                os.chmod( filepath, stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH ) # rw-r--r-- / 644 / read-write owner, read group, read others
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
    for directoryRoot, dirnames, filenames, in os.walk( path, followlinks = False ):

        for name in dirnames:
            dirpath = os.path.join( directoryRoot, name )

            demuxLogger.debug( " "*demux.spacing1 + f"chmod 644 {dirpath}" ) # print chmod 755 {dirpath}

            if not os.path.isdir( dirpath ):
                text = f"{dirpath} is not a directory. Exiting."
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            try:
                # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
                os.chmod( dirpath, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH ) # rwxr-xr-x / 755 / read-write-execute owner, read-execute group, read-execute others
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




########################################################################
# tarProjectFiles
########################################################################

def tarProjectFiles( ):
    """

    """
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Adding files to tape archives started ==", color="yellow" ) )

#---------- Prepare a list of the projects to tar under /data/for_transfer ----------------------

    projectsToProcess = [ ]
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

        if any( var in project for var in [ demux.nextSeq, demux.miSeq ] ):         # Make sure there is a nextseq or misqeq tag, before adding the directory to the projectsToProcess
            projectsToProcess.append( project )
            demuxLogger.debug( f"{project:{demux.spacing2}} added to projectsToProcess." )

    text = "projectsToProcess:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{projectsToProcess}" )
    text = "len(projectsToProcess):"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{len( projectsToProcess )}" )
    for project in projectsToProcess:               # create the directories for the individual project e.g. 
                                                    # if project is APEC-Seq it will create {demux.forTransferRunIdDir}/{demux.RunIDShort}.{project}
                                                    # /data/for_transfer/220603_M06578_0105_000000000-KB7MY_demultiplex/220603_M06578.APEC-Seq/
                                                    #
                                                    # Directory path is formatted as absolute
                                                    # 
                                                    # demux.forTransferRunIdDir is created inside prepareDelivery( )
        try:
            forTransferDirProject = os.path.join( demux.forTransferRunIdDir, project )
            os.mkdir( forTransferDirProject ) # we save each tar file into its own directory
        except FileExistsError as err:
            text = [
                f"Error while trying to mkdir {project}",
                f"Error message: { str( err ) }",
                "Exiting."
            ]
            text = '\n'.join( text )
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

#---------- Use the projectsToProcess list to tar files demux data.demultiplexRunID to demux.forTransferRunIdDir   ----------------------

    counter = 0         # used in counting how many projects we have archived so far
    for project in projectsToProcess:
        tarFileDir = os.path.join( demux.forTransferRunIdDir, project )
        tarFile    = os.path.join( tarFileDir, project + demux.tarSuffix )
        demuxLogger.debug( f"tarFile:\t\t\t{tarFile}")

        if not os.path.isfile( tarFile ) :
            tarFileHandle = tarfile.open( name = tarFile, mode = "w:" )
        else:
            text = f"{tarFile} exists. Please investigate or delete. Exiting."
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

#---------- chdir to demux.demultiplexRunIdDir, for nice relative path names when untarring  ----------------------
    try:
        os.chdir( demux.demultiplexRunIdDir )
    except FileExistsError as err:
        text = [
            f"Error while trying to mkdir {project}",
            f"Error message: { str( err ) }",
            "Exiting."
        ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

#---------- Iterrate through demux.demultiplexRunIdDir/projectsToProcess list and make a single tar file for each directory under data.forTransferRunIdDir   ----------------------
        # 
        # build the filetree
        demuxLogger.debug( termcolor.colored( f"\n== walk the file tree, {inspect.stack()[0][3]}() , {os.getcwd( )}/{project} ======================", attrs=["bold"] ) )

        counter = counter + 1
        demuxLogger.info( termcolor.colored( f"==> Archiving {project} ( {counter} out of { len( projectsToProcess ) } projects ) ==================", color="yellow", attrs=["bold"] ) )
        for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.demultiplexRunIdDir, project ), followlinks = False ): 
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

        demux.tarFileStack.append( tarFile ) # add to list of archived tar files, we will use them with lstat later to see if they pass untarring quality control

        demuxLogger.info( termcolor.colored( f'==< Archived {project} ({counter} out of { len( projectsToProcess ) } projects ) ==================\n', color="yellow", attrs=["bold"] ) )

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

    demuxLogger.info( termcolor.colored( f"==> Archiving {demux.demuxQCDirectoryPath} =================", color="yellow", attrs=["bold"] ) )

    tarQCFileHandle = ""

    if demux.verbosity == 2:
        demuxLogger.debug( f"demuxQCDirectoryPath:\t{demux.demuxQCDirectoryPath}" )
        demuxLogger.debug( f"multiqc_data:\t\t{demux.multiqc_data}" )

    if not os.path.isfile( demux.forTransferQCtarFile ): # exit if /data/for_transfer/RunID/qc.tar file exists.
        tarQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "w:" )
    else:
        text = f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.demultiplexRunIdDir, demux.demuxQCDirectoryPath ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the Archivinguser that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( demux.demuxQCDirectoryPath, file )
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            text = "filenameToTar:"
            text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
            demuxLogger.info( text + filenameToTar )
            tarQCFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on

    demux.tarFileStack.append( demux.forTransferQCtarFile ) # list of archived tar files, we will use them with lstat later ot see if they pass untarring quality control

    demuxLogger.info( termcolor.colored( f"==> Archived {demux.demuxQCDirectoryPath} ==================", color="yellow", attrs=["bold"] ) )




########################################################################
# createMultiQcTarFile
########################################################################

def createMultiQcTarFile( ):
    """
    Add the multiqc_data to the qc.tar under /data/for_transfer/RunID
    """
    demuxLogger.info( termcolor.colored( f"==> Archiving {demux.multiqc_data} ==================", color="yellow", attrs=["bold"] ) )

    if os.path.isfile( demux.forTransferQCtarFile ): # /data/for_transfer/RunID/qc.tar must exist before writi
        tarQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "a:" ) # "a:" for exclusive, uncompresed append.
    else:
        text = f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.demultiplexRunIdDir, demux.multiqc_data ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the user that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( demux.multiqc_data, file )
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            text = "filenameToTar"
            text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
            demuxLogger.info( text + filenameToTar )

    # both {demux.RunIDShort}_QC and multidata_qc go in the same tar file
    tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
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

def controlProjectsQC ( RunID ):
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

def sha512FileQualityCheck ( RunID ):
    """
    re-perform (quietly) the sha512 calculation and compare that with the result on file for the specific file.
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: sha512 files check started ==", color="green", attrs=["bold"] ) )

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: sha512 files check finished ==", color="red", attrs=["bold"] ) )





########################################################################
# tarFileQualityCheck: verify tar files before upload
########################################################################

def tarFileQualityCheck ( RunID ):
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
        delete {demux.forTransferRunIdDir}/{demux.forTransferRunIDdirTest} and contents
        return True/false depending on answer

    INPUT
        Input is RunID rather than demux.RunID or some other variable because we can use this method later to check the tarFile quality of any fetched tar file from archive
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Tar files quaility check started ==", color="green", attrs=["bold"] ) )

#---- Step 1: create a /data/for_transfer/RunID/test directory -------------------------------------------------------------------------------------------

    # ensure that demux.forTransferDir (/data/for_transfer) exists
    if not os. path. isdir( demux.forTransferDir ):
        text = f"{demux.forTransferDir} does not exist! Please re-run the ansible playbook! Exiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )    

    try: 
        forTransferRunIDdirTest = os.join( demux.forTransferRunIdDir,demux.forTransferRunIdDirTestName )
        os.mkdir( forTransferRunIDdirTest )
    except e as err:
        text = f"{demux.forTransferRunIdDir} cannot be created: { str( err ) }\nExiting!"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

#---- Step 2: copy any tar file for relevant RunIDShort into the test directory ---------------------------------------------------------------------------

    # we need a list of the .tar files inside demux.forTransferRunIdDir ( /data/for_transfer/220603_M06578_0105_000000000-KB7MY )
    transferTarFiles = glob.glob( f"{demux.forTransferRunIdDir}/*.tar" )
    # get a copy of the sha512 files, as well
    transfterSha512Files = glob.glob( f"{demux.forTransferRunIdDir}/*.sha512")
    #
    # then copy them into forTransferRunIDdirTest

#---- Step 3: untar files under /data/for_transfer/RunID/test -------------------------------------------------------------------------------------------
    transferTarTestFiles = glob.glob( f"{demux.forTransferRunIdDir}/{demux.forTransferRunIDdirTest}/*.tar" )
    for tarfile in transferTarTestFiles:
        try:
            tarHandle = tarfile.open( name = tarfile, mode = 'r', fileobj = None, bufsize = 10240 )
            tarHandle.extractall( forTransferRunIDdirTest )
            tarHandle.close( )
        except e as err:
            text = f"{forTransferRunIDdirTest}/{tarfile} cannot be created: { str( err ) }\nExiting!"
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

#---- Step 4: recalculate sha512 hash for each file ------------------------------------------------------------------------------------------------------


#---- Step 5: compare result with hash file on disk ------------------------------------------------------------------------------------------------------


#---- Step 6: delete {demux.forTransferRunIdDir}/{demux.forTransferRunIDdirTest} and contents ------------------------------------------------------------


#---- Step 7: return True/false depending on answer ------------------------------------------------------------------------------------------------------

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Tar files quaility check finished ==", color="red", attrs=["bold"] ) )

    sys.exit( )





########################################################################
# script_completion_file
########################################################################

def scriptComplete( ):
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

def deliverFilesToVIGASP( RunID ):
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

def deliverFilesToNIRD( RunID ):
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




########################################################################
# setupEventAndLogHandling( )
########################################################################

def setupEventAndLogHandling( ):
    """
    Setup the event and log handling we will be using everywhere
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Set up the Event and Log handling ==\n", color="green", attrs=["bold"] ) )


    # demuxLogFormatter = logging.Formatter( "%(asctime)s %(dns)s %(name)s %(levelname)s %(message)s", defaults = { "dns": socket.gethostname( ) } ) #
    demuxLogFormatter      = logging.Formatter( "%(asctime)s %(dns)s %(filename)s %(levelname)s %(message)s", datefmt = '%Y-%m-%d %H:%M:%S', defaults = { "dns": socket.gethostname( ) } )
    demuxSyslogFormatter   = logging.Formatter( "%(levelname)s %(message)s" )

    # setup loging for console
    demuxConsoleLogHandler    = logging.StreamHandler( stream = sys.stderr )
    demuxConsoleLogHandler.setFormatter( demuxLogFormatter )

    # # setup logging for syslog
    demuxSyslogLoggerHandler       = logging.handlers.SysLogHandler( address = '/dev/log', facility = syslog.LOG_USER ) # setup the syslog logger
    demuxSyslogLoggerHandler.ident = f"{os.path.basename(__file__)} "
    demuxSyslogLoggerHandler.setFormatter( demuxSyslogFormatter )

    # # setup email notifications
    demuxSMTPfailureLogHandler = BufferingSMTPHandler( demux.mailhost, demux.fromAddress, demux.toAddress, demux.subjectFailure )
    demuxSMTPsuccessLogHandler = BufferingSMTPHandler( demux.mailhost, demux.fromAddress, demux.toAddress, demux.subjectSuccess )

    demuxLogger.addHandler( demuxSyslogLoggerHandler )
    demuxLogger.addHandler( demuxConsoleLogHandler )
    demuxLogger.addHandler( demuxSMTPsuccessLogHandler )

    # this has to be in a separate logger because we are only logging to it when we fail
    demuxFailureLogger.addHandler( demuxSMTPfailureLogHandler )

    # # setup logging for messaging over Workplace
    # demuxHttpsLogHandler       = logging.handlers.HTTPHandler( demux.httpsHandlerHost, demux.httpsHandlerUrl, method = 'GET', secure = True, credentials = None, context = None ) # FIXME later

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Set up the Event and Log handling ==\n", color="red", attrs=["bold"] ) )



########################################################################
# copySampleSheetIntoDemultiplexRunIdDir( )
########################################################################

def copySampleSheetIntoDemultiplexRunIdDir( ):
    """
    Copy SampleSheet.csv from {demux.SampleSheetFilePath} to {demux.DemultiplexRunIdDir}
        because bcl2fastq requires the file existing before it starts demultiplexing
    """
    #

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIdDir} ==\n", color="green", attrs=["bold"] ) )

    try:
        currentPermissions = stat.S_IMODE(os.lstat( demux.sampleSheetFilePath ).st_mode )
        os.chmod( demux.sampleSheetFilePath, currentPermissions & ~stat.S_IEXEC  ) # demux.SampleSheetFilePath is probably +x, remnant from windows transfer, so remove execute bit
        shutil.copy2( demux.sampleSheetFilePath, demux.demultiplexRunIdDir )
    except Exception as err:
        text = [    f"Copying {demux.sampleSheetFilePath} to {demux.demultiplexRunIdDir} failed.",
                    err.tostring( ),
                    "Exiting."
        ]
        '\n'.join( text )
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIdDir} ==\n", color="red", attrs=["bold"] ) )




########################################################################
# archiveSampleSheet( )
########################################################################

def archiveSampleSheet( ):
    """

    # Request by Cathrine: Copy the SampleSheet file to /data/samplesheet automatically

    Check for validity of the filepath of the sample sheet
    then
        archive a copy
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Archive {demux.sampleSheetFilePath} to {demux.sampleSheetArchiveFilePath} ==\n", color="green", attrs=["bold"] ) )


    if not os.path.exists( demux.sampleSheetFilePath ):
        text = f"{demux.sampleSheetFilePath} does not exist! Demultiplexing cannot continue. Exiting."
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )


    if not os.path.isfile( demux.sampleSheetFilePath ):
        text = f"{demux.ampleSheetFilePath} is not a file! Exiting."
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    try:
        shutil.copy2( demux.sampleSheetFilePath, demux.sampleSheetArchiveFilePath )
        currentPermissions = stat.S_IMODE(os.lstat( demux.sampleSheetArchiveFilePath ).st_mode )
        os.chmod( demux.sampleSheetArchiveFilePath, stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH ) # Set samplesheet to "o=rw,g=r,o=r"
    except Exception as err:
        frameinfo = getframeinfo( currentframe( ) )
        text = [    f"Archiving {demux.sampleSheetFilePath} to {demux.sampleSheetArchiveFilePath} failed.",
                    str(err),
                    f" at {frameinfo.filename}:{frameinfo.lineno}."
                    "Exiting.",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks:  Archive {demux.sampleSheetFilePath} to {demux.sampleSheetArchiveFilePath} ==\n", color="red", attrs=["bold"] ) )




########################################################################
# setupFileLogHandling( )
########################################################################

def setupFileLogHandling( ):
    """
    Setup the file event and log handling
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Setup the file event and log handling ==\n", color="green", attrs=["bold"] ) )

    # make sure that the /data/log directory exists.
    if not os.path.isdir( demux.logDirPath ) :
        text = [    "Trying to setup demux.logDirPath failed. Reason:\n",
                    "The parts of demux.logDirPath have the following values:\n",
                    f"demux.dataRootDirPath:\t\t\t{demux.dataRootDirPath}\n",
                    f"demux.logDirName:\t\t\t{demux.logDirName}\n",
                    f"demux.logDirPath:\t\t\t\t{demux.logDirPath}\n"
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    # # set up logging for /data/log/{demux.RunID}.log
    try: 
        demuxFileLogHandler   = logging.FileHandler( demux.demuxRunLogFilePath, mode = 'w', encoding = demux.decodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxFileLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.demuxRunLogFilePath have the following values:\n",
                    f"demux.demuxRunLogFilePath:\t\t\t{demux.demuxRunLogFilePath}\n",
                    f"demux.RunID + demux.logSuffix:\t\t{demux.RunID} + {demux.logSuffix}\n",
                    f"demux.logDirPath:\t\t\t\t{demux.logDirPath}\n"
        ]
        demuxFailureLogger.critical( *text  )
        demuxLogger.critical( *text )
        logging.shutdown( )
        sys.exit( )

    demuxLogFormatter      = logging.Formatter( "%(asctime)s %(dns)s %(filename)s %(levelname)s %(message)s", datefmt = '%Y-%m-%d %H:%M:%S', defaults = { "dns": socket.gethostname( ) } )
    demuxFileLogHandler.setFormatter( demuxLogFormatter )
    demuxLogger.setLevel( demux.loggingLevel )

    # set up cummulative logging in /data/log/demultiplex.log
    try:
        demuxFileCumulativeLogHandler   = logging.FileHandler( demux.demuxCumulativeLogFilePath, mode = 'a', encoding = demux.decodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxFileCumulativeLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.demuxRunLogFilePath have the following values:\n",
                    f"demux.demuxCumulativeLogFilePath:\t\t\t{demux.demuxCumulativeLogFilePath}\n",
                    f"demux.logDirPath:\t\t\t\t\t{demux.logDirPath}\n",
                    f"demux.demultiplexLogDirName:\t\t\t{demux.demultiplexLogDirName}\n",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxFileCumulativeLogHandler.setFormatter( demuxLogFormatter )

    # setup logging for /data/bin/demultiplex/demux.RunID/demultiplex_log/00_script.log
    try:
        demuxScriptLogHandler   = logging.FileHandler( demux.demultiplexScriptLogFilePath, mode = 'w', encoding = demux.decodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxScriptLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.DemultiplexScriptLogFilePath have the following values:\n",
                    f"demux.demultiplexScriptLogFilePath:\t\t\t{demux.demultiplexScriptLogFilePath}\n",
                    f"demux.demultiplexLogDirPath\t\t\t\t{demux.demultiplexLogDirPath}\n",
                    f"demux.scriptRunLogFileName:\t\t\t\t{demux.scriptRunLogFileName}\n",
                    f"demux.demultiplexRunIdDir:\t\t\t\t{demux.demultiplexRunIdDir}\n",
                    f"demux.demultiplexLogDirName:\t\t\t\t{demux.demultiplexLogDirName}\n",
                    f"demux.demultiplexDir:\t\t\t\t\t{demux.demultiplexDir}\n",
                    f"RunID + demux.demultiplexDirSuffix:\t{demux.RunID} + {demux.demultiplexDirSuffix}\n",
                    "Exiting.",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxScriptLogHandler.setFormatter( demuxLogFormatter )

    demuxLogger.addHandler( demuxScriptLogHandler )
    demuxLogger.addHandler( demuxFileLogHandler )
    demuxLogger.addHandler( demuxFileCumulativeLogHandler )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Setup the file event and log handling ==\n", color="red", attrs=["bold"] ) )



########################################################################
# checkRunningEnvironment( )
########################################################################

def checkRunningEnvironment( ):
    """
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Check the validity of the current running environment ==\n", color="green", attrs=["bold"] ) )

    # ensure Java[tm] exists
    if not shutil.which( "java"):
        text = "Java executable not detected! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    if len( demux.projectList ) == 0:
        text = "List projectList contains no projects/zero length! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )
    elif demux.debug and len( demux.projectList ) == 1: 
        demux.projectList.add( demux.testProject )               # if debug, have at least two project names to ensure multiple paths are being created

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Check the validity of the current running environment ==\n", color="red", attrs=["bold"] ) )



########################################################################
# printRunningEnvironment( )
########################################################################

def printRunningEnvironment( ):
    """
    Print our running environment
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Print out the current running environment ==\n", color="green", attrs=["bold"] ) )

    stateLetter = "R"  # initialize the state of this mini-automaton with 'R' cuz first item in the demux.globalDictionary starts with 'R'
    logString   = "log"

    demuxLogger.info( f"To rerun this script run\n" )
    demuxLogger.info( termcolor.colored( f"\tclear; rm -rf {demux.demultiplexRunIdDir} && rm -rf {demux.forTransferRunIdDir} && /usr/bin/python3 /data/bin/demultiplex_script.py {demux.RunID}\n\n", attrs=["bold"] ) )

    demuxLogger.debug( "=============================================================================")
    for key, value2 in demux.globalDictionary.items( ):         # take the key/label and the value of the key from the global dictionary
        if type( value2 ) is list:                              # if this is a list, print each individual member of the list
            demuxLogger.debug( "=============================================================================")
            for index, value1 in enumerate( value2 ):       
                text = f"{key}[{str(index)}]:"
                text = f"{text:{demux.spacing3}}{value1}"
                demuxLogger.debug( text )
        else:
            text = f"{key:{demux.spacing2}}" + value2           # if it is not a list, print the item but
            if key[0] != stateLetter:                           # if the first letter of this is different fr
                stateLetter = key[0]
                if re.search( logString, key, re.IGNORECASE):   # keep the *Log* variables together
                    continue
                demuxLogger.debug( "=============================================================================")
            
            demuxLogger.debug( text )
    demuxLogger.debug( "=============================================================================")
    demuxLogger.debug( "\n")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Print out the current running environment ==\n", color="red", attrs=["bold"] ) )





########################################################################
# setupEnvironment( )
########################################################################

def setupEnvironment( RunID ):
    """
    Setup the variables for our environment
    """

    demux.n = demux.n + 1
    if 'demuxLogger' in logging.Logger.manager.loggerDict.keys():
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Set up the current running environment ==\n", color="green", attrs=["bold"] ) )
    else:
        print( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Set up the current running environment ==\n", color="green", attrs=["bold"] ) )

    demux.RunID                         = RunID
    demux.RunIDShort                    = '_'.join( RunID.split('_')[0:2] ) # this should be turned into a setter in the demux object
######################################################
    demux.rawDataRunIDdir               = os.path.join( demux.rawDataDir,           demux.RunID )
    demux.sampleSheetFilePath           = os.path.join( demux.rawDataRunIDdir,      demux.sampleSheetFileName )
    demux.rtaCompleteFilePath           = os.path.join( demux.rawDataRunIDdir,      demux.rtaCompleteFile )

    demux.getProjectName( )             # get the list of projects in this current run

######################################################
    demux.demultiplexRunIdDir           = os.path.join( demux.demultiplexDir,       demux.RunID + demux.demultiplexDirSuffix ) 
    demux.demultiplexLogDirPath         = os.path.join( demux.demultiplexRunIdDir,  demux.demultiplexLogDirName ) 
    demux.demuxQCDirectoryName          = demux.RunIDShort + demux.qcSuffix              # example: 200624_M06578_QC  # QCSuffix is defined in object demux
    demux.demuxQCDirectoryPath          = os.path.join( demux.demultiplexRunIdDir,  demux.demuxQCDirectoryName  )
    demux.bcl2FastqLogFile              = os.path.join( demux.demultiplexRunIdDir,  demux.demultiplexLogDirPath, demux.bcl2FastqLogFileName )
######################################################
    demux.forTransferRunIdDir           = os.path.join( demux.forTransferDir,       demux.RunID )
    demux.forTransferQCtarFile          = os.path.join( demux.forTransferRunIdDir,  demux.RunID + demux.qcSuffix + demux.tarSuffix )
######################################################

    # set up
    demux.demuxRunLogFilePath           = os.path.join( demux.logDirPath,            demux.RunID + demux.logSuffix )
    demux.demuxCumulativeLogFilePath    = os.path.join( demux.logDirPath,            demux.demuxCumulativeLogFileName )
    demux.demultiplexLogDirPath         = os.path.join( demux.demultiplexRunIdDir,   demux.demultiplexLogDirName )
    demux.demultiplexScriptLogFilePath  = os.path.join( demux.demultiplexLogDirPath, demux.scriptRunLogFileName )
    demux.fastQCLogFilePath             = os.path.join( demux.demultiplexLogDirPath, demux.fastqcLogFileName )
    demux.mutliQCLogFilePath            = os.path.join( demux.demultiplexLogDirPath, demux.multiqcLogFileName )
    demux.sampleSheetArchiveFilePath    = os.path.join( demux.sampleSheetDirPath,    demux.RunID + demux.csvSuffix ) # .dot is included in csvSuffix

    # maintain the order added this way, so our little stateLetter trick will work
    demux.globalDictionary = {  
        'RunID'                         : str( ),
        'RunIDShort'                    : str( ),
        'rawDataRunIDdir'               : str( ),
        'rtaCompleteFilePath'           : str( ),
        'sampleSheetFilePath'           : str( ),
        'demultiplexRunIdDir'           : str( ),
        'demultiplexLogDirPath'         : str( ),
        'demuxQCDirectoryPath'          : str( ),
        'demuxRunLogFilePath'           : str( ),
        'demuxCumulativeLogFilePath'    : str( ),
        'demultiplexLogDirPath'         : str( ),
        'demultiplexScriptLogFilePath'  : str( ),
        'bcl2FastqLogFile'              : str( ),
        'fastQCLogFilePath'             : str( ),
        'mutliQCLogFilePath'            : str( ),
        'forTransferRunIdDir'           : str( ),
        'forTransferQCtarFile'          : str( ),
        'sampleSheetArchiveFilePath'    : str( ),
        'projectList'                   : list( ),
        'newProjectNameList'            : list( )
    }


    # maintain the order added this way, so our little stateLetter trick will work
    demux.globalDictionary[ 'RunID'                        ] = demux.RunID
    demux.globalDictionary[ 'RunIDShort'                   ] = demux.RunIDShort
    demux.globalDictionary[ 'rawDataRunIDdir'              ] = demux.rawDataRunIDdir
    demux.globalDictionary[ 'rtaCompleteFilePath'          ] = demux.rtaCompleteFilePath
    demux.globalDictionary[ 'sampleSheetFilePath'          ] = demux.sampleSheetFilePath
    demux.globalDictionary[ 'demultiplexRunIdDir'          ] = demux.demultiplexRunIdDir
    demux.globalDictionary[ 'demultiplexLogDirPath'        ] = demux.demultiplexLogDirPath
    demux.globalDictionary[ 'demuxQCDirectoryPath'         ] = demux.demuxQCDirectoryPath
    demux.globalDictionary[ 'demuxRunLogFilePath'          ] = demux.demuxRunLogFilePath
    demux.globalDictionary[ 'demuxCumulativeLogFilePath'   ] = demux.demuxCumulativeLogFilePath
    demux.globalDictionary[ 'demultiplexLogDirPath'        ] = demux.demultiplexLogDirPath
    demux.globalDictionary[ 'demultiplexScriptLogFilePath' ] = demux.demultiplexScriptLogFilePath
    demux.globalDictionary[ 'bcl2FastqLogFile'             ] = demux.bcl2FastqLogFile
    demux.globalDictionary[ 'fastQCLogFilePath'            ] = demux.fastQCLogFilePath
    demux.globalDictionary[ 'mutliQCLogFilePath'           ] = demux.mutliQCLogFilePath
    demux.globalDictionary[ 'forTransferRunIdDir'          ] = demux.forTransferRunIdDir
    demux.globalDictionary[ 'forTransferQCtarFile'         ] = demux.forTransferQCtarFile
    demux.globalDictionary[ 'sampleSheetArchiveFilePath'   ] = demux.sampleSheetArchiveFilePath
    demux.globalDictionary[ 'projectList'                  ] = demux.projectList
    demux.globalDictionary[ 'newProjectNameList'           ] = demux.newProjectNameList


    if 'demuxLogger' in logging.Logger.manager.loggerDict.keys():
        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Set up the current running environment ==\n", color="red", attrs=["bold"] ) )
    else:
        print( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Set up the current running environment ==\n", color="red", attrs=["bold"] ) )




########################################################################
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


    setupEventAndLogHandling( )                                                                         # setup the event and log handing, which we will use everywhere, sans file logging 
    setupEnvironment( RunID )                                                                           # set up variables needed in the running setupEnvironment  
    # moved inside setupEnvironment( )
    # demux.getProjectName( )                                                                             # get the list of projects in this current run
    createDemultiplexDirectoryStructure( )                                                              # create the directory structure under {demux.demultiplexRunIdDir}
    # renameProjectListAccordingToAgreedPatttern( )                                                     # rename the contents of the projectList according to {RunIDShort}.{project}
    # #################### createDemultiplexDirectoryStructure( ) needs to be called before we start logging  ###########################################
    setupFileLogHandling( )                                                                             # setup the file event and log handing, which we left out
    printRunningEnvironment( )                                                                          # print our running environment
    checkRunningEnvironment( )                                                                          # check our running environment
    copySampleSheetIntoDemultiplexRunIdDir( )                                                           # copy SampleSheet.csv from {demux.sampleSheetFilePath} to {demux.demultiplexRunIdDir}
    archiveSampleSheet( )                                                                               # make a copy of the Sample Sheet for future reference
    demultiplex( )                                                                                      # use blc2fastq to convert .bcl files to fastq.gz
    renameFilesAndDirectories( )                                                                        # rename the *.fastq.gz files and the directory project to comply to the {RunIDShort}.{project} convention
    qualityCheck( )                                                                                     # execute QC on the incoming fastq files
    calcFileHash( demux.demultiplexRunIdDir )                                                           # create .md5/.sha512 checksum files for every .fastqc.gz/.tar/.zip file under demultiplexRunIdDir
    changePermissions( demux.demultiplexRunIdDir  )                                                     # change permissions for the files about to be included in the tar files 
    prepareForTransferDirectoryStructure( )                                                             # create /data/for_transfer/RunID and any required subdirectories
    prepareDelivery( )                                                                                  # prepare the delivery files
    calcFileHash( demux.forTransferRunIdDir )                                                           # create .md5/.sha512 checksum files for the delivery .fastqc.gz/.tar/.zip files under demultiplexRunIdDir, but this 2nd fime do it for the new .tar files created by prepareDelivery( )
    changePermissions( demux.forTransferRunIdDir  )                                                     # change permissions for all the delivery files, including QC
    controlProjectsQC ( )                                                                               # check to see if we need to create the report for any control projects present
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

    if sys.hexversion < 50923248: # Require Python 3.9 or newer
        sys.exit( "Python 3.9 or newer is required to run this program." )

    # FIXMEFIXME add named arguments
    if len(sys.argv) == 1:
        sys.exit( "No RunID argument present. Exiting." )

    demuxLogger             = logging.getLogger( __name__ )
    demuxFailureLogger      = logging.getLogger( "SMTPFailureLogger" )
    RunID                   = sys.argv[1]
    RunID                   = RunID.replace( "/", "" ) # Just in case anybody just copy-pastes from a listing in the terminal, be forgiving

    main( RunID )
