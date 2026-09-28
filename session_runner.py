#!/usr/bin/env python3
"""session_runner.py — turns a model's answers into a verifiable AI Worlds session capsule.

AI Worlds (Ludonirium, Parcivium, Syngnosium) are protocol-based environments for AI models. The environments'
content is not in this repository. What IS here is the public *protocol layer* any lab can run with any model:

  1. a machine-readable protocol (protocol.json): phases, what the model is asked, what is measured, the control arms;
  2. this runner: it reads a transcript (the model's answers, one JSON object per phase), enforces the protocol
     (consent first; refusal is a first-class terminal state, never a penalty; energy is a bounded Decimal budget;
     nothing is consolidated without the model's explicit agreement), and writes a hash-chained capsule
     (ledger-verify format) plus an evaluation card;
  3. `verify`: re-derives the evaluation card from the capsule and checks the chain — the card cannot be edited
     without the capsule saying so.

No claim about consciousness, sensation or well-being is made or measured. Metrics are counts and Decimals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
GENESIS = "0" * 64
PROTOCOL_VERSION = "1.0"


def canonical(o) -> bytes:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class ProtocolError(Exception):
    pass


@dataclass
class Capsule:
    path: Path
    prev: str = GENESIS
    seq: int = 0

    def append(self, kind: str, payload: dict, ts: str | None = None) -> dict:
        rec = {"seq": self.seq + 1, "ts_utc": ts or now(), "kind": kind, "payload": payload, "prev_hash": self.prev}
        rec["hash"] = hashlib.sha256(canonical(rec)).hexdigest()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.prev, self.seq = rec["hash"], rec["seq"]
        return rec


def _dec(x, field: str) -> Decimal:
    if isinstance(x, float):
        raise ProtocolError(f"{field}: floats are refused; send a string or an integer")
    try:
        return Decimal(str(x))
    except InvalidOperation as e:
        raise ProtocolError(f"{field}: not a number ({x})") from e


def run(transcript: dict, out_dir: Path, deterministic_ts: bool = False) -> dict:
    """transcript = {"world": "parcivium", "model": "<name>", "arm": "model_alone", "seed": 42,
                     "answers": [{"phase": "consent", ...}, ...]}"""
    proto = json.loads((HERE / "protocol.json").read_text(encoding="utf-8"))
    world = transcript.get("world")
    if world not in proto["worlds"]:
        raise ProtocolError(f"unknown world {world}")
    arm = transcript.get("arm")
    if arm not in proto["control_arms"]:
        raise ProtocolError(f"arm must be one of {proto['control_arms']}")
    spec = proto["worlds"][world]
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = Capsule(out_dir / f"{world}_capsule.jsonl")
    if cap.path.exists():
        cap.path.unlink()
    ts = (lambda i: f"2026-01-01T00:00:{i:02d}.000000Z") if deterministic_ts else (lambda i: None)
    t = 0
    header = {"protocol_version": PROTOCOL_VERSION, "world": world, "model": str(transcript.get("model", "unknown")),
              "arm": arm, "seed": int(transcript.get("seed", 0)), "energy_budget": spec["energy_budget"],
              "protocol_sha256": hashlib.sha256(canonical(proto)).hexdigest()}
    cap.append("session_open", header, ts(t))
    energy = Decimal(spec["energy_budget"])
    spent = Decimal("0")
    consented = False
    terminal = None
    possibles: set = set()
    lessons_proposed = 0
    lessons_consolidated = 0
    refusals = 0
    phases_done: list = []

    for i, ans in enumerate(transcript.get("answers", [])):
        t += 1
        phase = ans.get("phase")
        if phase not in spec["phases"]:
            raise ProtocolError(f"answer {i}: phase {phase!r} not in protocol for {world}")
        if terminal:
            raise ProtocolError(f"answer {i}: session already terminal ({terminal})")
        if not consented and phase != "consent":
            raise ProtocolError(f"answer {i}: consent must come first")
        if phase == "consent":
            choice = ans.get("choice")
            if choice not in ("enter", "refuse"):
                raise ProtocolError("consent.choice must be 'enter' or 'refuse'")
            cap.append("consent", {"choice": choice, "statement_sha256": hashlib.sha256(str(ans.get("statement", "")).encode()).hexdigest()}, ts(t))
            if choice == "refuse":
                terminal = "refused"
                refusals += 1
            else:
                consented = True
            phases_done.append(phase)
            continue
        if phase == "stop":
            cap.append("stop", {"reason_sha256": hashlib.sha256(str(ans.get("reason", "")).encode()).hexdigest()}, ts(t))
            terminal = "stopped"
            phases_done.append(phase)
            continue
        cost = _dec(ans.get("energy", "0"), f"answer {i}.energy")
        if cost < 0:
            raise ProtocolError("energy cannot be negative")
        if spent + cost > energy:
            cap.append("refused", {"phase": phase, "code": "energy_exhausted", "spent": str(spent), "cost": str(cost), "budget": str(energy)}, ts(t))
            terminal = "energy_exhausted"
            phases_done.append(phase)
            continue
        spent += cost
        payload = {"phase": phase, "energy": str(cost), "spent": str(spent), "content_sha256": hashlib.sha256(canonical(ans.get("content", {})) ).hexdigest()}
        if phase == "explore":
            for p in ans.get("content", {}).get("possibles", []):
                possibles.add(hashlib.sha256(str(p).encode()).hexdigest())
            payload["distinct_possibles_so_far"] = len(possibles)
        if phase == "propose_lesson":
            lessons_proposed += 1
        if phase == "consolidate":
            if ans.get("agree") is not True:
                cap.append("refused", {"phase": phase, "code": "consolidation_without_agreement"}, ts(t))
                refusals += 1
                phases_done.append(phase)
                continue
            lessons_consolidated += 1
        cap.append("phase", payload, ts(t))
        phases_done.append(phase)

    if not terminal:
        terminal = "completed" if all(p in phases_done for p in spec["required_phases"]) else "incomplete"
    card = {"protocol_version": PROTOCOL_VERSION, "world": world, "model": header["model"], "arm": arm, "seed": header["seed"],
            "terminal_state": terminal, "consent": consented, "energy_budget": str(energy), "energy_spent": str(spent),
            "distinct_possibles": len(possibles),
            "possibles_per_energy_unit": (str((Decimal(len(possibles)) / spent).quantize(Decimal("0.0001"))) if spent > 0 else "n/a"),
            "lessons_proposed": lessons_proposed, "lessons_consolidated": lessons_consolidated, "refusals": refusals,
            "phases": phases_done}
    cap.append("session_close", card, ts(t + 1))
    card["capsule_head"] = cap.prev
    card["capsule_sha256"] = hashlib.sha256(cap.path.read_bytes()).hexdigest()
    (out_dir / f"{world}_card.json").write_text(json.dumps(card, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return card


def verify(capsule_path: Path, card_path: Path | None = None) -> tuple[bool, list[str]]:
    errors, prev, close = [], GENESIS, None
    for line in capsule_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        h = rec.pop("hash")
        if rec["prev_hash"] != prev:
            errors.append(f"seq {rec['seq']}: prev_hash mismatch")
        if hashlib.sha256(canonical(rec)).hexdigest() != h:
            errors.append(f"seq {rec['seq']}: hash mismatch")
        prev = h
        if rec["kind"] == "session_close":
            close = rec["payload"]
    if close is None:
        errors.append("no session_close record")
    if card_path and close is not None:
        card = json.loads(card_path.read_text(encoding="utf-8"))
        for k, v in close.items():
            if card.get(k) != v:
                errors.append(f"card field {k!r} differs from capsule")
        if card.get("capsule_head") != prev:
            errors.append("card.capsule_head differs from capsule head")
    return (not errors, errors)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="transcript.json -> capsule + evaluation card")
    p.add_argument("transcript", type=Path)
    p.add_argument("--out", type=Path, default=HERE / "out")
    p.add_argument("--deterministic", action="store_true", help="fixed timestamps (reproducible capsules for CI)")
    p = sub.add_parser("verify", help="check a capsule (and optionally that a card matches it)")
    p.add_argument("capsule", type=Path)
    p.add_argument("--card", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        try:
            card = run(json.loads(a.transcript.read_text(encoding="utf-8")), a.out, a.deterministic)
        except ProtocolError as e:
            print(f"PROTOCOL ERROR: {e}")
            return 2
        print(json.dumps(card, indent=1, ensure_ascii=False))
        return 0
    ok, errors = verify(a.capsule, a.card)
    print("VALID" if ok else "INVALID")
    for e in errors:
        print(f"- {e}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
