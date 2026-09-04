"""S40 environment intelligence tests: sections, secrets-proof, mismatch.

Hermetic: no network; binary probes limited to what shutil.which finds on
this machine; GPU probe tolerated absent.
"""

import json
import os
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qacompanion.agent import ToolCall, ToolRegistry, Workspace
from qacompanion.agent.environment import EnvironmentToolkit, find_mismatches
from qacompanion.agent.fs_tools import agent_registry


class EnvTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = Workspace(self.tmp)
        self.toolkit = EnvironmentToolkit(self.ws)
        self.reg = ToolRegistry()
        for tool in self.toolkit.tools():
            self.reg.register(tool)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, **arguments):
        return self.reg.execute(ToolCall(name="get_environment_summary",
                                         arguments=arguments),
                                workspace=self.ws)

    def payload(self, **arguments):
        out = self.call(**arguments)
        self.assertTrue(out.ok, f"summary failed: {out.error}")
        return json.loads(out.output)


class TestSummarySections(EnvTestBase):
    def test_full_summary_has_all_sections_and_is_serializable(self):
        payload = self.payload()
        for section in ("os", "cpu", "memory", "gpu", "runtimes",
                        "package_managers", "disk", "variables"):
            self.assertIn(section, payload)
        line = json.dumps(payload)  # must not raise
        self.assertTrue(line)

    def test_os_section_sane(self):
        payload = self.payload(section="os")
        self.assertIn(payload["os"]["system"], ("Windows", "Linux", "Darwin"))
        self.assertTrue(payload["os"]["python"])

    def test_memory_returns_ints_on_windows(self):
        payload = self.payload(section="memory")
        memory = payload["memory"]
        if isinstance(memory, dict):
            self.assertIsInstance(memory["total_bytes"], int)
        else:
            self.assertEqual(memory, "unknown")

    def test_python_and_git_runtimes_found(self):
        payload = self.payload(section="runtimes")
        self.assertTrue(payload["runtimes"]["python"])
        self.assertIsNotNone(payload["runtimes"]["git"])

    def test_absent_binary_reported_not_crashed(self):
        with patch("qacompanion.agent.environment.shutil.which",
                   return_value=None):
            payload = self.payload(section="runtimes")
        self.assertIsNone(payload["runtimes"]["node"])

    def test_gpu_null_without_evidence(self):
        with patch("qacompanion.agent.environment.shutil.which",
                   return_value=None):
            payload = self.payload(section="gpu")
        self.assertIsNone(payload["gpu"])

    def test_disk_section(self):
        payload = self.payload(section="disk")
        self.assertIsInstance(payload["disk"]["free_bytes"], int)

    def test_package_managers_presence_flags(self):
        payload = self.payload(section="package_managers")
        for name in ("pip", "npm", "cargo"):
            self.assertIsInstance(payload["package_managers"][name], bool)


class TestVariableMetadata(EnvTestBase):
    def test_names_and_setness_never_values(self):
        with patch.dict(os.environ, {"SECRET_TOKEN": "super-secret-value"}):
            # pretend SECRET_TOKEN is watched by patching the watch list
            with patch("qacompanion.agent.environment.WATCHED_VARIABLES",
                       ("PATH", "SECRET_TOKEN")):
                payload = self.payload(section="variables")
        variables = {v["name"]: v["set"] for v in payload["variables"]}
        self.assertTrue(variables["SECRET_TOKEN"])
        self.assertNotIn("super-secret-value", json.dumps(payload))


class TestPorts(EnvTestBase):
    def test_bound_port_unavailable_free_port_available(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.listen(1)
        try:
            payload = self.payload(check_ports=[port])
            self.assertFalse(payload["ports"][0]["available"])
        finally:
            sock.close()
        payload = self.payload(check_ports=[port])
        self.assertTrue(payload["ports"][0]["available"])


class TestMismatchCheck(EnvTestBase):
    def test_satisfied_requirement(self):
        import sys
        major = sys.version_info[0]
        payload = self.payload(requires={"python": f"{major}.0"})
        self.assertTrue(payload["satisfied"])
        self.assertEqual(payload["mismatches"], [])

    def test_unsatisfiable_requirement_reported(self):
        payload = self.payload(requires={"python": "999.0"})
        self.assertFalse(payload["satisfied"])
        self.assertEqual(payload["mismatches"][0]["tool"], "python")
        self.assertIsNotNone(payload["mismatches"][0]["found"])

    def test_missing_tool_mismatch_with_null_found(self):
        with patch("qacompanion.agent.environment.shutil.which",
                   return_value=None):
            mismatches = find_mismatches({"node": "18"})
        self.assertEqual(mismatches[0]["found"], None)

    def test_version_tuple_compare(self):
        from qacompanion.agent.environment import _version_tuple
        self.assertEqual(_version_tuple("v18.17.0"), (18, 17, 0))
        self.assertIsNone(_version_tuple("unknown"))


class TestSectionFilter(EnvTestBase):
    def test_section_returns_only_that_section(self):
        payload = self.payload(section="cpu")
        self.assertIn("cpu", payload)
        self.assertNotIn("os", payload)

    def test_unknown_section_structured_error(self):
        out = self.call(section="quantum")
        self.assertFalse(out.ok)
        self.assertIn("unknown section", out.error)


class TestRegistration(EnvTestBase):
    def test_tool_metadata(self):
        described = self.reg.describe()[0]
        self.assertEqual(described["name"], "get_environment_summary")
        self.assertEqual(described["side_effect_level"], "READ_ONLY")
        self.assertEqual(described["category"], "environment")
        self.assertTrue(described["requires_workspace"])

    def test_agent_registry_includes_environment_tool(self):
        reg = agent_registry(self.ws)
        self.assertIn("get_environment_summary", reg.names())


if __name__ == "__main__":
    unittest.main()
