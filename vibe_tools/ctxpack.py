"""ctxpack - pack a repo into ONE token-budgeted, secret-scrubbed, LLM-ready
context file, so you stop copy-pasting files into a chatbot one by one.

Pain it solves (r/ChatGPTCoding, recurring 2026 - people manually paste whole
codebases into an LLM chat, blow the context window with node_modules and
lockfiles, and occasionally leak an API key into the prompt):

    ctxpack .                         # -> stdout, a single markdown bundle
    ctxpack src/ --out context.md --max-tokens 100000
    ctxpack . --redact                # blank out any secrets before packing

It walks the tree (skipping .git, node_modules, venvs, binaries, lockfiles),
builds a file tree + per-file fenced bundle, enforces a token budget, and
warns (or redacts) when it spots credentials. Pipe the result to `llmcost`.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ._common import (
    estimate_tokens,
    human_int,
    iter_source_files,
    read_text,
    scan_secrets,
)

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "tsx",
    ".jsx": "jsx", ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
    ".php": "php", ".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp",
    ".sh": "bash", ".sql": "sql", ".html": "html", ".css": "css",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".md": "markdown",
}


def redact(text: str) -> tuple[str, int]:
    """Replace any detected secrets with a placeholder. Returns (text, count)."""
    from ._common import SECRET_PATTERNS

    count = 0
    for _label, pat in SECRET_PATTERNS:
        text, n = pat.subn("<<REDACTED-SECRET>>", text)
        count += n
    return text, count


def build_tree(files: list[Path], root: Path) -> str:
    lines = []
    for f in files:
        try:
            rel = f.relative_to(root)
        except ValueError:
            rel = f
        lines.append(f"  {rel.as_posix()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="ctxpack",
        description="Pack a repo into one token-budgeted, secret-aware LLM context file.",
    )
    ap.add_argument("root", nargs="?", default=".", help="directory or file to pack (default: .)")
    ap.add_argument("--out", type=Path, help="write to this file instead of stdout")
    ap.add_argument(
        "--max-tokens",
        type=int,
        default=120_000,
        help="stop adding files once this budget is reached (default: 120000)",
    )
    ap.add_argument(
        "--tokenizer",
        choices=["heuristic", "tiktoken"],
        default="heuristic",
        help="token counter (default: heuristic ~4 chars/token, offline)",
    )
    ap.add_argument("--redact", action="store_true", help="blank out detected secrets before packing")
    ap.add_argument("--max-file-bytes", type=int, default=500_000, help="skip files larger than this")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.exists():
        ap.error(f"{root} does not exist")

    candidates = list(iter_source_files(root, max_file_bytes=args.max_file_bytes))

    included: list[Path] = []
    body_parts: list[str] = []
    total_tokens = 0
    skipped_budget = 0
    secret_warnings: list[str] = []
    redacted_total = 0

    for f in candidates:
        content = read_text(f)
        if content is None:
            continue

        hits = scan_secrets(content)
        if hits:
            if args.redact:
                content, n = redact(content)
                redacted_total += n
            else:
                for label, snippet in hits:
                    secret_warnings.append(f"{f}: {label} ({snippet})")

        tok = estimate_tokens(content, args.tokenizer)
        if total_tokens + tok > args.max_tokens:
            skipped_budget += 1
            continue

        try:
            rel = f.relative_to(root if root.is_dir() else root.parent)
        except ValueError:
            rel = f
        lang = LANG_BY_EXT.get(f.suffix.lower(), "")
        body_parts.append(f"### {rel.as_posix()}\n\n```{lang}\n{content.rstrip()}\n```")
        included.append(f)
        total_tokens += tok

    tree = build_tree(included, root if root.is_dir() else root.parent)
    header = (
        f"# Context bundle: {root}\n\n"
        f"{len(included)} files, ~{human_int(total_tokens)} tokens "
        f"(tokenizer={args.tokenizer}, budget={human_int(args.max_tokens)}).\n\n"
        f"## File tree\n\n{tree}\n\n## Files\n"
    )
    bundle = header + "\n\n".join(body_parts) + "\n"

    if args.out:
        args.out.write_text(bundle, encoding="utf-8")
        print(f"Wrote {args.out} - {len(included)} files, ~{human_int(total_tokens)} tokens.", file=sys.stderr)
    else:
        sys.stdout.write(bundle)

    # Diagnostics always go to stderr so stdout stays a clean bundle for piping.
    if skipped_budget:
        print(f"note: {skipped_budget} file(s) skipped to stay under the "
              f"{human_int(args.max_tokens)}-token budget.", file=sys.stderr)
    if args.redact and redacted_total:
        print(f"redacted {redacted_total} secret(s) before packing.", file=sys.stderr)
    if secret_warnings:
        print(f"\nWARNING: {len(secret_warnings)} possible secret(s) included "
              f"(run with --redact to scrub):", file=sys.stderr)
        for w in secret_warnings[:20]:
            print(f"  - {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
