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

    def __init__( self ):
        """
        __init__
            Check for existance of RunID
                Complain if not
            Checks to see if debug or not is set
        """
        #self.RunID =
        #self.debug = sys.argsv[ 'debug' ]
        #self.debug = True
        # self.demultiplex_out_file = 


########################################################################
# getProjectName
########################################################################

def getProjectName( DemultiplexFolder ):
    """
    Get the associated project name from SampleSheet.csv

    Parsing is simple:
        go line-by-line
        ignore all the we do not need until
            we hit the line that contains 'Sample_Project'
            if 'Sample_Project' found
                split the line and 
                    take the value of 'Sample_Project'
                    take the value of 'Analysis'

        return an set of the values of all values of 'Sample_Project' and 'Analysis'
    """

    project_line_check = False
    project_index  = ''
    analysis_index = ''
    project_list   = []
    SampleSheetFileName = 'SampleSheet.csv'
    SampleSheetFilePath = os.path.join( DemultiplexFolder, SampleSheetFileName )

    for line in open( SampleSheetFilePath, 'r', encoding="utf-8" ):
        line = line.rstrip()
        if project_line_check == True:
            project_list.append(line.split(',')[project_index] + '.' + line.split(',')[analysis_index])
        if 'Sample_Project' in line:
            project_index      = line.split(',').index('Sample_Project')
            analysis_index     = line.split(',').index('Analysis')
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

def createDirectory(DemultiplexFolder, RunId_short):
    """
    If the Demultiplexing directory or any relevant directory does not exist, create it
    """
    if os.path.isdir( DemultiplexFolder ):
        return( False )
    else:
        QCSuffix    = '_QC'                  # this and next are duplicated.
        DemuxLogDir = 'demultiplex_log'      # could be throw them in an object
        QCDirectory = RunId_short + QCSuffix # joining the two previous strins
        # DemultiplexLogFile = os.path.join( ) 
        os.mkdir( DemultiplexFolder )                              # root directory for run
        os.mkdir( os.path.join( DemultiplexFolder, QCDirectory ) ) # QC directory   for run
        os.mkdir( os.path.join( DemultiplexFolder, DemuxLogDir ) ) # log directory  for run



########################################################################
# demutliplex
########################################################################

def demutliplex( RunFolder, DemultiplexFolder, demultiplex_out_file):
    """
    """
    SampleSheetFile = 'SampleSheet.csv'
    source          = os.path.join( RunFolder, SampleSheetFile )
    # destination   = DemultiplexFolder
    shutil.copy2( source, DemultiplexFolder ) # shutil.copy2() is the only method in Python 3 in which you are allowed to use a directory as a destionation https://stackoverflow.com/questions/123198/how-to-copy-files
    demultiplex_out_file.write('2/5 Tasks: Demultiplexing started\n')

    bcl2fastq_bin = '/usr/local/bin/bcl2fastq'
    argv = [
        '--no-lane-splitting',
        f"--runfolder-dir {RunFolder}"
        f"--output-dir {DemultiplexFolder}"
    ]
    Bcl2FastqLogDirName  = 'demultiplex_log'
    Bcl2FastqLogFileName = '02_demultiplex.log'
    Bcl2FastqLogFile     = os.path.join( DemultiplexFolder, os.path.join( Bcl2FastqLogDir, Bcl2FastqLogFileName ) )

    try:
        # EXAMPLE: /usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + RunFolder + ' --output-dir ' + DemultiplexFolder + ' 2> ' + DemultiplexFolder + '/demultiplex_log/02_demultiplex.log'
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

def moveFiles(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file):
    """
    Move?Rename? files FIXMEFIXMEFIXME more info when debugging
    """
    CompressedFastqSuffix = 'fastq.gz' 

    for root, dirs, files in os.walk(DemultiplexFolder):
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

        # /usr/bin/mv DemultiplexFolder/project.split('.')[0] DemultiplexFolder/RunId_short.project
        source      = os.path.join( DemultiplexFolder, project.split('.')[0] )
        destination = os.path.join( DemultiplexFolder, '.'.join( RunId_short, project  ) )
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

def qc(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file):
    """
    Run QC on the sequence run files
    """

    for project in project_list:
        project_folder = DemultiplexFolder + '/' + RunId_short + '.' + project


        try:
            command = '/usr/local/bin/fastqc'
            args = [ '-t 4', 
                    f"{project_folder}/*fastq.gz"
            ]
            # EXAMPLE: /usr/local/bin/fastqc -t 4 project_folder/*fastq.gz > DemultiplexFolder/demultiplex_log/04_fastqc.log
            result = subprocess.run( command, args, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
        except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: { err.cmd }", # interpolated strings
                     f"Return code: { err.returncode }"
                     f"Process output: { err.output }",
            ]

        # EXAMPLE: /usr/bin/cp project_folder/*zip project_folder/*html DemultiplexFolder/RunId_short_QC # (destination is a directory)
        zipFiles = f"{project_folder}/*zip"                     # source of zip files
        destination = f"{DemultiplexFolder}/{RunId_short}_QC"   # destination folder
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

            # EXAMPLE: /usr/local/bin/multiqc project_folder -o project_folder 2> DemultiplexFolder/demultiplex_log/05_multiqc.log
            result = subprocess.run( command, args, stdout = demultiplex_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
        except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: { err.cmd }", # interpolated strings
                     f"Return code: { err.returncode }"
                     f"Process output: { err.output }",
            ]
        demultiplex_out_file.write('4/5 Tasks: FastQC complete\n')

        # EXAMPLE: /usr/local/bin/multiqc DemultiplexFolder/RunId_short_QC -o DemultiplexFolder /RunId_short_QC 2> DemultiplexFolder/demultiplex_log/05_multiqc.log
        try:
            command = '/usr/local/bin/multiqc'
            args = [ project_folder,
                    f"-o {project_folder}" 
            ]

            # EXAMPLE: /usr/local/bin/multiqc project_folder -o project_folder 2> DemultiplexFolder/demultiplex_log/05_multiqc.log
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

def script_completion_file(DemultiplexFolder, demultiplex_out_file):
    """
    """
    DemultiplexCompleteFile = 'DemultiplexComplete.txt'
    try: 
        Path( os.path.join ( DemultiplexFolder, DemultiplexCompleteFile )).touch( mode=644, exist_ok=False)
    except Exception as e:
        print( e.error )
        print( f"{DemultiplexFolder}/{DemultiplexCompleteFile} already exists. Please delete it before running demux.\n")
        exit( )
        # FIXMEFIXME notify_warning_system_that_error_occured( )



########################################################################
# prepare_delivery
########################################################################

def prepare_delivery(folder, DemultiplexFolder , tar_file, md5_file, demultiplex_out_file):
    """
    """
    # EXAMPLE: /bin/tar -cvf tar_file -C DemultiplexFolder folder 
    execute('/bin/tar -cvf ' + tar_file + ' -C ' + DemultiplexFolder + ' ' + folder , demultiplex_out_file)
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

    DataFolder             = '/data'
    DemultiplexLogDir      = 'demultiplex_log'
    ScriptLog              = 'script.log'
    DemultiplexLogFilePath = os.path.join( DemultiplexLogDir, ScriptLog )
    md5Extension           = '.md5'
    tarExtension           = '.tar'
    ForTransferDirPath     = 'for_transfer'
    RunLocation            = os.path.join( DataFolder, 'scratch' )
    DemultiplexLocation    = os.path.join( DataFolder, 'demultiplex' )
    DemultiplexDirSuffix   = '_demultiplex'
    QCDirSuffix            = '_QC'

    RunId_short          = '_'.join(RunId.split('_')[0:2])
    RunFolder            = os.path.join( RunLocation, RunId )
    DemultiplexFolder    = os.path.join( DemultiplexLocation, RunId +  DemultiplexDirSuffix )
    demultiplex_out_file = open( DemultiplexLogFilePath , 'w')
    project_list         = getProjectName( DemultiplexFolder, demultiplex_out_file )
    project_name         = '.'.join( RunId_short, project_list )
    DemultiplexDirPath   = os.path.join( DemultiplexFolder, project_name )
    tar_file             = os.path.join( DataFolder, os.path.join( ForTransferDirPath, project_name + tarExtension ) )
    md5_file             = '+'.join( tar_file, md5Extension )
    QC_tar_file          = os.path.join( DemultiplexLocation, os.path.join ( ForTransferDirPath, ''.join( RunId_short, '_QC.tar' ) ) )
    QC_md5_file          = '+'.join( QC_tar_file, md5Extension )

    if checkComplete( RunFolder ) is False:
        print( ' '.join( RunId, 'is not finished sequencing yet!' ) )
        sys.exit()

    if createDirectory( DemultiplexFolder, RunId_short ) is False:
        print( ' '.join( DemultiplexFolder, 'exists. Delete or rename the demultiplex folder before re-running the script' ) )
        sys.exit()
    else:
        demultiplex_out_file.write('1/5 Tasks: Directories created\n')

    demutliplex( RunFolder, DemultiplexFolder, demultiplex_out_file )
    moveFiles(   DemultiplexFolder, RunId_short, project_list, demultiplex_out_file )
    qc(          DemultiplexFolder, RunId_short, project_list, demultiplex_out_file )

    change_permission( DemultiplexFolder, demultiplex_out_file )
    for project in project_list:

        create_md5deep(    DemultiplexDirPath, demultiplex_out_file )
        prepare_delivery(  project_name, DemultiplexFolder, tar_file, md5_file, demultiplex_out_file )
        change_permission( tar_file, demultiplex_out_file )
        change_permission( md5_file, demultiplex_out_file )

    prepare_delivery(  RunId_short + QCDirSuffix, DemultiplexFolder, QC_tar_file, QC_md5_file, demultiplex_out_file )
    change_permission( QC_tar_file, demultiplex_out_file )
    change_permission( QC_md5_file, demultiplex_out_file )

    script_completion_file(DemultiplexFolder, demultiplex_out_file)

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
