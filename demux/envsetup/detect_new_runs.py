
import os
import sys
import subprocess
import time

from time import strftime, localtime, time

from demux.loggers import demuxLogger, demuxFailureLogger


########################################################################
# detect_new_runs
########################################################################

def detect_new_runs( demux ):
    """
    Detect if a new run has been uploaded to /data/rawdata
    https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/122
    """

    #########
    # TODO TODO TODO
    #
    #   new feature: logging.info out all the new runs detected
    #       mention which one is being processed
    #       mention which one are remaining
    #########
    demux.n = demux.n + 1
    demuxLogger.info( f"==> {demux.n}/{demux.totalTasks} tasks: Detecting if new runs exist started\n")


    # LIMITATIONS/ASSUMPTIONS:
    #   This method cannot handle more than 1 new run
    #       if more than 1 new run exists in /data/rawdata/ the method will pick the first
    #       directory  os.listdir() will return, THERE IS NO GUARANTEE FOR LEXICOGRAPHICAL
    #       ORDER.
    #
    # INPUT:
    #   none from command line
    #   the directory contents of /data/rawdata and /data/demultiplex
    #
    # OUTPUT:
    #   Log file in /data/bin/cron_out.log, append mode, file does not get overwritten with each run
    #           "2021-09-09 10:00:01 - 24 in rawdata and 24 in demultiplex : all the runs have been demultiplexed"  
    #       or
    #           Need to work on this: $COMMAND_TO_RUN completed
    #       or
    #           Need to work on this: $COMMAND_TO_RUN, waiting for the run to complete
    #
    # WHAT DOES THIS SCRIPT DO:
    #       This method sets up the demultiplexing:
    #           Picks up all the existing folders within /data/rawdata/*M06578*_demultiplex in variable runList     
    #       Initializes a new variable
    #           fills it up with the var from runList
    #           but removes the _demultiplex part
    #               demultiplexList.append(dirName.replace('_demultiplex',''))
    #       Differentiates the new item to run by comparing with the os.listdir(DemultiplexDir)
    #           FIXME comparison needs revision, inefficient
    #
    #       if there is a difference between the two lists
    #           the method starts a new run by
    #               creating the dir path to be demultiplexed
    #               checks if /data/rawdata/$NEWRUN/SampleSheet.csv exists
    #           executes /bin/python3 /data/bin/current_demultiplex_script.py
    #               with the new dir name as argument, example
    #                   /bin/python3 /data/bin/current_demultiplex_script.py 210903_NB552450_0002_AH3VYYBGXK_copy   
    #           method waits for the output of /data/bin/current_demultiplex_script.py and appends it to
    #               /data/bin/cron_out.log


    runList = []
    print( f"==> Getting new rawdata directories started ==\n")

    for dirName in os.listdir( demux.rawDataDir ): # add directory names from the raw generated data directory

        if demux.demultiplexDirSuffix in dirName: #  ignore any _demux dirs
            continue
        if any( tag in dirName for tags in [ demux.nextSeq, demux.miSeq ] for tag in tags ): # only add directories that have a sequncer tag
            runList.append( dirName )

    print( f"==< Getting new rawdata directories finished ==\n")


    DemultiplexList = [] 
    print( f"==> Getting demultiplexed directories started ==\n")

    for dirName in os.listdir( demux.demultiplexDir ):

        if demux.demultiplexDirSuffix not in dirName: #  demultiplexed directories must have the  _demultiplex suffix # safety in case any other dirs included in /data/demultiplex
            continue
        if any( tag in dirName for tags in [ demux.nextSeq, demux.miSeq ] for tag in tags ): # ignore directories that have no sequncer tag
            DemultiplexList.append( dirName.replace( demux.demultiplexDirSuffix, '' ) ) # null _demultiplex so we can compare the two lists below

    print( f"==> Getting demultiplexed directories finished ==\n")


    # Right now the method operates on only one run at a time, but in the future we might want to run miltiple things at a time

    count = 0
    newRunList = [ ]
    newRunID = '' # turn this into an array
    for item in runList: # iterate over runList to see if there a new item in DemultiplexList, effectively comparing the contents of the two directories
        if item in DemultiplexList:
            count += 1
        else:
            newRunList.append( item )
            newRunID = item # any runList item that is not in the demux list, gets processed

    localTime = strftime( "%Y-%m-%d %H:%M:%S", localtime( ) ) 
    print( f"{ localTime } - { len( runList ) } in rawdata and { len( DemultiplexList ) } in demultiplex: ")

    if count == len( runList ): # no new items in DemultiplexList, therefore count == len( runList )
         print( 'all the runs have been demultiplexed\n' )

    if newRunID:

        flatNewRunList = ", ".join( newRunList )
        print( f"{len(newRunList)} new items to demux: {flatNewRunList}")

        print( f"Will work on this RunID: {newRunID}\n" ) # caution: if the corresponding _demux directory is somehow corrupted (wrong data in SampleSheetFilename or incomplete files), this will be printed over and over in the log file

        # essential condition to process is that RTAComplete.txt and SampleSheet.csv
        if demux.rtaCompleteFile in os.listdir( os.path.join( demux.rawDataDir, newRunID ) ) and demux.sampleSheetFileName in os.listdir( os.path.join( demux.rawDataDir, newRunID ) ):

            # if demux.debug: 
                # print( f"{demux.python3_bin} {demux.scriptFilePath} {newRunID}")

            if not os.path.exists( demux.scriptFilePath ):
                print( f"{demux.scriptFilePath} does not exist!" )
                exit( )

            # EXAMPLE: /bin/python3.11 /data/bin/current_demultiplex_script.py 210903_NB552450_0002_AH3VYYBGXK 
            return newRunID 
            # or
            return newRunIDs

            print( 'completed\n' )
        else:
            print( ', waiting for the run to complete\n' )

    demuxLogger.info( f"==< {demux.n}/{demux.totalTasks} tasks: Detecting if new runs exist finished\n")