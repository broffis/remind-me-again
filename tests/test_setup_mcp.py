import json
from pathlib import Path
import subprocess
import unittest

import test_autosave
import autosave
import setup_mcp


class SetupMCPTests(unittest.TestCase):
    def setUp(self):
        test_autosave.AutosaveTests.setUp(self)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)

    def test_setup_is_idempotent_and_preserves_unrelated_configuration(self):
        mcp_path = self.repo / ".mcp.json"
        other = {"type": "stdio", "command": "other", "tools": ["read"]}
        mcp_path.write_text(json.dumps({"mcpServers": {"other": other}}))
        config_path = self.repo / ".github/session-info.json"
        config_path.parent.mkdir()
        config_path.write_text('{"version":1,"autoread":false,"autosave":false}')
        setup_mcp.setup(self.cwd)
        paths = setup_mcp.setup(self.cwd)
        self.assertEqual(len(paths), 3)
        servers = json.loads(mcp_path.read_text())["mcpServers"]
        self.assertEqual(servers["other"], other)
        self.assertEqual(servers["remind-me-again"]["tools"],
                         ["get_checkpoint_context", "save_checkpoint"])
        self.assertEqual(servers["remind-me-again"]["args"][-1], str(self.cwd))
        self.assertTrue(autosave.enabled(self.cwd))
        self.assertFalse(autosave.enabled(self.cwd, "autoread"))
        self.assertEqual(autosave.checkpoint_transport(self.cwd), "mcp")
        self.assertFalse((autosave.copilot_home() / "permissions-config.json").exists())

    def test_explicit_approval_is_narrow_and_preserves_other_permissions(self):
        permission_path = autosave.copilot_home() / "permissions-config.json"
        permission_path.parent.mkdir(parents=True)
        other = {"kind": "commands", "commandIdentifiers": ["git status"]}
        permission_path.write_text(json.dumps({"locations": {
            str(self.repo): {"tool_approvals": [other], "allowed_directories": [str(self.home)]},
            "/other/project": {"tool_approvals": [{"kind": "read"}]},
        }}))
        setup_mcp.setup(self.cwd, approve=True)
        setup_mcp.setup(self.cwd, approve=True)
        locations = json.loads(permission_path.read_text())["locations"]
        self.assertEqual(locations[str(self.repo)]["tool_approvals"],
                         [other, setup_mcp.APPROVAL, setup_mcp.CONTEXT_APPROVAL])
        self.assertEqual(locations[str(self.repo)]["allowed_directories"], [str(self.home)])
        self.assertEqual(locations["/other/project"], {"tool_approvals": [{"kind": "read"}]})

    def test_dry_run_does_not_write_and_conflicts_fail_before_changes(self):
        setup_mcp.setup(self.cwd, approve=True, dry_run=True)
        self.assertFalse((self.repo / ".mcp.json").exists())
        self.assertFalse((self.repo / ".github").exists())
        self.assertFalse(autosave.copilot_home().exists())
        path = self.repo / ".mcp.json"
        path.write_text('{"mcpServers":{"remind-me-again":{"command":"unrelated"}}}')
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "replace"):
            setup_mcp.setup(self.cwd, approve=True)
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((self.repo / ".github").exists())

    def test_invalid_or_legacy_permissions_are_not_overwritten(self):
        path = autosave.copilot_home() / "permissions-config.json"
        path.parent.mkdir(parents=True)
        for content in ("not JSON", '{"locations":[]}', '{"locations":{' +
                        json.dumps(str(self.repo)) + ':{"tool_approvals":{}}}}'):
            path.write_text(content)
            with self.assertRaises(ValueError):
                setup_mcp.setup(self.cwd, approve=True)
            self.assertEqual(path.read_text(), content)
            self.assertFalse((self.repo / ".mcp.json").exists())
        path.unlink()
        path.with_suffix("").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Legacy"):
            setup_mcp.setup(self.cwd, approve=True)

    def test_linked_worktree_permissions_use_main_repository_location(self):
        subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Test",
             "-c", "user.email=test@example.invalid", "commit",
             "--allow-empty", "-qm", "Initial"],
            check=True,
        )
        worktree = self.home / "linked"
        subprocess.run(
            ["git", "-C", str(self.repo), "worktree", "add", "-qb", "linked", str(worktree)],
            check=True,
        )
        setup_mcp.setup(worktree, approve=True)
        permissions = autosave.read_json(autosave.copilot_home() / "permissions-config.json")
        self.assertEqual(set(permissions["locations"]), {str(self.repo)})
        setup_mcp.remove_setup(setup_mcp.plan_removal(
            worktree, Path(setup_mcp.__file__).resolve().parents[1]
        ))
        permissions = autosave.read_json(autosave.copilot_home() / "permissions-config.json")
        self.assertEqual(permissions["locations"][str(self.repo)]["tool_approvals"], [])

    def test_existing_hook_conflict_prevents_all_writes(self):
        hook = self.repo / ".github/hooks/session-info.json"
        hook.parent.mkdir(parents=True)
        hook.write_text('{"unrelated":true}')
        with self.assertRaisesRegex(ValueError, "overwrite"):
            setup_mcp.setup(self.cwd, approve=True)
        self.assertFalse((self.repo / ".mcp.json").exists())
        self.assertEqual(hook.read_text(), '{"unrelated":true}')

    def test_setup_upgrades_identical_save_only_registration(self):
        setup_mcp.setup(self.cwd)
        path = self.repo / ".mcp.json"
        config = json.loads(path.read_text())
        config["mcpServers"]["remind-me-again"]["tools"] = ["save_checkpoint"]
        path.write_text(json.dumps(config))
        setup_mcp.setup(self.cwd)
        self.assertEqual(
            json.loads(path.read_text())["mcpServers"]["remind-me-again"]["tools"],
            ["get_checkpoint_context", "save_checkpoint"],
        )

    def test_removal_preserves_unrelated_entries_and_other_project_permissions(self):
        setup_mcp.setup(self.cwd, approve=True)
        installation = Path(setup_mcp.__file__).resolve().parents[1]
        mcp_path = self.repo / ".mcp.json"
        mcp = autosave.read_json(mcp_path)
        mcp["mcpServers"]["other"] = {"command": "keep"}
        autosave.write_json(mcp_path, mcp)
        hook_path = self.repo / ".github/hooks/session-info.json"
        hooks = autosave.read_json(hook_path)
        hooks["hooks"]["agentStop"].append({"type": "command", "command": "keep"})
        autosave.write_json(hook_path, hooks)
        config_path = self.repo / ".github/session-info.json"
        autosave.write_json(config_path, dict(autosave.settings(config_path), custom="keep"))
        permission_path = autosave.copilot_home() / "permissions-config.json"
        permissions = autosave.read_json(permission_path)
        other = {"kind": "mcp", "serverName": "other", "toolName": None}
        permissions["locations"][str(self.repo)]["tool_approvals"].append(other)
        permissions["locations"][str(self.repo)]["allowed_directories"] = [str(self.home)]
        permissions["locations"]["/other"] = {"tool_approvals": [setup_mcp.APPROVAL]}
        autosave.write_json(permission_path, permissions)
        changes = setup_mcp.plan_removal(self.cwd, installation)
        setup_mcp.remove_setup(changes)
        self.assertEqual(autosave.read_json(mcp_path), {"mcpServers": {"other": {"command": "keep"}}})
        self.assertEqual(autosave.read_json(hook_path)["hooks"],
                         {"agentStop": [{"type": "command", "command": "keep"}]})
        self.assertEqual(autosave.read_json(config_path), {"version": 1, "custom": "keep"})
        locations = autosave.read_json(permission_path)["locations"]
        self.assertEqual(locations[str(self.repo)]["tool_approvals"], [other])
        self.assertEqual(locations[str(self.repo)]["allowed_directories"], [str(self.home)])
        self.assertEqual(locations["/other"]["tool_approvals"], [setup_mcp.APPROVAL])

    def test_global_removal_requires_flag_and_retains_other_global_servers(self):
        installation = Path(setup_mcp.__file__).resolve().parents[1]
        autosave.configure("global", "on", self.cwd)
        setup_mcp.setup(self.cwd)
        global_mcp = autosave.copilot_home() / "mcp-config.json"
        server = autosave.read_json(self.repo / ".mcp.json")["mcpServers"]["remind-me-again"]
        autosave.write_json(global_mcp, {"mcpServers": {
            "remind-me-again": server, "other": {"command": "keep"},
        }})
        setup_mcp.remove_setup(setup_mcp.plan_removal(self.cwd, installation))
        self.assertTrue(global_mcp.exists())
        self.assertTrue((autosave.copilot_home() / "hooks/session-info.json").exists())
        setup_mcp.remove_setup(setup_mcp.plan_removal(self.cwd, installation, True))
        self.assertEqual(autosave.read_json(global_mcp), {"mcpServers": {"other": {"command": "keep"}}})
        self.assertFalse((autosave.copilot_home() / "hooks/session-info.json").exists())
        self.assertFalse((autosave.copilot_home() / "session-info-settings.json").exists())
        self.assertEqual(setup_mcp.plan_removal(self.cwd, installation, True), [])

    def test_removal_preflights_conflicting_hooks_and_invalid_permissions(self):
        setup_mcp.setup(self.cwd, approve=True)
        installation = Path(setup_mcp.__file__).resolve().parents[1]
        mcp_path = self.repo / ".mcp.json"
        original = mcp_path.read_bytes()
        permission_path = autosave.copilot_home() / "permissions-config.json"
        permissions = permission_path.read_bytes()
        permission_path.write_text('{"locations":[]}')
        with self.assertRaisesRegex(ValueError, "locations"):
            setup_mcp.plan_removal(self.cwd, installation)
        self.assertEqual(mcp_path.read_bytes(), original)
        permission_path.write_bytes(permissions)
        hook = self.repo / ".github/hooks/session-info.json"
        hook.write_text('{"version":1,"hooks":{"agentStop":[{"command":"unrelated"}]}}')
        with self.assertRaisesRegex(ValueError, "unrecognized hook"):
            setup_mcp.plan_removal(self.cwd, installation)
        self.assertEqual(mcp_path.read_bytes(), original)

    def test_removal_rejects_other_installation_and_symlink_registration(self):
        setup_mcp.setup(self.cwd)
        installation = Path(setup_mcp.__file__).resolve().parents[1]
        mcp_path = self.repo / ".mcp.json"
        original = mcp_path.read_bytes()
        with self.assertRaisesRegex(ValueError, "unrecognized MCP"):
            setup_mcp.plan_removal(self.cwd, self.home / "different-install")
        self.assertEqual(mcp_path.read_bytes(), original)
        target = self.home / "mcp-backup.json"
        mcp_path.rename(target)
        mcp_path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            setup_mcp.plan_removal(self.cwd, installation)
        self.assertEqual(target.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
