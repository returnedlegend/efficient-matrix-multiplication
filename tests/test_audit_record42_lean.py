"""Bounded evidence preservation and proof-audit controls; no Lean subprocesses."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_record42_lean.py"
SPEC = importlib.util.spec_from_file_location("audit42", SCRIPT)
A = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(A)


class AuditRecord42Tests(unittest.TestCase):
    def test_nested_comments_removed_before_source_audit(self):
        self.assertEqual(A.stripped_lean('/- sorry /- axiom -/ -/\ndef x := 1 -- admit\n'), '\ndef x := 1 \n')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Control.lean"
            path.write_text('/- sorry and axiom are comments -/\ndef x := 1\n')
            self.assertTrue(A.source_audit(path)["no_sorry_or_custom_axioms"])
            for token in ("sorry", "sorryAx", "admit", "axiom", "constant", "unsafe"):
                path.write_text("def x := " + token + "\n")
                with self.assertRaises(ValueError):
                    A.source_audit(path)

    def test_axiom_output_required_and_unapproved_axioms_rejected(self):
        good = ("'ExplicitCertificate.coefficient_certificate' depends on axioms: [propext, Lean.ofReduceBool]\n"
                "'ExplicitCertificate.multiplication_correct' depends on axioms: [propext, Lean.ofReduceBool, Quot.sound]\n")
        self.assertIn("Lean.ofReduceBool", A.check_axioms(good)["coefficient_certificate"])
        for bad in ("", good.replace("Quot.sound", "sorryAx"), good.replace("Quot.sound", "customAssumption")):
            with self.assertRaises(ValueError):
                A.check_axioms(bad)

    def run_audit(self, source, root, *extra):
        result = subprocess.run([sys.executable, str(SCRIPT), str(source), "--audit-root", str(root), *extra],
                                cwd=ROOT, capture_output=True, text=True, timeout=5)
        output = json.loads(result.stdout)
        audit = Path(output["audit_directory"])
        return result, audit, json.loads((audit / "audit-report.json").read_text())

    def test_invalid_input_preserved_before_rejection_without_lean(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invalid.json"
            raw = b'{"dimension":5,"dimension":5,"field":2,"terms":[]}'
            source.write_bytes(raw)
            result, audit, report = self.run_audit(source, root / "audits")
            self.assertEqual(result.returncode, 1)
            self.assertEqual((audit / "candidate.raw.json").read_bytes(), raw)
            self.assertEqual((audit / "candidate.raw.json").stat().st_mode & 0o222, 0)
            self.assertEqual(report["steps"], [])
            self.assertFalse(report["valid_explicit_lean_proof"])
            hashes = json.loads((audit / "all-checksums.json").read_text())
            self.assertEqual(hashes["candidate.raw.json"], A.sha(raw))
            self.assertTrue((audit / "candidate.raw.sha256").is_file())

    def test_published93_cannot_reach_record_compile(self):
        with tempfile.TemporaryDirectory() as directory:
            result, audit, report = self.run_audit(ROOT / "artifacts/km93_f2.json", Path(directory))
            self.assertEqual(result.returncode, 1)
            self.assertTrue(report["independent_verification"]["valid"])
            self.assertEqual(report["steps"], [])
            self.assertIn("R<=92", report["errors"][0])
            self.assertFalse((audit / "ExplicitCandidate.lean").exists())

    def test_exclusive_preservation_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence"
            A.preserve(path, b"first")
            with self.assertRaises(FileExistsError):
                A.preserve(path, b"second")
            self.assertEqual(path.read_bytes(), b"first")


if __name__ == "__main__":
    unittest.main()
