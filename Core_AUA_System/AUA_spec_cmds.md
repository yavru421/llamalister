# AUA (Autonomous User Agent) Quick Commands Guide

## 🚀 Quick Start Commands

### 1. Start Bridge Server (Required for most operations)

```bash
# Windows PowerShell
python aua_bridge_server.py

# Or background (recommended)
Start-Job { python .\aua_bridge_server.py } | Out-Null
```

### 2. Launch GUI Interface

```bash
# Windows PowerShell
python run_aua_gui.py

# Alternative
python aua_gui.py
```

### 3. CLI Interface

```bash
# Windows PowerShell
python aua_cli.py
```

## 📋 Environment Variables

Set these before running AUA:

```powershell
# Windows PowerShell
$env:REMOTE_MEMORY_SERVER_URL = "http://your-pi-server:7860/graph"
$env:TOR_MEMORY_SERVER_URL = "http://your-tor-server/graph"
$env:REMOTE_MEMORY_SERVER_URL = "http://192.168.1.100:7860/graph"  # Example IP
```

## 🔧 Direct Python Usage

### Basic AUA Interaction

```python
# Copy-paste this into Python REPL or script
from src.agents.autonomous_user_agent import AutonomousUserAgent

# Create AUA instance
aua = AutonomousUserAgent()

# Ask about projects
print(aua.run("Tell me about the llamamachinery project"))

# Run commands
print(aua.run("list files in current directory"))

# Get workspace overview
print(aua.run("show me the workspace structure"))
```

### Memory Service Direct Access

```python
# Copy-paste this into Python REPL
from src.memory_service import AUAMemoryService

# Create memory service
ms = AUAMemoryService()

# Get workspace overview
overview = ms.get_workspace_overview()
print("Workspace Overview:", overview)

# Get project context
context = ms.get_project_context("llamamachinery")
print("Project Context:", context)

# Sync remote graph
result = ms.sync_remote_graph()
print("Sync Result:", result)
```

## 🎯 Common AUA Commands

### Project & Workspace Queries

```python
# Ask AUA directly
aua.run("What projects are in the workspace?")
aua.run("Tell me about llamamachinery")
aua.run("What are the related projects?")
aua.run("Show workspace overview")
```

### File Operations

```python
# Via AUA
aua.run("list files in the current directory")
aua.run("create a file called test.txt with content 'hello world'")
aua.run("read the file README.md")
aua.run("find all .py files")
```

### System Operations

```python
# Via AUA
aua.run("show system information")
aua.run("check disk space")
aua.run("list running processes")
aua.run("get current environment variables")
```

### Git Operations

```python
# Via AUA
aua.run("check git status")
aua.run("add all files to git")
aua.run("commit changes with message 'update'")
aua.run("push to remote repository")
```

## 🌐 Network & Remote Operations

### Connect to Remote Memory

```python
# Via AUA
aua.run({"task": "self_diagnose", "parameters": {"remote_memory_url": "http://192.168.1.100:7860/graph"}})
```

### HTTP Requests

```python
# Via AUA
aua.run("make a GET request to https://api.github.com/user")
aua.run("download file from https://example.com/file.zip")
```

## 🛠️ Development & Testing

### Run Tests

```bash
# Windows PowerShell
python -m pytest tests/ -v

# Or specific test
python -m pytest aua_baseline_test.py -v
```

### Compile Agents

```bash
# Windows PowerShell
python -m compileall src/agents
```

### Check Requirements

```bash
# Windows PowerShell
pip install -r requirements.txt
```

## 🔍 Debugging Commands

### Check Memory Stats

```python
# Copy-paste into Python
from src.memory_service import AUAMemoryService
ms = AUAMemoryService()
stats = ms.get_stats()
print("Memory Stats:", stats)
```

### View Recent Interactions

```python
# Copy-paste into Python
from src.memory_service import AUAMemoryService
ms = AUAMemoryService()
interactions = ms.get_recent_interactions(limit=5)
for i in interactions:
    print(f"User: {i['user_input']}")
    print(f"Agent: {i['agent_response']}")
    print("---")
```

### Check Remote Graph Data

```python
# Copy-paste into Python
from src.memory_service import AUAMemoryService
ms = AUAMemoryService()
edges = ms.get_remote_graph_edges()
print(f"Found {len(edges)} edges in remote graph")
for edge in edges[:3]:  # Show first 3
    print(edge)
```

## 🚀 PowerShell Automation Scripts

### Background Bridge Server

```powershell
# Save as start_bridge.ps1
Start-Job {
    try {
        Set-Location "C:\Users\John\Desktop\llamagent\llamamachinery-main\llamamachinery-main"
        python aua_bridge_server.py
    } catch {
        Write-Host "Bridge server error: $_"
    }
} | Out-Null
Write-Host "Bridge server started in background"
```

### Quick AUA Query

```powershell
# Save as query_aua.ps1
param([string]$query = "show workspace overview")

try {
    Set-Location "C:\Users\John\Desktop\llamagent\llamamachinery-main\llamamachinery-main"
    $pythonCode = @"
from src.agents.autonomous_user_agent import AutonomousUserAgent
aua = AutonomousUserAgent()
result = aua.run('$query')
print(result)
"@
    python -c $pythonCode
} catch {
    Write-Host "AUA query error: $_"
}
```

### Memory Sync Script

```powershell
# Save as sync_memory.ps1
try {
    Set-Location "C:\Users\John\Desktop\llamagent\llamamachinery-main\llamamachinery-main"
    $pythonCode = @"
from src.memory_service import AUAMemoryService
ms = AUAMemoryService()
result = ms.sync_remote_graph()
print('Sync result:', result)
"@
    python -c $pythonCode
} catch {
    Write-Host "Memory sync error: $_"
}
```

## 📝 Usage Examples

### Example 1: Project Analysis

```python
from src.agents.autonomous_user_agent import AutonomousUserAgent
aua = AutonomousUserAgent()

# Get comprehensive project info
result = aua.run("analyze the llamamachinery project structure")
print(result)

# Check related projects
result = aua.run("what other projects are connected to llamamachinery?")
print(result)
```

### Example 2: File Management

```python
from src.agents.autonomous_user_agent import AutonomousUserAgent
aua = AutonomousUserAgent()

# Create project documentation
result = aua.run("create a README.md file for the llamamachinery project")
print(result)

# Analyze codebase
result = aua.run("find all Python files and count lines of code")
print(result)
```

### Example 3: System Monitoring

```python
from src.agents.autonomous_user_agent import AutonomousUserAgent
aua = AutonomousUserAgent()

# System health check
result = aua.run("check system resources and memory usage")
print(result)

# Network connectivity
result = aua.run("test connection to remote memory server")
print(result)
```

## ⚡ Quick Reference

### Most Used Commands

```python
# Start everything
aua = AutonomousUserAgent()

# Ask questions
aua.run("tell me about llamamachinery")
aua.run("show workspace")
aua.run("list files")

# Do actions
aua.run("create file test.py with hello world")
aua.run("run command dir")
aua.run("check git status")
```

### Environment Setup

```powershell
# Set remote memory URL
$env:REMOTE_MEMORY_SERVER_URL = "http://your-server:7860/graph"

# Start bridge
python aua_bridge_server.py

# Launch GUI
python run_aua_gui.py
```

---

**Note**: All commands assume you're in the llamamachinery project root directory. Adjust paths as needed for your setup.