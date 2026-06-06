#!/usr/bin/env python3.11
########################################################################
#
# tests/benchmark_step07.py
#
# Benchmark harness for the IRIDA upload state machine (step07).
#
# Runs deliver_files_to_VIGASP() across a matrix of
# (irida_max_in_flight, irida_upload_batch_stagger_seconds) combinations,
# records per-stage times, and produces:
#   - benchmark_step07_results.csv
#   - benchmark_step07_total_time.png
#   - benchmark_step07_verify_time.png
#
# NOTE: irida_max_in_flight is tuned to current VIGASP hardware (NREC VM).
# Optimal value will change if hardware changes or Galaxy competes for CPU.
#
# Prerequisites:
#   - VPN to NVI is up
#   - bw serve is running and vault is unlocked
#   - IRIDA is reachable at irida.vigasp.vetinst.no:8080
#   - test .fastq.gz files exist in tests/
#
# Usage:
#   /usr/bin/python3.11 tests/benchmark_step07.py
#
# https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/27
#
# Copyright: The Norwegian Veterinary Institute
# Licenced under the GNU Public License 3.0 or newer
#
########################################################################

import csv
import os
import sys
import time

import matplotlib
matplotlib.use( 'Agg' )  # no display needed
import matplotlib.pyplot as plt

sys.path.insert( 0, os.path.join( os.path.dirname( __file__ ), '..' ) )
from demux.core import demux
from tests.test_step07 import _setup, _cleanup_irida, _cleanup_local, _wait_for_irida_processing, TEST_SAMPLE_COUNT
from demux.steps.step07_deliver_files_to_VIGASP import deliver_files_to_VIGASP


########################################################################
# benchmark matrix
########################################################################

BENCHMARK_MAX_IN_FLIGHT:list  = [ 1, 2, 4, 8 ]
BENCHMARK_STAGGER_SECONDS:list = [ 0, 5, 10, 20 ]

OUTPUT_DIR:str  = os.path.dirname( os.path.abspath( __file__ ) )
CSV_PATH:str    = os.path.join( OUTPUT_DIR, 'benchmark_step07_results.csv' )
TOTAL_PNG:str   = os.path.join( OUTPUT_DIR, 'benchmark_step07_total_time.png' )
VERIFY_PNG:str  = os.path.join( OUTPUT_DIR, 'benchmark_step07_verify_time.png' )


########################################################################
# run one combination
########################################################################

def _run_one( max_in_flight: int, stagger: int ) -> dict:
    """
    Run one benchmark combination and return results.

    :returns: dict with max_in_flight, stagger, total_time, stage times, passed.
    """
    print( f"\n{'=' * 72}" )
    print( f"  max_in_flight={max_in_flight}  stagger={stagger}s" )
    print( f"{'=' * 72}" )

    demux.irida_max_in_flight               = max_in_flight
    demux.irida_upload_batch_stagger_seconds = stagger

    tmp_base:str  = ""
    passed:bool   = False
    total_time:float = 0.0

    try:
        tmp_base = _setup()
        t0:float = time.time()
        deliver_files_to_VIGASP( demux )
        total_time = round( time.time() - t0, 2 )
        passed = demux.irida_verification_passed and demux.irida_run_completed
    except Exception as error:
        print( f"  FAILED: {type( error ).__name__}: {error}" )
        total_time = round( time.time() - t0, 2 ) if 't0' in dir() else 0.0
    finally:
        _wait_for_irida_processing()
        _cleanup_irida()
        _cleanup_local( tmp_base )

    result:dict = {
        'max_in_flight':  max_in_flight,
        'stagger':        stagger,
        'passed':         passed,
        'total_time':     total_time,
        'preflight':      demux.irida_stage_times.get( 'preflight',      0.0 ),
        'check_projects': demux.irida_stage_times.get( 'check_projects', 0.0 ),
        'hash':           demux.irida_stage_times.get( 'hash',           0.0 ),
        'create_run':     demux.irida_stage_times.get( 'create_run',     0.0 ),
        'upload':         demux.irida_stage_times.get( 'upload',         0.0 ),
        'verify':         demux.irida_stage_times.get( 'verify',         0.0 ),
        'complete':       demux.irida_stage_times.get( 'complete',       0.0 ),
    }

    print( f"  passed={passed}  total={total_time}s  upload={result['upload']}s  verify={result['verify']}s" )
    return result


########################################################################
# write csv
########################################################################

def _write_csv( results: list ) -> None:
    fieldnames:list = [ 'max_in_flight', 'stagger', 'passed', 'total_time',
                        'preflight', 'check_projects', 'hash', 'create_run',
                        'upload', 'verify', 'complete' ]
    with open( CSV_PATH, 'w', newline = '' ) as fh:
        writer = csv.DictWriter( fh, fieldnames = fieldnames )
        writer.writeheader()
        writer.writerows( results )
    print( f"\nCSV written to {CSV_PATH}" )


########################################################################
# plot graphs
########################################################################

def _plot_graphs( results: list ) -> None:

    # group by stagger
    for png_path, field, title, ylabel in [
        ( TOTAL_PNG,  'total_time', 'IRIDA upload: total time vs max_in_flight', 'total time (s)' ),
        ( VERIFY_PNG, 'verify',     'IRIDA upload: verify time vs max_in_flight', 'verify time (s)' ),
    ]:
        fig, ax = plt.subplots( figsize = ( 10, 6 ) )

        for stagger in BENCHMARK_STAGGER_SECONDS:
            xs:list = []
            ys:list = []
            for r in results:
                if r[ 'stagger' ] == stagger:
                    xs.append( r[ 'max_in_flight' ] )
                    ys.append( r[ field ] if r[ 'passed' ] else None )
            ax.plot( xs, ys, marker = 'o', label = f"stagger={stagger}s" )

        ax.set_xlabel( 'irida_max_in_flight (workers)' )
        ax.set_ylabel( ylabel )
        ax.set_title( title )
        ax.legend()
        ax.grid( True )
        fig.tight_layout()
        fig.savefig( png_path, dpi = 150 )
        plt.close( fig )
        print( f"graph written to {png_path}" )


########################################################################
# main
########################################################################

def main() -> int:

    benchmark_start:float = time.time()

    total_combinations:int = len( BENCHMARK_MAX_IN_FLIGHT ) * len( BENCHMARK_STAGGER_SECONDS )
    print( "=" * 72 )
    print( "benchmark_step07: IRIDA upload state machine benchmark" )
    print( "=" * 72 )
    print( f"  combinations:   {total_combinations}" )
    print( f"  max_in_flight:  {BENCHMARK_MAX_IN_FLIGHT}" )
    print( f"  stagger values: {BENCHMARK_STAGGER_SECONDS}s" )
    print( f"  sample count:   {TEST_SAMPLE_COUNT}" )
    print( f"  estimated time: ~{total_combinations * 600 // 60} minutes" )
    print( )

    results:list = []
    for max_in_flight in BENCHMARK_MAX_IN_FLIGHT:
        for stagger in BENCHMARK_STAGGER_SECONDS:
            results.append( _run_one( max_in_flight, stagger ) )

    _write_csv( results )
    _plot_graphs( results )

    elapsed:float = time.time() - benchmark_start
    print( f"\nbenchmark complete in {elapsed:.1f}s ({elapsed / 60:.1f} minutes)" )
    return 0


if __name__ == '__main__':
    sys.exit( main() )