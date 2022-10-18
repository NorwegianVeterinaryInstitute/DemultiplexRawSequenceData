#!/bin/env /bin/python3

import os
import sys
import shutil
import subprocess
import argparse
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
    SampleSheetFileName = 'SampleSheet.csv'

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
# execute
########################################################################

def execute(command, demultiplex_out_file):
    """
    Invoke the appropriate demux/QC command, while writing out to the log file.
        There used to be a reference to activating a conda environment here
        but got removed to make the execution environment less complex
    """
    demultiplex_out_file.write('    ' + command + '\n')
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()



########################################################################
# checkComplete
########################################################################

def checkComplete(SequenceRunOriginDir):
    """
    Check to see if the SequenceRunOriginDir/RTAComplete.txt file exists and return true/false,
    signaling that the sequencing run is complete or not.
    """
    RTACompleteFile = "RTAComplete.txt"
    if os.path.exists( os.path.join( SequenceRunOriginDir, RTACompleteFile ) ):
        return ( True )
    else:
        return ( False )



########################################################################
# createDirectory
########################################################################

def createDirectory(DemultiplexDir, RunId_short):
    """
    If the Demultiplexing directory or any relevant directory does not exist, create it
    """
    if os.path.isdir( DemultiplexDir ):
        return( False )
    else:
        QCSuffix    = '_QC'                  # this and next are duplicated.
        DemuxLogDir = 'demultiplex_log'      # could be throw them in an object
        QCDirectory = RunId_short + QCSuffix # joining the two previous strins
        # DemultiplexLogFile = os.path.join( ) 
        os.mkdir( DemultiplexDir )                              # root directory for run
        os.mkdir( os.path.join( DemultiplexDir, QCDirectory ) ) # QC directory   for run
        os.mkdir( os.path.join( DemultiplexDir, DemuxLogDir ) ) # log directory  for run



########################################################################
# demutliplex
########################################################################

def demutliplex( SequenceRunOriginDir, DemultiplexDir, demultiplex_out_file):
    """
    """
    source          = os.path.join( SequenceRunOriginDir, demux.SampleSheetFile )
    # destination   = DemultiplexDir
    shutil.copy2( source, DemultiplexDir ) # shutil.copy2() is the only method in Python 3 in which you are allowed to use a directory as a destionation https://stackoverflow.com/questions/123198/how-to-copy-files
    demultiplex_out_file.write('2/5 Tasks: Demultiplexing started\n')

    bcl2fastq_bin = '/usr/local/bin/bcl2fastq'
    argv = [
        '--no-lane-splitting',
        f"--runfolder-dir {SequenceRunOriginDir}"
        f"--output-dir {DemultiplexDir}"
    ]
    Bcl2FastqLogDirName  = 'demultiplex_log'
    Bcl2FastqLogFileName = '02_demultiplex.log'
    Bcl2FastqLogFile     = os.path.join( DemultiplexDir, os.path.join( Bcl2FastqLogDir, Bcl2FastqLogFileName ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + SequenceRunOriginDir + ' --output-dir ' + DemultiplexDir + ' 2> ' + DemultiplexDir + '/demultiplex_log/02_demultiplex.log'
        result = subprocess.run( bcl2fastq_bin, argv, stdout = cron_out_file, stderr = Bcl2FastqLogFile, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
    except ChildProcessError as err: 
        text = [ "Caught exception!",
            f"Command: {err.cmd}", # interpolated strings
            f"Return code: {err.returncode}"
            f"Process output: {err.output}",
        ]
        print( '\n'.join( text ) )
    demultiplex_out_file.write( result.output )

    demultiplex_out_file.write('2/5 Tasks: Demultiplexing complete\n')



########################################################################
# moveFiles
########################################################################

def moveFiles(DemultiplexDir, RunId_short, project_list, demultiplex_out_file):
    """
    Move?Rename? files FIXMEFIXMEFIXME more info when debugging
    """
    CompressedFastqSuffix = 'fastq.gz' 

    for root, dirs, files in os.walk(DemultiplexDir):
        for name in files:

            if CompressedFastqSuffix in name:
                source = os.path.join( root, name )
                destination = os.path.join( root, '.'.join( [ RunId_short, name ] ) )
                if demux.debug:
                    print( f"/usr/bin/mv {source} {destination}")
                else:
                    try:
                        # EXAMPLE: /usr/bin/mv root/name root/RunId_short.name
                        result = shutil.move( source, destination )
                    except ChildProcessError as err: 
                        text = [ "Caught exception!",
                                f"Command: { err.cmd }", # interpolated strings
                                f"Return code: { err.returncode }"
                                f"Process output: { err.output }",
                        ]

    for project in project_list:

        # /usr/bin/mv DemultiplexDir/project.split('.')[0] DemultiplexDir/RunId_short.project
        source      = os.path.join( DemultiplexDir, project.split('.')[0] )
        destination = os.path.join( DemultiplexDir, '.'.join( RunId_short, project  ) )
        if demux.debug:
            print( f"/usr/bin/mv {source} {destination}")
        else:
            try:
                # EXAMPLE: /usr/bin/mv root/name root/RunId_short.name
                result = shutil.move( source, destination )
            except ChildProcessError as err: 
                text = [ "Caught exception!",
                        f"Command: { err.cmd }", # interpolated strings
                        f"Return code: { err.returncode }"
                        f"Process output: { err.output }",
                ]

    demultiplex_out_file.write('3/5 Tasks: Moving files complete\n')

    if demux.debug:
        exit()



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

def script_completion_file(DemultiplexDir, demultiplex_out_file):
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

def prepare_delivery(folder, DemultiplexDir , tar_file, md5_file, demultiplex_out_file):
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

def change_permission(folder_or_file, demultiplex_out_file):
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

def main(RunId):
    """
    Main function for the demultiplex script.
    All actions are coordinated through here
    """

    DataRootDirPath        = '/data'
    RawDataDirName         = 'rawdata'
    DemultiplexDirName     = "demultiplex"
    ForTransferDirName     = 'for_transfer'
    DemultiplexDirSuffix   = '_demultiplex'
    DemultiplexLogDir      = 'demultiplex_log'
    ScriptLogFile          = 'script.log'
    QCDirSuffix            = '_QC'
    tarExtension           = '.tar'
    md5Extension           = '.md5'
    # RunId
    DemultiplexRunIdDir    = os.path.join( DataRootDirPath, os.path.join( DemultiplexDirName, RunId + DemultiplexDirSuffix ) )
    DemultiplexLogDirPath  = os.path.join( DemultiplexRunIdDir, DemultiplexLogDir )
    DemultiplexLogFilePath = os.path.join( DemultiplexLogDirPath, ScriptLogFile )
    ForTransferDirRoot     = os.path.join ( DataRootDirPath, ForTransferDirName )
    RawDataLocationDirRoot = os.path.join( DataRootDirPath, RawDataDirName )
    DemultiplexDirRoot     = os.path.join( DataRootDirPath, DemultiplexDirName )
    RunId_short            = '_'.join(RunId.split('_')[0:2])
    SequenceRunOriginDir   = os.path.join( RawDataLocationDirRoot, RunId )
    SampleSheetFilePath    = os.path.join( SequenceRunOriginDir, demux.SampleSheetFileName )
    QC_tar_file_source     = f"{DemultiplexRunIdDir}/{RunId_short}{QCDirSuffix}{tarExtension}" # dot is stored in tarExtension
    QC_md5_file_source     = f"{QC_tar_file_source}{md5Extension}" # dot is stored in md5Extension
    QC_tar_file_dest       = f"{ForTransferDirRoot}/{RunId}/{RunId_short}{QCDirSuffix}{tarExtension}"
    QC_md5_file_dest       = f"{QC_tar_file_dest}{md5Extension}" # dot is stored in md5Extension


    project_list           = demux.getProjectName( SampleSheetFilePath )
    if demux.debug:
        project_list.add( "FOO-blahblah-BAR" ) # if debug, have at least two project names to ensure multiple paths are being created

    DemuxProjectNames       = []
    # Build the paths for each of the projects. example: /data/for_transfer/{RunId}/{item}
    for item in project_list: 
        DemuxProjectNames.append( f"{ForTransferDirRoot}/{RunId}/" + str(item) )

    if demux.debug: # print the values here # FIXME https://docs.python.org/3/tutorial/inputoutput.html "Column output in Python3"
            print( f"RunId:\t\t\t{RunId}")
            print( f"RunId_short:\t\t{RunId_short}")
            print( f"project_list:\t\t{project_list}")
            print( "=============================================================================")
            print( f"DemultiplexDirRoot:\t{DemultiplexDirRoot}")
            print( f"DemultiplexRunIdDir:\t{DemultiplexRunIdDir}")
            print( f"DemultiplexLogDirPath:\t{DemultiplexLogDirPath}")
            print( f"DemultiplexLogFilePath:\t{DemultiplexLogFilePath}")
            print( f"DemuxProjectNames:\t{DemuxProjectNames}")
            print( "=============================================================================")
            print( f"RawDataLocationDirRoot:\t{RawDataLocationDirRoot}")
            print( f"SequenceRunOriginDir:\t{SequenceRunOriginDir}")
            print( f"SampleSheetFilePath:\t{SampleSheetFilePath}")
            print( "=============================================================================")
            print( f"QC_tar_file_source:\t{QC_tar_file_source}")
            print( f"QC_md5_file_source:\t{QC_md5_file_source}")
            print( f"QC_tar_file_dest:\t{QC_tar_file_dest}")
            print( f"QC_md5_file_dest:\t{QC_md5_file_dest}")
    sys.exit( )

    project_name           = f"{RunId_short}.{project_list}"
    tar_file               = os.path.join( DataRootDirPath, os.path.join( ForTransferDirRoot, project_name + tarExtension ) )
    md5_file               = f"{tar_file}.{tarExtension}"

    # init:
    #   check if /data/demultiplex exists
    #       exit if not
    #   create directory structrure
    #       /data/demultiplex/{RunId}_{DemultiplexDirSuffix}
    #       /data/demultiplex/{RunId}_{DemultiplexDirSuffix}/{DemultiplexLogDir}

    if checkComplete( SequenceRunOriginDir ) is False:
        print( f"{RunId} is not finished sequencing yet!" ) 
        sys.exit()

    demultiplex_out_file = open( DemultiplexLogFilePath , 'w')
    if createDirectory( DemultiplexDirPath ) is False:
        print( f"{DemultiplexDirPath} exists. Delete the demultiplex folder before re-running the script" )
        sys.exit()
    else:
        demultiplex_out_file.write('1/5 Tasks: Directories created\n')

    demutliplex( SequenceRunOriginDir, DemultiplexDir, demultiplex_out_file )
    moveFiles(   DemultiplexDir, RunId_short, project_list, demultiplex_out_file )
    qc(          DemultiplexDir, RunId_short, project_list, demultiplex_out_file )
    change_permission( DemultiplexDir, demultiplex_out_file )

    for project in project_list:

        create_md5deep(    DemultiplexDirPath, demultiplex_out_file )
        prepare_delivery(  project_name, DemultiplexDir, tar_file, md5_file, demultiplex_out_file )
        change_permission( tar_file, demultiplex_out_file )
        change_permission( md5_file, demultiplex_out_file )

    prepare_delivery(  RunId_short + QCDirSuffix, DemultiplexDir, QC_tar_file, QC_md5_file, demultiplex_out_file )
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
