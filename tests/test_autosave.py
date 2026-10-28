from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "remind-me-again/scripts")
)
import autosave


SESSION = "12345678-1234-1234-1234-123456789abc"
START = int(datetime(2026, 10, 23, 10).astimezone().timestamp() * 1000)


class AutosaveTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.repo = self.home / "personal" / "example"
        (self.repo / ".git").mkdir(parents=True)
        self.cwd = self.repo / "nested"
        self.cwd.mkdir()
        patcher = patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        env = patch.dict("os.environ", {"COPILOT_HOME": str(self.home / ".copilot")})
        env.start()
        self.addCleanup(env.stop)
        self.base = {"sessionId": SESSION, "cwd": str(self.cwd), "timestamp": START}

    def event(self, event, **fields):
        return autosave.handle(event, dict(self.base, **fields))

    def enable(self, scope="repo"):
        return autosave.configure(scope, "on", self.cwd)

    def start(self):
        self.event("sessionStart", source="startup")

    def prompt(self, text="Implement the change.", timestamp=START + 1):
        self.event("userPromptSubmitted", prompt=text, timestamp=timestamp)

    def stop(self, **fields):
        return self.event("agentStop", stop_hook_active=False, **fields)

    def test_default_off_has_no_writes_or_continuation(self):
        self.assertEqual(self.stop(), {})
        self.assertFalse((self.home / ".copilot").exists())
        self.assertFalse((self.repo / ".github").exists())

    def test_config_precedence_global_repo_off_and_inherit(self):
        self.enable("global")
        self.assertTrue(autosave.enabled(self.cwd))
        autosave.configure("repo", "off", self.cwd)
        self.assertFalse(autosave.enabled(self.cwd))
        self.assertEqual(self.stop(), {})
        autosave.configure("repo", "inherit", self.cwd)
        self.assertTrue(autosave.enabled(self.cwd))
        autosave.configure("global", "off", self.cwd)
        self.assertFalse(autosave.enabled(self.cwd))
        self.enable()
        self.assertTrue(autosave.enabled(self.cwd))

    def test_status_defaults_are_read_only_inside_and_outside_git(self):
        for cwd, root in ((self.cwd, str(self.repo)), (self.home, None)):
            with self.subTest(cwd=cwd):
                result = autosave.configuration_status(cwd)
                self.assertEqual(result["repo"], root)
                for feature in autosave.FEATURES:
                    self.assertEqual(result["features"][feature], {
                        "global": "inherit",
                        "repo": "inherit" if root else None,
                        "effective": False,
                        "source": "default",
                    })
        self.assertFalse((self.home / ".copilot").exists())
        self.assertFalse((self.repo / ".github").exists())

    def test_status_tracks_overrides_inheritance_and_preserves_files(self):
        self.enable("global")
        autosave.configure("repo", "off", self.cwd)
        autosave.configure("repo", "on", self.cwd, feature="autoread")
        paths = [
            self.home / ".copilot/session-info-settings.json",
            self.repo / ".github/session-info.json",
        ]
        before = {path: path.read_bytes() for path in paths}
        result = autosave.configuration_status(self.cwd)
        self.assertEqual(result["features"]["autosave"], {
            "global": "on", "repo": "off", "effective": False, "source": "repo",
        })
        self.assertEqual(result["features"]["autoread"], {
            "global": "inherit", "repo": "on", "effective": True, "source": "repo",
        })
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        autosave.configure("repo", "inherit", self.cwd)
        inherited = autosave.configuration_status(self.cwd)["features"]["autosave"]
        self.assertEqual(inherited, {
            "global": "on", "repo": "inherit", "effective": True, "source": "global",
        })
        self.assertEqual(inherited["effective"], autosave.enabled(self.cwd))
        autosave.configure("global", "inherit", self.cwd)
        self.assertEqual(
            autosave.configuration_status(self.cwd)["features"]["autosave"]["source"],
            "default",
        )

    def test_status_lists_mcp_registration_without_exposing_credentials_or_writes(self):
        self.enable()
        autosave.configure_transport(self.cwd, "mcp")
        global_path = autosave.copilot_home() / "mcp-config.json"
        global_path.parent.mkdir(parents=True, exist_ok=True)
        project_path = self.repo / ".mcp.json"
        alternate_path = self.repo / ".github/mcp.json"
        for path, tools in (
            (global_path, None),
            (project_path, ["get_checkpoint_context", "save_checkpoint"]),
            (alternate_path, []),
        ):
            server = {"command": "private-command", "env": {"TOKEN": "private-token"}}
            if tools is not None:
                server["tools"] = tools
            path.write_text(json.dumps({"mcpServers": {"remind-me-again": server}}))
        before = {path: path.read_bytes() for path in (
            global_path, project_path, alternate_path,
        )}
        result = autosave.configuration_status(self.cwd)
        self.assertEqual(result["mcp"]["transport"], "mcp")
        self.assertEqual(len(result["mcp"]["registrations"]), 3)
        text = autosave.format_configuration_status(result)
        for expected in ("unspecified", "get_checkpoint_context", "Enabled tools: none"):
            self.assertIn(expected, text)
        for secret in ("private-command", "private-token"):
            self.assertNotIn(secret, json.dumps(result))
            self.assertNotIn(secret, text)
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)
        outside = autosave.configuration_status(self.home)
        self.assertEqual(outside["mcp"]["transport"], "shell")
        self.assertEqual(len(outside["mcp"]["registrations"]), 1)

    def test_status_rejects_malformed_mcp_and_ignores_unrelated_servers(self):
        path = self.repo / ".mcp.json"
        for config in (
            {"mcpServers": []},
            {"remind-me-again": "invalid"},
            {"remind-me-again": {"tools": "all"}},
            {"remind-me-again": {"tools": [123]}},
        ):
            path.write_text(json.dumps(config))
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                autosave.configuration_status(self.cwd)
            self.assertEqual(path.read_bytes(), original)
        path.write_text('{"mcpServers":{"other":{"command":"unrelated"}}}')
        result = autosave.configuration_status(self.cwd)
        self.assertEqual(result["mcp"]["registrations"], [])
        self.assertIn("Registration: not configured", autosave.format_configuration_status(result))
        self.assertIn(
            "outside a Git repository",
            autosave.format_configuration_status(autosave.configuration_status(self.home)),
        )

    def test_status_cli_reports_json_and_rejects_invalid_settings_without_writes(self):
        command = [
            sys.executable, "-B", str(autosave.SCRIPT), "status", "--cwd", str(self.cwd),
        ]
        environment = dict(os.environ, HOME=str(self.home))
        result = subprocess.run(
            command, env=environment, text=True, capture_output=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), autosave.configuration_status(self.cwd))
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.home / ".copilot").exists())
        path = self.repo / ".github/session-info.json"
        path.parent.mkdir()
        for content in ('{"version":1,"autosave":"yes"}', "invalid json"):
            path.write_text(content)
            failed = subprocess.run(
                command, env=environment, text=True, capture_output=True,
            )
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(failed.stdout, "")
            self.assertIn("Session-info autosave error", failed.stderr)
            self.assertEqual(path.read_text(), content)

    def test_installs_both_scopes_without_overwriting_other_hooks(self):
        other = self.repo / ".github/hooks/other.json"
        other.parent.mkdir(parents=True)
        other.write_text('{"version":1,"hooks":{}}')
        original = other.read_bytes()
        for scope in ("repo", "global"):
            self.enable(scope)
        self.assertEqual(other.read_bytes(), original)
        repo_hook = json.loads((other.parent / "session-info.json").read_text())
        user_hook = json.loads(
            (self.home / ".copilot/hooks/session-info.json").read_text()
        )
        self.assertEqual(repo_hook, user_hook)
        self.assertEqual(set(repo_hook["hooks"]), {
            "sessionStart", "userPromptSubmitted", "agentStop", "sessionEnd",
        })
        self.enable()
        collision = other.parent / "session-info.json"
        collision.write_text('{"unrelated":true}')
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.enable()
        self.assertEqual(collision.read_text(), '{"unrelated":true}')

    def test_requests_one_continuation_and_deduplicates_hooks_and_saves(self):
        self.enable()
        self.start()
        self.prompt()
        self.prompt()
        result = self.stop()
        self.assertEqual(result["decision"], "block")
        self.assertIn("checkpoint", result["reason"])
        self.assertTrue(result["reason"].startswith("Session-summary autosave requested."))
        self.assertIn("SKILL.md", result["reason"])
        self.assertNotIn("autosave executed", result["reason"])
        self.assertNotIn("Implement the change.", result["reason"])
        self.assertEqual(self.stop(), {})
        state = autosave.read_state(self.cwd, SESSION)
        token = state["turn"]
        first = autosave.checkpoint(self.cwd, SESSION, token, "Implemented the change.")
        original = first.read_bytes()
        self.assertEqual(
            autosave.checkpoint(self.cwd, SESSION, token, "Do not duplicate."), first
        )
        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(self.stop(), {})
        self.assertEqual(
            self.event("agentStop", stop_hook_active=True), {}
        )
        self.assertEqual(first.read_text().count(f"## Session {SESSION}"), 1)
        self.assertIn(f"copilot --resume={SESSION}", first.read_text())

    def test_resume_preserves_start_date_and_new_turn_saves_only_once(self):
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        state = autosave.read_state(self.cwd, SESSION)
        first = autosave.checkpoint(self.cwd, SESSION, state["turn"], "First progress.")
        self.event("sessionEnd", reason="user_exit")
        self.event("sessionStart", source="resume", timestamp=START + 86400000)
        self.prompt("More work.", START + 86400001)
        self.stop()
        state = autosave.read_state(self.cwd, SESSION)
        second = autosave.checkpoint(self.cwd, SESSION, state["turn"], "More progress.")
        self.assertEqual(first, second)
        self.assertEqual(second.name, "2026-10-23.md")
        self.assertNotIn("First progress.", second.read_text())
        self.assertIn("More progress.", second.read_text())
        self.assertEqual(second.read_text().count(f"## Session {SESSION}"), 1)

    def test_checkpoint_continuation_prompt_preserves_pending_token(self):
        self.enable()
        self.start()
        self.prompt()
        result = self.stop()
        before = autosave.read_state(self.cwd, SESSION)
        self.prompt(result["reason"], START + 2)
        self.prompt(result["reason"], START + 2)
        self.assertEqual(autosave.read_state(self.cwd, SESSION), before)
        destination = autosave.checkpoint(
            self.cwd, SESSION, before["turn"], "Live continuation progress."
        )
        self.assertIn("Live continuation progress.", destination.read_text())
        self.assertEqual(self.event("agentStop", stop_hook_active=True), {})

    def test_mcp_transport_is_explicit_and_preserves_continuation_token(self):
        self.enable()
        self.assertEqual(autosave.checkpoint_transport(self.cwd), "shell")
        autosave.configure_transport(self.cwd, "mcp")
        self.assertTrue(autosave.enabled(self.cwd))
        self.start()
        self.prompt()
        result = self.stop()
        self.assertEqual(
            result["reason"],
            f"Session-summary autosave requested\nsession_id: {SESSION}",
        )
        self.assertNotIn("Send the summary through stdin", result["reason"])
        before = autosave.read_state(self.cwd, SESSION)
        self.prompt(result["reason"], START + 2)
        self.assertEqual(autosave.read_state(self.cwd, SESSION), before)
        destination = autosave.checkpoint(
            self.cwd, SESSION, before["turn"], "MCP continuation progress."
        )
        self.assertIn("MCP continuation progress.", destination.read_text())
        self.assertEqual(self.event("agentStop", stop_hook_active=True), {})
        autosave.configure_transport(self.cwd, "shell")
        self.assertEqual(autosave.checkpoint_transport(self.cwd), "shell")

    def test_mcp_modified_session_id_invalidates_pending_token(self):
        self.enable()
        autosave.configure_transport(self.cwd, "mcp")
        self.start()
        self.prompt()
        result = self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        other_session = "aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa"
        self.prompt(result["reason"].replace(SESSION, other_session), START + 2)
        with self.assertRaisesRegex(ValueError, "stale"):
            autosave.checkpoint(self.cwd, SESSION, token, "Old progress.")
        self.assertIsNone(autosave.read_state(self.cwd, SESSION)["requested"])

    def test_transport_configuration_does_not_enable_autosave(self):
        autosave.configure_transport(self.cwd, "mcp")
        self.assertFalse(autosave.enabled(self.cwd))
        with self.assertRaisesRegex(ValueError, "transport"):
            autosave.configure_transport(self.cwd, "unknown")
        with self.assertRaisesRegex(ValueError, "repository"):
            autosave.configure_transport(self.home, "mcp")

    def test_modified_continuation_prompt_still_invalidates_pending_token(self):
        self.enable()
        self.start()
        self.prompt()
        result = self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        self.prompt(result["reason"] + "\nA new user instruction.", START + 2)
        with self.assertRaisesRegex(ValueError, "stale"):
            autosave.checkpoint(self.cwd, SESSION, token, "Old progress.")
        self.assertIsNone(autosave.read_state(self.cwd, SESSION)["requested"])

    def test_old_continuation_cannot_restore_token_after_new_user_turn(self):
        self.enable()
        self.start()
        self.prompt()
        result = self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        self.prompt("A genuinely newer request.", START + 2)
        self.prompt(result["reason"], START + 3)
        with self.assertRaisesRegex(ValueError, "stale"):
            autosave.checkpoint(self.cwd, SESSION, token, "Old progress.")

    def test_failed_save_remains_unsaved_and_exit_reports_it(self):
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        state = autosave.read_state(self.cwd, SESSION)
        with self.assertRaises(ValueError):
            autosave.checkpoint(self.cwd, SESSION, state["turn"], " \n")
        with self.assertRaisesRegex(ValueError, "unsaved"):
            self.event("agentStop", stop_hook_active=True)
        with self.assertRaisesRegex(ValueError, "unsaved"):
            self.event("sessionEnd", reason="abort")
        state = autosave.read_state(self.cwd, SESSION)
        self.assertNotEqual(state["saved"], state["turn"])

    def test_recovery_after_append_succeeds_but_state_write_fails(self):
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        with patch.object(autosave, "write_json", side_effect=OSError("Disk error")):
            with self.assertRaisesRegex(OSError, "Disk error"):
                autosave.checkpoint(self.cwd, SESSION, token, "Saved before error.")
        self.assertNotEqual(autosave.read_state(self.cwd, SESSION)["saved"], token)
        destination = autosave.checkpoint(self.cwd, SESSION, token, "Retry content.")
        content = destination.read_text()
        self.assertEqual(content.count(f"## Session {SESSION}"), 1)
        self.assertIn("Saved before error.", content)
        self.assertNotIn("Retry content.", content)
        self.assertEqual(autosave.read_state(self.cwd, SESSION)["saved"], token)

    def test_resume_can_retry_unsaved_turn_without_a_new_prompt(self):
        self.enable()
        self.start()
        self.prompt()
        self.assertEqual(self.stop()["decision"], "block")
        self.assertEqual(self.stop(), {})
        self.event("sessionStart", source="resume", timestamp=START + 86400000)
        self.assertEqual(self.stop()["decision"], "block")

    def test_initial_prompt_is_checkpointed_without_separate_prompt_event(self):
        self.enable()
        self.event("sessionStart", source="startup", initialPrompt="Initial task.")
        self.assertEqual(self.stop()["decision"], "block")

    def test_no_prompt_does_not_request_checkpoint_and_exit_is_clean(self):
        self.enable()
        self.start()
        self.assertEqual(self.stop(), {})
        self.assertEqual(self.event("sessionEnd", reason="complete"), {})

    def test_raw_append_failure_does_not_advance_saved_state(self):
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        with patch.object(autosave, "save_summary", side_effect=OSError("Denied")):
            with self.assertRaisesRegex(OSError, "Denied"):
                autosave.checkpoint(self.cwd, SESSION, token, "Progress.")
        self.assertIsNone(autosave.read_state(self.cwd, SESSION)["saved"])

    def test_autosave_entries_work_with_incremental_rollups(self):
        import rollup
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        autosave.checkpoint(self.cwd, SESSION, token, "First checkpoint.")
        rollup.save(rollup.prepare(self.cwd, "2026-10-23"), "First synthesis.")
        self.prompt("More work.", START + 2)
        self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        autosave.checkpoint(self.cwd, SESSION, token, "Second checkpoint.")
        plan = rollup.prepare(self.cwd, "2026-10-23")
        self.assertEqual(len(plan["pending"]), 1)
        self.assertIn("Second checkpoint.", plan["pending"][0]["text"])
        self.assertNotIn("First checkpoint.", plan["pending"][0]["text"])
        destination = rollup.save(plan, "Combined synthesis.")
        self.assertEqual(destination.read_text().count(f"| `{SESSION}` |"), 1)

    def test_stale_or_disabled_checkpoint_is_rejected(self):
        self.enable()
        self.start()
        self.prompt()
        self.stop()
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        self.prompt("A newer request.", START + 2)
        with self.assertRaisesRegex(ValueError, "stale"):
            autosave.checkpoint(self.cwd, SESSION, token, "Old progress.")
        autosave.configure("repo", "off", self.cwd)
        with self.assertRaisesRegex(ValueError, "disabled"):
            autosave.checkpoint(self.cwd, SESSION, token, "Old progress.")

    def test_unknown_resume_needs_explicit_initial_date(self):
        self.enable()
        with self.assertRaisesRegex(ValueError, "initialize"):
            self.event("sessionStart", source="resume")
        autosave.initialize(self.cwd, SESSION, "2026-10-21")
        self.event("sessionStart", source="resume")
        self.assertEqual(
            autosave.read_state(self.cwd, SESSION)["session_date"], "2026-10-21"
        )

    def test_subagents_are_ignored_and_missing_start_is_explicit(self):
        self.enable()
        self.assertEqual(self.event("agentStop", agentId="child"), {})
        with self.assertRaisesRegex(ValueError, "initialize"):
            self.prompt()

    def test_invalid_settings_are_not_silently_treated_as_disabled(self):
        path = self.home / ".copilot/session-info-settings.json"
        path.parent.mkdir()
        for content in ('{"autosave":"yes"}', "not json"):
            path.write_text(content)
            with self.assertRaises(ValueError):
                autosave.enabled(self.cwd)

    def test_missing_git_repository_is_rejected_for_repo_config(self):
        with self.assertRaisesRegex(ValueError, "repository"):
            autosave.configure("repo", "on", self.home)

    def test_concurrent_hook_registrations_request_only_one_checkpoint(self):
        self.enable()
        self.start()
        self.prompt()
        command = [sys.executable, "-B", str(autosave.SCRIPT), "hook", "agentStop"]
        environment = dict(os.environ, HOME=str(self.home))

        def invoke(_):
            return subprocess.run(
                command,
                input=json.dumps(dict(self.base, stop_hook_active=False)),
                env=environment, text=True, capture_output=True, check=True,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(invoke, range(2)))
        decisions = [json.loads(result.stdout).get("decision") for result in responses]
        self.assertEqual(decisions.count("block"), 1)
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        save_command = [
            sys.executable, "-B", str(autosave.SCRIPT), "checkpoint",
            "--cwd", str(self.cwd), "--session-id", SESSION, "--token", token,
        ]

        def checkpoint(_):
            return subprocess.run(
                save_command, input="Concurrent checkpoint.",
                env=environment, text=True, capture_output=True, check=True,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            saves = list(executor.map(checkpoint, range(2)))
        destination = Path(saves[0].stdout.strip())
        self.assertEqual(saves[0].stdout, saves[1].stdout)
        self.assertEqual(destination.read_text().count(f"## Session {SESSION}"), 1)

    def test_installed_hook_runs_using_documented_stdin_stdout_contract(self):
        self.enable()
        hook_path = self.repo / ".github/hooks/session-info.json"
        hooks = json.loads(hook_path.read_text())["hooks"]
        environment = dict(
            os.environ, HOME=str(self.home),
            PYTHONDONTWRITEBYTECODE="1",
        )
        for event, fields in (
            ("sessionStart", {"source": "startup"}),
            ("userPromptSubmitted", {"prompt": "A task.", "timestamp": START + 1}),
            ("agentStop", {"stop_hook_active": False}),
        ):
            hook = hooks[event][0]
            result = subprocess.run(
                [hook["exec"], *hook["args"]],
                input=json.dumps(dict(self.base, **fields)),
                env=environment, text=True, capture_output=True, check=True,
            )
        self.assertEqual(json.loads(result.stdout)["decision"], "block")
        self.assertEqual(result.stderr, "")
        token = autosave.read_state(self.cwd, SESSION)["turn"]
        saved = subprocess.run(
            [
                sys.executable, "-B", str(autosave.SCRIPT), "checkpoint",
                "--cwd", str(self.cwd), "--session-id", SESSION, "--token", token,
            ],
            input="Progress saved through the CLI.", env=environment,
            text=True, capture_output=True, check=True,
        )
        self.assertIn(
            "Progress saved through the CLI.",
            Path(saved.stdout.strip()).read_text(),
        )
        hook = hooks["agentStop"][0]
        stopped = subprocess.run(
            [hook["exec"], *hook["args"]],
            input=json.dumps(dict(self.base, stop_hook_active=True)),
            env=environment, text=True, capture_output=True, check=True,
        )
        self.assertEqual(json.loads(stopped.stdout), {})
        self.assertEqual(stopped.stderr, "")


if __name__ == "__main__":
    unittest.main()
