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

def main(RunId):
    RunLocation = '/mnt/data/scratch/' + RunId
    DemultiplexLocation = '/mnt/data/demultiplex/' + RunId + '_demultiplex'

    if checkComplete(RunLocation) is 'False':
        print (RunId + ' is not finished sequencing yet!!!')
        sys.exit()
    if createDirectory(DemultiplexLocation) is 'False':
        print (DemultiplexLocation + ' exists. Delete or rename the demultiplex folder before re-running the script')
        sys.exit()
    else:
        demultiplex_out_file = open(DemultiplexLocation + '/demultiplex_log/demultiplex.log', 'w')
        demultiplex_out_file.write('1/5 Tasks: Directories created\n')

    demutliplex(RunLocation, DemultiplexLocation, demultiplex_out_file)
    moveFiles(DemultiplexLocation, demultiplex_out_file)
    qc(DemultiplexLocation, demultiplex_out_file)
    
    execute('touch ' + DemultiplexLocation + '/DemultiplexComplete.txt', demultiplex_out_file)
    execute('chown -R arvindsu:sambagroup ' + DemultiplexLocation)

    demultiplex_out_file.write('\nAll done!\n')

    demultiplex_out_file.close()

if __name__ == '__main__':
    RunId = sys.argv[1]
    main(RunId)
