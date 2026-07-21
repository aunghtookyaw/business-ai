import email.message
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import BigShotBusinessOS as launcher


class FakeResponse:
    def __init__(self, payload, content_type="application/json", status=200):
        self.status = status
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.headers = email.message.Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self._body


class LauncherLogicTests(unittest.TestCase):
    def test_current_server_ip_is_accepted(self):
        self.assertEqual(
            launcher.discover_server("192.168.0.102", ["192.168.0.20"], lambda ip: ip == "192.168.0.102"),
            "192.168.0.102",
        )

    def test_saved_old_ip_failure_falls_back_to_scan(self):
        good_ip = "192.168.0.102"
        self.assertEqual(
            launcher.discover_server("192.168.0.88", [good_ip], lambda ip: ip == good_ip),
            good_ip,
        )

    def test_subnet_scan_finds_server(self):
        candidates = launcher.subnet_candidates(["10.20.30.44"])
        self.assertIn("10.20.30.1", candidates)
        self.assertIn("10.20.30.254", candidates)
        self.assertNotIn("10.20.30.44", candidates)
        self.assertEqual(launcher.scan_candidates(candidates, lambda ip: ip == "10.20.30.9"), "10.20.30.9")

    def test_manual_ip_validation_and_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "server.json"
            launcher.save_ip("192.168.50.7", path)
            self.assertEqual(launcher.load_saved_ip(path), "192.168.50.7")
        with mock.patch.object(launcher.urllib.request, "urlopen", return_value=FakeResponse({"status": "running"})):
            self.assertTrue(launcher.validate_server("192.168.50.7"))

    def test_server_unavailable_case(self):
        self.assertIsNone(launcher.discover_server("192.168.0.88", ["192.168.0.1"], lambda _ip: False))

    def test_malformed_status_response_is_rejected(self):
        responses = [
            FakeResponse(b"not-json"),
            FakeResponse({"status": "stopped"}),
            FakeResponse({"status": "running"}, content_type="text/plain"),
        ]
        for response in responses:
            with self.subTest(response=response), mock.patch.object(launcher.urllib.request, "urlopen", return_value=response):
                self.assertFalse(launcher.validate_server("192.168.0.102"))

    def test_automatic_ip_migration_saves_new_ip_and_opens_chrome_without_dialog(self):
        old_ip = "192.168.0.88"
        new_ip = "192.168.0.102"
        validation_order = []

        def validator(ip):
            validation_order.append(ip)
            return ip == new_ip

        with tempfile.TemporaryDirectory() as directory:
            saved_path = Path(directory) / "server.json"
            launcher.save_ip(old_ip, saved_path)

            discovered = launcher.discover_server(
                launcher.load_saved_ip(saved_path),
                candidates=[new_ip],
                validator=validator,
            )
            self.assertEqual(discovered, new_ip)
            self.assertEqual(validation_order, [old_ip, new_ip])

            fake_launcher = launcher.Launcher.__new__(launcher.Launcher)
            fake_launcher.root = mock.Mock()
            with (
                mock.patch.object(launcher, "cache_path", return_value=saved_path),
                mock.patch.object(launcher, "chrome_executable", return_value=r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                mock.patch.object(launcher.subprocess, "Popen") as popen,
                mock.patch.object(fake_launcher, "handle_not_found") as not_found_dialog,
            ):
                fake_launcher.open_server(discovered)

            self.assertEqual(launcher.load_saved_ip(saved_path), new_ip)
            popen.assert_called_once_with(
                [r"C:\Program Files\Google\Chrome\Application\chrome.exe", f"http://{new_ip}:5059/business-os"]
            )
            fake_launcher.root.destroy.assert_called_once_with()
            not_found_dialog.assert_not_called()


if __name__ == "__main__":
    unittest.main()
