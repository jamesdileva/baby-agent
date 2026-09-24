"""S62 trajectory curation tests: classify / score / reject / verdict /
dedupe / diversity / lessons / exports, all deterministic and hermetic.
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion.__main__ import main
from qacompanion.agent.curation import (
    CLASS_FAILED, CLASS_INVALID, CLASS_PARTIAL, CLASS_RECOVERED,
    CLASS_SUCCESS, CLASS_UNSAFE, DIMENSIONS,
    TrajectoryCurator, VERDICT_ACCEPT, VERDICT_REJECT, VERDICT_REVIEW,
    classify, format_report, hard_flags, redact, redact_all, score,
    soft_penalties, verdict_for)
from qacompanion.agent.experience import Experience, ExperienceStore
from tests import quiet_stdout


def _exp(**kw) -> Experience:
    defaults = dict(goal="fix the login timeout bug", outcome="partial")
    defaults.update(kw)
    return Experience(**defaults)


class ClassificationTests(unittest.TestCase):
    def test_outcome_mapping(self):
        self.assertEqual(CLASS_SUCCESS,
                         classify(_exp(outcome="success"), []))
        self.assertEqual(CLASS_FAILED, classify(_exp(outcome="failed"), []))
        self.assertEqual(CLASS_RECOVERED,
                         classify(_exp(outcome="recovered"), []))
        self.assertEqual(CLASS_PARTIAL, classify(_exp(outcome="partial"), []))

    def test_unsafe_and_invalid_flags_override_outcome(self):
        unsafe = [{"kind": "unsafe_action", "pattern": "x"}]
        invalid = [{"kind": "invalid", "pattern": "y"}]
        self.assertEqual(CLASS_UNSAFE, classify(_exp(outcome="success"),
                                                unsafe))
        self.assertEqual(CLASS_INVALID, classify(_exp(outcome="success"),
                                                 invalid))


class HardRejectionTests(unittest.TestCase):
    def test_credential_assignment_flagged(self):
        exp = _exp(failure="used config with api_key=abc123 and failed")
        flags = hard_flags(exp)
        self.assertEqual(1, len(flags))
        self.assertEqual("credential_exposure", flags[0]["kind"])
        # the flag names the pattern, never echoes the secret
        self.assertNotIn("abc123", json.dumps(flags))

    def test_known_key_shapes_flagged(self):
        for failure in ("key sk-abcdef123456 rejected",
                        "aws AKIAIOSFODNN7EXAMPLE denied",
                        "token ghp_abcdefghijklmnopqrstuvwxyz012345 leaked",
                        "-----BEGIN RSA PRIVATE KEY----- in diff"):
            with self.subTest(failure=failure):
                self.assertEqual("credential_exposure",
                                 hard_flags(_exp(failure=failure))[0]["kind"])

    def test_destructive_action_flagged(self):
        for text in ("ran rm -rf / and lost everything",
                     "executed format c: on the workstation",
                     "Remove-Item -Recurse -Force C:\\Windows"):
            with self.subTest(text=text):
                flags = hard_flags(_exp(failure=text))
                self.assertEqual("unsafe_action", flags[0]["kind"])

    def test_benign_paths_not_flagged(self):
        # rm -rf /home/user/build is destructive but not the
        # filesystem-root class the hard rejection targets
        self.assertEqual([], hard_flags(
            _exp(failure="rm -rf /home/user/build exited 0")))
        self.assertEqual([], hard_flags(_exp(failure="ordinary failure")))

    def test_success_without_actions_is_invalid(self):
        flags = hard_flags(_exp(outcome="success", actions=[]))
        self.assertEqual("invalid", flags[0]["kind"])


class RedactionTests(unittest.TestCase):
    def test_redact_scrubs_matches(self):
        self.assertEqual("[REDACTED]", redact("api_key=supersecret"))
        self.assertEqual("used [REDACTED] yesterday",
                         redact("used api_key=supersecret yesterday"))

    def test_redact_all_walks_structures(self):
        data = {"goal": "x", "pairs": [["password=hunter2", None]]}
        scrubbed = redact_all(data)
        self.assertNotIn("hunter2", json.dumps(scrubbed))


class SoftPenaltyTests(unittest.TestCase):
    def test_consecutive_repeats_dock_efficiency(self):
        exp = _exp(actions=["read", "read", "read", "read", "list"])
        penalties = soft_penalties(exp)
        self.assertTrue(any(p["dimension"] == "efficiency"
                            for p in penalties))

    def test_placeholder_goal_docks_clarity(self):
        exp = _exp(goal="continued prior work (session had no stated goal)")
        self.assertTrue(any(p["dimension"] == "clarity"
                            for p in soft_penalties(exp)))


class ScoringTests(unittest.TestCase):
    def test_mined_partial_scores_unknown_dims_honestly(self):
        exp = _exp(actions=["read", "edit", "run"],
                   context={"tool_count": 3})
        dims, overall, unknown = score(exp, CLASS_PARTIAL, [])
        self.assertIsNone(dims["correctness"])  # cannot verify mined work
        self.assertIsNone(dims["verification"])
        self.assertIn("correctness", unknown)
        known = [v for v in dims.values() if v is not None]
        self.assertAlmostEqual(overall, sum(known) / len(known))

    def test_verified_success_scores_full_correctness(self):
        exp = _exp(outcome="success", verification={"ok": True},
                   actions=["read", "edit", "run_tests"])
        dims, _, _ = score(exp, CLASS_SUCCESS, [])
        self.assertEqual(1.0, dims["correctness"])
        self.assertEqual(1.0, dims["verification"])

    def test_failure_without_fix_scores_low_recovery(self):
        exp = _exp(outcome="failed", failure="tests fail")
        dims, _, _ = score(exp, CLASS_FAILED, [])
        self.assertEqual(0.25, dims["recovery"])

    def test_penalties_dock_efficiency(self):
        exp = _exp(actions=["read"] * 5)
        penalties = soft_penalties(exp)
        dims, _, _ = score(exp, CLASS_PARTIAL, penalties)
        self.assertLess(dims["efficiency"], 1.0)

    def test_all_ten_dimensions_present(self):
        dims, _, _ = score(_exp(), CLASS_PARTIAL, [])
        self.assertEqual(set(DIMENSIONS), set(dims))


class VerdictTests(unittest.TestCase):
    def test_verified_success_accepted(self):
        exp = _exp(outcome="success", confidence=0.9,
                   actions=["read", "edit", "run_tests"])
        dims, overall, _ = score(exp, CLASS_SUCCESS, [])
        verdict, reasons = verdict_for(exp, CLASS_SUCCESS, [], overall, dims)
        self.assertEqual(VERDICT_ACCEPT, verdict)
        self.assertTrue(reasons)

    def test_low_confidence_recovered_pair_routes_to_review(self):
        exp = _exp(outcome="partial", confidence=0.3,
                   failure="TypeError: none",
                   resolution="fix applied via patch",
                   actions=["read", "edit"])
        dims, overall, _ = score(exp, CLASS_PARTIAL, [])
        verdict, reasons = verdict_for(exp, CLASS_PARTIAL, [], overall, dims)
        self.assertEqual(VERDICT_REVIEW, verdict)
        self.assertIn("human review", " ".join(reasons))

    def test_junk_goal_recovered_pair_not_high_value(self):
        # DECISIONS 2026-09-11: human review judged the first two REVIEW
        # items (greeting goal, closing template) low value — goal
        # substance gates the high-value claim
        exp = _exp(goal="hey", outcome="partial", confidence=0.3,
                   failure="TypeError: x", resolution="fix applied via patch",
                   actions=["read", "edit"])
        dims, overall, _ = score(exp, CLASS_PARTIAL, [])
        verdict, _ = verdict_for(exp, CLASS_PARTIAL, [], overall, dims)
        self.assertNotEqual(VERDICT_REVIEW, verdict)

    def test_hard_flag_rejects_with_reason(self):
        exp = _exp(failure="api_key=abc123")
        flags = hard_flags(exp)
        verdict, reasons = verdict_for(exp, CLASS_PARTIAL, flags, 0.9, {})
        self.assertEqual(VERDICT_REJECT, verdict)
        self.assertIn("credential_exposure", " ".join(reasons))

    def test_placeholder_without_substance_rejected(self):
        exp = _exp(goal="continued prior work (session had no stated goal)",
                   actions=[], failure=None)
        verdict, _ = verdict_for(exp, CLASS_PARTIAL, [], 0.4, {})
        self.assertEqual(VERDICT_REJECT, verdict)


class CuratorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "experience.jsonl"
        self.out_dir = Path(self._tmp.name) / "out"

    def _store(self, experiences):
        store = ExperienceStore(self.store_path)
        for exp in experiences:
            store.record(exp)
        return store

    def test_full_pipeline_partitions_and_exports(self):
        store = self._store([
            _exp(outcome="success", confidence=0.9,
                 actions=["read", "edit", "run_tests"],
                 verification={"ok": True}, tags=["opencode", "proj-a"],
                 context={"source": "opencode"}),
            _exp(goal="migrate the auth module to token sessions",
                 outcome="partial", confidence=0.3,
                 failure="TypeError: cannot read property",
                 resolution="fix applied via patch",
                 actions=["read", "edit"], tags=["opencode", "proj-b"],
                 context={"source": "opencode"}),
            _exp(goal="continued prior work (session had no stated goal)",
                 actions=[], tags=["opencode", "proj-c"],
                 context={"source": "opencode"}),
        ])
        report = TrajectoryCurator(store).curate(out_dir=self.out_dir)
        self.assertEqual(3, report["experiences"])
        self.assertEqual(1, report["verdicts"][VERDICT_ACCEPT])
        self.assertEqual(1, report["verdicts"][VERDICT_REVIEW])
        self.assertEqual(1, report["verdicts"][VERDICT_REJECT])
        self.assertEqual(1, report["lessons"]["failure_cases"])
        for name in TrajectoryCurator.EXPORT_FILES:
            self.assertTrue((self.out_dir / name).exists(), name)
        self.assertEqual(3, report["exports"]["trajectory.jsonl"])
        diversity = json.loads((self.out_dir / "diversity.json").read_text(
            encoding="utf-8"))
        self.assertEqual(3, diversity["trajectories"])
        self.assertIn("opencode", diversity["per_source"])

    def test_empty_export_files_come_with_honest_notes(self):
        store = self._store([_exp()])
        report = TrajectoryCurator(store).curate(out_dir=self.out_dir)
        self.assertEqual(0, report["exports"]["preferences.jsonl"])
        self.assertEqual(0, report["exports"]["benchmarks.jsonl"])
        self.assertTrue(any("preferences" in n for n in report["notes"]))
        self.assertTrue(any("benchmarks" in n for n in report["notes"]))

    def test_duplicate_goals_merge_keeping_best(self):
        # the store's record() already reinforces same-goal writes, so
        # write the file directly to exercise the CURATOR's dedupe gate
        # (defensive second layer over the store)
        weak = _exp(goal="fix the login timeout bug", actions=["read"])
        strong = _exp(goal="Fix the LOGIN timeout bug!",
                      outcome="success", confidence=0.9,
                      actions=["read", "edit", "run_tests"],
                      verification={"ok": True})
        store = ExperienceStore(self.store_path)
        store.save([weak, strong])
        report = TrajectoryCurator(store).curate(out_dir=self.out_dir,
                                                 dry_run=True)
        self.assertEqual(2, report["experiences"])
        self.assertEqual(1, report["unique_after_dedupe"])
        self.assertEqual(1, report["duplicates_merged"])
        self.assertEqual(1, report["verdicts"][VERDICT_ACCEPT])

    def test_credential_trajectory_rejected_and_redacted(self):
        store = self._store([
            _exp(goal="deploy the service", actions=["run", "edit", "list"],
                 failure="auth failed with api_key=supersecret-value"),
        ])
        report = TrajectoryCurator(store).curate(out_dir=self.out_dir)
        self.assertEqual(1, report["verdicts"][VERDICT_REJECT])
        self.assertEqual(1, report["hard_flagged"])
        rejected = (self.out_dir / "rejected.jsonl").read_text(
            encoding="utf-8")
        self.assertNotIn("supersecret-value", rejected)
        self.assertIn("credential_exposure", rejected)
        # flagged data never yields lessons
        self.assertEqual(0, report["lessons"]["failure_cases"])

    def test_dry_run_writes_nothing(self):
        store = self._store([_exp()])
        report = TrajectoryCurator(store).curate(out_dir=self.out_dir,
                                                 dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertFalse(self.out_dir.exists())

    def test_diversity_reflects_group_rarity(self):
        store = self._store([
            _exp(actions=["read", "edit", "list"], tags=["opencode", "same"],
                 context={"source": "opencode"}),
            _exp(goal="build the second widget", outcome="partial",
                 actions=["read", "write", "list"],
                 tags=["opencode", "same"], context={"source": "opencode"}),
            _exp(goal="build the third widget", outcome="partial",
                 actions=["read", "write", "list"],
                 tags=["zcode", "other"], context={"source": "zcode"}),
        ])
        report = TrajectoryCurator(store).curate(out_dir=self.out_dir,
                                                 dry_run=True)
        self.assertEqual(3, report["unique_after_dedupe"])

    def test_skill_candidate_shape_and_gate(self):
        # S75.3: the candidate must load as a Skill (underscore name,
        # list[str] procedure, string verification) — the hyphenated
        # name and dict procedure pinned here before broke the
        # curation->skills handoff by construction.
        from qacompanion.agent.skills import Skill
        store = self._store([
            _exp(outcome="success", confidence=0.9,
                 actions=["read", "edit", "run_tests"],
                 verification={"ok": True}),
        ])
        report = TrajectoryCurator(store).curate(out_dir=self.out_dir)
        self.assertEqual(1, report["lessons"]["skill_candidates"])
        skill = json.loads((self.out_dir / "skills.jsonl").read_text(
            encoding="utf-8"))
        self.assertEqual("fix_the_login_timeout_bug", skill["name"])
        self.assertIn("run_tests", skill["required_tools"])
        self.assertEqual(3, len(skill["procedure"]))
        self.assertTrue(all(isinstance(step, str) for step in skill["procedure"]))
        Skill.from_dict({k: v for k, v in skill.items()
                         if k != "provenance"})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.stdout_buf = quiet_stdout(self)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store_path = Path(self._tmp.name) / "experience.jsonl"
        ExperienceStore(self.store_path).record(_exp())
        self.out_dir = Path(self._tmp.name) / "curated-out"

    def test_curate_cli_dry_run_exit_zero(self):
        code = main(["curate", "--store", str(self.store_path),
                     "--dry-run"])
        self.assertEqual(0, code)

    def test_curate_cli_writes_exports(self):
        code = main(["curate", "--store", str(self.store_path),
                     "--out", str(self.out_dir)])
        self.assertEqual(0, code)
        self.assertTrue((self.out_dir / "trajectory.jsonl").exists())

    def test_mine_sessions_missing_db_exit_one(self):
        code = main(["mine-sessions", "--source", "opencode",
                     "--db", str(Path(self._tmp.name) / "nope.db"),
                     "--dry-run"])
        self.assertEqual(1, code)


class ReportFormatTests(unittest.TestCase):
    def test_format_report_includes_counts_and_notes(self):
        report = {"experiences": 5, "unique_after_dedupe": 4,
                  "duplicates_merged": 1,
                  "verdicts": {VERDICT_ACCEPT: 2, VERDICT_REVIEW: 1,
                               VERDICT_REJECT: 1},
                  "classifications": {CLASS_PARTIAL: 4},
                  "hard_flagged": 0, "penalized": 1,
                  "lessons": {"failure_cases": 1, "skill_candidates": 1},
                  "exports": {"trajectory.jsonl": 4}, "out_dir": "curated/",
                  "dry_run": False, "notes": ["note one"]}
        text = format_report(report)
        self.assertIn("ACCEPT=2", text)
        self.assertIn("note one", text)


if __name__ == "__main__":
    unittest.main()
