"""Public package interface for typo-guard."""

from .core import Diagnostic, Identifier, extract_identifiers, lint_file, lint_paths, lint_source, split_identifier

__version__ = "0.1.0"
__all__ = [
    "Diagnostic",
    "Identifier",
    "extract_identifiers",
    "lint_file",
    "lint_paths",
    "lint_source",
    "split_identifier",
]
