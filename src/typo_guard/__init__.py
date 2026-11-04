"""typo-guard: an AST-powered spellchecker linter for Python identifiers.

Quick start::

    from typo_guard import lint_source

    for issue in lint_source("recieved_data = 1", filename="demo.py"):
        print(issue.location, issue.word, issue.suggestions)
"""

from .core import (
    DEFAULT_ALLOWLIST,
    DEFAULT_EXCLUDES,
    Diagnostic,
    Identifier,
    extract_identifiers,
    iter_python_files,
    lint_file,
    lint_paths,
    lint_source,
    read_source,
    split_identifier,
)
from .runner import FileError, ScanResult, scan_paths

__version__ = "0.2.0"

__all__ = [
    "DEFAULT_ALLOWLIST",
    "DEFAULT_EXCLUDES",
    "Diagnostic",
    "FileError",
    "Identifier",
    "ScanResult",
    "__version__",
    "extract_identifiers",
    "iter_python_files",
    "lint_file",
    "lint_paths",
    "lint_source",
    "read_source",
    "scan_paths",
    "split_identifier",
]
