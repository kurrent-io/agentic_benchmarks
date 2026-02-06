"""Claude (Anthropic) client for LLM inference."""

import os
from dataclasses import dataclass, field
from typing import Any

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from framework.agents.ollama import ChatMessage, ToolDefinition


@dataclass
class ClaudeConfig:
    """Configuration for Claude client."""
    api_key: str | None = None  # If None, uses ANTHROPIC_API_KEY env var
    # Claude Sonnet 4.0 - same pricing as 3.5 ($3/$15 per 1M tokens)
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.1
    max_tokens: int = 4096


class ClaudeClient:
    """Client for Anthropic Claude API."""

    def __init__(self, config: ClaudeConfig | None = None):
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        self.config = config or ClaudeConfig()
        api_key = self.config.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")

        self.client = anthropic.Anthropic(api_key=api_key)

    def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
        stream: bool = False,
    ) -> ChatMessage:
        """Send a chat completion request to Claude."""
        # Separate system message from conversation
        system_content = None
        conversation = []

        for m in messages:
            if m.role == "system":
                system_content = m.content
            elif m.role == "tool":
                # Convert tool response to Claude format
                conversation.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "unknown",
                        "content": m.content,
                    }]
                })
            elif m.role == "assistant" and m.tool_calls:
                # Assistant message with tool calls
                content = []
                if m.content:
                    content.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    func = tc.get("function", {})
                    content.append({
                        "type": "tool_use",
                        "id": tc.get("id", func.get("name", "unknown")),
                        "name": func.get("name", ""),
                        "input": func.get("arguments", {}),
                    })
                conversation.append({"role": "assistant", "content": content})
            else:
                conversation.append({"role": m.role, "content": m.content})

        # Build Claude tools format
        claude_tools = None
        if tools:
            claude_tools = []
            for t in tools:
                claude_tools.append({
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters if t.parameters else {"type": "object", "properties": {}},
                })

        # Make API call
        kwargs = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": conversation,
        }

        if system_content:
            kwargs["system"] = system_content
        if claude_tools:
            kwargs["tools"] = claude_tools
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature

        response = self.client.messages.create(**kwargs)

        # Parse response
        content_text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "function": {
                        "name": block.name,
                        "arguments": block.input,
                    }
                })

        return ChatMessage(
            role="assistant",
            content=content_text,
            tool_calls=tool_calls if tool_calls else None,
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
        )

    def generate(self, prompt: str) -> str:
        """Simple text generation."""
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.config.temperature,
        )

        return response.content[0].text if response.content else ""

    def is_available(self) -> bool:
        """Check if Claude API is available."""
        try:
            # Try a minimal API call
            self.client.messages.create(
                model=self.config.model,
                max_tokens=10,
                messages=[{"role": "user", "content": "hi"}],
            )
            return True
        except Exception:
            return False
