#

import os
import sys
import tarfile
import logging
import inspect
import termcolor

from demux.loggers import demuxLogger, demuxFailureLogger

########################################################################
# tar_project_files
########################################################################


def collect_projects_to_tar( demux ):
   
    """
    Prepare a list of the projects to tar under /data/for_transfer 
    """

    # this looks duplicated from demux.getProjects( ) and it is, but I am not sure how to resolve the duplication. Let's keep this for now as second check, as this is more complete than
    # the one found in demux.getProjects( )
    # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/87
    
    tarFile = ""
    projectsToProcessList = [ ]
    for project in demux.newProjectNameList:                                        # this loop is a check against project names which are not suppossed to be eventually tarred

        if any( var in project for var in [ demux.qcSuffix ] ):                     # skip anything that includes '_QC'
            demuxLogger.warning( f"{demux.qcSuffix} directory found in projects. Skipping." )
            continue
        elif any( var in project for var in [ demux.testProject ] ):                # skip the test project, 'FOO-blahblah-BAR'
            demuxLogger.warning( f"{demux.testProject} test project directory found in projects. Skipping." )
            continue
        elif any( var in project for var in demux.controlProjects ):                # if the project name includes a control project name, ignore it
            demuxLogger.warning( termcolor.colored( f"\"{project}\" control project name found in projects. Skipping, it will be handled in controlProjectsQC( ).\n", color="magenta" ) )
            continue
        elif demux.temp in project:                                                 # disregard the temp directory
            demuxLogger.warning( f"{demux.temp} directory found. Skipping." )
            continue
        elif demux.demultiplexLogDirPath in project: # disregard demultiplex_log
            demuxLogger.warning( f"{demux.demultiplexLogDirPath} directory found. Skipping." )
            continue

        if any( tag in project for tags in [ demux.nextSeq, demux.miSeq ] for tag in tags ):         # Make sure there is a nextseq or misqeq tag, before adding the directory to the projectsToProcessList
            projectsToProcessList.append( project )
            demuxLogger.debug( f"{project:{demux.spacing2}} added to projectsToProcessList." )

    return projectsToProcessList

def tar_project_files( demux ):
    """
    tar all project files

    """
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Adding files to tape archives started ==", color="yellow" ) )

    projectsToProcessList = [ ]
    projectsToProcessList = collect_projects_to_tar( demux ) # get the projectsToProcessList to tar files from demux.demultiplexRunIDdir to demux.forTransferRunIdDir
    os.chdir( demux.demultiplexRunIDdir )       # change the current working directory to demux.demultiplexRunIDdir, so we can get nice relative paths 

    # this means that while we are sitting in data.demultiplexRunIDdir, we are saving tar files under demux.forTransferRunIdDir
    counter = 0         # used in counting how many projects we have archived so far
    for project in projectsToProcessList: # this needs to be pregenerated # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/120

        demuxLogger.debug( termcolor.colored( f"\n== walk the file tree, {inspect.stack()[0][3]}() , {demux.demultiplexRunIDdir}/{project} ======================", attrs=["bold"] ) )

        tarFile    = os.path.join(  demux.forTransferRunIdDir, project + demux.tarSuffix )

        if not os.path.isfile( tarFile ):                                   # Using absolute path to open the tar file
            tarFileHandle = tarfile.open( name = tarFile, mode = "w:" )     # Open a tar file under  demux.forTransferRunIdDir as project + demux.tarSuffix . example: /data/for_transfer/220603_M06578_0105_000000000-KB7MY/220603_M06578.42015-NORM-VET.tar
        else:
            text = f"{tarFile} exists. Please investigate or delete. Exiting."
            demuxFailureLogger.critical( f"{ text }" )
            demuxLogger.critical( f"{ text }" )
            logging.shutdown( )
            sys.exit( )

#---------- Iterrate through demux.demultiplexRunIDdir/projectsToProcessList and make a single tar file for each project under data.forTransferRunIdDir   ----------------------

        counter = counter + 1
        demuxLogger.info( termcolor.colored( f"==> Archiving {project} ( {counter} out of { len( projectsToProcessList ) } projects ) ==================", color="yellow", attrs=["bold"] ) )
        text = "tarFile:"
        demuxLogger.debug( f"{text:{demux.spacing2}}" + os.path.join( demux.forTransferRunIdDir, tarFile ) )  # print the absolute path
        for directoryRoot, dirnames, filenames, in os.walk( project, followlinks = False ): 
             for file in filenames:
                # add one file at a time so we can give visual feedback to the user that the script is processing files
                # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
                # of output that make users uncomfortable
                filenameToTar = os.path.join( project, file )
                tarFileHandle.add( name = filenameToTar, recursive = False )
                text = "filenameToTar:"
                text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
                demuxLogger.info( text + filenameToTar )

        tarFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on

        demuxLogger.info( termcolor.colored( f'==< Archived {project} ({counter} out of { len( projectsToProcessList ) } projects ) ==================\n', color="yellow", attrs=["bold"] ) )

#---------- Finished taring   -----------------------------------------------------------------------------------------------------------------------------------------------------
    
    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Adding files to tape archives finished ==", color="cyan" ) )



########################################################################
# create_qc_tar_file
########################################################################

def create_qc_tar_file( demux ):
    """
    create the qc.tar file by reading from /data/demultiplex/RunID/RunID_QC and writing the tar file to /data/for_transfer/RunID/demux.RunIDShort_qc.tar
    What to put inside the QC file: {demux.RunIDShort}_QC and multiqc_data

    """

    demuxLogger.info( termcolor.colored( f"==> Archiving {demux.demuxQCDirectoryFullPath} =================", color="yellow", attrs=["bold"] ) )

    if demux.verbosity == 2:
        text = "demuxQCDirectoryFullPath:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + demux.demuxQCDirectoryFullPath )
        text = "multiqc_data:"
        demuxLogger.debug( f"{text:{demux.spacing3}}" + demux.multiqc_data )

    if not os.path.isfile( demux.forTransferQCtarFile ): # exit if /data/for_transfer/RunID/qc.tar file exists.
        tarQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "w:" )
    else:
        text = f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    # paths are relative here, cuz we chdir( ) in tarProjectFiles( )
    for directoryRoot, dirnames, filenames, in os.walk( demux.demuxQCDirectoryName , followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the Archivinguser that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( demux.demuxQCDirectoryName, file ) # demux.demuxQCDirectoryName is relative, for example '220603_M06578_QC'
            tarQCFileHandle.add( name = filenameToTar, recursive = False )
            text = "filenameToTar:"
            text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
            demuxLogger.info( text + filenameToTar )

    tarQCFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on

    demuxLogger.info( termcolor.colored( f"==> Archived {demux.demuxQCDirectoryFullPath} ==================", color="yellow", attrs=["bold"] ) )




########################################################################
# create_multiqc_tar_file
########################################################################

def create_multiqc_tar_file( demux ):
    """
    Add the multiqc_data to the qc.tar under /data/for_transfer/RunID
    """
    demuxLogger.info( termcolor.colored( f"==> Archiving {demux.multiqc_data} ==================", color="yellow", attrs=["bold"] ) )

    if os.path.isfile( demux.forTransferQCtarFile ): # /data/for_transfer/RunID/qc.tar must exist before writi
        multiQCFileHandle = tarfile.open( demux.forTransferQCtarFile, "a:" ) # "a:" for exclusive, uncompresed append.
    else:
        text = f"{demux.forTransferQCtarFile} exists. Please investigate or delete. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    # paths are relative here, cuz we chdir( ) in tarProjectFiles( )
    for directoryRoot, dirnames, filenames, in os.walk( os.path.join( demux.multiqc_data ), followlinks = False ): 
         for file in filenames:
            # add one file at a time so we can give visual feedback to the user that the script is processing files
            # less efficient than setting recursive to = True and name to a directory, but it prevents long pauses
            # of output that make users uncomfortable
            filenameToTar = os.path.join( demux.multiqc_data, file )
            multiQCFileHandle.add( name = filenameToTar, recursive = False )
            text = "filenameToTar"
            text = f"{inspect.stack()[0][3]}: {text:{demux.spacing2}}"
            demuxLogger.info( text + filenameToTar )

    # bothisfiledemux.RunIDShort}_QC and multidata_qc go in the same tar file
    multiQCFileHandle.close( )      # whatever happens make sure we have closed the handle before moving on
    demuxLogger.info( termcolor.colored( f"==> Archived {demux.multiqc_data} ==================", color="yellow", attrs=["bold"] ) )    



########################################################################
# prepareDelivery
########################################################################

def prepare_delivery( demux ):
    """
    Prepare the appropriate tar files for transfer and write the appropirate .md5/.sha512 checksum files

    Preparing has the following steps:
        tar the entire DemultiplexRunIdDir
        tar the QC directory
        make the DemultiplexRunIdDir/temp directory
        copy all tar/md5/sha512 files into DemultiplexRunIdDir/temp
        md5/sha512 the DemultiplexRunIdDir tar file
        md5/sha512 the QC tar file
        make the /data/for_delivery/RunID directory
        copy the resulting Demux and QC tar files along with the associated .md5/.sha512 files to /data/for_transfer/RunID
        run clean up
            delete the DemultiplexRunIdDir/temp directory

    WHAT TO PUT INSIDE THE QC FILE
        {demux.RunIDShort}_QC/
        multiqc_data/

    WHAT TO IGNORE
        From time to time, if the library to be sequenced has extra space, the lab includes a control sample
        We are going to ignore them for the purpose of tarring and delivery and run QC separate.
        The name of the projects are stored in demux.ControlProjects
            would be a good idea to pull the control projects right out of irida or clarity.

    Original commands:
        EXAMPLE: /bin/tar -cvf tar_file -C DemultiplexDir folder 
        EXAMPLE: /bin/md5sum tar_file | sed_command > md5_file

    First, exclude:
        qcSuffix project
        test projects used by this software
        control projects inserted by the lab periodically
        demultiplex_log directory that stores all the logs for the run

    For the projects left, 
        create the directory projects under /data/for_transfer/RunID/{project_name}
        create the tar file
            by recursing down the /data/RunID_demultiplex
    
    Finally
        crete the _QC tar file

    """

    demux.n = demux.n + 1
    demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Preparing files for delivery started ==", color="green", attrs=["bold"] ) )


    if not os.path.isdir( demux.forTransferRunIdDir ): # we save each tar file into its own directory
        text = f"Error: {demux.forTransferRunIdDir} does not exist. Exiting."
        demuxFailureLogger.critical( f"{ text }" )
        demuxLogger.critical( f"{ text }" )
        logging.shutdown( )
        sys.exit( )

    tar_project_files( demux )
    create_qc_tar_file( demux )
    create_multiqc_tar_file( demux )

    demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Preparing files for delivery finished ==", color="red", attrs=["bold"] ) )
