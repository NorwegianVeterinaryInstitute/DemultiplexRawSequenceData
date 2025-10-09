import glob
import logging
import os
import shutil
import subprocess
import sys
import termcolor

########################################################################
# prepareMultiQC
########################################################################

def prepare_multiqc( demux ):
    """
    Preperation to run MultiQC:
        copy *.zip and *.html from individual {demux.demultiplexRunIdDir}/{demux.RunIDShort}.{project} directories to the {demultiplexRunIdDirNewNamel}/{demux.RunIDShort}_QC directory
  
    INPUT
        the renamed project list
            does not include demux.TestProject
            deos not include any demux.ControlProjects

    """

    demux.n            = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for MultiQC started ==", color="yellow" ) )

    zipFiles       = [ ]
    HTMLfiles      = [ ]
    sourcefiles    = [ ]
    countZipFiles  = 0
    countHTMLFiles = 0
    totalZipFiles  = 0
    totalHTMLFiles = 0

    demuxLogger.debug( "-----------------")

    for project in demux.newProjectNameList:

        if any( var in project for var in [ demux.testProject ] ):                # skip the test project, 'FOO-blahblah-BAR'
            demuxLogger.warning( termcolor.colored( f"{demux.testProject} test project directory found in projects. Skipping.", color="magenta" ) )
            continue
        elif any( var in project for var in demux.controlProjects ):                # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        else:
            zipFilesPath   = os.path.join( demux.demultiplexRunIdDir, project ,'*' + demux.zipSuffix  ) # {project} here is already in the {RunIDShort}.{project_name} format
            htmlFilesPath  = os.path.join( demux.demultiplexRunIdDir, project, '*' + demux.htmlSuffix ) # {project} here is already in the {RunIDShort}.{project_name} format
            globZipFiles   = glob.glob( zipFilesPath )
            globHTMLFiles  = glob.glob( htmlFilesPath )
            countZipFiles  = len( globZipFiles )
            countHTMLFiles = len( globHTMLFiles )
            totalZipFiles  = totalZipFiles + countZipFiles
            totalHTMLFiles = totalHTMLFiles + countHTMLFiles
        
        if not globZipFiles or not globHTMLFiles:
            demuxLogger.debug( f"globZipFiles or globHTMLFiles came back empty on project {project}" )
            text = "DemultiplexRunIdDir/project:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{demux.demultiplexRunIdDir}/{project}" )
            text = "globZipFiles:"
            demuxLogger.debug( f"{text:{demux.spacing3}}" + f"{ ' '.join( globZipFiles  ) }"         )
            text = "globHTMLFiles:"
            demuxLogger.debug( f"{text:{demux.spacing3}}" + f"{ ' '.join( globHTMLFiles ) }"         )
            continue
        else:
            zipFiles  = zipFiles  + globZipFiles  # source zip files
            HTMLfiles = HTMLfiles + globHTMLFiles # source html files

        text  = termcolor.colored( f"Now working on project:", color="cyan", attrs=["reverse"]      ) 
        demuxLogger.debug( f"{text:{demux.spacing3}}" + project                                     )
        if demux.verbosity == 2:
            text = "added"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( countZipFiles  ) + " zip files"  )
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( countHTMLFiles ) + " HTML files" )
            text = "totalZipFiles:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( totalZipFiles  )                )
            text = "totalHTMLFiles:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + str( totalHTMLFiles )                )
            text  = f"zipFiles:"
            # text1 = " ".join( zipFiles[ counter ] )
            text1 = " ".join( zipFiles )
            demuxLogger.debug( f"{text:{demux.spacing3}}" + text1                                   )
            text  = f"HTMLfiles:"
            # text1 = " ".join( HTMLfiles[ counter ] )
            text1 = " ".join( HTMLfiles )
            demuxLogger.debug( f"{text:{demux.spacing3}}" + text1                                   )
        demuxLogger.debug( "-----------------")


    if ( not zipFiles[0] or not HTMLfiles[0] ):
        demuxLogger.critical( f"zipFiles or HTMLfiles in {inspect.stack()[0][3]} came up empty! Please investigate {demux.demultiplexRunIdDir}. Exiting.")
        logging.shutdown( )
        sys.exit( )

    demuxLogger.debug( "-----------------")
    sourcefiles = zipFiles + HTMLfiles
    destination = os.path.join( demux.demultiplexRunIdDir, demux.RunIDShort + demux.qcSuffix )     # QC folder eg /data/demultiplex/220603_M06578_0105_000000000-KB7MY_demultiplex/220603_M06578_QC/
    if demux.verbosity == 2:
        text        = "sourcefiles:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + str( ' '.join( sourcefiles ) ) + '\n' )
    demuxLogger.debug( "-----------------")

    if len( sourcefiles ) != totalZipFiles + totalHTMLFiles:
        text =  f"len(sourcefiles) {len(sourcefiles)} not equal to totalZipFiles ({totalZipFiles}) plus totalHTMLFiles ({totalHTMLFiles}) == {totalZipFiles + totalHTMLFiles }"
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    if not os.path.isdir( destination ) :
        text =  f"Directory {destination} does not exist. Please check the logs. You can also just delete {demux.demultiplexRunIdDir} and try again."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    try:
        # EXAMPLE: /usr/bin/cp project/*zip project/*html DemultiplexDir/demux.RunIDShort.short_QC # (destination is a directory)
        for source  in sourcefiles :
            text    = "Command to execute:"
            command = f"/usr/bin/cp {source} {destination}"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + command )
            shutil.copy2( source, destination )     # destination has to be a directory
    except FileNotFoundError as err:                # FileNotFoundError is a subclass of OSError[ errno, strerror, filename, filename2 ]
        text = [ f"\tFileNotFoundError in {inspect.stack()[0][3]}()" ,
                 f"\terrno:\t{err.errno}",
                 f"\tstrerror:\t{err.strerror}",
                 f"\tfilename:\t{err.filename}",
                 f"\tfilename2:\t{err.filename2}",
                 f"Exiting."
               ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for multiQC finished ==\n", color="cyan" ) )


########################################################################
# fastqc
########################################################################

def fastqc( demux ):
    """
    fastQC: Run /data/bin/fastqc (which is a symlink to the real qc)
    """

    demux.n            = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: fastQC started ==", color="yellow" ) )

    command             = demux.fastqc_bin
    argv                = [ command, '-t', str(demux.threadsToUse), *demux.newProjectFileList ]  # the * operator on a list/array "splats" (flattens) the values in the array, breaking them down to individual arguemtns

    arguments = " ".join( argv[1:] )
    text = "Command to execute:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{command} {arguments}")     # exclude the first element of the array # example for filename: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/

    try:
        # EXAMPLE: /usr/local/bin/fastqc -t 4 {demux.demultiplexRunIdDir}/{project}/*fastq.gz > demultiplexRunIdDir/demultiplex_log/04_fastqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demux.demultiplexRunIdDir, check = True, encoding = demux.decodeScheme )
    except ChildProcessError as err: 
            text = [ "Caught exception!",
                     f"Command: {err.cmd}", # interpolated strings
                     f"Return code: {err.returncode}"
                     f"Process output: {err.output}",
                     f"Exiting."
                ]
            text = '\n'.join( text )
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

    # log FastQC output
    fastQCLogFileHandle = ""
    try: 
        fastQCLogFileHandle = open( demux.fastQCLogFilePath, "x" ) # fail if file exists
        if demux.verbosity == 2:
            text = f"fastQCLogFilePath:"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.fastQCLogFilePath )
        fastQCLogFileHandle.write( result.stdout ) 
        fastQCLogFileHandle.close( )
    except FileNotFoundError as err:
        text = [    f"Error opening fastQCLogFilePath: {demux.fastQCLogFilePath} does not exist",
                    f"err.filename:  {err.filename}",
                    f"Exiting!"
                ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: FastQC complete ==\n", color="cyan" )  )



########################################################################
# multiqc
########################################################################

def multiqc( demux ):
    """
    Run /data/bin/multiqc against the project list.

    Result are zip files in the individual project directories
    """ 

    demux.n            = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: multiQC started ==", color="yellow" ) )

    command = demux.mutliqc_bin
    argv    = [ command, demux.demultiplexRunIdDir,
               '-o', demux.demultiplexRunIdDir 
              ]
    args    = " ".join(argv[1:]) # ignore the command part so we can logging.debug this string below, fresh all the time, in case we change tool command name

    text = "Command to execute:"
    demuxLogger.debug( f"{text:{demux.spacing2}}{command} {args}" )

    try:
        # EXAMPLE: /usr/local/bin/multiqc {demux.demultiplexRunIdDir} -o {demux.demultiplexRunIdDir} 2> {demux.demultiplexRunIdDir}/demultiplex_log/05_multiqc.log
        result = subprocess.run( argv, capture_output = True, cwd = demux.demultiplexRunIdDir, check = True, encoding = demux.decodeScheme )
    except ChildProcessError as err: 
        text = [    f"Caught exception!",
                    f"Command:\t{err.cmd}", # interpolated strings
                    f"Return code:\t{err.returncode}"
                    f"Process output: {err.output}",
                    f"Exiting."
                ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    # log multiqc output
    demux.multiQCLogFilePath  = os.path.join( demux.demultiplexLogDirPath, demux.multiqcLogFileName ) ############# FIXME FIXME FIXME FIXME take out
    try: 
        multiQCLogFileHandle      = open( demux.multiQCLogFilePath, "x" ) # fail if file exists
        if demux.verbosity == 2:
            text = "multiQCLogFilePath"
            demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.multiQCLogFilePath )
        multiQCLogFileHandle.write( result.stderr ) # The MultiQC people are special: They write output to stderr
        multiQCLogFileHandle.close( )
    except OSError as err:
        text = [    f"Caught exception!",
                    f"Command: {err.cmd}", # interpolated strings
                    f"Return code: {err.returncode}"
                    f"Process output: {err.stdout}",
                    f"Process error:  {err.stderr}",
                    f"Exiting."
                 ]
        text = '\n'.join( text )
        demuxFailureLogger.critical( text )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )    


    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: multiQC finished ==\n", color="cyan" ) )



########################################################################
# quality_check
########################################################################

def quality_check( demux ):
    """
    Run QC on the sequence run files

        FastQC takes the fastq.gz R1 and R2 of each sample sub-project and performs some Quality Checking on them
            The result of running FastQC is html and .zip files, one for each input fastq.gz file. The .zip file contails a directory with the complete analysis of the sample. The .html file is the entry point for all the stuff in the subdirectory

        MultiQC takes {EXPLAIN INPUT HERE}
    """

    demux.n            = demux.n + 1

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Quality Check started ==", color="green", attrs=["bold"] ) )

    fastqc( demux )
    prepare_multiqc( demux )
    multiqc( demux )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Quality Check finished ==\n", color="red", attrs=["bold"] ) )

