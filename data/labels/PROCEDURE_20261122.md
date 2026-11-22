# StripDock: what goes where (22–24 Nov 2026)

Reference sheet for the team. Units: mg/L NO₃⁻. **Stock B = 921 mg/L** (100 mL of stock A + 900 mL distilled water;
if B was instead made by weighing 1.63 g of salt into 1 L, it is 938 mg/L and every stock volume below goes down about 2%).

Rules for every strip:
- Take one strip, **close the bottle cap at once**, hold the strip by the handle end only.
- **Dip 1 s** so the nitrate pad (the tip) is fully under, lift, **touch the long edge to a tissue** (blot), don't wipe the pads.
- Pads up, tip into the strip stop, tray **fully in** against the tray stop. The app starts the 60 s timer by itself.
- **Don't touch the dock** until the verdict shows (~70 s). Then take the strip out.
- **Never dip into stock B** (921 mg/L, far above the chart). Never pour a used solution back.
- Containers: wash with tap water, shake dry, final rinse with ~10 mL distilled water.

## 0. Before anything: make the dock repeatable (no water, no strips)
1. **Tray stop:** the tray must stop in exactly the same place every time it is pushed in.
2. **Strip stop:** an L-shaped piece of card glued on the tray floor at the strip's tip end.
3. Claude recalibrates (strip in → one picture; strip out → one picture).
4. Claude checks repeatability with the dry strip D1 (put in / take out 3 times; no new strips).

## 1. Dry runs (session `dry`), 2 new strips + D1
| Code | What goes in the tray | Water |
|---|---|---|
| E1, E2, E3 | nothing (empty tray) | none |
| D1 | the dry strip from today (keep it! reused later) | none |
| W1 | NEW strip dipped in **distilled water** (~50 mL in a clean cup) | 50 mL distilled |
| T1 | NEW strip dipped in **tap water** (~50 mL in a clean cup) | 50 mL tap |

Then Claude sets the quality thresholds. Then the fail-safe checks (HIL 4–6) with D1: no water.

## 2. Training (session `train`), 14 new strips, two containers, levels go up by adding stock B
**Container 1:** 100 mL distilled water (measure with the 100 mL container, pour into the 250 mL container).
**Container 2:** a fresh 100 mL distilled water, same steps for the -B strips.

| Step | Add stock B now (mL) | Total stock B in container (mL) | Level (mg/L) | Strip code (container 1 / 2) |
|---|---|---|---|---|
| 1 | 0 | 0 | 0 | S0-A / S0-B |
| 2 | 1.10 | 1.10 | 10 | S10-A / S10-B |
| 3 | 1.69 | 2.79 | 25 | S25-A / S25-B |
| 4 | 1.16 | 3.95 | 35 | S35-A / S35-B |
| 5 | 1.19 | 5.14 | 45 | S45-A / S45-B |
| 6 | 1.21 | 6.35 | 55 | S55-A / S55-B |
| 7 | 5.83 | 12.18 | 100 | S100-A / S100-B |

After every addition: **stir ~10 s**, then dip. **Tell Claude the volume actually added each time**; the label is computed
from the real volumes (`c = 921 × V_stock_total / (100 + V_stock_total)`).
Water: 200 mL distilled. Stock B: ~24 mL.

## 3. Blind test (session `test`), 9 new strips: CHEMISTRY PERSON ONLY
The chemistry person picks the concentrations, labels the cups **B01–B09 only**, and writes
`data/labels/test_answer_key.csv` (sample_id, true_concentration_mg_L, type, tds_ppm). Operators must not see it.
- **5 spiked tap** (type `spiked_tap`, 60–100 mg/L): 100 mL **tap water** + stock B:

  | target (mg/L added) | 60 | 70 | 80 | 90 | 100 |
  |---|---|---|---|---|---|
  | stock B (mL) | 6.97 | 8.23 | 9.51 | 10.83 | 12.18 |

  Record the tap water's TDS (ppm) if a TDS meter is available. Note: tap water's own nitrate adds to this
  (T1 gives a rough idea); the answer key records the **added** concentration and the report says so.
- **4 compliant** (type `compliant`, 0–10 mg/L): 100 mL **distilled water** + stock B: 0 mg/L → 0 mL, 5 → 0.55 mL, 10 → 1.10 mL.

Water: ~400 mL distilled + ~500 mL tap. Stock B: ~50 mL.

## 4. Degraded reads (session `degraded`): no new strips, no water
Reuse D1 and used strips. Order and types: `data/labels/collection_plan_20261122.csv` (G01–G15).

## 5. Demo for filming (session `demo`), 2 new strips
- DEMO-1: 100 mL **tap** + 9.51 mL stock B (80 mg/L) → expected HOLD.
- DEMO-2: 100 mL **distilled** (0 mg/L) → expected PASS, then press CONFIRM on the panel.

## Totals
| | Distilled | Tap | Stock B | New strips |
|---|---|---|---|---|
| Dry runs | 50 mL | 50 mL | 0 | 2 (W1, T1) + D1 = 3 |
| Training | 200 mL | 0 | ~24 mL | 14 |
| Blind | ~400 mL | ~500 mL | ~50 mL | 9 |
| Demo | 100 mL | 100 mL | ~10 mL | 2 |
| Rinses | ~150 mL | as needed | 0 | 0 |
| **Total** | **~900 mL** | | **~85 mL of 1 L** | **28** |
