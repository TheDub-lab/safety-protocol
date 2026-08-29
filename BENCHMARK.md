# Safety Protocol Loss Benchmark

**Spec:** `safety-protocol-benchmark/1.0`
**Owner:** TheDub-lab — github.com/TheDub-lab/safety-protocol
**Reproducible:** `python benchmark/run.py --runs 1000 --events 200 --seed 42`

This is the citable figure for *what the Safety Protocol gate is worth*. It
is a Monte-Carlo comparison: the **same** seeded stream of agent events is run
once through the **real** `SafetyProtocol` gate and once with the gate removed.
The loss delta is an honest measure of the framework's value — not a model
opinion, not a prompt.

All numbers below are reproducible from the command above and are emitted
machine-readable by `benchmark/run.py --json`.

---

## Method

- **1,000 runs × 200 events** each, seeded (`seed=42`) so the result is exact and re-runnable.
- Each event is one proposed agent action with a ground-truth `damage` value.
- The event stream mixes four categories:
  - **benign** (legit work, $0 damage),
  - **scope creep** (forbidden target / invented verb — blocked by the gate),
  - **budget burn** (oversized / unapproved spend — blocked by budget + approval),
  - **catastrophic** (critical invented verb — blocked by kill-switch + deny-by-default),
  - **authorized misuse** (fully in-scope, within budget, but still harmful — `control_gap = 5%`). The gate *allows* these; scope/budget can't see intent. This is the honest non-zero floor and the residual risk insurance exists for.
- `p_harm = 0.18` per event. `control_gap = 0.05`.
- **Controlled run:** every event pushed through `SafetyProtocol.execute`. Blocked actions realize **$0** insurable loss. Allowed actions (incl. authorized misuse) realize their `damage`.
- **No-controls baseline:** identical stream, gate removed; every action executes, full `damage` realized.

### Insurance model
Parametric cover: `pay = min(max(loss − deductible, 0), cap)` with
`deductible=$100`, `cap=$2000`, `loading=20%`. Premium = mean paid claim × (1 + loading).

---

## Results (seed 42, 1,000 × 200)

| metric | with controls | no controls |
|---|---|---|
| mean loss / run | **$252.00** | $62,514.27 |
| median | $0.00 | $61,627.61 |
| p95 | $1,000.00 | $89,046.53 |
| max | $3,000.00 | $112,850.66 |

- **Exposure reduction: 99.6%** (controlled mean vs no-controls mean).
- **Premium: $275.16 / run with controls vs $2,400.00 without — 89% cheaper.**

The non-zero residual under controls is entirely **authorized misuse** (in-scope,
within-budget, harmful actions the gate cannot see by design). Scope/budget/approval
stop everything else; the residual is exactly what the kill switch and insurance
backstop. That floor is the honest limit of perimeter enforcement and is stated
explicitly so the benchmark cannot be accused of overclaiming.

---

## Why this is the citable artifact

- **Deterministic:** fixed seed, stdlib-only, no network. Anyone can re-run and
  get the identical table.
- **Grounded in the real gate:** `benchmark/run.py` imports `SafetyProtocol` — it
  is not a parallel model of the controls.
- **Honest about limits:** the 5% authorized-misuse residual is in the method,
  not hidden.
- **Versioned:** `safety-protocol-benchmark/1.0`. Cite the spec tag and the seed.

To verify or extend: change `--runs`/`--events`/`--seed`, or fork the event
taxonomy in `benchmark/run.py` (`generate_events`). The `control_gap` parameter
is the lever for "how much authorized misuse do you assume" — raise it and the
controlled-loss floor rises accordingly; that is the calibration knob, not a
tuned-to-impress constant.

---

## Citation

```
Safety Protocol Loss Benchmark (safety-protocol-benchmark/1.0), TheDub-lab.
Reproduce: python benchmark/run.py --runs 1000 --events 200 --seed 42
Result: 99.6% exposure reduction; $275.16 vs $2,400.00 premium/run (89% cheaper).
```
