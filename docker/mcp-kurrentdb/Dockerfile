# Official KurrentDB MCP Server with HTTP transport wrapper
FROM python:3.12-slim

WORKDIR /app

# Install git and curl for health checks
RUN apt-get update && apt-get install -y git curl && rm -rf /var/lib/apt/lists/*

# Clone official KurrentDB MCP server
RUN git clone https://github.com/kurrent-io/mcp-server.git /app/kurrentdb-mcp

# Install dependencies
RUN pip install --no-cache-dir -r /app/kurrentdb-mcp/requirements.txt

# Install additional dependencies for HTTP wrapper
RUN pip install --no-cache-dir flask

# Copy HTTP wrapper
COPY http_wrapper.py /app/http_wrapper.py

ENV MCP_PORT=3003
ENV KURRENTDB_CONNECTION_STRING=esdb://admin:changeit@kurrentdb:2113?tls=false

EXPOSE 3003

CMD ["python", "/app/http_wrapper.py"]
