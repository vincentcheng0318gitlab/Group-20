"""Fault-tolerant scanning of many files.

:func:`typo_guard.core.lint_paths` stops at the first bad file, which is the
right contract for a library call.  A command-line run over a whole project
should instead report *every* finding and *every* unreadable file, so this
module wraps the unchanged engine with per-file error collection.
"""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from .core import Diagnostic, PathLike, iter_python_files, lint_file

# tokenize.open() reports undecodable files / bad coding cookies as SyntaxError.
_ENCODING_PROBLEM = re.compile(r"encoding declaration|encoding problem|unknown encoding")
_FOR_FILENAME = re.compile(r"\s+for\s+'[^']*'")
_ENCODING_HINT = "save it as UTF-8 or add a '# -*- coding: ... -*-' line"


@dataclass(frozen=True)
class FileError:
    """A file (or directory) that could not be analysed."""

    path: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None

    @property
    def location(self) -> str:
        parts = [self.path]
        if self.line:
            parts.append(str(self.line))
            if self.column:
                parts.append(str(self.column))
        return ":".join(parts)

    def format_text(self) -> str:
        return f"{self.location}: {self.message}"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ScanResult:
    """Everything a reporter needs to describe one run."""

    files: List[str] = field(default_factory=list)
    diagnostics: List[Diagnostic] = field(default_factory=list)
    errors: List[FileError] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def affected_files(self) -> int:
        return len({item.path for item in self.diagnostics})

    @property
    def affected_identifiers(self) -> int:
        return len({(item.path, item.line, item.column, item.identifier) for item in self.diagnostics})


def describe_error(path: PathLike, error: BaseException) -> FileError:
    """Turn an exception raised while reading/parsing ``path`` into a message."""
    name = os.fspath(path)
    if isinstance(error, SyntaxError):
        message = error.msg or "invalid syntax"
        if _ENCODING_PROBLEM.search(message):
            return FileError(name, f"cannot decode file: {_FOR_FILENAME.sub('', message)} ({_ENCODING_HINT})")
        line = error.lineno if isinstance(error.lineno, int) and error.lineno > 0 else None
        column = error.offset if line and isinstance(error.offset, int) and error.offset > 0 else None
        return FileError(name, f"syntax error: {message}", line, column)
    if isinstance(error, UnicodeDecodeError):
        return FileError(
            name,
            f"cannot decode file as {error.encoding} at byte {error.start} ({_ENCODING_HINT})",
        )
    if isinstance(error, OSError):
        reason = error.strerror or str(error) or type(error).__name__
        return FileError(os.fspath(error.filename) if error.filename else name, reason)
    return FileError(name, str(error) or type(error).__name__)


def scan_paths(
    paths: Sequence[PathLike],
    *,
    allow_words: Iterable[str] = (),
    max_suggestions: int = 3,
    exclude: Optional[Iterable[str]] = None,
) -> ScanResult:
    """Lint every Python file under ``paths``, collecting errors per file."""
    result = ScanResult()
    allow = tuple(allow_words) if not isinstance(allow_words, str) else (allow_words,)

    for raw_path in paths:
        candidate = Path(raw_path)
        if candidate.is_file() and candidate.suffix != ".py":
            result.skipped.append(os.fspath(raw_path))

    walk_errors: List[OSError] = []
    files = sorted(
        iter_python_files(paths, exclude=exclude, on_error=walk_errors.append),
        key=lambda item: str(item),
    )
    result.errors.extend(describe_error(error.filename or "<directory>", error) for error in walk_errors)

    for path in files:
        result.files.append(str(path))
        try:
            result.diagnostics.extend(
                lint_file(path, allow_words=allow, max_suggestions=max_suggestions)
            )
        except (OSError, UnicodeError, SyntaxError, ValueError) as error:
            result.errors.append(describe_error(path, error))
    return result
