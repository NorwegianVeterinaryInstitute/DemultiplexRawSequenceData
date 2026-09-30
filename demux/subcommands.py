# demux/subcommands.py

"""
One handler per subcommand.
`run` and scan mode (no subcommand) go through main( ) in demultiplex.py; every other subcommand lands here.
Each handler is a stub until the subcommand is implemented: it stops the script with "not yet implemented".
"""

import argparse


def _not_implemented( args: argparse.Namespace ) -> None:
    """
    Stop the script: the subcommand exists on the command line but has no implementation yet.
    """
    raise SystemExit( f"error: {args.subcommand}: not yet implemented." )


def subcommand_validate( args: argparse.Namespace ) -> None:
    """
    validate: not yet implemented.
    """
    _not_implemented( args )


def subcommand_clean( args: argparse.Namespace ) -> None:
    """
    clean: not yet implemented.
    """
    _not_implemented( args )


def subcommand_delete( args: argparse.Namespace ) -> None:
    """
    delete: not yet implemented.
    """
    _not_implemented( args )


def subcommand_rename_run( args: argparse.Namespace ) -> None:
    """
    rename-run: not yet implemented.
    """
    _not_implemented( args )


def subcommand_rename_sample( args: argparse.Namespace ) -> None:
    """
    rename-sample: not yet implemented.
    """
    _not_implemented( args )


def subcommand_export_rawdata( args: argparse.Namespace ) -> None:
    """
    export-rawdata: not yet implemented.
    """
    _not_implemented( args )


def subcommand_archive( args: argparse.Namespace ) -> None:
    """
    archive: not yet implemented.
    """
    _not_implemented( args )


def subcommand_tag( args: argparse.Namespace ) -> None:
    """
    tag: not yet implemented.
    """
    _not_implemented( args )


def subcommand_list( args: argparse.Namespace ) -> None:
    """
    list: not yet implemented.
    """
    _not_implemented( args )


def subcommand_status( args: argparse.Namespace ) -> None:
    """
    status: not yet implemented.
    """
    _not_implemented( args )


def subcommand_statistics( args: argparse.Namespace ) -> None:
    """
    statistics: not yet implemented.
    """
    _not_implemented( args )


def subcommand_notify( args: argparse.Namespace ) -> None:
    """
    notify: not yet implemented.
    """
    _not_implemented( args )


def subcommand_approve( args: argparse.Namespace ) -> None:
    """
    approve: not yet implemented.
    """
    _not_implemented( args )


def subcommand_reject( args: argparse.Namespace ) -> None:
    """
    reject: not yet implemented.
    """
    _not_implemented( args )


def subcommand_daemon( args: argparse.Namespace ) -> None:
    """
    daemon: not yet implemented.
    """
    _not_implemented( args )


# subcommand name, as argparse sets args.subcommand -> handler
SUBCOMMAND_HANDLERS: dict = {
    'validate':       subcommand_validate,
    'clean':          subcommand_clean,
    'delete':         subcommand_delete,
    'rename-run':     subcommand_rename_run,
    'rename-sample':  subcommand_rename_sample,
    'export-rawdata': subcommand_export_rawdata,
    'archive':        subcommand_archive,
    'tag':            subcommand_tag,
    'list':           subcommand_list,
    'status':         subcommand_status,
    'statistics':     subcommand_statistics,
    'notify':         subcommand_notify,
    'approve':        subcommand_approve,
    'reject':         subcommand_reject,
    'daemon':         subcommand_daemon,
}
