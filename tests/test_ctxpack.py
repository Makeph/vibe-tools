from pathlib import Path

from vibe_tools.ctxpack import redact, main
from vibe_tools._common import scan_secrets, iter_source_files


def test_scan_and_redact_secret():
    text = 'API_KEY = "sk-ant-abcdefghijklmnopqrstuvwxyz123"'
    assert scan_secrets(text)
    cleaned, n = redact(text)
    assert n >= 1
    assert "sk-ant-" not in cleaned
    assert "<<REDACTED-SECRET>>" in cleaned


def test_iter_skips_noise_dirs(tmp_path: Path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("noise")
    (tmp_path / "keep.py").write_text("print('hi')")
    found = {p.name for p in iter_source_files(tmp_path)}
    assert "keep.py" in found
    assert "junk.js" not in found


def test_ctxpack_writes_bundle(tmp_path: Path, capsys):
    (tmp_path / "a.py").write_text("x = 1\n")
    out = tmp_path / "bundle.md"
    rc = main([str(tmp_path), "--out", str(out)])
    assert rc == 0
    bundle = out.read_text()
    assert "a.py" in bundle and "x = 1" in bundle and "## File tree" in bundle
