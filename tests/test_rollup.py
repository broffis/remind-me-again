from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "session-summary/scripts")
)
import rollup
from save_summary import save_summary


FIRST = "12345678-1234-1234-1234-123456789abc"
SECOND = "87654321-4321-4321-4321-cba987654321"


class RollupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.cwd = self.home / "personal" / "recipe-app"
        self.cwd.mkdir(parents=True)
        patcher = patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)

    def raw(self, text="First progress.", session=FIRST, day="2026-10-22"):
        return save_summary(self.cwd, session, day, text)

    def prepare(self, day="2026-10-23"):
        return rollup.prepare(self.cwd, day)

    def test_includes_every_related_session_and_date_and_resume_command(self):
        self.raw()
        self.raw("Second progress.", SECOND, "2026-10-23")
        plan = self.prepare()
        self.assertEqual(len(plan["pending"]), 2)
        destination = rollup.save(plan, "Combined progress.")
        self.assertEqual(destination.name, "2026-10-23.md")
        self.assertEqual(destination.parent.name, "rollup")
        content = destination.read_text()
        for day, session in (("2026-10-22", FIRST), ("2026-10-23", SECOND)):
            self.assertIn(f"| {day} | `{session}` |", content)
            self.assertIn(f"copilot --resume={session}", content)
        self.assertIn("Combined progress.", content)

    def test_refreshes_same_file_with_only_new_input_and_retains_sessions(self):
        self.raw()
        path = rollup.save(self.prepare(), "First synthesis.")
        self.raw("Additional progress.", SECOND)
        plan = self.prepare()
        self.assertEqual(len(plan["pending"]), 1)
        self.assertIn("Additional progress.", plan["pending"][0]["text"])
        self.assertNotIn("First progress.", plan["pending"][0]["text"])
        self.assertEqual(plan["existing_summary"], "First synthesis.")
        self.assertEqual(rollup.save(plan, "Updated synthesis."), path)
        content = path.read_text()
        self.assertIn("Updated synthesis.", content)
        self.assertNotIn("First synthesis.", content)
        self.assertEqual(content.count(f"| `copilot --resume={FIRST}` |"), 1)
        self.assertIn(f"copilot --resume={SECOND}", content)

    def test_next_day_only_includes_new_material_even_in_old_raw_file(self):
        self.raw()
        previous = rollup.save(self.prepare(), "Yesterday's synthesis.")
        original = previous.read_bytes()
        self.raw("Late addition.", SECOND)
        plan = self.prepare("2026-10-24")
        self.assertEqual(plan["existing_summary"], "")
        self.assertEqual(plan["sessions"], [{"date": "2026-10-22", "id": SECOND}])
        self.assertNotIn("First progress.", plan["pending"][0]["text"])
        rollup.save(plan, "New synthesis.")
        self.assertEqual(previous.read_bytes(), original)
        self.assertEqual(self.prepare("2026-10-25")["pending"], [])

    def test_no_new_input_does_not_write(self):
        self.assertEqual(self.prepare()["pending"], [])
        with self.assertRaisesRegex(ValueError, "No new"):
            rollup.save(self.prepare(), "Nothing new.")
        self.assertFalse((self.home / ".copilot").exists())
        self.raw()
        path = rollup.save(self.prepare(), "Saved synthesis.")
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "No new"):
            rollup.save(self.prepare(), "Repeated synthesis.")
        self.assertEqual(path.read_bytes(), original)

    def test_stale_plan_is_rejected_without_consuming_new_progress(self):
        self.raw()
        plan = self.prepare()
        self.raw("New progress.")
        with self.assertRaisesRegex(ValueError, "changed"):
            rollup.save(plan, "Stale synthesis.")
        self.assertIn("New progress.", self.prepare()["pending"][0]["text"])

    def test_concurrent_rollup_rejects_stale_plan_and_preserves_saved_file(self):
        self.raw()
        stale = self.prepare()
        path = rollup.save(self.prepare(), "Another writer's synthesis.")
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "changed"):
            rollup.save(stale, "Stale synthesis.")
        self.assertEqual(path.read_bytes(), original)

    def test_same_session_on_multiple_dates_keeps_both_dates(self):
        self.raw(day="2026-10-21")
        self.raw(day="2026-10-22")
        self.assertEqual(self.prepare()["sessions"], [
            {"date": "2026-10-21", "id": FIRST},
            {"date": "2026-10-22", "id": FIRST},
        ])

    def test_cli_prepare_and_save(self):
        self.raw()
        command = [sys.executable, "-B", str(Path(rollup.__file__))]
        environment = dict(os.environ, HOME=str(self.home))
        prepared = subprocess.run(
            command + ["prepare", "--cwd", str(self.cwd), "--date", "2026-10-23"],
            env=environment, capture_output=True, text=True, check=True,
        )
        plan = self.home / "plan.json"
        plan.write_text(prepared.stdout)
        self.assertEqual(len(json.loads(prepared.stdout)["pending"]), 1)
        saved = subprocess.run(
            command + ["save", "--plan", str(plan)],
            input="CLI synthesis.", env=environment, capture_output=True,
            text=True, check=True,
        )
        destination = Path(saved.stdout.strip())
        self.assertIn("CLI synthesis.", destination.read_text())
        self.assertEqual(self.prepare()["pending"], [])

    def test_rejects_modified_consumed_content_and_missing_raw_files(self):
        raw = self.raw()
        rollup.save(self.prepare(), "Saved synthesis.")
        original = raw.read_bytes()
        raw.write_text("Changed earlier content.")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.prepare()
        raw.write_bytes(original)
        raw.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            self.prepare()

    def test_rejects_empty_synthesis_and_untracked_existing_rollup(self):
        self.raw()
        plan = self.prepare()
        with self.assertRaisesRegex(ValueError, "empty"):
            rollup.save(plan, " \n")
        path = self.home / ".copilot/session-info/personal/recipe-app/rollup/2026-10-23.md"
        path.write_text("An older handwritten rollup.")
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.prepare()
        self.assertEqual(path.read_text(), "An older handwritten rollup.")


if __name__ == "__main__":
    unittest.main()
