"""Ollama client for local LLM inference."""

import json
import requests
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass
class OllamaConfig:
    """Configuration for Ollama client."""
    base_url: str = "http://localhost:11434"
    model: str = "llama3.2"
    temperature: float = 0.1
    timeout: int = 300  # 5 minutes for complex tool calls


@dataclass
class ChatMessage:
    """A chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class ToolDefinition:
    """Definition of a tool available to the agent."""
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_ollama_format(self) -> dict:
        """Convert to Ollama tool format."""
        # Remove 'required' from parameters - some models (like Qwen3) get confused
        # by required fields and refuse to call tools without all params specified
        params = dict(self.parameters) if self.parameters else {}
        if "required" in params:
            params = {k: v for k, v in params.items() if k != "required"}

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": params,
            }
        }


class OllamaClient:
    """Client for Ollama API."""

    def __init__(self, config: OllamaConfig | None = None):
        self.config = config or OllamaConfig()

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        stream: bool = False,
    ) -> ChatMessage:
        """Send a chat completion request to Ollama."""
        url = f"{self.config.base_url}/api/chat"

        # Build messages, handling tool messages specially
        formatted_messages = []
        for m in messages:
            msg = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg["tool_calls"] = m.tool_calls
            formatted_messages.append(msg)

        payload = {
            "model": self.config.model,
            "messages": formatted_messages,
            "stream": stream,
            "options": {
                "temperature": self.config.temperature,
            },
        }

        if tools:
            payload["tools"] = [t.to_ollama_format() for t in tools]

        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.config.timeout,
                )
                response.raise_for_status()
                break  # Success, exit retry loop
            except requests.exceptions.Timeout as e:
                last_error = f"Request timed out after {self.config.timeout}s (attempt {attempt + 1}/{max_retries})"
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise RuntimeError(last_error) from e
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error (attempt {attempt + 1}/{max_retries}): {e}"
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(last_error) from e
            except requests.exceptions.HTTPError as e:
                # Try to get more details about the error
                error_detail = ""
                try:
                    error_detail = response.text
                except Exception:
                    pass
                raise RuntimeError(f"Ollama API error: {e}. Details: {error_detail}") from e

        data = response.json()
        message = data.get("message", {})

        return ChatMessage(
            role=message.get("role", "assistant"),
            content=message.get("content", ""),
            tool_calls=message.get("tool_calls"),
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
        )

    def generate(self, prompt: str) -> str:
        """Simple text generation."""
        url = f"{self.config.base_url}/api/generate"

        response = requests.post(
            url,
            json={
                "model": self.config.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.config.temperature,
                },
            },
            timeout=self.config.timeout,
        )
        response.raise_for_status()

        return response.json().get("response", "")

    def list_models(self) -> list[str]:
        """List available models."""
        url = f"{self.config.base_url}/api/tags"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        models = response.json().get("models", [])
        return [m.get("name", "") for m in models]

    def is_available(self) -> bool:
        """Check if Ollama is available."""
        try:
            response = requests.get(
                f"{self.config.base_url}/api/tags",
                timeout=5,
            )
            return response.status_code == 200
        except Exception:
            return False
