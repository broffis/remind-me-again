import importlib.util
import hashlib
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
