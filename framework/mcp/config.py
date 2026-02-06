"""MCP server configuration for database access."""

from dataclasses import dataclass, field
from typing import Any
import json
from pathlib import Path


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class MCPConfig:
    """Configuration for all MCP servers used in the benchmark."""
    servers: dict[str, MCPServerConfig] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "MCPConfig":
        """Create default MCP configuration for benchmark databases."""
        return cls(
            servers={
                # Official PostgreSQL MCP server
                "postgres": MCPServerConfig(
                    name="postgres",
                    command="npx",
                    args=[
                        "-y",
                        "@modelcontextprotocol/server-postgres",
                        "postgresql://bench:bench@localhost:5432/benchmark",
                    ],
                ),
                # Official Filesystem MCP server (for reading schemas, etc.)
                "filesystem": MCPServerConfig(
                    name="filesystem",
                    command="npx",
                    args=[
                        "-y",
                        "@modelcontextprotocol/server-filesystem",
                        ".",
                    ],
                ),
            }
        )

    @classmethod
    def for_benchmark(
        cls,
        postgres_url: str = "postgresql://bench:bench@localhost:5432/benchmark",
        kurrentdb_url: str = "kurrentdb://localhost:2113?tls=false",
    ) -> "MCPConfig":
        """Create MCP configuration for all benchmark databases."""
        return cls(
            servers={
                # Official PostgreSQL MCP server (handles CRUD, CDC, Events, TimeSeries schemas)
                "postgres": MCPServerConfig(
                    name="postgres",
                    command="npx",
                    args=[
                        "-y",
                        "@modelcontextprotocol/server-postgres",
                        postgres_url,
                    ],
                ),
            }
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "MCPConfig":
        """Load MCP configuration from a JSON file."""
        with open(path) as f:
            data = json.load(f)

        servers = {}
        for name, config in data.get("mcpServers", {}).items():
            servers[name] = MCPServerConfig(
                name=name,
                command=config.get("command", ""),
                args=config.get("args", []),
                env=config.get("env", {}),
            )

        return cls(servers=servers)

    def to_claude_config(self) -> dict:
        """Convert to Claude MCP config format."""
        return {
            "mcpServers": {
                name: {
                    "command": server.command,
                    "args": server.args,
                    "env": server.env,
                }
                for name, server in self.servers.items()
            }
        }

    def save(self, path: str | Path) -> None:
        """Save MCP configuration to a JSON file."""
        with open(path, "w") as f:
            json.dump(self.to_claude_config(), f, indent=2)
