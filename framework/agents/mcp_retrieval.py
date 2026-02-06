"""MCP-based retrieval agent that answers questions using Docker MCP servers."""

import json
from dataclasses import dataclass, field
from typing import Any

from framework.agents.ollama import OllamaClient, OllamaConfig, ChatMessage, ToolDefinition

# Optional Claude support
try:
    from framework.agents.claude import ClaudeClient, ClaudeConfig
    CLAUDE_AVAILABLE = True
except ImportError:
    CLAUDE_AVAILABLE = False
    ClaudeClient = None
    ClaudeConfig = None
from framework.mcp.client import MCPClientManager, MCPTool


# Default MCP server URLs (Docker containers)
DEFAULT_MCP_SERVERS = {
    "postgres": "http://localhost:3000",
    "kurrentdb": "http://localhost:3003",
}


@dataclass
class MCPRetrievalResult:
    """Result from the MCP retrieval agent."""
    question: str
    answer: str
    reasoning: str
    tools_called: list[dict] = field(default_factory=list)
    raw_results: list[Any] = field(default_factory=list)
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class MCPRetrievalAgent:
    """Agent that retrieves information from databases via MCP servers.

    Uses Docker-based MCP servers for database access:
    - mcp-postgres: PostgreSQL via official @modelcontextprotocol/server-postgres
    - mcp-kurrentdb: KurrentDB event store via official kurrent-io/mcp-server
    """

    SYSTEM_PROMPT_BASE = """You are a data retrieval agent. Answer questions by querying databases using ONLY the tools available to you.

CRITICAL: Only use tools that are listed in your available tools. Do NOT attempt to call tools that don't exist.

{db_instructions}

INSTRUCTIONS:
1. Provide a definitive answer. Never ask "Would you like me to proceed?" - just proceed.
2. If a query returns null or empty results, try alternative queries.
3. Keep querying until you have a concrete answer (a number, a name, a list, etc.)
4. NEVER give up or ask permission. Investigate and find the answer."""

    POSTGRES_INSTRUCTIONS = """You have access to **PostgreSQL** via SQL queries.
- Data is stored in JSONB 'data' column alongside an 'id' column.
- Use schema-qualified table names: {domain}.{entity}s
- Extract values with: data->>'field_name'"""

    CDC_INSTRUCTIONS = """You have access to **PostgreSQL+CDC** (Change Data Capture) via SQL queries.
- CDC events are in cdc.cdc_events table with columns: entity_type, entity_id, op, before_state (JSONB), after_state (JSONB), ts_ms
- before_state has the previous values, after_state has the new values
- Use: SELECT * FROM cdc.cdc_events WHERE entity_id = '...' AND entity_type = '...'"""

    KURRENTDB_INSTRUCTIONS = """You have access to **KurrentDB** (event sourcing database).
- Read events from a stream using read_stream with the stream name
- Stream names follow the pattern: {entity_type}-{entity_id}
- Events contain 'previous', 'current', and 'reason' fields in their data"""

    def __init__(
        self,
        ollama_config: OllamaConfig | None = None,
        mcp_servers: dict[str, str] | None = None,
        llm_client: OllamaClient | None = None,
        use_claude: bool = False,
        claude_config: "ClaudeConfig | None" = None,
    ):
        """Initialize the MCP retrieval agent.

        Args:
            ollama_config: Configuration for Ollama LLM (deprecated, use llm_client)
            mcp_servers: Dict mapping server names to HTTP URLs
                         e.g., {"postgres": "http://localhost:3000"}
            llm_client: Pre-configured LLM client (OllamaClient or ClaudeClient)
            use_claude: If True, use Claude instead of Ollama
            claude_config: Configuration for Claude (only used if use_claude=True)
        """
        if llm_client:
            self.llm = llm_client
        elif use_claude:
            if not CLAUDE_AVAILABLE:
                raise ImportError("Claude not available. Run: pip install anthropic")
            self.llm = ClaudeClient(claude_config or ClaudeConfig())
        else:
            self.llm = OllamaClient(ollama_config or OllamaConfig())

        self.mcp_servers = mcp_servers or DEFAULT_MCP_SERVERS
        self.mcp_manager: MCPClientManager | None = None
        self._ollama_tools: list[ToolDefinition] = []
        self._tool_mapping: dict[str, tuple[str, str]] = {}  # clean_name -> (server, original_name)
        self._system_prompt: str = ""

    def start(self) -> None:
        """Connect to MCP servers and initialize tools."""
        self.mcp_manager = MCPClientManager()

        # Connect to each MCP server
        for name, url in self.mcp_servers.items():
            try:
                self.mcp_manager.add_http_server(name, url)
                print(f"Connected to MCP server: {name} at {url}")
            except Exception as e:
                print(f"Warning: Failed to connect to MCP server '{name}' at {url}: {e}")

        # Build Ollama tool definitions from MCP tools
        self._build_ollama_tools()

        # Build dynamic system prompt based on connected servers
        self._build_system_prompt()

    def _build_ollama_tools(self) -> None:
        """Convert MCP tools to Ollama tool definitions."""
        if not self.mcp_manager:
            return

        self._ollama_tools = []

        for server_name, tools in self.mcp_manager.list_all_tools().items():
            for tool in tools:
                # Clean up the tool name for Ollama compatibility
                # Use single underscore separator and ensure alphanumeric names
                clean_server = server_name.replace("-", "").replace("_", "")
                clean_tool = tool.name.replace("-", "_").replace(" ", "_")
                tool_name = f"{clean_server}_{clean_tool}"

                # Ensure parameters have the required JSON schema structure
                params = tool.input_schema or {}
                if "type" not in params:
                    params = {
                        "type": "object",
                        "properties": params.get("properties", {}),
                        "required": params.get("required", []),
                    }

                # Create Ollama tool definition with server prefix
                ollama_tool = ToolDefinition(
                    name=tool_name,
                    description=f"[{server_name}] {tool.description}",
                    parameters=params,
                )
                self._ollama_tools.append(ollama_tool)

                # Store mapping from clean name to original
                self._tool_mapping[tool_name] = (server_name, tool.name)

        print(f"Loaded {len(self._ollama_tools)} tools from MCP servers")

    def _build_system_prompt(self) -> None:
        """Build system prompt based on which MCP servers are actually connected."""
        server_names = set(self.mcp_servers.keys())
        instructions = []

        if "postgres" in server_names:
            instructions.append(self.POSTGRES_INSTRUCTIONS)
        if "postgres_cdc" in server_names:
            instructions.append(self.CDC_INSTRUCTIONS)
        if "kurrentdb" in server_names:
            instructions.append(self.KURRENTDB_INSTRUCTIONS)

        self._system_prompt = self.SYSTEM_PROMPT_BASE.format(
            db_instructions="\n\n".join(instructions)
        )

    def _execute_mcp_tool(self, full_tool_name: str, arguments: dict) -> str:
        """Execute an MCP tool and return the result."""
        if not self.mcp_manager:
            return json.dumps({"error": "MCP manager not initialized"})

        # Look up in tool mapping first
        if full_tool_name in self._tool_mapping:
            server_name, tool_name = self._tool_mapping[full_tool_name]
        elif "__" in full_tool_name:
            # Legacy format with double underscore
            server_name, tool_name = full_tool_name.split("__", 1)
        elif "_" in full_tool_name:
            # Try to parse single underscore format
            # Find the matching tool by prefix matching
            for clean_name, (server, orig) in self._tool_mapping.items():
                if full_tool_name == clean_name:
                    server_name, tool_name = server, orig
                    break
            else:
                # Default to postgres if no match
                server_name = "postgres"
                tool_name = full_tool_name
        else:
            # Default to postgres if no prefix
            server_name = "postgres"
            tool_name = full_tool_name

        result = self.mcp_manager.call_tool(server_name, tool_name, arguments)

        if result.success:
            content = str(result.content) if result.content else "Query executed successfully"
            # Special handling for list_streams to help LLM process the result
            if tool_name == "list_streams" and content:
                # Count streams by prefix to help the model
                lines = content.strip().split('\n') if '\n' in content else content.split(',')
                stream_names = [s.strip() for s in lines if s.strip()]
                prefix_counts = {}
                for name in stream_names:
                    prefix = name.split('-')[0] + '-' if '-' in name else name
                    prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
                content = f"TOOL RESULT - LIST OF {len(stream_names)} STREAMS:\n{content}\n\nSUMMARY OF STREAM COUNTS BY PREFIX:\n"
                for prefix, count in sorted(prefix_counts.items()):
                    content += f"  - Streams starting with '{prefix}': {count}\n"
                content += f"\nNow answer the original question by looking at the counts above."
            # Special handling for read_stream to count events automatically
            elif tool_name == "read_stream" and "An event of type:" in content:
                event_count = content.count("An event of type:")
                # Add count summary at the beginning
                content = f"TOOL RESULT - STREAM CONTAINS {event_count} EVENTS:\n\n{content}\n\n=== SUMMARY ===\nTOTAL EVENT COUNT: {event_count}\n\nThe answer to 'how many' is: {event_count}"
            return content
        else:
            return json.dumps({"error": result.error})

    def answer(self, question: str, max_iterations: int = 10) -> MCPRetrievalResult:
        """Answer a question by querying databases via MCP."""
        if not self.mcp_manager:
            self.start()

        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=f"Question: {question}\n\nPlease query the appropriate database to find the answer."),
        ]

        tools_called = []
        raw_results = []
        reasoning_parts = []
        total_prompt_tokens = 0
        total_completion_tokens = 0

        for iteration in range(max_iterations):
            # Get response from LLM with MCP tools
            try:
                response = self.llm.chat(messages, tools=self._ollama_tools)
                total_prompt_tokens += response.prompt_tokens
                total_completion_tokens += response.completion_tokens
            except Exception as e:
                error_msg = str(e)
                # Try to extract more details from common error types
                if hasattr(e, 'response'):
                    try:
                        error_msg = f"{e}: {e.response.text if hasattr(e.response, 'text') else e.response}"
                    except:
                        pass
                return MCPRetrievalResult(
                    question=question,
                    answer=f"Error during LLM inference: {error_msg[:200]}",
                    reasoning=f"Ollama error (iteration {iteration + 1}): {error_msg}",
                    tools_called=tools_called,
                    raw_results=raw_results,
                    error=error_msg,
                    prompt_tokens=total_prompt_tokens,
                    completion_tokens=total_completion_tokens,
                    total_tokens=total_prompt_tokens + total_completion_tokens,
                )
            messages.append(response)

            # Check if there are tool calls
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    func = tool_call.get("function", {})
                    tool_name = func.get("name", "")
                    arguments = func.get("arguments", {})

                    # Parse arguments if string
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}

                    # Execute MCP tool
                    tool_result = self._execute_mcp_tool(tool_name, arguments)

                    tools_called.append({
                        "tool": tool_name,
                        "arguments": arguments,
                        "iteration": iteration + 1,
                    })

                    try:
                        raw_results.append(json.loads(tool_result))
                    except (json.JSONDecodeError, TypeError):
                        raw_results.append(tool_result)

                    # Add tool result to messages
                    messages.append(ChatMessage(
                        role="tool",
                        content=tool_result,
                        tool_call_id=tool_call.get("id", ""),
                    ))

                    reasoning_parts.append(f"Iteration {iteration + 1}: Called {tool_name}")
            else:
                # No tool calls - check if agent is asking permission or showing uncertainty
                content = response.content.lower()
                uncertainty_phrases = [
                    "would you like me to",
                    "shall i",
                    "do you want me to",
                    "should i proceed",
                    "let me know if",
                    "i can investigate",
                    "i could check",
                ]

                if any(phrase in content for phrase in uncertainty_phrases):
                    # Agent is being hesitant - push it to continue
                    messages.append(ChatMessage(
                        role="user",
                        content="Yes, proceed with the investigation. Find the actual answer - do not ask for permission, just do it."
                    ))
                    reasoning_parts.append(f"Iteration {iteration + 1}: Pushed agent to continue investigating")
                else:
                    # Agent seems confident - we're done
                    break

        # Extract final answer
        final_response = messages[-1] if messages else None
        answer = final_response.content if final_response else "Unable to determine answer"

        # Clean up answer
        if "Answer:" in answer:
            answer = answer.split("Answer:")[-1].strip()

        return MCPRetrievalResult(
            question=question,
            answer=answer,
            reasoning="\n".join(reasoning_parts),
            tools_called=tools_called,
            raw_results=raw_results,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_prompt_tokens + total_completion_tokens,
        )

    def close(self) -> None:
        """Close MCP server connections."""
        if self.mcp_manager:
            self.mcp_manager.close()
            self.mcp_manager = None

    def __enter__(self) -> "MCPRetrievalAgent":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()
