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
        self.assertEqual(servers["session-summary"]["tools"],
                         ["get_checkpoint_context", "save_checkpoint"])
        self.assertEqual(servers["session-summary"]["args"][-1], str(self.cwd))
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
        path.write_text('{"mcpServers":{"session-summary":{"command":"unrelated"}}}')
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
        config["mcpServers"]["session-summary"]["tools"] = ["save_checkpoint"]
        path.write_text(json.dumps(config))
        setup_mcp.setup(self.cwd)
        self.assertEqual(
            json.loads(path.read_text())["mcpServers"]["session-summary"]["tools"],
            ["get_checkpoint_context", "save_checkpoint"],
        )


if __name__ == "__main__":
    unittest.main()
