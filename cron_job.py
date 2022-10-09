#!/bin/env /bin/python3

import os, sys, subprocess
import time
from time import strftime, localtime, time

# LIMITATIONS/ASSUMPTIONS:
#   This script cannot handle more than 1 new run /data/scratch/*M06578*_demultiplex
#       if more than 1 new run exists in /data/scratch/ the script will pick the first
#       directory  os.listdir() will return, THERE IS NO GUARANTEE FOR LEXICOGRAPHICAL
#       ORDER.
#
# INPUT:
#   none from command line
#   the directories in /data/scratch/*M06578*_demultiplex
#
# OUTPUT:
#   Log file in /data/bin/cron_out.log, append mode, file does not get overwritten with each run
#           "2021-09-09 10:00:01 - 24 in scratch and 24 in demultiplex : all the runs have been demultiplexed"  
#       or
#           Need to work on this: $COMMAND_TO_RUN completed
#       or
#           Need to work on this: $COMMAND_TO_RUN, waiting for the run to complete
#
# WHAT DOES THIS SCRIPT DO:
#       This script sets up the demultiplexing:
#           Picks up all the existing folders within /data/scratch/*M06578*_demultiplex in variable RunList     
#       Initializes a new variable
#           fills it up with the var from RunList
#           but removes the _demultiplex part
#               demultiplexList.append(foldername.replace('_demultiplex',''))
#       Differentiates the new item to run by comparing with the os.listdir(DemultiplexDir)
#           FIXME comparison needs revision, inefficient
#
#       if there is a difference between the two lists
#           the script starts a new run by
#               creating the dir path to be demultiplexed
#               checks if /data/scratch/$NEWRUN/SampleSheet.csv exists
#           executes /bin/python3 /data/bin/current_demultiplex_script.py
#               with the new dir name as argument, example
#                   /bin/python3 /data/bin/current_demultiplex_script.py 210903_NB552450_0002_AH3VYYBGXK_copy   
#           script waits for the output of /data/bin/current_demultiplex_script.py and appends it to
#               /data/bin/cron_out.log


DataDir = '/data'
RunDir = '/data/scratch'
DemultiplexDir = '/data/demultiplex'
cron_out_file = open( DataDir + '/' + 'bin/cron_out.log', 'a')

RunList = []
for foldername in os.listdir(RunDir): # future perfomance, read the list into var, then itterate
    # if 'M06578' in foldername and '_demultiplex' and 'copy' not in foldername:
    if ( ( 'NB552450' in foldername ) or ( 'M06578' in foldername ) ) and ( '_demultiplex' not in foldername ): 
        RunList.append(foldername)

DemultiplexList = []
for foldername in os.listdir(DemultiplexDir): # future perfomance, read the list into var, then itterate        
    if ( ( 'M06578' in foldername ) or ( 'NB552450' in foldername ) ) and  ( '_demultiplex' in foldername ):    
        DemultiplexList.append(foldername.replace('_demultiplex',''))

count = 0
NewRun = ''
for item in RunList:
    if item in DemultiplexList:
        count += 1
    else:
        NewRun = item

cron_out_file.write(strftime("%Y-%m-%d %H:%M:%S", localtime()) + ' - ')
cron_out_file.write(str(len(RunList)) + ' in scratch and ' + str(len(DemultiplexList)) + ' in demultiplex : ')

if count == len(RunList):
     cron_out_file.write('all the runs have been demultiplexed\n')

if NewRun:
    cron_out_file.write('Need to work on this: ' + NewRun)
    if 'RTAComplete.txt' in os.listdir(RunDir + '/' + NewRun) and 'SampleSheet.csv' in os.listdir(RunDir + '/' + NewRun):
        command = '/bin/python3 /data/bin/current_demultiplex_script.py ' + NewRun
        cron_out_file.write('\n' + command + '\n')
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (output, err) = p.communicate()
        p_status = p.wait()
        cron_out_file.write('completed\n')
    else:
        cron_out_file.write(', waiting for the run to complete\n')

cron_out_file.close()
