import ast
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import security_config as config


class ConfigurationTests(unittest.TestCase):
    def test_missing_value_does_not_disclose_other_secrets(self):
        with patch.dict(os.environ, {"OTHER_SECRET": "synthetic-secret"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "POSTGRES_PASSWORD") as result:
                config.required_env("POSTGRES_PASSWORD")
            self.assertNotIn("synthetic-secret", str(result.exception))

    def test_database_password_special_characters(self):
        env = dict(POSTGRES_HOST="localhost", POSTGRES_PORT="5432",
                   POSTGRES_DB="demo", POSTGRES_USER="demo",
                   POSTGRES_PASSWORD="synthetic:@/#? password")
        with patch.dict(os.environ, env, clear=True):
            url = config.database_url()
            self.assertEqual(url.password, env["POSTGRES_PASSWORD"])
            self.assertNotIn(env["POSTGRES_PASSWORD"], str(url))

    def test_relative_path_is_independent_of_working_directory(self):
        with patch.dict(os.environ, {"TEST_PATH": "data/example.csv"}, clear=True):
            self.assertEqual(config.configured_path("TEST_PATH"), config.ROOT / "data/example.csv")

    def test_empty_token_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token.txt"
            token.write_text("  ", encoding="utf-8")
            with patch.dict(os.environ, {"GESTTA_TOKEN_PATH": str(token)}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "vazio"):
                    config.gestta_token()

    def test_python_sources_parse(self):
        for path in (ROOT / "src").rglob("*.py"):
            with self.subTest(path=str(path.relative_to(ROOT))):
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


if __name__ == "__main__":
    unittest.main()
