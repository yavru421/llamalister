"""
LlamaMachinery operations for AutonomousUserAgent.

This module handles LlamaMachinery-specific agent operations.
"""

import os
import sys
from typing import Dict, Any, List
from . import BaseOperations, OperationResult


class LlamaMachineryOperations(BaseOperations):
    """Handles LlamaMachinery agent operations"""

    def list_agents(self, params: Dict[str, Any]) -> OperationResult:
        """List available LlamaMachinery agents"""
        try:
            self._log_operation("list_agents")

            # Try to import agent registry
            try:
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                parent_dir = os.path.dirname(current_dir)
                sys.path.insert(0, parent_dir)

                from agents.agent_registry import AgentRegistry
                registry = AgentRegistry()
                agents = registry.load_agents()

                if agents:
                    # Format agent information
                    result = f"Available LlamaMachinery Agents ({len(agents)} registered):\n"
                    for agent in agents:
                        result += f"• {agent.get('name', 'Unknown')} ({agent.get('model', 'Unknown Model')})\n"
                        tags = agent.get('tags', [])
                        if tags:
                            result += f"  Tags: {', '.join(tags)}\n"
                        purpose = agent.get('system_prompt', '')
                        if purpose:
                            result += f"  Purpose: {purpose[:100]}{'...' if len(purpose) > 100 else ''}\n"
                        result += "\n"
                    return OperationResult(True, result, agents)
            except ImportError:
                pass  # Fall through to mock response

            # If no agents in registry or registry not available, list available agent classes
            agent_classes = [
                "DataIngestionAgent",
                "OrchestrationAgent",
                "ReportingAgent",
                "APIGatewayAgent",
                "MonitoringAgent",
                "VisionAgent",
                "LlamaMachineryMaintenanceAgent",
                "LibrarianAgent",
                "InventionAgent",
                "EchoPlexusAgent",
                "QuantumEchoPlexusAgent",
                "RealEstateInvestmentAgent"
            ]
            result = f"LlamaMachinery Agent Classes ({len(agent_classes)}):\n" + "\n".join(f"• {cls}" for cls in agent_classes)
            return OperationResult(True, result, agent_classes)

        except Exception as e:
            return OperationResult(False, f"Error listing agents: {e}")

    def run_agent(self, params: Dict[str, Any]) -> OperationResult:
        """Run a specific LlamaMachinery agent"""
        try:
            agent_name = params.get("agent_name")
            agent_input = params.get("agent_input", "")

            if not agent_name:
                return OperationResult(False, "Error: agent_name is required for running an agent")

            self._log_operation("run_agent", f"name={agent_name}")

            # Handle specific agents with actual execution
            if agent_name == "deployment_agent":
                # Parse input: "deploy <contract_path>"
                if agent_input.startswith("deploy "):
                    contract_path = agent_input[7:].strip()
                    if not os.path.exists(contract_path):
                        return OperationResult(False, f"Contract file not found: {contract_path}")

                    # Run forge create to deploy to local anvil
                    # Assume anvil is running on localhost:8545
                    command = f"cd foundry && forge create {contract_path}:GeneratedContract --rpc-url http://localhost:8545 --private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
                    # Note: Using a common anvil private key for testing

                    import subprocess
                    try:
                        result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
                        if result.returncode == 0:
                            return OperationResult(True, f"Deployment successful:\n{result.stdout}", result.stdout)
                        else:
                            return OperationResult(False, f"Deployment failed:\n{result.stderr}", result.stderr)
                    except Exception as e:
                        return OperationResult(False, f"Error executing deployment: {e}")
                else:
                    return OperationResult(False, f"Invalid input for deployment_agent: {agent_input}")

            # Import agent registry to get agent class
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            parent_dir = os.path.dirname(current_dir)
            sys.path.insert(0, parent_dir)

            try:
                from agents.agent_registry import AgentRegistry

                registry = AgentRegistry()
                agent_class = registry.get_agent_class(agent_name)

                if agent_class is None:
                    return OperationResult(False, f"Error: Agent {agent_name} not found in registry. Available agents: LibrarianAgent, InventionAgent, EchoPlexusAgent, etc.")

                # Instantiate and run the agent with standardized interface
                agent = agent_class()
                result = agent.run(input=agent_input, context={"agent_source": "AutonomousUserAgent"})
                return OperationResult(True, f"Agent {agent_name} execution result:\n{result}", result)
            except ImportError:
                # Mock agent execution for testing when registry is not available
                mock_result = f"Mock execution of agent {agent_name} with input: '{agent_input}'\nAgent would process the input and return results."
                return OperationResult(True, f"Agent {agent_name} execution result:\n{mock_result}", mock_result)

        except Exception as e:
            return OperationResult(False, f"Error running agent {params.get('agent_name', 'unknown')}: {e}")

    def orchestrate_workflow(self, params: Dict[str, Any]) -> OperationResult:
        """Orchestrate a workflow with multiple agents"""
        try:
            workflow_steps = params.get("workflow_steps", [])

            if not workflow_steps:
                return OperationResult(False, "Error: workflow_steps is required for orchestration")

            self._log_operation("orchestrate_workflow", f"steps={len(workflow_steps)}")

            # Try to import orchestration module
            try:
                current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                parent_dir = os.path.dirname(current_dir)
                sys.path.insert(0, parent_dir)

                from agents.orchestration_agent import OrchestrationAgent
                from agents.agent_registry import AgentRegistry

                orchestrator = OrchestrationAgent()
                registry = AgentRegistry()

                # Helper dummy agent for unknown agents
                class _DummyAgent:
                    def __init__(self, name):
                        self.name = name
                    def run(self, *args, **kwargs):
                        return f"Unknown agent {self.name}"

                # Add tasks to the workflow
                for step in workflow_steps:
                    agent_name = step.get("agent")
                    agent_input = step.get("input")

                    agent_class = None
                    try:
                        agent_class = registry.get_agent_class(agent_name)
                    except Exception:
                        agent_class = None

                    if agent_class:
                        agent_instance = agent_class()
                        # Only pass input if it's not None/empty, let OrchestrationAgent handle chaining
                        if agent_input:
                            orchestrator.add_task(agent_instance, input=agent_input, context={"agent_source": "OrchestrationAgent"})
                        else:
                            orchestrator.add_task(agent_instance, context={"agent_source": "OrchestrationAgent"})
                    else:
                        # add dummy task to record missing agent
                        if agent_input:
                            orchestrator.add_task(_DummyAgent(agent_name), input=agent_input, context={"agent_source": "OrchestrationAgent"})
                        else:
                            orchestrator.add_task(_DummyAgent(agent_name), context={"agent_source": "OrchestrationAgent"})

                # Run the workflow
                results = orchestrator.run()
                return OperationResult(True, f"Workflow orchestration result:\n{results}", results)

            except ImportError:
                # Mock orchestration for testing when modules are not available
                results = []
                for i, step in enumerate(workflow_steps):
                    agent_name = step.get("agent", "Unknown")
                    agent_input = step.get("input", "")
                    results.append(f"Step {i+1}: Agent {agent_name} would process '{agent_input}'")

                result_text = f"Workflow orchestration result:\nMock workflow orchestration completed ({len(workflow_steps)} steps):\n" + "\n".join(results)
                return OperationResult(True, result_text, results)

        except Exception as e:
            return OperationResult(False, f"Error orchestrating workflow: {e}")

    def check_agent_health(self, params: Dict[str, Any]) -> OperationResult:
        """Check the health status of a LlamaMachinery agent"""
        try:
            agent_name = params.get("agent_name")

            if not agent_name:
                return OperationResult(False, "Error: agent_name is required for health check")

            self._log_operation("check_agent_health", f"name={agent_name}")

            # Use registry to check agent existence and try instantiation
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            parent_dir = os.path.dirname(current_dir)
            sys.path.insert(0, parent_dir)

            from agents.agent_registry import AgentRegistry

            registry = AgentRegistry()
            try:
                agent_class = registry.get_agent_class(agent_name)
            except Exception:
                agent_class = None

            if agent_class is None:
                return OperationResult(True, f"Agent {agent_name} health: NOT FOUND")

            try:
                agent_instance = agent_class()
                return OperationResult(True, f"Agent {agent_name} health: HEALTHY (instantiated successfully)")
            except Exception as e:
                return OperationResult(False, f"Agent {agent_name} health: UNHEALTHY (instantiation failed: {e})")
        except Exception as e:
            return OperationResult(False, f"Error checking agent health: {e}")

    def create_agent(self, params: Dict[str, Any]) -> OperationResult:
        """Create a new LlamaMachinery agent"""
        try:
            agent_config = params.get("agent_config", {})
            agent_purpose = params.get("agent_purpose", "")
            agent_tags = params.get("agent_tags", [])

            if not agent_config or not agent_purpose:
                return OperationResult(False, "Error: agent_config and agent_purpose are required for creating an agent")

            self._log_operation("create_agent", f"name={agent_config.get('name', 'NewAgent')}")

            # Import agent registry for creation
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            parent_dir = os.path.dirname(current_dir)
            sys.path.insert(0, parent_dir)

            from agents.agent_registry import AgentRegistry

            registry = AgentRegistry()

            # Create agent data structure
            agent_data = {
                "name": agent_config.get("name", "NewAgent"),
                "model": agent_config.get("model", "Llama-4-Scout-17B-16E-Instruct-FP8"),
                "endpoint": agent_config.get("endpoint", "https://llama-universal-netlify-project.netlify.app/.netlify/functions/llama-proxy?path=/chat/completions"),
                "system_prompt": agent_purpose,
                "version": agent_config.get("version", "1.0.0"),
                "tags": agent_tags
            }

            result = registry.add_agent(agent_data)
            return OperationResult(True, f"Agent creation result:\n{result}", result)
        except Exception as e:
            return OperationResult(False, f"Error creating agent: {e}")

    def update_agent_config(self, params: Dict[str, Any]) -> OperationResult:
        """Update configuration of a LlamaMachinery agent"""
        try:
            agent_name = params.get("agent_name")
            agent_config = params.get("agent_config", {})

            if not agent_name or not agent_config:
                return OperationResult(False, "Error: agent_name and agent_config are required for updating agent config")

            self._log_operation("update_agent_config", f"name={agent_name}")

            # Import agent registry
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            parent_dir = os.path.dirname(current_dir)
            sys.path.insert(0, parent_dir)

            from agents.agent_registry import AgentRegistry

            registry = AgentRegistry()
            agents = registry.load_agents()

            # Find and update the agent
            for agent in agents:
                if agent.get("name") == agent_name:
                    agent.update(agent_config)
                    registry.save_agents(agents)
                    return OperationResult(True, f"Agent {agent_name} configuration updated successfully")

            return OperationResult(False, f"Agent {agent_name} not found")
        except Exception as e:
            return OperationResult(False, f"Error updating agent config: {e}")

    def get_agent_logs(self, params: Dict[str, Any]) -> OperationResult:
        """Get logs for a LlamaMachinery agent"""
        try:
            agent_name = params.get("agent_name")
            limit = params.get("limit", 10)

            if not agent_name:
                return OperationResult(False, "Error: agent_name is required for getting agent logs")

            self._log_operation("get_agent_logs", f"name={agent_name}, limit={limit}")

            # Check for log files in logs directory
            current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            parent_dir = os.path.dirname(current_dir)
            logs_dir = os.path.join(parent_dir, "logs")

            if not os.path.exists(logs_dir):
                return OperationResult(False, f"No logs directory found for agent {agent_name}")

            # Look for agent-specific log files
            log_files = [f for f in os.listdir(logs_dir) if agent_name.lower() in f.lower() and f.endswith('.log')]

            if not log_files:
                return OperationResult(False, f"No log files found for agent {agent_name}")

            # Read the most recent log file
            log_file = os.path.join(logs_dir, sorted(log_files)[-1])
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Return last 'limit' lines
            recent_logs = lines[-limit:] if len(lines) > limit else lines
            result = f"Agent {agent_name} logs (last {len(recent_logs)} entries):\n{''.join(recent_logs)}"
            return OperationResult(True, result, recent_logs)
        except Exception as e:
            return OperationResult(False, f"Error getting agent logs: {e}")