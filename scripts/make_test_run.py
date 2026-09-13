#!/usr/bin/env python3
"""
make_test_run.py - clone a real Illumina run directory into a fake test run.

Copies /data/rawdata/<source RunID> to /data/rawdata/999999_M09180_9999_<NNNNNNNNN>-M7V7K,
where NNNNNNNNN is one higher than the highest existing fake run, and rewrites
SampleSheet.csv so every Sample_Project is renamed to a TESTDATA project.
Everything else in the run directory is copied untouched.

usage: make_test_run.py 260904_M09180_0073_000000000-MF398

Copyright (C) 2026  George Marselis <george.marselis@vetinst.no>
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""

import argparse
import os
import re
import subprocess
import sys
ub
RAWDATA_DIR: str = "/data/rawdata"
SAMPLE_SHEET: str = "SampleSheet.csv"
FAKE_PREFIX: str = "999999_M09180_9999_"
FAKE_SUFFIX: str = "-M7V7K"
FAKE_PATTERN: re.Pattern = re.compile(r"^999999_M09180_9999_(\d{9})-M7V7K$")
TEST_PROJECT_PREFIX: str = "99999-TESTDATA_Trollus_norvegicus_"
DATA_SECTION: str = "[Data]"
PROJECT_COLUMN: str = "Sample_Project"
CP: str = "/usr/bin/cp"


def next_fake_run_id() -> str:
    """
    Scan RAWDATA_DIR for existing fake runs and return the next RunID.

    :return: RunID string with the nine-digit counter incremented
    """
    highest: int = -1
    entry: str
    for entry in os.listdir(RAWDATA_DIR):
        match: re.Match | None = FAKE_PATTERN.match(entry)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{FAKE_PREFIX}{highest + 1:09d}{FAKE_SUFFIX}"


def rewrite_sample_sheet(path: str) -> dict[str, str]:
    """
    Rewrite Sample_Project values in the [Data] section to TESTDATA names.

    :param path: absolute path to SampleSheet.csv inside the fake run
    :return: mapping of original project name -> test project name
    """
    with open(path, "r", encoding="utf-8", newline="") as handle:
        lines: list[str] = handle.read().splitlines(keepends=True)

    mapping: dict[str, str] = {}
    in_data: bool = False
    project_index: int = -1
    output: list[str] = []
    line: str
    for line in lines:
        stripped: str = line.rstrip("\r\n")
        newline: str = line[len(stripped):]
        if stripped.startswith("["):
            in_data = stripped == DATA_SECTION
            output.append(line)
            continue
        if not in_data or stripped == "":
            output.append(line)
            continue
        fields: list[str] = stripped.split(",")
        if project_index < 0:
            if PROJECT_COLUMN not in fields:
                raise ValueError(f"{PROJECT_COLUMN} column not found in {path}")
            project_index = fields.index(PROJECT_COLUMN)
            output.append(line)
            continue
        original: str = fields[project_index]
        if original not in mapping:
            mapping[original] = f"{TEST_PROJECT_PREFIX}{len(mapping) + 1:02d}"
        fields[project_index] = mapping[original]
        output.append(",".join(fields) + newline)

    if project_index < 0:
        raise ValueError(f"{DATA_SECTION} section not found in {path}")

    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.writelines(output)
    return mapping


def main() -> int:
    """
    Entry point.

    :return: process exit code
    """
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Clone a real run into an incrementing fake test run.")
    parser.add_argument("source", help=f"source RunID under {RAWDATA_DIR}")
    args: argparse.Namespace = parser.parse_args()
    args.source = args.source.rstrip("/")

    source_dir: str = os.path.join(RAWDATA_DIR, args.source)
    if not os.path.isdir(source_dir):
        print(f"ERROR: {source_dir} is not a directory", file=sys.stderr)
        return 1
    if not os.path.isfile(os.path.join(source_dir, SAMPLE_SHEET)):
        print(f"ERROR: {source_dir} has no {SAMPLE_SHEET}", file=sys.stderr)
        return 1
    if FAKE_PATTERN.match(args.source):
        print(f"ERROR: {args.source} is a fake run; source must be a real run", file=sys.stderr)
        return 1

    fake_run_id: str = next_fake_run_id()
    target_dir: str = os.path.join(RAWDATA_DIR, fake_run_id)
    if os.path.exists(target_dir):
        print(f"ERROR: {target_dir} already exists", file=sys.stderr)
        return 1
    if os.path.realpath(target_dir) == os.path.realpath(source_dir):
        print(f"ERROR: target resolves to source {source_dir}; refusing", file=sys.stderr)
        return 1

    print(f"copying {source_dir} -> {target_dir}")
    result: subprocess.CompletedProcess = subprocess.run([CP, "-a", source_dir, target_dir], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: {CP} failed: {result.stderr.strip()}", file=sys.stderr)
        return result.returncode

    sheet_path: str = os.path.join(target_dir, SAMPLE_SHEET)
    if os.path.realpath(sheet_path).startswith(os.path.realpath(source_dir) + os.sep):
        print(f"ERROR: {sheet_path} is inside the source run; refusing to write", file=sys.stderr)
        return 1
    mapping: dict[str, str] = rewrite_sample_sheet(sheet_path)
    original: str
    renamed: str
    for original, renamed in mapping.items():
        print(f"{original} -> {renamed}")
    print(fake_run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
