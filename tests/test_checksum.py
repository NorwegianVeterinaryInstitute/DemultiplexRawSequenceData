# test_checksum.py
# pytest tests for demux/util/checksum.py hash file output
#
# usage: pytest tests/test_checksum.py
#
# NOTE: tests are self-contained and use a temporary file as input.
#       No real sequencing data or demux object required.
# NOTE: test_hash_files_pass_system_verification requires /usr/bin/md5sum
#       and /usr/bin/sha512sum to be present on the test host.
#
# covers:
#   #78  - hash lengths are correct (md5: 32 hex chars, sha512: 128 hex chars)
#   #80  - hash files pass md5sum -c / sha512sum -c
#   #90  - hash file references the correct file for the current run
#   #91  - hash file structure is correct (two spaces, basename only, single newline)
#
# example: pytest tests/test_checksum.py -v
#
# Copyright (C) 2026 George Marselis <george.marselis@vetinst.no>
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

import os
import subprocess
import tempfile

import pytest

from demux.util.checksum import hash_file, write_checksum_files
import demux.config.constants as constants


@pytest.fixture
def tmp_target_file():
    """Write a small binary file to a temp directory, yield its path, clean up after."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath: str = os.path.join(tmpdir, "test_run_sample.tar")
        with open(filepath, "wb") as fh:
            fh.write(b"NVI demux test payload 2026")
        yield filepath


def test_hash_lengths(tmp_target_file: str) -> None:
    """#78 - md5 digest is 32 hex chars, sha512 digest is 128 hex chars."""
    filepath: str
    md5sum: str
    sha512sum: str
    filepath, md5sum, sha512sum = hash_file(tmp_target_file)
    assert len(md5sum)    == 32,  f"md5 digest should be 32 hex chars, got {len(md5sum)}"
    assert len(sha512sum) == 128, f"sha512 digest should be 128 hex chars, got {len(sha512sum)}"


def test_hash_file_structure(tmp_target_file: str) -> None:
    """#91 - hash file is: <hash><two spaces><basename><newline>, nothing else."""
    filepath: str
    md5sum: str
    sha512sum: str
    filepath, md5sum, sha512sum = hash_file(tmp_target_file)
    write_checksum_files((filepath, md5sum, sha512sum))

    basename: str = os.path.basename(tmp_target_file)

    for suffix, expected_hash in [(constants.MD5_SUFFIX, md5sum), (constants.SHA512_SUFFIX, sha512sum)]:
        hash_filepath: str = f"{tmp_target_file}{suffix}"
        with open(hash_filepath, "r") as fh:
            content: str = fh.read()

        lines: list[str] = content.splitlines()
        assert len(lines) == 1,                             f"{suffix}: expected exactly one line, got {len(lines)}"
        assert "  " in lines[0],                            f"{suffix}: missing two-space separator"
        assert not lines[0].startswith(" "),                f"{suffix}: line must start with hash, not space"
        assert content.endswith("\n"),                      f"{suffix}: file must end with newline"
        assert lines[0] == f"{expected_hash}  {basename}", f"{suffix}: unexpected content: {lines[0]!r}"
        assert "/" not in lines[0].split("  ", 1)[1],      f"{suffix}: hash file must contain basename only, not a path"


def test_hash_files_pass_system_verification(tmp_target_file: str) -> None:
    """#80 - md5sum -c and sha512sum -c exit 0 against the generated hash files."""
    filepath: str
    md5sum: str
    sha512sum: str
    filepath, md5sum, sha512sum = hash_file(tmp_target_file)
    write_checksum_files((filepath, md5sum, sha512sum))

    workdir: str = os.path.dirname(tmp_target_file)

    for cmd, suffix in (
        ("/usr/bin/md5sum",    constants.MD5_SUFFIX),
        ("/usr/bin/sha512sum", constants.SHA512_SUFFIX),
    ):
        hash_filepath: str = f"{tmp_target_file}{suffix}"
        result: subprocess.CompletedProcess = subprocess.run(
            [cmd, "--check", "--quiet", hash_filepath],
            cwd=workdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"{cmd} --check failed for {hash_filepath}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )