"""
Base operations module for AutonomousUserAgent operations.

This module provides base classes and common functionality for all operation modules.
"""

import os
import logging
from typing import Any, Optional


class OperationResult:
    """Standardized result container for operations"""

    def __init__(self, success: bool, message: str, data: Optional[Any] = None, progress: Optional[list] = None):
        self.success = success
        self.message = message
        self.data = data
        self.progress = progress or []

    def add_progress(self, message: str, percent: Optional[float] = None) -> None:
        """Append a progress update to the result's progress list."""
        self.progress.append({"message": message, "percent": percent})

    def __str__(self):
        return self.message


class BaseOperations:
    """Base class for operation modules"""

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._progress_callback = None

    def set_progress_callback(self, callback):
        """Set a callable that receives progress updates. The callable should accept (message, percent)."""
        self._progress_callback = callback

    def report_progress(self, message: str, percent: Optional[float] = None) -> None:
        """Log progress locally and call the configured callback if present."""
        try:
            self.logger.info(f"PROGRESS: {percent if percent is not None else ''} - {message}")
        except Exception:
            # Ensure this cannot crash operation code due to logging errors
            pass
        if getattr(self, "_progress_callback", None):
            try:
                self._progress_callback(message, percent)
            except Exception:
                self.logger.exception("Progress callback failed")

    def _ensure_absolute_path(self, path: str) -> str:
        """Ensure a path is absolute, making it relative to current directory if not"""
        if not os.path.isabs(path):
            return os.path.join(os.getcwd(), path)
        return path

    def _log_operation(self, operation: str, details: Optional[str] = None):
        """Log an operation with optional details"""
        if details:
            self.logger.info(f"{operation}: {details}")
        else:
            self.logger.info(operation)
