import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from delivery_qc.cli import _read_app_key


class ReadAppKeyTests(unittest.TestCase):
    def test_prefers_environment(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            secret = Path(temporary_directory) / "key"
            secret.write_text("file-key\n", encoding="utf-8")
            environment = {
                "STRATUS_APP_KEY": " env-key ",
                "STRATUS_APP_KEY_FILE": str(secret),
            }
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(_read_app_key(), "env-key")

    def test_reads_file(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            secret = Path(temporary_directory) / "key"
            secret.write_text("file-key\n", encoding="utf-8")
            environment = {"STRATUS_APP_KEY_FILE": str(secret)}
            with patch.dict(os.environ, environment, clear=True):
                self.assertEqual(_read_app_key(), "file-key")


if __name__ == "__main__":
    unittest.main()
