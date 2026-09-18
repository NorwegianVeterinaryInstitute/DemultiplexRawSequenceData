#!/usr/bin/env -S -- /usr/bin/python3.11
#
# delete_test_pairs.py - delete IRIDA sequence file pairs by forward file name prefix.
#
# Sweeps every sample in the given IRIDA projects and deletes every pair whose
# forward file name starts with the given prefix. Cleanup for the demux test runs:
# the fake run ID prefix (999999_M09180) marks the pairs.
#
# Environment: IRIDA_TOKEN and IRIDA_BASE_URL, the same two the bash tools use.
# Dry run by default; --delete actually deletes.
#
# DELETE path: /api/samples/{sampleId}/pairs/{pairId}. The documented
# /api/samples/{id}/sequenceFiles/{fileId} is wrong (see delete_irida_sequence_file).
#
# usage: delete_test_pairs.py 999999_M09180 10 12 17 21 44 75 115 [--delete]
#
# Copyright (C) 2026  George Marselis <george.marselis@vetinst.no>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import argparse
import os
import sys
import time

import requests

TIMEOUT: int = 60
STAGGER: int = 5                                                              # seconds between DELETEs; IRIDA does not like bursts
SPINNER: str = "|/-\\"


def _get( session: requests.Session, base_url: str, path: str ) -> dict:
    response: requests.Response = session.get( f"{base_url}/api/{path}", timeout = TIMEOUT )
    response.raise_for_status( )
    return response.json( )


def _resources( payload: dict ) -> list[ dict ]:
    return payload[ "resource" ][ "resources" ]


def main( ) -> int:
    parser = argparse.ArgumentParser( description = "Delete IRIDA sequence file pairs by forward file name prefix." )
    parser.add_argument( "prefix",    help = "forward file name prefix to match, e.g. 999999_M09180" )
    parser.add_argument( "projects",  nargs = "+", type = int, help = "IRIDA project IDs to sweep" )
    parser.add_argument( "--delete",  action = "store_true", help = "actually delete; default is a dry run" )
    args = parser.parse_args( )

    token:    str | None = os.environ.get( "IRIDA_TOKEN" )
    base_url: str | None = os.environ.get( "IRIDA_BASE_URL" )
    if not token:
        print( "IRIDA_TOKEN must be set", file = sys.stderr )
        return 2
    if not base_url:
        print( "IRIDA_BASE_URL must be set", file = sys.stderr )
        return 2
    base_url = base_url.rstrip( "/" )

    session: requests.Session = requests.Session( )
    session.headers[ "Authorization" ] = f"Bearer {token}"
    session.headers[ "Accept" ]        = "application/json"

    # phase 1: collect, so the operator sees the count before anything is touched
    matches: list[ tuple[ int, str, str, str, str ] ] = [ ]                   # project, sample_id, sample_name, pair_id, filename
    for project in args.projects:
        for sample in _resources( _get( session, base_url, f"projects/{project}/samples" ) ):
            sample_id: str = sample[ "identifier" ]
            for pair in _resources( _get( session, base_url, f"samples/{sample_id}/pairs" ) ):
                pair_id:  str  = pair[ "identifier" ]
                detail:   dict = _get( session, base_url, f"samples/{sample_id}/pairs/{pair_id}" )
                filename: str  = detail[ "resource" ][ "forwardSequenceFile" ][ "fileName" ]
                if filename.startswith( args.prefix ):
                    matches.append( ( project, sample_id, sample[ "sampleName" ], pair_id, filename ) )

    for project, sample_id, sample_name, pair_id, filename in matches:
        print( f"project {project} sample {sample_id} ({sample_name}) pair {pair_id} {filename}" )
    print( f"found {len( matches )} pairs with prefix {args.prefix}" )

    if not args.delete:
        print( "dry run, pass --delete to remove them" )
        return 0

    # phase 2: delete, one every STAGGER seconds, spinner on stderr
    deleted: int = 0
    for index, ( project, sample_id, sample_name, pair_id, filename ) in enumerate( matches ):
        print( f"\r{SPINNER[ index % len( SPINNER ) ]} deleting {index + 1}/{len( matches )}", end = "", file = sys.stderr, flush = True )
        response: requests.Response = session.delete( f"{base_url}/api/samples/{sample_id}/pairs/{pair_id}", timeout = TIMEOUT )
        if response.status_code == 200:
            deleted += 1
        else:
            print( f"\nDELETE failed for sample {sample_id} pair {pair_id}: HTTP {response.status_code} {response.text[ :200 ]}", file = sys.stderr )
        if index + 1 < len( matches ):
            time.sleep( STAGGER )
    print( file = sys.stderr )

    print( f"deleted {deleted} of {len( matches )}" )
    return 0 if deleted == len( matches ) else 1


if __name__ == "__main__":
    sys.exit( main( ) )