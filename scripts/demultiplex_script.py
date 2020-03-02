import os, sys, subprocess

def execute(command):
    command2 = 'source activate miseq && ' + command
    print ('    ' + command2)
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
        execute('mkdir ' + DemultiplexLocation)
        execute('mkdir ' + DemultiplexLocation + '/QC')
        execute('mkdir ' + DemultiplexLocation + '/demultiplex_log')
        print ('1/5 Tasks: Directories created')

def demutliplex(RunLocation, DemultiplexLocation):
    print ('2/5 Tasks: Demultiplexing started')
    execute('bcl2fastq --runfolder-dir ' + RunLocation + ' --output-dir ' + DemultiplexLocation + ' 2> ' + DemultiplexLocation + '/demultiplex_log/02_demultiplex.log')
    print ('2/5 Tasks: Demultiplexing complete')

def moveFiles(DemultiplexLocation):
    for root, dirs, files in os.walk(DemultiplexLocation):
        for name in files:
            if 'fastq.gz' in name:
                execute('mv ' + root + '/' + name + ' ' + root + '/' + '_'.join(RunId.split('_')[0:2]) + '.' + name)
    print ('3/5 Tasks: Moving files complete')

def qc(DemultiplexLocation):
    execute('fastqc -t 4 ' + DemultiplexLocation + '/*fastq.gz ' + DemultiplexLocation + '/*/*.fastq.gz ' + DemultiplexLocation + '/*/*/*.fastq.gz' + ' -o ' + DemultiplexLocation + '/QC' + ' > ' + DemultiplexLocation + '/demultiplex_log/04_fastqc.log')
    print ('4/5 Tasks: FastQC complete')
    execute('multiqc ' + DemultiplexLocation + '/QC' + ' -o ' + DemultiplexLocation + '/QC' + ' 2> ' + DemultiplexLocation + '/demultiplex_log/05_multiqc.log')
    print ('5/5 Tasks: MultiQC complete')

def main(RunId):
    RunLocation = '/mnt/data/scratch/' + RunId
    DemultiplexLocation = '/mnt/data/demultiplex/' + RunId + '_demultiplex'

    if checkComplete(RunLocation) is 'False':
        print (RunId + ' is not finished sequencing yet!!!')
        sys.exit()
    if createDirectory(DemultiplexLocation) is 'False':
        print (DemultiplexLocation + ' exists. Delete or rename the demultiplex folder before re-running the script')
        sys.exit()
    demutliplex(RunLocation, DemultiplexLocation)
    moveFiles(DemultiplexLocation)
    qc(DemultiplexLocation)
    print('\nAll done!')

if __name__ == '__main__':
    RunId = sys.argv[1]
    main(RunId)
