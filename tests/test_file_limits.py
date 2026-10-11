"""File size limit helpers."""

from config import config


def test_max_file_size_bytes():
    assert config.max_file_size_bytes == config.max_file_size_mib * 1024 * 1024
    assert config.max_file_size_mib == 45  # default from env or fallback
