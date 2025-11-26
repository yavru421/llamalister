"""
Network operations for AutonomousUserAgent.

This module handles network-related operations including downloads and HTTP requests.
"""

import os
import urllib.request
from typing import Dict, Union
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
from . import BaseOperations, OperationResult


class NetworkOperations(BaseOperations):
    """Handles network operations"""

    def download_file(self, url: str, destination: str) -> OperationResult:
        """Download file from URL"""
        try:
            if not destination:
                destination = os.path.basename(url)
            destination = self._ensure_absolute_path(destination)

            self._log_operation("download_file", f"{url} -> {destination}")
            urllib.request.urlretrieve(url, destination)

            return OperationResult(True, f"Downloaded {url} to {destination} successfully")
        except Exception as e:
            return OperationResult(False, f"Error downloading file: {e}")

    def http_get(self, url: str, headers: Dict[str, str], timeout: int = 10) -> OperationResult:
        """Make HTTP GET request with timeout"""
        try:
            self._log_operation("http_get", url)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode('utf-8')
                return OperationResult(True, f"HTTP GET {url} response:\n{content[:2000]}", content)  # Limit output
        except Exception as e:
            return OperationResult(False, f"Error making HTTP GET request: {e}")

    def http_post(self, url: str, data: Union[str, bytes], headers: Dict[str, str], timeout: int = 10) -> OperationResult:
        """Make HTTP POST request with timeout"""
        try:
            self._log_operation("http_post", url)
            if isinstance(data, str):
                data = data.encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method='POST')
            with urllib.request.urlopen(req, timeout=timeout) as response:
                content = response.read().decode('utf-8')
                return OperationResult(True, f"HTTP POST {url} response:\n{content[:2000]}", content)  # Limit output
        except Exception as e:
            return OperationResult(False, f"Error making HTTP POST request: {e}")

    def connect_to_tor_memory_server(
        self,
        url: str,
        proxy_host: str = "127.0.0.1",
        proxy_port: int = 9050,
        timeout: int = 15,
        verify_ssl: bool = True,
    ) -> OperationResult:
        """Attempt to connect to a Tor .onion memory server through a SOCKS5 proxy.

        This method requires `requests` with socks support (requests[socks] / PySocks).
        It will try to route the request through the provided SOCKS proxy and return
        an OperationResult with the status and a snippet of the response.
        """
        if not HAS_REQUESTS:
            return OperationResult(
                False,
                "The requests library is not available. Install with: pip install requests[socks]",
            )

        try:
            proxies = {
                "http": f"socks5h://{proxy_host}:{proxy_port}",
                "https": f"socks5h://{proxy_host}:{proxy_port}",
            }

            self._log_operation("connect_to_tor_memory_server", f"url={url} proxy={proxy_host}:{proxy_port}")

            # If the target is an onion address, ensure socks5h is used for name resolution
            # requests will raise InvalidSchema if socks is not installed
            try:
                resp = requests.get(url, proxies=proxies, timeout=timeout, verify=verify_ssl)
            except Exception as e:
                # Provide an informative error if PySocks is missing
                from requests.exceptions import InvalidSchema

                if isinstance(e, InvalidSchema):
                    return OperationResult(
                        False,
                        "Invalid schema - PySocks (socks) dependency is required for Tor SOCKS support. Install with: pip install pysocks",
                    )
                return OperationResult(False, f"Error connecting via Tor: {e}")

            if resp.status_code == 200:
                return OperationResult(True, f"Connected to Tor memory server {url} (200).", resp.text[:2000])
            else:
                return OperationResult(False, f"Tor server responded with status {resp.status_code}: {resp.text[:400]}")
        except Exception as e:
            return OperationResult(False, f"Unexpected error connecting to Tor memory server: {e}")
