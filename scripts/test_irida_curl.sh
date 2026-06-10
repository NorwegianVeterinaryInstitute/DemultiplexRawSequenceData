#!/usr/bin/env bash

BW_ITEM="irida.vigasp.vetinst.no"
IRIDA_PORT="8080"
BASE_URL="http://${BW_ITEM}:${IRIDA_PORT}/irida-23.01.3/api"
BW_URL="http://127.0.0.1:8087"

CLIENT_ID="test_client_for_file_download_webcart"
CLIENT_SECRET=$( /usr/bin/curl --silent "${BW_URL}/object/notes/${BW_ITEM}" | /usr/bin/jq -r '.data' | /usr/bin/sed 's/^token://')
USERNAME=$( /usr/bin/curl --silent "${BW_URL}/object/username/${BW_ITEM}"   | /usr/bin/jq -r '.data' )
PASSWORD=$( /usr/bin/curl --silent "${BW_URL}/object/password/${BW_ITEM}"   | /usr/bin/jq -r '.data' )

## /usr/bin/curl --silent --no-progress-meter -X POST "http://irida.vigasp.vetinst.no:8080/irida-23.01.3/api/oauth/token" -d "client_id=test_client_for_file_download_webcart&client_secret=a7Twk2LUZazMPJymGxHzY4Ebbx0l3FCA94Y09q8SdT&grant_type=password&username=gmarselis&password='okn#y7z!7&mHPU'" | /usr/bin/jq -r '.access_token'


#TOKEN=$( /usr/bin/curl --silent -X POST "${BASE_URL}/oauth/token" -d "client_id=${CLIENT_ID}&client_secret=${CLIENT_SECRET}&grant_type=password&username=${USERNAME}&password=${PASSWORD}" | /usr/bin/jq -r '.access_token' )

#echo "Token: ${TOKEN}"

#/usr/bin/curl --silent "${BASE_URL}/projects" -H "Authorization: Bearer ${TOKEN}" | /usr/bin/jq .
