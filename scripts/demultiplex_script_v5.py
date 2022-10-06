#!/bin/env /bin/python3

import os, sys, subprocess

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


def execute(command, demultiplex_out_file):
    # why is  export LANG=nb_NO.utf8 && export LC_ALL=nb_NO.utf8 there?
    command2 = 'source activate miseq && export LANG=nb_NO.utf8 && export LC_ALL=nb_NO.utf8 && ' + command
    #demultiplex_out_file.write('    ' + command2 + '\n')
    demultiplex_out_file.write('    ' + command + '\n')
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()

def checkComplete(RunFolder):
    if os.path.exists(RunFolder + '/RTAComplete.txt'):
        return ('True')
    else:
        return ('False')

def createDirectory(DemultiplexFolder, RunId_short):
    if os.path.isdir(DemultiplexFolder):
        return('False')
    else:
        os.mkdir(DemultiplexFolder)
        os.mkdir(DemultiplexFolder + '/' + RunId_short + '_QC')
        os.mkdir(DemultiplexFolder + '/demultiplex_log')

def demutliplex( RunFolder, DemultiplexFolder, demultiplex_out_file):
    demultiplex_out_file.write('2/5 Tasks: Demultiplexing started\n')
    execute('/bin/cp ' + RunFolder + '/SampleSheet.csv ' + DemultiplexFolder, demultiplex_out_file)
    #execute('/usr/local/bin/bcl2fastq --ignore-missing-bcl --no-lane-splitting --runfolder-dir ' + RunFolder + ' --output-dir ' + DemultiplexFolder + ' 2> ' + DemultiplexFolder + '/demultiplex_log/02_demultiplex.log', demultiplex_out_file)
    execute('/usr/local/bin/bcl2fastq --no-lane-splitting --runfolder-dir ' + RunFolder + ' --output-dir ' + DemultiplexFolder + ' 2> ' + DemultiplexFolder + '/demultiplex_log/02_demultiplex.log', demultiplex_out_file)
    demultiplex_out_file.write('2/5 Tasks: Demultiplexing complete\n')

def getProjectName( DemultiplexFolder, demultiplex_out_file):
    project_line_check = 'no'
    project_index = ''
    analysis_index = ''
    project_list = []

    for line in open(DemultiplexFolder + '/SampleSheet.csv', 'r'):
        line = line.rstrip()
        if project_line_check == 'yes':
            project_list.append(line.split(',')[project_index] + '.' + line.split(',')[analysis_index])
        if 'Sample_Project' in line:
            project_index = line.split(',').index('Sample_Project')
            analysis_index = line.split(',').index('Analysis')
            project_line_check = 'yes'
    return(set(project_list))

def moveFiles(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file):
    for root, dirs, files in os.walk(DemultiplexFolder):
        for name in files:
            if 'fastq.gz' in name:
                execute('/bin/mv ' + root + '/' + name + ' ' + root + '/' + RunId_short + '.' + name, demultiplex_out_file)

    for project in project_list:
        execute('/bin/mv ' + DemultiplexFolder + '/' + project.split('.')[0] + ' ' + DemultiplexFolder + '/' + RunId_short + '.'+ project, demultip
lex_out_file)

    demultiplex_out_file.write('3/5 Tasks: Moving files complete\n')

def qc(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file):
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

def create_md5deep(Folder, demultiplex_out_file):
    md5deep_out = Folder + '/md5sum.txt'
    sed_command = '/bin/sed "s ' + Folder + '/  g" '
    execute('/bin/md5deep -r ' + Folder + ' | ' + sed_command + ' | grep -v md5sum | grep -v script > ' + md5deep_out, demultiplex_out_file)       

def script_completion_file(DemultiplexFolder, demultiplex_out_file):
    execute('/bin/touch ' + DemultiplexFolder + '/DemultiplexComplete.txt', demultiplex_out_file)

def prepare_delivery(folder, DemultiplexFolder , tar_file, md5_file, demultiplex_out_file):
    execute('/bin/tar -cvf ' + tar_file + ' -C ' + DemultiplexFolder + ' ' + folder , demultiplex_out_file)
    #sed_command = '/bin/sed "s /mnt/data/demultiplex/for_transfer/  g" '
    sed_command = '/bin/sed "s /data/for_transfer/  g" '
    execute('/bin/md5sum ' + tar_file + ' | ' + sed_command + ' > ' + md5_file, demultiplex_out_file)

def change_permission(folder_or_file, demultiplex_out_file):
    execute('/bin/chown -R sambauser01:sambagroup ' + folder_or_file, demultiplex_out_file)
    execute('/bin/chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file)

def main(RunId):

    DataFolder = '/data'
    RunLocation = DataFolder + '/' + 'scratch'
    DemultiplexLocation = DataFolder + '/' + 'demultiplex'

    RunId_short = '_'.join(RunId.split('_')[0:2])
    RunFolder = RunLocation + '/' + RunId
    DemultiplexFolder = DemultiplexLocation + '/' + RunId + '_demultiplex'

    if checkComplete(RunFolder) is 'False':
        print (RunId + ' is not finished sequencing yet!!!')
        sys.exit()
    if createDirectory(DemultiplexFolder, RunId_short) is 'False':
        print (DemultiplexFolder + ' exists. Delete or rename the demultiplex folder before re-running the script')
        sys.exit()
    else:
        demultiplex_out_file = open(DemultiplexFolder + '/demultiplex_log/script.log', 'w')
        demultiplex_out_file.write('1/5 Tasks: Directories created\n')

    demutliplex( RunFolder, DemultiplexFolder, demultiplex_out_file)

    # runs to here
    project_list = getProjectName( DemultiplexFolder, demultiplex_out_file)
    moveFiles(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file)
    qc(DemultiplexFolder, RunId_short, project_list, demultiplex_out_file)

    change_permission(DemultiplexFolder, demultiplex_out_file)
    for project in project_list:
        project_name = RunId_short + '.' + project
        create_md5deep(DemultiplexFolder + '/' + project_name, demultiplex_out_file)
        #tar_file = DemultiplexLocation + 'for_transfer/' + project_name + '.tar'
        tar_file = DataFolder + '/'+ 'for_transfer/' + project_name + '.tar'
        md5_file = tar_file + '.md5'
        prepare_delivery(project_name, DemultiplexFolder, tar_file, md5_file, demultiplex_out_file)
        change_permission(tar_file, demultiplex_out_file)
        change_permission(md5_file, demultiplex_out_file)

    QC_tar_file = DemultiplexLocation + '/' + 'for_transfer/' + RunId_short + '_QC.tar'
    QC_md5_file = QC_tar_file + '.md5'

    prepare_delivery(RunId_short + '_QC', DemultiplexFolder, QC_tar_file, QC_md5_file, demultiplex_out_file)
    change_permission(QC_tar_file, demultiplex_out_file)
    change_permission(QC_md5_file, demultiplex_out_file)

    script_completion_file(DemultiplexFolder, demultiplex_out_file)

    demultiplex_out_file.write('\nAll done!\n')

    demultiplex_out_file.close()

if __name__ == '__main__':
    RunId = sys.argv[1]
    main(RunId)
