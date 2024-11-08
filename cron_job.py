#!/bin/env /bin/python3


# TO FIX: if someone passes a run with a / at the end be forgiving and just remove the '/'


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
#               demultiplexList.append(dirName.replace('_demultiplex',''))
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
print( f"==> Getting new rawdata directories started ==\n")

for dirName in os.listdir( demultiplex_script.demux.rawDataDir ): # add directory names from the raw generated data directory

    if demultiplex_script.demux.demultiplexDirSuffix in dirName: #  ignore any _demux dirs
        continue
    if any( var in dirName for var in[ demultiplex_script.demux.nextSeq, demultiplex_script.demux.miSeq ] ): # only add directories that have a sequncer tag
        RunList.append(dirName)

print( f"==< Getting new rawdata directories finished ==\n")


DemultiplexList = [] 
print( f"==> Getting demultiplexed directories started ==\n")

for dirName in os.listdir( demultiplex_script.demux.demultiplexDir ):

    if demultiplex_script.demux.demultiplexDirSuffix not in dirName: #  demultiplexed directories must have the  _demultiplex suffix # safety for other dirs included in /data/demultiplex
        continue
    if any( var in dirName for var in[ demultiplex_script.demux.nextSeq, demultiplex_script.demux.miSeq ] ): # ignore directories that have no sequncer tag
        DemultiplexList.append( dirName.replace( demultiplex_script.demux.DemultiplexDirSuffix, '' ) ) # null _demultiplex so we can compare the two lists below

print( f"==> Getting demultiplexed directories finished ==\n")


# Right now the script operates on only one run at a time, but in the future we might want to run miltiple things at a time

count = 0
NewRunList = [ ]
NewRunID = '' # turn this into an array
for item in RunList: # iterate over RunList to see if there a new item in DemultiplexList, effectively comparing the contents of the two directories
    if item in DemultiplexList:
        count += 1
    else:
        NewRunList.append( item )
        NewRunID = item # any RunList item that is not in the demux list, gets processed

localTime = strftime( "%Y-%m-%d %H:%M:%S", localtime( ) ) 
print( f"{ localTime } - { len( RunList ) } in scratch and { len( DemultiplexList ) } in demultiplex: ")

if count == len( RunList ): # no new items in DemultiplexList, therefore count == len( RunList )
     print( 'all the runs have been demultiplexed\n' )

if NewRunID:

    flatNewRunList = ", ".join( NewRunList )
    print( f"{len(NewRunList)} new items to demux: {flatNewRunList}")

    print( f"Will work on this RunID: {NewRunID}\n" ) # caution: if the corresponding _demux directory is somehow corrupted (wrong data in SampleSheetFilename or incomplete files), this will be printed over and over in the log file

    # essential condition to process is that RTAComplete.txt and SampleSheet.csv
    if demultiplex_script.demux.rtaCompleteFile in os.listdir( os.path.join( demultiplex_script.demux.rawDataDir, NewRunID ) ) and demultiplex_script.demux.sampleSheetFileName in os.listdir( os.path.join( demultiplex_script.demux.rawDataDir, NewRunID ) ):

        if demultiplex_script.demux.debug: 
            print( f"{demultiplex_script.demux.python3_bin} {demultiplex_script.demux.scriptFilePath} {NewRunID}")

        if not os.path.exists( demultiplex_script.demux.scriptFilePath ):
            print( f"{demultiplex_script.demux.scriptFilePath} does not exist!" )
            exit( )

        # EXAMPLE: /bin/python3 /data/bin/current_demultiplex_script.py 210903_NB552450_0002_AH3VYYBGXK 
        demultiplex_script.main( NewRunID )

        print( 'completed\n' )
    else:
        print( ', waiting for the run to complete\n' )
