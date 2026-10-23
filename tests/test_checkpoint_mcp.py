import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import test_autosave

import autosave
import checkpoint_mcp


SESSION = test_autosave.SESSION
START = test_autosave.START


class CheckpointMCPTests(unittest.TestCase):
    setUp = test_autosave.AutosaveTests.setUp
    enable = test_autosave.AutosaveTests.enable
    start = test_autosave.AutosaveTests.start
    prompt = test_autosave.AutosaveTests.prompt
    stop = test_autosave.AutosaveTests.stop
    event = test_autosave.AutosaveTests.event

    def test_stdio_round_trip_saves_once_and_reports_errors(self):
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        arguments = {
            "session_id": SESSION, "token": token, "summary": "MCP progress."
        }
        messages = [
            {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"method": "notifications/initialized"},
            {"id": 2, "method": "tools/list"},
            {"id": 3, "method": "tools/call", "params": {
                "name": "save_checkpoint", "arguments": arguments,
            }},
            {"id": 4, "method": "tools/call", "params": {
                "name": "save_checkpoint", "arguments": arguments,
            }},
            {"id": 5, "method": "tools/call", "params": {
                "name": "save_checkpoint",
                "arguments": dict(arguments, output_path="/tmp/not-allowed"),
            }},
        ]
        result = subprocess.run(
            [sys.executable, "-B", str(Path(checkpoint_mcp.__file__)),
             "--cwd", str(self.cwd)],
            input="".join(json.dumps(dict(message, jsonrpc="2.0")) + "\n"
                          for message in messages),
            env=dict(os.environ, HOME=str(self.home)),
            text=True, capture_output=True, check=True,
        )
        self.assertEqual(result.stderr, "")
        responses = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([response["id"] for response in responses], [1, 2, 3, 4, 5])
        self.assertEqual(responses[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(
            [tool["name"] for tool in responses[1]["result"]["tools"]],
            ["save_checkpoint"],
        )
        destination = Path(responses[2]["result"]["content"][0]["text"])
        self.assertIn("MCP progress.", destination.read_text())
        self.assertEqual(destination.read_text().count(f"## Session {SESSION}"), 1)
        self.assertEqual(responses[2]["result"], responses[3]["result"])
        self.assertTrue(responses[4]["result"]["isError"])
        self.assertEqual(autosave.read_state(self.cwd, SESSION)["saved"], token)

    def test_mcp_enforces_project_binding_stale_tokens_and_opt_in(self):
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        params = {"name": "save_checkpoint", "arguments": {
            "session_id": SESSION, "token": token, "summary": "Progress.",
        }}
        for arguments, error in (
            (dict(params["arguments"], summary=" "), "empty"),
            (dict(params["arguments"], session_id="../other"), "UUID"),
            (dict(params["arguments"], token="invalid"), "hexadecimal"),
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(ValueError, error):
                    checkpoint_mcp.call_tool(
                        self.cwd, {"name": "save_checkpoint", "arguments": arguments}
                    )
        other = self.home / "other"
        (other / ".git").mkdir(parents=True)
        autosave.configure("repo", "on", other)
        with self.assertRaisesRegex(ValueError, "Missing autosave"):
            checkpoint_mcp.call_tool(other, params)
        self.prompt("New request.", START + 2)
        with self.assertRaisesRegex(ValueError, "stale"):
            checkpoint_mcp.call_tool(self.cwd, params)
        autosave.configure("repo", "off", self.cwd)
        with self.assertRaisesRegex(ValueError, "disabled"):
            checkpoint_mcp.call_tool(self.cwd, params)

    def test_protocol_errors_and_tool_errors_are_visible(self):
        source = io.StringIO(
            'invalid json\n'
            '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
            '{"jsonrpc":"2.0","id":2,"method":"initialize","params":{}}\n'
            '{"jsonrpc":"2.0","id":3,"method":"unknown"}\n'
            '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":'
            '{"name":"execute_shell"}}\n'
        )
        output = io.StringIO()
        checkpoint_mcp.serve(self.cwd, source, output)
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1]["error"]["code"], -32000)
        self.assertEqual(responses[3]["error"]["code"], -32601)
        self.assertTrue(responses[4]["result"]["isError"])


if __name__ == "__main__":
    unittest.main()
