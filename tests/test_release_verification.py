import hashlib
from pathlib import Path

import pytest

from github_updater import (
    UpdateVerificationError,
    calculate_sha256,
    parse_checksum_file,
    verify_sha256,
)


def test_calculate_sha256(tmp_path: Path):
    test_file = tmp_path / "release.tar.gz"
    test_file.write_bytes(b"SolarInspector")

    expected = hashlib.sha256(b"SolarInspector").hexdigest()

    assert calculate_sha256(test_file) == expected


def test_parse_checksum_file():
    checksum = "a" * 64
    content = f"{checksum}  SolarInspector-4.1.0.tar.gz\n"

    result = parse_checksum_file(
        content,
        "SolarInspector-4.1.0.tar.gz",
    )

    assert result == checksum


def test_checksum_filename_must_match():
    checksum = "b" * 64
    content = f"{checksum}  foreign-package.tar.gz\n"

    with pytest.raises(UpdateVerificationError):
        parse_checksum_file(
            content,
            "SolarInspector-4.1.0.tar.gz",
        )


def test_verify_sha256_rejects_modified_file(tmp_path: Path):
    test_file = tmp_path / "release.tar.gz"
    test_file.write_bytes(b"manipulated")

    with pytest.raises(UpdateVerificationError):
        verify_sha256(test_file, "0" * 64)
