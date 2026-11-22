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
