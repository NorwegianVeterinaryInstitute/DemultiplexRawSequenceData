#!/usr/bin/python3.11

"""

Module to put methods for new run discovery

"""


########################################################################
# displayNewRuns
########################################################################

def detect_new_runs( ):
    """
    buzz
    """
    return


########################################################################
# existsNewRun
########################################################################

def existsNewRun( ):
    """
    kot
    """
    count = 0
    demux.newRunList = [ ]  # needs moving
    NewRunID = '' # turn this into an array
    for item in RunList: # iterate over RunList to see if there a new item in DemultiplexList, effectively comparing the contents of the two directories
        if item in DemultiplexList:
            count += 1
        else:
            NewRunList.append( item )
            NewRunID = item # any RunList item that is not in the demux list, gets processed

    localTime = strftime( "%Y-%m-%d %H:%M:%S", localtime( ) ) 
    demuxLogger.info( f"{ localTime } - { len( RunList ) } in rawdata and { len( DemultiplexList ) } in demultiplex: ")

    if count == len( RunList ): # no new items in DemultiplexList, therefore count == len( RunList )
         demuxLogger.info( 'all the runs have been demultiplexed\n' )
         return True

    if NewRunID: # TODO this needs it's own function.

        flatNewRunList = ", ".join( demux.newRunList )
        demuxLogger.info( f"{len(NewRunList)} new items to demux: {flatNewRunList}")

        demuxLogger.info( f"Will work on this RunID: {NewRunID}\n" ) # caution: if the corresponding _demux directory is somehow corrupted (wrong data in SampleSheetFilename or incomplete files), this will be printed over and over in the log file

        # essential condition to process is that RTAComplete.txt and SampleSheet.csv
        if demux.rtaCompleteFile in os.listdir( os.path.join( demux.rawDataDir, NewRunID ) ) and demux.sampleSheetFileName in os.listdir( os.path.join( demux.rawDataDir, NewRunID ) ):

            if not os.path.exists( demux.scriptFilePath ):
                demuxLogger.info( f"{demux.scriptFilePath} does not exist!" )
                exit( )

            # EXAMPLE: /bin/python3.11 /data/bin/demultiplex.py 210903_NB552450_0002_AH3VYYBGXK 
            demultiplex_script.main( NewRunID )

            demuxLogger.info( 'completed\n' )
            return True
        else:
            demuxLogger.info( ', waiting for the run to complete\n' )
            return False

    return True



########################################################################
# getDemultiplexedDirs
########################################################################

def getDemultiplexedDirs( ):
    """
    bar
    """

    demuxLogger.info( f"==> Getting demultiplexed directories started ==\n")

    for dirName in os.listdir( demux.demultiplexDir ):

        if demux.config.constants.DEMULTIPLEX_DIR_SUFFIX not in dirName: #  demultiplexed directories must have the  _demultiplex suffix # safety in case any other dirs included in /data/demultiplex
            continue
        if any( tag in dirName for tags in [ demux.nextSeq, demux.miSeq ] for tag in tags ): # ignore directories that have no sequncer tag
            demux.demultiplexList.append( dirName.replace( demux.config.constants.DEMULTIPLEX_DIR_SUFFIX, '' ) ) # null _demultiplex so we can compare the two lists below

    demuxLogger.info( f"==> Getting demultiplexed directories finished ==\n")

    return

########################################################################
# getRawdataDirs
########################################################################

def getRawdataDirs( ):
    """
    foo
    """

    demuxLogger.info( f"==> Getting new rawdata directories started ==\n" )

    for dirName in os.listdir( demux.rawDataDir ): # add directory names from the raw generated data directory

        if demux.config.constants.DEMULTIPLEX_DIR_SUFFIX in dirName: #  ignore any _demux dirs
            continue
        if any( tag in dirName for tags in [ demux.nextSeq, demux.miSeq ] for tag in tags ): # only add directories that have a sequncer tag
            demux.RunList.append( dirName )

    demuxLogger.info( f"==< Getting new rawdata directories finished ==\n" )

    return


