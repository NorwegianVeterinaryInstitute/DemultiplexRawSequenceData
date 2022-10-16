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
# CONDA/EXECUTION environment


#
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


#
def checkComplete(RunFolder):
    """
    Check to see if the RunFolder/RTAComplete.txt file exists and return true/false,
    signaling that the sequencing run is complete or not.
    """
    RTACompleteFile = "RTAComplete.txt"
    if os.path.exists( os.path.join( RunFolder, RTACompleteFile ) ):
        return ( True )
    else:
        return ( False )

#
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


#
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
    except CalledProcessError as err: 
        text = [ "Caught exception!",
            f"Command: {err.cmd}", # interpolated strings
            f"Return code: {err.returncode}"
            f"Process output: {err.output}",
        ]
        print( '\n'.join( text ) )
    demultiplex_out_file.write( result.output )

    demultiplex_out_file.write('2/5 Tasks: Demultiplexing complete\n')

#
def getProjectName( DemultiplexFolder, demultiplex_out_file):
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


#
def moveFiles(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file):
    """
    """

    CompressedFastqSuffix = 'fastq.gz' 

    for root, dirs, files in os.walk(DemultiplexFolder):
        for name in files:
            if CompressedFastqSuffix in name:
                execute('/bin/mv ' + root + '/' + name + ' ' + root + '/' + RunId_short + '.' + name, demultiplex_out_file)

    for project in project_list:
        execute('/bin/mv ' + DemultiplexFolder + '/' + project.split('.')[0] + ' ' + DemultiplexFolder + '/' + RunId_short + '.'+ project, demultip
lex_out_file)

    demultiplex_out_file.write('3/5 Tasks: Moving files complete\n')


#
def qc(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file):
    """
    Run QC on the sequence run files
    """

    for project in project_list:
        project_folder = DemultiplexFolder + '/' + RunId_short + '.' + project
        #execute('/src/anaconda3/envs/miseq/bin/fastqc -t 4 ' + project_folder + '/*fastq.gz' + ' > ' + DemultiplexFolder + '/demultiplex_log/04_fastqc.log', demultiplex_out_file)
        execute('/usr/local/bin/fastqc -t 4 ' + project_folder + '/*fastq.gz' + ' > ' + DemultiplexFolder + '/demultiplex_log/04_fastqc.log', demul
tiplex_out_file)
        execute('/bin/cp ' + project_folder + '/*zip ' + project_folder + '/*html ' + DemultiplexFolder + '/' + RunId_short + '_QC', demultiplex_ou
t_file)
        #execute('/src/anaconda3/envs/miseq/bin/multiqc ' + project_folder + ' -o ' + project_folder + ' 2> ' + DemultiplexFolder + '/demultiplex_log/05_multiqc.log', demultiplex_out_file)
        execute('/usr/local/bin/multiqc ' + project_folder + ' -o ' + project_folder + ' 2> ' + DemultiplexFolder + '/demultiplex_log/05_multiqc.log', demultiplex_out_file)
    demultiplex_out_file.write('4/5 Tasks: FastQC complete\n')
    #execute('/src/anaconda3/envs/miseq/bin/multiqc ' + DemultiplexFolder + '/' + RunId_short + '_QC' + ' -o ' + DemultiplexFolder + '/' + RunId_short + '_QC' + ' 2> ' + DemultiplexFolder + '/demultiplex_log/05_multiqc.log', demultiplex_out_file)
    execute('/usr/local/bin/multiqc ' + DemultiplexFolder + '/' + RunId_short + '_QC' + ' -o ' + DemultiplexFolder + '/' + RunId_short + '_QC' + ' 2> ' + DemultiplexFolder + '/demultiplex_log/05_multiqc.log', demultiplex_out_file)
    demultiplex_out_file.write('5/5 Tasks: MultiQC complete\n')


#
def create_md5deep(Folder, demultiplex_out_file):
    md5deep_out = Folder + '/md5sum.txt'
    sed_command = '/bin/sed "s ' + Folder + '/  g" '
    execute('/bin/md5deep -r ' + Folder + ' | ' + sed_command + ' | grep -v md5sum | grep -v script > ' + md5deep_out, demultiplex_out_file)       

#
def script_completion_file(DemultiplexFolder, demultiplex_out_file):
    execute('/bin/touch ' + DemultiplexFolder + '/DemultiplexComplete.txt', demultiplex_out_file)


#
def prepare_delivery(folder, DemultiplexFolder , tar_file, md5_file, demultiplex_out_file):
    execute('/bin/tar -cvf ' + tar_file + ' -C ' + DemultiplexFolder + ' ' + folder , demultiplex_out_file)
    #sed_command = '/bin/sed "s /mnt/data/demultiplex/for_transfer/  g" '
    sed_command = '/bin/sed "s /data/for_transfer/  g" '
    execute('/bin/md5sum ' + tar_file + ' | ' + sed_command + ' > ' + md5_file, demultiplex_out_file)

#
def change_permission(folder_or_file, demultiplex_out_file):

    argv1    =
    argv2    =
    command1 = '/bin/chown -R sambauser01:sambagroup ' + folder_or_file, demultiplex_out_file
    command2 = '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file

# TRY TO SEE IF THERE IS A RECURSIVE CHOWN call in Python

    try:
        # EXAMPLE: /bin/chown -R sambauser01:sambagroup ' + folder_or_file
        result = subprocess.run( command1, argv1, stdout = cron_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
    except CalledProcessError as err: 
        text = [ "Caught exception!",
                 f"Command: { err.cmd }", # interpolated strings
                 f"Return code: { err.returncode }"
                 f"Process output: { err.output }",
               ]

    try:
        # EXAMPLE: '/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file
        result = subprocess.run( command2, argv2, stdout = cron_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
    except CalledProcessError as err: 
        text = [ "Caught exception!",
                 f"Command: { err.cmd }", # interpolated strings
                 f"Return code: { err.returncode }"
                 f"Process output: { err.output }",
               ]

        
        print( '\n'.join( text ) )

#
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

    RunId_short         = '_'.join(RunId.split('_')[0:2])
    RunFolder           = os.path.join( RunLocation, RunId )
    DemultiplexFolder   = os.path.join( DemultiplexLocation, RunId +  DemultiplexDirSuffix )
    project_name        = '.'.join( RunId_short, project )
    DemultiplexDirPath  = os.path.join( DemultiplexFolder, project_name )
    project_list        = getProjectName( DemultiplexFolder, demultiplex_out_file )
    tar_file            = os.path.join( DataFolder, os.path.join( ForTransferDirPath, project_name + tarExtension ) )
    md5_file            = '+'.join( tar_file, md5Extension )
    QC_tar_file         = os.path.join( DemultiplexLocation, os.path.join ( ForTransferDirPath, ''.join( RunId_short, '_QC.tar' ) ) )
    QC_md5_file         = '+'.join( QC_tar_file, md5Extension )

    if checkComplete( RunFolder ) is False:
        print( ' '.join( RunId, 'is not finished sequencing yet!' ) )
        sys.exit()

    if createDirectory( DemultiplexFolder, RunId_short ) is False:
        print( ' '.join( DemultiplexFolder, 'exists. Delete or rename the demultiplex folder before re-running the script' ) )
        sys.exit()
    else:
        demultiplex_out_file = open( os.path.join( DemultiplexFolder, DemultiplexLogFile ) , 'w')
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

if __name__ == '__main__':
    RunId = sys.argv[1]
    main(RunId)
