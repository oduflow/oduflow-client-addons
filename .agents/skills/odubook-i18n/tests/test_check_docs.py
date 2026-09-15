import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "odubook_i18n_check_docs",
    SKILL_DIR / "scripts" / "check_docs.py",
)
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class CheckDocsTestCase(unittest.TestCase):

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name)
        self.module = self.repo / "addons" / "sample_module"
        self.doc = self.module / "doc"
        self.mirror = self.doc / "i18n" / "ru" / "user_guide.md"
        self.source = self.doc / "user_guide.md"
        self.module.mkdir(parents=True)
        self.mirror.parent.mkdir(parents=True)
        (self.module / "__manifest__.py").write_text("{}\n", encoding="utf-8")
        (self.repo / "LANG.local.md").write_text(
            "# Documentation Languages\n\n"
            "- source: en\n"
            "- targets: ru\n"
            "- translate: user_guide.md\n"
            "- source-only: tech_spec.md\n",
            encoding="utf-8",
        )
        self.write_pair(
            "# Guide\n\n- Use `field_name` from "
            "[the model](https://example.com/model).\n",
            "# Руководство\n\n- Используйте `field_name` из "
            "[модели](https://example.com/model).\n",
        )
        self.git("init", "-q")
        self.git("config", "user.email", "litnimax@users.noreply.github.com")
        self.git("config", "user.name", "Max")
        self.commit()

    def tearDown(self):
        self.temporary_directory.cleanup()

    def git(self, *args):
        subprocess.run(
            ["git"] + list(args),
            cwd=self.repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")

    def write_pair(self, source_text, mirror_body, marker_sha=None):
        self.source.write_text(source_text, encoding="utf-8")
        sha = marker_sha or CHECKER.source_sha(self.source)
        self.mirror.write_text(
            "<!-- i18n source=user_guide.md sha=%s lang=ru -->\n%s"
            % (sha, mirror_body),
            encoding="utf-8",
        )

    def run_check(self, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = CHECKER.check(self.repo, **kwargs)
        return result, output.getvalue()

    def test_clean_documents_pass_plain_and_git_aware_checks(self):
        self.assertEqual(self.run_check()[0], 0)
        self.assertEqual(self.run_check(against="HEAD")[0], 0)

    def test_changed_document_with_structure_drift_is_rejected(self):
        self.write_pair(
            "# Guide\n\n## New section\n\n- Use `field_name`.\n",
            "# Руководство\n\n## Новый раздел\n\nИспользуйте `field_name`.\n",
        )

        result, output = self.run_check(against="HEAD")

        self.assertEqual(result, 1)
        self.assertIn("structure: sample_module:ru:user_guide.md", output)
        self.assertIn("list structure", output)

    def test_marker_only_update_is_rejected(self):
        old_body = CHECKER.read_mirror(self.mirror)[1]
        self.write_pair(
            "# Guide\n\n- Use `field_name` from the configured model.\n",
            old_body,
        )

        result, output = self.run_check(against="HEAD")

        self.assertEqual(result, 1)
        self.assertIn("unchanged: sample_module:ru:user_guide.md", output)

    def test_fix_markers_requires_a_changed_valid_mirror(self):
        old_sha = CHECKER.source_sha(self.source)
        self.write_pair(
            "# Guide\n\n- Use `field_name` from the configured model.\n",
            "# Руководство\n\n- Используйте `field_name` из настроенной модели.\n",
            marker_sha=old_sha,
        )

        result, output = self.run_check(against="HEAD", fix_markers=True)

        self.assertEqual(result, 0)
        self.assertIn("updated: sample_module:ru:user_guide.md", output)
        marker = CHECKER.read_mirror(self.mirror)[0]
        self.assertEqual(marker.group("sha"), CHECKER.source_sha(self.source))

    def test_fix_markers_does_not_restamp_unchanged_stale_mirror(self):
        self.mirror.write_text(
            self.mirror.read_text(encoding="utf-8").replace(
                CHECKER.source_sha(self.source),
                "000000000000",
                1,
            ),
            encoding="utf-8",
        )
        self.commit()

        result, output = self.run_check(against="HEAD", fix_markers=True)

        self.assertEqual(result, 1)
        self.assertNotIn("updated:", output)
        self.assertIn("stale: sample_module:ru:user_guide.md", output)

    def test_strict_structure_exposes_legacy_drift_without_breaking_default(self):
        source_text = self.source.read_text(encoding="utf-8")
        self.write_pair(
            source_text,
            "# Руководство\n\n- Используйте поле из модели.\n",
        )
        self.commit()

        self.assertEqual(self.run_check()[0], 0)
        result, output = self.run_check(strict_structure=True)
        self.assertEqual(result, 1)
        self.assertIn("inline code", output)
        self.assertIn("link targets", output)

    def test_show_diff_prints_only_changed_source(self):
        old_body = CHECKER.read_mirror(self.mirror)[1]
        self.write_pair(
            "# Guide\n\n- Use `field_name` from the configured model.\n",
            old_body,
        )

        _, output = self.run_check(against="HEAD", show_diff=True)

        self.assertIn("source-diff: addons/sample_module/doc/user_guide.md", output)
        self.assertIn("+- Use `field_name` from the configured model.", output)

    def test_claude_entrypoint_uses_shared_checker(self):
        entrypoint = (
            SKILL_DIR.parents[2]
            / ".claude"
            / "skills"
            / "odubook-i18n"
            / "scripts"
            / "check_docs.py"
        )

        result = subprocess.run(
            ["python3", str(entrypoint), "--repo-root", str(self.repo)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Documentation translations are synchronized", result.stdout)


if __name__ == "__main__":
    unittest.main()
