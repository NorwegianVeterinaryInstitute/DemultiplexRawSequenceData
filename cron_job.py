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


DataDir              = '/data'
RawDir               = '/data/scratch'
DemultiplexDir       = '/data/demultiplex'
logfileLocation      = 'bin/cron_out.log'
cron_out_file        = open( os.path.join( DataDir, logfileLocation ), 'a')
MiSeq                = 'M06578'   # if we get more than one, turn this into an array
NextSeq              = 'NB552450' # if we get more than one, turn this into an array
DemuxDirectorySuffix = '_demultiplex'
RTACompleteFilename  = 'RTAComplete.txt'
SampleSheetFilename  = 'SampleSheet.csv'



RunList = []
for foldername in os.listdir( RawDir ): # add directory names from the raw generated data directory
    # if ( ( MiSeq in foldername ) or ( NextSeq in foldername ) ) and  ( DemuxDirectorySuffix in foldername ):
    if ( MiSeq or NextSeq ) in foldername and ( DemuxDirectorySuffix not in foldername ): # ignore directories that have no sequncer tag; ignore any _demux dirs
        RunList.append(foldername)

DemultiplexList = [] 
for foldername in os.listdir(DemultiplexDir):
    # if ( ( MiSeq in foldername ) or ( NextSeq in foldername ) ) and  ( DemuxDirectorySuffix in foldername ):
    if ( MiSeq or NextSeq ) in foldername and ( addendum in foldername ): # ignore directories that have no sequncer tag; require any _demux dirs
        DemultiplexList.append( foldername.replace( DemuxDirectorySuffix, '' ) ) # null _demultiplex so we can compare the two lists below

# Right now the script operates on only one run at a time, but in the future we might want to run miltiple things at a time

count = 0
NewRunID = '' # turn this into an array
for item in RunList: # iterate over RunList to see if there a new item in DemultiplexList, effectively comparing the contents of the two directories
    if item in DemultiplexList:
        count += 1
    else:
        NewRunID = item # any RunList item that is not in the demux list, gets processed


cron_out_file.write( strftime( "%Y-%m-%d %H:%M:%S", localtime() ) + ' - ' )
cron_out_file.write( str( len( RunList ) ) + ' in scratch and ' + str( len( DemultiplexList ) ) + ' in demultiplex : ')

if count == len( RunList ): # no new items in DemultiplexList, therefore count == len( RunList )
     cron_out_file.write( 'all the runs have been demultiplexed\n' )

if NewRunID:
    cron_out_file.write(' Need to work on this: ' + NewRunID ) # caution: if the corresponding _demux directory is somehow corrupted (wrong data in SampleSheetFilename or incomplete files), this will be printed over and over in the log file

    # essential condition to process is that RTAComplete.txt and SampleSheet.csv
    if RTACompleteFilename in os.listdir( os.path.join( RawDir, NewRunID ) ) and SampleSheetFilename in os.listdir( os.path.join( RawDir, NewRunID ) ):

        python_bin     = '/usr/bin/python3'
        ScriptFilepath = '/data/bin/demultiplex_script.py'
        argv           =  [ ScriptFilepath , NewRunID ]

        cron_out_file.write('\n' + python_bin + ' ' + ' ' + '\n') # format and write out the 

        try:
            # EXAMPLE: /bin/python3 /data/bin/current_demultiplex_script.py 210903_NB552450_0002_AH3VYYBGXK        
            result = subprocess.run( python_bin, argv, stdout = cron_out_file, capture_output = True, cwd = RawDir, check = True, encoding = "utf-8" )
        except CalledProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: {err.cmd}", # interpolated strings
                     f"Return code: {err.returncode}"
                     f"Process output: {err.output}",
                   ]
            
            print( '\n'.join( text ) )

        # cron_out_file.write( result.output )

        # p = subprocess.Popen(command, stdout = subprocess.PIPE, stderr = subprocess.PIPE, shell=True)
        # (output, err) = p.communicate()
        # p_status = p.wait()
        cron_out_file.write('completed\n')
    else:
        cron_out_file.write(', waiting for the run to complete\n')

cron_out_file.close()
