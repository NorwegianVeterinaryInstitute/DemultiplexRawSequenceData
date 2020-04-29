import os, sys, subprocess

def execute(command, demultiplex_out_file):
    command2 = 'source activate miseq && ' + command
    demultiplex_out_file.write('    ' + command2 + '\n')
    p = subprocess.Popen(command2, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()

def checkComplete(RunLocation):
    if os.path.exists(RunLocation + '/RTAComplete.txt'):
        return ('True')
    else:
        return ('False')

def createDirectory(DemultiplexLocation):
    if os.path.isdir(DemultiplexLocation):
        return('False')
    else:
        os.mkdir(DemultiplexLocation)
        os.mkdir(DemultiplexLocation + '/QC')
        os.mkdir(DemultiplexLocation + '/demultiplex_log')
#        demultiplex_out_file.write('1/5 Tasks: Directories created\n')

def demutliplex(RunLocation, DemultiplexLocation, demultiplex_out_file):
    demultiplex_out_file.write('2/5 Tasks: Demultiplexing started\n')
    execute('cp ' + RunLocation + '/SampleSheet.csv ' + DemultiplexLocation, demultiplex_out_file)
    execute('bcl2fastq --runfolder-dir ' + RunLocation + ' --output-dir ' + DemultiplexLocation + ' 2> ' + DemultiplexLocation + '/demultiplex_log/02_demultiplex.log', demultiplex_out_file)
    demultiplex_out_file.write('2/5 Tasks: Demultiplexing complete\n')

def moveFiles(DemultiplexLocation, demultiplex_out_file):
    for root, dirs, files in os.walk(DemultiplexLocation):
        for name in files:
            if 'fastq.gz' in name:
                execute('mv ' + root + '/' + name + ' ' + root + '/' + '_'.join(RunId.split('_')[0:2]) + '.' + name, demultiplex_out_file)

    check = 'False'
    project_list = []
    for line in open(DemultiplexLocation + '/SampleSheet.csv', 'r'):
        if check == 'True':
            if line.rstrip().split(',')[9] not in project_list:
                project_list.append(line.rstrip().split(',')[9])
        if 'Sample_ID' in line:
            check = 'True'
    for project in project_list:
        execute('mv ' + DemultiplexLocation + '/' + project + ' ' + DemultiplexLocation + '/' + '_'.join(RunId.split('_')[0:2]) + '.'+ project, demultiplex_out_file)
    demultiplex_out_file.write('3/5 Tasks: Moving files complete\n')

def qc(DemultiplexLocation, demultiplex_out_file):
    execute('fastqc -t 4 ' + DemultiplexLocation + '/*fastq.gz ' + DemultiplexLocation + '/*/*.fastq.gz ' + DemultiplexLocation + '/*/*/*.fastq.gz' + ' -o ' + DemultiplexLocation + '/QC' + ' > ' + DemultiplexLocation + '/demultiplex_log/04_fastqc.log', demultiplex_out_file)
    demultiplex_out_file.write('4/5 Tasks: FastQC complete\n')
    execute('multiqc ' + DemultiplexLocation + '/QC' + ' -o ' + DemultiplexLocation + '/QC' + ' 2> ' + DemultiplexLocation + '/demultiplex_log/05_multiqc.log', demultiplex_out_file)
    demultiplex_out_file.write('5/5 Tasks: MultiQC complete\n')

def create_md5deep(DemultiplexLocation, demultiplex_out_file):
    md5deep_out = DemultiplexLocation + '/md5sum.txt'
    sed_command = 'sed "s ' + DemultiplexLocation + '/  g" '
    execute('md5deep -r ' + DemultiplexLocation + ' | ' + sed_command + ' | grep -v md5sum | grep -v script > ' + md5deep_out, demultiplex_out_file)

def script_completion_file(DemultiplexLocation, demultiplex_out_file):
    execute('touch ' + DemultiplexLocation + '/DemultiplexComplete.txt', demultiplex_out_file)

def prepare_delivery(DemultiplexLocation, tar_file, md5_file, demultiplex_out_file):
    execute('tar -cvf ' + tar_file + ' ' + DemultiplexLocation, demultiplex_out_file)
    sed_command = 'sed "s /mnt/data/demultiplex/  g" '
    execute('md5sum ' + tar_file + ' | ' + sed_command + ' > ' + md5_file, demultiplex_out_file)

def change_permission(folder_or_file, demultiplex_out_file):
    execute('chown -R arvindsu:sambagroup ' + folder_or_file, demultiplex_out_file)
    execute('chmod -R g+rwX sambagroup ' + folder_or_file, demultiplex_out_file)

def main(RunId):
    RunLocation = '/mnt/data/scratch/' + RunId
    DemultiplexLocation = '/mnt/data/demultiplex/' + RunId + '_demultiplex'
    tar_file = DemultiplexLocation + '.tar'
    md5_file = tar_file + '.md5'

    if checkComplete(RunLocation) is 'False':
        print (RunId + ' is not finished sequencing yet!!!')
        sys.exit()
    if createDirectory(DemultiplexLocation) is 'False':
        print (DemultiplexLocation + ' exists. Delete or rename the demultiplex folder before re-running the script')
        sys.exit()
    else:
        demultiplex_out_file = open(DemultiplexLocation + '/demultiplex_log/script.log', 'w')
        demultiplex_out_file.write('1/5 Tasks: Directories created\n')

    demutliplex(RunLocation, DemultiplexLocation, demultiplex_out_file)
    moveFiles(DemultiplexLocation, demultiplex_out_file)
    qc(DemultiplexLocation, demultiplex_out_file)

    create_md5deep(DemultiplexLocation, demultiplex_out_file)

    script_completion_file(DemultiplexLocation, demultiplex_out_file)
    prepare_delivery(DemultiplexLocation, tar_file, md5_file, demultiplex_out_file)

    change_permission(DemultiplexLocation, demultiplex_out_file)
    change_permission(tar_file, demultiplex_out_file)
    change_permission(md5_file, demultiplex_out_file)


    demultiplex_out_file.write('\nAll done!\n')

    demultiplex_out_file.close()

if __name__ == '__main__':
    RunId = sys.argv[1]
    main(RunId)
