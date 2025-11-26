"""
Directory operations for AutonomousUserAgent.

This module handles directory-related operations including list, create, and delete.
"""

import os
from . import BaseOperations, OperationResult


class DirectoryOperations(BaseOperations):
    """Handles directory operations"""

    def list_dir(self, dir_path: str) -> OperationResult:
        """List directory contents"""
        try:
            dir_path = self._ensure_absolute_path(dir_path)

            if not os.path.exists(dir_path):
                return OperationResult(False, f"Directory {dir_path} does not exist")

            self._log_operation("list_dir", f"path={dir_path}")
            items = os.listdir(dir_path)

            result = f"Contents of {dir_path}:\n"
            for item in sorted(items):
                full_path = os.path.join(dir_path, item)
                item_type = "DIR" if os.path.isdir(full_path) else "FILE"
                result += f"[{item_type}] {item}\n"

            return OperationResult(True, result, items)
        except Exception as e:
            return OperationResult(False, f"Error listing directory: {e}")

    def create_dir(self, dir_path: str) -> OperationResult:
        """Create a directory"""
        try:
            dir_path = self._ensure_absolute_path(dir_path)
            self._log_operation("create_dir", f"path={dir_path}")

            os.makedirs(dir_path, exist_ok=True)
            return OperationResult(True, f"Directory {dir_path} created successfully")
        except Exception as e:
            return OperationResult(False, f"Error creating directory: {e}")

    def delete_dir(self, dir_path: str) -> OperationResult:
        """Delete a directory"""
        try:
            dir_path = self._ensure_absolute_path(dir_path)

            if not os.path.exists(dir_path):
                return OperationResult(False, f"Directory {dir_path} does not exist")

            self._log_operation("delete_dir", f"path={dir_path}")
            import shutil
            shutil.rmtree(dir_path)

            return OperationResult(True, f"Directory {dir_path} deleted successfully")
        except Exception as e:
            return OperationResult(False, f"Error deleting directory: {e}")