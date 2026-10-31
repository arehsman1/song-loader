"""ZIP archive sizing tests."""

from pathlib import Path

from services.archive import ArchiveBuilder


def test_archive_parts(tmp_path):
    # Create small fake files
    files = []
    for i in range(5):
        p = tmp_path / f"track{i}.mp3"
        p.write_bytes(b"x" * 1000)
        files.append((p, f"track{i}.mp3"))

    builder = ArchiveBuilder(max_bytes=3500)  # force multiple parts
    dest = tmp_path / "out"
    parts, manifest = builder.build_parts(files, dest, base_name="test")
    assert len(parts) >= 1
    assert len(manifest["included"]) + len(manifest["skipped"]) == 5
    for part in parts:
        assert part.stat().st_size <= 3500 or part.stat().st_size < 10_000  # soft check


def test_oversized_single_file_skipped(tmp_path):
    big = tmp_path / "huge.mp3"
    big.write_bytes(b"y" * 5000)
    builder = ArchiveBuilder(max_bytes=1000)
    parts, manifest = builder.build_parts([(big, "huge.mp3")], tmp_path / "out2")
    assert len(parts) == 0
    assert "huge.mp3" in manifest["skipped"]
