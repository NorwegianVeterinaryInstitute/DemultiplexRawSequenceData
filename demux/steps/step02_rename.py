#!/usr/bin/python3.11

import glob
import logging
import os
import sys
import termcolor

########################################################################
# renameDirectories( )
########################################################################

def rename_directories( demux ):
    """
        For each project directory in demux.projectList
            rename the project directory  to conform from the {demux.demultiplexRunIdDir}/{project} pattern to the {demux.demultiplexRunIdDir}/{demux.RunIDShort}.{project}

        Why you ask?
            That's how the original script does it (TRADITION!)

            One good reason is, of course to keep track of the file, if something goes wrong.
    """

    demux.n            = demux.n + 1
    demuxLogger        = logging.getLogger("__main__")        # logging to output
    demuxFailureLogger = logging.getLogger("demuxFailureLogger") # logging to email

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Renaming project directories from project_name to RunIDShort.project_name ==\n", color="green", attrs=["bold"] ) )


    for index, item in enumerate( demux.projectList ):
        text = f"demux.projectList[{index}]:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + item) # make sure the debugging output is all lined up.

    for project in demux.projectList: # rename the project directories

        oldname = os.path.join( demux.demultiplexRunIdDir, project )
        newname = os.path.join( demux.demultiplexRunIdDir, demux.RunIDShort + '.' + project )
        olddirExists = os.path.isdir( oldname )
        newdirExists = os.path.isdir( newname )

        # make sure oldname dir exists
        # make sure newname dir name does not exist
        if olddirExists and not newdirExists: # rename directory

            try: 
                os.rename( oldname, newname )
            except FileNotFoundError as err:
                text = [    f"Error during renaming {oldname}:", 
                            f"oldname: {oldname}",
                            f"oldfileExists: {oldfileExists}",
                            f"newfile: {newname}",
                            f"newfileExists: {newfileExists}",
                            f"err.filename:  {err.filename}",
                            f"err.filename2: {err.filename2}",
                            f"Exiting!"
                        ]
                text = '\n'.join( text )
                demuxFailureLogger.critical( f"{ text }" )
                demuxLogger.critical( f"{ text }" )
                logging.shutdown( )
                sys.exit( )

            demuxLogger.debug( f"Renaming " + termcolor.colored(  f"{oldname:92}", color="cyan", attrs=["reverse"] ) + " to " + termcolor.colored(  f"{newname:106}", color="yellow", attrs=["reverse"] ) )

    for index, item in enumerate( demux.newProjectFileList ):
        text = f"demux.newProjectFileList[{index}]:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + item) # make sure the debugging output is all lined up.

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Renaming project directories from project_name to RunIDShort.project_name ==\n", color="red", attrs=["bold"] ) )


########################################################################
# rename_files( )
########################################################################

def rename_files( demux ):
    """
    Rename the files within each {project} to conform to the {RunIDShort}.{filename}.fastq.gz pattern

    Why? see above? it's always been done that way.
    """

    demux.n            = demux.n + 1
    demuxLogger        = logging.getLogger("demuxLogger")        # logging to output
    demuxFailureLogger = logging.getLogger("demuxFailureLogger") # logging to email

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Rename files ==\n", color="green" ) )

    oldname            = ""
    newname            = ""
    for project in demux.projectList: # rename files in each project directory

        if any( var in project for var in demux.controlProjects ):      # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        elif project == demux.testProject:                              # ignore the test project
            demuxLogger.debug( f"Test project '{demux.testProject}' detected. Skipping." )
            continue

        compressedFastQfilesDir = os.path.join( demux.demultiplexRunIdDir, project )
        # text1 = termcolor.colored( "Now working on project:", color="cyan", attrs=["reverse"] )
        text1 = "Now working on project:"
        text2 = "compressedFastQfilesDir:"
        demuxLogger.debug( termcolor.colored( f"{text1:{demux.spacing2 - 1}}", color="cyan", attrs=["reverse"] ) + " " + termcolor.colored( f"{project}", color="cyan", attrs=["reverse"] ) )
        demuxLogger.debug( f"{text2:{demux.spacing2}}{compressedFastQfilesDir}")

        filesToSearchFor     = os.path.join( compressedFastQfilesDir, '*' + demux.compressedFastqSuffix )
        compressedFastQfiles = glob.glob( filesToSearchFor )            # example: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH/sample*fastq.gz

        if not any( compressedFastQfiles ): # if array is empty
            text = f"\n\nProject {project} does not contain any .fastq.gz entries"
            text = f"{text} | method {inspect.stack()[0][3]}() ]"
            text = f"{text}\n\n"

            demuxFailureLogger.critical( text )
            demuxLogger.critical( text )
            sys.exit( )

        text = "fastq files for '" + project + "':"
        demuxLogger.debug( f"{text:{demux.spacing2}}{filesToSearchFor}" )

        for index, item in enumerate( compressedFastQfiles ):
            text1 = "compressedFastQfiles[" + str(index) + "]:"
            demuxLogger.debug( f"{text1:{demux.spacing3}}{item}" )


        demuxLogger.debug( "-----------------")
        demuxLogger.debug( f"Move commands to execute:" )
        for file in compressedFastQfiles: # compressedFastQfiles is already in absolute path format
    
            # get the base filename. We picked up sample*.{CompressedFastqSuffix} and we have to rename it to {demux.RunIDShort}sample*.{CompressedFastqSuffix}
            baseFileName = os.path.basename( file )

            oldname     = file
            newname     = os.path.join( demux.demultiplexRunIdDir, project, demux.RunIDShort + '.' + baseFileName )
            renamedFile = os.path.join( demux.demultiplexRunIdDir, demux.RunIDShort + '.' + project, demux.RunIDShort + '.' + baseFileName ) # saving this var to use later when renaming directories
                                # The idea here is that the format of the new path is the fully renamed directory + fully renamed file
                                #
                                # DO NOT REMOVE THE DOTS. Look at https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/86#issuecomment-2527335084
                                # if you want some documentation as to 'why'

            if renamedFile not in demux.newProjectFileList:
                demux.newProjectFileList.append( renamedFile )  # demux.newProjectFileList is used in fastQC( )
                                                                # We are saving here in order to not have to read in the
                                                                # filenames, again

            text  = f"/usr/bin/mv {oldname} {newname}"
            demuxLogger.debug( " "*demux.spacing1 + text )
            
            # make sure oldname files exist
            # make sure newname files do not exist
            oldfileExists = os.path.isfile( oldname )
            newfileExists = os.path.isfile( newname )

            if oldfileExists and not newfileExists:
                try: 
                    os.rename( oldname, newname )
                except FileNotFoundError as err:
                    text = [    f"Error during renaming {oldname}:",
                                f"oldname: {oldname}\noldfileExists: {oldfileExists}",
                                f"newname: {newname}\nnewfileExists: {newfileExists}",
                                f"err.filename:  {err.filename}",
                                f"err.filename2: {err.filename2}",
                                f"Exiting!"
                         ]
                    text = '\n'.join( text )
                    demuxFailureLogger.critical( f"{ text }" )
                    demuxLogger.critical( f"{ text }" )
                    logging.shutdown( )
                    sys.exit( )
        demuxLogger.debug( "-----------------")

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Copy {demux.sampleSheetFilePath} to {demux.demultiplexRunIdDir} ==\n", color="red" ) )

########################################################################
# rename_files_and_directories( )
########################################################################

def rename_files_and_directories( demux ):
    """
    Rename any [sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ] files inside 
        {demux.demultiplexRunIdDir}/{demux.RunIDShort}/[ { projectList[0] }, .. , { projectList[n] } ] to match the pattern
        {demux.RunIDShort}.[sample-1_S1_R1_001.fastq.gz, .. , sample-1_S1_Rn_001.fastq.gz ]
    
    Then rename the 
        {demux.demultiplexRunIdDir}/{demux.RunIDShort}/[ { projectList[0] }, .. , { projectList[n] } ] to match the pattern
        {demux.demultiplexRunIdDir}/{demux.RunIDShort}/{demux.RunIDShort}.[ {projectList[0] }, .. , { projectList[n] } ] to match the pattern
        
    Examples:
    
        demultiplexRunIdDir: /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/
        Sample_Project:      SAV-amplicon-MJH              ### DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'
        demux.RunIDShort:    220314_M06578

        1. Rename the files:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R1_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R1_001.fastq.gz
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/sample-1_S1_R2_001.fastq.gz /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH/220314_M06578.sample-1_S1_R2_001.fastq.gz

        2. Rename the base directory, for each project:
            /bin/mv /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/SAV-amplicon-MJH /data/demultiplex/220314_M06578_0091_000000000-DFM6K_demultiplex/220314_M06578.SAV-amplicon-MJH

    """

    demux.n            = demux.n + 1
    demuxLogger        = logging.getLogger("demuxLogger")        # logging to output
    demuxFailureLogger = logging.getLogger("demuxFailureLogger") # logging to email

    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Renaming started ==", color="green", attrs=["bold"] ) )

    text = f"demultiplexRunIdDir:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.demultiplexRunIdDir )    # tabulation error
    text = f"RunIDShort:"
    demuxLogger.debug( f"{text:{demux.spacing2}}" + demux.RunIDShort )
    if demux.verbosity == 2:
        text = "demux.projectList:"
        demuxLogger.debug( f"{text:{demux.spacing2}}" + f"{demux.projectList}" )

    rename_files( demux )        # CHECK IF FILES ARE RENAMED CORRECTLY:
                                 #
                                 #  /data/for_transfer/201218_M06578_0041_000000000-JF7TM/MHC-amplicon-UG/201218_M06578.*tar.gz
    rename_directories( demux )  # same, check if the directories were renamed correctly

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Renaming finished ==", color="red", attrs=["bold"] ) )
