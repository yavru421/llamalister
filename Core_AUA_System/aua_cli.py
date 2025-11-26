#!/usr/bin/env python3
"""
AutonomousUserAgent CLI Interface
A command-line interface for accessing all AutonomousUserAgent capabilities without memorizing commands.
"""

import argparse
import sys

# Activate APT strict mode for the CLI
try:
    import strict_mode  # noqa: F401 - activate strict mode
except ImportError:
    print("[APT FATAL ERROR] strict_mode module not found")
    sys.exit(1)
import json
import requests
import os
import sys
import subprocess
import time
from typing import Dict, Any

class AUACLI:
    def __init__(self):
        self.bridge_url = "http://127.0.0.1:5055/chat"

        # Ensure bridge is running
        self.ensure_bridge_running()

    def ensure_bridge_running(self):
        if not self.is_bridge_running():
            print("Starting AUA Bridge Server...")
            subprocess.Popen([sys.executable, "aua_bridge_server.py"],
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)

    def is_bridge_running(self):
        try:
            response = requests.get("http://127.0.0.1:5055/health", timeout=5)
            return response.status_code == 200
        except:
            return False

        # Action categories and actions
        self.action_categories = {
            "File Operations": ["create_file", "read_file", "edit_file", "delete_file"],
            "Directory Operations": ["list_dir", "create_dir", "delete_dir", "move_file", "copy_file"],
            "Shell Commands": ["run_command"],
            "Package Management": ["install_package", "run_pip"],
            "Search": ["grep_search", "find_files"],
            "Network": ["download_file", "http_get", "http_post"],
            "System Info": ["system_info", "disk_space", "memory_info"],
            "Process Management": ["list_processes", "kill_process"],
            "Git": ["git_status", "git_add", "git_commit", "git_push"],
            "Archive": ["zip_files", "unzip_file"],
            "Environment": ["get_env", "set_env"],
            "GitHub": ["github_create_issue", "github_add_issue_comment", "github_get_issue", "github_list_issues", "github_create_repository", "github_get_repository", "github_create_branch", "github_create_pull_request"],
            "PowerShell": ["create_ps1_script", "run_ps1_script", "create_and_run_ps1_script"],
            "LlamaMachinery": ["list_agents", "run_agent", "orchestrate_workflow", "check_agent_health", "create_agent", "update_agent_config", "get_agent_logs"],
            "GUI": ["show_chat_interface"]
        }

        # Parameter definitions for each action
        self.action_params = {
            "create_file": {"file_path": "str", "content": "text"},
            "read_file": {"file_path": "str"},
            "edit_file": {"file_path": "str", "old_string": "str", "new_string": "str"},
            "delete_file": {"file_path": "str"},
            "list_dir": {"dir_path": "str"},
            "create_dir": {"dir_path": "str"},
            "delete_dir": {"dir_path": "str"},
            "move_file": {"source": "str", "destination": "str"},
            "copy_file": {"source": "str", "destination": "str"},
            "run_command": {"command": "str"},
            "install_package": {"package": "str"},
            "run_pip": {"command": "str"},
            "grep_search": {"pattern": "str", "file_path": "str"},
            "find_files": {"pattern": "str", "dir_path": "str"},
            "download_file": {"url": "str", "destination": "str"},
            "http_get": {"url": "str", "headers": "dict"},
            "http_post": {"url": "str", "data": "str", "headers": "dict"},
            "system_info": {},
            "disk_space": {"path": "str"},
            "memory_info": {},
            "list_processes": {},
            "kill_process": {"pid": "int"},
            "git_status": {"repo_path": "str"},
            "git_add": {"files": "list", "repo_path": "str"},
            "git_commit": {"message": "str", "repo_path": "str"},
            "git_push": {"repo_path": "str"},
            "zip_files": {"files": "list", "zip_path": "str"},
            "unzip_file": {"zip_path": "str", "destination": "str"},
            "get_env": {"env_var": "str"},
            "set_env": {"env_var": "str", "env_value": "str"},
            "github_create_issue": {"owner": "str", "repo": "str", "title": "str", "body": "str", "labels": "list"},
            "github_add_issue_comment": {"owner": "str", "repo": "str", "issue_number": "int", "body": "str"},
            "github_get_issue": {"owner": "str", "repo": "str", "issue_number": "int"},
            "github_list_issues": {"owner": "str", "repo": "str", "state": "str"},
            "github_create_repository": {"name": "str", "description": "str", "private": "bool", "auto_init": "bool"},
            "github_get_repository": {"owner": "str", "repo": "str"},
            "github_create_branch": {"owner": "str", "repo": "str", "branch": "str", "from_branch": "str"},
            "github_create_pull_request": {"owner": "str", "repo": "str", "title": "str", "head": "str", "base": "str", "body": "str", "draft": "bool"},
            "create_ps1_script": {"script_path": "str", "content": "text"},
            "run_ps1_script": {"script_path": "str", "background": "bool", "parameters": "str"},
            "create_and_run_ps1_script": {"script_path": "str", "content": "text", "background": "bool", "parameters": "str"},
            "list_agents": {},
            "run_agent": {"agent_name": "str", "agent_input": "str"},
            "orchestrate_workflow": {"workflow_steps": "list"},
            "check_agent_health": {"agent_name": "str"},
            "create_agent": {"agent_config": "dict", "agent_purpose": "str", "agent_tags": "list"},
            "update_agent_config": {"agent_name": "str", "agent_config": "dict"},
            "get_agent_logs": {"agent_name": "str", "limit": "int"},
            "show_chat_interface": {}
        }

    def run(self):
        parser = argparse.ArgumentParser(description="AutonomousUserAgent CLI Interface")
        parser.add_argument("--interactive", action="store_true", help="Run in interactive mode")
        parser.add_argument("--action", help="Action to perform")
        parser.add_argument("--params", help="JSON string of parameters")
        parser.add_argument("--nl", help="Natural language input")

        args = parser.parse_args()

        if args.interactive:
            self.interactive_mode()
        elif args.nl:
            self.send_request(args.nl)
        elif args.action and args.params:
            try:
                params = json.loads(args.params)
                payload = {"action": args.action, "parameters": params}
                self.send_request(json.dumps(payload))
            except json.JSONDecodeError:
                print("Error: Invalid JSON in --params")
        else:
            parser.print_help()

    def interactive_mode(self):
        print("Welcome to AutonomousUserAgent CLI!")
        print("Type 'help' for help, 'quit' to exit.")
        print("Shortcuts: 'ls' for list_dir, 'cat <file>' for read_file, 'run <cmd>' for run_command")

        while True:
            try:
                user_input = input("> ").strip()
                if user_input.lower() == "quit":
                    break
                elif user_input.lower() == "help":
                    self.show_help()
                elif user_input.lower() == "list":
                    self.list_actions()
                elif user_input.startswith("ls"):
                    # Shortcut for list_dir
                    parts = user_input.split(" ", 1)
                    dir_path = parts[1] if len(parts) > 1 else "."
                    payload = {"action": "list_dir", "parameters": {"dir_path": dir_path}}
                    self.send_request(json.dumps(payload))
                elif user_input.startswith("cat "):
                    # Shortcut for read_file
                    parts = user_input.split(" ", 1)
                    if len(parts) > 1:
                        file_path = parts[1]
                        payload = {"action": "read_file", "parameters": {"file_path": file_path}}
                        self.send_request(json.dumps(payload))
                    else:
                        print("Usage: cat <file_path>")
                elif user_input.startswith("lib"):
                    # Shortcut for listing Python libraries or directory
                    parts = user_input.split(" ", 1)
                    if len(parts) > 1 and parts[1] == "list":
                        payload = {"action": "run_command", "parameters": {"command": "pip list"}}
                        self.send_request(json.dumps(payload))
                    else:
                        dir_path = parts[1] if len(parts) > 1 else "library"
                        payload = {"action": "list_dir", "parameters": {"dir_path": dir_path}}
                        self.send_request(json.dumps(payload))
                elif user_input.startswith("py "):
                    # Shortcut for running Python code
                    parts = user_input.split(" ", 1)
                    if len(parts) > 1:
                        code = parts[1]
                        payload = {"action": "run_command", "parameters": {"command": f"python -c \"{code}\""}}
                        self.send_request(json.dumps(payload))
                    else:
                        print("Usage: py <python_code>")
                elif user_input.startswith("info"):
                    # Shortcut for system info
                    payload = {"action": "system_info", "parameters": {}}
                    self.send_request(json.dumps(payload))
                elif user_input.startswith("action "):
                    parts = user_input.split(" ", 2)
                    if len(parts) >= 2:
                        action = parts[1]
                        params_str = parts[2] if len(parts) > 2 else "{}"
                        try:
                            params = json.loads(params_str)
                            payload = {"action": action, "parameters": params}
                            self.send_request(json.dumps(payload))
                        except json.JSONDecodeError:
                            print("Error: Invalid JSON parameters")
                    else:
                        print("Usage: action <action_name> [json_params]")
                else:
                    # Treat as natural language
                    self.send_request(user_input)
            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"Error: {e}")

    def list_actions(self):
        print("Available action categories:")
        for category, actions in self.action_categories.items():
            print(f"  {category}:")
            for action in actions:
                print(f"    - {action}")
        print("\nUse 'action <action_name> {params}' to execute, or type natural language.")

    def show_help(self):
        print("""
AutonomousUserAgent CLI Help

Commands:
  help          Show this help
  list          List all available actions
  action <name> [params]  Execute an action with JSON parameters
  quit          Exit the CLI

You can also type natural language descriptions of what you want to do.

Examples:
  > list
  > action create_file {"file_path": "test.txt", "content": "Hello World"}
  > Create a file called hello.txt with content 'Hi there'
        """)

    def send_request(self, message: str):
        try:
            response = requests.post(self.bridge_url, json={"message": message}, timeout=30)
            if response.status_code == 200:
                result = response.json().get("response", "No response")
                print(f"Result: {result}")
            else:
                print(f"Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"Error: {str(e)}")

if __name__ == "__main__":
    cli = AUACLI()
    cli.run()