"""MCP client for communicating with MCP servers via HTTP or stdio."""

import subprocess
import json
import os
import threading
import requests
from typing import Any
from dataclasses import dataclass, field

from framework.mcp.config import MCPServerConfig


@dataclass
class MCPToolResult:
    """Result from an MCP tool call."""
    success: bool
    content: Any
    error: str | None = None


@dataclass
class MCPTool:
    """An MCP tool definition."""
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)


class MCPHttpClient:
    """Client for interacting with MCP servers via HTTP.

    Used for Docker-based MCP servers that expose HTTP endpoints.
    """

    def __init__(self, base_url: str, name: str = "unknown"):
        self.base_url = base_url.rstrip('/')
        self.name = name
        self._tools: list[MCPTool] = []
        self._initialized = False
        self._request_id = 0

    def start(self) -> None:
        """Initialize the MCP connection."""
        self._initialize()

    def stop(self) -> None:
        """No cleanup needed for HTTP client."""
        self._initialized = False
        self._tools = []

    def _send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC 2.0 request via HTTP."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        try:
            response = requests.post(
                f"{self.base_url}/message",
                json=request,
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "error": {"code": -32000, "message": str(e)}
            }

    def _initialize(self) -> None:
        """Initialize the MCP connection."""
        response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "agentic-benchmark", "version": "1.0.0"},
        })

        if "error" in response:
            raise RuntimeError(f"MCP initialize failed: {response['error']}")

        # Send initialized notification
        self._send_request("notifications/initialized")

        self._initialized = True
        self._fetch_tools()

    def _fetch_tools(self) -> None:
        """Fetch available tools from the MCP server."""
        response = self._send_request("tools/list")

        if "error" in response:
            raise RuntimeError(f"Failed to list tools: {response['error']}")

        tools_data = response.get("result", {}).get("tools", [])
        self._tools = [
            MCPTool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    def list_tools(self) -> list[MCPTool]:
        """List available tools."""
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """Call a tool on the MCP server."""
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        try:
            response = self._send_request("tools/call", {
                "name": name,
                "arguments": arguments,
            })

            if "error" in response:
                return MCPToolResult(
                    success=False,
                    content=None,
                    error=response["error"].get("message", str(response["error"])),
                )

            result = response.get("result", {})
            content = result.get("content", [])

            # Extract text content
            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)

            return MCPToolResult(
                success=True,
                content="\n".join(text_parts) if text_parts else result,
            )

        except Exception as e:
            return MCPToolResult(
                success=False,
                content=None,
                error=str(e),
            )

    def __enter__(self) -> "MCPHttpClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


class MCPStdioClient:
    """Client for interacting with MCP servers via stdio.

    Used for local MCP servers spawned as subprocesses.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: subprocess.Popen | None = None
        self._request_id = 0
        self._tools: list[MCPTool] = []
        self._initialized = False
        self._stderr_thread: threading.Thread | None = None
        self._stderr_output: list[str] = []

    def start(self) -> None:
        """Start the MCP server process and initialize."""
        env = {**os.environ, **self.config.env}

        self.process = subprocess.Popen(
            [self.config.command] + self.config.args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )

        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

        self._initialize()

    def _read_stderr(self) -> None:
        """Read stderr in background thread."""
        if self.process and self.process.stderr:
            for line in self.process.stderr:
                self._stderr_output.append(line.strip())

    def stop(self) -> None:
        """Stop the MCP server process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
        self._initialized = False
        self._tools = []

    def _send_request(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC 2.0 request to the MCP server."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise RuntimeError("MCP server not started")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params is not None:
            request["params"] = params

        request_str = json.dumps(request) + "\n"
        self.process.stdin.write(request_str)
        self.process.stdin.flush()

        response_line = self.process.stdout.readline()
        if not response_line:
            stderr_info = "\n".join(self._stderr_output[-10:]) if self._stderr_output else "No stderr"
            raise RuntimeError(f"No response from MCP server. Stderr: {stderr_info}")

        return json.loads(response_line)

    def _send_notification(self, method: str, params: dict | None = None) -> None:
        """Send a JSON-RPC 2.0 notification."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP server not started")

        notification = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            notification["params"] = params

        notification_str = json.dumps(notification) + "\n"
        self.process.stdin.write(notification_str)
        self.process.stdin.flush()

    def _initialize(self) -> None:
        """Initialize the MCP connection."""
        response = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "clientInfo": {"name": "agentic-benchmark", "version": "1.0.0"},
        })

        if "error" in response:
            raise RuntimeError(f"MCP initialize failed: {response['error']}")

        self._send_notification("notifications/initialized")
        self._initialized = True
        self._fetch_tools()

    def _fetch_tools(self) -> None:
        """Fetch available tools."""
        response = self._send_request("tools/list")

        if "error" in response:
            raise RuntimeError(f"Failed to list tools: {response['error']}")

        tools_data = response.get("result", {}).get("tools", [])
        self._tools = [
            MCPTool(
                name=t.get("name", ""),
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in tools_data
        ]

    def list_tools(self) -> list[MCPTool]:
        """List available tools."""
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")
        return self._tools

    def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """Call a tool on the MCP server."""
        if not self._initialized:
            raise RuntimeError("MCP client not initialized")

        try:
            response = self._send_request("tools/call", {
                "name": name,
                "arguments": arguments,
            })

            if "error" in response:
                return MCPToolResult(
                    success=False,
                    content=None,
                    error=response["error"].get("message", str(response["error"])),
                )

            result = response.get("result", {})
            content = result.get("content", [])

            text_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
                elif isinstance(item, str):
                    text_parts.append(item)

            return MCPToolResult(
                success=True,
                content="\n".join(text_parts) if text_parts else result,
            )

        except Exception as e:
            return MCPToolResult(
                success=False,
                content=None,
                error=str(e),
            )

    def __enter__(self) -> "MCPStdioClient":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


class MCPClientManager:
    """Manages multiple MCP server connections (both HTTP and stdio)."""

    def __init__(self):
        self.clients: dict[str, MCPHttpClient | MCPStdioClient] = {}

    def add_http_server(self, name: str, base_url: str) -> None:
        """Add and connect to an HTTP-based MCP server."""
        client = MCPHttpClient(base_url, name)
        client.start()
        self.clients[name] = client

    def add_stdio_server(self, config: MCPServerConfig) -> None:
        """Add and start a stdio-based MCP server."""
        client = MCPStdioClient(config)
        client.start()
        self.clients[config.name] = client

    def get_client(self, name: str) -> MCPHttpClient | MCPStdioClient | None:
        """Get an MCP client by name."""
        return self.clients.get(name)

    def list_all_tools(self) -> dict[str, list[MCPTool]]:
        """List all tools from all connected servers."""
        return {
            name: client.list_tools()
            for name, client in self.clients.items()
        }

    def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> MCPToolResult:
        """Call a tool on a specific server."""
        client = self.clients.get(server_name)
        if not client:
            return MCPToolResult(
                success=False,
                content=None,
                error=f"Server '{server_name}' not found",
            )
        return client.call_tool(tool_name, arguments)

    def close(self) -> None:
        """Close all MCP server connections."""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()

    def __enter__(self) -> "MCPClientManager":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
