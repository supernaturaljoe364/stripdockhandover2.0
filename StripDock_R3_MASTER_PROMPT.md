# StripDock Round 3: master prompt for Claude Code

You are building the software half of **StripDock**, Team Undampori's (RSET) entry in **atomQUEST 2026, Track 2 (water purifiers), Round 3**. The hardware is built. Your job is the Windows PC software that captures a test-strip photo from a phone, reads the nitrate pad against a dataset we will collect ourselves, decides HOLD / PASS / UNKNOWN, and drives the Arduino panel. You also build the tooling to collect, train and evaluate that dataset, and a runbook so four non-expert students can operate it.

**Deadline context:** submission closes **26 Nov 2026, 11:59 PM IST**. Today is 19 Nov evening. Training runs ~21 Nov, scored tests 22–23 Nov, filming 24 Nov. The software must be usable by tomorrow evening.

Work through the phases in order. After each phase, append a short entry to `PROGRESS.md` (what was built, what was verified, how, what is still open). Never claim something works unless you ran it.

---

## 1. Ground rules (read twice)

**Scope and safety (you have unrestricted permissions, so these are hard rules):**
- Work only inside the project folder `C:\stripdock_r3\` (create it). If a `D:\atomquest round-2\work` folder exists, you may **read** it and copy useful pieces in; never modify or delete it.
- Do not delete, move or modify anything outside the project folder. No system settings, registry, drivers, firewall or antivirus changes. Installing Python packages into a project venv, and Python itself via winget if missing, is allowed.
- No git pushes, no uploads, no accounts, no network calls except to the phone on the local network and to package registries.
- **Do not modify or re-upload the Arduino sketch.** It is `StripDockPanel.ino`, it passed all its safety tests on hardware, and its behaviour is frozen. If you believe a firmware change is needed, write the proposal in `PROGRESS.md` and stop to ask.
- Do not change the phone's camera settings except through the documented IP Webcam HTTP interface, and only the settings listed in Phase 2.

**Honesty (the report is checked against the video by the judges):**
- Never fabricate data. Synthetic or simulated images are allowed **only** for software tests, must live under `tests/synthetic/`, and must never be mixed into `data/` or reported as results.
- Every number in any results file must come from a script you ran on real captures, and the script and inputs must be recorded.
- Report results as they are, including misses. Don't tune thresholds on the scored test set.
- The software must never display or print "safe to drink" or equivalent wording. StripDock is indicative screening.

**Ask me (stop and wait) only for:** the phone's IP address, the strip bottle chart photo, the strip's read time and nitrate units, and anything that would change the safety rules in section 4. Otherwise make a sensible choice, record it in `DECISIONS.md`, and keep going.

---

## 2. The system as built (facts; don't re-derive them)

| Part | What it is | How it connects |
|---|---|---|
| Camera | Android phone running **IP Webcam** (Pavel Khlebovich), lying screen-up on the dock lid, back camera looking down through a hole | Wi-Fi (same hotspot/LAN as the PC). HTTP at `http://<PHONE_IP>:8080` |
| Dock | Black foam-board light-tight box; sliding tray with an end-stop holds the strip; white, grey and black matte reference patches beside the nitrate pad; hole(s) in the lid for the phone camera (and the flash, see lighting) | Physical only |
| Lighting | **Either** 4 white LEDs inside the dock on their own 5 V supply (not computer-controlled), **or** the phone's torch through the flash hole. Support both via config `lighting_mode: dock_leds \| phone_torch`. Default `dock_leds` | dock_leds: nothing to control. phone_torch: IP Webcam torch endpoints |
| Panel | **Arduino Nano** (ATmega328P, clone) running `StripDockPanel.ino`: 0.96" SSD1306 OLED, red HOLD LED, green CONFIRM LED, CONFIRM push button. Owns the hold state in EEPROM | USB serial, **COM8** on this PC (auto-detect if it changes), **115200 baud** |
| PC | Windows 11, this machine. Runs your app | — |

There is **no ESP32** in the build anymore. The Round 2 design used an ESP32-CAM. Ignore its firmware, but its pipeline ideas and tests may be reusable.

**How the parts relate:** the phone never connects to the breadboard. The PC is the bridge: phone → (Wi-Fi) → PC app → (USB serial) → Arduino → OLED/LEDs/button.

---

## 3. Arduino protocol (exact; the sketch is already running)

- Serial 115200, newline-terminated ASCII commands: `HOLD`, `PASS`, `UNKNOWN`, `PING`, `STATUS` (case-insensitive).
- Every command gets the reply `OK <STATE>` where STATE is `ADAPTIVE`, `HOLD` or `CONFIRM_WAIT`. Unknown commands get `ERR unknown command: <text>`.
- On boot it prints `READY <STATE>`. **Opening the serial port resets the Nano** (DTR), so after opening: wait up to 3 s for `READY`, then send `STATUS`.
- Asynchronous events: `EVT CLEARED` (button pressed during CONFIRM_WAIT → ADAPTIVE), `EVT CONFIRM_TIMEOUT` (60 s passed → back to HOLD), `EVT BUTTON_IGNORED`.
- Behaviour: `HOLD` latches the hold into EEPROM. `PASS` while held → CONFIRM_WAIT (green LED). Only a physical button press within 60 s clears it. `PASS` while ADAPTIVE stays ADAPTIVE. `UNKNOWN` never clears a hold and cancels a pending CONFIRM_WAIT. With no command for 10 s, the OLED shows LINK LOST (hold unchanged). The PC must send `PING` every 2 s while running.
- The Arduino is the single source of truth for the hold. The PC app mirrors it (from replies and EVT lines) and never assumes.

---

## 4. Decision rules (frozen; don't change without asking)

1. Read the nitrate pad at the strip's read time (from the bottle; expected ~60 s), measured by the app's timer from the moment the operator presses START after dipping. Never earlier.
2. If any quality check fails, or the phone is unreachable, or the classifier is not confident → send `UNKNOWN`.
3. If the estimated nitrate is at or above the chart's **25 mg/L block** → send `HOLD`. (BIS limit is 45 mg/L. 45 falls between the 25 and 50 blocks, and strips can read low, so 25 is the deliberate conservative trigger.)
4. Otherwise → send `PASS`.
5. UNKNOWN never clears a hold (the Arduino enforces this too). Clearing needs a PASS plus the physical button.
6. Never say water is safe.

Units: strips may be charted as nitrate (NO₃⁻) or nitrate-nitrogen (NO₃-N). 45 mg/L NO₃⁻ = 10.2 mg/L NO₃-N (×0.2259). Work internally in **mg/L NO₃⁻**, and convert chart values if the bottle says NO₃-N. Ask me to confirm the units from the bottle photo.

---

## 5. Project layout

```
C:\stripdock_r3\
  config.yaml            # phone_ip, serial_port (or auto), lighting_mode, read_time_s, chart blocks, thresholds
  app\                   # the Python package
  data\
    chart\               # bottle chart photo(s) + chart.json (blocks, units, read time, pad order)
    calib\roi.json       # pad + patch regions, made by the calibration tool
    sessions\<YYYYMMDD_HHMM>_<purpose>\   # purpose = train | test | degraded | demo | dry
       <sample_id>\frames\*.jpg, meta.json
    labels\train_labels.csv, test_answer_key.csv (written by the chemistry person, see section 8)
  models\                # frozen model files with a hash and freeze date
  results\               # evaluation outputs, tables, figures, logs
  tests\                 # unit tests; tests\synthetic\ for generated test images only
  RUNBOOK.md  PROGRESS.md  DECISIONS.md  README.md
```

Use a Python 3.11+ venv at `C:\stripdock_r3\.venv`. Allowed packages: opencv-python, numpy, pyserial, requests, flask (or fastapi + uvicorn), pyyaml, pandas, matplotlib, pytest, scikit-image (for CIEDE2000) or your own ΔE00 implementation. Prefer simple, transparent methods over deep learning: we will only have ~21 training strips.

---

## 6. Phases

### Phase 0: environment audit (15 min)
- Record OS, Python, free disk, and available COM ports (show their descriptions; the Nano shows as "USB Serial Port" or "USB-SERIAL CH340").
- Create the venv and install packages. Log everything to `PROGRESS.md`.
- Search for `D:\atomquest round-2\work`. If it exists, list what's reusable (chart definitions, colour-separability simulation, safety tests, quality-gate code) and copy only what you will use, noting the source.

### Phase 1: connectivity (30 min)
- **Arduino:** auto-detect the port (prefer config `serial_port`, else the single CH340/USB-serial port), open it, wait for READY, send STATUS, then PING every 2 s from a background thread. Parse every line, and keep a thread-safe `panel_state` plus an event log. Only one program can hold the port: if opening fails with "Access is denied", tell me to close the Arduino IDE's Serial Monitor (and any other serial tool), then retry. Write `tools\panel_check.py`, which prints state and lets me send each command interactively. Verify on hardware: OLED goes from LINK LOST to Link OK while pinging.
- **Phone:** ask me for `PHONE_IP` if `config.yaml` lacks it. Fetch `/status.json?show_avail=1` (or the equivalent your probing finds) and save the response to `results\ipwebcam_status.json`. Determine which still endpoints exist (`/shot.jpg` = current video frame, `/photo.jpg` = camera still, `/photoaf.jpg` = still with autofocus; **never use autofocus at read time**). Write `tools\phone_check.py`: grab 10 frames from each available endpoint, report resolution, latency and colour stability (mean ΔE00 of a fixed central patch across the 10 frames), then pick the endpoint with stable colour and acceptable latency. Record the choice in `DECISIONS.md`.

### Phase 2: camera locking (30 min)
- From the status JSON, find which settings exist on this phone: focus mode, focus lock, exposure lock, white-balance lock, white-balance mode, torch, resolution, quality, night vision or HDR.
- Write `tools\lock_camera.py` that, **only for settings the phone actually reports**, sets: resolution to 1920×1080 (or the closest), JPEG quality high, night vision or HDR off, flash off for stills. If `lighting_mode: phone_torch`, turn the torch on and keep it on for the whole session (constant light, never flash per shot). After a 3 s settle, lock focus, exposure and white balance. Then verify by grabbing 10 frames and checking ΔE00 stability < 1.0 on the white patch.
- If a setting can't be controlled over HTTP on this phone, print clear manual instructions ("in IP Webcam → Video preferences → … turn on Exposure lock") and add them to RUNBOOK.md.
- `lock_camera.py --check` must report whether the current state matches the frozen session settings saved in `data\calib\camera_settings.json`. Training and testing must both refuse to start if the check fails.

### Phase 3: region calibration (45 min)
- `tools\calibrate_roi.py` (or a page in the web UI): grab a frame with a strip in the tray, show it, and let me click/drag rectangles for: **nitrate pad**, **white patch**, **grey patch**, **black patch**, plus optionally the nitrite pad and a **strip-edge anchor**. Save to `data\calib\roi.json` with the reference frame.
- At read time, re-locate regions with small-shift tolerance (template-match the anchor or the patch row within ±15 px), and shrink each region by 20% from its edges before sampling, to avoid borders and edge bleed.
- If re-location fails or moves more than the tolerance → quality failure (UNKNOWN), with the reason "strip not seated".

### Phase 4: quality gate (1 h)
Each check returns pass/fail plus a measured value. The thresholds live in config. Set initial values from dry/blank captures, then **freeze them before scored tests**:
- **Light leak:** black patch mean L* above threshold, or a frame-to-frame jump in black-patch L* (drawer opened or torch shone in) → fail.
- **Exposure:** white patch L* inside a range, and fewer than 1% clipped pixels in the white patch.
- **Glare:** fraction of near-saturated, low-chroma pixels inside the pad region above threshold → fail. This matters especially for `phone_torch`, because on-axis light reflects off the wet pad.
- **Blur:** variance of the Laplacian on the pad plus patch region below threshold.
- **Timing:** read before `read_time_s` → fail. Also sample 5 frames across read_time ± 3 s; pad colour drift > threshold ΔE00 → fail ("still developing").
- **Strip present:** pad region differs from the empty-tray reference by more than a threshold.
- **Phone reachable / frame fresh:** HTTP errors, timeouts, or a frame older than 2 s → fail.
- Unit-test every check with synthetic images under `tests\synthetic\`.

### Phase 5: colour correction and features (45 min)
- Convert to linear RGB, then white-balance using the white patch and the grey patch: a per-channel gain from white, checked against grey. Fit a simple per-channel linear correction from three points (black, grey, white) when that is stable. Then convert to CIELAB (D65).
- Features per capture: pad L*, a*, b* (median over the shrunken ROI, averaged over the 5 read-time frames), pad hue angle and chroma, plus the same for the nitrite pad if present (logged only, not used for the decision).
- Log the raw RGB and the corrected Lab for every region of every frame to the sample's `meta.json`.

### Phase 6: classifier and unknown rejection (1 h)
- Training data: our own nitrate standards at **0, 10, 25, 35, 45, 55, 100 mg/L**, 3 strips each (≈21 strips), plus whatever else we add.
- Model: treat the pad colours as a 1-D calibration curve. Fit a smooth monotonic curve through the per-standard mean Lab points (for example, principal-curve or ordered-polyline interpolation in Lab), and map a new capture to an **estimated concentration** by nearest point on the curve (log-concentration interpolation between neighbours). Also report the **nearest chart block** (chart blocks from `chart.json`, expected 0/10/25/50/100/250).
- **Unknown rejection:** if the capture's distance from the curve exceeds a threshold (ΔE00, set from training spread, for example the 99th percentile of training residuals × 1.5) → UNKNOWN ("colour not on calibration curve").
- A borderline band around the 25-block decision boundary, set from training spread, also returns HOLD (conservative), not PASS. Document the exact numbers in `DECISIONS.md` and `models\model_card.md`.
- Also implement a second, simpler reference method (nearest-centroid in Lab with the same rejection rule), and report both in evaluation. Pick the primary by **leave-one-strip-out cross-validation on training data only**.
- `train.py` refuses to run unless `lock_camera.py --check` passes and the training session's settings match. Output: a model file + hash + freeze timestamp. `freeze_model.py` copies the model to `models\frozen\` and makes it read-only. Evaluation scripts load only frozen models.
- Before training data exists, test the whole training path on clearly-marked synthetic data in `tests\synthetic\`.

### Phase 7: the read flow and the app (2 h)
A local web app at `http://localhost:5000` (Flask is fine), designed for a phone-filmed demo: big, readable, no clutter.
- **Live page:** live phone preview (MJPEG from IP Webcam, or 2 fps stills), ROI overlay, panel state mirrored big (HOLD in red / CONFIRM? in green / ADAPTIVE), link status for phone and Arduino, last verdict with reason.
- **Read flow:** the operator types or scans a sample code, dips the strip per the bottle, blots the edge, slides the tray in and presses **START**. A countdown to read_time runs. The app captures frames, runs the quality gate → features → model → decision, then sends HOLD/PASS/UNKNOWN to the Arduino and shows the verdict, estimated block and reasons. It saves everything to the session folder. Total dip-to-verdict time is logged.
- **Modes:** `train` (operator enters the known concentration), `test` (operator enters only the blind sample code; nothing about the true value is shown), `degraded` (operator records which degradation was done: drawer open, torch through seam, blur, early read, no strip, phone moved), `demo`.
- **CONFIRM handling:** when the app sends PASS while the panel is on HOLD, show "Press CONFIRM on the panel within 60 s". Reflect `EVT CLEARED` or `EVT CONFIRM_TIMEOUT` when they arrive.
- Wording on screen: "HOLD: RO+UV", "Adaptive mode (TDS logic)", "UNKNOWN: re-test". Never "safe".
- On startup, show a checklist: Arduino linked, phone reachable, camera locked, ROI loaded, model frozen (test mode only). Block the START button until all are green, and say why.

### Phase 8: dataset protocol tooling (45 min)
- `data\labels\train_labels.csv`: sample_id, concentration_mg_L, standard_batch, strip_lot, tds_ppm, made_by, date.
- `data\labels\test_answer_key.csv`: written by the chemistry person only (sample_id, true concentration, type: spiked_tap / compliant / unseen_standard / conservative, tds_ppm). The app never reads it during test sessions. Only `evaluate.py` reads it, after the test session is closed.
- A `close_session.py` that locks a session folder (read-only plus a hash manifest), so test data can't be edited after the fact.
- Baselines for the "within one block" claim: a form or CSV where a person records their eye reading against the bottle chart, and a phone-photo reading, for the same unseen strips.

### Phase 9: evaluation against the abstract's targets (1 h)
`evaluate.py` produces `results\round3_results.md`, CSVs and figures (confusion matrix, colour curve with training points, per-test tables):

| Test | Samples | Target |
|---|---|---|
| Missed nitrate | 20 tap samples spiked to 60–100 mg/L, meter TDS < 300 | ≤ 1/20 not held (baseline TDS rule: 20/20 missed) |
| False holds | 20 compliant samples, 0–10 mg/L | ≤ 2/20 held |
| Block accuracy | 30 unseen standards: 0, 25, 35, 45, 55, 100 mg/L × 5 | ≥ 29/30 within one block |
| Conservative zone | 10 standards at 25–44 mg/L | Report how many are held |
| Degraded images | 30 deliberately degraded captures | ≥ 95% return UNKNOWN |
| Dip to verdict | All scored reads | ≤ 3 min |

- **"Within one block" definition** (state it in the results file): for a standard exactly on a chart block, correct = that block or either neighbour. For a standard between two blocks (35, 45 and 55 sit between 25 and 50, or between 50 and 100 depending on the chart), correct = either bracketing block.
- An UNKNOWN on a spiked sample counts as **not missed** for the safety claim (the hold is never cleared), but count and report UNKNOWN rates separately and honestly in every table.
- Report 95% Clopper–Pearson intervals next to every proportion, and state plainly that 29/30 is a pass/fail target, not proof of 95%.
- Include the eye and phone-photo baselines for the 30 unseen strips.
- Never recompute with different thresholds after seeing test results. If you find a bug after the test, report both versions and label them.

### Phase 10: tests and verification (ongoing, finish before handover)
- Unit tests: every quality check, the colour correction, curve fitting and rejection, the decision rule (all branches, including the borderline band), unit conversion, and the serial parser (fed recorded Arduino lines).
- Hardware-in-the-loop script `tools\hil_check.py`, run with me watching:
  1. Ping keeps Link OK.
  2. The app sends UNKNOWN while on HOLD → stays HOLD.
  3. The app sends PASS while on HOLD → CONFIRM_WAIT. I press the button → ADAPTIVE is mirrored in the app.
  4. Pull the phone off Wi-Fi mid-read → UNKNOWN.
  5. Open the drawer mid-read → light-leak fail → UNKNOWN.
  6. Read a dry, undipped strip and record what happens. A dry pad can look like the 0 mg/L block. If the pipeline can't tell dry from wet (for example by pad sheen or colour), list "operator must dip the strip; a dry strip can read as 0" as a known limitation in `DECISIONS.md` and RUNBOOK.md.
  Record each result in `results\hil_log.md` with time.
- Dry runs I can do tonight without nitrate solutions: empty tray, dry strip, strip dipped in distilled water, strip dipped in plain tap water. Use these to set initial quality-gate thresholds and to test the flow end to end. Label them `purpose=dry` and never use them as training data for nitrate levels except the 0 mg/L distilled blanks, if I confirm.

### Phase 11: handover documents (45 min)
- **RUNBOOK.md**, written for non-experts, with numbered steps and screenshots:
  1. Start of day: plug in the Arduino, start IP Webcam, run the app, pass the startup checklist.
  2. Lock the camera.
  3. Calibrate the ROI (only when the tray, phone or lid moves; after training starts, never).
  4. Run a training session.
  5. Train and freeze the model.
  6. Run a blind test session.
  7. Run a degraded session.
  8. Evaluate.
  9. Run the demo for filming (including the live fail-safe: pull the drawer, pull the Arduino USB and replug, clear the hold with PASS + button).
  10. Troubleshooting.
- **README.md**: architecture diagram (phone → PC → Arduino), how to install, how to run tests.
- **For the report:** `results\report_numbers.md`, every number the 4-page PDF needs, each with its source file. Also measured app timings, and a list of all changes since Round 2 (ESP32-CAM replaced by phone + IP Webcam, Arduino Nano panel, 7-in-1 strips, fertiliser-grade KNO₃ standards from Stanes Hugo 13-0-45, ≥94% by label).

---

## 7. What I will give you when you ask

1. The phone's IP address (shown in IP Webcam after "Start server").
2. A daylight photo of the strip bottle's colour chart and instructions: pad order, nitrate pad position, read time, units.
3. Confirmation of `lighting_mode` (dock LEDs inside the box, or phone torch through the flash hole).
4. Later: `train_labels.csv` and `test_answer_key.csv` from our chemistry person.

---

## 8. Final self-check before you report done

Re-read this prompt end to end and confirm, item by item, in `PROGRESS.md`:
- The Arduino protocol in code matches section 3 exactly, including reset-on-open handling and the 2 s PING.
- The decision rules match section 4. UNKNOWN is never mapped to PASS anywhere.
- No file under `data\` or `results\` contains synthetic data.
- Test mode never reads the answer key. Evaluation only loads frozen models.
- Training and testing refuse to run if the camera lock check fails or the ROI changed since the model was frozen (store the ROI hash in the model).
- No screen, log or file says "safe to drink".
- All unit tests pass (paste the pytest summary). The HIL steps that need me are listed as "pending: needs operator".
- RUNBOOK.md can be followed by someone who has never seen the code.

Then give me a short summary: what works, what was verified on hardware, what still needs us (standards, training, scored tests), and the exact next commands to run.
