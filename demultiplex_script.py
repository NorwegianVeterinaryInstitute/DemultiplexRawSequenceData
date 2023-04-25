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
    verbosity = 1
    ######################################################
    DataRootDirPath                 = '/data'
    RawDataDirName                  = 'rawdata'
    RawDataDir                      =  os.path.join( DataRootDirPath, RawDataDirName )
    DemultiplexDirName              = "demultiplex"
    DemultiplexDir                  = os.path.join( DataRootDirPath, DemultiplexDirName )
    ForTransferDirName              = 'for_transfer'
    ForTransferDir                  = os.path.join( DataRootDirPath, ForTransferDirName )
    SampleSheetDirName              = 'samplesheets'
    SampleSheetDirPath              = os.path.join( DataRootDirPath, SampleSheetDirName )
    LogDirName                      = "log"
    LogDirPath                      = os.path.join( DataRootDirPath, LogDirName )
    ######################################################
    CompressedFastqSuffix           = '.fastq.gz' 
    CSVSuffix                       = '.csv'
    DemultiplexDirSuffix            = '_demultiplex'
    multiqc_data                    = 'multiqc_data'
    md5Suffix                       = '.md5'
    QCSuffix                        = '_QC'
    sha512Suffix                    = '.sha512'
    tarSuffix                       = '.tar'
    temp                            = 'temp'
    zipSuffix                       = '.zip'
    HTMLSuffix                      = '.html'
    LogSuffix                       = '.log'
    ######################################################
    bcl2fastq_bin                   = f"{DataRootDirPath}/bin/bcl2fastq"
    fastqc_bin                      = f"{DataRootDirPath}/bin/fastqc"
    mutliqc_bin                     = f"{DataRootDirPath}/bin/multiqc"
    python3_bin                     = f"/usr/bin/python3"
    ScriptFilePath                  = __file__
    ######################################################
    RTACompleteFile                 = 'RTAComplete.txt'
    SampleSheetFileName             = 'SampleSheet.csv'
    TestProject                     = 'FOO-blahblah-BAR'
    Sample_Project                  = 'Sample_Project'
    DemultiplexCompleteFile         = 'DemultiplexComplete.txt'
    vannControlNegativReport        = 'Negativ'
    md5File                         = 'md5sum.txt'
    MiSeq                           = 'M06578'   # if we get more than one, turn this into an array, or read from config, or read from illumina
    NextSeq                         = 'NB552450' # if we get more than one, turn this into an array, or read from config, or read from illumina
    DecodeScheme                    = "utf-8"
    footarfile                      = f"foo{tarSuffix}"      # class variable shared by all instances
    barzipfile                      = f"zip{zipSuffix}"
    TotalTasks                      = 0  

    ######################################################
    RunIDShort                      = ""
    RawDataRunIDdir                 = ""
    DemultiplexRunIDdir             = ""
    DemultiplexLogDirPath           = ""
    DemultiplexQCDirPath            = ""
    DemultiplexScriptLogFilePath    = ""
    DemuxQCDirectoryName            = ""
    DemuxQCDirectoryPath            = ""
    ForTransferRunIDdir             = ""
    ForTransferQCtarFile            = ""
    SampleSheetFilePath             = os.path.join( SampleSheetDirPath, SampleSheetFileName )
    SampleSheetArchiveFilePath      = ""
    ######################################################
    DemultiplexProjSubDirs          = [ ]
    ForTransferProjNames            = [ ]
    tarFileStack                    = [ ]
    ######################################################
    ControlProjects                 = [ "Negativ" ]
    ######################################################
    ForTransferRunIdDir             = ""
    forTransferQCtarFile            = ""
    ######################################################
    DemuxCumulativeLogFileName      = 'demultiplex.log'
    DemultiplexLogDirName           = 'demultiplex_log'
    ScriptRunLogFileName            = '00_script.log'
    Bcl2FastqLogFileName            = '01_demultiplex.log'
    FastqcLogFileName               = '02_fastqcLogFile.log'
    MultiqcLogFileName              = '03_multiqcLogFile.log'
    LoggingLevel                    = logging.DEBUG
    ######################################################
    DemuxCumulativeLogFilePath      = ""
    DemuxBcl2FastqLogFilePath       = ""
    FastQCLogFilePath               = ""
    LogFilePath                     = ""
    MultiQCLogFilePath              = ""
    ScriptRunLogFile                = ""
    ForTransferDirRoot              = ""

    ######################################################
    # mailhost                        = 'seqtech00.vetinst.no'
    mailhost                        = 'localhost'
    fromAddress                     = 'demultiplex@seqtech00.vetinst.no'
    toAddress                       = 'gmarselis@localhost'
    subjectFailure                  = 'Demultiplexing has failed'
    subjectSuccess                  = 'Demultiplexing has finished successfuly'
    ######################################################
    httpsHandlerHost                = 'veterinaerinstituttet307.workplace.com'
    httpsHandlerUrl                 = 'https://veterinaerinstituttet307.workplace.com/chat/t/4997584600311554'
    ######################################################
    threadsToUse                    = 12                        # the amount of threads FastQC and other programs can utilize
    ######################################################
    with open( __file__ ) as f:     # little trick from openstack: read the current script and count the functions and initialize TotalTasks to it
        tree = ast.parse( f.read( ) )
        TotalTasks = sum( isinstance( exp, ast.FunctionDef ) for exp in tree.body ) + 2 # + 2 adjust as needed
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
                Example of returned project_list:     {'SAV-amplicon-MJH'}

        Parsing is simple:
            go line-by-line
            ignore all the we do not need until
                we hit the line that contains 'Sample_Project'
                if 'Sample_Project' found
                    split the line and 
                        take the value of 'Sample_Project'
            return an set of the values of all values of 'Sample_Project' and 'Analysis'
        """

        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Get project name from {demux.SampleSheetFilePath} started ==\n", color="green", attrs=["bold"] ) )

        project_line_check = False
        project_index  = 0
        project_list   = []
        SampleSheetContents = [ ]

        SampleSheetFileHandle = open( demux.SampleSheetFilePath, 'r', encoding= demux.DecodeScheme )
        SampleSheetContent    = SampleSheetFileHandle.read( )     # read the contents of the SampleSheet here

        if demux.debug and demux.verbosity == 2:
            demuxLogger.debug(f"SampleSheetContents:\n{SampleSheetContent}") # logging.info it

        SampleSheetContents   = SampleSheetContent.split( '\n' )  # then split it in lines


        for line in SampleSheetContents:

            if demux.debug and demux.verbosity == 2:
                demuxLogger.debug( f"procesing line '{line}'")

            if line != '': # line != '' is not the same as 'not line'
                line = line.rstrip()
                if demux.debug and demux.verbosity == 2:
                    demuxLogger.debug( f"project_index: {project_index}" )
                item = line.split(',')[project_index]
            else:
                break

            if project_line_check == True and item not in project_list :
                if demux.debug and demux.verbosity == 2:
                    demuxLogger.debug( f"item:\t\t\t\t\t\t{item}")
                project_list.append( item )# + '.' + line.split(',')[analysis_index]) # this is the part where .x shows up. Removed.

            elif demux.Sample_Project in line: # demux.Sample_Project is defined in class demux:

                project_index      = line.split(',').index( demux.Sample_Project )
                if demux.debug and demux.verbosity == 2:
                    demuxLogger.debug( f"project_index:\t\t\t\t{project_index}")

                project_line_check = True
            else:
                continue

        if len( project_list ) == 0:
            text = "project_list is empty! Exiting!"
            demuxFailureLogger.critical( text  )
            demuxLogger.critical( text )
            logging.shutdown( )
            sys.exit( )
        else:
            demuxLogger.info( f"project_list: {project_list}\n" )

        demux.project_list = project_list   # no need to return anything, save everything in the object space
        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Get project name from {demux.SampleSheetFilePath} finished ==\n", color="red", attrs=["bold"] ) )



    ########################################################################
    # checkTarFiles( )
    ########################################################################
    def checkTarFiles ( listOfTarFilesToCheck ):
        """
        Check to see if the tar files created for delivery can be listed with no errors
        use
            TarFile.list(verbose=True, *, members=None)
                    Print a table of contents to sys.stdout. If verbose is False, only the names of the members are logging.infoed. If it is True, output similar to that of ls -l is produced. If optional members is given, it must be a subset of the list returned by getmembers(). 

            https://docs.python.org/3/library/tarfile.html

        But do it quietly, no need for output other than an OK/FAIL
        """

        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Verify that the tar files produced are actually untarrable started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Verify that the tar files produced are actually untarrable finished ==\n", color="red", attrs=["bold"] ) )



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
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: See if the specific RunID has already been demultiplexed started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: See if the specific RunID has already been demultiplexed finished ==\n", color="red", attrs=["bold"] ) )



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
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: See if the specific RunID has already been demultiplexed started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: See if the specific RunID has already been demultiplexed finished ==\n", color="red", attrs=["bold"] ) )



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
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Check SampleSheet.csv for common human mistakes started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Check SampleSheet.csv for common human mistakes finished ==\n", color="red", attrs=["bold"] ) )




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

def createDemultiplexDirectoryStructure( DemultiplexRunIdDir ):
    """
    If the Demultiplexing directory or any relevant directory does not exist, create it
        demux.RunIDShort format is in the pattern of (date +%y%m%d)_SEQUENCERSERIALNUMBER Example: 220314_M06578
        {DemultiplexDirRoot} == "/data/demultiplex" # default

        {DemultiplexDirRoot}/{RunID}_{DemultiplexDirSuffix}/
        {DemultiplexDirRoot}/{RunID}_{DemultiplexDirSuffix}/project_list[0]
        {DemultiplexDirRoot}/{RunID}_{DemultiplexDirSuffix}/project_list[1]
        .
        .
        .
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/project_list[ len(project_list) -1 ]
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/{DemultiplexLogDir}
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/{demux.RunIDShort}{demux.QCSuffix}
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/Reports      # created by bcl2fastq
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/Stats        # created by bcl2fastq
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Create directory structure started ==", color="green", attrs=["bold"] ) )

    demux.DemultiplexLogDirPath = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDirName ) 
    demux.DemuxQCDirectoryName  = f"{demux.RunIDShort}{demux.QCSuffix}" # QCSuffix is defined in object demux
    demux.DemuxQCDirectoryPath  = os.path.join( DemultiplexRunIdDir, demux.DemuxQCDirectoryName  )

    if demux.debug:
            demuxLogger.debug( f"demux.DemultiplexRunIdDir\t\t\t{demux.DemultiplexRunIdDir}" )
            demuxLogger.debug( f"DemultiplexRunIdDir/DemultiplexLogDir:\t\t{demux.DemultiplexLogDirPath}" )
            demuxLogger.debug( f"DemultiplexRunIdDir/DemuxQCDirectory:\t\t{demux.DemuxQCDirectoryPath}" )

    try:
        os.mkdir( demux.DemultiplexRunIdDir )   # root directory for run
        os.mkdir( demux.DemultiplexLogDirPath ) # log directory for run
        os.mkdir( demux.DemuxQCDirectoryPath )  # QC directory  for run
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


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Create directory structure finished ==\n", color="red", attrs=["bold"] ) )



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
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Demultiplexing started ==\n", color="green", attrs=["bold"] ) )

    argv = [ demux.bcl2fastq_bin,
         "--no-lane-splitting",
         "--runfolder-dir",
        f"{demux.RawDataRunIDdir}",
         "--output-dir",
        f"{demux.DemultiplexRunIdDir}"
    ]
    if demux.debug:
        demuxLogger.debug( f"Command to execute:\t\t\t\t" + " ".join( argv ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + demux.RawDataRunIDdir + ' --output-dir ' + DemultiplexDir + ' 2> ' + DemultiplexDir + '/demultiplex_log/02_demultiplex.log'
        result =  subprocess.run( argv, capture_output = True, cwd = demux.RawDataRunIDdir, check = True, encoding = demux.DecodeScheme )
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
        Bcl2FastqLogFile     = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDirPath, demux.Bcl2FastqLogFileName )
        file = open( Bcl2FastqLogFile, "w" )
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

    if demux.debug:
        if not os.path.isfile( Bcl2FastqLogFile ):
            demuxFailureLogger.critical( f"{Bcl2FastqLogFile} did not get written to disk. Exiting." )
            demuxLogger.debug( f"{Bcl2FastqLogFile} did not get written to disk. Exiting." )
            logging.shutdown( )
            sys.exit( )
        else:
            filesize = os.path.getsize( Bcl2FastqLogFile )
            demuxLogger.debug( f"Bcl2FastqLogFile:\t\t\t\t{Bcl2FastqLogFile} is {filesize} bytes.\n")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Demultiplexing finished ==\n", color="red", attrs=["bold"] ) )




########################################################################
# renameDirectories( )
########################################################################

def renameDirectories( project_list ):
    """
        For each project directory in project_list
            rename the project directory  to conform from the {demux.DemultiplexRunIdDir}/{project} pattern to the {demux.DemultiplexRunIdDir}/{demux.RunIDShort}.{project}

        Why you ask?
            That's how the original script does it (TRADITION!)

            One good reason is, of course to keep track of the file, if something goes wrong.
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Print out the current running environment ==\n", color="green" ) )


    for project in project_list: # rename the project directories

        oldname = f"{demux.DemultiplexRunIdDir}/{project}"
        newname = f"{demux.DemultiplexRunIdDir}/{demux.RunIDShort}.{project}"
        # make sure oldname dir exists
        # make sure newname dir name does not exist
        olddirExists = os.path.isdir( oldname )
        newdirExists = os.path.isdir( newname )

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

            if demux.debug:
                demuxLogger.debug( termcolor.colored( f"Renaming {oldname} to {newname}", color="cyan", attrs=["reverse"] ) )

    for index, item in enumerate( newProjectFileList ):
        demuxLogger.debug( f"newProjectFileList[{index}]:\t\t\t\t{item}") # make sure the debugging output is all lined up.

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Renaming files finished ==\n", color="red" ) )



def renameFiles( DemultiplexRunIdDir, project_list ):
    """
    Rename the files within each {project} to conform to the {RunIDShort}.{filename}.fastq.gz pattern

    Why? see above? it's always been done that way.
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Rename files ==\n", color="green" ) )

    oldname            = ""
    newname            = ""
    newProjectFileList = [ ]
    for project in project_list: # rename files in each project directory

        if any( var in project for var in demux.ControlProjects ):      # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        elif project == demux.TestProject:                              # ignore the test project
            if demux.debug:
                demuxLogger.debug( f"Test project '{demux.TestProject}' detected. Skipping." )
                continue

        CompressedFastQfilesDir = f"{demux.DemultiplexRunIdDir}/{project}"
        if demux.debug:
            demuxLogger.debug( termcolor.colored(   f"Now working on project:\t\t\t\t{project}", color="cyan", attrs=["reverse"] ) )
            demuxLogger.debug( f"CompressedFastQfilesDir:\t\t\t{CompressedFastQfilesDir}")

        filesToSearchFor     = f'{CompressedFastQfilesDir}/*{demux.CompressedFastqSuffix}'
        CompressedFastQfiles = glob.glob( filesToSearchFor )            # example: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/sample*fastq.gz

        if not CompressedFastQfiles: # if array is empty
            text = f"\n\nProject {project} does not contain any .fastq.gz entries"
            if demux.debug:
                text = f"{text} | method {inspect.stack()[0][3]}() ]"
            text = f"{text}\n\n"

            demuxFailureLogger.critical( text )
            demuxLogger.critical( text )
            sys.exit( )


        if demux.debug:
            demuxLogger.debug( f"fastq files for {project}:\t\t\t{filesToSearchFor}" )

            for index, item in enumerate( CompressedFastQfiles ):
                demuxLogger.debug( f"CompressedFastQfiles[{index}]:\t\t\t\t{item}" )


        for file in CompressedFastQfiles:
    
            # get the base filename. We picked up sample*.{CompressedFastqSuffix} and we have to rename it to {demux.RunIDShort}sample*.{CompressedFastqSuffix}
            baseFileName = os.path.basename( file )
            if demux.debug:
                demuxLogger.debug( "-----------------")
                demuxLogger.debug( f"baseFilename:\t\t\t\t\t{baseFileName}")

            oldname = f"{file}"
            newname = f"{demux.DemultiplexRunIdDir}/{project}/{demux.RunIDShort}.{baseFileName}"
            newfoo  = f"{demux.DemultiplexRunIdDir}/{demux.RunIDShort}.{project}/{demux.RunIDShort}.{baseFileName}" # saving this var to pass locations of new directories

            if demux.debug:
                demuxLogger.debug( f"file:\t\t\t\t\t\t{file}")
                demuxLogger.debug( f"command to execute:\t\t\t\t/usr/bin/mv {oldname} {newname}\n" )
            
            # make sure oldname files exist
            # make sure newname files do not exist
            oldfileExists = os.path.isfile( oldname )
            newfileExists = os.path.isfile( newname )

            if newfoo not in newProjectFileList:
                newProjectFileList.append( newfoo ) # save it to return the list, so we will not have to recreate the filenames

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

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Copy {demux.SampleSheetFilePath} to {demux.DemultiplexRunIdDir} ==\n", color="red" ) )

    demuxLogger.info( "-----------------")

    return newProjectFileList

########################################################################
# renameFilesAndDirectories( )
########################################################################

def renameFilesAndDirectories( DemultiplexRunIdDir, project_list ):
    """
    Rename any [sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ] files inside 
        {demux.DemultiplexRunIdDir}/{demux.RunIDShort}/[{project_list[0]}, .. , {project_list[n]}] to match the pattern
        {demux.RunIDShort}.[sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ]
    
    Then rename the 
        {demux.DemultiplexRunIdDir}/{demux.RunIDShort}/[{project_list[0]}, .. , {project_list[n]}] to match the pattern
        {demux.DemultiplexRunIdDir}/{demux.RunIDShort}/{demux.RunIDShort}.[{project_list[0]}, .. , {project_list[n]}] to match the pattern
        
    Examples:
    
        DemultiplexRunIdDir: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/
        Sample_Project:      SAV-amplicon-MJH
        demux.RunIDShort:    220314_M06578

        1. Rename the files:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R1_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R1_001.fastq.gz
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R2_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R2_001.fastq.gz

        2. Rename the base directory, for each project:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Renaming started ==", color="green", attrs=["bold"] ) )


    if demux.debug:
        demuxLogger.debug( f"demux.DemultiplexRunIdDir:\t\t\t{demux.DemultiplexRunIdDir}")    # tabulation error
        demuxLogger.debug( f"demux.RunIDShort:\t\t\t\t{demux.RunIDShort}")
        # for index, item in enumerate( project_list ):
        if demux.verbosity == 2:
            demuxLogger.debug( f"project_list:\t\t\t\t{project_list}")

    newProjectFileList = renameFiles( DemultiplexRunIdDir, project_list )
    renameDirectories( project_list )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Renaming started ==", color="red", attrs=["bold"] ) )

    return newProjectFileList


########################################################################
# FastQC
########################################################################

def FastQC( newFileList ):
    """
    FastQC: Run /data/bin/fastqc (which is a symlink to the real qc)
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: FastQC started ==", color="green", attrs=["bold"] ) )

    command             = demux.fastqc_bin
    argv                = [ command, '-t', str(demux.threadsToUse), *newFileList ]  # the * operator on a list/array "splats" (flattens) the values in the array, breaking them down to individual arguemtns
    demultiplexRunIdDir = os.path.dirname( os.path.dirname( newFileList[0] ) )

    if demux.debug:
        arguments = " ".join( argv[1:] )
        demuxLogger.debug( f"Command to execute:\t\t\t\t{command} {arguments}")     # exclude the first element of the array # example for filename: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/
        if demux.verbosity == 2:
            demuxLogger.debug( f"demultiplexRunIdDir:\t\t\t\t{demultiplexRunIdDir}")

    try:
        # EXAMPLE: /usr/local/bin/fastqc -t 4 {demux.DemultiplexRunIdDir}/{project}/*fastq.gz > DemultiplexRunIdDir/demultiplex_log/04_fastqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demultiplexRunIdDir, check = True, encoding = demux.DecodeScheme )
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
    demux.FastQCLogFilePath   = os.path.join( demux.DemultiplexLogDirPath, demux.FastqcLogFileName )  #### FIXME FIXME FIXME ADJUST AND TAKE OUT
    try: 
        fastQCLogFileHandle = open( demux.FastQCLogFilePath, "x" ) # fail if file exists
        if demux.debug:
            demuxLogger.debug( f"FastQCLogFilePath:\t\t\t\t{demux.FastQCLogFilePath}")
        fastQCLogFileHandle.write( result.stdout ) 
        fastQCLogFileHandle.close( )
    except FileNotFoundError as err:
        text = [    f"Error opening FastQCLogFilePath {oldname}:", 
                    f"FastQCLogFilePath: {demux.FastQCLogFilePath} does not exist",
                    f"err.filename:  {err.filename}",
                    f"Exiting!"
                ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: FastQC complete ==\n", color="red", attrs=["bold"] )  )



########################################################################
# prepareMultiQC
########################################################################

def prepareMultiQC( project_list ):
    """
    Preperation to run MultiQC:
        copy *.zip and *.html from individual {demux.DemultiplexRunIdDir}/{demux.RunIDShort}.{project} directories to the {DemultiplexRunIdDirNewNamel}/{demux.RunIDShort}_QC directory
  
    INPUT
        the renamed project list
            does not include demux.TestProject
            deos nto include any demux.ControlProjects

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for MultiQC started ==", color="green", attrs=["bold"] ) )

    zipFiles    = [ ]
    HTMLfiles   = [ ]
    sourcefiles = [ ]
    for project in project_list:
        project_directory = f"{demux.DemultiplexRunIdDir}/{demux.RunIDShort}.{project}"
        zipFiles  = glob.glob( f"{project_directory}/*zip" )    # source zip files
        HTMLfiles = glob.glob( f"{project_directory}/*html" )   # source html files

        if ( not zipFiles[0] or not HTMLfiles[0] ):
            demuxLogger.critical( f"zipFiles or HTMLfiles in {inspect.stack()[0][3]} came up empty! Please investigate {demux.DemultiplexRunIdDir}. Exiting.")
            sys.exit( )

        if demux.debug:
            demuxLogger.debug( termcolor.colored( f"Now working on project \"{project}\"", color="cyan", attrs=["reverse"] ) )
            demuxLogger.debug( f"zipFiles:\t\t\t\t\t{zipFiles}"                               )
            demuxLogger.debug( f"HTMLfiles:\t\t\t\t\t{HTMLfiles}"                             )


    sys.exit( )


    sourcefiles = [ *zipFiles, *HTMLfiles ]
    demuxLogger.debug( f"sourcefiles:\t\t\t\t\t{sourcefiles}\n\n")
    destination = f"{demux.DemultiplexRunIdDir}/{demux.RunIDShort}{demux.QCSuffix}"     # QC folder eg /data/demultiplex/220603_M06578_0105_000000000-KB7MY_demultiplex/220603_M06578_QC/

    if demux.debug:
            demuxLogger.debug( f"demux.RunIDShort:\t\t\t\t{demux.RunIDShort}"                 )
            demuxLogger.debug( f"project_list:\t\t\t\t\t{project_list}"                       )
            demuxLogger.debug( f"demux.DemultiplexRunIdDir:\t\t\t{demux.DemultiplexRunIdDir}" )
            demuxLogger.debug( f"zipFiles:\t\t\t\t\t{zipFiles}"                               )
            demuxLogger.debug( f"HTMLfiles:\t\t\t\t\t{HTMLfiles}"                             )

    if not os.path.isdir( destination ) :
        text =  f"Directory {destination} does not exist. Please check the logs. You can also just delete {demux.DemultiplexRunIdDir} and try again."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    try:
        # EXAMPLE: /usr/bin/cp project/*zip project_f/*html DemultiplexDir/demux.RunIDShort.short_QC # (destination is a directory)
        demuxLogger.debug( f"source:\t\t\t\t\t{[*sourcefiles]}" )
        for source in [ *sourcefiles ]:
            if demux.debug:
                demuxLogger.debug( f"Command to execute:\t\t\t\t/usr/bin/cp {source} {destination}" )
            shutil.copy2( source, destination )    # destination has to be a directory
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

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for MultiQC finished ==\n", color="red", attrs=["bold"] ) )



########################################################################
# prepareMultiQC
########################################################################

def MultiQC( ):
    """
    Run /data/bin/multiqc against the project list.

    Result are zip files in the individual project directories
    """ 

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: MultiQC started ==", color="green", attrs=["bold"] ) )

    if demux.debug:
        demuxLogger.debug( f"demux.DemultiplexRunIdDir:\t\t\t{demux.DemultiplexRunIdDir}" )

    command = demux.mutliqc_bin
    argv    = [ command, demux.DemultiplexRunIdDir,
               '-o', demux.DemultiplexRunIdDir 
              ]
    args    = " ".join(argv[1:]) # ignore the command part so we can logging.debug this string below, fresh all the time, in case we change tool command name

    if demux.debug:
        demuxLogger.debug( f"Command to execute:\t\t\t\t{command} {args}" )

    try:
        # EXAMPLE: /usr/local/bin/multiqc {demux.DemultiplexRunIdDir} -o {demux.DemultiplexRunIdDir} 2> {demux.DemultiplexRunIdDir}/demultiplex_log/05_multiqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demux.DemultiplexRunIdDir, check = True, encoding = demux.DecodeScheme )
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
    demux.MutliQCLogFilePath  = os.path.join( demux.DemultiplexLogDirPath, demux.MultiqcLogFileName ) ############# FIXME FIXME FIXME FIXME take out
    try: 
        multiQCLogFileHandle      = open( demux.MutliQCLogFilePath, "x" ) # fail if file exists
        if demux.debug:
            demuxLogger.debug( f"MutliQCLogFilePath:\t\t\t\t{demux.MutliQCLogFilePath}")
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


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: MultiQC finished ==\n", color="red", attrs=["bold"] ) )


########################################################################
# qc
########################################################################

def qualityCheck( newFileList, newProjectNameList ):
    """
    Run QC on the sequence run files

        FastQC takes the fastq.gz R1 and R2 of each sample sub-project and performs some Quality Checking on them
            The result of running FastQC is html and .zip files, one for each input fastq.gz file. The .zip file contails a directory with the complete analysis of the sample. The .html file is the entry point for all the stuff in the subdirectory

        MultiQC takes {EXPLAIN INPUT HERE}
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Quality Check started ==", color="green", attrs=["bold"] ) )

    if demux.debug:
        demuxLogger.debug( f"newFileList:\t\t\t\t\t{newFileList}" )
        demuxLogger.debug( f"demux.DemultiplexRunIdDir:\t\t\t{demux.DemultiplexRunIdDir}" )
        demuxLogger.debug( f"newProjectNameList:\t\t\t\t{newProjectNameList}" )

    FastQC( newFileList )
    prepareMultiQC( newProjectNameList )
    MultiQC( )


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Quality Check finished ==\n", color="red", attrs=["bold"] ) )




########################################################################
# calcFileHash
########################################################################

def calcFileHash( DemultiplexRunIdDir ):
    """
    Calculate the md5 sum for files which are meant to be delivered:
        .tar
        .zip
        .fasta.gz

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
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files started ==", color="green", attrs=["bold"] ) )

    if demux.debug:
        demuxLogger.debug( f"for debug puproses, creating empty files {demux.DemultiplexRunIdDir}/foo.tar and {demux.DemultiplexRunIdDir}/bar.zip\n" )
        pathlib.Path( f"{demux.DemultiplexRunIdDir}/{demux.footarfile}" ).touch( )
        pathlib.Path( f"{demux.DemultiplexRunIdDir}/{demux.barzipfile}" ).touch( )


    # build the filetree
    if demux.debug:
        demuxLogger.debug( f'= walk the file tree, {inspect.stack()[0][3]}() ======================')
    for directoryRoot, dirnames, filenames, in os.walk( DemultiplexRunIdDir, followlinks = False ):

        for file in filenames:
            if not any( var in file for var in [ demux.CompressedFastqSuffix, demux.zipSuffix, demux.tarSuffix ] ): # grab only .zip, .fasta.gz and .tar files
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
            if demux.debug:
                demuxLogger.debug( f"md5sum: {md5sum} | sha512sum: {sha512sum} | filepath: {filepath}" )


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

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files finished ==\n", color="red", attrs=["bold"] ) )



#######################################################################
# change_permission
########################################################################

def changePermissions( path ):
    """
    changePermissions: recursively walk down from {directoryRoot} and 
        change the owner to :sambagroup
        if directory
            change permissions to 755
        if file
            change permissions to 644
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Changing Permissions started ==", color="green", attrs=["bold"] ) )

    if demux.debug:
        demuxLogger.debug( termcolor.colored( f"= walk the file tree, {inspect.stack()[0][3]}() ======================", attrs=["bold"] ) )

    for directoryRoot, dirnames, filenames, in os.walk( path, followlinks = False ):
    
        # change ownership and access mode of files
        for file in filenames:
            filepath = os.path.join( directoryRoot, file )
            if demux.debug:
                demuxLogger.debug( filepath )

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
    if demux.debug:
        demuxLogger.debug( termcolor.colored( f"= walk the dir tree, {inspect.stack()[0][3]}() ======================", attrs=["bold"] ) )
    for directoryRoot, dirnames, filenames, in os.walk( path, followlinks = False ):

        for name in dirnames:
            dirpath = os.path.join( directoryRoot, name )

            if demux.debug:
                demuxLogger.debug( dirpath )

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

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Changing Permissions finished ==\n", color="red", attrs=["bold"] ) )



########################################################################
# prepare_delivery
########################################################################

def prepareDelivery( RunID ):
    """
    Prepare the appropiarate tar files for transfer and write the appropirate .md5/.sha512 checksum files
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
        os.mkdir( ForTransferRunIdDir )
        move all the tar files in there
            one directory per project
        calcFileHash( ForTransferRunIdDir ) # use a temp dir to re-use the same function we used earlier, so I will not have to write a new function to do the same thing

    Original commands:
        EXAMPLE: /bin/tar -cvf tar_file -C DemultiplexDir folder 
        EXAMPLE: /bin/md5sum tar_file | sed_command > md5_file
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery started ==", color="green", attrs=["bold"] ) )

    counter = 0

    if demux.debug:
        text = [    f"Current working directory:\t{os.getcwd( )}",
                    f"DemultiplexRunIdDir:\t\t{demux.DemultiplexRunIdDir}",
                    f"ForTransferRunIdDir:\t\t{demux.ForTransferRunIdDir}",
                    f"forTransferQCtarFile:\t{demux.forTransferQCtarFile}",
                    f"Original working directory:\t{ os.getcwd( ) }"
                ]
        '\n'.join( text )
        demuxLogger.debug( text )

    # Switch to the Demultiplex directory we will be archiving
    try:
        os.chdir( demux.DemultiplexRunIdDir )
    except FileNotFoundError:
        text = f"Directory: {demux.DemultiplexRunIdDir} does not exist. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )
    except NotADirectoryError:
        text =  f"{demux.DemultiplexRunIdDir} is not a directory. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )
    except Exception as e:
        text = f"You do not have permissions to change to {demux.DemultiplexRunIdDir}. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    if demux.debug:
        demuxLogger.debug( f"Changed into directory\t{demux.DemultiplexRunIdDir}")

    # Make {demux.ForTransferRunIdDir} directory
    if not os.path.isdir( demux.ForTransferRunIdDir ):
        os.mkdir( demux.ForTransferRunIdDir )
    else:
        text = f"{demux.ForTransferRunIdDir} exists, this is not supposed to exist, please investigate and re-run the demux. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    projectList = os.listdir( "." )                                         # get the contents of the demux.DemultiplexRunIdDir directory

    if demux.debug:
        demuxLogger.debug( f"{demux.DemultiplexRunIdDir} directory contents: {projectList}" ) 


def renameProjects( ):
    projectsToProcess = [ ]
    for project in projectList:                                                 # itterate over said demux.DemultiplexRunIdDirs contents, take only the projects we need

        if any( var in project for var in [ demux.QCSuffix ] ):                     # skip anything that includes '_QC'
            demuxLogger.warning( f"{demux.QCSuffix} directory found in projects. Skipping." )
            continue
        elif any( var in project for var in [ demux.TestProject ] ):                # skip the test project, 'FOO-blahblah-BAR'
            demuxLogger.warning( f"{demux.TestProject} test project directory found in projects. Skipping." )
            continue
        elif any( var in project for var in demux.ControlProjects ):                # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        elif demux.temp in project:                                                 # disregard the temp directory
            demuxLogger.warning( f"{demux.temp} directory found. Skipping." )
            continue
        elif demux.DemultiplexLogDirPath in project: # disregard demultiplex_log
            demuxLogger.warning( f"{demux.DemultiplexLogDirPath} directory found. Skipping." )
            continue

        if any( var in project for var in [ demux.NextSeq, demux.MiSeq ] ):         # Make sure there is a nextseq or misqeq tag, before adding the directory to the newProjectNameList
            if demux.debug:
                demuxLogger.warning( f"Now processing {project} project." )
            projectsToProcess.append( project )

    if demux.debug:
        demuxLogger.debug( f"projectsToProcess:\t\t{ projectsToProcess }" )
        demuxLogger.debug( f"len(projectsToProcess):\t{len( projectsToProcess  )}" )

    for project in projectsToProcess:                                               # create the directories for the individual project e.g. 
                                                                                    # if project is APEC-Seq it will create {demux.ForTransferRunIdDir}/{demux.RunIDShort}.{project}
                                                                                    # /data/demultiplex/220603_M06578_0105_000000000-KB7MY_demultiplex/220603_M06578.APEC-Seq/
        try:
            os.mkdir( f"{demux.ForTransferRunIdDir}/{project}" ) # we save each tar file into its own directory
        except FileExistsError as err:
            text = [
                f"Error while trying to mkdir {demux.ForTransferRunIdDir}/{project}",
                f"Error message: {err}",
                "Exiting."
            ]
            text = '\n'.join( text )
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )


        tarFile = os.path.join( demux.ForTransferRunIdDir, project )
        tarFile = os.path.join( tarFile, f"{project}{demux.tarSuffix}" )
        if demux.debug:
            demuxLogger.debug( f"tarFile:\t\t\t{tarFile}")

        if not os.path.isfile( tarFile ) :
            tarFileHandle = tarfile.open( name = tarFile, mode = "w:" )
        else:
            text = f"{tarFile} exists. Please investigate or delete. Exiting."
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )


        # we iterrate through all the renamed Sample_Project directories and make a single tar file for each directory
        # build the filetree
        if demux.debug:
            demuxLogger.debug( termcolor.colored( f"\n== walk the file tree, {inspect.stack()[0][3]}() , {os.getcwd( )}/{project} ======================", attrs=["bold"] ) )

        counter = counter + 1
        demuxLogger.info( termcolor.colored( f"==> Archiving {project} ({counter} out of { len( projectsToProcess ) } projects ) ==================", color="yellow", attrs=["bold"] ) )
        for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.DemultiplexRunIdDir, project ), followlinks = False ): 
             for file in filenames:
                # add one file at a time so we can give visual feedback to the user that the script is processing files
                # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
                # of output that make users uncomfortable
                filenameToTar = os.path.join( project, file )
                tarFileHandle.add( name = filenameToTar, recursive = False )
                demuxLogger.info( f"filenameToTar:\t\t{filenameToTar}" )

        tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
        demuxLogger.info( termcolor.colored( f'==< Archived {project} ({counter} out of { len( projectsToProcess ) } projects ) ==================\n', color="yellow", attrs=["bold"] ) )
        demux.tarFileStack.append( tarFile ) # add to list of archived tar files, we will use them with lstat later ot see if they pass untarring quality control

    ###########################################################
    #
    #   QC.tar
    #
    ###########################################################
    QCDir           = f"{demux.RunIDShort}{demux.QCSuffix}"
    multiQCDir      = demux.multiqc_data
    if demux.debug:
        text = [
            f"demux.RunIDShort:\t\t{demux.RunIDShort}",
            f"QCDir:\t\t\t{QCDir}",
            f"multiQCDir:\t\t\t{multiQCDir}"
        ]
        '\n'.join( text )
        demuxLogger.debug( text )
    

    ################################################################################
    # What to put inside the QC file: {demux.RunIDShort}_QC and multiqc_data
    ################################################################################
    # {demux.RunIDShort}_QC
    ################################################################################
    if not os.path.isfile( demux.forTransferQCtarFile ):
        tarQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "w:" )
    else:
        text = f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )
    demuxLogger.info( termcolor.colored( f"==> Archiving {QCDir} ==================", color="yellow", attrs=["bold"] ) )
    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.DemultiplexRunIdDir, QCDir ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the Archivinguser that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( QCDir, file )
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            demuxLogger.info( f"filenameToTar:\t\t{filenameToTar}" )

    demuxLogger.info( termcolor.colored( f"==> Archived {QCDir} ==================", color="yellow", attrs=["bold"] ) )
    demux.tarFileStack.append( demux.forTransferQCtarFile ) # list of archived tar files, we will use them with lstat later ot see if they pass untarring quality control

    ################################################################################
    # multiqc_data
    ################################################################################
    demuxLogger.info( termcolor.colored( f"==> Archiving {multiQCDir} ==================", color="yellow", attrs=["bold"] ) )
    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.DemultiplexRunIdDir, multiQCDir ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the user that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( multiQCDir, file )
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            demuxLogger.info( f"filenameToTar:\t\t{filenameToTar}" )

    # both {demux.RunIDShort}_QC and multidata_qc go in the same tar file
    tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
    demuxLogger.info( termcolor.colored( f"==> Archived {multiQCDir} ==================", color="yellow", attrs=["bold"] ) )    


    ###########################################################
    # cleanup
    ###########################################################

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery finished ==\n", color="red", attrs=["bold"] ) )




########################################################################
# Water Control Negative report
########################################################################

def controlProjectsQC ( RunID ):
    """
    This function creeates a report if any water control samples are submitted for sequence ( and subsequently, analysis )

    If there are no water control samples, no report is generated.

    If there are water control samples,
        create the full report ONLY if any amplicons are found
    Otherwise
        just mention in green text that no results are detected (and move on)
    """





########################################################################
# Perform a sha512 comparision
########################################################################

def sha512FileQualityCheck ( RunID ):
    """
    re-perform (quietly) the sha512 calculation and compare that with the result on file for the specific file.
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: sha512 files check started ==", color="green", attrs=["bold"] ) )

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: sha512 files check finished ==", color="red", attrs=["bold"] ) )




########################################################################
# tarFileQualityCheck: verify tar files before upload
########################################################################

def tarFileQualityCheck ( RunID ):
    """
    Perform a final quality check on the tar files before uploading them.

    If there are errors in the untarring or the sha512 check, halt.

    If there are no errors, go ahead with the uploading
    """
    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Tar files quaility check started ==", color="green", attrs=["bold"] ) )

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Tar files quaility check finished ==", color="red", attrs=["bold"] ) )




########################################################################
# script_completion_file
########################################################################

def scriptComplete( DemultiplexRunIdDir ):
    """
    Create the {DemultiplexDir}/{demux.DemultiplexCompleteFile} file to signal that this script has finished
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Finishing up script ==", color="green", attrs=["bold"] ) )

    try:
        file = os.path.join( DemultiplexRunIdDir, demux.DemultiplexCompleteFile )
        pathlib.Path( file ).touch( mode=644, exist_ok=False)
    except Exception as e:
        demuxLogger.critical( f"{file} already exists. Please delete it before running {__file__}.\n")
        sys.exit( )

    demuxLogger.debug( f"DemultiplexCompleteFile {file} created.")
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Finishing up script ==", color="red", attrs=["bold"] ) )



########################################################################
# deliverFilesToVIGASP
########################################################################

def deliverFilesToVIGASP( RunID ):
    """
    Write the uploader file needed to upload the data to VIGASP and then
        upload the relevant files.
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for uploading to VIGASP started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for uploading to VIGASP finished\n")




########################################################################
# deliverFilesToNIRD
########################################################################

def deliverFilesToNIRD( RunID ):
    """
    Make connection to NIRD and upload the data
    """
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for archiving to NIRD started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for archiving to NIRD finished\n")




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
    demuxLogger.info( f"==> {demux.n}/{demux.TotalTasks} tasks: Detecting if new runs exist started\n")


    demuxLogger.info( f"==< {demux.n}/{demux.TotalTasks} tasks: Detecting if new runs exist finished\n")




########################################################################
# setupEventAndLogHandling( )
########################################################################

def setupEventAndLogHandling( ):
    """
    Setup the event and log handling we will be using everywhere
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Set up the Event and Log handling ==\n", color="green", attrs=["bold"] ) )


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

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Set up the Event and Log handling ==\n", color="red", attrs=["bold"] ) )



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
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Copy {demux.SampleSheetFilePath} to {demux.DemultiplexRunIdDir} ==\n", color="green", attrs=["bold"] ) )

    try:
        currentPermissions = stat.S_IMODE(os.lstat( demux.SampleSheetFilePath ).st_mode )
        os.chmod( demux.SampleSheetFilePath, currentPermissions & ~stat.S_IEXEC  ) # demux.SampleSheetFilePath is probably +x, remnant from windows transfer, so remove execute bit
        shutil.copy2( demux.SampleSheetFilePath, demux.DemultiplexRunIdDir )
    except Exception as err:
        text = [    f"Copying {demux/SampleSheetFilePath} to {demux.DemultiplexRunIdDir} failed.",
                    err.tostring( ),
                    "Exiting."
        ]
        '\n'.join( text )
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Copy {demux.SampleSheetFilePath} to {demux.DemultiplexRunIdDir} ==\n", color="red", attrs=["bold"] ) )




########################################################################
# archiveSampleSheet( )
########################################################################

def archiveSampleSheet( RunID ):
    """

    # Request by Cathrine: Copy the SampleSheet file to /data/samplesheet automatically

    Check for validity of the filepath of the sample sheet
    then
        archive a copy
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Archive {demux.SampleSheetFilePath} to {demux.SampleSheetArchiveFilePath} ==\n", color="green", attrs=["bold"] ) )


    if not os.path.exists( demux.SampleSheetFilePath ):
        text = f"{demux.SampleSheetFilePath} does not exist! Demultiplexing cannot continue. Exiting."
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )


    if not os.path.isfile( demux.SampleSheetFilePath ):
        text = f"{demux.SampleSheetFilePath} is not a file! Exiting."
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    try:
        shutil.copy2( demux.SampleSheetFilePath, demux.SampleSheetArchiveFilePath )
        currentPermissions = stat.S_IMODE(os.lstat( demux.SampleSheetArchiveFilePath ).st_mode )
        os.chmod( demux.SampleSheetArchiveFilePath, stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH ) # Set samplesheet to "o=rw,g=r,o=r"
    except Exception as err:
        frameinfo = getframeinfo( currentframe( ) )
        text = [    f"Archiving {demux.SampleSheetFilePath} to {demux.SampleSheetArchiveFilePath} failed.",
                    str(err),
                    f" at {frameinfo.filename}:{frameinfo.lineno}."
                    "Exiting.",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks:  Archive {demux.SampleSheetFilePath} to {demux.SampleSheetArchiveFilePath} ==\n", color="red", attrs=["bold"] ) )




########################################################################
# setupFileLogHandling( )
########################################################################

def setupFileLogHandling( RunID ):
    """
    Setup the file event and log handling
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Setup the file event and log handling ==\n", color="green", attrs=["bold"] ) )

    # make sure that the /data/log directory exists.
    if not os.path.isdir( demux.LogDirPath ) :
        text = [    "Trying to setup demux.LogDirPath failed. Reason:\n",
                    "The parts of demux.LogDirPath have the following values:\n",
                    f"demux.LogDirPath:\t\t\t\t{demux.LogDirPath}\n"
                    f"demux.DataRootDirPath:\t\t\t{demux.DataRootDirPath}\n",
                    f"demux.LogDirName:\t\t\t{demux.LogDirName}\n",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    # # set up logging for /data/log/{RunID}.log
    try: 
        demuxFileLogHandler   = logging.FileHandler( demux.DemuxRunLogFilePath, mode = 'w', encoding = demux.DecodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxFileLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.DemuxRunLogFilePath have the following values:\n",
                    f"demux.DemuxRunLogFilePath:\t\t\t{demux.DemuxRunLogFilePath}\n",
                    f"RunID + demux.LogSuffix:\t\t\t{RunID} + {demux.LogSuffix}\n",
                    f"demux.LogDirPath:\t\t\t\t{demux.LogDirPath}\n"
        ]
        demuxFailureLogger.critical( *text  )
        demuxLogger.critical( *text )
        logging.shutdown( )
        sys.exit( )

    demuxLogFormatter      = logging.Formatter( "%(asctime)s %(dns)s %(filename)s %(levelname)s %(message)s", datefmt = '%Y-%m-%d %H:%M:%S', defaults = { "dns": socket.gethostname( ) } )
    demuxFileLogHandler.setFormatter( demuxLogFormatter )
    demuxLogger.setLevel( demux.LoggingLevel )

    # set up cummulative logging in /data/log/demultiplex.log
    try:
        demuxFileCumulativeLogHandler   = logging.FileHandler( demux.DemuxCumulativeLogFilePath, mode = 'a', encoding = demux.DecodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxFileCumulativeLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.DemuxRunLogFilePath have the following values:\n",
                    f"demux.DemuxCumulativeLogFilePath:\t\t\t{demux.DemuxCumulativeLogFilePath}\n",
                    f"demux.LogDirPath:\t\t\t\t\t{demux.LogDirPath}\n",
                    f"demux.DemultiplexLogDirName:\t\t\t{demux.DemultiplexLogDirName}\n",
        ]
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxFileCumulativeLogHandler.setFormatter( demuxLogFormatter )

    # setup logging for /data/bin/demultiplex/RunID/demultiplex_log/00_script.log
    try:
        demuxScriptLogHandler   = logging.FileHandler( demux.DemultiplexScriptLogFilePath, mode = 'w', encoding = demux.DecodeScheme )
    except Exception as err:
        text = [    "Trying to setup demuxScriptLogHandler failed. Reason:\n",
                    str(err),
                    "The parts of demux.DemultiplexScriptLogFilePath have the following values:\n",
                    f"demux.DemultiplexScriptLogFilePath:\t\t\t{demux.DemultiplexScriptLogFilePath}\n",
                    f"demux.DemultiplexLogDirPath\t\t\t\t{demux.DemultiplexLogDirPath}\n",
                    f"demux.ScriptRunLogFileName:\t\t\t\t{demux.ScriptRunLogFileName}\n",
                    f"demux.DemultiplexRunIdDir:\t\t\t\t{demux.DemultiplexRunIdDir}\n",
                    f"demux.DemultiplexLogDirName:\t\t\t\t{demux.DemultiplexLogDirName}\n",
                    f"demux.DemultiplexDir:\t\t\t\t\t{demux.DemultiplexDir}\n",
                    f"RunID + demux.DemultiplexDirSuffix:\t{RunID} + {demux.DemultiplexDirSuffix}\n",
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

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Setup the file event and log handling ==\n", color="red", attrs=["bold"] ) )



########################################################################
# checkRunningEnvironment( )
########################################################################

def checkRunningEnvironment( RunID ):
    """
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Check the validity of the current running environment ==\n", color="green", attrs=["bold"] ) )

    if len( demux.project_list ) == 0:
        text = "List project_list contains no projects/zero length! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )
    elif demux.debug and len( demux.project_list ) == 1: 
        demux.project_list.add( demux.TestProject )               # if debug, have at least two project names to ensure multiple paths are being created

    for project in demux.project_list:                            # build the full list of subdirectories to make under {demux.DemultiplexRunIdDir}
        demux.DemultiplexProjSubDirs.append( f"{demux.DemultiplexRunIdDir}/{demux.RunIDShort}.{project}" )

    # Build the directory paths inside the /data/for_transfer/RunID for each of the projects. example: /data/for_transfer/{RunID}_demultiplext/{demux.RunIDShort}.{project}
    for project in demux.project_list: 
        demux.ForTransferProjNames.append( f"{demux.DemultiplexRunIdDir}/{demux.RunIDShort}.{project}" )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Check the validity of the current running environment ==\n", color="red", attrs=["bold"] ) )



########################################################################
# printRunningEnvironment( )
########################################################################

def printRunningEnvironment( RunID ):
    """
    Print our running environment
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Print out the current running environment ==\n", color="green", attrs=["bold"] ) )


    demuxLogger.info( f"To rerun this script run\n" )
    demuxLogger.info( termcolor.colored( f"\tclear; rm -rf {demux.DemultiplexRunIdDir} && rm -rf {demux.ForTransferRunIdDir} && /usr/bin/python3 /data/bin/demultiplex_script.py {RunID}\n\n", attrs=["bold"] ) )
    if demux.debug: # logging.info the values here # FIXME https://docs.python.org/3/tutorial/inputoutput.html "Column output in Python3"
        demuxLogger.debug( "=============================================================================")
        demuxLogger.debug( f"RunID:\t\t\t\t\t\t{RunID}")
        demuxLogger.debug( f"demux.RunIDShort:\t\t\t\t{demux.RunIDShort}")
        demuxLogger.debug( f"project_list:\t\t\t\t\t{demux.project_list}")
        demuxLogger.debug( "=============================================================================")
        demuxLogger.debug( f"RawDataDir:\t\t\t\t\t{demux.RawDataDir}" )
        demuxLogger.debug( f"RawDataRunIDdir:\t\t\t\t{demux.RawDataRunIDdir}" )
        demuxLogger.debug( f"SampleSheetFilePath:\t\t\t\t{demux.SampleSheetFilePath}" )
        demuxLogger.debug( f"RTACompleteFilePath:\t\t\t\t{demux.RawDataRunIDdir}/{demux.RTACompleteFile}" )
        demuxLogger.debug( "=============================================================================")
        demuxLogger.debug( f"DemultiplexDirRoot:\t\t\t\t{demux.DemultiplexDir}" )
        demuxLogger.debug( f"DemultiplexRunIdDir:\t\t\t\t{demux.DemultiplexRunIdDir}" )
        demuxLogger.debug( f"DemultiplexLogDirPath:\t\t\t\t{demux.DemultiplexLogDirPath}" )
        demuxLogger.debug( f"DemuxRunLogFilePath:\t\t\t\t{demux.DemuxRunLogFilePath}" )
        demuxLogger.debug( f"DemultiplexScriptLogFilePath:\t\t\t{demux.DemultiplexScriptLogFilePath}" )
        demuxLogger.debug( f"DemultiplexQCDirPath:\t\t\t\t{demux.DemultiplexQCDirPath}" )
        for index, project in enumerate( demux.DemultiplexProjSubDirs):
            demuxLogger.debug( f"DemultiplexProjSubDirs[{index}]:\t\t\t{project}")
        demuxLogger.debug( "=============================================================================")
        demuxLogger.debug( f"ForTransferDir:\t\t\t\t\t{demux.ForTransferDir}" )
        demuxLogger.debug( f"ForTransferRunIdDir:\t\t\t\t{demux.ForTransferRunIdDir}" )
        for index, project in enumerate( demux.ForTransferProjNames):
            demuxLogger.debug( f"ForTransferProjNames[{index}]:\t\t\t\t{project}")
        demuxLogger.debug( "=============================================================================\n")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Print out the current running environment ==\n", color="red", attrs=["bold"] ) )
    # sys.exit( )





########################################################################
# setupEnvironment( )
########################################################################

def setupEnvironment( RunID ):
    """
    Setup the variables for our environment
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Set up the current running environment ==\n", color="green", attrs=["bold"] ) )

    # RunID
    demux.RunIDShort                    = '_'.join(RunID.split('_')[0:2]) # this should be turned into a setter in the demux object
######################################################
    demux.RawDataRunIDdir               = os.path.join( demux.RawDataDir, RunID )
    demux.SampleSheetFilePath           = os.path.join( demux.RawDataRunIDdir, demux.SampleSheetFileName )
    demux.RTACompleteFilePath           = f"{demux.RawDataRunIDdir}/{demux.RTACompleteFile}"
######################################################
    demux.DemultiplexRunIdDir           = os.path.join( demux.DemultiplexDir, RunID + demux.DemultiplexDirSuffix ) 
    demux.DemultiplexQCDirPath          = f"{demux.DemultiplexRunIdDir}/{demux.RunIDShort}{demux.QCSuffix}"
######################################################
    demux.ForTransferRunIdDir           = os.path.join( demux.ForTransferDir, RunID )
    demux.ForTransferQCtarFile          = os.path.join( demux.ForTransferRunIdDir, f"{RunID}{demux.QCSuffix}{demux.tarSuffix}" )
######################################################

######################################################
    # set up
    demux.DemuxRunLogFilePath          = os.path.join( demux.LogDirPath,            RunID + demux.LogSuffix )
    demux.DemuxCumulativeLogFilePath   = os.path.join( demux.LogDirPath,            demux.DemuxCumulativeLogFileName )
    demux.DemultiplexLogDirPath        = os.path.join( demux.DemultiplexRunIdDir,   demux.DemultiplexLogDirName )
    demux.DemultiplexScriptLogFilePath = os.path.join( demux.DemultiplexLogDirPath, demux.ScriptRunLogFileName )
    demux.DemuxBcl2FastqLogFilePath    = os.path.join( demux.DemultiplexLogDirPath, demux.Bcl2FastqLogFileName )
    demux.FastQCLogFilePath            = os.path.join( demux.DemultiplexLogDirPath, demux.FastqcLogFileName )
    demux.MutliQCLogFilePath           = os.path.join( demux.DemultiplexLogDirPath, demux.MultiqcLogFileName )
    demux.SampleSheetArchiveFilePath   = os.path.join( demux.SampleSheetDirPath, f"{RunID}{demux.CSVSuffix}" ) # .dot is included in CSVsuffix

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Set up the current running environment ==\n", color="red", attrs=["bold"] ) )




########################################################################
# checkRunningDirectoryStructure( )
########################################################################

def checkRunningDirectoryStructure( RunID ):
    """
    Check if the runtime directory structure is ready for processing
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Check if the runtime directory structure is ready for processing ==\n", color="green", attrs=["bold"] ) )

    # init:

    #   check if sequencing run has completed, exit if not
    #       Completion of sequencing run is signaled by the existance of the file {RTACompleteFilePath} ( {SequenceRunOriginDir}/{demux.RTACompleteFile} )
    if not os.path.isfile( f"{RTACompleteFilePath}" ):
        text = f"{RunID} is not finished sequencing yet!"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    #   check if {DemultiplexDirRoot} exists
    #       exit if not
    if not os.path.exists( DemultiplexDirRoot ):
        text = f"{DemultiplexDirRoot} is not present, please use the provided ansible file to create the root directory hierarchy"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    if not os.path.isdir( DemultiplexDirRoot ):
        text = f"{DemultiplexDirRoot} is not a directory! Cannot stored demultiplex data in a non-directory structure! Exiting." 
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )
    if os.path.exists( demux.DemultiplexRunIdDir ):
        text = f"{demux.DemultiplexRunIdDir} exists. Delete the demultiplex folder before re-running the script"
        demuxFailureLogger.critical( text  )
        demuxLogger.critical( text )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Check if the runtime directory structure is ready for processing ==\n", color="red" ) )



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
    #   create {DemultiplexDirRoot} directory structrure
    createDemultiplexDirectoryStructure( demux.DemultiplexRunIdDir )                                    # create the directory structure under {demux.DemultiplexRunIdDir}

    # #################### demux.getProjectName( ) needs to be called before we start logging  ##########################################################
    demux.getProjectName( )                                                                             # get the list of projects in this current run
    # renameProjectListAccordingToAgreedPatttern( )                                                     # rename the contents of the project_list according to {RunIDShort}.{project}
    # #################### createDemultiplexDirectoryStructure( ) needs to be called before we start logging  ###########################################
    setupFileLogHandling( RunID )                                                                       # setup the file event and log handing, which we left out
    printRunningEnvironment( RunID )                                                                    # print our running environment
    checkRunningEnvironment( RunID )                                                                    # check our running environment
    copySampleSheetIntoDemultiplexRunIdDir( )                                                           # copy SampleSheet.csv from {demux.SampleSheetFilePath} to {demux.DemultiplexRunIdDir}
    archiveSampleSheet( RunID )                                                                         # make a copy of the Sample Sheet for future reference
    demultiplex( )                                                                                      # use blc2fastq to convert .bcl files to fastq.gz
    newFileList = renameFilesAndDirectories( demux.DemultiplexRunIdDir, demux.project_list )            # rename the *.fastq.gz files and the directory project to comply to the {RunIDShort}.{project} convention
    qualityCheck( newFileList, project_list )                                                           # execute QC on the incoming fastq files

    calcFileHash( demux.DemultiplexRunIdDir )                                                           # create .md5/.sha512 checksum files for every .fastqc.gz/.tar/.zip file under DemultiplexRunIdDir
    changePermissions( demux.DemultiplexRunIdDir  )                                                     # change permissions for the files about to be included in the tar files 
    prepareDelivery( RunID )                                                                            # prepare the delivery files
    calcFileHash( demux.ForTransferRunIdDir )                                                           # create .md5/.sha512 checksum files for the delivery .fastqc.gz/.tar/.zip files under DemultiplexRunIdDir, 2nd fime for the new .tar files created by prepareDelivery( )
    changePermissions( demux.ForTransferRunIdDir  )                                                     # change permissions for all the delivery files, including QC
    controlProjectsQC ( RunID )                                                                         # check to see if we need to create the report for any control projects present
    tarFileQualityCheck( RunID )                                                                        # QC for tarfiles: can we untar them? does untarring them keep match the sha512 written? have they been tampered with while in storage?
    deliverFilesToVIGASP( RunID )                                                                       # Deliver the output files to VIGASP
    deliverFilesToNIRD( RunID )                                                                         # deliver the output files to NIRD
    scriptComplete( demux.DemultiplexRunIdDir )                                                         # mark the script as complete
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
