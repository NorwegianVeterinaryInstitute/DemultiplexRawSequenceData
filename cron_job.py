#!/bin/env /bin/python3

import os, sys, subprocess
import time
from time import strftime, localtime, time
import demultiplex_script

# LIMITATIONS/ASSUMPTIONS:
#   This script cannot handle more than 1 new run /data/scratch/{*M06578*,*NB552450*}_demultiplex
#       if more than 1 new run exists in /data/scratch/ the script will pick the first
#       directory  os.listdir() will return, THERE IS NO GUARANTEE FOR LEXICOGRAPHICAL
#       ORDER.
#
# INPUT:
#   none from command line
#   the directories in /data/scratch/{*M06578*,*NB552450*}_demultiplex
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


RunList = []
for foldername in os.listdir( demultiplex_script.demux.RawDataDir ): # add directory names from the raw generated data directory
    if ( demultiplex_script.demux.MiSeq or demultiplex_script.demux.NextSeq ) in foldername and ( demultiplex_script.demux.DemultiplexDirSuffix not in foldername ): # ignore directories that have no sequncer tag; ignore any _demux dirs
        RunList.append(foldername)

DemultiplexList = [] 
for foldername in os.listdir( demultiplex_script.demux.DemultiplexDir ):
    if ( demultiplex_script.demux.MiSeq or demultiplex_script.demux.NextSeq ) in foldername and ( demultiplex_script.demux.addendum in foldername ): # ignore directories that have no sequncer tag; require any _demux dirs
        DemultiplexList.append( foldername.replace( demultiplex_script.demux.DemultiplexDirSuffix, '' ) ) # null _demultiplex so we can compare the two lists below

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

        python_bin     = "/usr/bin/python3"
        ScriptFilePath = "/data/bin/demultiplex_script.py"
        argv           = [ python_bin, ScriptFilePath , NewRunID ]

        cron_out_file.write('\n' + python_bin + ' ' + ' ' + '\n') # format and write out the

        if demultiplex_script.demux.debug: 
            print( f"{python_bin} {ScriptFilePath} {NewRunID}")

        if not os.path.exists( ScriptFilePath ):
            print( f"{ScriptFilePath} does not exist!" )
            exit( )

        # EXAMPLE: /bin/python3 /data/bin/current_demultiplex_script.py 210903_NB552450_0002_AH3VYYBGXK 
        demultiplex_script.main( NewRunID )

        cron_out_file.write('completed\n')
    else:
        cron_out_file.write(', waiting for the run to complete\n')

cron_out_file.close()
