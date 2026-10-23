"""Project-bound checkpoint writer using MCP JSON-RPC over stdio."""

import argparse
import json
import sys
from pathlib import Path

from autosave import checkpoint, checkpoint_context, repository
from storage import project_directory


PROTOCOLS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
TOOL = {
    "name": "save_checkpoint",
    "description": (
        "Save a cumulative session summary, replacing the session's previous one, for the server's configured project. "
        "Requires autosave to be enabled and an exact current hook-issued token. "
        "Does not execute commands, enable automation, or accept output paths."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "format": "uuid"},
            "token": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "summary": {"type": "string", "minLength": 1},
        },
        "required": ["session_id", "token", "summary"],
        "additionalProperties": False,
    },
}
CONTEXT_TOOL = {
    "name": "get_checkpoint_context",
    "description": (
        "Read the pending checkpoint for the exact runtime-provided session UUID "
        "in this configured project. Never guess a session or select the newest. "
        "Call once before composing the summary; do not refresh after a stale save."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"session_id": {"type": "string", "format": "uuid"}},
        "required": ["session_id"],
        "additionalProperties": False,
    },
    "annotations": {"readOnlyHint": True},
}


def call_tool(cwd, params):
    if not isinstance(params, dict):
        raise ValueError("Unknown checkpoint tool.")
    arguments = params.get("arguments")
    if params.get("name") == CONTEXT_TOOL["name"]:
        if (
            not isinstance(arguments, dict) or set(arguments) != {"session_id"}
            or not isinstance(arguments["session_id"], str)
        ):
            raise ValueError("Expected only string session_id.")
        context = checkpoint_context(cwd, arguments["session_id"])
        return {"content": [{"type": "text", "text": json.dumps(context)}]}
    if params.get("name") != TOOL["name"]:
        raise ValueError("Unknown checkpoint tool.")
    if (
        not isinstance(arguments, dict)
        or set(arguments) != {"session_id", "token", "summary"}
        or any(not isinstance(value, str) for value in arguments.values())
    ):
        raise ValueError("Expected only string session_id, token, and summary.")
    token = arguments["token"]
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise ValueError("Checkpoint token must be 64 lowercase hexadecimal characters.")
    destination = checkpoint(
        cwd, arguments["session_id"], token, arguments["summary"]
    )
    return {"content": [{"type": "text", "text": str(destination)}]}


def respond(message, cwd, initialized):
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {
            "jsonrpc": "2.0", "id": None,
            "error": {"code": -32600, "message": "Invalid JSON-RPC request."},
        }, initialized
    if "id" not in message:
        return None, initialized
    response = {"jsonrpc": "2.0", "id": message["id"]}
    method = message.get("method")
    params = message.get("params", {})
    if method == "initialize":
        if not isinstance(params, dict):
            response["error"] = {"code": -32602, "message": "Invalid initialize parameters."}
        else:
            version = params.get("protocolVersion")
            response["result"] = {
                "protocolVersion": version if version in PROTOCOLS else PROTOCOLS[-1],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "session-summary", "version": "1.0.0"},
            }
            initialized = True
    elif method == "ping":
        response["result"] = {}
    elif not initialized:
        response["error"] = {"code": -32000, "message": "Initialize the server first."}
    elif method == "tools/list":
        response["result"] = {"tools": [CONTEXT_TOOL, TOOL]}
    elif method == "tools/call":
        try:
            response["result"] = call_tool(cwd, params)
        except (OSError, ValueError, KeyError, TypeError) as error:
            response["result"] = {
                "isError": True,
                "content": [{"type": "text", "text": f"Checkpoint failed: {error}"}],
            }
    else:
        response["error"] = {"code": -32601, "message": "Method not found."}
    return response, initialized


def serve(cwd, source, output):
    initialized = False
    for line in source:
        try:
            message = json.loads(line)
        except ValueError:
            response = {
                "jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Invalid JSON."},
            }
        else:
            response, initialized = respond(message, cwd, initialized)
        if response is not None:
            output.write(json.dumps(response) + "\n")
            output.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", type=Path, required=True)
    args = parser.parse_args()
    try:
        cwd = args.cwd.expanduser().resolve(strict=True)
        project_directory(cwd)
        if repository(cwd) is None:
            raise ValueError("--cwd must be inside a Git repository.")
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        serve(cwd, sys.stdin, sys.stdout)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Checkpoint MCP server error: {error}\n")


if __name__ == "__main__":
    main()
