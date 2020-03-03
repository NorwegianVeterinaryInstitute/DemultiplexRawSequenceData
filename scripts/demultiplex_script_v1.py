import os, sys, subprocess

def execute(command):
    print ('	' + command)
    p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    (output, err) = p.communicate()
    p_status = p.wait()

def activateConda():
    execute('source /src/anaconda3/etc/profile.d')
    execute('conda activate miseq')

def checkComplete(RunId):
    if not os.path.exists('/mnt/data/scratch/' + RunId + '/RTAComplete.txt'):
        print ('Run is not complete')
        return ('False')
    else:
        return ('True')

def createDirectory(RunId):
    execute('mkdir /mnt/data/demultiplex/' + RunId)
    execute('mkdir /mnt/data/demultiplex/' + RunId + '/QC')
    execute('mkdir /mnt/data/demultiplex/' + RunId + '/demultiplex_log')
    print ('1/6 Tasks: Directories created')

def demutliplex(RunId):
    print ('2/6 Tasks: Demultiplexing started')
    execute('bcl2fastq --runfolder-dir /mnt/data/scratch/' + RunId + ' --output-dir /mnt/data/demultiplex/' + RunId + ' 2> /mnt/data/demultiplex/' + RunId + '/demultiplex_log/02_demultiplex.log')
    print ('2/6 Tasks: Demultiplexing complete')

def moveFiles(RunId):
    for fastq in os.listdir('/mnt/data/demultiplex/' + RunId):
        if 'fastq.gz' in fastq:
            execute('mv /mnt/data/demultiplex/' + RunId + '/' + fastq + ' /mnt/data/demultiplex/' + RunId + '/' + '_'.join(RunId.split('_')[0:2]) + '.' + fastq)
    print ('3/6 Tasks: Moving files complete')

def qc(RunId):
    execute('fastqc -t 4 /mnt/data/demultiplex/' + RunId + '/*fastq.gz -o /mnt/data/demultiplex/' + RunId + '/QC' + ' > /mnt/data/demultiplex/' + RunId + '/demultiplex_log/04_fastqc.log')
    print ('4/6 Tasks: FastQC complete')
    execute('multiqc /mnt/data/demultiplex/' + RunId + '/QC' + ' -o /mnt/data/demultiplex/' + RunId + '/QC' + ' 2> /mnt/data/demultiplex/' + RunId + '/demultiplex_log/05_multiqc.log')
    print ('5/6 Tasks: MultiQC complete')

def copyOutput(RunId):
    execute('mv /mnt/data/demultiplex/' + RunId + ' /mnt/data/demultiplex/' + RunId + '_demultiplex_test')
    execute('rsync /mnt/data/demultiplex/' +  RunId + '_demultiplex_test' + ' /mnt/data/scratch/')
    print ('6/6 Tasks: Renamed demultiplex folder and copied the results to scratch (Z:/ drive)')
    print ('Check Z:/' + RunId + '_demultiplex folder for the output')

# def copyQC(RunId):
#     execute('rsync /mnt/data/demultiplex/' + RunId + '/Stats ' + '/mnt/data/demultiplex/' + RunId + '/demultiplex_log ' + ' /mnt/data/scratch/' + RunId)
#    execute('rsync /mnt/data/demultiplex/' + RunId + '/Reports ' + '/mnt/data/demultiplex/' + RunId + '/demultiplex_log ' + ' /mnt/data/scratch/' + RunId)

def main(RunId):
    if checkComplete(RunId) is 'True':
        activateConda()
        createDirectory(RunId)
        demutliplex(RunId)
        moveFiles(RunId)
        qc(RunId)
        copyOutput(RunId)
#    copyQC(RunId)

if __name__ == '__main__':
    RunId = sys.argv[1]
    main(RunId)
    print('')
    print('All done!')
