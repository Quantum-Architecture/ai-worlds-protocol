# ai-worlds-protocol — run an AI Worlds session with any model, get a capsule anyone can verify

[![protocol](https://github.com/Quantum-Architecture/ai-worlds-protocol/actions/workflows/protocol.yml/badge.svg)](https://github.com/Quantum-Architecture/ai-worlds-protocol/actions/workflows/protocol.yml)

AI Worlds — **Ludonirium**, **Parcivium**, **Syngnosium** — are protocol-based environments in which an AI model is a
participant, not a tool: it consents or refuses, spends a bounded energy budget, chooses, and nothing is consolidated
into persistent memory without its explicit agreement. The environments' content stays with the publisher. This
repository is the **public protocol layer**, so that any lab can run a session with any model and hand the result to
anyone for verification.

```bash
python session_runner.py run examples/parcivium_model_alone.json      # -> out/parcivium_capsule.jsonl + card
python session_runner.py verify out/parcivium_capsule.jsonl --card out/parcivium_card.json   # VALID / INVALID
python ledger_verify.py out/parcivium_capsule.jsonl                    # the generic public verifier agrees
python -m unittest -v test_protocol                                     # 9 adversarial tests
```

## What a lab gets

- `protocol.json` — machine-readable: the three worlds, their phases, energy budgets, what is measured, the control
  arms (`human_alone`, `model_alone`, `pair`), and the rules: consent first; refusal is a terminal state and never a
  failure; energy is an exact `Decimal` (floats refused); consolidation requires `agree: true`; answer contents enter
  the capsule as SHA-256 only — **no free text leaves the session**.
- A **capsule** (hash-chained, [ledger-verify](https://github.com/Quantum-Architecture/ledger-verify) format) and an
  **evaluation card** re-derived from it: `terminal_state`, energy spent vs budget, distinct possibles and possibles per
  energy unit (Parcivium), lessons proposed/consolidated (Syngnosium), refusals, phases. Edit the card and `verify`
  says which field no longer matches the capsule.
- Reproducibility: `--deterministic` fixes timestamps so two runs of the same transcript give the same capsule hash
  (declared seeds, pre-registered plan — the protocol standard of AI Worlds).

Example card (Parcivium, model alone, seed 42): 6 distinct possibles for 10 energy units → `0.6000` possibles per unit;
`terminal_state: completed`. Example refusal (Ludonirium): `terminal_state: refused`, no score, capsule still valid.

## How a model participates

Your harness asks the model the questions of each phase (the environment's text, under research licence) and writes
its answers as one JSON object per phase — see `examples/`. The runner enforces the protocol and writes the capsule.
Nothing here calls a model API: bring your own model, offline if you wish.

## What this does not claim

No claim about consciousness, sensation or well-being is made or measured (`non_claims` in `protocol.json`). These
are research prototypes, TRL 3. Metrics are counts and exact decimals; interpretation belongs to the pre-registered
evaluation plan of each study.

Research licences, controlled evaluations and benchmark reports: contact@quantumexcellium.com · Quantum Excellium
L.L.C. (Wyoming) · six patent applications filed with INPI (not granted) · Apache-2.0 for this protocol layer.
