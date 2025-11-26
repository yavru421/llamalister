#!/usr/bin/env python3
"""
Lightweight HTTP bridge that exposes the AutonomousUserAgent over a JSON API.
This allows external clients (e.g. the PowerShell GUI) to exchange messages with
the agent without embedding Python directly in the GUI implementation.
"""

from __future__ import annotations
import sys

# Enforce APT fatal mode for the bridge server
try:
    import strict_mode  # noqa: F401 - enable APT fatal mode
except ImportError:
    print("[APT FATAL ERROR] strict_mode module not found")
    sys.exit(1)

import json
import logging
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Tuple

# Ensure the src package is on the path when the bridge is launched from the repo root.
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, os.path.join(ROOT_DIR, "src"))
if os.path.dirname(ROOT_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(ROOT_DIR))

from src.agents.autonomous_user_agent import AutonomousUserAgent  # noqa: E402
from src.memory_service import get_memory_service, start_session, end_session  # noqa: E402


class AUABridgeRequestHandler(BaseHTTPRequestHandler):
    """Simple JSON API for interacting with the AutonomousUserAgent."""

    agent = AutonomousUserAgent()
    memory_service = get_memory_service()

    def _set_json_headers(self, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _read_request_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler naming)
        if self.path == "/health":
            self._set_json_headers()
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.wfile.write(payload)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler naming)
        if self.path != "/run":
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")
            return

        raw_body = self._read_request_body()
        command_text = ""
        if raw_body:
            try:
                parsed = json.loads(raw_body.decode("utf-8"))
                command_text = str(parsed.get("command", "")).strip()
            except json.JSONDecodeError:
                command_text = raw_body.decode("utf-8").strip()

        if not command_text:
            self._set_json_headers(HTTPStatus.BAD_REQUEST)
            payload = json.dumps({"error": "Empty message"}).encode("utf-8")
            self.wfile.write(payload)
            return

        try:
            response_text = self.agent.run(command_text)
            self._set_json_headers()
            payload = json.dumps({"response": response_text}).encode("utf-8")
            self.wfile.write(payload)

            # Log successful API interaction
            self.memory_service.log_interaction(
                interaction_type="api",
                method="run",
                user_input=command_text,
                agent_response=response_text,
                session_id=getattr(self.agent, 'current_session_id', None),
                success=True,
                metadata={"client_ip": self.client_address[0]}
            )

            # Learn from successful API interactions
            interaction_data = {
                'user_input': command_text,
                'agent_response': response_text,
                'success': True,
                'interaction_type': 'api',
                'method': 'run'
            }
            self.memory_service.learn_from_interaction(interaction_data)
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.exception("AUA bridge failed to process request")
            self._set_json_headers(HTTPStatus.INTERNAL_SERVER_ERROR)
            payload = json.dumps({"error": str(exc)}).encode("utf-8")
            self.wfile.write(payload)

            # Log failed API interaction
            self.memory_service.log_interaction(
                interaction_type="api",
                method="run",
                user_input=command_text,
                agent_response=str(exc),
                session_id=getattr(self.agent, 'current_session_id', None),
                success=False,
                error_message=str(exc),
                metadata={"client_ip": self.client_address[0]}
            )

    # Suppress the default console logging to keep output clean.
    def log_message(self, format: str, *args: Tuple[object, ...]) -> None:  # noqa: A003
        logging.info("%s - %s", self.address_string(), format % args)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    host = os.environ.get("AUA_BRIDGE_HOST", "127.0.0.1")
    port = int(os.environ.get("AUA_BRIDGE_PORT", "5055"))

    server = ThreadingHTTPServer((host, port), AUABridgeRequestHandler)
    logging.info("AUA bridge server running on http://%s:%s", host, port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down bridge server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
