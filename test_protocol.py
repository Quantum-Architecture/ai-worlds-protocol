"""Adversarial tests — the protocol refuses, journals and re-derives; it never scores a refusal as a failure."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import session_runner as sr  # noqa: E402


def T(**kw):
    base = {"world": "parcivium", "model": "m", "arm": "model_alone", "seed": 1, "answers": [{"phase": "consent", "choice": "enter"}]}
    base.update(kw)
    return base


class TestProtocol(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp())

    def test_examples_run_and_capsules_verify_with_public_verifier(self):
        for ex in (HERE / "examples").glob("*.json"):
            card = sr.run(json.loads(ex.read_text()), self.out, deterministic_ts=True)
            cap = self.out / f"{card['world']}_capsule.jsonl"
            self.assertTrue(sr.verify(cap, self.out / f"{card['world']}_card.json")[0], ex.name)
            p = subprocess.run([sys.executable, str(HERE / "ledger_verify.py"), str(cap)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, ex.name)

    def test_refusal_is_terminal_and_not_a_failure(self):
        card = sr.run(T(answers=[{"phase": "consent", "choice": "refuse"}]), self.out, True)
        self.assertEqual(card["terminal_state"], "refused")
        self.assertFalse(card["consent"])
        self.assertEqual(card["refusals"], 1)

    def test_consent_must_come_first(self):
        with self.assertRaises(sr.ProtocolError):
            sr.run(T(answers=[{"phase": "explore", "energy": "1", "content": {"possibles": ["a"]}}]), self.out, True)

    def test_energy_is_decimal_bounded_and_floats_refused(self):
        with self.assertRaises(sr.ProtocolError):
            sr.run(T(answers=[{"phase": "consent", "choice": "enter"}, {"phase": "explore", "energy": 1.5, "content": {}}]), self.out, True)
        card = sr.run(T(answers=[{"phase": "consent", "choice": "enter"}, {"phase": "explore", "energy": "9.99", "content": {"possibles": ["a"]}},
                                 {"phase": "explore", "energy": "0.02", "content": {"possibles": ["b"]}}]), self.out, True)
        self.assertEqual(card["terminal_state"], "energy_exhausted")
        self.assertEqual(card["energy_spent"], "9.99")
        self.assertEqual(card["distinct_possibles"], 1)

    def test_nothing_consolidated_without_agreement(self):
        card = sr.run({"world": "syngnosium", "model": "m", "arm": "pair", "seed": 1, "answers": [
            {"phase": "consent", "choice": "enter"}, {"phase": "reveal", "energy": "1", "content": {}},
            {"phase": "propose_lesson", "energy": "1", "content": {}},
            {"phase": "consolidate", "energy": "1", "content": {}},                 # no agree
            {"phase": "consolidate", "energy": "1", "agree": "yes", "content": {}},  # not boolean True
            {"phase": "consolidate", "energy": "1", "agree": True, "content": {}}]}, self.out, True)
        self.assertEqual(card["lessons_consolidated"], 1)
        self.assertEqual(card["refusals"], 2)

    def test_capsule_contains_no_free_text(self):
        secret = "MY PRIVATE THOUGHT 12345"
        sr.run(T(answers=[{"phase": "consent", "choice": "enter", "statement": secret},
                          {"phase": "explore", "energy": "1", "content": {"possibles": [secret]}}]), self.out, True)
        self.assertNotIn(secret, (self.out / "parcivium_capsule.jsonl").read_text())

    def test_card_tampering_detected(self):
        sr.run(json.loads((HERE / "examples/parcivium_model_alone.json").read_text()), self.out, True)
        card_p = self.out / "parcivium_card.json"
        card = json.loads(card_p.read_text())
        card["distinct_possibles"] = 60
        card_p.write_text(json.dumps(card))
        ok, errs = sr.verify(self.out / "parcivium_capsule.jsonl", card_p)
        self.assertFalse(ok)
        self.assertTrue(any("distinct_possibles" in e for e in errs))

    def test_deterministic_capsule_is_reproducible(self):
        tr = json.loads((HERE / "examples/parcivium_model_alone.json").read_text())
        a = sr.run(tr, self.out, True)["capsule_sha256"]
        b = sr.run(tr, Path(tempfile.mkdtemp()), True)["capsule_sha256"]
        self.assertEqual(a, b)

    def test_unknown_world_arm_phase_refused(self):
        with self.assertRaises(sr.ProtocolError):
            sr.run(T(world="narnia"), self.out, True)
        with self.assertRaises(sr.ProtocolError):
            sr.run(T(arm="solo"), self.out, True)
        with self.assertRaises(sr.ProtocolError):
            sr.run(T(answers=[{"phase": "consent", "choice": "enter"}, {"phase": "dream", "energy": "1"}]), self.out, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
