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

"""
demux module:
    A "pythonized" Obj-Oriented approach to demultiplexing Illumina bcl files and prepearing them for delivery to the individual NVI systems for subprocessing

    Module can run on its own, without needing to include in a library as such:

    /usr/bin/python3     /data/bin/demultiplex_script.py  200306_M06578_0015_000000000-CWLBG

    python interpreter | path to script                 | RunID directory from /data/rawdata

INPUTS:
    - RunID directory from /data/rawdata

OUTPUTS:
    - fastq.gz files that are used by FastQC and MultiQC
    - MultiQC creates .zip files which are included in the QC tar file
    - .tar files for the fastq.gz and .md5/.sha512 hashes
    - [Future feature] Upload files to VIGASP
    - [Future feature] Archive files to NIRD

WHY DOES THIS PROGRAM EXIST
WHAT DO THE FASTQ.GZ FILES CONTAIN
WHAT DO THE ZIP FILES CONTAIN
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


WHAT DOES THE QC TAR FILE CONTAIN
    [RunIDShort}_QC directory contains all the .zip and .html files for all projects, as each filename is unique. So for the QC tar file, we iterate through all the Sample_Projects and stuff their files in a single tar file

WHY NOT USE MD5 ANY MORE AND PREFER SHA512

WHY THIS PROGRAM SHOULD EVENTUALLY BE A DAEMON

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


HOW DOES THE SCRIPT DO WHAT IT DOES
    - uses Illumina's blc2fastq tool     ( https://emea.support.illumina.com/downloads/bcl2fastq-conversion-software-v2-20.html )
    - uses FastQ                         ( https://www.bioinformatics.babraham.ac.uk/projects/download.html#fastqc )
    - uses MultiQC                       ( as root, pip3 install multiqc )
    - hashing is done by the internal Python3 hashlib library (do not need any external or OS level packages)
        - hashing can be memory intensive as the entire file is read to memory
        - should be ok, unless we start sequencing large genomes

LIMITATIONS
    - Can demultipex one directory at a time only
    - No sanity checking to see if a demultiplexed directory is correctly demux'ed
        - Relies only on output directory name and does not verify contents

Needs: 
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

"""


class demux:
    """
    demux: make an object of the entire demultiplex process.
    """
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
    DemultiplexLogDir       = 'demultiplex_log'
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
    # SampleSheetFilePath     = os.path.join( SampleSheetDirPath, RunID, SampleSheetFileName )
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
    with open( __file__ ) as f:     # little trick from openstack: read the current script and count the functions and initialize TotalTasks to it
        tree = ast.parse( f.read( ) )
        TotalTasks = sum( isinstance( exp, ast.FunctionDef ) for exp in tree.body )
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
        print( f"==> {demux.n}/{demux.TotalTasks} tasks: Get project name from {SampleSheetFilePath} started ==\n" )

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


        print( f"==< {demux.n}/{demux.TotalTasks} tasks: Get project name from {SampleSheetFilePath} finished ==\n" )
        return( set( project_list ) )




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
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Create directory structure started ==\n" )

    DemultiplexLogDir     = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDir ) 
    DemuxQCDirectoryName  = f"{RunIDShort}{demux.QCSuffix}"                    # QCSuffix is defined in object demux
    DemuxQCDirectoryPath  = os.path.join( DemultiplexRunIdDir, DemuxQCDirectoryName  )

    if demux.debug:
            print( f"DemultiplexRunIdDir\t\t\t\t{DemultiplexRunIdDir}" )
            print( f"DemultiplexRunIdDir/DemultiplexLogDir:\t\t{DemultiplexLogDir}" )
            print( f"DemultiplexRunIdDir/DemuxQCDirectory:\t\t{DemuxQCDirectoryPath}\n" )

    os.mkdir( DemultiplexRunIdDir )                                          # root directory for run
    os.mkdir( DemultiplexLogDir )    # log directory for run
    os.mkdir( DemuxQCDirectoryPath ) # QC directory  for run

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Create directory structure finished ==\n" )



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
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Demultiplexing started ==\n" )

    argv = [ demux.bcl2fastq_bin,
         "--no-lane-splitting",
         "--runfolder-dir",
        f"{SequenceRunOriginDir}",
         "--output-dir",
        f"{DemultiplexRunIdDir}"
    ]
    Bcl2FastqLogFile     = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDir, demux.Bcl2FastqLogFileName )
    if demux.debug:
        print( f"Command to execute:\t\t\t\t" + " ".join( argv ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + SequenceRunOriginDir + ' --output-dir ' + DemultiplexDir + ' 2> ' + DemultiplexDir + '/demultiplex_log/02_demultiplex.log'
        result =  subprocess.run( argv, capture_output = True, text = True, cwd = SequenceRunOriginDir, check = True, encoding = demux.DecodeScheme )
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

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Demultiplexing finished ==\n" )


########################################################################
# renameFiles( )
########################################################################

def renameFiles( DemultiplexRunIdDir, RunIDShort, project_list ):
    """
    Rename any [sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ] files inside 
        {DemultiplexRunIdDir}/{RunIDShort}[{project_list[0]}, .. , {project_list[n]}] to match the pattern
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
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Renaming files started ==\n" )

    oldname            = ""
    newname            = ""
    newProjectNameList = [ ]

    if demux.debug:
        print( f"DemultiplexRunIdDir:\t{DemultiplexRunIdDir}")
        print( f"RunIDShort:\t\t\t{RunIDShort}")
        for index, item in enumerate( project_list ):
            print( f"DemultiplexRunIdDir[{index}]:\t{DemultiplexRunIdDir[index]}")

    for project in project_list: # rename files in each project directory

        if project == demux.TestProject:
            if demux.debug:
                print( f"Test project '{demux.TestProject}' detected. Skipping.\n" )
                continue

        CompressedFastQfilesDir = f"{DemultiplexRunIdDir}/{project}"
        if demux.debug:
            print( f"CompressedFastQfilesDir:\t\t\t{CompressedFastQfilesDir}")

        filesToSearchFor     = f'{CompressedFastQfilesDir}/*{demux.CompressedFastqSuffix}'
        CompressedFastQfiles = glob.glob( filesToSearchFor ) # example: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/sample*fastq.gz

        if demux.debug:
            print( f"fastq files for {project}:\t\t{filesToSearchFor}" )
            for index, item in enumerate( CompressedFastQfiles ):
                print( f"CompressedFastQfiles[{index}]:\t\t\t{item}" )

        if not CompressedFastQfiles: # if array is empty
            print( f"CompressedFastQfiles var is empty in method {inspect.stack()[0][3]}(). Exiting. ")
            sys.exit( )

        for file in CompressedFastQfiles:
    
            # get the base filename. We picked up sample*.{CompressedFastqSuffix} and we have to rename it to {RunIDShort}sample*.{CompressedFastqSuffix}
            baseFileName = os.path.basename( file )
            if demux.debug:
                print( f"baseFilename:\t\t\t\t\t{baseFileName}")

            oldname = f"{file}"
            newname = f"{DemultiplexRunIdDir}/{project}/{RunIDShort}.{baseFileName}"
            newfoo  = f"{DemultiplexRunIdDir}/{RunIDShort}.{project}/{RunIDShort}.{baseFileName}" # saving this var to pass locations of new directories

            if demux.debug:
                print( f"file:\t\t\t\t\t\t{file}")
                print( f"command to execute:\t\t\t\t/usr/bin/mv {oldname} {newname}" )
            

            print( "\n" )

            # make sure oldname files exist
            # make sure newname files do not exist
            oldfileExists = os.path.isfile( oldname )
            newfileExists = os.path.isfile( newname )

            if newfoo not in newProjectNameList:
                newProjectNameList.append( newfoo ) # save it to return the list, so we will not have to recreate the filenames

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


        DemultiplexRunIdDirNewNameList = [ ]


    for project in project_list: # rename the project directories

        oldname = f"{DemultiplexRunIdDir}/{project}"
        newname = f"{DemultiplexRunIdDir}/{RunIDShort}.{project}"
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
                print( f"Renaming {oldname} to {newname}" )
                for index, item in enumerate( newProjectNameList ):
                    if index < 10:
                        print( f"newProjectNameList[{index}]:\t\t\t\t{item}") # make sure the debugging output is all lined up.
                    else:
                        print( f"newProjectNameList[{index}]:\t\ts\t{item}")     
                for index, item in enumerate( DemultiplexRunIdDirNewNameList ):
                    print( f"DemultiplexRunIdDirNewNameList[{index}]:\t\t{item}\n")

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Renaming files finished ==\n" )

    return newProjectNameList, DemultiplexRunIdDirNewNameList


########################################################################
# FastQC
########################################################################

def FastQC( newFileList ):
    """
    FastQC: Run /data/bin/fastqc (which is a symlink to the real qc)
    """

    demux.n = demux.n + 1
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: FastQC started ==\n" )

    command             = demux.fastqc_bin
    argv                = [ command, '-t', '4', *newFileList ] # the * operator on a list/array "splats" (flattens) the values in the array, breaking them down to individual arguemtns
    demultiplexRunIdDir = os.path.dirname( os.path.dirname( newFileList[0] ) )

    if demux.debug:
        print( f"argv:\t\t\t\t\t\t{argv}")
        arguments = " ".join( argv[1:] )
        print( f"Command to execute:\t\t\t\t{command} {arguments}") # exclude the first element of the array # example for filename: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/
        print( f"demultiplexRunIdDir:\t\t\t\t{demultiplexRunIdDir}\n")

    try:
        # EXAMPLE: /usr/local/bin/fastqc -t 4 {DemultiplexRunIdDir}/{project}/*fastq.gz > DemultiplexRunIdDir/demultiplex_log/04_fastqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demultiplexRunIdDir, check = True, encoding = demux.DecodeScheme )
    except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: {err.cmd}", # interpolated strings
                     f"Return code: {err.returncode}"
                     f"Process output: {err.output}",
            ]

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: FastQC complete ==\n" )


def prepareMultiQC( DemultiplexRunIdDir, projectNewNameList, RunIDShort ):
    """
    Preperation to run MultiQC:
        copy *.zip and *.html from  {DemultiplexRunIdDirNewNamel}/{RunIDShort}_QC directory
    """

    demux.n = demux.n + 1
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for MultiQC started ==\n" )

    zipFiles  = [ ]
    HTLMfiles = [ ]
    for project in projectNewNameList:
        if f"{RunIDShort}.{demux.TestProject}" == project:
            if demux.debug:
                print( f"Test project '{RunIDShort}.{demux.TestProject}' detected. Skipping.")
            continue
        zipFiles  = glob.glob( f"{DemultiplexRunIdDir}/{project}/*zip"  ) # source zip files
        HTLMfiles = glob.glob( f"{DemultiplexRunIdDir}/{project}/*html" ) # source html files
        if demux.debug:
            print( f"DemultiplexRunIdDir/project/*zip:\t\t{DemultiplexRunIdDir}/{project}/*zip"  )
            print( f"DemultiplexRunIdDir/project/*html:\t\t{DemultiplexRunIdDir}/{project}/*html"  )

    sourcefiles = [ *zipFiles, *HTLMfiles ]
    destination = f"{DemultiplexRunIdDir}/{RunIDShort}{demux.QCSuffix}"  # destination folder
    textsource  = " ".join(sourcefiles)

    if demux.debug:
        print( f"RunIDShort:\t\t\t\t\t{RunIDShort}"                 )
        print( f"projectNewNameList:\t\t\t\t{projectNewNameList}"   )
        print( f"DemultiplexRunIdDir:\t\t\t\t{DemultiplexRunIdDir}" )
        print( f"zipFiles:\t\t\t\t\t{zipFiles}"                     )
        print( f"HTLMfiles:\t\t\t\t\t{HTLMfiles}"                   )
        print( f"sourcefiles:\t\t\t\t\t{sourcefiles}"               ) # textual representation of the source files.
        print( f"Command to execute:\t\t\t\t/usr/bin/cp {textsource} {destination}\n" )

    if not os.path.isdir( destination ) :
        print( f"Directory {destination} does not exist. Please check the logs, delete {DemultiplexRunIdDir} and try again." )
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

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for MultiQC finished ==\n" )


def MultiQC( DemultiplexRunIdDir ):
    """
    Run /data/bin/multiqc against the project list.

    Result are zip files in the individual project directories
    """ 

    demux.n = demux.n + 1
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: MultiQC started ==\n")

    if demux.debug:
        print( f"DemultiplexRunIdDir:\t\t\t\t{DemultiplexRunIdDir}" )

    command = demux.mutliqc_bin
    argv    = [ command, DemultiplexRunIdDir,
               '-o', DemultiplexRunIdDir 
              ]
    args    = " ".join(argv[1:]) # ignore the command part so we can print this string below, fresh all the time, in case we change tool command name

    if demux.debug:
        print( f"Command to execute:\t\t\t\t{command} {args}\n" )

    try:
        # EXAMPLE: /usr/local/bin/multiqc {DemultiplexRunIdDir} -o {DemultiplexRunIdDir} 2> {DemultiplexRunIdDir}/demultiplex_log/05_multiqc.log
        result = subprocess.run( argv, capture_output = True, cwd = DemultiplexRunIdDir, check = True, encoding = demux.DecodeScheme )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
            f"Command:\t{err.cmd}", # interpolated strings
            f"Return code:\t{err.returncode}"
            f"Process output: {err.output}",
        ]

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: MultiQC finished ==\n")


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
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Quality Check started ==\n")

    DemultiplexRunIdDir = os.path.dirname( DemultiplexRunIdDirNewNameList[0] )

    if demux.debug:
        print( f"newFileList:\t\t\t\t\t{newFileList}" )
        print( f"DemultiplexRunIdDirNewNameList:\t\t\t{DemultiplexRunIdDirNewNameList}" )
        print( f"RunIDShort:\t\t\t\t\t{RunIDShort}" )
        print( f"newProjectNameList:\t\t\t\t{newProjectNameList}" )
        print( f"DemultiplexRunIdDir:\t\t\t\t{DemultiplexRunIdDir}\n" )

    for project in newProjectNameList: 
        if f"{RunIDShort}.{demux.TestProject}" == project:
            if demux.debug:
                print( f"{demux.TestProject} test project detected. Skipping." )
            continue

    FastQC( newFileList )
    prepareMultiQC( DemultiplexRunIdDir, newProjectNameList, RunIDShort )
    MultiQC( DemultiplexRunIdDir )


    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Quality Check finished ==\n")




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

    ORIGINAL COMMAND: /usr/bin/md5deep -r {DemultiplexRunIdDir} | /usr/bin/sed s {DemultiplexRunIdDir}  g | /usr/bin/grep -v md5sum | /usr/bin/grep -v script
    EXAMPLE: /usr/bin/md5deep -r /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex | /usr/bin/sed s /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/  g | /usr/bin/grep -v md5sum | /usr/bin/grep -v script

    """

    demux.n = demux.n + 1
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files started ==\n")

    if demux.debug:
        print( f"for debug puproses, creating empty files {DemultiplexRunIdDir}/foo.tar and {DemultiplexRunIdDir}/bar.zip" )
        pathlib.Path( f"{DemultiplexRunIdDir}/{demux.footarfile}" ).touch( )
        pathlib.Path( f"{DemultiplexRunIdDir}/{demux.barzipfile}" ).touch( )


    # build the filetree
    if demux.debug:
        print( f'= walk the file tree, {inspect.stack()[0][3]}() ======================')
    for directoryRoot, dirnames, filenames, in os.walk( DemultiplexRunIdDir, followlinks = False ):

        for file in filenames:
            if not any( var in file for var in [ demux.CompressedFastqSuffix, demux.zipSuffix, demux.tarSuffix ] ): # grab only .zip, .fasta.gz and .tar files
                continue

            filepath = os.path.join( directoryRoot, file )

            if not os.path.isfile( filepath ):
                print( f"{filepath} is not a file. Exiting.")
                sys.exit( )

            if os.path.getsize( filepath ) == 0 : # make sure it's not a zero length file 
                print( f"file {filepath} has zero length. Skipping.")
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

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Calculating md5/sha512 sums for .tar and .gz files finished ==\n")



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
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Changing Permissions started ==\n")

    if demux.debug:
        print( f'= walk the file tree, {inspect.stack()[0][3]}() ======================')

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
        print( f'= walk the dir tree, {inspect.stack()[0][3]}() ======================')
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

    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Changing Permissions finished ==\n")



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
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery started ==\n")

    DemultiplexRunIdDir        = os.path.join( demux.DemultiplexDir, f"{RunID}{demux.DemultiplexDirSuffix}" )   # This needs to be moved to __init__
    ForTransferRunIdDir        = os.path.join( demux.ForTransferDir, RunID )                                    # This needs to be moved to __init__
    # forTransferTarMD5File      = os.path.join( demultiplexTempDir, f"{RunID}{tarSuffix}{md5Suffix}" )
    # forTransferTarSHA512File   = os.path.join( demultiplexTempDir, f"{RunID}{tarSuffix}{sha512Suffix}" )
    forTransferQCtarFile       = os.path.join( ForTransferRunIdDir, f"{RunID}{demux.QCSuffix}{demux.tarSuffix}" )
    forTransferQCMD5tarFile    = os.path.join( ForTransferRunIdDir, f"{RunID}{demux.QCSuffix}{demux.tarSuffix}{demux.md5Suffix}" )
    forTransferQCSHA512tarFile = os.path.join( ForTransferRunIdDir, f"{RunID}{demux.QCSuffix}{demux.tarSuffix}{demux.sha512Suffix}" )
    counter = 0

    if demux.debug:
        print( f"Current working directory:\t{DemultiplexRunIdDir}")
        print( f"DemultiplexRunIdDir:\t\t{DemultiplexRunIdDir}" )
        print( f"ForTransferRunIdDir:\t\t{ForTransferRunIdDir}" )
        # print( f"tarFile:\t\t\t{tarFile}" )
        # print( f"tarQCFile:\t\t\t{tarQCFile}" )
        # print( f"forTransferTarFile:\t\t\t{forTransferTarFile}" )
        # print( f"forTransferTarMD5File:\t\t\t{forTransferTarMD5File}" )
        # print( f"forTransferTarSHA512File:\t\t\t{forTransferTarSHA512File}" )
        print( f"forTransferQCtarFile:\t\t{forTransferQCtarFile}" )
        print( f"forTransferQCMD5tarFile:\t{forTransferQCMD5tarFile}" )
        print( f"forTransferQCSHA512tarFile:\t{forTransferQCSHA512tarFile}" )

    if demux.debug:
        print( f"Original working directory:\t{ os.getcwd( ) }" )

    # Switch to the Demultiplex directory we will be archiving
    try:
        os.chdir( DemultiplexRunIdDir )
    except FileNotFoundError:
        print( f"Directory: {DemultiplexRunIdDir} does not exist. Exiting." )
        sys.exit( )
    except NotADirectoryError:
        print( f"{DemultiplexRunIdDir} is not a directory. Exiting." )
        sys.exit( )
    except DemultiplexRunIdDir:
        print( f"You do not have permissions to change to {DemultiplexRunIdDir}. Exiting." )
        sys.exit( )

    if demux.debug:
        print( f"Changed into directory\t\t{DemultiplexRunIdDir}")

    # Make {ForTransferRunIdDir} directory
    if not os.path.isdir( ForTransferRunIdDir ):
        os.mkdir( ForTransferRunIdDir )
    else:
        print( f"{ForTransferRunIdDir} exists, this is not supposed to exist, please investigate and re-run the demux. Exiting." )
        sys.exit( )


    projectList = os.listdir( "." )                     # get the contents of the DemultiplexRunIdDir directory
    if demux.debug:
        print( f"{DemultiplexRunIdDir} directory contents: {projectList}" ) 

    projectsToProcess = [ ]
    for project in projectList:                       # itterate over said DemultiplexRunIdDir contents
        if any( var in project for var in [ demux.TestProject ] ):          # skip the test project, 'FOO-blahblah-BAR'
            continue
        if any( var in project for var in [ demux.NextSeq, demux.MiSeq ] ): # if there is a nextseq or misqeq tag, add the directory to the newProjectNameList
            projectsToProcess.append( project )

    print( f"projectsToProcess:\t\t{ projectsToProcess }" )
    print( f"len(projectsToProcess):\t\t{len(projectsToProcess)}")

    for project in projectsToProcess:

        if demux.TestProject in project:       # disregard the debug Test Project # This is extra, but just in case.
            if demux.debug:
                print( f"\"{demux.TestProject}\" test project found. Skipping." )
            continue
        if demux.temp in project:              # disregard the temp directory # This is extra, but just in case.
            if demux.debug:
                print( f"\"{demux.temp}\" directory found. Skipping." )
            continue
        if demux.DemultiplexLogDir in project: # disregard demultiplex_log
            if demux.debug:
                print( f"\"{demux.DemultiplexLogDir}\" directory found. Skipping." )
            continue
        if demux.QCSuffix in project:          # disregard '_QC'
            if demux.debug:
                print( f"\"{demux.QCSuffix}\" directory found. Skipping." )
            continue


        try:
            os.mkdir( f"{ForTransferRunIdDir}/{project}" )  # we save each tar file into its own directory
        except FileExistsError as err:
            print( f"Error while trying to mkdir {ForTransferRunIdDir}/{project}")
            print( f"Error message: {err}")
            print ( "Exiting.")
            sys.exit( )

        tarFile = os.path.join( ForTransferRunIdDir, project )
        tarFile = os.path.join ( tarFile, f"{project}{demux.tarSuffix}" )
        if demux.debug:
            print( f"tarFile: {tarFile}")

        if not os.path.isfile( tarFile ) :
            tarFileHandle = tarfile.open( name = tarFile, mode = "w:" )
        else:
            printf( f"{tarFile} exists. Please investigate or delete. Exiting." )
            sys.exit( )


        # we iterrate through all the renamed Sample_Project directories and make a single tar file for each directory
        # build the filetree
        if demux.debug:
            print( f"\n== walk the file tree, {inspect.stack()[0][3]}() ======================\n" )

        counter = counter + 1
        print( f"==> Archiving {project} ({counter} out of {len(projectsToProcess)} projects ) ==================" )
        for directoryRoot, dirnames, filenames, in os.walk( os.path.join( DemultiplexRunIdDir, project ), followlinks = False ): 
             for file in filenames:
                # add one file at a time so we can give visual feedback to the user that the script is processing files
                # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
                # of output that make users uncomfortable
                filenameToTar = os.path.join( project, file )
                tarFileHandle.add( name = filenameToTar, recursive = False )
                print( filenameToTar )

        tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
        print( f'==< Archived {project} ({counter} out of {len(projectsToProcess)} projects ) ==================\n' )

    sys.exit( )

    if not tarfile.is_tarfile( tarQCFile ):
        tarQCFileHandle = tarfile.open( tarQCFile, "w:" )
    else:
        printf( f"{tarQCFile} exists. Please investigate or delete. Exiting." )
        sys.exit( )
    ###########################################################
    # What to put inside the QC file
    ###########################################################
    # stuff *.zip and *.html into a giant flat tar file. 
    #       all filenames are guaranteed to be unique
    # build the filetree
    if demux.debug:
        print( f"= walk the file tree, {inspect.stack()[0][3]}() ======================\n")
    # for directoryRoot, dirnames, filenames, in os.walk( DemultiplexRunIdDir, followlinks = False ):

    tarQCFileHandle.write( )
    tarQCFileHandle.close( )    # whatever happens make sure we have closed the handle before moving on

    # assuming nobody was able to create the files in a milisecond worth of amount of time
    source      = [ tarFile, tarQCFile ]
    destination = demultiplexTempDir
    shutil.copy2( source, destination )
    ###########################################################
    # md5/sha512 the tar and the QC file
    ###########################################################
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Hashing tar and QC files started ==\n")
    calcFileHash( demultiplexTempDir )
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Hashing tar and QC files finished ==\n")

    ###########################################################
    # move tar/QC/md5/sha512
    ###########################################################

    source = [ forTransferTarFile, forTransferTarMD5File, forTransferTarSHA512File, forTransferQCtarFile, forTransferQCMD5tarFile, forTransferQCSHA512tarFile ]
    destination = ForTransferRunIdDir
    shutil.copy2( source, destination )

    if not os.path.isdir( ForTransferRunIdDir ):
        print( f"{ForTransferRunIdDir} exists, this is not supposed to exist, please investiage and re-run the demux. Exiting." )
        os.exit( )

    ###########################################################
    # cleanup
    ###########################################################
    try:
        shutil.rmtree( demultiplexTempDir )
    except OSError as error:
        print( f"{demultiplexTempDir} cannot be removed. Exiting." )
        os.exit( )
 
    print( f"==< {demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery finished ==\n")



########################################################################
# script_completion_file
########################################################################

def scriptComplete( DemultiplexDir):
    """
    Create the {DemultiplexDir}/{demux.DemultiplexCompleteFile} file to signal that this script has finished
    """

    demux.n = demux.n + 1
    print( f"==> {demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery started ==\n")

    try: 
        Path( os.path.join ( DemultiplexDir, demux.DemultiplexCompleteFile )).touch( mode=644, exist_ok=False)
    except Exception as e:
        print( e.error )
        print( f"{DemultiplexDir}/{DemultiplexCompleteFile} already exists. Please delete it before running demux.\n")
        sys.exit( )
        # FIXMEFIXME notify_warning_system_that_error_occured( )

    print( f"{demux.n}/{demux.TotalTasks} tasks: Preparing files for delivery finished\n")



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

    # setattr( demux, RunID, RunID )

    # RunID
    RunIDShort             = '_'.join(RunID.split('_')[0:2]) # this should be turned into a setter in the demux object
 ######################################################
    RawDataLocationDirRoot = os.path.join( demux.DataRootDirPath, demux.RawDataDirName )
    SequenceRunOriginDir   = os.path.join( RawDataLocationDirRoot, RunID )
    SampleSheetFilePath    = os.path.join( SequenceRunOriginDir, demux.SampleSheetFileName )
    RTACompleteFilePath    = f"{SequenceRunOriginDir}/{demux.RTACompleteFile}"
######################################################
    DemultiplexDirRoot     = os.path.join( demux.DataRootDirPath, demux.DemultiplexDirName )
    DemultiplexRunIdDir    = os.path.join( DemultiplexDirRoot, RunID + demux.DemultiplexDirSuffix ) 
    DemultiplexLogDirPath  = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDir )
    DemultiplexLogFilePath = os.path.join( DemultiplexLogDirPath, demux.ScriptLogFile )
    DemultiplexQCDirPath   = f"{DemultiplexRunIdDir}/{RunIDShort}{demux.QCSuffix}"
    DemultiplexProjSubDirs = [ ]
######################################################
    ForTransferDirRoot     = os.path.join ( demux.DataRootDirPath, demux.ForTransferDirName )
    ForTransferDir         = os.path.join ( ForTransferDirRoot, RunID )
    ForTransferProjNames   = []
######################################################
    QC_tar_file_source     = f"{DemultiplexRunIdDir}/{RunIDShort}{demux.QCSuffix}{demux.tarSuffix}"        # dot is included in demux.tarSuffix string
    QC_md5_file_source     = f"{QC_tar_file_source}{demux.md5Suffix}"                                      # dot is included in demux.md5Suffix string
    QC_tar_file_dest       = f"{ForTransferDirRoot}/{RunID}/{RunIDShort}{demux.QCSuffix}{demux.tarSuffix}" # dot is included in demux.tarSuffix string
    QC_md5_file_dest       = f"{QC_tar_file_dest}{demux.md5Suffix}"                                        # dot is included in demux.md5Suffix string

    project_list           = demux.getProjectName( SampleSheetFilePath )
    if demux.debug and len(project_list) == 1:
        project_list.add( demux.TestProject ) # if debug, have at least two project names to ensure multiple paths are being created
    for project_name in project_list:         # build the full list of subdirectories to make under {DemultiplexRunIdDir}
        DemultiplexProjSubDirs.append( f"{DemultiplexRunIdDir}/{RunIDShort}.{project_name}" )

    # Build the paths for each of the projects. example: /data/for_transfer/{RunID}/{item}
    for project in project_list: 
        ForTransferProjNames.append( f"{DemultiplexRunIdDir}/{RunIDShort}.{project}" )


    print( f"\nTo rerun this script run\n\tclear; rm -rf {DemultiplexRunIdDir} && rm -rf {ForTransferDir} && /usr/bin/python3 /data/bin/demultiplex_script.py {RunID}\n\n")
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
        print( f"DemultiplexRunIdDir:\t\t{DemultiplexRunIdDir}" )
        print( f"DemultiplexLogDirPath:\t\t{DemultiplexLogDirPath}" )
        print( f"DemultiplexLogFilePath:\t\t{DemultiplexLogFilePath}" )
        print( f"DemultiplexQCDirPath:\t\t{DemultiplexQCDirPath}" )
        for index, directory in enumerate( DemultiplexProjSubDirs):
            print( f"DemultiplexProjSubDirs[{index}]:\t{directory}")
        print( "=============================================================================")
        print( f"QC_tar_file_source:\t\t{QC_tar_file_source}" )            # FIXME path and filename needs validating
        print( f"QC_md5_file_source:\t\t{QC_md5_file_source}" )            # FIXME path and filename needs validating
        print( f"QC_tar_file_dest:\t\t{QC_tar_file_dest}" )                # FIXME path and filename needs validating
        print( f"QC_md5_file_dest:\t\t{QC_md5_file_dest}" )                # FIXME path and filename needs validating
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
    if os.path.exists( DemultiplexRunIdDir ):
        print( f"{DemultiplexRunIdDir} exists. Delete the demultiplex folder before re-running the script" )
        sys.exit()

    #   create {DemultiplexDirRoot} directory structrure
    createDemultiplexDirectoryStructure( DemultiplexRunIdDir, RunIDShort, project_list  )
    #   copy SampleSheet.csv from {SampleSheetFilePath} to {DemultiplexRunIdDir} . bcl2fastq uses the file for demultiplexing
    try:
        demux.n = demux.n + 1
        shutil.copy2( SampleSheetFilePath, DemultiplexRunIdDir )
        print( f"==> {demux.n}/{demux.TotalTasks} tasks: {demux.SampleSheetFileName} copied to {DemultiplexRunIdDir}\n")
    except Exception as err:
        print( err )
        exit( )
    try:
        # Request by Cathrine: Copy the SampleSheet file to /data/SampleSheet automatically
        demux.n = demux.n + 1
        SampleSheetArchiveFilePath = os.path.join( demux.SampleSheetDirPath, f"{RunID}{demux.CSVSuffix}" ) # .dot is included in CSVsuffix
        shutil.copy2( SampleSheetFilePath, SampleSheetArchiveFilePath )
        print( f"==> {demux.n}/{demux.TotalTasks} tasks: Archive {SampleSheetFilePath} to {SampleSheetArchiveFilePath} ==\n" )
    except Exception as err:
        print( err )
        exit( )

    demultiplex( SequenceRunOriginDir, DemultiplexRunIdDir )
    newFileList, DemultiplexRunIdDirNewName = renameFiles( DemultiplexRunIdDir, RunIDShort, project_list )

    newProjectNamelist = [ ]
    for project in project_list:
        newProjectNamelist.append( f"{RunIDShort}.{project}")
    
    qualityCheck( newFileList, DemultiplexRunIdDirNewName, RunIDShort, newProjectNamelist )
    calcFileHash( DemultiplexRunIdDir )                                                                 # create .md5/.sha512 checksum files for every .fastqc.gz/.tar/.zip file under DemultiplexRunIdDir
    changePermissions( DemultiplexRunIdDir  )                                                           # change permissions for the files about to be included in the tar files 
    prepareDelivery( RunID )                                                                            # prepare the main delivery files
    sys.exit( )

    calcFileHash( DemultiplexRunIdDir )                                                                 # create .md5/.sha512 checksum files for the delivery .fastqc.gz/.tar/.zip files under DemultiplexRunIdDir, 2nd fime for the new .tar files created by prepareDelivery( )
    prepare_delivery(  RunIDShort + QCSuffix, DemultiplexRunIdDirNewName, QC_tar_file, QC_md5_file ) # prepare the QC files
    change_permission( QC_tar_file )                                                                    # change permissions for all the delivery files, including QC
    change_permission( QC_md5_file )
    deliverFilesToVIGASP( )
    deliverFilesToNIRD( )
    script_completion_file( DemultiplexDir )

    printf( "\n====== All done! ======\n" )



########################################################################
# MAIN
########################################################################

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    # FIXMEFIXME add named arguments
    RunID = sys.argv[1]
    main( RunID )
