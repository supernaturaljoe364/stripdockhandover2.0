# StripDock: handover

You are taking over the **software and data collection** for StripDock (Team Undampori, RSET), atomQUEST 2026, Track 2, Round 3.
**Submission deadline: 26 Nov 2026, 11:59 PM IST.** This file tells you what exists, what works, what doesn't yet, and exactly what to do next.

Read in this order: this file → `RUNBOOK.md` (operator steps) → `DECISIONS.md` (why things are the way they are) → `PROGRESS.md` (build log).
The original brief is `StripDock_R3_MASTER_PROMPT.md`. Its **rules on honesty and safety still apply** (section 1 and section 4).

---

## 0. Status at the end of 2026-11-22 (new laptop) — read this first

Done today (details: `PROGRESS.md` "Day 4", `data/labels/collection_log_20261122.md`, DECISIONS D-41 to D-46):
- Migrated to the new laptop (Python 3.11.6, `requirements.txt`, adb in `.platform-tools/`, panel on COM7, phone over USB). 93 tests pass.
- Recalibrated (ROI `a4857fd2db689a0d`, camera hash `231eb85694496d11`), dry runs, quality thresholds applied, HIL 4 and 5 **PASS**.
- Seated tolerance widened (D-44: tray 30 px, strip 40 px with strong tip match) and frozen into the model; strip_min_dE 3.0 (D-45).
- Training: series A + S0-B (8 reads); series B skipped by the team (D-46). **Model frozen 15:01** (`models/frozen/model_20261122_150113.json`).
- Blind test: B01–B13 (18 reads, sessions `20261122_1746_test`, `20261122_1842_test`, closed). Answer key revealed afterwards and
  `evaluate.py` run: spiked tap 0/4 missed; compliant 0 mg/L held 2/2 samples (false holds); conservative 3/3 held; every sample HOLD.
  Numbers with sources: `results/report_numbers.md`; full tables: `results/round3_results.md`.
- **No new strips are left.** Only D1 (dry, undipped, kept clean) remains.

Open for 23–24 Nov:
1. **Start of day:** plug in panel + phone, IP Webcam *Start server*, `.venv\Scripts\python tools\lock_camera.py`, then `--check`.
   If the phone or lid was touched, run `toolslign_phone.py` (red outlines = calibrated view; nudge until GREEN). Don't recalibrate:
   the frozen model belongs to ROI `a4857fd2db689a0d`. Air the box between wet strips (fog lowered sharpness to the blur limit today).
2. **Confirm with the chemistry person** that the blind numbers were mL of stock B in 100 mL of water (assumed in
   `data/labels/blind_preparation_20261122.csv`). If tap-water TDS can be measured, add it to `test_answer_key.csv` (`tds_ppm`) and run
   `evaluate.py --tag tds`.
3. **HIL 6 with the frozen model:** dry strip D1, `tools\hil_check.py --steps 6` (close the app first).
4. **Degraded session** (no new strips: reuse D1): purpose `degraded`, codes G01–G15 from `data/labels/collection_plan_20261122.csv`,
   then close it and run `evaluate.py` again (it reads all closed test + degraded sessions).
5. **Demo (RUNBOOK §10) needs 2 new strips.** Caution: in the blind test both 0 mg/L samples were estimated 12–13 mg/L and HELD
   (borderline band from 4.5 mg/L), so a live **PASS + CONFIRM may not happen** with this model. Don't retune it. Options: film the
   PASS → CONFIRM → button path with `tools\hil_check.py --steps 3` (a labelled panel test, verified 19 Nov), or film whatever the
   live read gives and say so. Drawer-pulled (UNKNOWN) and USB-pulled (hold survives) need no strips.
6. Report: copy only numbers that have a source in `results/report_numbers.md`; state the caveats listed there.

## 1. What StripDock is (one paragraph)

A phone (IP Webcam app) looks down into a light-tight box at a water-test strip. The PC app reads the **nitrate pad** 60 s after dipping, checks image quality, corrects the colour with the white patch, and converts colour to an estimated nitrate (mg/L NO₃⁻) using a calibration curve **trained on our own standards**. It then sends **HOLD** (≥ 25 mg/L or borderline), **PASS** or **UNKNOWN** (any doubt) over USB to an **Arduino Nano panel** (OLED, HOLD/CONFIRM LEDs, CONFIRM button). A hold is cleared only by a PASS plus a physical button press. The software **never** says water is safe.

## 2. Status on 2026-11-20 (honest)

| Area | Status |
|---|---|
| Software (app, tools, train / freeze / evaluate, tests) | **Built.** 89 unit tests pass (`.venv\Scripts\python -m pytest -q tests`). |
| Arduino panel link | **Verified on hardware.** PING keeps "Link OK"; UNKNOWN on HOLD stays HOLD; PASS → CONFIRM → button → ADAPTIVE (`results/hil_log.md`). |
| Phone link | **Verified over a USB cable** (adb port forward): 30 of 30 frames in under 0.11 s. Wi-Fi was unreliable (DECISIONS D-36). |
| Camera lock | **Verified.** Manual exposure 4.548 ms / ISO 25, daylight white balance, single-shot autofocus, torch on; colour stability ΔE00 < 0.4 (`results/camera_lock_check.json`). |
| Regions (ROI) | Calibrated for the layout of 20 Nov 11:05 (strip across the top of the view, patches below). **Will need redoing** when the box or phone moves (and they will move in transport). |
| Quality thresholds | **Still placeholders.** Dry runs are not done yet, so every read currently fails "light_leak" (expected). |
| Training data | **Pilot only:** 7 strips, one per level (10, 25, 35, 45, 55, 70, 100 mg/L), session `20261120_1120_train`. See `data/labels/collection_log_20261120.md`. |
| Model | **None trained or frozen yet.** |
| Fail-safe checks 4–6 (phone lost mid-read, drawer opened mid-read, dry strip) | **Pending.** |
| Blind tests, degraded tests, evaluation, report numbers | **Pending.** |

### What the pilot data shows (single strips, indicative only)
The nitrate pad gets pinker (CIELAB a\* rises) from **10 → 25 mg/L (Δa\* ≈ 4)**, stays **almost flat from 25 to 55** (Δa\* < 1), then rises again at **70–100**. So:
- telling ≥ 25 (HOLD) from 10 should work;
- telling 25, 35, 45 and 55 apart will be hard. Expect block-accuracy misses in that range. Report it honestly.

## 3. Hardware you are receiving

| Item | Notes |
|---|---|
| **Phone**: Samsung Galaxy S24 (SM-S921E) with **IP Webcam** | Lies screen-up on the lid, back camera over the hole. USB debugging is ON. Accept "Allow USB debugging" for your laptop (tick *Always allow*). |
| **Arduino Nano panel** (FTDI USB-serial, 115200 baud) | Runs `StripDockPanel.ino` (frozen; reference copy in `firmware/`). **Never modify or re-upload it.** The CONFIRM button is the physical push button on the panel. |
| **Dock** | Light-tight box, sliding tray. White / grey / black reference patches (paper + marker) are on the tray floor. **Glue them down permanently** (they moved several times). |
| **Strips**: eSHa AQUA QUICK TEST 7-in-1, lot 7833 | About 42 left after 20 Nov (8 used). **Count them.** Nitrate = pad 1 at the tip. Read at 60 s. Units on the bottle: mg/L NO₃⁻. |
| **Stocks** (made 20 Nov) | Stock A ≈ 9,207 mg/L NO₃⁻ (16 g Stanes Hugo 13-0-45 in 1 L). Stock B ≈ 921 mg/L (100 mL A + 900 mL distilled water). Recipes: `data/labels/STANDARDS_PREP.md`. |

## 4. Set up your laptop (Windows)

1. Install **Git**, **Python 3.11 or newer**, the **Android SDK platform-tools** (for `adb.exe`; the standalone zip from Google is enough), and the **FTDI VCP driver** if Windows doesn't recognise the panel.
2. Clone the repo, e.g. into `C:\stripdock_r3`. The scripts assume that folder; if you use another, edit `start_app.bat`.
3. Create the environment:
   ```
   cd C:\stripdock_r3
   python -m venv .venv
   .venv\Scripts\python -m pip install opencv-python numpy pyserial requests flask pyyaml pandas matplotlib pytest
   .venv\Scripts\python -m pytest -q tests
   ```
   All tests must pass (89 on 20 Nov). The tests don't need any hardware.
4. Edit **`config.yaml`**:
   - `adb_path:` → where *your* `adb.exe` is (e.g. `C:/platform-tools/adb.exe`). Also fix the path in `start_app.bat`.
   - `serial_port:` → `auto` (or your COM port from Device Manager → Ports).
   - Leave `phone_ip: 127.0.0.1` (USB link). To use Wi-Fi instead, put the IP shown in IP Webcam and empty `adb_path`. Not recommended.
5. Plug in the phone (USB, debugging allowed) and the panel. Start IP Webcam → *Start server*.
6. Check each part:
   ```
   .venv\Scripts\python tools\panel_check.py --watch 10     (expect OK <STATE> every 2 s; OLED "Link OK")
   .venv\Scripts\python tools\phone_check.py               (expect /shot.jpg latency well under 0.5 s)
   ```

## 5. What to do next, in order

**A. Make the dock repeatable (most important, about 30 min).** On 20 Nov, strips landed 10–42 px from the calibrated spot and the tray itself shifted by up to 30 px. That failed the ±15 px "seated" check on every read.
   - Glue an **L-shaped stop** (cardboard or foam) on the tray floor. The strip tip goes into the corner every time.
   - Give the tray a **hard stop**, so pushing it "fully in" always ends at the same place.
   - Glue the **patches** down flat. Better still, use a printed **50% grey** square and **matte black** card (marker ink is shiny under the torch).
   - Tape the **phone** into position.

**B. Re-lock the camera and recalibrate** (RUNBOOK §2–3): `tools\lock_camera.py --new`, recalibrate on the web page `/calibrate` (needs one empty-tray capture), then `tools\lock_camera.py --new` again and `--refresh-focus-ref`. After this, today's 7 pilot reads no longer match the ROI hash, so `train.py` will refuse them. That is by design: treat them as pilot data, and collect training data again with the repeatable dock.

**C. Optional code change, D-39 (about 30 min).** If the physical stop still can't get placement within ±15 px, implement the proposed separate strip tolerance in `app/roi.py` `locate()`: patch tolerance stays 15 px; strip tolerance 40 px if the anchor score is ≥ 0.75; search window 60 px. Add tests in `tests/test_quality.py` and record it in DECISIONS.

**D. Dry runs → thresholds** (RUNBOOK §4, 3 strips): in the app, purpose `dry`. Reads: E1 note `empty` (no strip), D1 note `dry` (new strip, undipped; keep it for E), W1 note `distilled`, T1 note `tap`. Close the session, close the app, then run `tools\suggest_thresholds.py` and, if the table looks sensible, `--apply`.

**E. Fail-safe checks** (reuse the dry strip): `tools\hil_check.py --steps 4 5 6` (close the app first). Record the dry-strip result. If it reads like 0 mg/L, the "operator must dip" limitation stays in the report.

**F. Training** (RUNBOOK §5). Levels **0, 10, 25, 35, 45, 55, 100 mg/L**. **Use at least 2 strips per level** (14 strips). With one strip per level the software can't measure strip-to-strip spread, and the UNKNOWN / borderline thresholds become guesses. Make each level in its own cup if you can. Cup recipe (250 mL distilled water + stock B): 10 → 2.7 mL, 25 → 7.0, 35 → 9.9, 45 → 12.9, 55 → 15.9, 100 → 30.5. If you only have one cup, use the ascending recipe in `data/labels/collection_log_20261120.md`. Fill in `data/labels/train_labels.csv`.
   - `tools\guided_read.py` can start reads from the command line while someone else handles strips (it uses the running app).

**G. Train and freeze:** `train.py`, read `models\model_card.md`, then `freeze_model.py`. After freezing, change nothing: no recalibration, no `lock_camera --new`, no `config.yaml` edits.

**H. Blind tests (about 22 strips) + degraded (about 6 strips + no-strip reads) + demo (3 strips).** Strip budget table: DECISIONS D-38 and the earlier plan in `data/labels/collection_plan_20261120.csv`. The chemistry person writes `test_answer_key.csv`; operators never see it. Close every session.

**I. Evaluate:** `evaluate.py` → `results\round3_results.md`. Copy the numbers into `results\report_numbers.md` with their sources. Sample sizes are below the original targets; the results file says so and gives 95% intervals. **Don't tune thresholds after seeing test results.**

**J. Film the demo** (RUNBOOK §10): HOLD on a spiked sample; PASS + CONFIRM button; drawer pulled → UNKNOWN; USB pulled and replugged → the hold survives.

## 6. Rules you must keep (from the brief)

- **Never fabricate data.** Synthetic images exist only under `tests/synthetic/` and are never used as results.
- Every number in the report must come from a script run on real captures; record the script and the inputs.
- Report misses and UNKNOWNs as they are. Don't change thresholds after seeing test results; if you fix a bug afterwards, report both versions, labelled (`evaluate.py --tag`).
- On screen and in documents: "HOLD: RO+UV", "Adaptive mode (TDS logic)", "UNKNOWN: re-test". **Never "safe".**
- Decision rules (section 4 of the brief) are frozen: HOLD at ≥ 25 mg/L block; any doubt → UNKNOWN; UNKNOWN never clears a hold.
- The Arduino sketch is frozen.

## 7. Known issues and gotchas

| Issue | What to do |
|---|---|
| "COM… is in use / Access is denied" | Close the Arduino IDE Serial Monitor. Only one program may hold the panel's port. |
| Phone unreachable | IP Webcam *Start server*; USB cable in; run `adb forward tcp:8080 tcp:8080` (the app also does this). Accept the USB-debugging prompt. |
| IP Webcam restarted → "Camera NOT locked" | `tools\lock_camera.py` (no options) re-applies the frozen settings and refocuses once. |
| Every read UNKNOWN "light_leak" | Thresholds not set yet. Do step D. |
| "strip not seated" | Placement/tray not repeatable. Do step A (and maybe C). |
| Raw ΔE00 shows exactly 0.00 between frames | Not a frozen camera. The median of a uniform patch is an integer 8-bit value and often identical between frames. Real frames differ by ~0.4 grey levels. |
| Wi-Fi drops 10–25% of frames | Use the USB link (default now). |

## 8. Map of the repo

```
HANDOVER.md  RUNBOOK.md  DECISIONS.md  PROGRESS.md  README.md   StripDock_R3_MASTER_PROMPT.md
config.yaml                     all settings + thresholds (FREEZE ones marked)
run_app.py / start_app.bat      the web app (http://localhost:5000)
train.py freeze_model.py evaluate.py close_session.py
app/        panel (serial), phone (IP Webcam), adbfwd (USB link), camlock, roi, colour, quality,
            features, model, decision, readflow, session, station, web + templates
tools/      panel_check, phone_check, lock_camera, calibrate_roi, suggest_thresholds, hil_check, guided_read
firmware/   frozen Arduino sketch (reference copy)
data/chart/        bottle photos + chart.json (blocks 0/10/25/50/100/250/500 mg/L NO3-)
data/calib/        roi.json + reference/empty-tray frames, camera_settings.json (frozen camera state)
data/sessions/     every read: frames + meta.json (raw RGB and corrected Lab per region per frame). Closed sessions are read-only + MANIFEST.sha256.
data/labels/       STANDARDS_PREP.md, collection plan + log, label templates
results/           phone/camera checks, HIL log, report_numbers.md
tests/             unit tests; tests/synthetic/ = generated test images only
docs/screenshots/  UI and ROI layout images
```

Sessions so far: `20261119_2145_dry` (empty, opened but unused), `20261120_1058_train` (1 invalid read, strip misplaced), `20261120_1120_train` (7 pilot reads, closed).
