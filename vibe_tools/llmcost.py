"""llmcost - estimate how many tokens, and how much money, a prompt/file/repo
will cost across today's models BEFORE you send it.

Pain it solves (r/artificial, June 2026 - "Our AI bills are subsidised, and I
don't think many people have priced in what happens next", 221 pts / 208 cmt):
people fire huge prompts and whole codebases at LLMs with zero idea of the bill.

    echo "summarise this" | llmcost
    llmcost README.md src/
    llmcost --text "..." --output-tokens 800 --json

Token counts default to a fast offline heuristic (~4 chars/token). Pass
--tokenizer tiktoken for the exact cl100k_base count (if tiktoken is installed).
Prices live in pricing.json and are INDICATIVE - override with --pricing FILE.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ._common import estimate_tokens, human_int, iter_source_files, read_text

HERE = Path(__file__).resolve().parent
DEFAULT_PRICING = HERE.parent / "pricing.json"


def load_pricing(path: Path) -> dict[str, dict[str, float]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["models"] if "models" in data else data


def gather_input(args: argparse.Namespace) -> tuple[str, list[str]]:
    """Return (combined_text, list_of_source_labels)."""
    chunks: list[str] = []
    labels: list[str] = []

    if args.text:
        chunks.append(args.text)
        labels.append("<--text>")

    for path_arg in args.paths:
        p = Path(path_arg)
        if not p.exists():
            print(f"warning: {p} does not exist, skipping", file=sys.stderr)
            continue
        for f in iter_source_files(p):
            content = read_text(f)
            if content is None:
                continue
            chunks.append(content)
            labels.append(str(f))

    # If nothing was given on the command line, read stdin (pipe support).
    if not chunks and not sys.stdin.isatty():
        stdin_text = sys.stdin.read()
        if stdin_text.strip():
            chunks.append(stdin_text)
            labels.append("<stdin>")

    return "\n".join(chunks), labels


def estimate_costs(
    input_tokens: int,
    output_tokens: int,
    pricing: dict[str, dict[str, float]],
) -> list[dict]:
    rows = []
    for model, price in pricing.items():
        in_cost = input_tokens / 1_000_000 * price["input"]
        out_cost = output_tokens / 1_000_000 * price["output"]
        rows.append(
            {
                "model": model,
                "input_cost": in_cost,
                "output_cost": out_cost,
                "total": in_cost + out_cost,
            }
        )
    rows.sort(key=lambda r: r["total"])
    return rows


def render_table(rows: list[dict], input_tokens: int, output_tokens: int) -> str:
    width = max(len(r["model"]) for r in rows)
    lines = [
        f"{'model':<{width}}   {'in $':>9}   {'out $':>9}   {'total $':>10}",
        f"{'-' * width}   {'-' * 9}   {'-' * 9}   {'-' * 10}",
    ]
    for r in rows:
        lines.append(
            f"{r['model']:<{width}}   {r['input_cost']:>9.4f}   "
            f"{r['output_cost']:>9.4f}   {r['total']:>10.4f}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="llmcost",
        description="Estimate tokens + USD cost of a prompt/file/repo across models.",
    )
    ap.add_argument("paths", nargs="*", help="files or directories to price (also reads stdin)")
    ap.add_argument("--text", help="inline text to price")
    ap.add_argument(
        "--output-tokens",
        type=int,
        default=500,
        help="assumed completion size for the output-cost column (default: 500)",
    )
    ap.add_argument(
        "--tokenizer",
        choices=["heuristic", "tiktoken"],
        default="heuristic",
        help="token counter (default: heuristic ~4 chars/token, offline)",
    )
    ap.add_argument("--pricing", type=Path, default=DEFAULT_PRICING, help="pricing JSON override")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    text, labels = gather_input(args)
    if not text:
        ap.error("no input - pass text via --text, files/dirs, or pipe to stdin")

    input_tokens = estimate_tokens(text, args.tokenizer)
    rows = estimate_costs(input_tokens, args.output_tokens, load_pricing(args.pricing))

    if args.json:
        print(
            json.dumps(
                {
                    "input_tokens": input_tokens,
                    "output_tokens_assumed": args.output_tokens,
                    "tokenizer": args.tokenizer,
                    "sources": labels,
                    "estimates": rows,
                },
                indent=2,
            )
        )
        return 0

    src = f"{len(labels)} source(s)" if len(labels) != 1 else labels[0]
    print(f"Input: {human_int(input_tokens)} tokens from {src} "
          f"(tokenizer={args.tokenizer}); assuming {human_int(args.output_tokens)} output tokens\n")
    print(render_table(rows, input_tokens, args.output_tokens))
    print("\nPrices are INDICATIVE (pricing.json). Verify against provider pricing pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
