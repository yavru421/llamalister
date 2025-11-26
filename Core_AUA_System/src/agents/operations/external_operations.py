"""
External operations for AutonomousUserAgent.

This module handles external service operations including Git, GitHub, and archive operations.
"""

import os
import subprocess
import zipfile
from typing import List, Dict, Any
from . import BaseOperations, OperationResult


class ExternalOperations(BaseOperations):
    """Handles external service operations"""

    def install_package(self, package: str) -> OperationResult:
        """Install a system package"""
        try:
            self._log_operation("install_package", package)
            if os.name == 'nt':  # Windows
                # Try chocolatey first, then winget
                result = subprocess.run(f"choco install {package} -y", shell=True, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    result = subprocess.run(f"winget install {package}", shell=True, capture_output=True, text=True, timeout=300)
            else:  # Unix-like
                result = subprocess.run(f"sudo apt-get update && sudo apt-get install -y {package}", shell=True, capture_output=True, text=True, timeout=300)
            output = result.stdout
            if result.stderr:
                output += "\nSTDERR: " + result.stderr
            return OperationResult(True, f"Package installation result:\n{output}", output)
        except subprocess.TimeoutExpired:
            return OperationResult(False, "Package installation timed out")
        except Exception as e:
            return OperationResult(False, f"Error installing package: {e}")

    def run_pip(self, command: str) -> OperationResult:
        """Run pip command"""
        try:
            import sys
            self._log_operation("run_pip", command)
            full_command = f'"{sys.executable}" -m pip {command}'
            result = subprocess.run(full_command, shell=True, capture_output=True, text=True, timeout=120)
            output = result.stdout
            if result.stderr:
                output += "\nSTDERR: " + result.stderr
            return OperationResult(True, f"Pip command result:\n{output}", output)
        except subprocess.TimeoutExpired:
            return OperationResult(False, "Pip command timed out")
        except Exception as e:
            return OperationResult(False, f"Error running pip: {e}")

    def grep_search(self, pattern: str, file_path: str) -> OperationResult:
        """Search for pattern in files"""
        try:
            import re
            file_path = self._ensure_absolute_path(file_path)
            self._log_operation("grep_search", f"pattern={pattern}, path={file_path}")

            results = []
            if os.path.isfile(file_path):
                files = [file_path]
            else:
                files = []
                for root, _, files_in_dir in os.walk(file_path):
                    for file_in_dir in files_in_dir:
                        files.append(os.path.join(root, file_in_dir))

            for file in files[:50]:  # Limit to 50 files
                try:
                    with open(file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                        for i, line in enumerate(lines, 1):
                            if re.search(pattern, line):
                                results.append(f"{file}:{i}:{line.strip()}")
                except:
                    continue

            if results:
                return OperationResult(True, f"Search results for '{pattern}':\n" + "\n".join(results[:100]), results)  # Limit output
            else:
                return OperationResult(True, f"No matches found for pattern '{pattern}'")
        except Exception as e:
            return OperationResult(False, f"Error searching: {e}")

    def find_files(self, pattern: str, dir_path: str) -> OperationResult:
        """Find files matching pattern"""
        try:
            import glob
            dir_path = self._ensure_absolute_path(dir_path)
            self._log_operation("find_files", f"pattern={pattern}, path={dir_path}")

            matches = glob.glob(os.path.join(dir_path, pattern), recursive=True)
            if matches:
                return OperationResult(True, f"Files matching '{pattern}':\n" + "\n".join(matches[:50]), matches)  # Limit output
            else:
                return OperationResult(True, f"No files found matching '{pattern}'")
        except Exception as e:
            return OperationResult(False, f"Error finding files: {e}")

    def get_env(self, env_var: str) -> OperationResult:
        """Get environment variable"""
        try:
            self._log_operation("get_env", env_var)
            value = os.getenv(env_var)
            if value is None:
                return OperationResult(False, f"Environment variable '{env_var}' not found")
            return OperationResult(True, f"{env_var}={value}", value)
        except Exception as e:
            return OperationResult(False, f"Error getting environment variable: {e}")

    def set_env(self, env_var: str, env_value: str) -> OperationResult:
        """Set environment variable"""
        try:
            self._log_operation("set_env", f"{env_var}={env_value}")
            os.environ[env_var] = env_value
            return OperationResult(True, f"Set {env_var}={env_value}")
        except Exception as e:
            return OperationResult(False, f"Error setting environment variable: {e}")

    def zip_files(self, files: List[str], zip_path: str) -> OperationResult:
        """Create a zip archive"""
        try:
            zip_path = self._ensure_absolute_path(zip_path)
            self._log_operation("zip_files", f"files={len(files)}, zip={zip_path}")

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file in files:
                    file = self._ensure_absolute_path(file)
                    if os.path.isfile(file):
                        zipf.write(file, os.path.basename(file))
                    elif os.path.isdir(file):
                        for root, _, files_in_dir in os.walk(file):
                            for file_in_dir in files_in_dir:
                                full_path = os.path.join(root, file_in_dir)
                                arcname = os.path.relpath(full_path, os.path.dirname(file))
                                zipf.write(full_path, arcname)

            return OperationResult(True, f"Created zip archive {zip_path} with {len(files)} items")
        except Exception as e:
            return OperationResult(False, f"Error creating zip archive: {e}")

    def unzip_file(self, zip_path: str, destination: str) -> OperationResult:
        """Extract a zip archive"""
        try:
            zip_path = self._ensure_absolute_path(zip_path)
            destination = self._ensure_absolute_path(destination)
            self._log_operation("unzip_file", f"{zip_path} -> {destination}")

            with zipfile.ZipFile(zip_path, 'r') as zipf:
                zipf.extractall(destination)

            return OperationResult(True, f"Extracted {zip_path} to {destination}")
        except Exception as e:
            return OperationResult(False, f"Error extracting zip archive: {e}")

    def git_status(self, repo_path: str) -> OperationResult:
        """Get git status"""
        try:
            repo_path = self._ensure_absolute_path(repo_path)
            os.chdir(repo_path)
            self._log_operation("git_status", repo_path)
            result = subprocess.run("git status", shell=True, capture_output=True, text=True, timeout=30)
            return OperationResult(True, f"Git status for {repo_path}:\n{result.stdout}", result.stdout)
        except Exception as e:
            return OperationResult(False, f"Error getting git status: {e}")

    def git_add(self, files: List[str], repo_path: str) -> OperationResult:
        """Add files to git"""
        try:
            repo_path = self._ensure_absolute_path(repo_path)
            os.chdir(repo_path)
            file_list = " ".join(f'"{f}"' for f in files)
            self._log_operation("git_add", f"files={file_list}")
            result = subprocess.run(f"git add {file_list}", shell=True, capture_output=True, text=True, timeout=30)
            return OperationResult(True, f"Git add result:\n{result.stdout}", result.stdout)
        except Exception as e:
            return OperationResult(False, f"Error adding files to git: {e}")

    def git_commit(self, message: str, repo_path: str) -> OperationResult:
        """Commit changes to git"""
        try:
            repo_path = self._ensure_absolute_path(repo_path)
            os.chdir(repo_path)
            self._log_operation("git_commit", message)
            result = subprocess.run(f'git commit -m "{message}"', shell=True, capture_output=True, text=True, timeout=30)
            return OperationResult(True, f"Git commit result:\n{result.stdout}", result.stdout)
        except Exception as e:
            return OperationResult(False, f"Error committing to git: {e}")

    def git_push(self, repo_path: str) -> OperationResult:
        """Push changes to git remote"""
        try:
            repo_path = self._ensure_absolute_path(repo_path)
            os.chdir(repo_path)
            self._log_operation("git_push", repo_path)
            result = subprocess.run("git push", shell=True, capture_output=True, text=True, timeout=60)
            return OperationResult(True, f"Git push result:\n{result.stdout}", result.stdout)
        except Exception as e:
            return OperationResult(False, f"Error pushing to git: {e}")

    # GitHub operations (placeholder implementations)
    def github_create_issue(self, params: Dict[str, Any]) -> OperationResult:
        """Create a GitHub issue"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def github_add_issue_comment(self, params: Dict[str, Any]) -> OperationResult:
        """Add a comment to a GitHub issue"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def github_get_issue(self, params: Dict[str, Any]) -> OperationResult:
        """Get details of a GitHub issue"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def github_list_issues(self, params: Dict[str, Any]) -> OperationResult:
        """List GitHub issues"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def github_create_repository(self, params: Dict[str, Any]) -> OperationResult:
        """Create a new GitHub repository"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def github_get_repository(self, params: Dict[str, Any]) -> OperationResult:
        """Get details of a GitHub repository"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def github_create_branch(self, params: Dict[str, Any]) -> OperationResult:
        """Create a new branch in a GitHub repository"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def github_create_pull_request(self, params: Dict[str, Any]) -> OperationResult:
        """Create a pull request in a GitHub repository"""
        return OperationResult(False, "GitHub operations not implemented in modular version")

    def create_ps1_script(self, script_path: str, content: str) -> OperationResult:
        """Create a PowerShell script file"""
        try:
            self._log_operation("create_ps1_script", script_path)
            # Ensure the script has .ps1 extension
            if not script_path.lower().endswith('.ps1'):
                script_path += '.ps1'

            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return OperationResult(True, f"PowerShell script created successfully: {script_path}")
        except Exception as e:
            return OperationResult(False, f"Error creating PowerShell script: {e}")

    def run_ps1_script(self, script_path: str, background: bool = False, parameters: str = "") -> OperationResult:
        """Execute a PowerShell script"""
        try:
            self._log_operation("run_ps1_script", script_path)

            # Ensure the script has .ps1 extension
            if not script_path.lower().endswith('.ps1'):
                script_path += '.ps1'

            # Build the PowerShell command
            command = f'powershell -ExecutionPolicy Bypass -File "{script_path}"'
            if parameters:
                command += f" {parameters}"

            if background:
                # Run in background
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return OperationResult(True, f"PowerShell script started in background: {script_path} (PID: {process.pid})")
            else:
                # Run synchronously
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=300)
                output = result.stdout
                if result.stderr:
                    output += "\nSTDERR: " + result.stderr

                if result.returncode == 0:
                    return OperationResult(True, f"PowerShell script executed successfully:\n{output}")
                else:
                    return OperationResult(False, f"PowerShell script failed (exit code {result.returncode}):\n{output}")

        except subprocess.TimeoutExpired:
            return OperationResult(False, "PowerShell script execution timed out")
        except Exception as e:
            return OperationResult(False, f"Error running PowerShell script: {e}")

    def create_and_run_ps1_script(self, script_path: str, content: str, background: bool = False, parameters: str = "") -> OperationResult:
        """Create and immediately execute a PowerShell script"""
        try:
            self._log_operation("create_and_run_ps1_script", script_path)

            # First create the script
            create_result = self.create_ps1_script(script_path, content)
            if not create_result.success:
                return create_result

            # Then run it
            run_result = self.run_ps1_script(script_path, background, parameters)
            return OperationResult(
                run_result.success,
                f"Created and executed PowerShell script:\n{create_result.message}\n{run_result.message}"
            )

        except Exception as e:
            return OperationResult(False, f"Error in create and run operation: {e}")