# MCP PostgreSQL Server with HTTP transport
FROM node:20-slim

# Install curl for health checks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the official MCP PostgreSQL server
RUN npm install @modelcontextprotocol/server-postgres

# Copy HTTP wrapper
COPY server.js /app/server.js

ENV MCP_PORT=3000
ENV DATABASE_URL=postgresql://bench:bench@postgres:5432/benchmark

EXPOSE 3000

CMD ["node", "/app/server.js"]
