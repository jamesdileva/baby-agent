"""Regression tests for super-audit S1 (F1): every annotation in
qacompanion.agent must resolve eagerly.

Failure mode: missing `typing` names (Optional/Tuple) or module names
(Workspace) used only in annotations import cleanly on Python 3.14 (PEP
649/749 defers evaluation) but raise NameError at class/function definition
time on 3.9-3.13, breaking the whole agent package there. `typing.get_type_hints`
evaluates annotations eagerly on every version, so it pins the failure mode
even when run under 3.14. Stdlib only.
"""

import importlib
import inspect
import pkgutil
import typing
import unittest

import qacompanion.agent as _agent_pkg


def _iter_agent_modules():
    for modinfo in sorted(pkgutil.iter_modules(_agent_pkg.__path__),
                          key=lambda m: m.name):
        yield "qacompanion.agent." + modinfo.name


def _unresolvable_annotations():
    """(module, qualname, error) for every NameError-raising annotation."""
    problems = []
    for name in _iter_agent_modules():
        module = importlib.import_module(name)
        for _objname, obj in inspect.getmembers(module):
            if not (inspect.isclass(obj) or inspect.isfunction(obj)):
                continue
            if getattr(obj, "__module__", None) != module.__name__:
                continue
            targets = [obj] + [member for _mname, member
                               in vars(obj).items()
                               if inspect.isfunction(member)]
            for target in targets:
                try:
                    typing.get_type_hints(target)
                except NameError as exc:
                    problems.append(
                        (name, getattr(target, "__qualname__", target),
                         str(exc)))
    return problems


class TestAgentAnnotationsResolve(unittest.TestCase):
    def test_no_unresolvable_annotations_f1(self):
        problems = _unresolvable_annotations()
        self.assertEqual(
            [], problems,
            "unresolvable annotations (NameError under eager evaluation): "
            + "; ".join(f"{mod}.{qual}: {err}"
                        for mod, qual, err in problems))

    def test_known_f1_sites_resolve(self):
        # The exact F1 sites: each must survive eager hint evaluation.
        from qacompanion.agent import multi_agent, processes, providers
        from qacompanion.agent import skills, websearch

        self.assertIn("model", typing.get_type_hints(
            providers.GeminiModelProvider.__init__))
        self.assertIn("model", typing.get_type_hints(
            providers.OllamaProvider._generate_native))
        self.assertIn("verifier", typing.get_type_hints(
            multi_agent.MultiAgentLab.__init__))
        self.assertIn("timeout_seconds", typing.get_type_hints(
            processes.wait_for_port_serving))
        self.assertIn("workspace", typing.get_type_hints(
            skills.update_agent_registry))
        self.assertIn("workspace", typing.get_type_hints(
            websearch.update_agent_registry))


if __name__ == "__main__":
    unittest.main()
