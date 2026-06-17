"""slopcheck - catch hallucinated and typosquatted packages before you install
them ("slopsquatting" defense).

Pain it solves (2026 supply-chain pain): AI assistants confidently tell you to
`pip install <something>` for a package that doesn't exist - or worse, a
typosquat sitting one character away from a real one that an attacker has
registered. slopcheck reads the imports/requirements an LLM handed you and
tells you which packages are real, which don't exist on PyPI, and which look
like typosquats of popular packages.

    slopcheck app.py                  # check imports in a file
    slopcheck requirements.txt        # check a requirements file
    slopcheck src/                    # walk a directory
    slopcheck --offline app.py        # typosquat heuristics only, no network

Exit code is non-zero if anything suspicious is found (handy in CI / hooks).
"""
from __future__ import annotations

import argparse
import ast
import difflib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from ._common import iter_source_files, read_text

# Common `import X` -> PyPI package name mismatches.
IMPORT_TO_PKG = {
    "cv2": "opencv-python", "PIL": "Pillow", "sklearn": "scikit-learn",
    "yaml": "PyYAML", "bs4": "beautifulsoup4", "dotenv": "python-dotenv",
    "dateutil": "python-dateutil", "jwt": "PyJWT", "serial": "pyserial",
    "OpenSSL": "pyOpenSSL", "google": "google-api-python-client",
    "win32api": "pywin32", "Crypto": "pycryptodome", "redis": "redis",
}

# A small list of frequently-targeted popular packages for typosquat checks.
# Offline mode relies on this; online mode uses it to flag close-but-not-equal.
POPULAR_PACKAGES = {
    "requests", "urllib3", "numpy", "pandas", "scipy", "matplotlib", "pillow",
    "flask", "django", "fastapi", "pydantic", "sqlalchemy", "boto3", "click",
    "pytest", "setuptools", "wheel", "pip", "tensorflow", "torch", "keras",
    "scikit-learn", "beautifulsoup4", "selenium", "scrapy", "openai",
    "anthropic", "langchain", "transformers", "tiktoken", "tqdm", "rich",
    "typer", "httpx", "aiohttp", "uvicorn", "gunicorn", "celery", "redis",
    "pymongo", "psycopg2", "cryptography", "pyjwt", "python-dotenv", "colorama",
}


def find_python_imports(text: str) -> set[str]:
    """Return top-level imported module names from Python source."""
    mods: set[str] = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return mods
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:  # ignore relative imports
                mods.add(node.module.split(".")[0])
    return mods


def parse_requirements(text: str) -> set[str]:
    pkgs: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # strip version specifiers / extras / markers
        name = line.split(";")[0].split("[")[0]
        for sep in ("==", ">=", "<=", "~=", "!=", ">", "<", "="):
            name = name.split(sep)[0]
        name = name.strip()
        if name:
            pkgs.add(name)
    return pkgs


def collect_packages(paths: list[str]) -> set[str]:
    """Gather candidate PyPI package names from files/dirs."""
    stdlib = getattr(sys, "stdlib_module_names", set())
    pkgs: set[str] = set()
    files: list[Path] = []
    for p in paths:
        pp = Path(p)
        if not pp.exists():
            print(f"warning: {pp} does not exist, skipping", file=sys.stderr)
            continue
        files.extend(iter_source_files(pp))

    for f in files:
        text = read_text(f)
        if text is None:
            continue
        if f.name in ("requirements.txt", "requirements-dev.txt") or f.name.endswith(".requirements.txt"):
            pkgs |= parse_requirements(text)
        elif f.suffix == ".py":
            for mod in find_python_imports(text):
                if mod in stdlib:
                    continue
                pkgs.add(IMPORT_TO_PKG.get(mod, mod))
    # never flag the obvious local-package noise
    return {p for p in pkgs if p and not p.startswith("_")}


def pypi_exists(name: str, timeout: float = 6.0) -> bool | None:
    """True/False if known, None if the lookup failed (network error)."""
    url = f"https://pypi.org/pypi/{name}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "slopcheck/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        return None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def typosquat_of(name: str) -> str | None:
    """If *name* is a near-miss of a popular package (but not equal), return it."""
    lower = name.lower()
    if lower in POPULAR_PACKAGES:
        return None
    matches = difflib.get_close_matches(lower, POPULAR_PACKAGES, n=1, cutoff=0.85)
    return matches[0] if matches else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="slopcheck",
        description="Catch hallucinated / typosquatted packages before you install them.",
    )
    ap.add_argument("paths", nargs="+", help="files or directories to scan")
    ap.add_argument("--offline", action="store_true", help="typosquat heuristics only, no PyPI lookups")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    packages = sorted(collect_packages(args.paths))
    if not packages:
        print("No external packages found to check.")
        return 0

    results = []
    suspicious = 0
    for pkg in packages:
        squat = typosquat_of(pkg)
        if args.offline:
            exists = None
            if squat:
                status, note = "typosquat?", f"did you mean '{squat}'?"
            else:
                status, note = "skipped", "offline: existence not checked"
        else:
            exists = pypi_exists(pkg)
            if exists is False:
                status = "NOT FOUND"
                note = (f"not on PyPI - did you mean '{squat}'?" if squat
                        else "not on PyPI - likely hallucinated")
            elif exists is None:
                status, note = "lookup failed", "network error"
            elif squat:
                status = "typosquat?"
                note = f"exists, but 1-2 chars from '{squat}' - confirm it's the right one"
            else:
                status, note = "ok", ""
        if status in ("NOT FOUND", "typosquat?"):
            suspicious += 1
        results.append({"package": pkg, "status": status, "looks_like": squat,
                        "exists": exists, "note": note})

    if args.json:
        print(json.dumps({"checked": len(results), "suspicious": suspicious, "results": results}, indent=2))
        return 1 if suspicious else 0

    width = max(len(r["package"]) for r in results)
    print(f"{'package':<{width}}   status")
    print(f"{'-' * width}   {'-' * 18}")
    for r in results:
        note = f"  ({r['note']})" if r["note"] else ""
        print(f"{r['package']:<{width}}   {r['status']}{note}")

    print()
    if suspicious:
        print(f"[!] {suspicious} suspicious package(s) of {len(results)} checked. "
              f"Verify before installing.")
        return 1
    print(f"[ok] all {len(results)} package(s) look fine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
