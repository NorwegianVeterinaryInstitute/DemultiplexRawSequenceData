#!/bin/env /bin/python3

import os
import sys
import shutil
import subprocess
import argparse
import glob
from pathlib import Path

# INPUTS:
#   - Run name eg python /mnt/data/demultiplex/scripts/demultiplex_script_v2.py 200306_M06578_0015_000000000-CWLBG
#
# OUTPUTS:
#   - .fastq files for the run
#
#
# WHAT DOES THIS SCRIPT DO
#
#
# HOW DOES THE  SCRIPT DO WHAT IT DOES
#   - script returns output to calling script via pipe
#
# LIMITATIONS
#   - Can demultipex one directory at a time only
#   - No sanity checking to see if a demultiplexed directory is correctly demux'ed
#       - Relies only on output directory name and does not verify contents
#
#
# Needs: 
#   turn stuff into an object
#       then module
#   log to syslog
# 
#

class demux:
    """
    demux: make an object of the entire demultiplex process.
    """
    debug = True
    ######################################################
    DataRootDirPath         = '/data'
    RawDataDirName          = 'rawdata'
    DemultiplexDirName      = "demultiplex"
    ForTransferDirName      = 'for_transfer'
    ######################################################
    DemultiplexDirSuffix    = '_demultiplex'
    DemultiplexLogDir       = 'demultiplex_log'
    SampleSheetFileName     = 'SampleSheet.csv'
    RTACompleteFile         = 'RTAComplete.txt'
    ScriptLogFile           = 'script.log'
    QCDirSuffix             = '_QC'
    tarSuffix               = '.tar'
    md5Suffix               = '.md5'
    CompressedFastqSuffix   = 'fastq.gz' 
    ######################################################
    bcl2fastq_bin           = f"{DataRootDirPath}/bin/bcl2fastq"


    def __init__( self, RunId ):
        """
        __init__
            Check for existance of RunID
                Complain if not
            Checks to see if debug or not is set
        """
        self.RunID = RunId # this needs more reading, about globals and init'ing
        self.debug = True
        #self.debug = True
        # self.demultiplex_out_file = 


    ########################################################################
    # getProjectName
    ########################################################################
    def getProjectName( SampleSheetFilePath ):
        """
        Get the associated project name from SampleSheet.csv

        Requires:
           /data/rawdata/RunId/SampleSheet.csv

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

        project_line_check = False
        project_index  = ''
        # analysis_index = ''
        project_list   = []

        for line in open( SampleSheetFilePath, 'r', encoding="utf-8" ):
            line = line.rstrip()
            if project_line_check == True:
                project_list.append(line.split(',')[project_index] )# + '.' + line.split(',')[analysis_index]) # this is the part where .x shows up. Removed.
            if 'Sample_Project' in line:
                project_index      = line.split(',').index('Sample_Project')
                # analysis_index   = line.split(',').index('Analysis') # this is the part where .x shows up. Removed.
                project_line_check = True

        return( set( project_list ) )



########################################################################
# createDirectory
########################################################################

def createDemultiplexDirectoryStructure( DemultiplexRunIdDir, RunIDShort, project_list ):
    """
    If the Demultiplexing directory or any relevant directory does not exist, create it
        RunIDShort format is in the pattern of (date +%y%m%d)_SEQUENCERSERIALNUMBER Example: 220314_M06578
        {DemultiplexDirRoot} == "/data/demultiplex" # default

        {DemultiplexDirRoot}/{RunId}_{DemultiplexDirSuffix}/
        {DemultiplexDirRoot}/{RunId}_{DemultiplexDirSuffix}/{RunIDShort}.project_list[0]
        {DemultiplexDirRoot}/{RunId}_{DemultiplexDirSuffix}/{RunIDShort}.project_list[1]
        .
        .
        .
        {DemultiplexDirRoot}{RunId}_{DemultiplexDirSuffix}/{RunIDShort}.project_list[ len(project_list) -1 ]
        {DemultiplexDirRoot}{RunId}_{DemultiplexDirSuffix}/{DemultiplexLogDir}
        {DemultiplexDirRoot}{RunId}_{DemultiplexDirSuffix}/{RunIDShort}{demux.QCDirSuffix}
        {DemultiplexDirRoot}{RunId}_{DemultiplexDirSuffix}/Reports      # created by bcl2fastq
        {DemultiplexDirRoot}{RunId}_{DemultiplexDirSuffix}/Stats        # created by bcl2fastq
    """

    DemuxQCDirectory = RunIDShort + demux.QCDirSuffix                        # FIXMEFIXME move this to a setter in demux object
    os.mkdir( DemultiplexRunIdDir )                                          # root directory for run
    for Project_Sample in project_list: 
        os.mkdir( os.path.join( DemultiplexRunIdDir, Project_Sample ) )      # create a subdirectory for each of Project_Sample
    os.mkdir( os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDir ) ) # log directory for run
    os.mkdir( os.path.join( DemultiplexRunIdDir, DemuxQCDirectory  ) )       # QC directory  for run
                                                                             # 



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
    # demultiplex_out_file.write('2/5 Tasks: Demultiplexing started\n')
    print( "2/5 Tasks: Demultiplexing started" )

    argv = [ demux.bcl2fastq_bin,
         "--no-lane-splitting",
         "--runfolder-dir",
        f"{SequenceRunOriginDir}",
         "--output-dir",
        f"{DemultiplexRunIdDir}"
    ]
    Bcl2FastqLogFileName = '02_demultiplex.log'
    Bcl2FastqLogFile     = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDir, Bcl2FastqLogFileName )
    if demux.debug:
        print( f"Bcl2FastqLogFile:\t{Bcl2FastqLogFile}")
        print( f"Command to execute:\t" + " ".join( argv ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + SequenceRunOriginDir + ' --output-dir ' + DemultiplexDir + ' 2> ' + DemultiplexDir + '/demultiplex_log/02_demultiplex.log'
        result =  subprocess.run( argv, capture_output = True, text = True, cwd = SequenceRunOriginDir, check = True, encoding = "utf-8" )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
            f"Command: {err.cmd}", # interpolated strings
            f"Return code: {err.returncode}"
            f"Process output: {err.stdout}",
            f"Process error:  {err.stderr}"
        ]
        print( '\n'.join( text ) )

    handle = open( Bcl2FastqLogFile , 'w')
    handle.write('2/5 Tasks: Demultiplexing started\n')
    handle.write( result.stderr )
    handle.write('2/5 Tasks: Demultiplexing complete\n')

    print( "2/5 Tasks: Demultiplexing complete" )


########################################################################
# moveFiles
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

    print( '3/5 Tasks: Moving files started\n' )
    oldname = ""
    newname = ""
    newNameList = [ ]

    # rename files in each project directory
    for project in project_list:

        CompressedFastQfiles = glob.glob( f'{DemultiplexRunIdDir}/{project}/sample*.{demux.CompressedFastqSuffix}' ) # example: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/sample*fastq.gz

        if demux.debug:
            print( f"fastq files for {project}: {DemultiplexRunIdDir}/{project}/sample*.{demux.CompressedFastqSuffix}" )
            print( f"\t{CompressedFastQfiles}" )

        for file in CompressedFastQfiles:
    
            # get the base filename. We picked up sample*.{CompressedFastqSuffix} and we have to rename it to {RunIDShort}sample*.{CompressedFastqSuffix}
            baseFileName = os.path.basename( file )
            if demux.debug:
                print( f"baseFilename:\t{baseFileName}")

            oldname = f"{file}"
            newname = f"{DemultiplexRunIdDir}/{project}/{RunIDShort}.{baseFileName}"
            newfoo  = f"{DemultiplexRunIdDir}/{RunIDShort}.{project}/{RunIDShort}.{baseFileName}" # saving this var in order to print the location during debugging

            if demux.debug:
                print( f"name:\t{file}")
                print( f"/usr/bin/mv {oldname} {newfoo}" )
            

            # make sure oldname files exist
            # make sure newname files do not exist
            oldfileExists = os.path.isfile( oldname )
            newfileExists = os.path.isfile( newname )

            if oldfileExists and not newfileExists:
                try: 
                    os.rename( oldname, newname )
                except FileNotFoundError as err:
                    print( f"Error during renaming {oldname}:")
                    print( f"oldname: {oldname}\noldfileExists: {oldfileExists}" )
                    print( f"newfoo : {newfoo }\nnewfileExists: {newfileExists}" )
                    print( "err.filename:  {err.filename}" )
                    print( "err.filename2: {err.filename2}" )
                    print( "Exiting!" )

                newNameList.append( newfoo ) # save it to return the list, so we will not have to recreate the filenames

                if demux.debug:
                    print( f"\nRenaming {oldname} to {newfoo}\n" )

    for project in project_list:

        oldname = f"{DemultiplexRunIdDir}/{project}"
        newname = f"{DemultiplexRunIdDir}/{RunIDShort}.{project}"
        # make sure oldname dir exists
        # make sure newname dir name does not exist
        olddirExists = os.path.isdir( oldname )
        newdirExists = os.path.isdir( newname )

        if olddirExists and not newdirExists: # rename directory

            try: 
                os.rename( oldname, newname )
                if demux.debug:
                    print( f"Renaming {oldname} to {newname}")
            except FileNotFoundError as err:
                print( f"Error during renaming {oldname}:")
                print( f"oldname: {oldname}\noldfileExists: {oldfileExists}" )
                print( f"newfile: {newname}\nnewfileExists: {newfileExists}" )
                print( "err.filename:  {err.filename}")
                print( "err.filename2: {err.filename2}")
                print( "Exiting!")

            if demux.debug:
                print( f"\nRenaming {oldname} to {newname}\n" )
    print( '3/5 Tasks: Moving files complete\n' )
    return newNameList



########################################################################
# qc
########################################################################

def qc(DemultiplexDir, RunId_short, project_list, demultiplex_out_file):
    """
    Run QC on the sequence run files
    """

    for project in project_list:
        project_folder = DemultiplexDir + '/' + RunId_short + '.' + project


        try:
            command = '/usr/local/bin/fastqc'
            args = [ '-t 4', 
                    f"{project_folder}/*fastq.gz"
            ]
            # EXAMPLE: /usr/local/bin/fastqc -t 4 project_folder/*fastq.gz > DemultiplexDir/demultiplex_log/04_fastqc.log
            result = subprocess.run( command, args, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
        except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: { err.cmd }", # interpolated strings
                     f"Return code: { err.returncode }"
                     f"Process output: { err.output }",
            ]

        # EXAMPLE: /usr/bin/cp project_folder/*zip project_folder/*html DemultiplexDir/RunId_short_QC # (destination is a directory)
        zipFiles = f"{project_folder}/*zip"                     # source of zip files
        destination = f"{DemultiplexDir}/{RunId_short}_QC"   # destination folder
        for source in os.list ( zipFiles ):
            shutil.copy2( source, destination )                 # copy zip files
        HTLMfiles = f"{project_folder}/*html"
        for source in os.list ( HTLMfiles ):
            shutil.copy2( source, destination )                 # copy htlm files required by multiqc

        try:
            command = '/usr/local/bin/multiqc'
            args = [ project_folder,
                    f"-o {project_folder}" 
            ]

            # EXAMPLE: /usr/local/bin/multiqc project_folder -o project_folder 2> DemultiplexDir/demultiplex_log/05_multiqc.log
            result = subprocess.run( command, args, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
        except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: { err.cmd }", # interpolated strings
                     f"Return code: { err.returncode }"
                     f"Process output: { err.output }",
            ]
        demultiplex_out_file.write('4/5 Tasks: FastQC complete\n')

        # EXAMPLE: /usr/local/bin/multiqc DemultiplexDir/RunId_short_QC -o DemultiplexDir /RunId_short_QC 2> DemultiplexDir/demultiplex_log/05_multiqc.log
        try:
            command = '/usr/local/bin/multiqc'
            args = [ project_folder,
                    f"-o {project_folder}" 
            ]

            # EXAMPLE: /usr/local/bin/multiqc project_folder -o project_folder 2> DemultiplexDir/demultiplex_log/05_multiqc.log
            result = subprocess.run( command, args, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
        except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: { err.cmd }", # interpolated strings
                     f"Return code: { err.returncode }"
                     f"Process output: { err.output }",
            ]

        demultiplex_out_file.write('5/5 Tasks: MultiQC complete\n')



########################################################################
# create_md5deep
########################################################################

def create_md5deep( directory , demultiplex_out_file):
    """
    """
    md5File     = 'md5sum.txt'
    md5deep_out = os.path.join( directory, md5File )
    sed_bin     = '/usr/bin/sed'
    sed_command = [ sed_bin , f"s {directory}/  g" ]


    try:
        userid  = 'sambauser01'
        groupid = 'sambagroup'

        # FIXME check if folder_or_file exists
        # EXAMPLE: /bin/chown -R sambauser01:sambagroup folder_or_file
        result = os.chown( command, uid = userid, gid = groupid ) #uid = self.userid, gid = self.groupid )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
                 f"Command: { err.cmd }", # interpolated strings
                 f"Return code: { err.returncode }"
                 f"Process output: { err.output }",
        ]
    # FIXMEFIXMEFIXME this is not done

    if demux.debug: # DEBUG DEBUG DEBUG
        print ( f"/usr/bin/md5deep -r {directory} | {sed_command} | /usr/bin/grep -v md5sum | /usr/bin/grep -v script > md5deep_out " )
        exit( )
    else:
        command = f"/usr/bin/md5deep -r {directory} | {sed_command} | /usr/bin/grep -v md5sum | /usr/bin/grep -v script > md5deep_out "
        #argv    = 
        try:
            # FIXME check if folder_or_file exists
            # EXAMPLE: /bin/md5deep -r directory | sed_command | grep -v md5sum | grep -v script > md5deep_out
            result = subprocess.run( command, argv, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
        except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: { err.cmd }",           # interpolated strings
                     f"Return code: { err.returncode }"
                     f"Process output: { err.output }",
            ]



########################################################################
# script_completion_file
########################################################################

def script_completion_file( DemultiplexDir, demultiplex_out_file ):
    """
    """
    DemultiplexCompleteFile = 'DemultiplexComplete.txt'
    try: 
        Path( os.path.join ( DemultiplexDir, DemultiplexCompleteFile )).touch( mode=644, exist_ok=False)
    except Exception as e:
        print( e.error )
        print( f"{DemultiplexDir}/{DemultiplexCompleteFile} already exists. Please delete it before running demux.\n")
        exit( )
        # FIXMEFIXME notify_warning_system_that_error_occured( )



########################################################################
# prepare_delivery
########################################################################

def prepare_delivery( folder, DemultiplexDir , tar_file, md5_file, demultiplex_out_file ):
    """
    """
    # EXAMPLE: /bin/tar -cvf tar_file -C DemultiplexDir folder 
    execute('/bin/tar -cvf ' + tar_file + ' -C ' + DemultiplexDir + ' ' + folder , demultiplex_out_file)
    #sed_command = '/bin/sed "s /mnt/data/demultiplex/for_transfer/  g" '
    sed_command = '/bin/sed "s /data/for_transfer/  g" '
    # EXAMPLE: /bin/md5sum tar_file | sed_command > md5_file
    execute('/bin/md5sum ' + tar_file + ' | ' + sed_command + ' > ' + md5_file, demultiplex_out_file)



########################################################################
# change_permission
########################################################################

def change_permission( folder_or_file, demultiplex_out_file ):
    """
    """

    command1 = '/usr/bin/chown'
    command2 = '/usr/bin/chmod'
    user     = 'sambauser01'
    group    = 'sambagroup'
    argv1    = [ '-R', f"{user}:{group}", folder_or_file ]
    argv2    = [ '-R g+rwX', f"{group}", folder_or_file ]

    # TRY TO SEE IF THERE IS A RECURSIVE CHOWN call in Python
    try:
        # EXAMPLE: /bin/chown -R sambauser01:sambagroup ' + folder_or_file
        result = subprocess.run( command1, argv1, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
                 f"Command: { err.cmd }", # interpolated strings
                 f"Return code: { err.returncode }"
                 f"Process output: { err.output }",
        ]

    try:
        # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
        result = subprocess.run( command2, argv2, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
                 f"Command: { err.cmd }", # interpolated strings
                 f"Return code: { err.returncode }"
                 f"Process output: { err.output }",
        ]

        
        print( '\n'.join( text ) )


########################################################################
# MAIN
########################################################################

def main( RunId ):
    """
    Main function for the demultiplex script.
    All actions are coordinated through here
    """

    # RunId
    RunIDShort             = '_'.join(RunId.split('_')[0:2]) # this should be turned into a setter in the demux object
 ######################################################
    DemultiplexDirRoot     = os.path.join( demux.DataRootDirPath, demux.DemultiplexDirName )
    DemultiplexRunIdDir    = os.path.join( DemultiplexDirRoot, RunId + demux.DemultiplexDirSuffix ) 
    DemultiplexLogDirPath  = os.path.join( DemultiplexRunIdDir, demux.DemultiplexLogDir )
    DemultiplexLogFilePath = os.path.join( DemultiplexLogDirPath, demux.ScriptLogFile )
    DemultiplexQCDirPath   = f"{DemultiplexRunIdDir}/{RunIDShort}{demux.QCDirSuffix}"
    DemultiplexProjSubDirs = [ ]
######################################################
    RawDataLocationDirRoot = os.path.join( demux.DataRootDirPath, demux.RawDataDirName )
    SequenceRunOriginDir   = os.path.join( RawDataLocationDirRoot, RunId )
    SampleSheetFilePath    = os.path.join( SequenceRunOriginDir, demux.SampleSheetFileName )
    RTACompleteFilePath    = f"{SequenceRunOriginDir}/{demux.RTACompleteFile}"
######################################################
    ForTransferDirRoot     = os.path.join ( demux.DataRootDirPath, demux.ForTransferDirName )
    ForTransferDir         = os.path.join ( ForTransferDirRoot, RunId )
    ForTransferProjNames   = []
######################################################
    QC_tar_file_source     = f"{DemultiplexRunIdDir}/{RunIDShort}{demux.QCDirSuffix}{demux.tarSuffix}" # dot is included in demux.tarSuffix string
    QC_md5_file_source     = f"{QC_tar_file_source}{demux.md5Suffix}" # dot is included in demux.md5Suffix string
    QC_tar_file_dest       = f"{ForTransferDirRoot}/{RunId}/{RunIDShort}{demux.QCDirSuffix}{demux.tarSuffix}" # dot is included in demux.tarSuffix string
    QC_md5_file_dest       = f"{QC_tar_file_dest}{demux.md5Suffix}"   # dot is included in demux.md5Suffix string

    project_list           = demux.getProjectName( SampleSheetFilePath )
    if demux.debug and len(project_list) == 1:
        project_list.add( "FOO-blahblah-BAR" ) # if debug, have at least two project names to ensure multiple paths are being created
    for project_name in project_list: # build the full list of subdirectories to make under {DemultiplexRunIdDir}
        DemultiplexProjSubDirs.append( f"{DemultiplexRunIdDir}{RunIDShort}.{project_name}" )

    # Build the paths for each of the projects. example: /data/for_transfer/{RunId}/{item}
    for item in project_list: 
        ForTransferProjNames.append( f"{ForTransferDirRoot}/{RunId}/" + str(item) )

    if demux.debug: # print the values here # FIXME https://docs.python.org/3/tutorial/inputoutput.html "Column output in Python3"
        print( "=============================================================================")
        print( f"RunId:\t\t\t{RunId}")
        print( f"RunIDShort:\t\t{RunIDShort}")
        print( f"project_list:\t\t{project_list}")
        print( "=============================================================================")
        print( f"DemultiplexDirRoot:\t{DemultiplexDirRoot}" )
        print( f"DemultiplexRunIdDir:\t{DemultiplexRunIdDir}" )
        print( f"DemultiplexLogDirPath:\t{DemultiplexLogDirPath}" )
        print( f"DemultiplexLogFilePath:\t{DemultiplexLogFilePath}" )
        print( f"DemultiplexQCDirPath:\t{DemultiplexQCDirPath}" )
        print( f"DemultiplexProjSubDirs:\t{DemultiplexProjSubDirs}")
        print( "=============================================================================")
        print( f"RawDataLocationDirRoot:\t{RawDataLocationDirRoot}" )
        print( f"SequenceRunOriginDir:\t{SequenceRunOriginDir}" )
        print( f"SampleSheetFilePath:\t{SampleSheetFilePath}" )
        print( f"RTACompleteFilePath:\t{SequenceRunOriginDir}/{demux.RTACompleteFile}" )
        print( "=============================================================================")
        print( f"QC_tar_file_source:\t{QC_tar_file_source}" )            # FIXME path and filename needs validating
        print( f"QC_md5_file_source:\t{QC_md5_file_source}" )            # FIXME path and filename needs validating
        print( f"QC_tar_file_dest:\t{QC_tar_file_dest}" )                # FIXME path and filename needs validating
        print( f"QC_md5_file_dest:\t{QC_md5_file_dest}" )                # FIXME path and filename needs validating
        print( "=============================================================================")
        print( f"ForTransferDirRoot:\t{ForTransferDirRoot}" )
        print( f"ForTransferDir:\t\t{ForTransferDir}" )
        print( f"ForTransferProjNames:\t{ForTransferProjNames}" )
        print( "=============================================================================\n")

    # init:

    #   check if sequencing run has completed, exit if not
    #       Completion of sequencing run is signaled by the existance of the file {RTACompleteFilePath} ( SequenceRunOriginDir}/{demux.RTACompleteFile} )
    if not os.path.isfile( f"{RTACompleteFilePath}" ):
        print( f"{RunId} is not finished sequencing yet!" ) 
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
        shutil.copy2( SampleSheetFilePath, DemultiplexRunIdDir )
    except Exception as err:
        print( err ) # FIXMEFIXME more detail on the exception here, please


    # try:
    #   demultiplex_out_file = open( DemultiplexLogFilePath , 'w') # FIXME replace with syslog 
    # except Exception as err:
    #
    # demultiplex_out_file.write('1/5 Tasks: Directories created\n')
    print( '1/5 Tasks: Demultiplex directory structure created')
    
    demultiplex( SequenceRunOriginDir, DemultiplexRunIdDir )
    newFileList = renameFiles( DemultiplexRunIdDir, RunIDShort, project_list )
    print( f"\nnewFileList: {newFileList}\n")
    sys.exit( )
    qc(          DemultiplexDir, RunIDShort, project_list , demultiplex_out_file )
    change_permissions( DemultiplexDir , demultiplex_out_file ) # need only base dir, everything else is recursively changed.

    for project in project_list:

        create_md5deep( DemultiplexDirPath, demultiplex_out_file )
        prepare_delivery(  project_name, DemultiplexDir, tar_file, md5_file, demultiplex_out_file )
        change_permission( tar_file, demultiplex_out_file )
        change_permission( md5_file, demultiplex_out_file )

    prepare_delivery(  RunIDShort + QCDirSuffix, DemultiplexDir, QC_tar_file, QC_md5_file, demultiplex_out_file )
    change_permission( QC_tar_file, demultiplex_out_file )
    change_permission( QC_md5_file, demultiplex_out_file )

    script_completion_file(DemultiplexDir, demultiplex_out_file)

    demultiplex_out_file.write('\nAll done!\n')
    demultiplex_out_file.close()



########################################################################
# MAIN
########################################################################

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    # FIXMEFIXME add named arguments
    RunId = sys.argv[1]
    main(RunId)
