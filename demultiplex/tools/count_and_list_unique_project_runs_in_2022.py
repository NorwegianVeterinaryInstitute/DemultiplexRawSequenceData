#!/usr/bin/env python3

import os
import sys 
import shutil
import subprocess
import argparse
from pathlib import Path

# print out the Sample_Projects used this year

# How to use
# BASH: for file in $( ls -d $PWD/22*/*.csv | grep -v _ori ); do $PWD/count_and_list_unique_project_runs_in_2022.py $file ; done | sort | uniq

def getProjectName( SampleSheetFilePath ):
    """
    Print the associated Sample_Project from SampleSheet.csv

    Requires:
       /data/rawdata/RunId/SampleSheet.csv 

    Example of returned output_list:     {'SAV-amplicon-MJH'}

    Parsing is simple:
        go line-by-line
        ignore all the we do not need until
            we hit the line that contains 'Sample_Project'
            if 'Sample_Project' found
                split the line and
                    take the value of 'Sample_Project'
        return an set of the values of all values of 'Sample_Project' and 'Analysis'
    """

    project_line_check = False
    project_index  = ''
    project_list   = set( )

    for line in open( SampleSheetFilePath, 'r', encoding="utf-8" ):
        line = line.rstrip()
        if project_line_check == True:
            project_list.add(line.split(',')[project_index] ) # do not worry about duplicates, set nulls them
        if 'Sample_Project' in line:
            project_index      = line.split(',').index('Sample_Project')
            project_line_check = True

    for value in project_list:
        print( f"{value}" )

if __name__ == '__main__':

    # FIXMEFIXME add named arguments
    getProjectName( sys.argv[1] )

