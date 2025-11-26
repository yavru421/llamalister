"""
System operations for AutonomousUserAgent.

This module handles system-level operations including command execution, system information, and process management.
"""

import os
import subprocess
import platform
import shutil
from . import BaseOperations, OperationResult


class SystemOperations(BaseOperations):
    """Handles system operations"""

    def run_command(self, command: str) -> OperationResult:
        """Run a shell command"""
        try:
            self._log_operation("run_command", command)

            if os.name == "nt":
                # Prefer PowerShell for Windows commands so pipeline syntax works.
                powershell = shutil.which("pwsh") or shutil.which("powershell")
                if powershell:
                    ps_args = [
                        powershell,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-Command",
                        command,
                    ]
                    result = subprocess.run(
                        ps_args,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                else:
                    result = subprocess.run(
                        command,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
            else:
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

            output = result.stdout
            if result.stderr:
                output += "\nSTDERR: " + result.stderr
            return OperationResult(True, f"Command executed successfully:\n{output}", output)
        except subprocess.TimeoutExpired:
            return OperationResult(False, "Command timed out")
        except Exception as e:
            return OperationResult(False, f"Error running command: {e}")

    def system_info(self) -> OperationResult:
        """Get system information"""
        try:
            self._log_operation("system_info")
            info = {
                "Platform": platform.platform(),
                "System": platform.system(),
                "Release": platform.release(),
                "Version": platform.version(),
                "Machine": platform.machine(),
                "Processor": platform.processor(),
                "Python Version": platform.python_version(),
                "Current Directory": os.getcwd(),
                "User": os.getenv('USER') or os.getenv('USERNAME')
            }
            result = "System Information:\n" + "\n".join(f"{k}: {v}" for k, v in info.items())
            return OperationResult(True, result, info)
        except Exception as e:
            return OperationResult(False, f"Error getting system info: {e}")

    def disk_space(self, path: str) -> OperationResult:
        """Get disk space information"""
        try:
            path = self._ensure_absolute_path(path)
            self._log_operation("disk_space", f"path={path}")

            # Use shutil.disk_usage for cross-platform compatibility
            total, used, free = shutil.disk_usage(path)

            result = f"Disk space for {path}:\nTotal: {total / (1024**3):.2f} GB\nUsed: {used / (1024**3):.2f} GB\nFree: {free / (1024**3):.2f} GB"
            return OperationResult(True, result, {"total": total, "used": used, "free": free})
        except Exception as e:
            return OperationResult(False, f"Error getting disk space: {e}")

    def memory_info(self) -> OperationResult:
        """Get system memory (RAM) information"""
        try:
            # Check if psutil is available
            try:
                import psutil
                HAS_PSUTIL = True
            except ImportError:
                HAS_PSUTIL = False

            if not HAS_PSUTIL:
                return OperationResult(False, "psutil not available - cannot get memory info. Install with: pip install psutil")

            self._log_operation("memory_info")
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024**3)
            available_gb = mem.available / (1024**3)
            used_gb = mem.used / (1024**3)
            free_gb = mem.free / (1024**3)
            percent_used = mem.percent

            result = (
                f"Memory Information:\n"
                f"  Total: {total_gb:.2f} GB\n"
                f"  Available: {available_gb:.2f} GB\n"
                f"  Used: {used_gb:.2f} GB ({percent_used}%)\n"
                f"  Free: {free_gb:.2f} GB"
            )
            info = {
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "free": mem.free,
                "percent": percent_used,
            }
            return OperationResult(True, result, info)
        except Exception as e:
            return OperationResult(False, f"Error getting memory info: {e}")

    def list_processes(self) -> OperationResult:
        """List running processes"""
        try:
            # Check if psutil is available
            try:
                import psutil
                HAS_PSUTIL = True
            except ImportError:
                HAS_PSUTIL = False

            if not HAS_PSUTIL:
                return OperationResult(False, "psutil not available - cannot list processes. Install with: pip install psutil")

            self._log_operation("list_processes")
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    processes.append(
                        f"PID {proc.info['pid']}: {proc.info['name']} "
                        f"(CPU: {proc.info['cpu_percent']:.1f}%, MEM: {proc.info['memory_percent']:.1f}%)"
                    )
                except:
                    continue

            result = f"Running processes ({len(processes)}):\n" + "\n".join(processes[:50])  # Limit output
            return OperationResult(True, result, processes)
        except Exception as e:
            return OperationResult(False, f"Error listing processes: {e}")

    def kill_process(self, pid: int) -> OperationResult:
        """Kill a process by PID"""
        try:
            try:
                import psutil
                HAS_PSUTIL = True
            except ImportError:
                HAS_PSUTIL = False

            if not HAS_PSUTIL:
                return OperationResult(False, "psutil not available - cannot kill processes. Install with: pip install psutil")

            self._log_operation("kill_process", f"pid={pid}")
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=5)
            return OperationResult(True, f"Process {pid} terminated successfully")
        except psutil.NoSuchProcess:
            return OperationResult(False, f"Process {pid} not found")
        except Exception as e:
            return OperationResult(False, f"Error killing process: {e}")

    def get_env(self, env_var: str) -> OperationResult:
        """Get environment variable"""
        try:
            self._log_operation("get_env", f"var={env_var}")
            value = os.getenv(env_var)
            if value is None:
                return OperationResult(False, f"Environment variable '{env_var}' not found")
            return OperationResult(True, f"{env_var}={value}", value)
        except Exception as e:
            return OperationResult(False, f"Error getting environment variable: {e}")

    def set_env(self, env_var: str, env_value: str) -> OperationResult:
        """Set environment variable"""
        try:
            self._log_operation("set_env", f"var={env_var}")
            os.environ[env_var] = env_value
            return OperationResult(True, f"Set {env_var}={env_value}")
        except Exception as e:
            return OperationResult(False, f"Error setting environment variable: {e}")

    def install_package(self, package: str) -> OperationResult:
        """Install a system package"""
        try:
            self._log_operation("install_package", f"package={package}")
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
            return OperationResult(True, f"Package installation result:\n{output}")
        except subprocess.TimeoutExpired:
            return OperationResult(False, "Package installation timed out")
        except Exception as e:
            return OperationResult(False, f"Error installing package: {e}")

    def run_pip(self, command: str) -> OperationResult:
        """Run pip command"""
        try:
            import sys
            self._log_operation("run_pip", f"command={command}")
            full_command = f'"{sys.executable}" -m pip {command}'
            result = subprocess.run(full_command, shell=True, capture_output=True, text=True, timeout=120)
            output = result.stdout
            if result.stderr:
                output += "\nSTDERR: " + result.stderr
            return OperationResult(True, f"Pip command result:\n{output}")
        except subprocess.TimeoutExpired:
            return OperationResult(False, "Pip command timed out")
        except Exception as e:
            return OperationResult(False, f"Error running pip: {e}")
