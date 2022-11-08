#!/bin/env /bin/python3

import os
import sys
import shutil
import subprocess
import argparse
import glob
import inspect
import stat
import hashlib
import pathlib
import ast
import tarfile
import termcolor


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
    The QC tar file contains all the files under the {RunIDShort}_QC and multiqc_data directories 
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


New Features Requests: 
    log to syslog
    log to file
    When turned into an object, this program should detect if it has a RunID argument and demultiplex that only
    If there are no arguments, the program should detect how many new runs are there
    turn into daemon
        being able to query status via api:
            demultiplexted
            rawdata
            completed
            how many in Que
            RecentNewOnes
    Loop detection: if over the same run three times but no banana, send notificaiotn
        tighter in-between runs time requirement: not ever half an hour, but ever 10 minutes
    The ability to check if demux is happening already
        that way we can limit how simmultansious demultiplexing scripts can run
        and limit resource usage
    SampleSheet.csv validation
        Check for commas == specific number ( ex: There are too many commas between ‘A1’ and ‘RRBS-NMBU’ )
        Check for missing commas: state machine and report if state N is missing comma after transitioning to N+1 state ( ex: a comma was missing between ’Sample1’ and ‘LPRSSBASNMBU1 )

"""


class demux:
    """
    demux: make an object of the entire demultiplex process.
    """

    ######################################################
    debug = True
    ######################################################
    DataRootDirPath         = '/data'
    RawDataDirName          = 'rawdata'
    RawDataDir              =  os.path.join( DataRootDirPath, RawDataDirName )
    DemultiplexDirName      = "demultiplex"
    DemultiplexDir          = os.path.join( DataRootDirPath, DemultiplexDirName )
    ForTransferDirName      = 'for_transfer'
    ForTransferDir          = os.path.join( DataRootDirPath, ForTransferDirName )
    logfileLocation         = 'bin/cron_out.log'
    SampleSheetDirName      = 'SampleSheets'
    SampleSheetDirPath      = os.path.join( DataRootDirPath, SampleSheetDirName )
    ######################################################
    DemultiplexDirSuffix    = '_demultiplex'
    DemultiplexLogDirName   = 'demultiplex_log'
    multiqc_data            = 'multiqc_data'
    fastqcLogFileName       = '03_fastqcLogFile.log'
    multiqcLogFileName      = '04_multiqcLogFile.log'
    SampleSheetFileName     = 'SampleSheet.csv'
    RTACompleteFile         = 'RTAComplete.txt'
    temp                    = 'temp'
    ScriptLogFile           = 'script.log'
    QCSuffix                = '_QC'
    tarSuffix               = '.tar'
    md5Suffix               = '.md5'
    sha512Suffix            = '.sha512'
    zipSuffix               = '.zip'
    CompressedFastqSuffix   = '.fastq.gz' 
    CSVSuffix               = '.csv'
    htmlSuffix              = '.html'
    ######################################################
    bcl2fastq_bin           = f"{DataRootDirPath}/bin/bcl2fastq"
    fastqc_bin              = f"{DataRootDirPath}/bin/fastqc"
    mutliqc_bin             = f"{DataRootDirPath}/bin/multiqc"
    python3_bin             = f"/usr/bin/python3"
    group                   = 'sambagroup'
    ScriptFilePath          = __file__
    ######################################################
    ForTransferRunIdDir     = ""
    forTransferQCtarFile    = ""
    ######################################################
    TestProject             = 'FOO-blahblah-BAR'
    Sample_Project          = 'Sample_Project'
    Bcl2FastqLogFileName    = '02_demultiplex.log'
    DemultiplexCompleteFile = 'DemultiplexComplete.txt'
    md5File                 = 'md5sum.txt'
    MiSeq                   = 'M06578'   # if we get more than one, turn this into an array
    NextSeq                 = 'NB552450' # if we get more than one, turn this into an array
    logfileLocation         = 'bin/cron_out.log'
    DecodeScheme            = "utf-8"
    footarfile              = f"foo{tarSuffix}"      # class variable shared by all instances
    barzipfile              = f"zip{zipSuffix}"
    TotalTasks              = 0  
    ######################################################
    DemultiplexRunIdDir     = ""
    DemultiplexLogDirPath   = ""
    DemultiplexLogFilePath  = ""
    DemuxQCDirectoryPath    = ""
    DemuxQCDirectoryName    = ""
    DemuxQCDirectoryPath    = ""
    ######################################################
    ForTransferRunIdDir     = ""
    forTransferQCtarFile    = ""
    ######################################################
    multiQCLogFilePath      = ""
    ######################################################
    fastQCLogFilePath       = ""
    ######################################################
    with open( __file__ ) as f:     # little trick from openstack: read the current script and count the functions and initialize TotalTasks to it
        tree = ast.parse( f.read( ) )
        TotalTasks = sum( isinstance( exp, ast.FunctionDef ) for exp in tree.body ) + 2
    n                       = 0 # counter for current task



    def __init__( self, RunID ):
        """
        __init__
            Check for existance of RunID
                Complain if not
            Checks to see if debug or not is set
        """
        self.RunID = RunID # variables in __init___ are unique to each instance
        self.debug = True


    def writeVigasFile( ):
        """
        Write the file for the uploading of files to VIGASP
        """

        demux.n = demux.n + 1
        print( f"{demux.n}/{demux.TotalTasks} tasks: writing VIGASP uploadder file started\n")


        print( f"{demux.n}/{demux.TotalTasks} tasks: writing VIGASP uploadder file finished\n")



    ########################################################################
    # getProjectName
    ########################################################################
    def getProjectName( SampleSheetFilePath ):
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
        print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Get project name from {SampleSheetFilePath} started ==\n", color="green", attrs=["bold"] ) )

        project_line_check = False
        project_index  = 0
        # analysis_index = ''
        project_list   = []

        for line in open( SampleSheetFilePath, 'r', encoding= demux.DecodeScheme ):
            line = line.rstrip()
            item = line.split(',')[project_index]
            if project_line_check == True and item not in project_list :
                project_list.append( item )# + '.' + line.split(',')[analysis_index]) # this is the part where .x shows up. Removed.
            if demux.Sample_Project in line: # Sample_Project reflects the string it is assigned. Do not change.
                project_index      = line.split(',').index( demux.Sample_Project )
                project_line_check = True

        print( f"project_list: {project_list}\n" )


        print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Get project name from {SampleSheetFilePath} finished ==\n", color="red", attrs=["bold"] ) )
        return( set( project_list ) )

    def checkTarFiles ( listOfTarFilesToCheck ):
        """
        Check to see if the tar files created for delivery can be listed with no errors
        use
            TarFile.list(verbose=True, *, members=None)
                    Print a table of contents to sys.stdout. If verbose is False, only the names of the members are printed. If it is True, output similar to that of ls -l is produced. If optional members is given, it must be a subset of the list returned by getmembers(). 

            https://docs.python.org/3/library/tarfile.html

        But do it quietly, no need for output other than an OK/FAIL
        """




########################################################################
# createDirectory
########################################################################

def createDemultiplexDirectoryStructure( DemultiplexRunIdDir, RunIDShort, project_list ):
    """
    If the Demultiplexing directory or any relevant directory does not exist, create it
        RunIDShort format is in the pattern of (date +%y%m%d)_SEQUENCERSERIALNUMBER Example: 220314_M06578
        {DemultiplexDirRoot} == "/data/demultiplex" # default

        {DemultiplexDirRoot}/{RunID}_{DemultiplexDirSuffix}/
        {DemultiplexDirRoot}/{RunID}_{DemultiplexDirSuffix}/{RunIDShort}.project_list[0]
        {DemultiplexDirRoot}/{RunID}_{DemultiplexDirSuffix}/{RunIDShort}.project_list[1]
        .
        .
        .
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/{RunIDShort}.project_list[ len(project_list) -1 ]
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/{DemultiplexLogDir}
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/{RunIDShort}{demux.QCSuffix}
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/Reports      # created by bcl2fastq
        {DemultiplexDirRoot}{RunID}_{DemultiplexDirSuffix}/Stats        # created by bcl2fastq
    """

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Create directory structure started ==", color="green", attrs=["bold"] ) )

    demux.DemultiplexLogDirPath = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDirName ) 
    demux.DemuxQCDirectoryName  = f"{RunIDShort}{demux.QCSuffix}" # QCSuffix is defined in object demux
    demux.DemuxQCDirectoryPath  = os.path.join( DemultiplexRunIdDir, demux.DemuxQCDirectoryName  )

    if demux.debug:
            print( f"DemultiplexRunIdDir\t\t\t\t{demux.DemultiplexRunIdDir}" )
            print( f"DemultiplexRunIdDir/DemultiplexLogDir:\t\t{demux.DemultiplexLogDirPath}" )
            print( f"DemultiplexRunIdDir/DemuxQCDirectory:\t\t{demux.DemuxQCDirectoryPath}" )

    os.mkdir( demux.DemultiplexRunIdDir )   # root directory for run
    os.mkdir( demux.DemultiplexLogDirPath ) # log directory for run
    os.mkdir( demux.DemuxQCDirectoryPath )  # QC directory  for run

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Create directory structure finished ==\n", color="red", attrs=["bold"] ) )



########################################################################
# demultiplex
########################################################################

# def demultiplex( SequenceRunOriginDir, DemultiplexDir, demultiplex_out_file):
def demultiplex( SequenceRunOriginDir, DemultiplexRunIdDir ):
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

    CAREFUL: if you run blc2fastq with only --runfolder-dir {SequenceRunOriginDir} , bcl2fastq will create all the files within the {SequenceRunOriginDir} rawdata directory

    """

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Demultiplexing started ==\n", color="green", attrs=["bold"] ) )

    argv = [ demux.bcl2fastq_bin,
         "--no-lane-splitting",
         "--runfolder-dir",
        f"{SequenceRunOriginDir}",
         "--output-dir",
        f"{demux.DemultiplexRunIdDir}"
    ]
    Bcl2FastqLogFile     = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDirPath, demux.Bcl2FastqLogFileName )
    if demux.debug:
        print( f"Command to execute:\t\t\t\t" + " ".join( argv ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + SequenceRunOriginDir + ' --output-dir ' + DemultiplexDir + ' 2> ' + DemultiplexDir + '/demultiplex_log/02_demultiplex.log'
        result =  subprocess.run( argv, capture_output = True, cwd = SequenceRunOriginDir, check = True, encoding = demux.DecodeScheme )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
            f"Command: {err.cmd}", # interpolated strings
            f"Return code: {err.returncode}"
            f"Process output: {err.stdout}",
            f"Process error:  {err.stderr}"
        ]
        print( '\n'.join( text ) )

    file = open( Bcl2FastqLogFile, "w" )
    file.write( result.stderr )
    file.close( )

    if demux.debug:
        if not os.path.isfile( Bcl2FastqLogFile ):
            print( f"{Bcl2FastqLogFile} did not get written to disk. Exiting.")
            sys.exit( )
        else:
            filesize = os.path.getsize( Bcl2FastqLogFile )
            print( f"Bcl2FastqLogFile:\t\t\t\t{Bcl2FastqLogFile} is {filesize} bytes.\n")

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Demultiplexing finished ==\n", color="red", attrs=["bold"] ) )


########################################################################
# renameFiles( )
########################################################################

def renameFiles( DemultiplexRunIdDir, RunIDShort, project_list ):
    """
    Rename any [sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ] files inside 
        {demux.DemultiplexRunIdDir}/{RunIDShort}[{project_list[0]}, .. , {project_list[n]}] to match the pattern
        {RunIDShort}.[sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ]

    Examples:
    
        DemultiplexRunIdDir: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/
        Sample_Project:      SAV-amplicon-MJH
        RunIDShort:          220314_M06578

        1. Rename the files:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R1_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R1_001.fastq.gz
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R2_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R2_001.fastq.gz

        2. Rename the base directory, for each project:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH

    """

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Renaming files started ==", color="green", attrs=["bold"] ) )

    oldname            = ""
    newname            = ""
    newProjectFileList = [ ]

    if demux.debug:
        print( f"DemultiplexRunIdDir:\t\t\t\t{demux.DemultiplexRunIdDir}")
        print( f"RunIDShort:\t\t\t\t\t{RunIDShort}")
        # for index, item in enumerate( project_list ):
        print( f"project_list:\t\t\t\t\t{project_list}")

    for project in project_list: # rename files in each project directory

        if project == demux.TestProject:
            if demux.debug:
                print( f"Test project '{demux.TestProject}' detected. Skipping." )
                continue

        CompressedFastQfilesDir = f"{demux.DemultiplexRunIdDir}/{project}"
        if demux.debug:
            print( f"CompressedFastQfilesDir:\t\t\t{CompressedFastQfilesDir}")

        filesToSearchFor     = f'{CompressedFastQfilesDir}/*{demux.CompressedFastqSuffix}'
        CompressedFastQfiles = glob.glob( filesToSearchFor ) # example: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/sample*fastq.gz

        if demux.debug:
            if len( f"fastq files for {project}:" ) > 30:
                print( f"fastq files for {project}:\t\t{filesToSearchFor}" )
            else:
                print( f"fastq files for {project}:\t\t\t{filesToSearchFor}" )

            for index, item in enumerate( CompressedFastQfiles ):
                print( f"CompressedFastQfiles[{index}]:\t\t\t{item}" )

        if not CompressedFastQfiles: # if array is empty
            print( f"CompressedFastQfiles var is empty in method {inspect.stack()[0][3]}(). Exiting. ")
            sys.exit( )

        for file in CompressedFastQfiles:
    
            # get the base filename. We picked up sample*.{CompressedFastqSuffix} and we have to rename it to {RunIDShort}sample*.{CompressedFastqSuffix}
            baseFileName = os.path.basename( file )
            if demux.debug:
                print( "-----------------")
                print( f"baseFilename:\t\t\t\t\t{baseFileName}")

            oldname = f"{file}"
            newname = f"{demux.DemultiplexRunIdDir}/{project}/{RunIDShort}.{baseFileName}"
            newfoo  = f"{demux.DemultiplexRunIdDir}/{RunIDShort}.{project}/{RunIDShort}.{baseFileName}" # saving this var to pass locations of new directories

            if demux.debug:
                print( f"file:\t\t\t\t\t\t{file}")
                print( f"command to execute:\t\t\t\t/usr/bin/mv {oldname} {newname}" )
            
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
                    print( f"Error during renaming {oldname}:")
                    print( f"oldname: {oldname}\noldfileExists: {oldfileExists}" )
                    print( f"newname: {newname}\nnewfileExists: {newfileExists}" )
                    print( "err.filename:  {err.filename}" )
                    print( "err.filename2: {err.filename2}" )
                    print( "Exiting!" )

    print( "-----------------")

    DemultiplexRunIdDirNewNameList = [ ]
    for project in project_list: # rename the project directories

        oldname = f"{demux.DemultiplexRunIdDir}/{project}"
        newname = f"{demux.DemultiplexRunIdDir}/{RunIDShort}.{project}"
        # make sure oldname dir exists
        # make sure newname dir name does not exist
        olddirExists = os.path.isdir( oldname )
        newdirExists = os.path.isdir( newname )

        if olddirExists and not newdirExists: # rename directory

            try: 
                DemultiplexRunIdDirNewNameList.append( newname ) # EXAMPLE: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH
                os.rename( oldname, newname )
            except FileNotFoundError as err:
                print( f"Error during renaming {oldname}:")
                print( f"oldname: {oldname}\noldfileExists: {oldfileExists}" )
                print( f"newfile: {newname}\nnewfileExists: {newfileExists}" )
                print( "err.filename:  {err.filename}")
                print( "err.filename2: {err.filename2}")
                print( "Exiting!")

            if demux.debug:
                print( termcolor.colored( f"Renaming {oldname} to {newname}", color="cyan", attrs=["reverse"] ) )
                for index, item in enumerate( newProjectFileList ):
                    if index < 10:
                        print( f"newProjectFileList[{index}]:\t\t\t\t{item}") # make sure the debugging output is all lined up.
                    elif 100 < index  and index >= 10:
                        print( f"newProjectFileList[{index}]:\t\t\t{item}")
                    elif 1000 < index and index >= 100:
                        print( f"newProjectFileList[{index}]:\t\t{item}")
                    else:
                        print( f"newProjectFileList[{index}]:\t{item}")       # if we got more than 1000 files, well, frak me...  ## NOTE THIS IS AN INTERESTING STATISTIC: HOW MANY FILES PRODUCED (MEAN, AVERAGE) FOR EACH RUN 

                for index, item in enumerate( DemultiplexRunIdDirNewNameList ):
                    print( f"DemultiplexRunIdDirNewNameList[{index}]:\t\t{item}")

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Renaming files finished ==\n", color="red", attrs=["bold"] ) )

    return newProjectFileList, DemultiplexRunIdDirNewNameList


########################################################################
# FastQC
########################################################################

def FastQC( newFileList ):
    """
    FastQC: Run /data/bin/fastqc (which is a symlink to the real qc)
    """

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: FastQC started ==", color="green", attrs=["bold"] ) )

    command             = demux.fastqc_bin
    argv                = [ command, '-t', '4', *newFileList ] # the * operator on a list/array "splats" (flattens) the values in the array, breaking them down to individual arguemtns
    demultiplexRunIdDir = os.path.dirname( os.path.dirname( newFileList[0] ) )

    if demux.debug:
        print( f"argv:\t\t\t\t\t\t{argv}")
        arguments = " ".join( argv[1:] )
        print( f"Command to execute:\t\t\t\t{command} {arguments}") # exclude the first element of the array # example for filename: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/
        print( f"demultiplexRunIdDir:\t\t\t\t{demultiplexRunIdDir}")

    try:
        # EXAMPLE: /usr/local/bin/fastqc -t 4 {demux.DemultiplexRunIdDir}/{project}/*fastq.gz > DemultiplexRunIdDir/demultiplex_log/04_fastqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demultiplexRunIdDir, check = True, encoding = demux.DecodeScheme )
    except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: {err.cmd}", # interpolated strings
                     f"Return code: {err.returncode}"
                     f"Process output: {err.output}",
            ]

    # log FastQC output
    demux.fastQCLogFilePath   = os.path.join( demux.DemultiplexLogDirPath, demux.fastqcLogFileName )
    fastQCLogFileHandle = open( demux.fastQCLogFilePath, "x" ) # fail if file exists
    if demux.debug:
        print( f"fastQCLogFilePath:\t\t\t\t{demux.fastQCLogFilePath}")
    fastQCLogFileHandle.write( result.stdout ) 
    fastQCLogFileHandle.close( )

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: FastQC complete ==\n", color="red", attrs=["bold"] )  )


def prepareMultiQC( DemultiplexRunIdDir, projectNewNameList, RunIDShort ):
    """
    Preperation to run MultiQC:
        copy *.zip and *.html from  {DemultiplexRunIdDirNewNamel}/{RunIDShort}_QC directory
    """

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for MultiQC started ==", color="green", attrs=["bold"] ) )

    zipFiles  = [ ]
    HTLMfiles = [ ]
    for project in projectNewNameList:
        if f"{RunIDShort}.{demux.TestProject}" == project:
            if demux.debug:
                print( f"Test project '{RunIDShort}.{demux.TestProject}' detected. Skipping.")
            continue
        zipFiles  = glob.glob( f"{demux.DemultiplexRunIdDir}/{project}/*zip"  ) # source zip files
        HTLMfiles = glob.glob( f"{demux.DemultiplexRunIdDir}/{project}/*html" ) # source html files
        if demux.debug:
            print( f"DemultiplexRunIdDir/project/*zip:\t\t{demux.DemultiplexRunIdDir}/{project}/*zip"  )
            print( f"DemultiplexRunIdDir/project/*html:\t\t{demux.DemultiplexRunIdDir}/{project}/*html"  )

    sourcefiles = [ *zipFiles, *HTLMfiles ]
    destination = f"{demux.DemultiplexRunIdDir}/{RunIDShort}{demux.QCSuffix}"  # destination folder
    textsource  = " ".join(sourcefiles)

    if demux.debug:
        print( f"RunIDShort:\t\t\t\t\t{RunIDShort}"                 )
        print( f"projectNewNameList:\t\t\t\t{projectNewNameList}"   )
        print( f"DemultiplexRunIdDir:\t\t\t\t{demux.DemultiplexRunIdDir}" )
        print( f"zipFiles:\t\t\t\t\t{zipFiles}"                     )
        print( f"HTLMfiles:\t\t\t\t\t{HTLMfiles}"                   )
        print( f"sourcefiles:\t\t\t\t\t{sourcefiles}"               ) # textual representation of the source files.
        print( f"Command to execute:\t\t\t\t/usr/bin/cp {textsource} {destination}" )

    if not os.path.isdir( destination ) :
        print( f"Directory {destination} does not exist. Please check the logs, delete {demux.DemultiplexRunIdDir} and try again." )
        sys.exit( )


    try:
        # EXAMPLE: /usr/bin/cp project/*zip project_f/*html DemultiplexDir/RunIDShort.short_QC # (destination is a directory)
        for source in sourcefiles:
            shutil.copy2( source, destination )    # destination has to be a directory
    except FileNotFoundError as err:                # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
        print( f"\tFileNotFoundError in {inspect.stack()[0][3]}()" )
        print( f"\terrno:\t{err.errno}"                            )
        print( f"\tstrerror:\t{err.strerror}"                      )
        print( f"\tfilename:\t{err.filename}"                      )
        print( f"\tfilename2:\t{err.filename2}"                    )
        sys.exit( )

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for MultiQC finished ==\n", color="red", attrs=["bold"] ) )


def MultiQC( DemultiplexRunIdDir ):
    """
    Run /data/bin/multiqc against the project list.

    Result are zip files in the individual project directories
    """ 

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: MultiQC started ==", color="green", attrs=["bold"] ) )

    if demux.debug:
        print( f"DemultiplexRunIdDir:\t\t\t\t{demux.DemultiplexRunIdDir}" )

    command = demux.mutliqc_bin
    argv    = [ command, DemultiplexRunIdDir,
               '-o', DemultiplexRunIdDir 
              ]
    args    = " ".join(argv[1:]) # ignore the command part so we can print this string below, fresh all the time, in case we change tool command name

    if demux.debug:
        print( f"Command to execute:\t\t\t\t{command} {args}" )

    try:
        # EXAMPLE: /usr/local/bin/multiqc {demux.DemultiplexRunIdDir} -o {demux.DemultiplexRunIdDir} 2> {demux.DemultiplexRunIdDir}/demultiplex_log/05_multiqc.log
        result = subprocess.run( argv, capture_output = True, cwd = DemultiplexRunIdDir, check = True, encoding = demux.DecodeScheme )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
            f"Command:\t{err.cmd}", # interpolated strings
            f"Return code:\t{err.returncode}"
            f"Process output: {err.output}",
        ]

    # log multiqc output
    demux.mutliQCLogFilePath   = os.path.join( demux.DemultiplexLogDirPath, demux.multiqcLogFileName )
    multiQCLogFileHandle = open( demux.mutliQCLogFilePath, "x" ) # fail if file exists
    if demux.debug:
        print( f"mutliQCLogFilePath:\t\t\t\t{demux.mutliQCLogFilePath}")
    multiQCLogFileHandle.write( result.stderr ) # The MultiQC people are special: They write output to stderr
    multiQCLogFileHandle.close( )

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: MultiQC finished ==\n", color="red", attrs=["bold"] ) )


########################################################################
# qc
########################################################################

def qualityCheck( newFileList, DemultiplexRunIdDirNewNameList, RunIDShort, newProjectNameList ):
    """
    Run QC on the sequence run files

        FastQC takes the fastq.gz R1 and R2 of each sample sub-project and performs some Quality Checking on them
            The result of running FastQC is html and .zip files, one for each input fastq.gz file. The .zip file contails a directory with the complete analysis of the sample. The .html file is the entry point for all the stuff in the subdirectory

        MultiQC takes {EXPLAIN INPUT HERE}
    """

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Quality Check started ==", color="green", attrs=["bold"] ) )

    DemultiplexRunIdDir = os.path.dirname( DemultiplexRunIdDirNewNameList[0] )

    if demux.debug:
        print( f"newFileList:\t\t\t\t\t{newFileList}" )
        print( f"DemultiplexRunIdDirNewNameList:\t\t\t{DemultiplexRunIdDirNewNameList}" )
        print( f"RunIDShort:\t\t\t\t\t{RunIDShort}" )
        print( f"newProjectNameList:\t\t\t\t{newProjectNameList}" )
        print( f"DemultiplexRunIdDir:\t\t\t\t{demux.DemultiplexRunIdDir}" )

    for project in newProjectNameList: 
        if f"{RunIDShort}.{demux.TestProject}" == project:
            if demux.debug:
                print( f"{demux.TestProject} test project detected. Skipping.\n" )
            continue

    FastQC( newFileList )
    prepareMultiQC( DemultiplexRunIdDir, newProjectNameList, RunIDShort )
    MultiQC( DemultiplexRunIdDir )


    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Quality Check finished ==\n", color="red", attrs=["bold"] ) )




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
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files started ==", color="green", attrs=["bold"] ) )

    if demux.debug:
        print( f"for debug puproses, creating empty files {demux.DemultiplexRunIdDir}/foo.tar and {demux.DemultiplexRunIdDir}/bar.zip\n" )
        pathlib.Path( f"{demux.DemultiplexRunIdDir}/{demux.footarfile}" ).touch( )
        pathlib.Path( f"{demux.DemultiplexRunIdDir}/{demux.barzipfile}" ).touch( )


    # build the filetree
    if demux.debug:
        print( f'= walk the file tree, {inspect.stack()[0][3]}() ======================')
    for directoryRoot, dirnames, filenames, in os.walk( DemultiplexRunIdDir, followlinks = False ):

        for file in filenames:
            if not any( var in file for var in [ demux.CompressedFastqSuffix, demux.zipSuffix, demux.tarSuffix ] ): # grab only .zip, .fasta.gz and .tar files
                continue

            filepath = os.path.join( directoryRoot, file )

            if not os.path.isfile( filepath ):
                print( f"{filepath} is not a file. Exiting." )
                sys.exit( )

            if os.path.getsize( filepath ) == 0 : # make sure it's not a zero length file 
                print( f"file {filepath} has zero length. Skipping." )
                continue
        
            filehandle     = open( filepath, 'rb' )
            filetobehashed = filehandle.read( )
            md5sum         = hashlib.md5( filetobehashed ).hexdigest( )
            sha512sum      = hashlib.sha256( filetobehashed ).hexdigest( ) 
            if demux.debug:
                print( f"md5sum: {md5sum} | sha512sum: {sha512sum}\t| filepath: {filepath}" )


            if not os.path.isfile( f"{filepath}{demux.md5Suffix}" ):
                fh = open( f"{filepath}{demux.md5Suffix}", "w" )
                fh.write( f"{md5sum}\n" )
                fh.close( )
            else:
                print( f"{filepath}{demux.md5Suffix} exists, skipping" )
                continue
            if not os.path.isfile( f"{filepath}{demux.sha512Suffix}" ):
                fh = open( f"{filepath}{demux.sha512Suffix}", "w" )
                fh.write( f"{sha512sum}\n" )
                fh.close( )
            else:
                continue

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files finished ==\n", color="red", attrs=["bold"] ) )



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
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Changing Permissions started ==", color="green", attrs=["bold"] ) )

    if demux.debug:
        print( termcolor.colored( f"= walk the file tree, {inspect.stack()[0][3]}() ======================", attrs=["bold"] ) )

    for directoryRoot, dirnames, filenames, in os.walk( path, followlinks = False ):
    
        # change ownership and access mode of files
        for file in filenames:
            filepath = os.path.join( directoryRoot, file )
            if demux.debug:
                print( filepath )

            if not os.path.isfile( filepath ):
                print( f"{filepath} is not a file. Exiting.")
                sys.exit( )

            try:
                # shutil.chown( filepath, user = demux.user, group = demux.group ) # EXAMPLE: /bin/chown :sambagroup filepath
                shutil.chown( filepath, group = demux.group ) # EXAMPLE: /bin/chown :sambagroup filepath
                                                              # chown user is not available for non-root users
            except FileNotFoundError as err:                  # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
                print( f"\tFileNotFoundError in {inspect.stack()[0][3]}()" )
                print( f"\terrno:\t{err.errno}"                            )
                print( f"\tstrerror:\t{err.strerror}"                      )
                print( f"\tfilename:\t{err.filename}"                      )
                print( f"\tfilename2:\t{err.filename2}"                    )
                sys.exit( )

            try:
                # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
                os.chmod( filepath, stat.S_IREAD | stat.S_IWRITE | stat.S_IRGRP | stat.S_IROTH ) # rw-r--r-- / 644 / read-write owner, read group, read others
            except FileNotFoundError as err:                # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
                print( f"\tFileNotFoundError in {inspect.stack()[0][3]}()" )
                print( f"\terrno:\t{err.errno}"                            )
                print( f"\tstrerror:\t{err.strerror}"                      )
                print( f"\tfilename:\t{err.filename}"                      )
                print( f"\tfilename2:\t{err.filename2}"                    )
                sys.exit( )


    # change ownership and access mode of directories
    if demux.debug:
        print( termcolor.colored( f"= walk the dir tree, {inspect.stack()[0][3]}() ======================", attrs=["bold"] ) )
    for directoryRoot, dirnames, filenames, in os.walk( path, followlinks = False ):

        for name in dirnames:
            dirpath = os.path.join( directoryRoot, name )

            if demux.debug:
                print( dirpath )

            if not os.path.isdir( dirpath ):
                print( f"{dirpath} is not a directory. Exiting.")
                sys.exit( )

            try:
                shutil.chown( dirpath, group = demux.group ) # EXAMPLE: /bin/chown :sambagroup dirpath
                                                              # chown user is not available for non-root users
            except FileNotFoundError as err:                  # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
                print( f"\tFileNotFoundError in {inspect.stack()[0][3]}()" )
                print( f"\terrno:\t{err.errno}"                            )
                print( f"\tstrerror:\t{err.strerror}"                      )
                print( f"\tfilename:\t{err.filename}"                      )
                print( f"\tfilename2:\t{err.filename2}"                    )
                sys.exit( )

            try:
                # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
                os.chmod( dirpath, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH ) # rwxr-xr-x / 755 / read-write-execute owner, read-execute group, read-execute others
            except FileNotFoundError as err:                # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
                print( f"\tFileNotFoundError in {inspect.stack()[0][3]}()" )
                print( f"\terrno:\t{err.errno}"                            )
                print( f"\tstrerror:\t{err.strerror}"                      )
                print( f"\tfilename:\t{err.filename}"                      )
                print( f"\tfilename2:\t{err.filename2}"                    )
                sys.exit( )

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Changing Permissions finished ==\n", color="red", attrs=["bold"] ) )



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
        {RunIDShort}_QC/
        multiqc_data/

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
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery started ==", color="green", attrs=["bold"] ) )

    counter = 0

    if demux.debug:
        print( f"Current working directory:\t{os.getcwd( )}")
        print( f"DemultiplexRunIdDir:\t\t{demux.DemultiplexRunIdDir}" )
        print( f"ForTransferRunIdDir:\t\t{demux.ForTransferRunIdDir}" )
        print( f"forTransferQCtarFile:\t\t{demux.forTransferQCtarFile}" )

    if demux.debug:
        print( f"Original working directory:\t{ os.getcwd( ) }" )

    # Switch to the Demultiplex directory we will be archiving
    try:
        os.chdir( demux.DemultiplexRunIdDir )
    except FileNotFoundError:
        print( f"Directory: {demux.DemultiplexRunIdDir} does not exist. Exiting." )
        sys.exit( )
    except NotADirectoryError:
        print( f"{demux.DemultiplexRunIdDir} is not a directory. Exiting." )
        sys.exit( )
    except Exception as e:
        print( f"You do not have permissions to change to {demux.DemultiplexRunIdDir}. Exiting." )
        sys.exit( )

    if demux.debug:
        print( f"Changed into directory\t\t{demux.DemultiplexRunIdDir}")

    # Make {demux.ForTransferRunIdDir} directory
    if not os.path.isdir( demux.ForTransferRunIdDir ):
        os.mkdir( demux.ForTransferRunIdDir )
    else:
        print( f"{demux.ForTransferRunIdDir} exists, this is not supposed to exist, please investigate and re-run the demux. Exiting." )
        sys.exit( )


    projectList = os.listdir( "." )                                         # get the contents of the demux.DemultiplexRunIdDir directory
    if demux.debug:
        print( f"{demux.DemultiplexRunIdDir} directory contents: {projectList}" ) 

    projectsToProcess = [ ]
    for project in projectList:                                             # itterate over said demux.DemultiplexRunIdDirs contents
        if any( var in project for var in [ demux.QCSuffix ] ):             # skip anything that includes '_QC'
            continue
        if any( var in project for var in [ demux.TestProject ] ):          # skip the test project, 'FOO-blahblah-BAR'
            continue
        if any( var in project for var in [ demux.NextSeq, demux.MiSeq ] ): # if there is a nextseq or misqeq tag, add the directory to the newProjectNameList
            projectsToProcess.append( project )

    print( f"projectsToProcess:\t\t{ projectsToProcess }" )
    print( f"len(projectsToProcess):\t\t{len( projectsToProcess  ) }" )

    for project in projectsToProcess:

        if demux.TestProject in project:       # disregard the debug Test Project # This is extra, but just in case.
            if demux.debug:
                print( f"\"{demux.TestProject}\" test project found. Skipping." )
            continue
        if demux.temp in project:              # disregard the temp directory # This is extra, but just in case.
            if demux.debug:
                print( f"\"{demux.temp}\" directory found. Skipping." )
            continue
        if demux.DemultiplexLogDirPath in project: # disregard demultiplex_log
            if demux.debug:
                print( f"\"{demux.DemultiplexLogDirPath}\" directory found. Skipping." )
            continue
        if demux.QCSuffix in project:          # disregard '_QC'
            if demux.debug:
                print( f"\"{demux.QCSuffix}\" directory found. Skipping." )
            continue


        try:
            os.mkdir( f"{demux.ForTransferRunIdDir}/{project}" )  # we save each tar file into its own directory
        except FileExistsError as err:
            print( f"Error while trying to mkdir {demux.ForTransferRunIdDir}/{project}")
            print( f"Error message: {err}")
            print ( "Exiting.")
            sys.exit( )

        tarFile = os.path.join( demux.ForTransferRunIdDir, project )
        tarFile = os.path.join( tarFile, f"{project}{demux.tarSuffix}" )
        if demux.debug:
            print( f"tarFile:\t\t\t{tarFile}")

        if not os.path.isfile( tarFile ) :
            tarFileHandle = tarfile.open( name = tarFile, mode = "w:" )
        else:
            printf( f"{tarFile} exists. Please investigate or delete. Exiting." )
            sys.exit( )


        # we iterrate through all the renamed Sample_Project directories and make a single tar file for each directory
        # build the filetree
        if demux.debug:
            print( termcolor.colored( f"\n== walk the file tree, {inspect.stack()[0][3]}() , {os.getcwd( )}/{project} ======================", attrs=["bold"] ) )

        counter = counter + 1
        print( termcolor.colored( f"==> Archiving {project} ({counter} out of {len(projectsToProcess)} projects ) ==================", color="yellow", attrs=["bold"] ) )
        for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.DemultiplexRunIdDir, project ), followlinks = False ): 
             for file in filenames:
                # add one file at a time so we can give visual feedback to the user that the script is processing files
                # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
                # of output that make users uncomfortable
                filenameToTar = os.path.join( project, file )
                tarFileHandle.add( name = filenameToTar, recursive = False )
                print( filenameToTar )

        tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
        print( termcolor.colored( f'==< Archived {project} ({counter} out of {len(projectsToProcess)} projects ) ==================\n', color="yellow", attrs=["bold"] ) )

    ###########################################################
    #
    #   QC.tar
    #
    ###########################################################
    tmparray        = RunID.split("_")[:2] # got to re-create RunIDShort # FIXME FIXME FIXME RunID/RunIDShort has to be turned into an instance property
    RunIDShort      = "_".join( tmparray )
    QCDir           = f"{RunIDShort}{demux.QCSuffix}"
    multiQCDir      = demux.multiqc_data
    if demux.debug:
        print( f"RunIDShort (reconstructed, not global: {RunIDShort}" )
        print( f"QCDir:\t\t\t\t{QCDir}")
        print( f"multiQCDir:\t\t\t{multiQCDir}")
    

    ################################################################################
    # What to put inside the QC file: {RunIDShort}_QC and multiqc_data
    ################################################################################
    # {RunIDShort}_QC
    ################################################################################
    if not os.path.isfile( demux.forTransferQCtarFile ):
        tarQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "w:" )
    else:
        printf( f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting." )
        sys.exit( )
    print( termcolor.colored( f"==> Archiving {QCDir} projects ) ==================", color="yellow", attrs=["bold"] ) )
    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.DemultiplexRunIdDir, QCDir ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the user that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( QCDir, file )
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            print( filenameToTar )

    print( termcolor.colored( f"==> Archived {QCDir} ==================", color="yellow", attrs=["bold"] ) )

    ################################################################################
    # multiqc_data
    ################################################################################
    print( termcolor.colored( f"==> Archiving {multiQCDir} ==================", color="yellow", attrs=["bold"] ) )
    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.DemultiplexRunIdDir, multiQCDir ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the user that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( multiQCDir, file )
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            print( filenameToTar )

    # both {RunIDShort}_QC and multidata_qc go in the same tar file
    tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
    print( termcolor.colored( f"==> Archived {multiQCDir} ==================", color="yellow", attrs=["bold"] ) )    


    ###########################################################
    # cleanup
    ###########################################################

    print( termcolor.colored( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery finished ==\n", color="red", attrs=["bold"] ) )



########################################################################
# script_completion_file
########################################################################

def scriptComplete( DemultiplexRunIdDir ):
    """
    Create the {DemultiplexDir}/{demux.DemultiplexCompleteFile} file to signal that this script has finished
    """

    demux.n = demux.n + 1
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Finishing up script ==", color="green", attrs=["bold"] ) )

    try:
        file = os.path.join( DemultiplexRunIdDir, demux.DemultiplexCompleteFile )
        pathlib.Path( file ).touch( mode=644, exist_ok=False)
    except Exception as e:
        print( f"{file} already exists. Please delete it before running {__file__}.\n")
        sys.exit( )

    print( f"DemultiplexCompleteFile {file} created.")
    print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Finishing up script ==", color="red", attrs=["bold"] ) )



########################################################################
# deliverFilesToVIGASP
########################################################################

def deliverFilesToVIGASP(  ):
    """
    Write the uploader file needed to upload the data to VIGASP and then
        upload the relevant files.
    """

    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for uploading to VIGASP started\n")


    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for uploading to VIGASP finished\n")




########################################################################
# deliverFilesToNIRD
########################################################################

def deliverFilesToNIRD(  ):
    """
    Make connection to NIRD and upload the data
    """
    demux.n = demux.n + 1
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for archiving to NIRD started\n")


    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for archiving to NIRD finished\n")

#



########################################################################
# detectNewRuns
########################################################################

def detectNewRuns(  ):
    """
    Detect if a new run has been uploaded to /data/rawdata
    """

# TODO TODO TODO
#
#   new feature: print out all the new runs detected
#       mention which one is being processed
#       mention which one are remaining
#########
    demux.n = demux.n + 1
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Detecting if new runs exist started\n")


    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Detecting if new runs exist finished\n")

#



########################################################################
# MAIN
########################################################################

def main( RunID ):
    """
    Main function for the demultiplex script.
    All actions are coordinated through here
    """

    # RunID
    RunIDShort             = '_'.join(RunID.split('_')[0:2]) # this should be turned into a setter in the demux object
 ######################################################
    RawDataLocationDirRoot = os.path.join( demux.DataRootDirPath, demux.RawDataDirName )
    SequenceRunOriginDir   = os.path.join( RawDataLocationDirRoot, RunID )
    SampleSheetFilePath    = os.path.join( SequenceRunOriginDir, demux.SampleSheetFileName )
    RTACompleteFilePath    = f"{SequenceRunOriginDir}/{demux.RTACompleteFile}"
######################################################
    DemultiplexDirRoot     = os.path.join( demux.DataRootDirPath, demux.DemultiplexDirName )
    demux.DemultiplexRunIdDir    = os.path.join( DemultiplexDirRoot, RunID + demux.DemultiplexDirSuffix ) 
    demux.DemultiplexLogDirPath  = os.path.join( demux.DemultiplexRunIdDir, demux.DemultiplexLogDirName )
    demux.DemultiplexLogFilePath = os.path.join( demux.DemultiplexLogDirPath, demux.ScriptLogFile )
    DemultiplexQCDirPath   = f"{demux.DemultiplexRunIdDir}/{RunIDShort}{demux.QCSuffix}"
    DemultiplexProjSubDirs = [ ]
######################################################
    ForTransferDirRoot     = os.path.join ( demux.DataRootDirPath, demux.ForTransferDirName )
    ForTransferDir         = os.path.join ( ForTransferDirRoot, RunID )
    demux.ForTransferRunIdDir    = os.path.join( demux.ForTransferDir, RunID )
    demux.forTransferQCtarFile   = os.path.join( demux.ForTransferRunIdDir, f"{RunID}{demux.QCSuffix}{demux.tarSuffix}" )

    ForTransferProjNames   = []
######################################################

    project_list           = demux.getProjectName( SampleSheetFilePath )
    if demux.debug and len(project_list) == 1:
        project_list.add( demux.TestProject ) # if debug, have at least two project names to ensure multiple paths are being created
    for project_name in project_list:         # build the full list of subdirectories to make under {demux.DemultiplexRunIdDir}
        DemultiplexProjSubDirs.append( f"{demux.DemultiplexRunIdDir}/{RunIDShort}.{project_name}" )

    # Build the paths for each of the projects. example: /data/for_transfer/{RunID}/{item}
    for project in project_list: 
        ForTransferProjNames.append( f"{demux.DemultiplexRunIdDir}/{RunIDShort}.{project}" )


    print( f"To rerun this script run\n" )
    print( termcolor.colored( f"\tclear; rm -rf {demux.DemultiplexRunIdDir} && rm -rf {ForTransferDir} && /usr/bin/python3 /data/bin/demultiplex_script.py {RunID}\n\n", attrs=["bold"] ) )
    if demux.debug: # print the values here # FIXME https://docs.python.org/3/tutorial/inputoutput.html "Column output in Python3"
        print( "=============================================================================")
        print( f"RunID:\t\t\t\t{RunID}")
        print( f"RunIDShort:\t\t\t{RunIDShort}")
        print( f"project_list:\t\t\t{project_list}")
        print( "=============================================================================")
        print( f"RawDataLocationDirRoot:\t\t{RawDataLocationDirRoot}" )
        print( f"SequenceRunOriginDir:\t\t{SequenceRunOriginDir}" )
        print( f"SampleSheetFilePath:\t\t{SampleSheetFilePath}" )
        print( f"RTACompleteFilePath:\t\t{SequenceRunOriginDir}/{demux.RTACompleteFile}" )
        print( "=============================================================================")
        print( f"DemultiplexDirRoot:\t\t{DemultiplexDirRoot}" )
        print( f"DemultiplexRunIdDir:\t\t{demux.DemultiplexRunIdDir}" )
        print( f"DemultiplexLogDirPath:\t\t{demux.DemultiplexLogDirPath}" )
        print( f"DemultiplexLogFilePath:\t\t{demux.DemultiplexLogFilePath}" )
        print( f"DemultiplexQCDirPath:\t\t{DemultiplexQCDirPath}" )
        for index, directory in enumerate( DemultiplexProjSubDirs):
            print( f"DemultiplexProjSubDirs[{index}]:\t{directory}")
        print( "=============================================================================")
        print( f"ForTransferDirRoot:\t\t{ForTransferDirRoot}" )
        print( f"ForTransferDir:\t\t\t{ForTransferDir}" )
        for index, directory in enumerate( ForTransferProjNames):
            print( f"ForTransferProjNames[{index}]:\t{directory}")
        print( "=============================================================================\n")

    # init:

    #   check if sequencing run has completed, exit if not
    #       Completion of sequencing run is signaled by the existance of the file {RTACompleteFilePath} ( SequenceRunOriginDir}/{demux.RTACompleteFile} )
    if not os.path.isfile( f"{RTACompleteFilePath}" ):
        print( f"{RunID} is not finished sequencing yet!" ) 
        sys.exit()

    #   check if {DemultiplexDirRoot} exists
    #       exit if not
    if not os.path.exists( DemultiplexDirRoot ):
        print( f"{DemultiplexDirRoot} is not present, please use the provided ansible file to create the root directory hierarchy")
    if not os.path.isdir( DemultiplexDirRoot ):
        print( f"{DemultiplexDirRoot} is not a directory! Cannot stored demultiplex data in a non-directory structure! Exiting.")
        sys.exit( )
    if os.path.exists( demux.DemultiplexRunIdDir ):
        print( f"{demux.DemultiplexRunIdDir} exists. Delete the demultiplex folder before re-running the script" )
        sys.exit()

    #   create {DemultiplexDirRoot} directory structrure
    createDemultiplexDirectoryStructure( demux.DemultiplexRunIdDir, RunIDShort, project_list  )
    #   copy SampleSheet.csv from {SampleSheetFilePath} to {demux.DemultiplexRunIdDir} . bcl2fastq uses the file for demultiplexing
    try:
        demux.n = demux.n + 1
        shutil.copy2( SampleSheetFilePath, demux.DemultiplexRunIdDir )
        print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: {demux.SampleSheetFileName} copied to {demux.DemultiplexRunIdDir}\n", color="green" ) )
    except Exception as err:
        print( err )
        sys.exit( )
    try:
        # Request by Cathrine: Copy the SampleSheet file to /data/SampleSheet automatically
        demux.n = demux.n + 1
        SampleSheetArchiveFilePath = os.path.join( demux.SampleSheetDirPath, f"{RunID}{demux.CSVSuffix}" ) # .dot is included in CSVsuffix
        shutil.copy2( SampleSheetFilePath, SampleSheetArchiveFilePath )
        print( termcolor.colored( f"==> {demux.n}/{demux.TotalTasks} tasks: Archive {SampleSheetFilePath} to {SampleSheetArchiveFilePath} ==\n", color="green" ) )
    except Exception as err:
        print( err )
        sys.exit( )

    demultiplex( SequenceRunOriginDir, demux.DemultiplexRunIdDir )
    newFileList, DemultiplexRunIdDirNewNameList = renameFiles( demux.DemultiplexRunIdDir, RunIDShort, project_list )

    newProjectNamelist = [ ]
    for project in project_list:
        newProjectNamelist.append( f"{RunIDShort}.{project}")
    
    qualityCheck( newFileList, DemultiplexRunIdDirNewNameList, RunIDShort, newProjectNamelist )
    calcFileHash( demux.DemultiplexRunIdDir )                                                           # create .md5/.sha512 checksum files for every .fastqc.gz/.tar/.zip file under DemultiplexRunIdDir
    changePermissions( demux.DemultiplexRunIdDir  )                                                     # change permissions for the files about to be included in the tar files 
    prepareDelivery( RunID )                                                                            # prepare the delivery files
    calcFileHash( demux.ForTransferRunIdDir )                                                           # create .md5/.sha512 checksum files for the delivery .fastqc.gz/.tar/.zip files under DemultiplexRunIdDir, 2nd fime for the new .tar files created by prepareDelivery( )
    changePermissions( demux.ForTransferRunIdDir  )                                                                    # change permissions for all the delivery files, including QC
    deliverFilesToVIGASP( )
    deliverFilesToNIRD( )
    scriptComplete( demux.DemultiplexRunIdDir )

    print( termcolor.colored( "\n====== All done! ======\n", attrs=["blink"] ) )



########################################################################
# MAIN
########################################################################

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    # FIXMEFIXME add named arguments
    RunID = sys.argv[1]
    RunID = RunID.replace( "/", "" ) # Just in case anybody just copy-pastes from a listing in the terminal, be forgiving
    main( RunID )
