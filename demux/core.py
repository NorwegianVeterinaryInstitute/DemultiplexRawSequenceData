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

    ######################################################
    debug      = True
    verbosity  = 2
    state      = "demultiplexRunIDdir"                  # magic variable: sets the directory structure to hash/chmod. Set once per run, changes the first time change_permissions( ) is run
    ######################################################
    dataRootDirPath                 = '/data'
    rawDataDirName                  = 'rawdata'
    rawDataDir                      = os.path.join( dataRootDirPath, rawDataDirName )
    demultiplexDirName              = "demultiplex"
    demultiplexDir                  = os.path.join( dataRootDirPath, demultiplexDirName )
    forTransferDirName              = 'for_transfer'
    forTransferDir                  = os.path.join( dataRootDirPath, forTransferDirName )
    sampleSheetDirName              = 'samplesheets'
    sampleSheetDirPath              = os.path.join( dataRootDirPath, sampleSheetDirName )
    logDirName                      = "log"
    logDirPath                      = os.path.join( dataRootDirPath, logDirName )
    ######################################################
    commonEgid = 'sambagroup'
    ######################################################
    csvSuffix                       = '.csv'
    demultiplexDirSuffix            = '_demultiplex'
    multiqc_data                    = 'multiqc_data'
    md5Suffix                       = demux.config.constants.MD5_SUFFIX
    md5Length                       = demux.config.constants.MD5_LENGTH     # 128 bits
    qcSuffix                        = '_QC'
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
    RunID                           = ""
    runIDShort                      = ""  # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/126
    rawDataRunIDdir                 = ""
    demultiplexRunIDdir             = ""
    demultiplexLogDirPath           = ""
    demultiplexScriptLogFilePath    = ""
    demuxQCDirectoryName            = ""
    demuxQCDirectoryFullPath        = ""
    forTransferRunIDdir             = ""
    forTransferQCtarFile            = ""
    sampleSheetFilePath             = os.path.join( sampleSheetDirPath, sampleSheetFileName )
    sampleSheetArchiveFilePath      = ""
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
    forTransferDirRoot              = ""
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
    threadsToUse                    = 12                        # the amount of threads FastQC and other programs can utilize
    ######################################################
    with open( __file__ ) as f:     # little trick from openstack: read the current script and count the functions and initialize totalTasks to it
        tree = ast.parse( f.read( ) )
        totalTasks = sum( isinstance( exp, ast.FunctionDef ) for exp in tree.body ) + 2 # + 2 adjust as needed
    n = 0 # counter for keeping track of the number of the current task



    def __init__( self, RunID ):
        """
        __init__
            Check for existance of RunID
                Complain if not
            Checks to see if debug or not is set
        """
        self.RunID = RunID # variables in __init___ are unique to each instance
        self.debug = True


    ########################################################################
    # getProjectName
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

        Parsing is simple:
            go line-by-line
            ignore all the we do not need until
                we hit the line that contains 'Sample_Project'
                if 'Sample_Project' found
                    split the line and 
                        save the value of 'Sample_Project'
            return an set of the values of all values of 'Sample_Project' and 'Analysis'

        # DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'
        """

        demux.n = demux.n + 1

        demuxLogger.debug( termcolor.colored( f"==> {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} started ==\n", color="green", attrs=["bold"] ) )
        
        projectLineCheck            = False
        projectIndex                = 0
        sampleSheetContents         = [ ]
        projectList                 = [ ]
        newProjectNameList          = [ ]
        controlProjectsFoundList    = [ ]
        tarFilesToTransferList      = [ ]
        loggerName                  = 'demuxLogger'

        # https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/125
        # sampleSheetContent = ""
        # sampleSheetFileHandle = open( demux.sampleSheetFilePath, 'r', encoding = demux.decodeScheme ) # demux.decodeScheme
        # sampleSheetContent    = sampleSheetFileHandle.read( )                                         # read the contents of the SampleSheet here
        # sampleSheetContent    = check_for_illegal_characters( sampleSheetContent )
        # sampleSheetFileHandle.write(sampleSheetContent)
        # sampleSheetFileHandle.close()

        sampleSheetContent = SampleSheet( demux.sampleSheetFilePath )


        if demux.verbosity == 3:
            demuxLogger.debug( f"sampl:\n{sampleSheetContent }" ) # logging.debug it

#---------- Parse the contets of SampleSheet.csv ----------------------

        sampleSheetContents   = sampleSheetContent.split( '\n' )  # then split it in lines
        for line in sampleSheetContents:

            if demux.verbosity == 3:
                text = f"procesing line '{line}'"
                if loggerName in logging.Logger.manager.loggerDict.keys():
                    demuxLogger.debug( text )
                else:
                    print( text )

            if any( line ): # line != '' is not the same as 'not line'
                line = line.rstrip()
                if demux.verbosity == 3:
                    text = f"projectIndex: {projectIndex}" 
                    if loggerName in logging.Logger.manager.loggerDict.keys():
                        demuxLogger.debug( text )
                    else:
                        print( text )
                item = line.split(',')[projectIndex]
            else:
                continue

            if projectLineCheck == True and item not in projectList:
                if demux.verbosity == 2:
                    text = f"{'item:':{demux.spacing1}}{item}"
                    if loggerName in logging.Logger.manager.loggerDict.keys():
                        demuxLogger.debug( text )
                    else:
                        print( text )
                    
                projectList.append( item )                                 # + '.' + line.split(',')[analysis_index]) # this is the part where .x shows up. Removed.
                newProjectNameList.append( f"{demux.runIDShort}.{item}" )  #  since we are here, we might construct the new name list.

            elif demux.Sample_Project in line: ### DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'

                projectIndex     = line.split(',').index( demux.Sample_Project ) # DO NOT change Sample_Project to sampleProject. The relevant heading column in the .csv is litereally named 'Sample_Project'
                if demux.verbosity == 2:
                    text = f"{'projectIndex:':{demux.spacing1}}{projectIndex}"
                    if loggerName in logging.Logger.manager.loggerDict.keys():
                        demuxLogger.debug( text )
                    else:
                        print( text )
                projectLineCheck = True
            else:
                continue

        text = "\n"
        if loggerName in logging.Logger.manager.loggerDict.keys():
            demuxLogger.info( text )
        else:
            print( text )

#---------- Prepare a list of the projects to tar under /data/for_transfer/RunID ----------------------

        for index, project in enumerate( newProjectNameList ):
            if any( var in project for var in [ demux.testProject ] ):                # skip the test project, 'FOO-blahblah-BAR'
                continue
            elif any( var in project for var in demux.controlProjects ):                # if the project name includes a control project name, ignore it
                controlProjectsFoundList.append( project )
                continue
            elif project not in tarFilesToTransferList:
                tarFilesToTransferList.append(  os.path.join( demux.forTransferDir, demux.RunID, project + demux.tarSuffix) )

#---------- Let's make sure that demux.projectList and demux.newProjectNameList are not empty ----------------------

        if not any( projectList ):
            text = f"line {getframeinfo( currentframe( ) ).lineno} demux.projectList is empty! Exiting!"
            if loggerName in logging.Logger.manager.loggerDict.keys():
                demuxFailureLogger.critical( text  )
                demuxLogger.critical( text )
                logging.shutdown( )
            else:
                print( text )
            sys.exit( )
        elif not any( newProjectNameList ):
            text = f"line {getframeinfo( currentframe( ) ).lineno}: demux.newProjectNameList is empty! Exiting!"
            if loggerName in logging.Logger.manager.loggerDict.keys():
                demuxFailureLogger.critical( text  )
                demuxLogger.critical( text )
                logging.shutdown( )
            else:
                print( text )
            sys.exit( )
        else:
            text1 = f"projectList:"
            text1 = f"{text1:{demux.spacing2}}{projectList}"
            text2 = f"newProjectNameList:"
            text2 = f"{text2:{demux.spacing2}}{newProjectNameList}\n"
            if demux.verbosity == 3:
                demuxLogger.debug( text1 )
                demuxLogger.debug( text2 )

        demux.projectList               = projectList                        
        demux.newProjectNameList        = newProjectNameList
        demux.controlProjectsFoundList  = controlProjectsFoundList
        demux.tarFilesToTransferList    = tarFilesToTransferList

        text = termcolor.colored( f"==< {demux.n}/{demux.totalTasks} tasks: Get project name from {demux.sampleSheetFilePath} finished ==\n", color="red", attrs=["bold"] )
        if loggerName in logging.Logger.manager.loggerDict.keys():
            demuxLogger.info( text )
        else:
            print( text )




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



