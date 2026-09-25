"""Tests for scripts/audit_compare_at.py (run: python3 -m unittest discover -s tests -v)."""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "products_export_sample.csv"

spec = importlib.util.spec_from_file_location("audit_compare_at", ROOT / "scripts" / "audit_compare_at.py")
audit_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_mod)


class AuditTests(unittest.TestCase):
    def test_classification_active_only(self):
        findings, stats = audit_mod.audit(FIXTURE, include_inactive=False)
        verdicts = {(f["handle"], f["variant"]): f["verdict"] for f in findings}
        self.assertEqual(stats["variants"], 7)  # image-only row and draft product skipped
        self.assertEqual(stats["with_compare_at"], 5)
        self.assertEqual(verdicts[("real-sale", "")], "SALE?")
        self.assertEqual(verdicts[("bundle-value", "")], "SALE?")
        self.assertEqual(verdicts[("equal", "")], "CLEAR")
        self.assertEqual(verdicts[("lower", "")], "WRONG")
        self.assertEqual(verdicts[("multi", "1 l")], "SALE?")
        self.assertNotIn(("clean", ""), verdicts)
        self.assertNotIn(("draft-sale", ""), verdicts)
        multi = next(f for f in findings if f["handle"] == "multi")
        self.assertEqual(multi["title"], "Multi Variant")  # title carried over from the first row
        self.assertEqual([f["verdict"] for f in findings], sorted((f["verdict"] for f in findings),
                                                                  key={"SALE?": 0, "WRONG": 1, "CLEAR": 2}.get))

    def test_include_inactive(self):
        findings, stats = audit_mod.audit(FIXTURE, include_inactive=True)
        self.assertEqual(stats["variants"], 8)
        self.assertIn("draft-sale", {f["handle"] for f in findings})

    def test_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "audit.csv"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = audit_mod.main([str(FIXTURE), "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertIn("SALE?", buf.getvalue())
            with open(out, encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 5)

    def test_newer_export_header_names(self):
        findings, stats = audit_mod.audit(FIXTURE.with_name("products_export_new_headers.csv"), include_inactive=False)
        self.assertEqual(stats["variants"], 3)
        self.assertEqual({f["handle"] for f in findings}, {"real-sale", "bundle-value"})
        self.assertEqual({f["verdict"] for f in findings}, {"SALE?"})
        self.assertEqual(next(f for f in findings if f["handle"] == "bundle-value")["title"], "Bundle 6x")

    def test_rejects_non_shopify_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.csv"
            bad.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                audit_mod.audit(bad, include_inactive=False)


if __name__ == "__main__":
    unittest.main()
