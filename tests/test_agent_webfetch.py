"""S43 URL context & retrieval tests: safety policy, fetch, extract, download.

Hermetic: urllib and getaddrinfo are ALWAYS mocked — no test touches the
network.
"""

import hashlib
import io
import json
import shutil
import socket
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.fs_tools import agent_registry
from qacompanion.agent.webfetch import (
    WebFetchError,
    WebFetchToolkit,
    extract_relevant,
    fetch_page,
)

HTML_PAGE = b"""<html><head><title>Official Docs</title>
<base href="https://docs.example.com/v5/"></head>
<body>
<script>tracking();</script>
<h1>Installation</h1><p>Run the installer as admin.</p>
<style>.x{color:red}</style>
<p>Configuration lives in the config file.</p>
<a href="advanced.html">Advanced setup</a>
</body></html>"""


def _mock_urlopen(payload: bytes, content_type="text/html", final_url=None,
                  status=200):
    class FakeResponse:
        def __init__(self):
            self._io = io.BytesIO(payload)

        @property
        def status(self):
            return status

        def geturl(self):
            return final_url or "https://docs.example.com/v5/guide.html"

        def read(self, amount=-1):
            return self._io.read(amount)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(request, timeout=None):
        response = FakeResponse()
        response.headers = {"Content-Type": f"{content_type}; charset=utf-8"}
        return response

    return urlopen


def _public_dns(hostname, servicename=None):
    # deterministic stand-in for real resolution: docs.example.com -> public
    import socket
    return [(socket.AF_INET, None, None, "", ("93.184.216.34", 0))]


POLICY_PATCH = patch("qacompanion.agent.webfetch.socket.getaddrinfo",
                     side_effect=_public_dns)


class TestUrlSafetyPolicy(unittest.TestCase):
    def _fetch_expect_error(self, url, match):
        with POLICY_PATCH:
            with self.assertRaises(WebFetchError) as ctx:
                fetch_page(url)
        self.assertIn(match, str(ctx.exception))

    def test_scheme_rejected(self):
        self._fetch_expect_error("ftp://example.com/x", "scheme not allowed")

    def test_port_rejected(self):
        self._fetch_expect_error("http://example.com:8080/x", "port not allowed")

    def test_unresolvable_rejected(self):
        def dead_dns(hostname, servicename=None):
            raise socket.gaierror("no dns")
        with patch("qacompanion.agent.webfetch.socket.getaddrinfo",
                   side_effect=dead_dns):
            with self.assertRaises(WebFetchError) as ctx:
                fetch_page("https://ghost.example.com/")
        self.assertIn("cannot resolve", str(ctx.exception))

    def test_private_ips_rejected(self):
        import socket as socket_mod
        cases = {
            "127.0.0.1": "non-public",
            "10.0.0.5": "non-public",
            "192.168.1.10": "non-public",
            "172.16.0.9": "non-public",
            "169.254.169.254": "non-public",  # cloud metadata endpoint
            "fe80::1": "non-public",
            "0.0.0.0": "non-public",
        }
        for ip, match in cases.items():
            def fake_dns(hostname, servicename=None, _ip=ip):
                return [(socket_mod.AF_INET, None, None, "", (_ip, 0))]
            with patch("qacompanion.agent.webfetch.socket.getaddrinfo",
                       side_effect=fake_dns):
                with self.assertRaises(WebFetchError, msg=ip) as ctx:
                    fetch_page("https://evil.example.com/secret")
            self.assertIn(match, str(ctx.exception))

    def test_public_ip_passes_policy(self):
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(HTML_PAGE)):
            page = fetch_page("https://docs.example.com/v5/guide.html")
        self.assertEqual(page["title"], "Official Docs")


class TestFetchPage(unittest.TestCase):
    def test_extraction(self):
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(HTML_PAGE)):
            page = fetch_page("https://docs.example.com/v5/guide.html")
        self.assertEqual(page["title"], "Official Docs")
        self.assertIn("Run the installer as admin.", page["text"])
        self.assertNotIn("tracking()", page["text"])
        self.assertNotIn("color:red", page["text"])
        links = {link["url"] for link in page["links"]}
        self.assertIn("https://docs.example.com/v5/advanced.html", links)

    def test_size_cap_truncates(self):
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(b"x" * (2 * 1024 * 1024 + 100))):
            page = fetch_page("https://docs.example.com/big")
        self.assertTrue(page["truncated"])

    def test_binary_content_type_rejected(self):
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(b"\x00\x01",
                                          content_type="application/octet-stream")):
            with self.assertRaises(WebFetchError) as ctx:
                fetch_page("https://docs.example.com/blob")
        self.assertIn("download_artifact", str(ctx.exception))

    def test_http_error_structured(self):
        def error_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 404, "Nope", {},
                                         io.BytesIO(b""))
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=error_urlopen):
            with self.assertRaises(WebFetchError) as ctx:
                fetch_page("https://docs.example.com/missing")
        self.assertIn("HTTP 404", str(ctx.exception))


class TestExtractRelevant(unittest.TestCase):
    def test_matching_passages(self):
        text = ("Install with the installer. "
                "Configuration lives in the config file. "
                "Uninstall reverses everything.")
        excerpts = extract_relevant(text, "config file")
        self.assertEqual(len(excerpts), 1)
        self.assertIn("Configuration", excerpts[0])

    def test_no_match_is_empty(self):
        self.assertEqual(extract_relevant("nothing here", "quantum"), [])


class TestDownloadArtifact(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.toolkit = WebFetchToolkit(self.ws)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_download_into_workspace(self):
        payload = b"artifact-bytes-123"
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(payload,
                                          content_type="application/octet-stream")):
            out = self.toolkit.download_artifact(
                "https://docs.example.com/file.bin", "downloads/file.bin")
        record = json.loads(out)
        self.assertEqual(record["path"], "downloads/file.bin")
        self.assertEqual(record["bytes"], len(payload))
        self.assertEqual(record["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(
            (self.tmp / "downloads" / "file.bin").read_bytes(), payload)

    def test_escape_path_rejected(self):
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(b"x")):
            with self.assertRaises(WebFetchError):
                self.toolkit.download_artifact(
                    "https://docs.example.com/x", "../evil.bin")

    def test_oversize_rejected_before_write(self):
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(b"x" * 11 * 1024 * 1024,
                                          content_type="application/octet-stream")):
            with self.assertRaises(WebFetchError):
                self.toolkit.download_artifact(
                    "https://docs.example.com/huge.bin", "huge.bin")
        self.assertEqual(list(self.tmp.iterdir()), [])


class TestRegistration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.reg = ToolRegistry()
        for tool in WebFetchToolkit(self.ws).tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_three_tools_external(self):
        self.assertEqual(
            self.reg.names(), ["download_artifact", "extract_page", "open_url"])
        described = {d["name"]: d for d in self.reg.describe()}
        self.assertTrue(all(d["side_effect_level"] == "EXTERNAL"
                            for d in described.values()))
        self.assertTrue(described["download_artifact"]["requires_workspace"])
        self.assertFalse(described["open_url"]["requires_workspace"])

    def test_through_registry_with_confirmer(self):
        with POLICY_PATCH, patch(
                "qacompanion.agent.webfetch.urllib.request.urlopen",
                side_effect=_mock_urlopen(HTML_PAGE)):
            result = self.reg.execute(
                ToolCall(name="open_url",
                         arguments={"url": "https://docs.example.com/guide"}),
                workspace=self.ws, confirmer=lambda call, d: True)
        self.assertTrue(result.ok, result.error)
        page = json.loads(result.output)
        self.assertEqual(page["title"], "Official Docs")

    def test_default_posture_asks(self):
        result = self.reg.execute(
            ToolCall(name="open_url",
                     arguments={"url": "https://docs.example.com/guide"}),
            workspace=self.ws)
        self.assertFalse(result.ok)
        self.assertIn("no confirmer", result.error)

    def test_agent_registry_includes_url_tools(self):
        reg = agent_registry(self.ws)
        for name in ("open_url", "extract_page", "download_artifact"):
            self.assertIn(name, reg.names())


if __name__ == "__main__":
    unittest.main()
