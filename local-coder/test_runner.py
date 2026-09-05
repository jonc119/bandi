import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


spec = importlib.util.spec_from_file_location("local_coder", Path(__file__).resolve().parents[1] / "scripts/local_coder.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_paths_cannot_escape(self):
        with TemporaryDirectory() as temporary:
            for relative in ("../secret", "/etc/passwd", "C:/secret", "tests\\bad.py", ""):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    runner.safe_path(Path(temporary), relative)

    def test_only_declared_files_are_editable(self):
        with self.assertRaises(ValueError):
            runner.validate_reply({"summary": "unsafe", "edits": [{"path": "config/qc.toml", "content": "mode='live'"}]}, ["tests/test_new.py"])

    def test_empty_and_invalid_python_rejected(self):
        for content in ("", "def broken("):
            with self.subTest(content=content), self.assertRaises((ValueError, SyntaxError)):
                runner.validate_reply({"summary": "test", "edits": [{"path": "tests/test_new.py", "content": content}]}, ["tests/test_new.py"])

    def test_model_cannot_add_shell_actions(self):
        with self.assertRaises(ValueError):
            runner.validate_reply({"summary": "test", "edits": [], "command": "anything"}, [])

    def test_test_container_has_no_network_or_writable_host_mount(self):
        command = runner.test_command(Path("workspace"), "test-container")
        self.assertEqual("none", command[command.index("--network") + 1])
        self.assertIn("--read-only", command)
        self.assertIn("--user", command)
        mount = command[command.index("--mount") + 1]
        self.assertTrue(mount.endswith(",readonly"))
        self.assertNotIn("docker.sock", " ".join(command))
        self.assertNotIn("--rm", command)

    def test_source_edits_are_supported_but_integrations_are_not(self):
        runner.validate_task({"instruction": "Fix one pure function", "allowed_files": ["src/delivery_qc/domain/rules.py"], "context_files": ["src/delivery_qc/domain/models.py"]})
        with self.assertRaises(ValueError):
            runner.validate_task({"instruction": "unsafe", "allowed_files": ["scripts/run-daily-shadow.ps1"], "context_files": ["src/delivery_qc/domain/models.py"]})


if __name__ == "__main__":
    unittest.main()
