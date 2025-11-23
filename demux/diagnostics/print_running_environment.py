import re
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# print_running_environment( )
########################################################################
def print_running_environment( demux ):
    """
    Print our running environment
    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Print out the current running environment ==\n", color="green", attrs=["bold"] ) )

    stateLetter = "R"  # initialize the state of this mini-automaton with 'R' cuz first item in the demux.globalDictionary starts with 'R'
    logString   = "log"

    # using the constants here allows us to make removing the directories more succinct.
    demuxLogger.info( f"To rerun this script run\n" )
    demuxLogger.info( termcolor.colored( f"\tclear; rm -rvf /data/" + "{" + f"{demux.config.constants.DEMULTIPLEX_DIR_NAME},{demux.config.constants.FOR_TRANSFER_DIR_NAME}" + "}" + f"/{demux.RunID}* " + f"&&  /data/bin/demultiplex.py {demux.RunID}\n\n", attrs=["bold"] ) )

    demuxLogger.debug( "=============================================================================")
    for key, value2 in demux.globalDictionary.items( ):         # take the key/label and the value of the key from the global dictionary
        if type( value2 ) is list:                              # if this is a list, print each individual member of the list
            if not len( value2 ):
                continue
            demuxLogger.debug( "=============================================================================")
            for index, value1 in enumerate( value2 ):       
                text = f"{key}[{str(index)}]:"
                text = f"{text:{demux.spacing3}}{value1}"
                demuxLogger.debug( text )
        else:
            text = f"{key:{demux.spacing2}}" + value2           # if it is not a list, print the item but
            if key[0] != stateLetter:                           # if the first letter differs from the state variable, print a '=====' row
                if re.search( logString, key, re.IGNORECASE):   # keep the *Log* variables together
                    demuxLogger.debug( text )
                    continue
                else:
                    stateLetter = key[0]
                demuxLogger.debug( "=============================================================================")
            demuxLogger.debug( text )

    demuxLogger.debug( "=============================================================================")
    demuxLogger.debug( "\n")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Print out the current running environment ==\n", color="red", attrs=["bold"] ) )
