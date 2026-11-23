# Data collection log, 2026-11-22

Pre-registered plan: `collection_plan_20261122.csv` (written 12:15, before any read). This log records deviations.

1. **Dry session `20261122_1218_dry` (closed, INTACT):** E1–E3 empty tray → UNKNOWN (no strip; strip dE vs empty
   0.26 / 0.74 / 0.00), black patch raw L* 21.2, glare 0, frame latency < 0.08 s. D1 dry undipped strip (12:32) →
   UNKNOWN "not seated": strip clearly detected (dE vs empty 13.6), dry pad corrected Lab (95.3, −5.1, 15.2), drift 0.0.
   **Placement measured (wide search, ±120 px):** patch row (tray) moved (3, −50) px from calibration, strip tip (2, −27) px,
   so the strip sat ~23 px off relative to the tray. The app's ±30 px search clipped the tray shift at −30.
   Both the tray and the strip need physical stops (limit ±15 px ≈ 0.6 mm).
2. **Training method changed (team decision, 12:35, distilled water limited to ~1.5 L):** two cumulative ascending series
   (container 1: S*-A, container 2: S*-B), each 100 mL distilled + stock B additions, instead of the randomised order of the
   plan. Labels = volume-corrected actual concentrations from the volumes the team reports. Limitation: concentration is
   confounded with time within each series (as on 20 Nov, D-40); two independent series partly mitigate it.
   Recipes: `PROCEDURE_20261122.md`.
3. **Dry session `20261122_1252_dry` (open):** D1 (12:52) at the new reference: all quality checks pass (seated (0,0), strip dE 13.4,
   glare 0, drift 0, black L* 21.5); UNKNOWN only because no model exists. E1–E3 (12:55–12:58) empty → UNKNOWN (no strip; dE 1.06/0.26/0.26).
   W1 (distilled): dipped ~13:33; auto-START at 13:38 was **blocked** by a transient "focus lost" camera check (a frame taken while
   the tray was still moving; `lock_camera.py --check` passed 1 min later). Read at 13:39 **late (~6 min after the dip)**, noted in
   meta.json. Only `seated` failed (strip 39 px > 25). Pad (94.4, −3.3, 16.3) ≈ dry D1 (95.5, −4.1, 14.8): dry and 0 mg/L look alike (D-30 stands).
4. **D-44** (13:45): tolerance changed to tray 30 px / strip 40 px with tip match ≥ 0.75, before any training read.
5. **T1 (tap), session `20261122_1348_dry`** (13:59, START on the operator's chat reply; the team asked to stop camera-based
   auto-START, so dip-to-START is no longer measured, est. 15–40 s): all checks pass (tray 19 px, strip 32 px, tip match ok,
   strip dE 12.9, glare 0, drift 0.47). Pad (94.9, −2.9, 15.2) ≈ distilled W1: tap water's own nitrate looks low (indicative only).
6. **Quality thresholds applied** (14:00) from sessions 20261122_1252_dry + 20261122_1348_dry (3 strip reads, 3 empty):
   `results/threshold_suggestions.md`. drift_max_dE kept at 3.0; re-check with `--with-train` before freezing.
7. **HIL 4–6 with D1** (`results/hil_log.md`, sessions 20261122_1404/1408/1410_dry, closed):
   - 4, phone USB cable pulled ~14:05 during the countdown → **PASS** (UNKNOWN, "no read frames received"; panel stayed HOLD).
     START-to-verdict ≈ 3 min because each failed frame request times out and is retried.
   - 5, drawer opened ~14:09 → **PASS** (UNKNOWN, light leak: black-patch jump 2.7 L* > 2.0). Thin margin: black level 24.9 < 27.5.
   - 6, dry strip → RECORDED: UNKNOWN only because no model exists yet; pad (95.5, −4.1, 14.8) ≈ wet 0 mg/L strips. **Repeat after freezing.**
8. **Training series A** (container 1, 100 mL distilled + cumulative stock B; volumes in `training_volumes_20261122.csv`):
   session `20261122_1411_train` (closed): S0-A ok, **S10-A failed seated (41 px > 40)** → S10-A2 ok, S25-A ok, S35-A ok.
   D-45 (strip_min_dE 7 → 3) then session `20261122_1433_train`: **S45-A failed blur** (only read frame 0 at 60 s blurred, likely a bump of
   the table) → S45-A2 ok, S55-A ok, S100-A ok. Corrected pad a*: 0 → −2.8, 10 → −1.4, 25 → +2.0, 35 → +6.0, 45 → +4.6, 55 → +3.4, 100 → +7.8.
   "done X" replies were the cumulative stock total (confirmed by the pattern 2.79, 3.95, 5.14, 6.35, 12.18).
   Two redo strips → blind test reduced 9 → 7 (demo keeps 2).
9. **Model frozen 15:01** (D-46). **After freezing, the dock was disturbed (≈15:00–17:45), a deviation:** the phone/lid moved (patch row −23 px
   sideways, view hazy: raw black L* 21 → 44, grey 33 → 55, white 79 → 84, sharpness 596 → ~280). The team wiped the lens and repositioned the
   phone; the tray was also found pulled out. Re-aligned with the new `tools/align_phone.py` (live red-outline overlay); the team stopped at
   offset (+19, +7) px, rotation ≈ 3.1°. Then: patch row found at (11, 15) px, score 0.90; raw white 79.1, grey 37.1, black 26.0 (limit 27.5).
   Autofocus settles at sharpness ≈ 270–280 in this position, so `lock_camera.py --refresh-focus-ref` was run (280.3; camera settings hash
   unchanged 231eb85694496d11). ROI, camera settings and thresholds are unchanged, so the frozen model still matches, but **the physical
   geometry differs slightly from training** (≈3° rotation, a little residual haze); blind results must be read with this caveat.
10. **Blind test session `20261122_1746_test`** (17:46–18:42, closed + INTACT). Model frozen 15:01 matched (checklist "Model frozen" green).
    START on the operator's chat reply for every read. The team said cups B01–B07 were spiked and B08 onwards clean (type known to the
    operator, values only on the chemistry person's paper until the session was locked). Reads (verdict actually sent to the panel):
    - B01: UNKNOWN (seated, strip 60 px along its length), UNKNOWN (blur 53.5), UNKNOWN (blur 45.6), then HOLD (B01_r4; strip position and
      pad colour identical to B01_r3, so most likely the same strip read ~5 min after its dip).
    - B02–B07: HOLD ×6, all checks passed.
    - B08: UNKNOWN (blur 53.8), UNKNOWN (blur 52.2; position ≈ identical, possibly the same strip), then HOLD (B08_r3, sharpness 102, black L* 20.0).
      The team asked to count a blur-failed read as valid; declined (frozen gate, no post-hoc overrides). A labelled post-hoc analysis of the
      refused reads may be added after scoring, never replacing the primary result.
    - B09, B10: HOLD, all checks passed.
    Between 17:55 and 18:33 image sharpness hovered at the frozen blur limit (54.5) after the post-freeze phone disturbance (item 9); from 18:35
    it returned to training level (≈100, black L* 20). The blind test stopped at B10 to keep 2 strips for the demo.

## 2026-11-23
11. After a reboot: USB debugging had to be re-enabled; camera lock re-applied; phone re-aligned with `align_phone.py` (offset 2/10 px,
    turn −0.46°). Session `20261123_1448_dry` (closed): D1 reads UNKNOWN (dock moved during read 1; blur 38 / 41 in reads 2–3). 20 controlled
    single-AF triggers converged at sharpness 55–57; a lens wipe (team, through the box opening) raised it to ≈ 120 but raw black rose to ≈ 39
    and white to ≈ 83.5. Model estimate for the dry strip D1 (quality failed): 15.6 mg/L, i.e. it would be a borderline HOLD, not PASS.
12. **D-47 (v2):** black_L_max 40, white_L_max 90 by team instruction; model re-frozen 15:11 (same curve).
13. **Team confirmations (2026-11-23):** the blind numbers were mL of stock B added to 100 mL of water (answer key stands as computed).
    The remaining degraded types (no_strip, drawer_open, torch_through_seam, blur, phone_moved) will not be run.
