"""
LLM Client for llamamachinery framework.
Provides unified interface for text and vision LLM operations.
"""

import os
import requests
import logging
import json as _json
from typing import Dict, Any, Optional


def build_chat_completions_payload(user_content: str, model: str, system: Optional[str] = None) -> Dict[str, Any]:
    """Build payload for chat completions API."""
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user_content})

    return {
        "model": model,
        "messages": messages
    }


def build_vision_chat_payload(user_text: str, image_data_url: str, model: str, system: Optional[str] = None) -> Dict[str, Any]:
    """Build payload for vision chat API."""
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})

    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_data_url}}
        ]
    })

    return {
        "model": model,
        "messages": messages
    }


class LLMClient:
    """Client for interacting with Llama models via API."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        # Prefer explicit LLAMA_API_URL, fall back to Netlify dev/prod defaults.
        env_url = os.environ.get("LLAMA_API_URL")
        if env_url:
            base_url = env_url
        else:
            # If running under Netlify dev, default to local dev function URL.
            if os.environ.get("NETLIFY_DEV") == "true":
                base_url = "http://localhost:8888/.netlify/functions/llama-proxy"
            else:
                # Production Netlify deployment default
                base_url = "https://llama-universal-netlify-project.netlify.app/.netlify/functions/llama-proxy"

        self.base_url = base_url
        self.api_key = os.environ.get('LLAMA_API_KEY')
        self.default_model = os.environ.get('LLAMA_MODEL', 'Llama-4-Scout-17B-16E-Instruct-FP8')
        self.logger = logging.getLogger(__name__)

    def generate(self, prompt: str, system: Optional[str] = None, max_tokens: int = 1000, temperature: float = 0.7, **kwargs: Any) -> str:
        """
        Generate text response from LLM.

        Args:
            prompt: The user prompt
            system: System message (optional)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Returns:
            Generated text response
        """
        try:
            model: str = kwargs.get('model', self.default_model)
            payload = build_chat_completions_payload(
                user_content=prompt,
                model=model,
                system=system
            )
            payload.update({
                'max_tokens': max_tokens,
                'temperature': temperature,
                **kwargs
            })
            headers = {'Content-Type': 'application/json'}
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            proxy_url = f"{self.base_url}?path=/chat/completions"
            self.logger.info(f"LLMClient.generate: POST {proxy_url}\nPayload: {_json.dumps(payload)}")
            response = requests.post(
                proxy_url,
                json=payload,
                headers=headers,
                timeout=60
            )
            self.logger.info(f"LLMClient.generate: Response {response.status_code}\n{response.text}")
            if response.status_code == 200:
                result = response.json()
                return _json.dumps(result)
            else:
                error_message = f"API Error: {response.status_code} - {response.text}"
                self.logger.error(error_message)
                raise requests.exceptions.RequestException(error_message)
        except Exception as e:
            self.logger.error(f"LLMClient.generate: Exception {type(e).__name__}: {e}")
            raise


def get_llm_client(config: Optional[Dict[str, Any]] = None) -> LLMClient:
    """
    Factory function to get LLM client instance.

    Args:
        config: Optional configuration dictionary

    Returns:
        LLMClient instance
    """
    return LLMClient(config)
