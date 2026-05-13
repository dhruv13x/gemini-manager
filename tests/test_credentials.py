import os
import unittest
from unittest.mock import patch, MagicMock
import argparse
from gemini_manager.credentials import (
    resolve_credentials,
    load_env_file,
    get_doppler_token,
    fetch_doppler_secrets,
)


class TestCredentials(unittest.TestCase):
    # Note: We rely on pyfakefs (fs fixture) which is autouse in conftest.py
    # So standard os operations work on the fake filesystem.

    @patch("gemini_manager.credentials.os.environ", {})
    @patch("gemini_manager.credentials.load_env_file")
    @patch("gemini_manager.credentials.get_doppler_token")
    @patch("gemini_manager.credentials.get_setting")
    def test_cli_priority(self, mock_get_setting, mock_get_token, mock_load_env):
        # CLI args should win
        args = argparse.Namespace(b2_id="CLI_ID", b2_key="CLI_KEY", bucket="CLI_BUCKET")

        # Setup mocks to provide conflicting info
        mock_get_token.return_value = None
        mock_get_setting.return_value = "SETTINGS_VAL"

        cid, ckey, cbucket = resolve_credentials(args)
        self.assertEqual(cid, "CLI_ID")
        self.assertEqual(ckey, "CLI_KEY")
        self.assertEqual(cbucket, "CLI_BUCKET")

    @patch("gemini_manager.credentials.os.environ", {})
    @patch("gemini_manager.credentials.load_env_file")
    @patch("gemini_manager.credentials.get_doppler_token")
    @patch("gemini_manager.credentials.fetch_doppler_secrets")
    @patch("gemini_manager.credentials.get_setting")
    def test_doppler_priority(
        self, mock_get_setting, mock_fetch, mock_get_token, mock_load_env
    ):
        # CLI args missing
        args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)

        # Doppler token found
        mock_get_token.return_value = "TOKEN"
        mock_fetch.return_value = {
            "GEMINI_B2_KEY_ID": "DOPPLER_ID",
            "GEMINI_B2_APP_KEY": "DOPPLER_KEY",
            "GEMINI_B2_BUCKET": "DOPPLER_BUCKET",
        }

        mock_get_setting.return_value = "SETTINGS_VAL"

        cid, ckey, cbucket = resolve_credentials(args)
        self.assertEqual(cid, "DOPPLER_ID")
        self.assertEqual(ckey, "DOPPLER_KEY")
        self.assertEqual(cbucket, "DOPPLER_BUCKET")

    @patch(
        "gemini_manager.credentials.os.environ",
        {
            "GEMINI_B2_KEY_ID": "ENV_ID",
            "GEMINI_B2_APP_KEY": "ENV_KEY",
            "GEMINI_B2_BUCKET": "ENV_BUCKET",
        },
    )
    @patch("gemini_manager.credentials.load_env_file")
    @patch("gemini_manager.credentials.get_doppler_token")
    @patch("gemini_manager.credentials.get_setting")
    def test_env_priority(self, mock_get_setting, mock_get_token, mock_load_env):
        args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)
        mock_get_token.return_value = None
        mock_get_setting.return_value = "SETTINGS_VAL"

        cid, ckey, cbucket = resolve_credentials(args)
        self.assertEqual(cid, "ENV_ID")

    @patch("gemini_manager.credentials.os.environ", {})
    @patch("gemini_manager.credentials.load_env_file")
    @patch("gemini_manager.credentials.get_doppler_token")
    @patch("gemini_manager.credentials.get_setting")
    def test_env_file_priority(self, mock_get_setting, mock_get_token, mock_load_env):
        args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)
        mock_get_token.return_value = None
        mock_load_env.side_effect = lambda x: (
            {
                "GEMINI_B2_KEY_ID": "FILE_ID",
                "GEMINI_B2_APP_KEY": "FILE_KEY",
                "GEMINI_B2_BUCKET": "FILE_BUCKET",
            }
            if x == ".env"
            else {}
        )
        mock_get_setting.return_value = "SETTINGS_VAL"

        cid, ckey, cbucket = resolve_credentials(args)
        self.assertEqual(cid, "FILE_ID")

    # --- New Tests for Coverage ---

    def test_load_env_file(self):
        # Use fake fs instead of mock_open
        with open(".env", "w") as f:
            f.write("KEY=VALUE\n#Comment\n\nBADLINE\nQUOTED='val'")

        env = load_env_file(".env")
        self.assertEqual(env["KEY"], "VALUE")
        self.assertEqual(env["QUOTED"], "val")
        self.assertNotIn("BADLINE", env)

    def test_load_env_file_not_exists(self):
        # File doesn't exist in fake fs
        env = load_env_file("missing")
        self.assertEqual(env, {})

    def test_load_env_file_error(self):
        # Create unreadable file
        # We can't easily make file unreadable for root in some envs, but let's try or mock open
        # Mocking builtins.open is safer for "Permission denied" simulation here.
        # But wait, we can't use mock_open if pyfakefs is active for other tests?
        # Tests are isolated.
        # Using patch on open is fine.
        with patch("builtins.open", side_effect=IOError):
            env = load_env_file(".env")
            self.assertEqual(env, {})

    @patch.dict(os.environ, {}, clear=True)
    def test_get_doppler_token_from_env(self):
        with patch.dict(os.environ, {"DOPPLER_TOKEN": "env_token"}):
            self.assertEqual(get_doppler_token(), "env_token")

    @patch.dict(os.environ, {}, clear=True)
    @patch("gemini_manager.credentials.load_env_file")
    def test_get_doppler_token_from_doppler_env(self, mock_load_env):
        def load_side_effect(path):
            if path == "doppler.env":
                return {"DOPPLER_TOKEN": "doppler_env_token"}
            return {}

        mock_load_env.side_effect = load_side_effect
        self.assertEqual(get_doppler_token(), "doppler_env_token")

    @patch.dict(os.environ, {}, clear=True)
    @patch("gemini_manager.credentials.load_env_file")
    def test_get_doppler_token_from_dot_env(self, mock_load_env):
        def load_side_effect(path):
            if path == ".env":
                return {"DOPPLER_TOKEN": "dot_env_token"}
            return {}

        mock_load_env.side_effect = load_side_effect
        self.assertEqual(get_doppler_token(), "dot_env_token")

    @patch.dict(os.environ, {}, clear=True)
    @patch("gemini_manager.credentials.load_env_file", return_value={})
    def test_get_doppler_token_none(self, mock_load_env):
        self.assertIsNone(get_doppler_token())

    @patch("requests.get")
    def test_fetch_doppler_secrets_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"SECRET": "value"}
        mock_get.return_value = mock_resp
        self.assertEqual(fetch_doppler_secrets("t"), {"SECRET": "value"})

    @patch("requests.get")
    def test_fetch_doppler_secrets_fail_status(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp
        self.assertIsNone(fetch_doppler_secrets("t"))

    @patch("requests.get")
    def test_fetch_doppler_secrets_exception(self, mock_get):
        mock_get.side_effect = Exception("Net error")
        self.assertIsNone(fetch_doppler_secrets("t"))

    @patch("gemini_manager.credentials.os.environ", {})
    @patch("gemini_manager.credentials.load_env_file", return_value={})
    @patch("gemini_manager.credentials.get_doppler_token", return_value=None)
    @patch("gemini_manager.credentials.get_setting")
    def test_resolve_credentials_legacy(self, mock_get_setting, mock_token, mock_load):
        args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)

        settings = {"b2_id": "L_ID", "b2_key": "L_KEY", "bucket": "L_BUCKET"}
        mock_get_setting.side_effect = lambda k: settings.get(k)

        cid, ckey, cbucket = resolve_credentials(args)
        self.assertEqual(cid, "L_ID")
        self.assertEqual(ckey, "L_KEY")
        self.assertEqual(cbucket, "L_BUCKET")

    @patch("gemini_manager.credentials.os.environ", {})
    @patch("gemini_manager.credentials.load_env_file", return_value={})
    @patch("gemini_manager.credentials.get_doppler_token", return_value=None)
    @patch("gemini_manager.credentials.get_setting", return_value=None)
    def test_resolve_credentials_fail_allowed(
        self, mock_get_setting, mock_token, mock_load
    ):
        args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)
        # We need to make sure c_id etc are None initially which they are by default in resolve_credentials logic
        result = resolve_credentials(args, allow_fail=True)
        # Should return None, None, None tuple, or maybe just None?
        # The code: return None, None, None
        self.assertEqual(result, (None, None, None))

    @patch("gemini_manager.credentials.os.environ", {})
    @patch("gemini_manager.credentials.load_env_file", return_value={})
    @patch("gemini_manager.credentials.get_doppler_token", return_value=None)
    @patch("gemini_manager.credentials.get_setting", return_value=None)
    def test_resolve_credentials_fail_exit(
        self, mock_get_setting, mock_token, mock_load
    ):
        args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)
        with self.assertRaises(SystemExit):
            resolve_credentials(args)

    @patch("gemini_manager.credentials.os.environ", {})
    @patch("gemini_manager.credentials.load_env_file", return_value={})
    @patch("gemini_manager.credentials.get_doppler_token")
    @patch("gemini_manager.credentials.fetch_doppler_secrets", return_value=None)
    @patch("gemini_manager.credentials.get_setting", return_value=None)
    def test_resolve_credentials_doppler_fail(
        self, mock_get_setting, mock_fetch, mock_token, mock_load
    ):
        # Doppler token exists but fetch fails
        mock_token.return_value = "TOKEN"
        args = argparse.Namespace(b2_id=None, b2_key=None, bucket=None)
        with self.assertRaises(SystemExit):
            resolve_credentials(args)


if __name__ == "__main__":
    unittest.main()
