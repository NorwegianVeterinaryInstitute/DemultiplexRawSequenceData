import logging
import os
import termcolor

from demux.core    import demux
from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# setup_environment( )
########################################################################

def setup_environment( RunID ):
    """
    Setup the variables for our environment
    """

    demux.n = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Set up the current running environment ==\n", color="green", attrs=["bold"] ) )

    # this should be moved into the object initilization, not the environment init
    # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/127

    demux.RunID                         = RunID
    demux.runIDShort                    = '_'.join( RunID.split('_')[0:2] ) # this should be turned into a setter in the demux object
######################################################
    demux.rawDataRunIDdir               = os.path.join( demux.rawDataDir,           demux.RunID )
    demux.sampleSheetFilePath           = os.path.join( demux.rawDataRunIDdir,      demux.sampleSheetFileName )
    demux.rtaCompleteFilePath           = os.path.join( demux.rawDataRunIDdir,      demux.rtaCompleteFile )

    demux.parse_sample_sheet( )         # get the list of projects in this current run

######################################################
    demux.demultiplexRunIDdir           = os.path.join( demux.demultiplexDir,       demux.RunID + demux.demultiplexDirSuffix ) 
    demux.demultiplexLogDirPath         = os.path.join( demux.demultiplexRunIDdir,  demux.demultiplexLogDirName ) 
    demux.demuxQCDirectoryName          = demux.runIDShort + demux.qcSuffix              # example: 200624_M06578_QC  # QCSuffix is defined in object demux
    demux.demuxQCDirectoryFullPath      = os.path.join( demux.demultiplexRunIDdir,  demux.demuxQCDirectoryName  )
    demux.bcl2FastqLogFile              = os.path.join( demux.demultiplexRunIDdir,  demux.demultiplexLogDirPath, demux.bcl2FastqLogFileName )
######################################################
    demux.forTransferRunIdDir           = os.path.join( demux.forTransferDir,       demux.RunID )
    demux.forTransferQCtarFile          = os.path.join( demux.forTransferRunIdDir,  demux.RunID + demux.qcSuffix + demux.tarSuffix )
######################################################

    # set up
    demux.demuxRunLogFilePath           = os.path.join( demux.logDirPath,            demux.RunID + demux.logSuffix )
    demux.demuxCumulativeLogFilePath    = os.path.join( demux.logDirPath,            demux.demuxCumulativeLogFileName )
    demux.demultiplexLogDirPath         = os.path.join( demux.demultiplexRunIDdir,   demux.demultiplexLogDirName )
    demux.demultiplexScriptLogFilePath  = os.path.join( demux.demultiplexLogDirPath, demux.scriptRunLogFileName )
    demux.fastQCLogFilePath             = os.path.join( demux.demultiplexLogDirPath, demux.fastqcLogFileName )
    demux.mutliQCLogFilePath            = os.path.join( demux.demultiplexLogDirPath, demux.multiqcLogFileName )
    demux.sampleSheetArchiveFilePath    = os.path.join( demux.sampleSheetDirPath,    demux.RunID + demux.csvSuffix ) # .dot is included in csvSuffix


######################################################################################################################################################
# any mention of the globalDictionary should be move dover to a helper function:
# make it explicit: treat globalDictionary as a state snapshot. Rename it to state_snapshot or state_dict and rebuild it only when needed via a helper like:
# def capture_state(demux):
#    demux.state_snapshot = {k: getattr(demux, k) for k in demux.globalDictionary}
######################################################################################################################################################

    # maintain the order added this way, so our little stateLetter trick will work
    demux.globalDictionary = {  
        'RunID'                         : str( ),
        'runIDShort'                    : str( ),
        'rawDataRunIDdir'               : str( ),
        'rtaCompleteFilePath'           : str( ),
        'sampleSheetFilePath'           : str( ),
        'demultiplexRunIDdir'           : str( ),
        'demultiplexLogDirPath'         : str( ),
        'demuxQCDirectoryFullPath'      : str( ),
        'demuxRunLogFilePath'           : str( ),
        'demuxCumulativeLogFilePath'    : str( ),
        'demultiplexLogDirPath'         : str( ),
        'demultiplexScriptLogFilePath'  : str( ),
        'bcl2FastqLogFile'              : str( ),
        'fastQCLogFilePath'             : str( ),
        'mutliQCLogFilePath'            : str( ),
        'forTransferRunIdDir'           : str( ),
        'forTransferQCtarFile'          : str( ),
        'sampleSheetArchiveFilePath'    : str( ),
        'projectList'                   : list( ),
        'newProjectNameList'            : list( ),
        'controlProjectsFoundList'      : list( ),
        'tarFilesToTransferList'        : list( )
    }


    # add the QC file to the list of tar files, even if duplicate
    demux.tarFilesToTransferList.append( demux.forTransferQCtarFile )
    # maintain the order added this way, so our little stateLetter trick will work
    demux.globalDictionary[ 'RunID'                        ] = demux.RunID
    demux.globalDictionary[ 'runIDShort'                   ] = demux.runIDShort
    demux.globalDictionary[ 'rawDataRunIDdir'              ] = demux.rawDataRunIDdir
    demux.globalDictionary[ 'rtaCompleteFilePath'          ] = demux.rtaCompleteFilePath
    demux.globalDictionary[ 'sampleSheetFilePath'          ] = demux.sampleSheetFilePath
    demux.globalDictionary[ 'demultiplexRunIDdir'          ] = demux.demultiplexRunIDdir
    demux.globalDictionary[ 'demultiplexLogDirPath'        ] = demux.demultiplexLogDirPath
    demux.globalDictionary[ 'demuxQCDirectoryFullPath'     ] = demux.demuxQCDirectoryFullPath
    demux.globalDictionary[ 'demuxRunLogFilePath'          ] = demux.demuxRunLogFilePath
    demux.globalDictionary[ 'demuxCumulativeLogFilePath'   ] = demux.demuxCumulativeLogFilePath
    demux.globalDictionary[ 'demultiplexLogDirPath'        ] = demux.demultiplexLogDirPath
    demux.globalDictionary[ 'demultiplexScriptLogFilePath' ] = demux.demultiplexScriptLogFilePath
    demux.globalDictionary[ 'bcl2FastqLogFile'             ] = demux.bcl2FastqLogFile
    demux.globalDictionary[ 'fastQCLogFilePath'            ] = demux.fastQCLogFilePath
    demux.globalDictionary[ 'mutliQCLogFilePath'           ] = demux.mutliQCLogFilePath
    demux.globalDictionary[ 'forTransferRunIdDir'          ] = demux.forTransferRunIdDir
    demux.globalDictionary[ 'forTransferQCtarFile'         ] = demux.forTransferQCtarFile
    demux.globalDictionary[ 'sampleSheetArchiveFilePath'   ] = demux.sampleSheetArchiveFilePath
    demux.globalDictionary[ 'projectList'                  ] = demux.projectList
    demux.globalDictionary[ 'newProjectNameList'           ] = demux.newProjectNameList
    demux.globalDictionary[ 'controlProjectsFoundList'     ] = demux.controlProjectsFoundList
    demux.globalDictionary[ 'tarFilesToTransferList'       ] = demux.tarFilesToTransferList



    if 'demuxLogger' in logging.Logger.manager.loggerDict.keys():
        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Set up the current running environment ==\n", color="red", attrs=["bold"] ) )
    else:
        print( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Set up the current running environment ==\n", color="red", attrs=["bold"] ) )
