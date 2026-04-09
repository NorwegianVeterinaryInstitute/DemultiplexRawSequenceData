"""
arguments.py: argument parsing for the demultiplex script.
Parses and validates command line arguments passed to demultiplex.py.
Accepts a RunID either as a bare string or prefixed with an absolute directory path.

NOTE: Keep this docstring in sync with the argument definitions below when making changes.

Default behavior:
    demultiplex.py                  Scan rawdata directory and process all pending runs.
    demultiplex.py <RunID>          Alias for: demultiplex.py run <RunID>
    demultiplex.py run <RunID>      Explicit form.

    A RunID is the Illumina-format run identifier, e.g. 230415_M01234_1234_000000000-ABCDE,
    composed of: date (YYMMDD), instrument serial ID, run number and flowcell ID.
    It may be provided as a bare string or prefixed with its absolute directory path,
    e.g. /data/rawdata/230415_M01234_1234_000000000-ABCDE.

Subcommands and their arguments:

    run <RunID> [RunID ...]
        Run the full demultiplex pipeline for one or more runs.

        Skip flags:
            --skip-bcl2fastq    Skip bcl2fastq demultiplexing.
            --skip-fastqc       Skip FastQC quality check.
            --skip-multiqc      Skip MultiQC report generation.
            --skip-vigasp       Skip delivery to VIGASP.
            --skip-nird         Skip delivery to NIRD.
            --skip-checksum     Skip hash calculation steps.
            --skip-qc-tarball   Skip creating the QC tarball.

        Run control:
            --force             Bypass existing directory guard. Operator use only.
            --dry-run           Print what would be executed without running anything.
                                Not yet fully implemented.
            -v, --verbose       Increase verbosity. Use -v, -vv or -vvv.

        Targeted step (mutually exclusive with each other;
                        --only-vigasp exclusive with --skip-vigasp,
                        --only-nird exclusive with --skip-nird):
            --only-vigasp       Run delivery to VIGASP only, assuming all prior steps are complete.
            --only-nird         Run delivery to NIRD only, assuming all prior steps are complete.

        Run notes:
            --note <file>       Attach a note to this run, read from <file>.
            --note -            Attach a note to this run, read from stdin.
                                Supports shell redirection: demultiplex.py run <RunID> --note - < note.txt
                                If omitted, preflight will warn: "no note attached for this run."
                                Notes may also be attached after the run completes.

    validate <RunID> [RunID ...]
        Validate a run without executing the pipeline.

        What to validate (mutually exclusive, default: --samplesheet):
            --samplesheet       Validate the samplesheet (default).
            --hashes            Validate file hashes.

        --verbose               Increase verbosity.

    clean <RunID> [RunID ...]
        Remove intermediate files for a run, keeping final deliverables.

        What to clean:
            --bcl2fastq         Remove bcl2fastq intermediate files.
            --fastqc            Remove FastQC intermediate files.
            --multiqc           Remove MultiQC intermediate files.
            --uploads           Remove for_transfer directory contents for this run.
                                WARNING: do not use before confirming delivery to NIRD and VIGASP.

    delete <RunID> [RunID ...]
        Remove a demultiplexed run and all its artifacts.
        WARNING: never touches rawdata.

    rename-run <RunID> <NewRunID>
        Rename a run directory, tar files and samplesheet copy. Requires root.
        WARNING: destructive operation. Updates RunID in the samplesheet.

    rename-sample <RunID> <Sample> <NewSample>
        Rename a sample within a run. Requires root.
        WARNING: destructive operation. Updates SampleID in the samplesheet.
        <NewSample> must be a valid sample name from ShinyLIMS.

    export-rawdata <RunID> --destination|--ssh|--url <target> [<RunID> --destination|--ssh|--url <target> ...]
        Tar the raw BCL data directory for one or more runs and optionally transfer it.
        This operates on raw sequencer output, not the demultiplexed delivery tars.
        At least one RunID with a destination is required.

        Per-RunID destination (one required per RunID):
            --destination <PATH>        Write tar file to local PATH.
            --ssh <user@host:path>      Transfer tar via SSH. Requires working SSH connectivity,
                                        key-based authentication and SSH client configuration
                                        (~/.ssh/config). Connectivity and configuration are the
                                        caller's responsibility.
            --url <URL>                 Transfer tar via HTTP PUT.

        Transfer control:
            --keep                      Keep the local tar file after transfer (default: remove on success).

    archive <RunID> [RunID ...]
        Move raw data for a run into an archive directory.

        Destination (mutually exclusive, one required):
            --local <PATH>      Archive to a local directory.
            --nird              Archive to NIRD.

        Not yet implemented.

    tag <RunID> [RunID ...]
        Tag a run with metadata. Written to the database when available.

            --badrun            Mark as a bad run (bad data, failed flowcell, machine error).
            --control           Mark as a control run (water-only flowcell for QC purposes).

        Not yet implemented.

    list
        List all known runs.

        Filters (mutually exclusive):
            --failed            Show only failed runs.
            --pending           Show only pending runs.
            --completed         Show only completed runs.

    status <RunID> [RunID ...]
        Show the processing state of a run.

    stats [RunID]
    statistics [RunID]
        Show pipeline and QC statistics. If RunID is omitted, shows aggregate across all runs.

        Filters:
            --from <YYYY-MM-DD>     Show runs from this date onwards (start of day 00:00:00).
            --to   <YYYY-MM-DD>     Show runs up to and including this date (end of day 23:59:59).
            --instrument <SERIALID> Filter to a specific instrument by serial ID.
            --last <N>              Limit to the last N runs.

        QC (only valid when RunID is provided):
            --qc                Display FastQC summary verdicts (PASS/WARN/FAIL per module).
            --qc-plots          Render FastQC plots in the terminal if a terminal is detected,
                                otherwise push to Teams or save to disk.
            --undetermined      Show undetermined index rates per run.
                                High rates indicate samplesheet problems.

        Output (CLI only; web and Teams display uses FastQC/MultiQC HTML files directly):
            --format <fmt>      Output format: table (default), json, csv.

    notify <RunID> [RunID ...]
        Manually trigger the Teams QC notification for a run without waiting for the scheduled time.
        Not yet implemented.

    approve <RunID> [RunID ...]
        Manually approve a run from the CLI rather than via Teams.
        Not yet implemented.

    reject <RunID> [RunID ...]
        Manually reject a run from the CLI rather than via Teams.

            --reason <TEXT>     Optional reason for rejection. Logged and included in the
                                Teams notification.

        Not yet implemented.

    daemon <action>
        Control the demultiplex daemon.

        Actions:
            start               Start the daemon.
            stop                Wait for any current runs to finish, then stop cleanly.
            stop --force        Stop immediately. Abandons current runs and cleans up
                                partial output before exiting. Operator use only.
            status              Show daemon status.

        Not yet implemented.

Global flags (valid for all subcommands):
    -V, --version               Show version and exit.
    --config <PATH>             Path to an alternate config file.
"""
import argparse
import os
import sys
import demux.config.constants as constants
from demux.loggers import demuxLogger, demuxFailureLogger


class _VerboseHelpFormatter(argparse.RawDescriptionHelpFormatter):
    """
    Custom help formatter that preserves description formatting and
    shows argument defaults where available.
    """
    def _get_help_string(self, action):
        help_text = action.help
        if action.default is not None and action.default is not argparse.SUPPRESS:
            if '%(default)' not in (help_text or ''):
                if action.default is not False:                     # skip store_true flags with default=False
                    help_text = f"{help_text} (default: {action.default})"
        return help_text


def _preprocess_argv() -> None:
    """
    Preprocess sys.argv before the parser sees it.

    If the first non-flag argument looks like an Illumina RunID or a path
    containing one, insert 'run' before it so argparse sees a valid subcommand
    invocation. This enables the shorthand:

        demultiplex.py <RunID>              -> demultiplex.py run <RunID>
        demultiplex.py /path/to/<RunID>     -> demultiplex.py run /path/to/<RunID>
        demultiplex.py /path/to/<RunID>/    -> demultiplex.py run /path/to/<RunID>/

    Does nothing if:
        - sys.argv has no arguments (scan mode, handled downstream)
        - the first argument starts with '-' (it is a flag, not a RunID)
        - the first argument is already a known subcommand
    """
    known_subcommands = {
        'run', 'validate', 'clean', 'delete', 'rename-run', 'rename-sample',
        'export-rawdata', 'archive', 'tag', 'list', 'status', 'statistics',
        'stats', 'notify', 'approve', 'reject', 'daemon',
    }

    if len(sys.argv) < 2:
        return                                                          # no arguments: scan mode

    first = sys.argv[1]

    if first.startswith('-'):
        return                                                          # first arg is a flag, not a RunID

    if first in known_subcommands:
        return                                                          # already a valid subcommand

    candidate = os.path.basename(first.strip('/,.'))
    if constants.RUNID_PATTERN.match(candidate):
        sys.argv.insert(1, 'run')                                       # rewrite argv in place before argparse sees it


def parse_runid(value: str) -> str:
    """
    Parse a RunID from a string, stripping leading and trailing slashes,
    path components and trailing punctuation.
    Accepts formats:
        RunID
        RunID/
        /foo/bar/RunID
        /foo/bar/RunID/
    Returns the bare RunID string.
    Raises argparse.ArgumentTypeError if value is empty or does not match
    the expected Illumina RunID pattern.
    """
    if not value or not value.strip():
        raise argparse.ArgumentTypeError("RunID must not be empty.")
    RunID = os.path.basename(value.strip('/,.'))
    if not constants.RUNID_PATTERN.match(RunID):
        raise argparse.ArgumentTypeError(f"'{RunID}' does not look like a valid Illumina RunID. Aborting.")
    return RunID


def _add_runid_argument(parser: argparse.ArgumentParser) -> None:
    """
    Add the RunID positional argument to a subcommand parser.
    """
    parser.add_argument(
        'RunID',
        type=parse_runid,
        nargs='*',
        help=(
            'Illumina RunID, e.g. 230415_M01234_1234_000000000-ABCDE. '
            'Optionally prefixed with its absolute directory path.'
        )
    )


def _add_verbose_argument(parser: argparse.ArgumentParser) -> None:
    """
    Add the -v/--verbose flag to a subcommand parser.
    Only valid for subcommands that involve active execution or validation.
    """
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='Increase verbosity. Use -v, -vv or -vvv.'
    )


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add all flags valid under the `run` subcommand.
    """
    skip = parser.add_argument_group("  Skip flags")
    skip.add_argument("--skip-bcl2fastq", action="store_true", help="Skip bcl2fastq demultiplexing.")
    skip.add_argument("--skip-fastqc",    action="store_true", help="Skip FastQC quality check.")
    skip.add_argument("--skip-multiqc",   action="store_true", help="Skip MultiQC report generation.")
    skip.add_argument("--skip-vigasp",    action="store_true", help="Skip delivery to VIGASP.")
    skip.add_argument("--skip-nird",      action="store_true", help="Skip delivery to NIRD.")
    skip.add_argument("--skip-checksum",  action="store_true", help="Skip hash calculation steps.")
    skip.add_argument("--skip-qatarball", action="store_true", help="Skip hash calculation steps.")

    control = parser.add_argument_group("  Run control")
    control.add_argument("--force",   action="store_true", help="Bypass existing directory guard. Operator use only.")
    control.add_argument("--dry-run", action="store_true", help="Print what would be executed without running anything. Not yet fully implemented.")

    only = parser.add_argument_group("  Targeted step")
    group = only.add_mutually_exclusive_group()
    group.add_argument("--only-vigasp", action="store_true", help="Run delivery to VIGASP only, assuming all prior steps are complete.")
    group.add_argument("--only-nird",   action="store_true", help="Run delivery to NIRD only, assuming all prior steps are complete.")

    notes = parser.add_argument_group("  Run notes")
    notes.add_argument(
        "--note",
        type=str,
        metavar='file',
        default=None,
        help=(
            "Attach a note to this run. "
            "Provide a file path to read from, or '-' to read from stdin "
            "(supports shell redirection: demultiplex.py run <RunID> --note - < note.txt). "
            "If omitted, preflight will warn: 'no note attached for this run.' "
            "Notes may also be attached after the run completes."
        )
    )

    verbosity = parser.add_argument_group("  Verbosity")
    _add_verbose_argument(verbosity)


def _add_validate_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add flags for the `validate` subcommand.
    """
    what = parser.add_argument_group("  What to validate")
    group = what.add_mutually_exclusive_group()
    group.add_argument("--samplesheet", action="store_true", help="Validate the samplesheet (default).")
    group.add_argument("--hashes",      action="store_true", help="Validate file hashes.")

    parser.add_argument("--verbose", action="store_true", help="Increase verbosity.")


def _add_clean_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add flags for the `clean` subcommand.
    """
    what = parser.add_argument_group("  What to clean")
    what.add_argument("--bcl2fastq", action="store_true", help="Remove bcl2fastq intermediate files.")
    what.add_argument("--fastqc",    action="store_true", help="Remove FastQC intermediate files.")
    what.add_argument("--multiqc",   action="store_true", help="Remove MultiQC intermediate files.")
    what.add_argument("--uploads",   action="store_true", help="Remove for_transfer directory contents for this run. WARNING: do not use before confirming delivery to NIRD and VIGASP.")


def _add_list_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add filter flags for the `list` subcommand.
    """
    filters = parser.add_argument_group("  Filters")
    group = filters.add_mutually_exclusive_group()
    group.add_argument("--failed",    action="store_true", help="Show only failed runs.")
    group.add_argument("--pending",   action="store_true", help="Show only pending runs.")
    group.add_argument("--completed", action="store_true", help="Show only completed runs.")


def _add_statistics_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add flags for the `statistics` subcommand.
    """
    filters = parser.add_argument_group("  Filters")
    filters.add_argument("--from",       dest='from_date', type=str, metavar='YYYY-MM-DD', help="Show runs from this date onwards (start of day 00:00:00).")
    filters.add_argument("--to",         dest='to_date',   type=str, metavar='YYYY-MM-DD', help="Show runs up to and including this date (end of day 23:59:59).")
    filters.add_argument("--instrument", type=str,         metavar='SERIALID',             help="Filter to a specific instrument by serial ID.")
    filters.add_argument("--last",       type=int,         metavar='N',                    help="Limit to the last N runs.")

    qc = parser.add_argument_group("  QC (only valid when RunID is provided)")
    qc.add_argument("--qc",           action="store_true", help="Display FastQC summary verdicts (PASS/WARN/FAIL per module) from summary.txt.")
    qc.add_argument("--qc-plots",     action="store_true", help="Render FastQC plots in the terminal if a terminal is detected, otherwise push to Teams or save to disk.")
    qc.add_argument("--undetermined", action="store_true", help="Show undetermined index rates per run. High rates indicate samplesheet problems.")

    output = parser.add_argument_group("  Output (CLI only; web and Teams display uses FastQC/MultiQC HTML files directly)")
    output.add_argument("--format", type=str, choices=["table", "json", "csv"], default="table", help="Output format (default: table).")


def _add_export_rawdata_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add flags for the `export-rawdata` subcommand.
    Each RunID requires one destination flag immediately following it.
    """
    transfer = parser.add_argument_group("  Per-RunID destination (one required per RunID)")
    transfer.add_argument("--destination", type=str, metavar='PATH',           help="Write tar file to local PATH.")
    transfer.add_argument("--ssh",         type=str, metavar='user@host:path', help="Transfer tar via SSH. Requires working SSH connectivity, key-based authentication and SSH client configuration (~/.ssh/config). Connectivity and configuration are the caller's responsibility.")
    transfer.add_argument("--url",         type=str, metavar='URL',            help="Transfer tar via HTTP PUT.")

    control = parser.add_argument_group("  Transfer control")
    control.add_argument("--keep", action="store_true", help="Keep the local tar file after transfer (default: remove on success).")


def _add_archive_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add flags for the `archive` subcommand.
    """
    destination = parser.add_argument_group("  Destination (mutually exclusive, one required)")
    group = destination.add_mutually_exclusive_group(required=True)
    group.add_argument("--local", type=str, metavar='PATH', help="Archive raw data to a local directory.")
    group.add_argument("--nird",  action="store_true",      help="Archive raw data to NIRD.")


def _add_tag_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add flags for the `tag` subcommand.
    """
    tags = parser.add_argument_group("  Tags")
    tags.add_argument("--badrun",  action="store_true", help="Mark as a bad run (bad data, failed flowcell or machine error during sequencing).")
    tags.add_argument("--control", action="store_true", help="Mark as a control run (water-only flowcell run to verify instrument performance).")


def _add_reject_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add flags for the `reject` subcommand.
    """
    parser.add_argument(
        "--reason",
        type=str,
        metavar='TEXT',
        default=None,
        help="Optional reason for rejection. Logged and included in the Teams notification."
    )


def _add_daemon_arguments(parser: argparse.ArgumentParser) -> None:
    """
    Add arguments for the `daemon` subcommand.
    """
    parser.add_argument(
        'action',
        choices=['start', 'stop', 'status'],
        help='Daemon action: start, stop or status.'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='With stop: abandon current runs, clean up partial output and exit immediately. Operator use only.'
    )


def validate_arguments(args: argparse.Namespace) -> None:
    """
    Enforce constraints that argparse cannot express natively.
    Raises SystemExit with a descriptive error message on violation.
    Raises NotImplementedError for subcommands not yet implemented.
    """
    if args.subcommand == 'run':
        if args.only_vigasp and args.skip_vigasp:
            raise SystemExit("error: --only-vigasp and --skip-vigasp are mutually exclusive.")
        if args.only_nird and args.skip_nird:
            raise SystemExit("error: --only-nird and --skip-nird are mutually exclusive.")
        if (args.only_vigasp or args.only_nird) and args.force:
            raise SystemExit("error: --only-vigasp/--only-nird cannot be combined with --force.")
        only_active = args.only_vigasp or args.only_nird
        skip_active = any([args.skip_bcl2fastq, args.skip_fastqc, args.skip_multiqc, args.skip_checksum])
        if only_active and skip_active:
            raise SystemExit("error: --only-vigasp/--only-nird cannot be combined with --skip-X flags.")

    if args.subcommand == 'validate':
        if not args.samplesheet and not args.hashes:
            args.samplesheet = True  # enforce default explicitly

    if args.subcommand in ('rename-run', 'rename-sample'):
        if os.getuid() != 0:
            raise SystemExit(f"error: {args.subcommand} requires root.")

    if args.subcommand == 'statistics':
        if (args.qc or args.qc_plots or args.undetermined) and not args.RunID:
            raise SystemExit("error: --qc, --qc-plots and --undetermined require a RunID.")

    if args.subcommand == 'export-rawdata':
        if not args.RunID:
            raise SystemExit("error: export-rawdata requires at least one RunID.")
        if args.keep and args.destination:
            raise SystemExit("error: --keep is only meaningful with --ssh or --url.")

    if args.subcommand == 'tag':
        if not args.badrun and not args.control:
            raise SystemExit("error: tag requires at least one of --badrun or --control.")

    if args.subcommand == 'daemon':
        if args.force and args.action != 'stop':
            raise SystemExit("error: --force is only valid with daemon stop.")

    # not yet implemented
    for subcommand in (
        'statistics',
        'status',
        'list',
        'clean',
        'delete',
        'rename-run',
        'rename-sample',
        'export-rawdata',
        'archive',
        'tag',
        'notify',
        'approve',
        'reject',
        'daemon',
    ):
        if args.subcommand == subcommand:
            raise NotImplementedError(f"{subcommand}: not yet implemented.")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments for the demultiplex pipeline.
    Returns a Namespace containing the active subcommand and its arguments.

    Invocation modes:
        demultiplex.py                  Scan rawdata directory and process all pending runs.
        demultiplex.py <RunID>          Alias for: demultiplex.py run <RunID>
        demultiplex.py run <RunID>      Explicit form.
    """
    _preprocess_argv()                                                  # rewrite argv before parser sees it

    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),                             # respects binary rename e.g. nvi-demux
        description='Demultiplex Illumina MiSeq and NextSeq runs, perform QC and deliver results to NIRD and VIGASP/Galaxy.',
        epilog='Example: %(prog)s run 230415_M01234_1234_000000000-ABCDE',
        formatter_class=_VerboseHelpFormatter
    )

    # global flags
    parser.add_argument('-V', '--version', action='version', version=f'%(prog)s {constants.VERSION}')
    parser.add_argument('--config',        type=str, metavar='PATH', default=None, help='Path to an alternate config file.')

    subparsers = parser.add_subparsers(dest='subcommand', metavar='subcommand')
    subparsers.required = False                                         # no subcommand = scan mode

    # run
    run_parser = subparsers.add_parser(
        'run',
        help='Run the full demultiplex pipeline.',
        description=(
            'Run the full demultiplex pipeline for one or more Illumina runs.\n\n'
            'Processes BCL files through bcl2fastq, performs FastQC and MultiQC quality checks,\n'
            'calculates checksums, prepares delivery files and uploads to NIRD and VIGASP.\n\n'
            'Individual steps can be skipped via --skip-X flags.\n'
            'Delivery to a specific destination can be re-run via --only-X flags.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(run_parser)
    _add_run_arguments(run_parser)

    # validate
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate samplesheet or file hashes for a run.',
        description=(
            'Validate a run without executing the pipeline.\n\n'
            'Defaults to samplesheet validation if no flag is provided.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(validate_parser)
    _add_validate_arguments(validate_parser)

    # clean
    clean_parser = subparsers.add_parser(
        'clean',
        help='Remove intermediate files, keeping final deliverables.',
        description=(
            'Remove intermediate files for one or more runs, keeping final deliverables.\n\n'
            'WARNING: --uploads removes for_transfer directory contents.\n'
            'Do not use --uploads before confirming delivery to NIRD and VIGASP.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(clean_parser)
    _add_clean_arguments(clean_parser)

    # delete
    delete_parser = subparsers.add_parser(
        'delete',
        help='Remove a demultiplexed run and all its artifacts. Never touches rawdata.',
        description=(
            'Remove a demultiplexed run and all its artifacts.\n\n'
            'WARNING: this operation is irreversible.\n'
            'Raw sequencer data is never touched.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(delete_parser)

    # rename-run
    rename_run_parser = subparsers.add_parser(
        'rename-run',
        help='Rename a run. WARNING: destructive. Updates RunID in the samplesheet. Requires root.',
        description=(
            'Rename a run directory, tar files and samplesheet copy.\n\n'
            'WARNING: destructive operation. Requires root.\n'
            'Updates the RunID in the samplesheet copy.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    rename_run_parser.add_argument('RunID',    type=parse_runid, help='Existing RunID.')
    rename_run_parser.add_argument('NewRunID', type=parse_runid, help='New RunID.')

    # rename-sample
    rename_sample_parser = subparsers.add_parser(
        'rename-sample',
        help='Rename a sample within a run. WARNING: destructive. Updates SampleID in the samplesheet. Requires root.',
        description=(
            'Rename a sample within a run.\n\n'
            'WARNING: destructive operation. Requires root.\n'
            'Updates the SampleID in the samplesheet copy.\n'
            'NewSample must be a valid sample name from ShinyLIMS.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    rename_sample_parser.add_argument('RunID',     type=parse_runid, help='RunID containing the sample.')
    rename_sample_parser.add_argument('Sample',    type=str,         help='Existing sample name.')
    rename_sample_parser.add_argument('NewSample', type=str,         help='New sample name. Must be a valid sample name from ShinyLIMS.')

    # export-rawdata
    export_rawdata_parser = subparsers.add_parser(
        'export-rawdata',
        help='Tar raw BCL data directory and optionally transfer it via SSH or HTTP. Not the delivery tars.',
        description=(
            'Tar the raw BCL data directory for one or more runs and optionally transfer it.\n\n'
            'This operates on raw sequencer output, not the demultiplexed delivery tars.\n'
            'At least one RunID with a destination flag is required.\n'
            'Each RunID must be followed immediately by its destination flag.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(export_rawdata_parser)
    _add_export_rawdata_arguments(export_rawdata_parser)

    # archive
    archive_parser = subparsers.add_parser(
        'archive',
        help='Move raw data for a run into an archive directory. Not yet implemented.',
        description=(
            'Move raw data for one or more runs into an archive directory.\n\n'
            'NOT YET IMPLEMENTED.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(archive_parser)
    _add_archive_arguments(archive_parser)

    # tag
    tag_parser = subparsers.add_parser(
        'tag',
        help='Tag a run with metadata. Written to the database when available. Not yet implemented.',
        description=(
            'Tag a run with metadata for classification and reporting purposes.\n\n'
            'Tags are written to the database when available.\n\n'
            'NOT YET IMPLEMENTED.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(tag_parser)
    _add_tag_arguments(tag_parser)

    # list
    list_parser = subparsers.add_parser(
        'list',
        help='List all known runs.',
        description='List all known runs, optionally filtered by status.',
        formatter_class=_VerboseHelpFormatter
    )
    _add_list_arguments(list_parser)

    # status
    status_parser = subparsers.add_parser(
        'status',
        help='Show the processing state of a run.',
        description='Show the current processing state of one or more runs.',
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(status_parser)

    # statistics (alias: stats)
    statistics_parser = subparsers.add_parser(
        'statistics',
        aliases=['stats'],
        help='Show pipeline and QC statistics.',
        description=(
            'Show pipeline and QC statistics.\n\n'
            'If RunID is omitted, shows aggregate statistics across all runs.\n'
            'QC flags (--qc, --qc-plots, --undetermined) require a RunID.\n\n'
            'Output formats (--format) apply to CLI output only.\n'
            'Web and Teams display uses FastQC/MultiQC HTML files directly.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(statistics_parser)
    _add_statistics_arguments(statistics_parser)

    # notify
    notify_parser = subparsers.add_parser(
        'notify',
        help='Manually trigger Teams QC notification for a run. Not yet implemented.',
        description=(
            'Manually trigger the Teams QC notification for a run\n'
            'without waiting for the scheduled delivery time.\n\n'
            'NOT YET IMPLEMENTED.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(notify_parser)

    # approve
    approve_parser = subparsers.add_parser(
        'approve',
        help='Manually approve a run from the CLI rather than via Teams. Not yet implemented.',
        description=(
            'Manually approve a run from the CLI rather than via the Teams approval workflow.\n\n'
            'NOT YET IMPLEMENTED.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(approve_parser)

    # reject
    reject_parser = subparsers.add_parser(
        'reject',
        help='Manually reject a run from the CLI rather than via Teams. Not yet implemented.',
        description=(
            'Manually reject a run from the CLI rather than via the Teams approval workflow.\n\n'
            'NOT YET IMPLEMENTED.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_runid_argument(reject_parser)
    _add_reject_arguments(reject_parser)

    # daemon
    daemon_parser = subparsers.add_parser(
        'daemon',
        help='Control the demultiplex daemon. Not yet implemented.',
        description=(
            'Control the demultiplex daemon.\n\n'
            'stop waits for any current runs to finish before exiting cleanly.\n'
            'stop --force abandons current runs, cleans up partial output and exits immediately.\n\n'
            'NOT YET IMPLEMENTED.'
        ),
        formatter_class=_VerboseHelpFormatter
    )
    _add_daemon_arguments(daemon_parser)

    args = parser.parse_args()

    # normalize stats alias so downstream code only checks for 'statistics'
    if args.subcommand == 'stats':
        args.subcommand = 'statistics'

    # no subcommand: enter scan mode
    if args.subcommand is None:
        args.subcommand = 'scan'

    return args
