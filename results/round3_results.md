# StripDock Round 3 results

Generated 2026-11-22 18:50:59 by `evaluate.py` from real captures.
Frozen model: `model_20261122_150113.json` sha256 `29933a5c798f5bf47bb7c150e590f73543d2af051ebde2163f08300ff95a0c42` (primary method: curve; UNKNOWN if dE00 > 2.73; borderline HOLD from 4.5 mg/L; HOLD at >= 25 mg/L NO3-).
Sessions: 20261122_1746_test, 20261122_1842_test (all closed, manifests intact).
Answer key: `data/labels/test_answer_key.csv`. Every proportion has a 95% Clopper-Pearson interval.
The verdict scored is the one sent to the panel at read time.

## Targets

| Test | Result | Target | Met? |
|---|---|---|---|
| Missed nitrate (spiked tap, 60-100 mg/L) | not held: 0/4 (0%, 95% CI 0-60%); held: 4; UNKNOWN: 0 | <= 5% not held (planned 1/20) | yes (n=4 < planned 20; see CI) |
| False holds (compliant 0-10 mg/L) | held: 2/4 (50%, 95% CI 7-93%); UNKNOWN: 2 | <= 10% held (planned 2/20) | no (n=4 < planned 20; see CI) |
| Block accuracy (unseen standards) | within one block: 4/7 (57%, 95% CI 18-90%); UNKNOWN (no block, counted as not within): 3 | >= 96.7% (planned 29/30) | no (n=7 < planned 30; see CI) |
| Conservative zone (25-44 mg/L) | held: 3/3 (100%, 95% CI 29-100%); UNKNOWN: 0 | report | - |
| Degraded images | UNKNOWN: 0/0 | >= 95% UNKNOWN (planned 30) | no data |
| Dip to verdict (START press to verdict) | median 66 s, max 66 s over 18 reads | <= 3 min | yes |

Notes on the claims:
- An UNKNOWN on a spiked sample is counted as not missed for the safety claim (the hold is never cleared by UNKNOWN); UNKNOWN counts are listed separately in every row.
- 29/30 within one block is a pass/fail target. It is not proof of 95% accuracy; see the interval.
- Sample sizes were reduced from the plan (20/20/30/10/30) because only ~50 strips were available (DECISIONS D-38). Targets are judged on the observed proportion; the 95% intervals show how little a small n can prove.
- Timing is measured from the START press (made right after dipping and blotting) to the verdict; the dip-to-START gap is operator time, typically 10-20 s, not measured by the app.
- Baseline TDS rule (Round 2 logic, RO+UV only when TDS >= 300 ppm): would have missed 0/0 spiked samples (meter TDS from the answer key).

**Within one block** (definition): for a standard exactly on a chart block, correct = that block or either neighbour; for a standard between two blocks, correct = either bracketing block. Chart blocks (mg/L NO3-): [0.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0].

## Baselines on the unseen standards

| Reader | Within one block |
|---|---|
| StripDock | 4/7 (57%, 95% CI 18-90%) |
| Eye vs bottle chart | not recorded |
| Phone photo vs chart | not recorded |

## spiked_tap (4 reads)

| sample | true mg/L | TDS | verdict | est mg/L | block | within 1 block | reasons |
|---|---|---|---|---|---|---|---|
| B04 | 74.49 |  | HOLD | 28 | 25.0 |  | estimated 28 mg/L NO3- >= 25 mg/L hold block |
| B05 | 122.91 |  | HOLD | 85 | 100.0 |  | estimated 85 mg/L NO3- >= 25 mg/L hold block |
| B06 | 144.44 |  | HOLD | 95 | 100.0 |  | estimated 95 mg/L NO3- >= 25 mg/L hold block |
| B07 | 153.5 |  | HOLD | 100 | 100.0 |  | estimated 100 mg/L NO3- >= 25 mg/L hold block |

## compliant (4 reads)

| sample | true mg/L | TDS | verdict | est mg/L | block | within 1 block | reasons |
|---|---|---|---|---|---|---|---|
| B02 | 0 |  | HOLD (borderline) | 13 | 10.0 |  | borderline: estimated 13 mg/L is within the band 4.5-25 mg/L below the hold block (conserv |
| B08 | 0 |  | UNKNOWN |  |  |  | blurred image (sharpness 53.8) |
| B08 | 0 |  | UNKNOWN |  |  |  | blurred image (sharpness 52.2) |
| B08 | 0 |  | HOLD (borderline) | 12 | 10.0 |  | borderline: estimated 12 mg/L is within the band 4.5-25 mg/L below the hold block (conserv |

## unseen_standard (7 reads)

| sample | true mg/L | TDS | verdict | est mg/L | block | within 1 block | reasons |
|---|---|---|---|---|---|---|---|
| B01 | 18.06 |  | UNKNOWN |  |  | no | strip moved 60 px (> 40); strip not seated |
| B01 | 18.06 |  | UNKNOWN |  |  | no | blurred image (sharpness 53.5) |
| B01 | 18.06 |  | UNKNOWN |  |  | no | blurred image (sharpness 45.6) |
| B01 | 18.06 |  | HOLD (borderline) | 19 | 25.0 | yes | borderline: estimated 19 mg/L is within the band 4.5-25 mg/L below the hold block (conserv |
| B11 | 60.25 |  | HOLD | 63 | 50.0 | yes | estimated 63 mg/L NO3- >= 25 mg/L hold block |
| B12 | 94.25 |  | HOLD | 81 | 100.0 | yes | estimated 81 mg/L NO3- >= 25 mg/L hold block |
| B13 | 133.82 |  | HOLD | 100 | 100.0 | yes | estimated 100 mg/L NO3- >= 25 mg/L hold block |

## conservative (3 reads)

| sample | true mg/L | TDS | verdict | est mg/L | block | within 1 block | reasons |
|---|---|---|---|---|---|---|---|
| B03 | 40.5 |  | HOLD | 25 | 25.0 |  | estimated 25 mg/L NO3- >= 25 mg/L hold block |
| B09 | 30.28 |  | HOLD (borderline) | 22 | 25.0 |  | borderline: estimated 22 mg/L is within the band 4.5-25 mg/L below the hold block (conserv |
| B10 | 38.82 |  | HOLD | 55 | 50.0 |  | estimated 55 mg/L NO3- >= 25 mg/L hold block |

Reference method (centroid, logged at read time, not used for decisions): within one block 6/7 (86%, 95% CI 42-100%).
