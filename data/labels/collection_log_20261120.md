# Data collection log, 2026-11-20

Pre-registered plan: `collection_plan_20261120.csv` (written before any read). This log records deviations.

1. **Strip 1 (S10-3, session 20261120_1058_train) is INVALID for training.** The strip lay ~100 px from the
   calibrated position, so the nitrate-pad region measured bare tray (checks failed: seated, strip_present).
   Frames are kept. Not used.
2. **Recalibrated** at 11:05 to the layout as it was then (the strip across the top, patches below). ROI saved again.
3. **Single container, ascending series.** The team has one container. Solutions are made by cumulative additions of
   stock B (920.7 mg/L) to the same cup: start 250 mL distilled + 2.7 mL, then add 4.3 / 2.9 / 2.9 / 3.1 / 4.7 /
   9.9 mL. Actual concentrations (volume-corrected, used as labels):
   9.84 / 25.08 / 35.07 / 44.84 / 55.06 / 70.09 / 100.11 mg/L NO3-. Dip losses (~0.1 mL per strip) are ignored.
   The 0 and 5 mg/L levels and the tap / spiked-tap samples need the cup emptied and rinsed 3x first.
   **Consequence:** reads go level by level in ascending order, not in the randomised order of the plan. Time
   drift is confounded with concentration; this is stated in the report.
4. **Split unchanged:** strips -1, -2, -3 of each level are training, -4 is held out; U5/U70/TAP/SPK80 are held out.
5. **What was actually read** (session `20261120_1120_train`, closed and locked): ONE strip per level (team decision):
   S10-1 (9.84), S25-1 (25.08), S35-1 (35.07), S45-1 (44.84), S55-1 (55.06), U70-1 (70.09), S100-1 (100.11).
   Stopped before 0 mg/L; 0, 5, TAP and SPK80 are not done. Strips used today: 1 (invalid strip 1) + 7 = 8.
6. **Placement:** every read failed the strict ±15 px "seated" check, because strips and the tray landed 10–42 px from
   the calibrated spot. Visual check of the saved frames: the nitrate box was on the nitrate pad in all 7. S35-1 sat
   about 20 px high (anchor match 0.48), so its measurement must be re-checked. All frames are saved for re-measurement.
7. **First look at the data** (corrected pad CIELAB, mean of the 5 read frames at 60–66 s):

   | level (mg/L) | L* | a* | b* |
   |---|---|---|---|
   | 9.84  | 90.3 | -0.5 | 14.3 |
   | 25.08 | 88.7 |  3.6 | 14.0 |
   | 35.07 | 89.9 |  2.9 | 13.8 |
   | 44.84 | 89.0 |  3.2 | 14.2 |
   | 55.06 | 89.5 |  2.8 | 14.3 |
   | 70.09 | 88.9 |  6.0 | 14.1 |
   | 100.11| 89.2 |  6.2 | 14.7 |

   The pad turns pinker (a* rises) from 10 to 25 mg/L, stays about flat from 25 to 55, then rises again by 70–100.
   **Colour separation between 25 and 55 mg/L is small** (Δa* < 1). This matches the bottle chart (the 25 and 50 blocks
   look similar) and is the main risk for block accuracy. HOLD at ≥ 25 relies on the 10 → 25 step (Δa* ≈ 4).
   These are single strips with no replicates: indicative only, not a result.
8. The `light_leak` failures are expected: thresholds are still placeholders (raw black patch L* ~42 against the
   placeholder limit of 25). Set them with `tools/suggest_thresholds.py` once dry/empty reads exist.
