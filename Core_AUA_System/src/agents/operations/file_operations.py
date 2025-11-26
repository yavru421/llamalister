"""
File operations for AutonomousUserAgent.

This module handles all file system operations including create, read, edit, delete, move, and copy.
"""

import os
import shutil
from . import BaseOperations, OperationResult


class FileOperations(BaseOperations):
    """Handles file system operations"""

    def create_file(self, file_path: str, content: str) -> OperationResult:
        """Create a new file with content"""
        try:
            file_path = self._ensure_absolute_path(file_path)
            self._log_operation("create_file", f"path={file_path}")

            with open(file_path, 'w') as f:
                f.write(content)

            return OperationResult(True, f"File {file_path} created successfully")
        except Exception as e:
            return OperationResult(False, f"Error creating file: {e}")

    def read_file(self, file_path: str) -> OperationResult:
        """Read and return file content"""
        try:
            file_path = self._ensure_absolute_path(file_path)

            if not os.path.exists(file_path):
                return OperationResult(False, f"File {file_path} does not exist")

            self._log_operation("read_file", f"path={file_path}")

            with open(file_path, 'r') as f:
                content = f.read()

            return OperationResult(True, f"File content:\n{content}", content)
        except Exception as e:
            return OperationResult(False, f"Error reading file: {e}")

    def edit_file(self, file_path: str, old_string: str, new_string: str) -> OperationResult:
        """Edit a file by replacing old_string with new_string"""
        try:
            file_path = self._ensure_absolute_path(file_path)

            if not os.path.exists(file_path):
                return OperationResult(False, f"File {file_path} does not exist")

            self._log_operation("edit_file", f"path={file_path}")

            with open(file_path, 'r') as f:
                content = f.read()

            if old_string not in content:
                return OperationResult(False, f"Old string '{old_string}' not found in file")

            new_content = content.replace(old_string, new_string, 1)

            with open(file_path, 'w') as f:
                f.write(new_content)

            return OperationResult(True, f"File {file_path} edited successfully")
        except Exception as e:
            return OperationResult(False, f"Error editing file: {e}")

    def delete_file(self, file_path: str) -> OperationResult:
        """Delete a file"""
        try:
            file_path = self._ensure_absolute_path(file_path)

            if not os.path.exists(file_path):
                return OperationResult(False, f"File {file_path} does not exist")

            self._log_operation("delete_file", f"path={file_path}")
            os.remove(file_path)

            return OperationResult(True, f"File {file_path} deleted successfully")
        except Exception as e:
            return OperationResult(False, f"Error deleting file: {e}")

    def move_file(self, source: str, destination: str) -> OperationResult:
        """Move/rename a file or directory"""
        try:
            source = self._ensure_absolute_path(source)
            destination = self._ensure_absolute_path(destination)

            if not os.path.exists(source):
                return OperationResult(False, f"Source {source} does not exist")

            self._log_operation("move_file", f"{source} -> {destination}")
            shutil.move(source, destination)

            return OperationResult(True, f"Moved {source} to {destination} successfully")
        except Exception as e:
            return OperationResult(False, f"Error moving file: {e}")

    def copy_file(self, source: str, destination: str) -> OperationResult:
        """Copy a file or directory"""
        try:
            source = self._ensure_absolute_path(source)
            destination = self._ensure_absolute_path(destination)

            if not os.path.exists(source):
                return OperationResult(False, f"Source {source} does not exist")

            self._log_operation("copy_file", f"{source} -> {destination}")

            if os.path.isdir(source):
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)

            return OperationResult(True, f"Copied {source} to {destination} successfully")
        except Exception as e:
            return OperationResult(False, f"Error copying file: {e}")