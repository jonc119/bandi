from pathlib import Path
import tempfile
import unittest

from delivery_qc.config import load_config


class ConfigTests(unittest.TestCase):
    def test_live_mode_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "qc.toml"
            config_path.write_text('[deployment]\nmode = "live"\n', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "shadow-only"):
                load_config(config_path, root)


if __name__ == "__main__":
    unittest.main()
