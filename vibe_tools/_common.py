"""Shared helpers for the vibe-tools CLIs.

Deliberately dependency-free (Python 3.9+ stdlib only) so the tools run
anywhere with `python -m vibe_tools.<tool>` and the test suite needs no installs.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable, Iterator

# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------
# We default to a fast, offline heuristic (~4 characters per token, the common
# rule of thumb for English + code). If tiktoken is installed and the caller
# asks for it, we use the real BPE count. The heuristic is always labelled as
# an estimate in the CLIs so nobody mistakes it for a billing-grade number.

CHARS_PER_TOKEN = 4.0


def estimate_tokens(text: str, tokenizer: str = "heuristic") -> int:
    """Estimate the number of tokens in *text*.

    tokenizer="heuristic" -> len(text) / 4 (offline, no deps).
    tokenizer="tiktoken"  -> real cl100k_base count if tiktoken is available,
                             otherwise falls back to the heuristic.
    """
    if not text:
        return 0
    if tokenizer == "tiktoken":
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            # tiktoken missing or failed -> silent fall-through to heuristic.
            pass
    return max(1, round(len(text) / CHARS_PER_TOKEN))


# ---------------------------------------------------------------------------
# Secret detection
# ---------------------------------------------------------------------------
# Patterns for the credentials people most often paste into a chatbot by
# accident. Tuned for the 2026 "everyone has an LLM key" reality.
SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("Generic bearer secret", re.compile(r"(?i)\b(?:api[_-]?key|secret|token|passwd|password)\b\s*[:=]\s*['\"][^'\"]{12,}['\"]")),
]


def scan_secrets(text: str) -> list[tuple[str, str]]:
    """Return a list of (label, matched_snippet) for any secrets found."""
    hits: list[tuple[str, str]] = []
    for label, pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            snippet = m.group(0)
            if len(snippet) > 40:
                snippet = snippet[:18] + "..." + snippet[-6:]
            hits.append((label, snippet))
    return hits


# ---------------------------------------------------------------------------
# File walking
# ---------------------------------------------------------------------------
DEFAULT_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "target", ".idea",
    ".vscode", ".mypy_cache", ".pytest_cache", ".ruff_cache", "coverage",
    ".terraform", "vendor", ".cache",
}

# Files that are almost always noise when feeding code to an LLM.
DEFAULT_SKIP_GLOBS = {
    "*.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Cargo.lock", "*.min.js", "*.min.css", "*.map",
}

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg",
    ".pdf", ".zip", ".gz", ".tar", ".7z", ".rar", ".exe", ".dll", ".so",
    ".dylib", ".bin", ".o", ".a", ".class", ".jar", ".pyc", ".woff",
    ".woff2", ".ttf", ".eot", ".mp3", ".mp4", ".mov", ".avi", ".wav",
    ".db", ".sqlite", ".sqlite3", ".parquet", ".npy", ".pt", ".onnx",
}


def _fnmatch_any(name: str, globs: Iterable[str]) -> bool:
    from fnmatch import fnmatch

    return any(fnmatch(name, g) for g in globs)


def iter_source_files(
    root: str | os.PathLike,
    skip_dirs: set[str] | None = None,
    skip_globs: set[str] | None = None,
    max_file_bytes: int = 500_000,
) -> Iterator[Path]:
    """Yield text source files under *root*, skipping noise and binaries."""
    root = Path(root)
    skip_dirs = DEFAULT_SKIP_DIRS if skip_dirs is None else skip_dirs
    skip_globs = DEFAULT_SKIP_GLOBS if skip_globs is None else skip_globs

    if root.is_file():
        yield root
        return

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in place so os.walk doesn't descend.
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.suffix.lower() in BINARY_EXTS:
                continue
            if _fnmatch_any(fn, skip_globs):
                continue
            try:
                if p.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            yield p


def read_text(path: Path) -> str | None:
    """Read a file as UTF-8 text; return None if it looks binary/undecodable."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:1024]:  # NUL byte -> binary
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except UnicodeDecodeError:
            return None


def human_int(n: int) -> str:
    return f"{n:,}"
