#!/usr/bin/python3.11

import argparse
import ast
import pdb
import glob
import hashlib
import inspect
import grp
import logging
import logging.handlers
import os
import pathlib
import pprint
import re
import resource
import shutil
import socket
import stat
import string
import subprocess
import sys
import syslog
import tarfile
import termcolor

import demux.config.constants

from collections import defaultdict
from sample_sheet import SampleSheet # https://sample-sheet.readthedocs.io/quick-start.html


"""
The demux object is the central configuration/state holder for the whole pipeline.  It:
    - Defines all constants, paths, suffixes, executables, logging setup, and state variables used in the run
    - Tracks run IDs, directories, SampleSheet paths, QC directories, tar/checksum file names, and log locations
    - Is updated by functions( setupEnvironment, demultiplex, prepareDelivery, etc. ) which read/write its attributes while demultiplexing, running FastQC/MultiQC, hashing, packaging, and preparing delivery
    - 

    In short: it encapsulates the demultiplexing workflow state machine—everything from input rawdata → fastq/QC → tarballs with md5/sha512 for transfer.

Methods that mater: 
    - getProjectName( ) parses the samplesheet and gets the info needed.

"""

class demux:
    """
    demux: make an object of the entire demultiplex process.
    """

    # any variables here are *class* variables, their values do not change. 
    # values that their values change per run, go to __init__( )
    # constanths like /data/rawdata and the corresponding values are in demux/config/constants.py

    ######################################################
    # the following three need to be moved into __init__ on later date.
    ######################################################
    debug      = True
    verbosity  = 2
    state      = "demultiplexRunIDdir"  # magic variable: sets the directory structure to hash/chmod. Set once per run, changes the first time change_permissions( ) is run

    rawDataDir                      = os.path.join( demux.config.constants.DATA_ROOT_DIR, demux.config.constants.RAW_DATA_DIR_NAME     )
    demultiplexDir                  = os.path.join( demux.config.constants.DATA_ROOT_DIR, demux.config.constants.DEMULTIPLEX_DIR_NAME  )
    forTransferDir                  = os.path.join( demux.config.constants.DATA_ROOT_DIR, demux.config.constants.FOR_TRANSFER_DIR_NAME )
    sampleSheetDirPath              = os.path.join( demux.config.constants.DATA_ROOT_DIR, demux.config.constants.SAMPLESHEET_DIR_NAME  )
    logDirPath                      = os.path.join( demux.config.constants.DATA_ROOT_DIR, demux.config.constants.LOG_DIR_NAME          )
    ######################################################
    # commonEgid = 'sambagroup' # i don't know where i was going with this...
    ######################################################
    multiqc_data                    = 'multiqc_data'
    md5Suffix                       = demux.config.constants.MD5_SUFFIX
    md5Length                       = demux.config.constants.MD5_LENGTH     # 128 bits
    # qcSuffix                        = '_QC'
    sha512Suffix                    = demux.config.constants.SHA512_SUFFIX
    sha512Length                    = demux.config.constants.SHA512_LENGTH  # 512 bits
    tarSuffix                       = demux.config.constants.TAR_SUFFIX
    zipSuffix                       = demux.config.constants.ZIP_SUFFIX
    compressedFastqSuffix           = demux.config.constants.COMPRESSED_FASTQ_SUFFIX
    temp                            = 'temp'
    htmlSuffix                      = '.html'
    logSuffix                       = '.log'
    ######################################################
    executableProgramsPath          = f"/usr/local"
    bcl2fastq_bin                   = f"{executableProgramsPath}/bin/bcl2fastq"
    fastqc_bin                      = f"{executableProgramsPath}/bin/fastqc"
    mutliqc_bin                     = f"{executableProgramsPath}/bin/multiqc"
    python3_bin                     = f"/usr/bin/python3.11" # Switching over to python3.11 for speed gains
    scriptFilePath                  = __file__
    ######################################################
    rtaCompleteFile                 = 'RTAComplete.txt'
    sampleSheetFileName             = 'SampleSheet.csv'
    testProject                     = 'FOO-blahblah-BAR'
    Sample_Project                  = 'Sample_Project'
    demultiplexCompleteFile         = 'DemultiplexComplete.txt'
    vannControlNegativReport        = 'Negativ'
    forTransferRunIdDirTestName     = 'test_tar'
    md5File                         = 'md5sum.txt'
    miSeq                           = ['M06578', 'M09180']  # array of serial numbers for miseq. Change to read from config, or read from illumina
    nextSeq                         = ['NB552450']          # array of serial numbers for nextseq. Change to read from config, or read from illumina
    decodeScheme                    = "utf-8"
    footarfile                      = f"foo{demux.config.constants.TAR_SUFFIX}"      # class variable shared by all instances
    barzipfile                      = f"zip{demux.config.constants.ZIP_SUFFIX}"
    totalTasks                      = 0
    tabSpace                        = 8
    spacing1                        = 40
    spacing2                        = spacing1 + tabSpace
    spacing3                        = spacing2 + tabSpace
    spacing4                        = spacing3 + tabSpace
    spacing5                        = spacing4 + tabSpace
    spacing6                        = spacing5 + tabSpace
    spacing6                        = spacing6 + tabSpace

    ######################################################
    # All following are supposed to be filled in at run time
    RunID                           = ""
    runIDShort                      = ""                                                            # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/126
    rawDataRunIDdir                 = ""
    demultiplexRunIDdir             = ""
    demultiplexLogDirPath           = ""
    demultiplexScriptLogFilePath    = ""
    demuxQCDirectoryName            = ""
    demuxQCDirectoryFullPath        = ""
    forTransferRunIDdir             = ""
    forTransferQCtarFile            = ""
    multiqc_run_dir                 = ""
    sampleSheetFilePath             = os.path.join( sampleSheetDirPath, sampleSheetFileName )
    sampleSheetArchiveFilePath      = ""                                                            # demux/envsetup/setup_environment.py
    project_samples_metadata        = defaultdict( dict ) # hold an association of Sample_Project -> Sample_ID { Transfer_VIGAS, VIGASP_ID, Transfer_NIRD, NIRD_Location }
    ######################################################
    projectList                     = [ ]
    newProjectNameList              = [ ]
    newProjectFileList              = [ ]
    controlProjectsFoundList        = [ ]
    tarFilesToTransferList          = [ ]
    globalDictionary                = dict( )
    ######################################################
    controlProjects                 = [ "Negativ" ]
    ######################################################
    forTransferRunIdDir             = ""
    forTransferQCtarFile            = ""
    absoluteFilesToTransferList     = { }
    ######################################################
    demuxCumulativeLogFileName      = 'demultiplex.log'
    demultiplexLogDirName           = 'demultiplex_log'
    scriptRunLogFileName            = '00_script.log'
    bcl2FastqLogFileName            = '01_demultiplex.log'
    fastqcLogFileName               = '02_fastqcLogFile.log'
    multiqcLogFileName              = '03_multiqcLogFile.log'
    loggingLevel                    = logging.DEBUG
    ######################################################
    demuxCumulativeLogFilePath      = ""
    bcl2FastqLogFile                = ""
    fastQCLogFilePath               = ""
    logFilePath                     = ""
    multiQCLogFilePath              = ""
    scriptRunLogFile                = ""
    ######################################################
    # mailhost                        = 'seqtech00.vetinst.no'
    mailhost                        = 'localhost'
    fromAddress                     = f"demultiplex@{ socket.getfqdn( ) }"
    toAddress                       = 'gmarselis@localhost'
    subjectFailure                  = 'Demultiplexing has failed'
    subjectSuccess                  = 'Demultiplexing has finished successfuly'
    ######################################################
    httpsHandlerHost                = 'veterinaerinstituttet307.workplace.com'
    httpsHandlerUrl                 = 'https://veterinaerinstituttet307.workplace.com/chat/t/4997584600311554'
    ######################################################
    transfer_to_nird                = bool( )               # determine if trasfers should happen to nird
    nird_access_mode                = "mounted"
    allowed_nird_access_modes       = [ "ssh", "mounted" ]
    nird_copy_mode                  = "parallel"
    allowed_nird_copy_modes         = [ "serial", "parallel" ]
    # nird_upload_host                = "login.nird.sigma2.no"
    nird_upload_host                = "laptop"
    nird_scp_port                   = "22" # https://documentation.sigma2.no/getting_help/two_factor_authentication.html#how-to-copy-files-without-using-2fa-otp
    nird_username                   = "gmarselis" # change this to be the user running the script
    nird_base_upload_path_ssh       = "/nird/projects/NS9305K/SEQ-TECH/data_delivery"
    nird_base_upload_path_local     = "/data/tmp/nird"
    nird_base_upload_path           = ""
    nird_key_filename               = "/home/gmarselis/.ssh/id_ed25519.3jane"
    hostname                        = ""
    username                        = ""
    key_file                        = ""
    port                            = int( )
    ######################################################
    transfer_to_vigas               = bool( )               # determine if trasfers should happen to nird
    vigasp_api_key                  = ""    # we need to see how we can limit the damage including this api key can have
    vigasp_copy_mode                = "serial"
    allowed_vigasp_copy_modes       = [ "serial", "parallel" ]
    ######################################################
    threadsToUse                    = 12                        # the amount of threads FastQC and other programs can utilize
    ######################################################
    with open( __file__ ) as f:     # little trick from openstack: read the current script and count the functions and initialize totalTasks to it
        tree = ast.parse( f.read( ) )
        totalTasks = sum( isinstance( exp, ast.FunctionDef ) for exp in tree.body ) + 2 # + 2 adjust as needed
    n = 0 # counter for keeping track of the number of the current task



    def __init__( self, RunID ):
        """
        __init__
            Check for existence of RunID
                Complain if not
            Checks to see if debug or not is set
        """
        self.RunID = RunID # variables in __init___ are unique to each instance
        # # self.RunID = discover_new_runs( )  # this is for later # apparently this si a bad idea

    def _get_unique_sample_projects( sample_sheet ):
        """
        Returns the list of sample project names from the sample sheet, preserving their original order and removing duplicates.
        """
        return list( dict.fromkeys( sample_obj.Sample_Project for sample_obj in sample_sheet.samples ) )

    def _create_renamed_demux_project_list( projectList ):
        """
        Returns the list of project names with test and control projects removed and all remaining projects renamed using runIDShort.
        """
        newProjectNameList = [ ]

        for project in projectList:
            if any( var in project for var in [ demux.testProject ] ):                 # skip the test project, 'FOO-blahblah-BAR'
                continue
            elif any( var in project for var in demux.controlProjects ):                # if the project name includes a control project name, ignore it
                controlProjectsFoundList.append( project )
                continue
            elif project not in newProjectNameList:
                newProjectNameList.append( f"{demux.runIDShort}.{project}" )  #  since we are here, we might construct the new name list.

        return newProjectNameList

    def _create_tar_files_to_transfer_list( newProjectNameList ):
        """
        Builds and returns the list of absolute tar file paths to transfer, skipping test and control projects and appending the tar suffix for each remaining project.
        """
        tarFilesToTransferList = [ ]

        for index, project in enumerate( newProjectNameList ):
            if any( var in project for var in [ demux.testProject ] ):                 # skip the test project, 'FOO-blahblah-BAR'
                continue
            elif any( var in project for var in demux.controlProjects ):                # if the project name includes a control project name, ignore it
                controlProjectsFoundList.append( project )
                continue
            elif project not in tarFilesToTransferList:
                tarFilesToTransferList.append(  os.path.join( demux.forTransferDir, demux.RunID, project + demux.tarSuffix) )

        return tarFilesToTransferList

    def _build_project_sample_metadata( sample_sheet: SampleSheet) -> dict[str, dict[str, dict]]:
        """
        Build a nested mapping from Sample_Project to Sample_ID and all transfer-related metadata fields.
        """
        project_samples_metadata = defaultdict( dict ) # hold an association of Sample_Project -> Sample_ID { Transfer_VIGAS, VIGASP_ID, Transfer_NIRD, NIRD_Location }

        for sample in sample_sheet.samples:
            project_samples_metadata[ sample.Sample_Project ][ sample.Sample_ID ] = {
                "transfer_to_vigas": sample.Transfer_VIGAS.lower( ) == "yes",
                "vigas_project_id": int( sample.VIGASP_ID ),
                "transfer_to_nird": sample.Transfer_NIRD.lower( ) == "yes",
                "nird_location": sample.NIRD_Location,
            }

        return project_samples_metadata


    ########################################################################
    # parse_sample_sheet
    ########################################################################
    def parse_sample_sheet( ):
        """
        Parse the NVI SampleSheet.csv into an object and get the associated project name(s)

        Requires:
           /data/rawdata/RunID/SampleSheet.csv

        Returns:
            Samplesheet object
            List of included Sample Projects. 
                Example of returned projectList:     {'SAV-amplicon-MJH'}

        Parsing is done by the sample_sheet library
        """

        demux.n = demux.n + 1

        # loggerName                  = 'demuxLogger' # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/125
        # demuxLogger.debug( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} started ==\n", color="green", attrs=["bold"] ) )
        # use print for now till we figure out what is going on with the logging
        print( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} started ==\n", color="green", attrs=["bold"] ) )

        sample_sheet                    = SampleSheet( demux.sampleSheetFilePath )
        demux.projectList               = demux._get_unique_sample_projects( sample_sheet )    # get the project list
        demux.newProjectNameList        = demux._create_renamed_demux_project_list( demux.projectList ) # translate the project list to absolute names
        demux.tarFilesToTransferList    = demux._create_tar_files_to_transfer_list( demux.newProjectNameList ) # does not create the absolute path.
        demux.project_samples_metadata  = demux._build_project_sample_metadata( sample_sheet ) # hold an association of Sample_Project -> Sample_ID { Transfer_VIGAS, VIGASP_ID, Transfer_NIRD, NIRD_Location }


        for project, tar_file in zip( demux.projectList, demux.tarFilesToTransferList ):
            # take the project-level value directly from the first sample in that project
            first_sample = next( iter( demux.project_samples_metadata[ project ].values( ) ) )
            demux.absoluteFilesToTransferList[ tar_file ]  = {
                'transfer_to_nird': first_sample[ 'transfer_to_nird' ]
            }

        demux.transfer_to_vigas     = all( entry[ 'transfer_to_vigas' ] for entry in demux.project_samples_metadata[ project ].values( ) ) # all( ) logical ANDs the values
        demux.transfer_to_nird      = all( entry[ 'transfer_to_nird' ]  for entry in demux.project_samples_metadata[ project ].values( ) )

        # if we are debugging, print out the list of projects.
        if demux.verbosity == 3:
            pprint( "projectList: ", demux.projectList, width = 120 )

        print( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} finished ==\n", color="red", attrs=["bold"] ) )


    ########################################################################
    # listTarFiles( )
    ########################################################################
    def listTarFiles ( listOfTarFilesToCheck ):
        """
        Check to see if the tar files created for delivery can be listed with no errors
        use
            TarFile.list(verbose=True, *, members=None)
                    Print a table of contents to sys.stdout. If verbose is False, only the names of the members are logging.infoed. If it is True, output similar to that of ls -l is produced. If optional members is given, it must be a subset of the list returned by getmembers(). 

            https://docs.python.org/3/library/tarfile.html

        But do it quietly, no need for output other than an OK/FAIL
        """

        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Verify that the tar files produced are actually untarrable started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Verify that the tar files produced are actually untarrable finished ==\n", color="red", attrs=["bold"] ) )



    ########################################################################
    # hasBeenDemultiplexed( )
    ########################################################################
    def hasBeenDemultiplexed( RunID ):
        """
        Check if run has been demultiplexed before

        Steps:
            Check if SampleSheet has been changed
                point out which fields have been changed
                    write to log

        Returs
            *True* if RudID_demultiplex exists
        """
        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed finished ==\n", color="red", attrs=["bold"] ) )



    ########################################################################
    # reDemultiplex( )
    ########################################################################
    def reDemultiplex( RunID ):
        """
        setup nessecary paths:
            RunID_demupltiplex-ISODATETIME
        Copy modified samplesheet to /data/SampleSheets as RunID-ISODATETIME.csv
        Demultiplex RunID again
        """
        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: See if the specific RunID has already been demultiplexed finished ==\n", color="red", attrs=["bold"] ) )



    ########################################################################
    # checkSampleSheetForMistakes( )
    ########################################################################
    def checkSampleSheetForMistakes( RunID ):
        """
        Check SampleSheet.csv for common human mistakes

        common errors of SampleSheets
            1.       Space in sample name or project name. Especially hard to grasp if they occur at the end of the name. I replace the spaces with a “-“ if in middle of name. I erase the space if it is at the end.
            2.       Non-UTF8 Æ, Ø or Å in sample name or project names.
            3.       Extra lines in SampleSheet with no sample info in them. Will appear as a bunch of commas for each line which is empty. They need to be deleted or demuxing fails.
            4.       Forget to put ekstra column called “Analysis” and set an “x” in that column for all samples (I don’t know if we will keep this feature for the future)
            5.       . in sample names

        point any mistakes out to log
        """
        demux.n = demux.n + 1
        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Checking SampleSheet.csv for common human mistakes started ==\n", color="green", attrs=["bold"] ) )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Checking SampleSheet.csv for common human mistakes finished ==\n", color="red", attrs=["bold"] ) )

    ########################################################################
    # check_for_illegal_characters( )
    ########################################################################
    def check_for_illegal_characters( sampleSheetContent ): # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/125
        """
        Find and remove characters within the samplesheet that might cause us headaches
        """

        demuxLogger.info( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Checking SampleSheet.csv for characters that might cause us headaches started ==\n", color="green", attrs=["bold"] ) )

        ##########################################################################
        # check for non ASCII characters. if they exist, report them, then delete them
        #
        # if re.search(r'[^A-Za-z0-9_\-\n\r]', sampleSheetContent):
        #     invalidChars = [(m.group(), m.start()) for m in re.finditer(r'[^A-Za-z0-9_\-\n\r]', sampleSheetContent)]


        #     for char, position in invalidChars:
        #         lineNumber = sampleSheetContent.count( '\n', 0, position ) + 1
        #         columnNumber = position - sampleSheetContent.rfind( '\n', 0, position )
        #         print( f"Invalid character '{char}' at line {lineNumber}, column {columnNumber}" )

            # replace it according to rules below
            #
            # if char found is not in the rules, notify user

            # When you edit files in CSV format, some software saves the values surrounded by quotes
            # and some do not. So, precautionary strip single and double quotes
            #


            ##########################################################################
            # The following lists are designed to ensure compatibility with ASCII
            # as required by Illumina's bcl2fastq, eliminating character sets which
            # may be used by personnel in the lab handling the SampleSheet but are not
            # compatible with bcl2fastq.
            #
            # norwegianDanishCharactersPattern = r'[ÅÆØåæø]'
            # swedishFinnishCharactersPattern = r'[ÄÖäö]'
            # icelandicCharactersPattern = r'[ÁÐÍÓÚÝÞÖáðíóúýþ]'
            # # Ñ and ñ are Spanish-specific characters, everything else brazilianPortugueseCharactersPattern covers
            # spanishCharacterspattern = r'[Ññ]'
            # # Œ, œ, and ÿ are French-specific characters, everything else brazilianPortugueseCharactersPattern covers
            # frenchCharactersPattern = r'[Œœÿ]'
            # # Â,À,Ç are baptized as Brazilian Portugese cuz we got more Portugese speakers in the building
            # brazilianPortugueseCharactersPattern = r'[ÂÃÁÀÊÉÍÓÔÕÚÇâãáàêéíóôõúç]'
            # otherCharactersPattern = r'[\'\"=]'
            # currencyCharactersPattern = r'[€]'

            # # Catch Chinese, Japanese, and Korean (CJK) characters,
            # cjkPattern = r'[\u4E00-\u9FFF\u3040-\u30FF\uFF66-\uFF9F\u3400-\u4DBF]'
            #     # \u4E00-\u9FFF: Common and Unified CJK characters (Chinese, Japanese Kanji, Korean Hanja).
            #     # \u3040-\u30FF: Japanese Hiragana and Katakana.
            #     # \uFF66-\uFF9F: Half-width Katakana.
            #     # \u3400-\u4DBF: CJK Extension A (additional Chinese characters)
            # vietnameseCharactersPattern = r'[ÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚĂĐĨŨƠàáâãèéêìíòóôõùúăđĩũơƯưẠẢẤẦẨẪẬẮẰẲẴẶẸẺẼỀỀỂễỆỈỊỌỎỐỒỔỖỘỚỜỞỠỢỤỦỨỪỬỮỰ]'


            ##########################################################################
            # Classes of characters frequently found in SampleSheet

            # Leftover single and double quotes
            # line = line.replace( '\'', '' )
            # line = line.replace( "\"", '' )

            # # Norwegian characters
            # line = line.replace('Â', 'A')
            # line = line.replace('Å', 'A')
            # line = line.replace('Æ', 'AE')
            # line = line.replace('Ø', 'O')
            # line = line.replace('â', 'a')
            # line = line.replace('å', 'a')
            # line = line.replace('æ', 'ae')
            # line = line.replace('ø', 'o')

            # # Spanish accented characters
            # line = line.replace('Ã', 'A')
            # line = line.replace('ã', 'a')

            # # Euro currency sign
            # line = line.replace('€', ' ')

            # sys.exit( "what happens when multiples of the above exist, read up on line.replace()")
            # # remove any &nbsp
            # line = line.replace('\u00A0', ' ')

            # ###########################################################################
            # # WARN USER THAT SUCH CHARS WERE ENCOUNTERED
            # ###########################################################################
            # sys.exit( "working on: WARN USER THAT SUCH CHARS WERE ENCOUNTERED. Use this token to search for this sys.exit()" )

        demuxLogger.info( termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Checking SampleSheet.csv for characters that might cause us headaches finished ==\n", color="red", attrs=["bold"] ) )

        return sampleSheetContent



