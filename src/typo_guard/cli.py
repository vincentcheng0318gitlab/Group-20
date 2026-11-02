"""Command-line interface for typo-guard."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .core import lint_paths


def _load_allowlist(path: str | None, inline_words: Sequence[str]) -> set[str]:
    words = {word.lower() for word in inline_words}
    if path:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            clean = line.partition("#")[0].strip().lower()
            if clean:
                words.add(clean)
    return words


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="typo-guard",
        description="Find likely spelling mistakes in Python identifiers.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    lint = subparsers.add_parser("lint", help="lint Python files or directories")
    lint.add_argument("paths", nargs="+", help="Python files or directories")
    lint.add_argument("--format", choices=("text", "json"), default="text")
    lint.add_argument("--allow", action="append", default=[], metavar="WORD")
    lint.add_argument("--allowlist", metavar="FILE", help="one accepted word per line")
    lint.add_argument("--max-suggestions", type=int, default=3, metavar="N")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        missing = [path for path in args.paths if not Path(path).exists()]
        if missing:
            print(f"typo-guard: path not found: {missing[0]}", file=sys.stderr)
            return 2
        allow_words = _load_allowlist(args.allowlist, args.allow)
        diagnostics = lint_paths(
            args.paths,
            allow_words=allow_words,
            max_suggestions=max(0, args.max_suggestions),
        )
    except (OSError, UnicodeError, SyntaxError, RuntimeError) as error:
        print(f"typo-guard: {error}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps([item.to_dict() for item in diagnostics], indent=2))
    else:
        for diagnostic in diagnostics:
            print(diagnostic.format_text())
        print(f"Found {len(diagnostics)} possible typo(s).")
    return 1 if diagnostics else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
