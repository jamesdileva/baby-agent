"""Tests for qacompanion.skills.merge — teacher dedup tool.

merge --into A --from B re-points B's times_seen onto A and removes B,
with a merged-from note in A. Reduces false no-match results from
near-duplicate signatures.
"""

import json
import tempfile
import unittest
from pathlib import Path

from qacompanion import store
from qacompanion.skills.merge import MergeError, merge


def _make_case(case_id, sig="test_x::err_y", times_seen=1, **overrides):
    case = {
        "id": case_id,
        "signature": sig,
        "error_excerpt": f"excerpt {case_id}",
        "diagnosis": f"diagnosis {case_id}",
        "times_seen": times_seen,
        "last_seen": "2026-08-20T10:00:00Z",
        "confirmed_by": "agent-a",
    }
    case.update(overrides)
    return case


def _write_store(tmp, *cases):
    path = Path(tmp) / "cases.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    return path


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class MergeValidationTests(TempDirTest):
    def test_merge_same_id_rejected(self):
        path = _write_store(self.tmp, _make_case(1))
        st = store.CaseStore(path)
        with self.assertRaises(MergeError) as ctx:
            merge(st, into_id=1, from_id=1)
        self.assertIn("same", str(ctx.exception).lower())

    def test_merge_into_nonexistent_rejected(self):
        path = _write_store(self.tmp, _make_case(1))
        st = store.CaseStore(path)
        with self.assertRaises(MergeError):
            merge(st, into_id=99, from_id=1)

    def test_merge_from_nonexistent_rejected(self):
        path = _write_store(self.tmp, _make_case(1))
        st = store.CaseStore(path)
        with self.assertRaises(MergeError):
            merge(st, into_id=1, from_id=99)

    def test_merge_both_nonexistent_rejected(self):
        path = _write_store(self.tmp, _make_case(1))
        st = store.CaseStore(path)
        with self.assertRaises(MergeError):
            merge(st, into_id=99, from_id=88)


class MergePreservesCountsTests(TempDirTest):
    def test_counts_combined(self):
        a = _make_case(1, times_seen=3)
        b = _make_case(2, times_seen=5)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        result = merge(st, into_id=1, from_id=2)
        self.assertEqual(result["times_seen"], 8)

    def test_counts_from_into_when_into_larger(self):
        a = _make_case(1, times_seen=10)
        b = _make_case(2, times_seen=2)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        result = merge(st, into_id=1, from_id=2)
        self.assertEqual(result["times_seen"], 12)

    def test_counts_from_zero_edge(self):
        a = _make_case(1, times_seen=1)
        b = _make_case(2, times_seen=1)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        result = merge(st, into_id=1, from_id=2)
        self.assertEqual(result["times_seen"], 2)


class MergeRemovesSourceTests(TempDirTest):
    def test_source_removed(self):
        a = _make_case(1)
        b = _make_case(2)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        ids = [c["id"] for c in remaining]
        self.assertNotIn(2, ids)

    def test_target_preserved(self):
        a = _make_case(1)
        b = _make_case(2)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        ids = [c["id"] for c in remaining]
        self.assertIn(1, ids)

    def test_only_two_cases_one_removed(self):
        a = _make_case(1)
        b = _make_case(2)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        self.assertEqual(len(st.load()), 1)


class MergeNoteTests(TempDirTest):
    def test_merged_from_field_added(self):
        a = _make_case(1)
        b = _make_case(2)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        target = [c for c in remaining if c["id"] == 1][0]
        self.assertEqual(target["merged_from"], 2)

    def test_merged_from_not_on_source(self):
        a = _make_case(1)
        b = _make_case(2)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        self.assertFalse(any("merged_from" in c for c in remaining if c["id"] != 1))


class MergeLastSeenTests(TempDirTest):
    def test_last_seen_uses_newer(self):
        a = _make_case(1, last_seen="2026-08-01T00:00:00Z")
        b = _make_case(2, last_seen="2026-08-20T00:00:00Z")
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        target = [c for c in remaining if c["id"] == 1][0]
        self.assertEqual(target["last_seen"], "2026-08-20T00:00:00Z")

    def test_last_seen_keeps_into_when_newer(self):
        a = _make_case(1, last_seen="2026-08-25T00:00:00Z")
        b = _make_case(2, last_seen="2026-08-10T00:00:00Z")
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        target = [c for c in remaining if c["id"] == 1][0]
        self.assertEqual(target["last_seen"], "2026-08-25T00:00:00Z")


class MergeTargetKeepsIdentityTests(TempDirTest):
    def test_target_keeps_its_signature(self):
        a = _make_case(1, sig="test_a::err_a")
        b = _make_case(2, sig="test_b::err_b")
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        target = [c for c in remaining if c["id"] == 1][0]
        self.assertEqual(target["signature"], "test_a::err_a")

    def test_target_keeps_its_diagnosis(self):
        a = _make_case(1, diagnosis="root cause A")
        b = _make_case(2, diagnosis="root cause B")
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        target = [c for c in remaining if c["id"] == 1][0]
        self.assertEqual(target["diagnosis"], "root cause A")


class MergePersistenceTests(TempDirTest):
    def test_merge_persists(self):
        a = _make_case(1, times_seen=3)
        b = _make_case(2, times_seen=7)
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        reloaded = store.CaseStore(path).load()
        self.assertEqual(len(reloaded), 1)
        self.assertEqual(reloaded[0]["id"], 1)
        self.assertEqual(reloaded[0]["times_seen"], 10)
        self.assertEqual(reloaded[0]["merged_from"], 2)


class MergeThreeCasesTests(TempDirTest):
    def test_merge_middle_out(self):
        a = _make_case(1, times_seen=2)
        b = _make_case(2, times_seen=3)
        c = _make_case(3, times_seen=4)
        path = _write_store(self.tmp, a, b, c)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        self.assertEqual(len(remaining), 2)
        ids = sorted(c["id"] for c in remaining)
        self.assertEqual(ids, [1, 3])
        target = [c for c in remaining if c["id"] == 1][0]
        self.assertEqual(target["times_seen"], 5)


class MergeReportDisappearsTests(TempDirTest):
    def test_merged_case_not_in_report_top5(self):
        from qacompanion import report

        a = _make_case(1, times_seen=20, sig="test_a::err_a")
        b = _make_case(2, times_seen=15, sig="test_b::err_b")
        path = _write_store(self.tmp, a, b)
        st = store.CaseStore(path)
        merge(st, into_id=1, from_id=2)
        remaining = st.load()
        output = report.format_report(remaining)
        self.assertNotIn("test_b", output)
        self.assertIn("test_a", output)


if __name__ == "__main__":
    unittest.main()
