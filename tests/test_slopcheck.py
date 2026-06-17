from pathlib import Path

from vibe_tools.slopcheck import (
    find_python_imports,
    parse_requirements,
    typosquat_of,
    collect_packages,
    main,
)


def test_find_imports_ignores_relative():
    src = "import requests\nfrom os import path\nfrom . import sibling\nimport numpy as np\n"
    mods = find_python_imports(src)
    assert "requests" in mods and "numpy" in mods and "os" in mods
    assert "sibling" not in mods


def test_parse_requirements_strips_specifiers():
    txt = "requests==2.31.0\n# comment\nflask>=2.0\nuvicorn[standard]>=0.20\n"
    pkgs = parse_requirements(txt)
    assert {"requests", "flask", "uvicorn"} <= pkgs


def test_typosquat_detection():
    assert typosquat_of("reqeusts") == "requests"
    assert typosquat_of("requests") is None
    assert typosquat_of("totally-made-up-name-xyz") is None


def test_collect_maps_import_to_pkg(tmp_path: Path):
    (tmp_path / "app.py").write_text("import cv2\nimport os\n")
    pkgs = collect_packages([str(tmp_path)])
    assert "opencv-python" in pkgs  # cv2 -> opencv-python
    assert "os" not in pkgs          # stdlib filtered


def test_offline_run_flags_typosquat(tmp_path: Path):
    (tmp_path / "app.py").write_text("import reqeusts\n")
    rc = main(["--offline", str(tmp_path)])
    assert rc == 1  # suspicious -> non-zero exit
