/**
 * HTTP wrapper for the official PostgreSQL MCP server.
 *
 * Spawns the stdio-based MCP server and exposes it via HTTP
 * for Docker networking compatibility.
 */

const { spawn } = require('child_process');
const http = require('http');

const PORT = process.env.MCP_PORT || 3000;
const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://bench:bench@localhost:5432/benchmark';

let mcpProcess = null;
let requestId = 0;
let pendingRequests = new Map();

function startMCPServer() {
    console.log(`Starting MCP PostgreSQL server with DATABASE_URL: ${DATABASE_URL}`);

    mcpProcess = spawn('node', [
        'node_modules/@modelcontextprotocol/server-postgres/dist/index.js',
        DATABASE_URL
    ], {
        stdio: ['pipe', 'pipe', 'pipe']
    });

    mcpProcess.stderr.on('data', (data) => {
        console.error(`MCP stderr: ${data}`);
    });

    mcpProcess.stdout.on('data', (data) => {
        const lines = data.toString().split('\n').filter(l => l.trim());
        for (const line of lines) {
            try {
                const response = JSON.parse(line);
                const id = response.id;
                if (id && pendingRequests.has(id)) {
                    const { resolve } = pendingRequests.get(id);
                    pendingRequests.delete(id);
                    resolve(response);
                }
            } catch (e) {
                // Not JSON, ignore
            }
        }
    });

    mcpProcess.on('close', (code) => {
        console.log(`MCP process exited with code ${code}`);
        // Reject all pending requests
        for (const [id, { reject }] of pendingRequests) {
            reject(new Error('MCP server closed'));
        }
        pendingRequests.clear();
        // Restart after delay
        setTimeout(() => {
            mcpProcess = startMCPServer();
        }, 1000);
    });

    return mcpProcess;
}

function sendMCPRequest(method, params) {
    return new Promise((resolve, reject) => {
        if (!mcpProcess || !mcpProcess.stdin) {
            reject(new Error('MCP server not running'));
            return;
        }

        requestId++;
        const id = requestId;
        const request = {
            jsonrpc: '2.0',
            id,
            method,
        };
        if (params !== undefined) {
            request.params = params;
        }

        pendingRequests.set(id, { resolve, reject });

        mcpProcess.stdin.write(JSON.stringify(request) + '\n');

        // Timeout after 30 seconds
        setTimeout(() => {
            if (pendingRequests.has(id)) {
                pendingRequests.delete(id);
                reject(new Error('MCP request timeout'));
            }
        }, 30000);
    });
}

// Initialize MCP server
async function initialize() {
    try {
        const initResponse = await sendMCPRequest('initialize', {
            protocolVersion: '2024-11-05',
            capabilities: { tools: {} },
            clientInfo: { name: 'http-wrapper', version: '1.0.0' }
        });
        console.log('MCP initialized:', JSON.stringify(initResponse));

        // Send initialized notification (no response expected)
        mcpProcess.stdin.write(JSON.stringify({
            jsonrpc: '2.0',
            method: 'notifications/initialized'
        }) + '\n');

        return true;
    } catch (e) {
        console.error('Failed to initialize MCP:', e);
        return false;
    }
}

// HTTP server
const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
        res.writeHead(200);
        res.end();
        return;
    }

    if (req.url === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok' }));
        return;
    }

    if (req.url === '/message' && req.method === 'POST') {
        let body = '';
        req.on('data', chunk => { body += chunk; });
        req.on('end', async () => {
            try {
                const request = JSON.parse(body);
                const { method, params, id: clientId } = request;

                const response = await sendMCPRequest(method, params);

                // Update response ID to match client request
                if (clientId !== undefined) {
                    response.id = clientId;
                }

                res.writeHead(200, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify(response));

            } catch (e) {
                res.writeHead(500, { 'Content-Type': 'application/json' });
                res.end(JSON.stringify({
                    jsonrpc: '2.0',
                    error: { code: -32000, message: e.message }
                }));
            }
        });
        return;
    }

    if (req.url === '/tools' && req.method === 'GET') {
        try {
            const response = await sendMCPRequest('tools/list');
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(response.result || response));
        } catch (e) {
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: e.message }));
        }
        return;
    }

    res.writeHead(404);
    res.end('Not found');
});

// Start everything
console.log(`Starting HTTP wrapper on port ${PORT}`);
mcpProcess = startMCPServer();

// Wait a bit for MCP server to start, then initialize
setTimeout(async () => {
    const ok = await initialize();
    if (ok) {
        server.listen(PORT, () => {
            console.log(`MCP PostgreSQL HTTP server listening on port ${PORT}`);
        });
    } else {
        console.error('Failed to initialize, retrying...');
        setTimeout(async () => {
            await initialize();
            server.listen(PORT, () => {
                console.log(`MCP PostgreSQL HTTP server listening on port ${PORT}`);
            });
        }, 2000);
    }
}, 1000);
