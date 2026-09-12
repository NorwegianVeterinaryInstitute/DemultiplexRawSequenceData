import termcolor

from demux.config import constants as constants

from demux.loggers import demuxLogger, demuxFailureLogger

SEPARATOR:str = "============================================================================="

# explicit grouping: section -> globalDictionary keys. Replaces the stateLetter
# first-letter automaton, which depended on globalDictionary insertion order.
SECTIONS:dict[ str, list[ str ] ] = {
    'Run':          [ 'RunID', 'runIDShort', 'rawDataRunIDdir', 'rtaCompleteFilePath', 'sampleSheetFilePath' ],
    'Demultiplex':  [ 'demultiplexRunIDdir', 'demuxQCDirectoryFullPath' ],
    'Logs':         [ 'demuxRunLogFilePath', 'demuxCumulativeLogFilePath', 'demultiplexLogDirPath', 'demultiplexScriptLogFilePath', 'bcl2FastqLogFile', 'fastQCLogFilePath', 'mutliQCLogFilePath' ],
    'Transfer':     [ 'forTransferRunIdDir', 'forTransferQCtarFile', 'sampleSheetArchiveFilePath' ],
    'Lists':        [ 'projectList', 'newProjectNameList', 'controlProjectsFoundList', 'tarFilesToTransferList' ],
}

########################################################################
# print_running_environment( )
########################################################################
def print_running_environment( demux ):
    """
    Print our running environment, grouped by the explicit SECTIONS map.
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Print out the current running environment ==\n", color="green", attrs=["bold"] ) )

    # using the constants here allows us to make removing the directories more succinct.
    demuxLogger.info( f"To rerun this script run\n" )
    demuxLogger.info( termcolor.colored( f"\tclear; rm -rvf /data/" + "{" + f"{constants.DEMULTIPLEX_DIR_NAME},{constants.FOR_TRANSFER_DIR_NAME}" + "}" + f"/{demux.RunID}* " + f"&& {demux.exec_path} {demux.RunID}\n\n", attrs=["bold"] ) )

    printed_keys:list[ str ] = [ ]

    for section, keys in SECTIONS.items( ):
        demuxLogger.debug( SEPARATOR )
        for key in keys:
            if key not in demux.globalDictionary:
                continue
            _print_item( demux, key, demux.globalDictionary[ key ] )
            printed_keys.append( key )

    # catch-all: any key added to globalDictionary but not yet to SECTIONS still prints
    leftover_keys:list[ str ] = [ key for key in demux.globalDictionary if key not in printed_keys ]
    if leftover_keys:
        demuxLogger.debug( SEPARATOR )
        for key in leftover_keys:
            _print_item( demux, key, demux.globalDictionary[ key ] )

    demuxLogger.debug( SEPARATOR )
    demuxLogger.debug( "\n")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Print out the current running environment ==\n", color="red", attrs=["bold"] ) )


def _print_item( demux, key:str, value ) -> None:
    """
    Print one globalDictionary entry: lists one line per member, everything else on one line.
    """
    if type( value ) is list:
        for index, item in enumerate( value ):
            text:str = f"{key}[{str(index)}]:"
            text = f"{text:{demux.spacing3}}{item}"
            demuxLogger.debug( text )
    else:
        demuxLogger.debug( f"{key:{demux.spacing2}}" + value )
