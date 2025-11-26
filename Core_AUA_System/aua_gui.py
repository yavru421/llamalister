#!/usr/bin/env python3
"""
AutonomousUserAgent GUI Interface
A user-friendly GUI for accessing all AutonomousUserAgent capabilities without memorizing commands.
"""

import tkinter as tk
from tkinter import ttk
import sys

# Activate APT strict mode for the GUI
try:
    import strict_mode  # noqa: F401 - activate strict mode
except ImportError:
    print("[APT FATAL ERROR] strict_mode module not found")
    sys.exit(1)
from tkinter import ttk, messagebox, scrolledtext, filedialog
import json
import requests
import threading
import os

from automated_marketplace_poster import AutomatedMarketplacePoster

# Add memory service import
try:
    from src.memory_service import get_memory_service
except ImportError:
    from memory_service import get_memory_service

class AUAGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AutonomousUserAgent Interface")
        self.root.geometry("1000x700")

        # Bridge server URL
        self.bridge_url = "http://127.0.0.1:5055/chat"

        # Lazy-initialized marketplace poster
        self._poster = None

        # Initialize memory service
        self.memory_service = get_memory_service()

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

        self.create_widgets()

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left sidebar for categories and actions
        sidebar_frame = ttk.Frame(main_frame, width=250)
        sidebar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0,10))

        ttk.Label(sidebar_frame, text="Categories", font=("Arial", 12, "bold")).pack(pady=5)

        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(sidebar_frame, textvariable=self.category_var, state="readonly")
        self.category_combo['values'] = list(self.action_categories.keys())
        self.category_combo.pack(fill=tk.X, pady=5)
        self.category_combo.bind("<<ComboboxSelected>>", self.on_category_select)

        ttk.Label(sidebar_frame, text="Actions", font=("Arial", 12, "bold")).pack(pady=5)

        self.action_listbox = tk.Listbox(sidebar_frame, height=15)
        self.action_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.action_listbox.bind("<<ListboxSelect>>", self.on_action_select)

        # Form frame in sidebar
        form_frame = ttk.LabelFrame(sidebar_frame, text="Action Parameters")
        form_frame.pack(fill=tk.X, pady=(10,0))

        self.param_frame = ttk.Frame(form_frame)
        self.param_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Execute button
        ttk.Button(form_frame, text="Execute Action", command=self.execute_action).pack(pady=5)

        # Right panel for chat
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Chat history
        self.chat_history = scrolledtext.ScrolledText(right_frame, wrap=tk.WORD, state=tk.NORMAL)
        self.chat_history.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

        # Chat input frame
        input_frame = ttk.Frame(right_frame)
        input_frame.pack(fill=tk.X, padx=10, pady=(0,10))

        self.chat_input = ttk.Entry(input_frame)
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.chat_input.bind("<Return>", lambda e: self.send_chat_message())

        send_button = ttk.Button(input_frame, text="Send", command=self.send_chat_message)
        send_button.pack(side=tk.RIGHT)

        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Configure API Keys", command=self.configure_settings)

        marketplace_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Marketplace", menu=marketplace_menu)
        marketplace_menu.add_command(label="Open Marketplace Poster", command=self.open_marketplace_poster)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Action Help", command=self.show_help)

    def get_poster(self) -> AutomatedMarketplacePoster:
        if self._poster is None:
            self._poster = AutomatedMarketplacePoster()
        return self._poster

    def open_marketplace_poster(self):
        """Open a simple marketplace poster UI in a new window."""
        poster = self.get_poster()

        win = tk.Toplevel(self.root)
        win.title("Automated Marketplace Poster")
        win.geometry("500x600")

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Platform
        ttk.Label(frame, text="Platform:").grid(row=0, column=0, sticky=tk.W, pady=4)
        platform_var = tk.StringVar(value="ebay")
        platform_box = ttk.Combobox(frame, textvariable=platform_var, state="readonly")
        platform_box["values"] = ["ebay", "facebook_marketplace", "etsy"]
        platform_box.grid(row=0, column=1, sticky=tk.EW, pady=4)

        # Title
        ttk.Label(frame, text="Title:").grid(row=1, column=0, sticky=tk.W, pady=4)
        title_entry = ttk.Entry(frame)
        title_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)

        # Price
        ttk.Label(frame, text="Price (USD):").grid(row=2, column=0, sticky=tk.W, pady=4)
        price_entry = ttk.Entry(frame)
        price_entry.grid(row=2, column=1, sticky=tk.EW, pady=4)

        # Description
        ttk.Label(frame, text="Description:").grid(row=3, column=0, sticky=tk.W, pady=4)
        desc_text = scrolledtext.ScrolledText(frame, height=4)
        desc_text.grid(row=3, column=1, sticky=tk.EW, pady=4)

        # Category
        ttk.Label(frame, text="Category:").grid(row=4, column=0, sticky=tk.W, pady=4)
        category_entry = ttk.Entry(frame)
        category_entry.grid(row=4, column=1, sticky=tk.EW, pady=4)

        # Condition
        ttk.Label(frame, text="Condition:").grid(row=5, column=0, sticky=tk.W, pady=4)
        condition_var = tk.StringVar(value="used")
        condition_box = ttk.Combobox(frame, textvariable=condition_var, state="readonly")
        condition_box["values"] = ["new", "used", "like-new"]
        condition_box.grid(row=5, column=1, sticky=tk.EW, pady=4)

        # Tags
        ttk.Label(frame, text="Tags (comma-separated):").grid(row=6, column=0, sticky=tk.W, pady=4)
        tags_entry = ttk.Entry(frame)
        tags_entry.grid(row=6, column=1, sticky=tk.EW, pady=4)

        # Result log
        ttk.Label(frame, text="Status:").grid(row=7, column=0, sticky=tk.NW, pady=4)
        log_box = scrolledtext.ScrolledText(frame, height=10, state=tk.NORMAL)
        log_box.grid(row=7, column=1, sticky=tk.NSEW, pady=4)

        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)

        def post_listing():
            platform = platform_var.get().strip()
            title = title_entry.get().strip()
            price_text = price_entry.get().strip()

            if not platform or not title or not price_text:
                messagebox.showerror("Error", "Platform, title, and price are required.")
                return

            try:
                price = float(price_text)
            except ValueError:
                messagebox.showerror("Error", "Price must be a number.")
                return

            description = desc_text.get("1.0", tk.END).strip()
            category = category_entry.get().strip() or "General"
            condition = condition_var.get().strip() or "used"
            tags_raw = tags_entry.get().strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

            log_box.insert(tk.END, f"Starting automated posting to {platform}...\n")
            log_box.see(tk.END)

            def worker():
                try:
                    result = poster.quick_post(
                        platform,
                        title,
                        price,
                        description=description,
                        category=category,
                        condition=condition,
                        tags=tags,
                    )
                    if result.get("success"):
                        msg = f"✅ Posted to {platform} in {result['posting_result']['duration']:.1f}s\n"
                    else:
                        msg = f"❌ Posting failed: {result.get('error')}\n"
                except Exception as exc:
                    msg = f"❌ Exception during posting: {exc}\n"

                def update_log():
                    log_box.insert(tk.END, msg)
                    log_box.see(tk.END)

                self.root.after(0, update_log)

            threading.Thread(target=worker, daemon=True).start()

        ttk.Button(frame, text="Post Listing", command=post_listing).grid(row=8, column=1, sticky=tk.E, pady=10)

    def on_category_select(self, event):
        category = self.category_var.get()
        self.action_listbox.delete(0, tk.END)
        if category in self.action_categories:
            for action in self.action_categories[category]:
                self.action_listbox.insert(tk.END, action)

    def on_action_select(self, event):
        selection = self.action_listbox.curselection()
        if selection:
            action = self.action_listbox.get(selection[0])
            self.build_form(action)

    def build_form(self, action):
        # Clear previous form
        for widget in self.param_frame.winfo_children():
            widget.destroy()

        if action not in self.action_params:
            return

        params = self.action_params[action]
        row = 0
        self.param_entries = {}

        for param, param_type in params.items():
            ttk.Label(self.param_frame, text=f"{param} ({param_type}):").grid(row=row, column=0, sticky=tk.W, pady=2)
            if param_type == "str":
                entry = ttk.Entry(self.param_frame, width=50)
                entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.param_entries[param] = entry
            elif param_type == "text":
                text = scrolledtext.ScrolledText(self.param_frame, height=5, width=50)
                text.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.param_entries[param] = text
            elif param_type == "int":
                entry = ttk.Entry(self.param_frame, width=50)
                entry.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.param_entries[param] = entry
            elif param_type == "bool":
                var = tk.BooleanVar()
                check = ttk.Checkbutton(self.param_frame, variable=var)
                check.grid(row=row, column=1, sticky=tk.W, pady=2)
                self.param_entries[param] = var
            elif param_type == "list":
                text = scrolledtext.ScrolledText(self.param_frame, height=3, width=50)
                text.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.param_entries[param] = text
            elif param_type == "dict":
                text = scrolledtext.ScrolledText(self.param_frame, height=3, width=50)
                text.grid(row=row, column=1, sticky=tk.EW, pady=2)
                self.param_entries[param] = text
            row += 1

        # Add tooltips and validation
        for param, widget in self.param_entries.items():
            if isinstance(widget, ttk.Entry):
                widget.bind("<FocusIn>", lambda e, p=param: self.show_tooltip(p))
                widget.bind("<FocusOut>", lambda e: self.hide_tooltip())

    def show_tooltip(self, param):
        # Simple tooltip implementation
        tooltip_text = f"Enter the {param} value. This is required for the action."
        # For simplicity, we'll just print to console or use a label
        print(f"Tooltip: {tooltip_text}")

    def hide_tooltip(self):
        pass

    def execute_action(self):
        selection = self.action_listbox.curselection()
        if not selection:
            messagebox.showerror("Error", "Please select an action.")
            return

        action = self.action_listbox.get(selection[0])
        params = {}

        for param, widget in self.param_entries.items():
            if isinstance(widget, ttk.Entry):
                value = widget.get().strip()
                if not value:
                    messagebox.showerror("Error", f"Please fill in {param}.")
                    return
                params[param] = value
            elif isinstance(widget, scrolledtext.ScrolledText):
                value = widget.get("1.0", tk.END).strip()
                if not value:
                    messagebox.showerror("Error", f"Please fill in {param}.")
                    return
                if self.action_params[action][param] == "list":
                    try:
                        params[param] = json.loads(value)
                    except:
                        params[param] = value.split('\n')
                elif self.action_params[action][param] == "dict":
                    try:
                        params[param] = json.loads(value)
                    except:
                        params[param] = {}
                else:
                    params[param] = value
            elif isinstance(widget, tk.BooleanVar):
                params[param] = widget.get()
            elif isinstance(widget, ttk.Entry) and self.action_params[action][param] == "int":
                try:
                    params[param] = int(widget.get())
                except:
                    messagebox.showerror("Error", f"{param} must be an integer.")
                    return

        # Send to bridge server
        self.chat_history.insert(tk.END, f"You executed action: {action} with params {params}\n")
        payload = {"action": action, "parameters": params}
        message = json.dumps(payload)
        self.send_request(message)

    def send_request(self, message):
        def request_thread():
            try:
                response = requests.post(self.bridge_url, json={"message": message}, timeout=30)
                if response.status_code == 200:
                    result = response.json().get("response", "No response")
                    self.chat_history.insert(tk.END, f"Agent: {result}\n\n")
                    self.chat_history.see(tk.END)

                    # Log successful GUI interaction
                    self.memory_service.log_interaction(
                        interaction_type="gui",
                        method="chat",
                        user_input=message,
                        agent_response=result,
                        success=True
                    )

                    # Learn from successful GUI interactions
                    interaction_data = {
                        'user_input': message,
                        'agent_response': result,
                        'success': True,
                        'interaction_type': 'gui',
                        'method': 'chat'
                    }
                    self.memory_service.learn_from_interaction(interaction_data)
                else:
                    error_msg = f"Error: {response.status_code} - {response.text}"
                    self.chat_history.insert(tk.END, f"{error_msg}\n\n")
                    self.chat_history.see(tk.END)

                    # Log failed GUI interaction
                    self.memory_service.log_interaction(
                        interaction_type="gui",
                        method="chat",
                        user_input=message,
                        agent_response=error_msg,
                        success=False,
                        error_message=error_msg
                    )
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                self.chat_history.insert(tk.END, f"{error_msg}\n\n")
                self.chat_history.see(tk.END)

                # Log failed GUI interaction
                self.memory_service.log_interaction(
                    interaction_type="gui",
                    method="chat",
                    user_input=message,
                    agent_response=error_msg,
                    success=False,
                    error_message=str(e)
                )

        threading.Thread(target=request_thread).start()

    def configure_settings(self):
        # Simple settings dialog
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("400x300")

        ttk.Label(settings_window, text="API Key:").pack(pady=5)
        api_key_entry = ttk.Entry(settings_window, width=50)
        api_key_entry.pack(pady=5)
        api_key_entry.insert(0, os.environ.get("LLAMA_API_KEY", ""))

        def save_settings():
            os.environ["LLAMA_API_KEY"] = api_key_entry.get()
            messagebox.showinfo("Settings", "Settings saved.")
            settings_window.destroy()

        ttk.Button(settings_window, text="Save", command=save_settings).pack(pady=10)

    def show_help(self):
        help_window = tk.Toplevel(self.root)
        help_window.title("Help")
        help_window.geometry("600x400")

        help_text = scrolledtext.ScrolledText(help_window, wrap=tk.WORD)
        help_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        help_text.insert(tk.END, """
AutonomousUserAgent Interface Help

This GUI allows you to access all capabilities of the AutonomousUserAgent without memorizing commands.

How to use:
1. Select a category from the dropdown.
2. Choose an action from the list.
3. Fill in the required parameters in the form.
4. Click "Execute Action" to run it.

You can also use natural language input to describe what you want to do.

For more details on each action, refer to the agent documentation.
        """)
        help_text.config(state=tk.DISABLED)

    def send_chat_message(self):
        message = self.chat_input.get().strip()
        if not message:
            return
        self.chat_history.insert(tk.END, f"You: {message}\n")
        self.chat_input.delete(0, tk.END)

        def request_thread():
            try:
                response = requests.post(self.bridge_url, json={"message": message}, timeout=30)
                if response.status_code == 200:
                    result = response.json().get("response", "No response")
                    self.chat_history.insert(tk.END, f"Agent: {result}\n\n")
                    self.chat_history.see(tk.END)
                else:
                    self.chat_history.insert(tk.END, f"Error: {response.status_code} - {response.text}\n\n")
                    self.chat_history.see(tk.END)
            except Exception as e:
                self.chat_history.insert(tk.END, f"Error: {str(e)}\n\n")
                self.chat_history.see(tk.END)

        threading.Thread(target=request_thread).start()

if __name__ == "__main__":
    root = tk.Tk()
    progress_bar = ttk.Progressbar(root, orient='horizontal', length=200, mode='determinate')
    progress_bar.pack(pady=10)
    app = AUAGUI(root)
    root.mainloop()
