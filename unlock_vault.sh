#!/usr/bin/env bash

# Simple wrapper to curl, so nobody will have to learn what curl or json is
#
read -s -p "Enter your Bitwarden vault password: " PW; echo

/usr/bin/curl --request POST --output /dev/null --header "Content-Type: application/json" -d "{\"password\":\"$PW\"}" http://127.0.0.1/unlock

unset PW

