"""HTTP wrapper for the official KurrentDB MCP server.

This spawns the official stdio-based MCP server and exposes it via HTTP
for Docker networking compatibility.
"""

import json
import os
import subprocess
import threading
from flask import Flask, request, jsonify

app = Flask(__name__)

MCP_PORT = int(os.environ.get('MCP_PORT', 3003))
KURRENTDB_CONNECTION_STRING = os.environ.get('KURRENTDB_CONNECTION_STRING', 'esdb://localhost:2113?tls=false')

# Global MCP server process
mcp_process = None
mcp_lock = threading.Lock()
request_id = 0


def start_mcp_server():
    """Start the official KurrentDB MCP server process."""
    global mcp_process

    env = os.environ.copy()
    env['KURRENTDB_CONNECTION_STRING'] = KURRENTDB_CONNECTION_STRING

    mcp_process = subprocess.Popen(
        ['python', '/app/kurrentdb-mcp/server.py'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        bufsize=1,
    )

    # Start stderr reader thread
    def read_stderr():
        for line in mcp_process.stderr:
            print(f"[MCP stderr] {line.strip()}")

    threading.Thread(target=read_stderr, daemon=True).start()

    print(f"Started KurrentDB MCP server (PID: {mcp_process.pid})")
    return mcp_process


def send_mcp_request(method: str, params: dict = None) -> dict:
    """Send a JSON-RPC request to the MCP server."""
    global request_id, mcp_process

    with mcp_lock:
        if mcp_process is None or mcp_process.poll() is not None:
            mcp_process = start_mcp_server()

        request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            req["params"] = params

        try:
            # Send request
            mcp_process.stdin.write(json.dumps(req) + "\n")
            mcp_process.stdin.flush()

            # Read response
            response_line = mcp_process.stdout.readline()
            if not response_line:
                raise RuntimeError("No response from MCP server")

            return json.loads(response_line)
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(e)}
            }


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"})


@app.route('/message', methods=['POST'])
def message():
    """Handle MCP JSON-RPC messages."""
    try:
        req = request.get_json()

        method = req.get('method')
        params = req.get('params')
        req_id = req.get('id')

        # Forward to MCP server
        response = send_mcp_request(method, params)

        # Update response ID to match client request
        if req_id is not None:
            response['id'] = req_id

        return jsonify(response)

    except Exception as e:
        return jsonify({
            "jsonrpc": "2.0",
            "id": request.get_json().get('id') if request.is_json else None,
            "error": {"code": -32000, "message": str(e)}
        }), 500


@app.route('/tools', methods=['GET'])
def list_tools():
    """Convenience endpoint to list available tools."""
    response = send_mcp_request('tools/list')
    if 'result' in response:
        return jsonify(response['result'])
    return jsonify(response), 500


if __name__ == '__main__':
    # Initialize MCP server
    print(f"Starting HTTP wrapper on port {MCP_PORT}")
    print(f"KurrentDB connection: {KURRENTDB_CONNECTION_STRING}")

    # Start MCP server on first request (lazy init)
    start_mcp_server()

    # Initialize the MCP connection
    init_response = send_mcp_request('initialize', {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "clientInfo": {"name": "http-wrapper", "version": "1.0.0"}
    })
    print(f"MCP initialized: {init_response}")

    # Send initialized notification
    send_mcp_request('notifications/initialized')

    # Run Flask server
    app.run(host='0.0.0.0', port=MCP_PORT)
