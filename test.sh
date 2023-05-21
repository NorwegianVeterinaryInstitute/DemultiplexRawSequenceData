#!/bin/bash

clear
for run in $(ld -d /data/rawdata); do
    rm -rf /data/demultiplex/${run}_demultiplex
    rm -rf /data/for_transfer/${run}
    /usr/bin/python3 /data/bin/demultiplex_script.py ${1}
#    retVal=$?
#    if [ $retVal -ne 0 ]; then
#        exit $retVal
#    fi;
done
