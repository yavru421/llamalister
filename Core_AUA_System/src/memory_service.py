#!/usr/bin/env python3
"""
AUA Memory Service
Local SQLite-based memory service for storing all AUA interactions.
"""

import sqlite3
import json
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import threading

# Resolve repository root so DB path is stable even when daemonized
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Allow override via env for environments where the repo path is not writable
DEFAULT_DB_PATH = os.environ.get("AUA_DB_PATH") or os.path.join(ROOT_DIR, "aua_memory.db")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class AUAMemoryService:
    """
    Local memory service using SQLite to store all AUA interactions.
    Thread-safe for concurrent access.
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        # Always store an absolute path so daemons and background processes
        # don't depend on the current working directory.
        self.db_path = os.path.abspath(db_path)
        self._lock = threading.Lock()
        self.remote_memory_url = os.environ.get("REMOTE_MEMORY_SERVER_URL")
        self._init_db()
        # Auto-sync remote graph on init if URL is set and allowed
        should_sync_remote = os.environ.get("AUA_SYNC_REMOTE_ON_INIT", "").lower() in {"1", "true", "yes"}
        if self.remote_memory_url and should_sync_remote:
            try:
                self.sync_remote_graph()
            except Exception:
                # Don't fail init if sync fails
                pass

    def _init_db(self):
        """Initialize the database schema"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Interactions table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS interactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT,
                    interaction_type TEXT NOT NULL,  -- 'gui', 'cli', 'api', 'internal'
                    method TEXT NOT NULL,  -- 'chat', 'action', 'inquiry'
                    user_input TEXT,
                    agent_response TEXT,
                    actions_executed TEXT,  -- JSON array of actions
                    success BOOLEAN DEFAULT 1,
                    error_message TEXT,
                    metadata TEXT  -- JSON additional data
                )
            """
            )

            # Sessions table for grouping interactions
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    interaction_count INTEGER DEFAULT 0,
                    user_agent TEXT,
                    ip_address TEXT
                )
            """
            )

            # Knowledge base for learned information
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    category TEXT,
                    confidence REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source TEXT  -- 'interaction', 'learned', 'manual'
                )
            """
            )

            # Remote graph data
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS remote_graph (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    target TEXT NOT NULL,
                    type TEXT NOT NULL,
                    strength TEXT,
                    order_index INTEGER,
                    purpose TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source, target, type)
                )
            """
            )

            conn.commit()
            conn.close()

    def start_session(
        self, user_agent: Optional[str] = None, ip_address: Optional[str] = None
    ) -> str:
        """Start a new interaction session"""
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sessions (id, start_time, user_agent, ip_address)
                VALUES (?, ?, ?, ?)
            """,
                (session_id, datetime.now().isoformat(), user_agent, ip_address),
            )
            conn.commit()
            conn.close()

        return session_id

    def end_session(self, session_id: str):
        """End an interaction session"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sessions
                SET end_time = ?, interaction_count = (
                    SELECT COUNT(*) FROM interactions WHERE session_id = ?
                )
                WHERE id = ?
            """,
                (datetime.now().isoformat(), session_id, session_id),
            )
            conn.commit()
            conn.close()

    def log_interaction(
        self,
        interaction_type: str,
        method: str,
        user_input: Optional[str] = None,
        agent_response: Optional[str] = None,
        actions_executed: Optional[List[Dict[str, Any]]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Log an interaction"""

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO interactions
                (timestamp, session_id, interaction_type, method, user_input,
                 agent_response, actions_executed, success, error_message, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().isoformat(),
                    session_id,
                    interaction_type,
                    method,
                    user_input,
                    agent_response,
                    json.dumps(actions_executed) if actions_executed else None,
                    success,
                    error_message,
                    json.dumps(metadata) if metadata else None,
                ),
            )

            conn.commit()
            conn.close()

    def get_recent_interactions(
        self, limit: int = 50, session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recent interactions"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            if session_id:
                cursor.execute(
                    """
                    SELECT * FROM interactions
                    WHERE session_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """,
                    (session_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM interactions
                    ORDER BY timestamp DESC
                    LIMIT ?
                """,
                    (limit,),
                )

            rows = cursor.fetchall()
            conn.close()

            columns = [
                "id",
                "timestamp",
                "session_id",
                "interaction_type",
                "method",
                "user_input",
                "agent_response",
                "actions_executed",
                "success",
                "error_message",
                "metadata",
            ]

            return [dict(zip(columns, row)) for row in rows]

    def search_interactions(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search interactions by content"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM interactions
                WHERE user_input LIKE ? OR agent_response LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (f"%{query}%", f"%{query}%", limit),
            )

            rows = cursor.fetchall()
            conn.close()

            columns = [
                "id",
                "timestamp",
                "session_id",
                "interaction_type",
                "method",
                "user_input",
                "agent_response",
                "actions_executed",
                "success",
                "error_message",
                "metadata",
            ]

            return [dict(zip(columns, row)) for row in rows]

    def store_knowledge(
        self,
        key: str,
        value: str,
        category: Optional[str] = None,
        confidence: float = 1.0,
        source: str = "interaction",
    ):
        """Store learned knowledge"""
        now = datetime.now().isoformat()

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO knowledge
                (key, value, category, confidence, created_at, updated_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (key, value, category, confidence, now, now, source),
            )

            conn.commit()
            conn.close()

    def retrieve_knowledge(self, key: str) -> Optional[str]:
        """Retrieve stored knowledge"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT value FROM knowledge WHERE key = ?", (key,))
            row = cursor.fetchone()
            conn.close()

            return row[0] if row else None

    def get_stats(self) -> Dict[str, Any]:
        """Get memory service statistics"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Total interactions
            cursor.execute("SELECT COUNT(*) FROM interactions")
            total_interactions = cursor.fetchone()[0]

            # Active sessions
            cursor.execute("SELECT COUNT(*) FROM sessions WHERE end_time IS NULL")
            active_sessions = cursor.fetchone()[0]

            # Knowledge entries
            cursor.execute("SELECT COUNT(*) FROM knowledge")
            knowledge_entries = cursor.fetchone()[0]

            # Recent activity (last 24 hours)
            yesterday = (
                datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ).isoformat()
            cursor.execute("SELECT COUNT(*) FROM interactions WHERE timestamp > ?", (yesterday,))
            recent_interactions = cursor.fetchone()[0]

            conn.close()

            return {
                "total_interactions": total_interactions,
                "active_sessions": active_sessions,
                "knowledge_entries": knowledge_entries,
                "recent_interactions": recent_interactions,
            }

    def learn_from_interaction(self, interaction_data: Dict[str, Any]):
        """Learn patterns and preferences from successful interactions"""
        user_input = interaction_data.get("user_input", "").lower()
        agent_response = interaction_data.get("agent_response", "").lower()
        success = interaction_data.get("success", True)
        interaction_type = interaction_data.get("interaction_type", "unknown")

        if not success:
            return  # Don't learn from failures

        # Learn command patterns
        if "run_command" in agent_response or "executed" in agent_response:
            self._learn_command_pattern(user_input, agent_response)

        # Learn user preferences
        if "file" in user_input and "created" in agent_response:
            self._learn_file_preference(user_input)
        elif "directory" in user_input and "listed" in agent_response:
            self._learn_directory_preference(user_input)

        # Learn successful response patterns
        if len(agent_response) > 50:  # Substantial responses
            self._learn_response_pattern(user_input, agent_response)

    def _learn_command_pattern(self, user_input: str, agent_response: str):
        """Learn common command execution patterns"""
        # Extract command from response
        import re

        command_match = re.search(r"executed command:?\s*([^\\n]+)", agent_response, re.IGNORECASE)
        if command_match:
            command = command_match.group(1).strip()
            key = f"command_pattern_{hash(user_input) % 1000}"
            self.store_knowledge(key, command, "command_patterns", 0.8, "learned")

    def _learn_file_preference(self, user_input: str):
        """Learn user's file operation preferences"""
        if "create" in user_input or "new" in user_input:
            self.store_knowledge(
                "prefers_file_creation", "true", "user_preferences", 0.9, "learned"
            )
        elif "edit" in user_input or "modify" in user_input:
            self.store_knowledge("prefers_file_editing", "true", "user_preferences", 0.9, "learned")

    def _learn_directory_preference(self, user_input: str):
        """Learn user's directory operation preferences"""
        if "list" in user_input or "show" in user_input:
            self.store_knowledge(
                "prefers_directory_listing", "true", "user_preferences", 0.9, "learned"
            )

    def _learn_response_pattern(self, user_input: str, agent_response: str):
        """Learn successful response patterns for similar inputs"""
        # Create a pattern key based on input characteristics
        input_words = set(user_input.split())
        pattern_key = f"response_pattern_{'_'.join(sorted(list(input_words)[:3]))}"

        # Store the successful response pattern
        self.store_knowledge(pattern_key, agent_response[:200], "response_patterns", 0.7, "learned")

    def get_learning_context(self, current_input: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get relevant past interactions for context"""
        current_input_lower = current_input.lower()

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Find similar past interactions
            cursor.execute(
                """
                SELECT * FROM interactions
                WHERE success = 1 AND (
                    LOWER(user_input) LIKE ? OR
                    LOWER(agent_response) LIKE ?
                )
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (f"%{current_input_lower}%", f"%{current_input_lower}%", limit),
            )

            rows = cursor.fetchall()
            conn.close()

            columns = [
                "id",
                "timestamp",
                "session_id",
                "interaction_type",
                "method",
                "user_input",
                "agent_response",
                "actions_executed",
                "success",
                "error_message",
                "metadata",
            ]

            return [dict(zip(columns, row)) for row in rows]

    def get_user_preferences(self) -> Dict[str, str]:
        """Get learned user preferences"""
        preferences = {}
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT key, value FROM knowledge WHERE category = ?", ("user_preferences",)
            )
            rows = cursor.fetchall()
            conn.close()

            for key, value in rows:
                preferences[key] = value

        return preferences

    def get_command_patterns(self, input_text: str) -> List[str]:
        """Get relevant command patterns for input"""
        patterns = []
        input_hash = hash(input_text.lower()) % 1000

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT value FROM knowledge WHERE key LIKE ? AND category = ?",
                (f"command_pattern_{input_hash}", "command_patterns"),
            )
            rows = cursor.fetchall()
            conn.close()

            patterns = [row[0] for row in rows]

        return patterns

    def train_from_history(self, days_back: int = 30) -> Dict[str, int]:
        """Train/learn from interaction history"""
        from datetime import datetime, timedelta

        cutoff_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        trained_count = 0
        pattern_count = 0

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT * FROM interactions WHERE timestamp > ? AND success = 1", (cutoff_date,)
            )
            interactions = cursor.fetchall()
            conn.close()

            columns = [
                "id",
                "timestamp",
                "session_id",
                "interaction_type",
                "method",
                "user_input",
                "agent_response",
                "actions_executed",
                "success",
                "error_message",
                "metadata",
            ]

            for row in interactions:
                interaction_data = dict(zip(columns, row))
                self.learn_from_interaction(interaction_data)
                trained_count += 1

                # Count patterns learned
                if interaction_data.get("actions_executed"):
                    pattern_count += 1

        return {
            "interactions_processed": trained_count,
            "patterns_learned": pattern_count,
            "training_period_days": days_back,
        }

    def get_training_stats(self) -> Dict[str, Any]:
        """Get training/learning statistics"""
        stats = self.get_stats()
        preferences = self.get_user_preferences()

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Success rate
            cursor.execute("SELECT COUNT(*) FROM interactions WHERE success = 1")
            successful = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM interactions")
            total = cursor.fetchone()[0]

            # Pattern categories
            cursor.execute("SELECT category, COUNT(*) FROM knowledge GROUP BY category")
            pattern_stats = dict(cursor.fetchall())

            conn.close()

        return {
            **stats,
            "success_rate": successful / total if total > 0 else 0,
            "user_preferences": len(preferences),
            "pattern_categories": pattern_stats,
            "learning_active": True,
        }

    def connect_to_remote_memory_server(self, url: str, timeout: int = 15) -> Dict[str, Any]:
        """Connect to a remote memory server via HTTP and fetch graph data.

        Expects the server to return JSON graph data with edges/nodes.
        Returns a dict with 'success', 'data', and 'error' if applicable.
        """
        if not HAS_REQUESTS:
            return {
                "success": False,
                "error": "requests library not available. Install with: pip install requests",
                "data": None
            }

        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "data": data,
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "error": f"Server responded with status {response.status_code}: {response.text}",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error connecting to remote memory server: {e}",
                "data": None
            }

    def sync_remote_graph(self, url: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """Sync remote graph data into local database.

        If url is not provided, uses self.remote_memory_url.
        If force is True, syncs even if recently synced.
        Returns sync result.
        """
        remote_url = url or self.remote_memory_url
        if not remote_url:
            return {"success": False, "error": "No remote memory URL configured", "synced_count": 0}

        # Check if recently synced (unless force)
        if not force:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM remote_graph WHERE updated_at > datetime('now', '-1 hour')")
                recent_count = cursor.fetchone()[0]
                conn.close()
            if recent_count > 0:
                return {"success": True, "message": "Recently synced, skipping", "synced_count": 0}

        # Fetch remote data
        result = self.connect_to_remote_memory_server(remote_url)
        if not result["success"]:
            return result

        data = result["data"]
        if not isinstance(data, list):
            return {"success": False, "error": "Remote data is not a list of edges", "synced_count": 0}

        synced_count = 0
        now = datetime.now().isoformat()

        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            for edge in data:
                if not isinstance(edge, dict):
                    continue
                source = edge.get("source")
                target = edge.get("target")
                edge_type = edge.get("type")
                strength = edge.get("strength")
                order_index = edge.get("order")
                purpose = edge.get("purpose")

                if not source or not target or not edge_type:
                    continue

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO remote_graph
                    (source, target, type, strength, order_index, purpose, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (source, target, edge_type, strength, order_index, purpose, now)
                )
                synced_count += 1

            conn.commit()
            conn.close()

        return {"success": True, "synced_count": synced_count, "message": f"Synced {synced_count} edges"}

    def get_remote_graph_edges(self, source: Optional[str] = None, target: Optional[str] = None, edge_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get remote graph edges, optionally filtered."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            query = "SELECT source, target, type, strength, order_index, purpose, updated_at FROM remote_graph WHERE 1=1"
            params = []

            if source:
                query += " AND source = ?"
                params.append(source)
            if target:
                query += " AND target = ?"
                params.append(target)
            if edge_type:
                query += " AND type = ?"
                params.append(edge_type)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            conn.close()

            columns = ["source", "target", "type", "strength", "order_index", "purpose", "updated_at"]
            return [dict(zip(columns, row)) for row in rows]

    def find_related_projects(self, project_name: str) -> List[str]:
        """Find projects related to a given project through the graph."""
        edges = self.get_remote_graph_edges()
        related = set()

        # Find projects in same workspace
        for edge in edges:
            if edge['type'] == 'contains' and edge['target'] == project_name:
                workspace = edge['source']
                # Find other projects in same workspace
                for e in edges:
                    if e['source'] == workspace and e['target'] != project_name and e['type'] == 'contains':
                        related.add(e['target'])

        return list(related)

    def get_project_context(self, project_name: str) -> Dict[str, Any]:
        """Get comprehensive context for a project from the graph."""
        context = {
            'project': project_name,
            'workspace': None,
            'related_projects': [],
            'configurations': [],
            'resources': [],
            'purpose': None
        }

        edges = self.get_remote_graph_edges()

        # Find the actual project node (could be 'project_llamamachinery' for 'llamamachinery')
        actual_project_name = None
        for edge in edges:
            if project_name in edge['source'] or project_name in edge['target']:
                if 'project_' in edge['source'] and project_name in edge['source']:
                    actual_project_name = edge['source']
                    break
                elif 'project_' in edge['target'] and project_name in edge['target']:
                    actual_project_name = edge['target']
                    break

        # If no exact match, try partial match
        if not actual_project_name:
            for edge in edges:
                if project_name.lower() in edge['source'].lower() or project_name.lower() in edge['target'].lower():
                    if edge['source'].startswith('project_'):
                        actual_project_name = edge['source']
                        break
                    elif edge['target'].startswith('project_'):
                        actual_project_name = edge['target']
                        break

        # If still no match, use the original name
        if not actual_project_name:
            actual_project_name = project_name

        # Now search for context using the actual project name
        for edge in edges:
            if edge['target'] == actual_project_name:
                if edge['type'] == 'contains':
                    context['workspace'] = edge['source']
                elif edge['type'] == 'uses':
                    context['resources'].append({
                        'resource': edge['target'],
                        'purpose': edge.get('purpose')
                    })
            elif edge['source'] == actual_project_name:
                if edge['type'] == 'enables':
                    context['purpose'] = f"Enables {edge['target']}"

        # Find related projects
        context['related_projects'] = self.find_related_projects(actual_project_name)

        return context

    def get_workspace_overview(self) -> Dict[str, Any]:
        """Get overview of entire workspace from graph."""
        edges = self.get_remote_graph_edges()
        workspaces = {}

        for edge in edges:
            if edge['type'] == 'contains':
                ws = edge['source']
                if ws not in workspaces:
                    workspaces[ws] = {'projects': [], 'configurations': []}
                workspaces[ws]['projects'].append(edge['target'])
            elif edge['type'] == 'configures':
                ws = edge['source']
                if ws not in workspaces:
                    workspaces[ws] = {'projects': [], 'configurations': []}
                workspaces[ws]['configurations'].append(edge['target'])

        return workspaces


# Global instance
_memory_service = None
_memory_lock = threading.Lock()


def get_memory_service() -> AUAMemoryService:
    """Get the global memory service instance"""
    global _memory_service
    if _memory_service is None:
        with _memory_lock:
            if _memory_service is None:
                _memory_service = AUAMemoryService()
    return _memory_service


# Convenience functions for easy integration
def log_interaction(*args: Any, **kwargs: Any) -> None:
    """Convenience function to log interactions"""
    get_memory_service().log_interaction(*args, **kwargs)


def start_session(*args: Any, **kwargs: Any) -> str:
    """Convenience function to start sessions"""
    return get_memory_service().start_session(*args, **kwargs)


def end_session(*args: Any, **kwargs: Any) -> None:
    """Convenience function to end sessions"""
    get_memory_service().end_session(*args, **kwargs)
