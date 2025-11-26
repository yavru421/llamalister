"""
Centralized exception classes for LlamaMachinery.
Contains APT (Algebraic Pipeline Theory) fatal error handling.
"""

import sys
import traceback
from typing import Type
from types import TracebackType


class APTFatalError(Exception):
    """
    APT Fatal Error - represents an unrecoverable algebraic discontinuity.
    Any exception that halts the current pipeline execution permanently.
    """
    pass


def strict_excepthook(exc_type: Type[BaseException], exc_value: BaseException, exc_tb: TracebackType) -> None:
    """
    Strict exception hook for APT fatal error handling.
    Prints fatal error message and full traceback, then exits with code 1.
    """
    print(f"\n❌ APT FATAL ERROR: {exc_type.__name__} – {exc_value}")
    traceback.print_exc()
    sys.exit(1)


def initialize_apt_fatal_mode() -> None:
    """
    Initialize APT fatal mode by setting the strict exception hook.
    Call this at the beginning of any APT pipeline or agent.
    """
    sys.excepthook = strict_excepthook
    print("⚙️ APT Fatal Mode Active: All exceptions are terminal.")


# Initialize fatal mode by default for this module
initialize_apt_fatal_mode()
