import os, sys, subprocess
from time import gmtime, strftime, localtime

RunDir = '/mnt/data/scratch'
DemultiplexDir = '/mnt/data/demultiplex'
cron_out_file = open(DemultiplexDir + '/scripts/cron_out.txt', 'a')

RunList = []
for foldername in os.listdir(RunDir):
    if 'M06578' in foldername and '_demultiplex' not in foldername:
        RunList.append(foldername)

DemultiplexList = []
for foldername in os.listdir(DemultiplexDir):
    if 'M06578' in foldername and  '_demultiplex' in foldername:
        DemultiplexList.append(foldername.replace('_demultiplex',''))

count = 0
NewRun = ''
for item in RunList:
    if item in DemultiplexList:
        count += 1
    else:
        NewRun = item

cron_out_file.write(strftime("%Y-%m-%d %H:%M:%S", gmtime()) + ' - ')
cron_out_file.write(str(len(RunList)) + ' in scratch and ' + str(len(DemultiplexList)) + ' in demultiplex : ')

if count == len(RunList):
     cron_out_file.write('all the runs have been demultiplexed\n')

if NewRun:
    cron_out_file.write('Need to work on this: ' + NewRun)
    if 'RTAComplete.txt' in os.listdir(RunDir + '/' + NewRun) and 'SampleSheet.csv' in os.listdir(RunDir + '/' + NewRun):
        command = 'python /mnt/data/demultiplex/scripts/demultiplex_script_v2.py ' + NewRun
        cron_out_file.write('\n' + command + '\n')
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (output, err) = p.communicate()
        p_status = p.wait()
        cron_out_file.write('completed\n')
    else:
        cron_out_file.write(', waiting for the run to complete\n')

cron_out_file.close()
