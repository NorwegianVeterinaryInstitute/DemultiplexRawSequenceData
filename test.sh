#!/bin/bash

clear
for run in $( < /data/rawdata/testruns ); do
    rm -rf /data/demultiplex/${run}_demultiplex
    rm -rf /data/for_transfer/${run}
    /usr/bin/python3 /data/bin/demultiplex_script.py $( /usr/bin/basename ${run} )
#    retVal=$?
#    if [ $retVal -ne 0 ]; then
#        exit $retVal
#    fi;
done
