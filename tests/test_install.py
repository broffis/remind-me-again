import importlib.util
import hashlib
import shutil
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.skills = Path(temporary.name) / "skills"

    def test_install_copies_all_helpers_without_enabling_hooks(self):
        destination = installer.install(ROOT, self.skills)
        for script in (ROOT / "remind-me-again/scripts").glob("*.py"):
            self.assertEqual(
                (destination / "scripts" / script.name).read_bytes(),
                script.read_bytes(),
            )
        self.assertTrue((destination / "SKILL.md").is_file())
        self.assertFalse((destination / ".DS_Store").exists())
        self.assertFalse((self.skills.parent / "hooks").exists())

    def test_existing_install_requires_explicit_update(self):
        destination = installer.install(ROOT, self.skills)
        with self.assertRaisesRegex(ValueError, "update"):
            installer.install(ROOT, self.skills)
        self.assertEqual(installer.install(ROOT, self.skills, update=True), destination)

    def test_update_accepts_previous_payload_without_mcp_writer(self):
        destination = installer.install(ROOT, self.skills)
        (destination / "scripts/checkpoint_mcp.py").unlink()
        (destination / "scripts/setup_mcp.py").unlink()
        manifest_path = destination / installer.MANIFEST
        manifest = json.loads(manifest_path.read_text())
        del manifest["files"]["scripts/checkpoint_mcp.py"]
        del manifest["files"]["scripts/setup_mcp.py"]
        manifest_path.write_text(json.dumps(manifest))
        installer.install(ROOT, self.skills, update=True)
        self.assertTrue((destination / "scripts/checkpoint_mcp.py").is_file())

    def test_update_and_uninstall_refuse_modified_or_unowned_install(self):
        destination = installer.install(ROOT, self.skills)
        script = destination / "scripts/storage.py"
        script.write_text("local changes")
        for action in (
            lambda: installer.install(ROOT, self.skills, update=True),
            lambda: installer.uninstall(self.skills),
        ):
            with self.assertRaisesRegex(ValueError, "changed"):
                action()
            self.assertEqual(script.read_text(), "local changes")
        (destination / installer.MANIFEST).unlink()
        with self.assertRaisesRegex(ValueError, "managed"):
            installer.uninstall(self.skills, cwd=self.skills.parent)

    def test_uninstall_removes_only_owned_skill_and_preserves_summaries(self):
        destination = installer.install(ROOT, self.skills)
        summaries = self.skills.parent / "session-info"
        summaries.mkdir()
        (summaries / "saved.md").write_text("Keep this.")
        installer.uninstall(self.skills, cwd=self.skills.parent)
        self.assertFalse(destination.exists())
        self.assertEqual((summaries / "saved.md").read_text(), "Keep this.")

    def test_symlink_install_is_not_replaced_or_deleted(self):
        self.skills.mkdir()
        destination = self.skills / "remind-me-again"
        destination.symlink_to(ROOT / "remind-me-again", target_is_directory=True)
        for action in (
            lambda: installer.install(ROOT, self.skills, update=True),
            lambda: installer.uninstall(self.skills),
        ):
            with self.assertRaisesRegex(ValueError, "symbolic"):
                action()
        self.assertTrue(destination.is_symlink())

    def test_cli_uninstall_cleans_setup_and_dry_run_preserves_install(self):
        repo = self.skills.parent / "project"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        destination = installer.install(ROOT, self.skills)
        environment = dict(os.environ, HOME=str(self.skills.parent),
                           COPILOT_HOME=str(self.skills.parent / ".copilot"),
                           PYTHONDONTWRITEBYTECODE="1")
        subprocess.run(
            [sys.executable, "-B", str(destination / "scripts/setup_mcp.py"),
             "--cwd", str(repo), "--approve"],
            env=environment, check=True, capture_output=True, text=True,
        )
        command = [
            sys.executable, "-B", str(ROOT / "install.py"), "--uninstall",
            "--skills-dir", str(self.skills), "--cwd", str(repo),
        ]
        mcp = (repo / ".mcp.json").read_bytes()
        subprocess.run(command + ["--dry-run"], env=environment, check=True, capture_output=True)
        self.assertTrue(destination.is_dir())
        self.assertEqual((repo / ".mcp.json").read_bytes(), mcp)
        subprocess.run(command, env=environment, check=True, capture_output=True)
        self.assertFalse(destination.exists())
        self.assertFalse((repo / ".mcp.json").exists())
        self.assertFalse((repo / ".github/hooks/session-info.json").exists())
        self.assertFalse((repo / ".github/session-info.json").exists())
        permissions = json.loads(
            (self.skills.parent / ".copilot/permissions-config.json").read_text()
        )
        self.assertEqual(permissions["locations"][str(repo.resolve())]["tool_approvals"], [])

    def legacy_setup(self):
        """Create a project configured the way the old session-summary skill did."""
        repo = self.skills.parent / "project"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        destination = installer.install(ROOT, self.skills)
        self.environment = dict(
            os.environ, HOME=str(self.skills.parent),
            COPILOT_HOME=str(self.skills.parent / ".copilot"),
            PYTHONDONTWRITEBYTECODE="1",
        )
        subprocess.run(
            [sys.executable, "-B", str(destination / "scripts/setup_mcp.py"),
             "--cwd", str(repo), "--approve"],
            env=self.environment, check=True, capture_output=True,
        )
        legacy = self.skills / "session-summary"
        shutil.copytree(destination, legacy)
        (legacy / installer.MANIFEST).rename(legacy / installer.LEGACY_MANIFEST)
        manifest_path = legacy / installer.LEGACY_MANIFEST
        manifest = json.loads(manifest_path.read_text())
        manifest["installer"] = "session-summary"
        manifest_path.write_text(json.dumps(manifest))
        for path in (
            repo / ".mcp.json", repo / ".github/hooks/session-info.json",
            self.skills.parent / ".copilot/permissions-config.json",
        ):
            path.write_text(
                path.read_text().replace("/skills/remind-me-again/", "/skills/session-summary/")
                .replace('"remind-me-again"', '"session-summary"')
            )
        return repo, legacy

    def update(self, repo):
        return subprocess.run(
            [sys.executable, "-B", str(ROOT / "install.py"), "--update",
             "--skills-dir", str(self.skills), "--cwd", str(repo)],
            env=self.environment, check=True, capture_output=True, text=True,
        )

    def test_update_migrates_legacy_install_setup_and_approvals(self):
        repo, legacy = self.legacy_setup()
        result = self.update(repo)
        self.assertFalse(legacy.exists())
        self.assertIn("Removed old skill", result.stdout)
        script = str((self.skills / "remind-me-again/scripts").resolve())
        servers = json.loads((repo / ".mcp.json").read_text())["mcpServers"]
        self.assertEqual(list(servers), ["remind-me-again"])
        self.assertEqual(servers["remind-me-again"]["args"][1], f"{script}/checkpoint_mcp.py")
        self.assertEqual(servers["remind-me-again"]["args"][-1], str(repo.resolve()))
        hooks = json.loads((repo / ".github/hooks/session-info.json").read_text())["hooks"]
        self.assertTrue(all(
            entries[0]["args"][0] == f"{script}/autosave.py" for entries in hooks.values()
        ))
        permissions = json.loads(
            (self.skills.parent / ".copilot/permissions-config.json").read_text()
        )
        approvals = permissions["locations"][str(repo.resolve())]["tool_approvals"]
        self.assertEqual({item["serverName"] for item in approvals}, {"remind-me-again"})
        self.assertEqual(len(approvals), 2)
        self.assertNotIn("Migrated", self.update(repo).stdout)

    def test_modified_legacy_install_leaves_everything_unchanged(self):
        repo, legacy = self.legacy_setup()
        (legacy / "scripts/storage.py").write_text("local changes")
        mcp = (repo / ".mcp.json").read_bytes()
        result = self.update(repo)
        self.assertIn("left unchanged", result.stdout)
        self.assertTrue(legacy.is_dir())
        self.assertEqual((repo / ".mcp.json").read_bytes(), mcp)

    def test_unrecognized_legacy_setup_keeps_old_skill_for_working_hooks(self):
        repo, legacy = self.legacy_setup()
        mcp_path = repo / ".mcp.json"
        servers = json.loads(mcp_path.read_text())
        servers["mcpServers"]["session-summary"]["command"] = 5
        mcp_path.write_text(json.dumps(servers))
        result = self.update(repo)
        self.assertIn("left unchanged", result.stdout)
        self.assertTrue(legacy.is_dir())
        self.assertIn("session-summary/scripts", (repo / ".github/hooks/session-info.json").read_text())

    def test_downloaded_archive_installs_updates_and_uninstalls_via_cli(self):
        output = self.skills.parent / "release"
        subprocess.run(
            [
                sys.executable, "-B", str(ROOT / "build_release.py"),
                "--version", "v0.1.0", "--output-dir", str(output),
            ],
            check=True, capture_output=True, text=True,
        )
        archive_path = output / "remind-me-again-v0.1.0.zip"
        checksum = archive_path.with_suffix(".zip.sha256").read_text().split()[0]
        self.assertEqual(checksum, hashlib.sha256(archive_path.read_bytes()).hexdigest())
        extracted = self.skills.parent / "download"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(len(archive.namelist()), len(installer.PAYLOAD) + 3)
            archive.extractall(extracted)
        command = [
            sys.executable, "-B", str(extracted / "remind-me-again/install.py"),
            "--skills-dir", str(self.skills),
        ]
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        for arguments in ([], ["--update"]):
            subprocess.run(
                command + arguments, env=environment, check=True,
                capture_output=True, text=True,
            )
        for script in ("autosave.py", "save_summary.py", "retrieval.py", "rollup.py"):
            subprocess.run(
                [sys.executable, "-B", str(self.skills / "remind-me-again/scripts" / script), "--help"],
                check=True, capture_output=True, text=True,
            )
        subprocess.run(
            command + ["--uninstall", "--cwd", str(self.skills.parent)], env=environment, check=True,
            capture_output=True, text=True,
        )
        self.assertFalse((self.skills / "remind-me-again").exists())


if __name__ == "__main__":
    unittest.main()
