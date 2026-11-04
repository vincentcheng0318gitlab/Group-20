"""Command-line interface for typo-guard."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import __version__
from .core import DEFAULT_EXCLUDES
from .report import (
    make_console,
    render_errors,
    render_json,
    render_message,
    render_table,
    render_text,
)
from .runner import scan_paths

EXIT_CLEAN = 0
EXIT_TYPOS = 1
EXIT_ERROR = 2
EXIT_INTERRUPTED = 130

_WORD_SEPARATORS = re.compile(r"[\s,]+")


class AllowlistError(Exception):
    """The allowlist file is missing, not a file, or not readable text."""


def _split_words(text: str) -> list[str]:
    return [word.lower() for word in _WORD_SEPARATORS.split(text.strip()) if word]


def _load_allowlist(path: Optional[str], inline_words: Iterable[str]) -> set[str]:
    """Merge ``--allow`` words with an allowlist file (one or more words per line)."""
    words: set[str] = set()
    for item in inline_words:
        words.update(_split_words(item))
    if path:
        file = Path(path)
        if not file.exists():
            raise AllowlistError(f"allowlist file not found: {path}")
        if not file.is_file():
            raise AllowlistError(f"allowlist is not a regular file: {path}")
        try:
            text = file.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise AllowlistError(f"allowlist must be UTF-8 text: {path}") from error
        except OSError as error:
            raise AllowlistError(f"cannot read allowlist {path}: {error.strerror or error}") from error
        for line in text.splitlines():
            words.update(_split_words(line.partition("#")[0]))
    return words


def _non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="typo-guard",
        description=(
            "Find likely spelling mistakes in Python identifiers "
            "(variables, arguments, functions and classes)."
        ),
        epilog="Example: typo-guard lint src tests --allow numpy",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    lint = subparsers.add_parser(
        "lint",
        help="lint Python files or directories",
        description=(
            "Parse Python files with the ast module, split identifier names into "
            "words and report words missing from the offline English dictionary. "
            "Strings, comments and attribute accesses are never inspected."
        ),
    )
    lint.add_argument(
        "paths", nargs="+", metavar="PATH",
        help="Python files or directories (directories are scanned recursively)",
    )
    lint.add_argument(
        "--format", choices=("table", "text", "json"), default="table",
        help="output style: table (default), text (one line per finding) or json",
    )
    lint.add_argument(
        "--allow", action="append", default=[], metavar="WORD",
        help="accept WORD as correctly spelled (repeatable, comma-separated lists allowed)",
    )
    lint.add_argument(
        "--allowlist", metavar="FILE",
        help="file of accepted words, one per line; text after '#' is ignored",
    )
    lint.add_argument(
        "--max-suggestions", type=_non_negative_int, default=3, metavar="N",
        help="maximum suggestions per typo (default: 3; 0 hides suggestions)",
    )
    lint.add_argument(
        "--exclude", action="append", default=[], metavar="PATTERN",
        help=(
            "extra directory/file name pattern to skip while recursing, e.g. "
            "'migrations' or '*_pb2.py' (repeatable; .venv, build, __pycache__ ... "
            "are skipped by default)"
        ),
    )
    lint.add_argument(
        "--color", choices=("auto", "always", "never"), default="auto",
        help="colourise the table (default: auto)",
    )
    lint.add_argument(
        "--no-color", dest="color", action="store_const", const="never",
        help="shorthand for --color never",
    )
    lint.add_argument(
        "--exit-zero", action="store_true",
        help="exit with 0 even when typos are found (file errors still exit with 2)",
    )
    return parser


def _make_streams_safe() -> None:
    """Never crash with UnicodeEncodeError on legacy (non-UTF) consoles."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if reconfigure is not None and not encoding.startswith("utf"):
            try:
                reconfigure(errors="replace")
            except (AttributeError, OSError, ValueError):  # pragma: no cover
                pass


def _silence_stdout() -> None:
    """After a broken pipe (e.g. ``| head``) stop Python's flush-at-exit error."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError, AttributeError):
        pass


def _run_lint(args: argparse.Namespace) -> int:
    errors_out = make_console(stderr=True, color=args.color)

    missing = [path for path in args.paths if not Path(path).exists()]
    if missing:
        for path in missing:
            render_message(errors_out, "error", f"path not found: {path}")
        return EXIT_ERROR

    try:
        allow_words = _load_allowlist(args.allowlist, args.allow)
    except AllowlistError as error:
        render_message(errors_out, "error", str(error))
        return EXIT_ERROR

    result = scan_paths(
        args.paths,
        allow_words=allow_words,
        max_suggestions=args.max_suggestions,
        exclude=(*DEFAULT_EXCLUDES, *args.exclude),
    )

    for path in result.skipped:
        render_message(errors_out, "warning", f"skipped {path} (not a .py file)")
    if not result.files and not result.errors:
        render_message(errors_out, "warning", "no Python files found in the given path(s)")
    render_errors(result.errors, errors_out)

    if args.format == "json":
        print(render_json(result))
    elif args.format == "text":
        print(render_text(result))
    else:
        render_table(result, make_console(color=args.color))
    sys.stdout.flush()

    if result.errors:
        return EXIT_ERROR
    if result.diagnostics and not args.exit_zero:
        return EXIT_TYPOS
    return EXIT_CLEAN


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Console-script entry point; returns the process exit code."""
    _make_streams_safe()
    args = build_parser().parse_args(argv)
    try:
        return _run_lint(args)
    except KeyboardInterrupt:
        print("typo-guard: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    except BrokenPipeError:
        _silence_stdout()
        return EXIT_TYPOS
    except Exception as error:  # last-resort guard: never show a raw traceback
        if os.environ.get("TYPO_GUARD_DEBUG"):
            raise
        print(
            f"typo-guard: internal error: {type(error).__name__}: {error} "
            "(set TYPO_GUARD_DEBUG=1 for a traceback)",
            file=sys.stderr,
        )
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
