import glob
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Strict mode injector
try:
    import strict_mode  # noqa: F401 - activate strict mode
except ImportError:
    print("[APT FATAL ERROR] strict_mode module not found")
    sys.exit(1)

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Optional imports - handle gracefully if not available

# Optional imports - handle gracefully if not available
try:
    import psutil

    has_psutil = True
except ImportError:
    has_psutil = False

try:
    import requests

    has_requests = True
except ImportError:
    has_requests = False

# Local imports with fallbacks
try:
    from .base_agent import BaseAgent
except ImportError:
    from agents.base_agent import BaseAgent

try:
    from ..llm_client import get_llm_client
except ImportError:
    from llm_client import get_llm_client

try:
    from ..memory_service import get_memory_service, start_session, end_session
except ImportError:
    from memory_service import get_memory_service, start_session, end_session

# Import APT engine
try:
    sys.path.insert(0, os.path.join(ROOT_DIR, "apt_engine"))
    sys.path.insert(0, os.path.join(ROOT_DIR, "apt_engine", "engine"))
    from engine import APTEngine
except ImportError:
    APTEngine = None

try:
    from .operations.directory_operations import DirectoryOperations
    from .operations.external_operations import ExternalOperations
    from .operations.file_operations import FileOperations
    from .operations.llamamachinery_operations import LlamaMachineryOperations
    from .operations.network_operations import NetworkOperations
    from .operations.system_operations import SystemOperations
except ImportError:
    # Fallback imports if relative imports fail
    from operations.directory_operations import DirectoryOperations
    from operations.external_operations import ExternalOperations
    from operations.file_operations import FileOperations
    from operations.llamamachinery_operations import LlamaMachineryOperations
    from operations.network_operations import NetworkOperations
    from operations.system_operations import SystemOperations

gui_import_error = None
try:
    from .operations.gui_operations import GuiOperations
except ModuleNotFoundError as exc:
    if exc.name == "tkinter":
        GuiOperations = None
        gui_import_error = exc
    else:
        raise


class AutonomousUserAgent(BaseAgent):
    """
    Special agent that operates autonomously outside of Llama machinery,
    acting as a user and bridging between user and machine.
    Can perform all user-permitted actions.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(
            config
            or {
                "name": "AutonomousUserAgent",
                "description": "Autonomous agent that acts as a user, performing all user actions",
            }
        )
        self.llm_client = get_llm_client(self.config)

        # Initialize memory service
        self.memory_service = get_memory_service()
        self.current_session_id = None

        # Initialize APT engine
        if APTEngine:
            schema_path = os.path.join(ROOT_DIR, "apt_engine", "engine", "contracts", "apt_schema.json")
            self.apt_engine = APTEngine(schema_path)
            self.apt_pipeline_id = None
        else:
            self.apt_engine = None

        # Initialize operation modules up-front so execute_action can run safely
        self.file_ops = FileOperations()
        self.dir_ops = DirectoryOperations()
        self.sys_ops = SystemOperations()
        self.net_ops = NetworkOperations()
        self.ext_ops = ExternalOperations()
        self.llama_ops = LlamaMachineryOperations()
        self.gui_ops = GuiOperations() if GuiOperations else None
        self.gui_import_error = gui_import_error

        # Load Raspberry Pi configurations
        self.pi_configs = self._load_pi_configs()

        if self.gui_ops is None and self.gui_import_error:
            self.logger.warning("GUI operations disabled: %s", self.gui_import_error)

    def end_session(self):
        """End the current session"""
        if self.current_session_id:
            end_session(self.current_session_id)
            self.current_session_id = None

    def train_from_history(self, days_back: int = 30) -> Dict[str, Any]:
        """Train the agent from interaction history"""
        return self.memory_service.train_from_history(days_back)

    def get_training_stats(self) -> Dict[str, Any]:
        """Get training and learning statistics"""
        return self.memory_service.get_training_stats()

    def learn_from_success(
        self,
        user_input: str,
        agent_response: str,
        actions_taken: Optional[List[Dict[str, Any]]] = None,
    ):
        """Learn from successful interactions"""
        interaction_data = {
            "user_input": user_input,
            "agent_response": agent_response,
            "success": True,
            "interaction_type": "training",
            "actions_executed": actions_taken or [],
        }
        self.memory_service.learn_from_interaction(interaction_data)

    def self_diagnose(self, tor_url: Optional[str] = None, proxy_host: str = "127.0.0.1", proxy_port: int = 9050, remote_memory_url: Optional[str] = None) -> str:
        """Self-diagnose the agent: check memory service, LLM connectivity, system state, and optionally try to connect to a Tor memory server.

        Returns:
            A human-readable summary of the diagnostic checks and any remote connection attempts.
        """
        results = []

        # 1. System info
        try:
            sys_info = self.sys_ops.system_info()
            results.append(f"System Info: {sys_info.message}")
        except Exception as e:
            self.logger.error("Failed to gather system info: %s", e)
            results.append(f"System Info: ERROR - {e}")

        # 2. Memory service: stats & db file existence
        try:
            stats = self.memory_service.get_stats()
            results.append(f"Memory Service Stats: {stats}")

            # Check if the DB file exists
            try:
                db_path = self.memory_service.db_path
                db_exists = os.path.exists(db_path)
                results.append(f"Memory DB: {db_path} exists={db_exists}")
            except Exception:
                results.append("Memory DB: path check failed")
        except Exception as e:
            results.append(f"Memory Service: ERROR - {e}")

        # 3. LLM connectivity (basic ping)
        try:
            sample_prompt = "Ping: Please respond with OK"
            ping_resp = self.llm_client.generate(sample_prompt, max_tokens=5, temperature=0.0)
            results.append(f"LLM Client: reachable (sample response length {len(ping_resp)})")
        except Exception as e:
            results.append(f"LLM Client: ERROR - {e}")

        # 4. Tor proxy/process check
        tor_running = False
        if has_psutil:
            try:
                for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
                    name = (proc.info.get('name') or '').lower()
                    cmdline = ' '.join(proc.info.get('cmdline') or [])
                    if 'tor' in name or 'tor' in cmdline:
                        tor_running = True
                        break
            except Exception:
                # psutil errors shouldn't break the diagnosis
                tor_running = False
        else:
            # Fallback: check for 'tor' using shell commands
            try:
                res = self.sys_ops.run_command('tor --version' if os.name != 'nt' else 'tor --version')
                if 'Tor' in res.message:
                    tor_running = True
            except Exception:
                tor_running = False

        results.append(f"Tor Process: {'running' if tor_running else 'not detected'}")

        # 5. Try connecting to the provided Tor memory server (if available)
        if tor_url:
            try:
                connect_result = self.net_ops.connect_to_tor_memory_server(tor_url, proxy_host, proxy_port)
                results.append(f"Tor Memory Server: {connect_result.message}")
                # save to memory about the last tor test
                self.memory_service.log_interaction(
                    interaction_type="internal",
                    method="self_diagnose",
                    user_input=f"Tor test to {tor_url}",
                    agent_response=connect_result.message,
                    session_id=self.current_session_id,
                    success=connect_result.success,
                )
            except Exception as e:
                results.append(f"Tor Memory Server: ERROR - {e}")

        # 6. Try connecting to remote memory server (if URL provided in env or params)
        remote_url = remote_memory_url or os.environ.get("REMOTE_MEMORY_SERVER_URL")
        if remote_url:
            try:
                remote_result = self.memory_service.connect_to_remote_memory_server(remote_url)
                if remote_result["success"]:
                    results.append(f"Remote Memory Server: Connected successfully. Data length: {len(str(remote_result['data']))}")
                    # Sync the data into local DB
                    sync_result = self.memory_service.sync_remote_graph(remote_url)
                    if sync_result["success"]:
                        results.append(f"Remote Graph Synced: {sync_result['synced_count']} edges")
                    else:
                        results.append(f"Remote Graph Sync Failed: {sync_result.get('error', 'Unknown error')}")
                else:
                    results.append(f"Remote Memory Server: {remote_result['error']}")
                # Log the remote connection attempt
                self.memory_service.log_interaction(
                    interaction_type="internal",
                    method="self_diagnose",
                    user_input=f"Remote memory test to {remote_url}",
                    agent_response=str(remote_result),
                    session_id=self.current_session_id,
                    success=remote_result["success"],
                )
            except Exception as e:
                results.append(f"Remote Memory Server: ERROR - {e}")
        else:
            results.append("Remote Memory Server: No URL provided. Set REMOTE_MEMORY_SERVER_URL env var or pass via parameters.")

        # Log overall result
        result_text = "\n".join(results)
        self.memory_service.log_interaction(
            interaction_type="internal",
            method="self_diagnose",
            user_input="self_diagnose",
            agent_response=result_text,
            session_id=self.current_session_id,
            success=True,
        )

        return result_text

    def query_remote_graph(self, source: Optional[str] = None, target: Optional[str] = None, edge_type: Optional[str] = None) -> str:
        """Query the synced remote graph data."""
        edges = self.memory_service.get_remote_graph_edges(source, target, edge_type)
        if not edges:
            return "No matching edges found in remote graph."

        result = f"Found {len(edges)} edges:\n"
        for edge in edges[:20]:  # Limit output
            result += f"- {edge['source']} --({edge['type']})--> {edge['target']}"
            if edge.get('strength'):
                result += f" [strength: {edge['strength']}]"
            if edge.get('purpose'):
                result += f" [purpose: {edge['purpose']}]"
            result += "\n"
        if len(edges) > 20:
            result += f"... and {len(edges) - 20} more"
        return result

    def get_project_context(self, project_name: str) -> str:
        """Get comprehensive context for a project."""
        context = self.memory_service.get_project_context(project_name)

        result = f"Project Context for '{project_name}':\n"
        result += f"  Workspace: {context['workspace'] or 'Unknown'}\n"
        result += f"  Related Projects: {', '.join(context['related_projects']) or 'None'}\n"
        result += f"  Resources Used: {', '.join([r['resource'] for r in context['resources']]) or 'None'}\n"

        if context['resources']:
            result += "  Resource Details:\n"
            for resource in context['resources']:
                result += f"    - {resource['resource']}"
                if resource.get('purpose'):
                    result += f" (purpose: {resource['purpose']})"
                result += "\n"

        return result

    def get_workspace_overview(self) -> str:
        """Get overview of all workspaces."""
        overview = self.memory_service.get_workspace_overview()

        result = "Workspace Overview:\n"
        for workspace, data in overview.items():
            result += f"\n{workspace}:\n"
            result += f"  Projects: {', '.join(data['projects'])}\n"
            if data['configurations']:
                result += f"  Configurations: {', '.join(data['configurations'])}\n"

        return result

    def _get_graph_context(self, task_text):
        """Proactively query knowledge graph for relevant context based on user input."""
        try:
            # Check if input mentions projects, workspaces, or relationships
            task_lower = task_text.lower()

            # Keywords that trigger graph queries
            project_keywords = ['project', 'workspace', 'llamamachinery', 'nexus', 'smart-contract', 'forge', 'foundry']
            relationship_keywords = ['related', 'connect', 'link', 'dependency', 'relationship', 'context']

            should_query_graph = any(keyword in task_lower for keyword in project_keywords + relationship_keywords)

            if not should_query_graph:
                return None

            # Get workspace overview if workspace mentioned
            if 'workspace' in task_lower or 'llamamachinery' in task_lower:
                overview = self.memory_service.get_workspace_overview()
                if overview:
                    return f"WORKSPACE OVERVIEW:\n{overview}"

            # Get project context for specific projects
            if 'llamamachinery' in task_lower:
                context = self.memory_service.get_project_context('llamamachinery')
                if context and (context.get('workspace') or context.get('related_projects') or context.get('purpose')):
                    return f"LLAMAMACHINERY PROJECT CONTEXT:\n{self._format_project_context(context)}"

            if 'nexus' in task_lower or 'smart-contract' in task_lower:
                context = self.memory_service.get_project_context('nexus')
                if context and (context.get('workspace') or context.get('related_projects') or context.get('purpose')):
                    return f"NEXUS SMART CONTRACT PROJECT CONTEXT:\n{self._format_project_context(context)}"

            # Get related projects if asking about relationships
            # Note: find_related_projects requires a specific project name
            # if any(kw in task_lower for kw in relationship_keywords):
            #     related = self.memory_service.find_related_projects()
            #     if related:
            #         return f"RELATED PROJECTS:\n{related}"

            # Default: get general project context
            # Note: get_project_context requires a specific project name
            # context = self.memory_service.get_project_context()
            # if context:
            #     return f"PROJECT CONTEXT:\n{context}"

            return None

        except Exception as e:
            self.logger.warning(f"Failed to get graph context: {e}")
            return None

    def _format_project_context(self, context):
        """Format project context data into readable text."""
        try:
            result = f"Project: {context.get('project', 'Unknown')}\n"

            if context.get('workspace'):
                result += f"Workspace: {context['workspace']}\n"

            if context.get('purpose'):
                result += f"Purpose: {context['purpose']}\n"

            if context.get('related_projects'):
                result += f"Related Projects: {', '.join(context['related_projects'])}\n"

            if context.get('resources'):
                result += "Resources:\n"
                for resource in context['resources']:
                    result += f"  - {resource['resource']}"
                    if resource.get('purpose'):
                        result += f" (purpose: {resource['purpose']})"
                    result += "\n"

            if context.get('configurations'):
                result += f"Configurations: {', '.join(context['configurations'])}\n"

            return result.strip()

        except Exception as e:
            self.logger.warning(f"Failed to format project context: {e}")
            return str(context)

    def _load_pi_configs(self) -> Dict[str, Dict[str, str]]:
        """Load Raspberry Pi deployment configurations from environment variables or defaults."""
        configs = {}

        # Default configuration for pi1
        configs["pi1"] = {
            "host": os.environ.get("PI1_HOST", "192.168.1.100"),  # Default Pi IP
            "user": os.environ.get("PI1_USER", "pi"),
            "key_path": os.environ.get("PI1_KEY_PATH", "~/.ssh/id_rsa"),
        }

        # Allow additional Pis via environment variables (PI2_HOST, PI2_USER, etc.)
        for i in range(2, 10):  # Support up to 9 Pis
            host = os.environ.get(f"PI{i}_HOST")
            if host:
                configs[f"pi{i}"] = {
                    "host": host,
                    "user": os.environ.get(f"PI{i}_USER", "pi"),
                    "key_path": os.environ.get(f"PI{i}_KEY_PATH", "~/.ssh/id_rsa"),
                }

        self.logger.info(f"Loaded Pi configurations for: {list(configs.keys())}")
        return configs

    def run(
        self, input: Any = None, context: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> str:
        """
        Execute a task.
        - If the task is a specific dict to launch the GUI, it launches the GUI.
        - Otherwise, it sends the task to the GUI for interpretation.
        """
        task = kwargs.pop("task", None)
        if task is None:
            task = input

        # Start session if not already started
        if self.current_session_id is None:
            self.current_session_id = start_session(user_agent="AutonomousUserAgent")

        # Path 1: A script calls with a specific dictionary to launch the GUI.
        # This bypasses the LLM.
        if isinstance(task, dict) and task.get("task") == "show_chat_interface":
            if not self.gui_ops:
                error = "GUI chat interface is unavailable because tkinter is not installed."
                if self.gui_import_error:
                    error = f"{error} ({self.gui_import_error})"
                return error
            return self.gui_ops.show_chat_interface(self).message

        # Path 1.5: Direct request to self-diagnose and optionally connect to Tor memory
        if isinstance(task, dict) and task.get("task") == "self_diagnose":
            # Allow passing a tor memory server URL via parameters
            params = task.get("parameters", {}) if isinstance(task, dict) else {}
            tor_url = params.get("tor_url") or os.environ.get("TOR_MEMORY_SERVER_URL")
            return self.self_diagnose(tor_url=tor_url, proxy_host=proxy_host, proxy_port=proxy_port, remote_memory_url=remote_memory_url)
            proxy_host = params.get('proxy_host', '127.0.0.1')
            proxy_host = params.get('proxy_host', '127.0.0.1')
            proxy_port = int(params.get('proxy_port', 9050))
            remote_memory_url = params.get('remote_memory_url') or os.environ.get('REMOTE_MEMORY_SERVER_URL')
            return self.self_diagnose(tor_url=tor_url, proxy_host=proxy_host, proxy_port=proxy_port, remote_memory_url=remote_memory_url)
            proxy_host = params.get('proxy_host', '127.0.0.1')
            proxy_port = int(params.get('proxy_port', 9050))
            remote_memory_url = params.get('remote_memory_url') or os.environ.get('REMOTE_MEMORY_SERVER_URL')
            return self.self_diagnose(tor_url=tor_url, proxy_host=proxy_host, proxy_port=proxy_port, remote_memory_url=remote_memory_url)
