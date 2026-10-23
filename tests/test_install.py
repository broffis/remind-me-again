import importlib.util
import hashlib
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
        for script in (ROOT / "session-summary/scripts").glob("*.py"):
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
            installer.uninstall(self.skills)

    def test_uninstall_removes_only_owned_skill_and_preserves_summaries(self):
        destination = installer.install(ROOT, self.skills)
        summaries = self.skills.parent / "session-info"
        summaries.mkdir()
        (summaries / "saved.md").write_text("Keep this.")
        installer.uninstall(self.skills)
        self.assertFalse(destination.exists())
        self.assertEqual((summaries / "saved.md").read_text(), "Keep this.")

    def test_symlink_install_is_not_replaced_or_deleted(self):
        self.skills.mkdir()
        destination = self.skills / "session-summary"
        destination.symlink_to(ROOT / "session-summary", target_is_directory=True)
        for action in (
            lambda: installer.install(ROOT, self.skills, update=True),
            lambda: installer.uninstall(self.skills),
        ):
            with self.assertRaisesRegex(ValueError, "symbolic"):
                action()
        self.assertTrue(destination.is_symlink())

    def test_downloaded_archive_installs_updates_and_uninstalls_via_cli(self):
        output = self.skills.parent / "release"
        subprocess.run(
            [
                sys.executable, "-B", str(ROOT / "build_release.py"),
                "--version", "v0.1.0", "--output-dir", str(output),
            ],
            check=True, capture_output=True, text=True,
        )
        archive_path = output / "session-summary-skill-v0.1.0.zip"
        checksum = archive_path.with_suffix(".zip.sha256").read_text().split()[0]
        self.assertEqual(checksum, hashlib.sha256(archive_path.read_bytes()).hexdigest())
        extracted = self.skills.parent / "download"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertEqual(len(archive.namelist()), len(installer.PAYLOAD) + 3)
            archive.extractall(extracted)
        command = [
            sys.executable, "-B", str(extracted / "session-summary-skill/install.py"),
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
                [sys.executable, "-B", str(self.skills / "session-summary/scripts" / script), "--help"],
                check=True, capture_output=True, text=True,
            )
        subprocess.run(
            command + ["--uninstall"], env=environment, check=True,
            capture_output=True, text=True,
        )
        self.assertFalse((self.skills / "session-summary").exists())


if __name__ == "__main__":
    unittest.main()
