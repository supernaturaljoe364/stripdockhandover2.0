# StripDock: Round 3 PC software

Team Undampori (RSET), atomQUEST 2026, Track 2 (water purifiers).
StripDock reads the **nitrate pad** of an eSHa AQUA QUICK TEST strip with a phone camera inside a light-tight dock. It decides **HOLD / PASS / UNKNOWN** and drives the purifier control panel. It is indicative screening; it never says water is safe.

## Architecture

```
 ┌──────────────────────┐   USB cable: adb forward → HTTP (IP Webcam)   ┌─────────────────────────────┐   USB serial 115200   ┌───────────────────────────┐
 │ Android phone        │ ──── /shot.jpg frames ────▶ │ Windows PC: this app        │ ── HOLD/PASS/UNKNOWN ─▶│ Arduino Nano panel        │
 │ IP Webcam, torch on, │ ◀─── /settings, torch ───── │ quality gate → colour corr. │ ◀── OK <STATE>, EVT ── │ StripDockPanel.ino        │
 │ camera locked        │                             │ → model → decision → log    │      PING every 2 s    │ OLED, HOLD/CONFIRM LEDs,  │
 └──────────┬───────────┘                             │ web UI http://localhost:5000│                        │ CONFIRM button, EEPROM    │
            │ looks down through the lid              └─────────────────────────────┘                        └───────────────────────────┘
 ┌──────────▼───────────┐
 │ Dock: light-tight box│  strip in a sliding tray against an end-stop,
 │                      │  white / grey / black reference patches glued on the tray floor
 └──────────────────────┘
```

Since 2026-11-20 the phone is reached over a USB cable (`adb forward tcp:8080 tcp:8080`), because Wi-Fi dropped frames (DECISIONS D-36). The phone never talks to the panel. The PC is the bridge. The **Arduino is the single source of truth for the hold**: the app only mirrors the replies and EVT lines it receives.

## What one read does

1. The operator dips the strip, blots it, slides the tray in, and presses **START**. The timer starts.
2. Every ~1 s the app grabs a frame and checks the black patch for light leaks and that the strip and patches are where calibration put them.
3. At 60, 61.5, 63, 64.5 and 66 s (never before 60 s) it takes 5 read frames.
4. **Quality gate**: phone reachable / frame fresh, strip seated (±15 px), light leak, exposure and clipping, glare, blur, timing, colour drift across the 5 frames ("still developing"), reference-patch consistency, strip present. Any failure → UNKNOWN.
5. **Colour**: linear RGB → white-patch gain → 3-point (black/grey/white) per-channel fit → CIELAB D65. The pad colour is the median over each region shrunk 20%, averaged over the 5 frames.
6. **Model** (frozen, hash-checked): a calibration curve through our own standards in Lab, plus a nearest-centroid reference. Too far from the curve → UNKNOWN.
7. **Decision** (frozen rules): estimate ≥ 25 mg/L NO₃⁻ → HOLD; a borderline band below 25 → HOLD; otherwise PASS. Then send it to the panel.
8. Everything (frames, raw RGB and corrected Lab per region per frame, checks, verdict, panel reply, timing) is saved to `data\sessions\<session>\<sample>\`.

## Install

Python 3.11 or newer (this PC: 3.14.3).
```
cd C:\stripdock_r3
python -m venv .venv
.venv\Scripts\python -m pip install opencv-python numpy pyserial requests flask pyyaml pandas matplotlib pytest
```

## Run

| What | Command |
|---|---|
| App (web UI) | `start_app.bat` or `.venv\Scripts\python run_app.py` |
| Panel check / send commands by hand | `.venv\Scripts\python tools\panel_check.py` |
| Phone endpoints, latency, stability | `.venv\Scripts\python tools\phone_check.py` |
| Camera lock: new / re-apply / check | `tools\lock_camera.py --new` / `tools\lock_camera.py` / `tools\lock_camera.py --check` |
| ROI calibration (no web UI) | `.venv\Scripts\python tools\calibrate_roi.py` |
| Threshold suggestions from dry runs | `.venv\Scripts\python tools\suggest_thresholds.py [--apply]` |
| Hardware-in-the-loop check | `.venv\Scripts\python tools\hil_check.py` |
| Train / freeze | `.venv\Scripts\python train.py` then `.venv\Scripts\python freeze_model.py` |
| Close (lock) a session | `.venv\Scripts\python close_session.py <session>` (`--list`, `--verify`) |
| Evaluate | `.venv\Scripts\python evaluate.py [--tag name]` |

**New to the project? Start with HANDOVER.md.** The operator procedure is in **RUNBOOK.md**, the design choices in **DECISIONS.md**, and the build log in **PROGRESS.md**.

## Tests

```
.venv\Scripts\python -m pytest -q tests
```
89 tests cover: CIEDE2000 (Sharma 2005 reference pairs), colour correction, units and blocks, every decision branch (including the borderline band and "UNKNOWN never becomes PASS"), the serial protocol against a fake board that runs the sketch's state machine (reset-on-open, READY/STATUS, PING, events, USB unplug/replug, silent-board watchdog), every quality check, ROI re-location, curve and centroid models, rejection, LOSO, freeze and tamper detection, session locking, an end-to-end read flow with a fake phone (drawer opened, phone lost, no strip, phone moved, early read, glare, blur, off-curve colour), the whole train → freeze → test → close → evaluate path, and guards (the app never reads the answer key, no "safe" wording, no synthetic data in `data\` or `results\`).

**Synthetic images are used only in tests** (`tests\synthetic\`). Their invented pad colours are not the eSHa strip's response and are never written to `data\` or `results\`.

## Layout

```
config.yaml            phone IP, serial port, lighting, read time, thresholds
app\                   package: panel, phone, camlock, roi, colour, quality, features, model, decision, readflow, station, web
tools\                 panel_check, phone_check, lock_camera, calibrate_roi, suggest_thresholds, hil_check
data\chart\            bottle photos + chart.json
data\calib\            roi.json, roi_reference.jpg, empty_tray.jpg, camera_settings.json
data\sessions\         one folder per session (train / test / degraded / demo / dry)
data\labels\           train_labels.csv, test_answer_key.csv (chemistry person only), baselines
models\                model_latest.json, model_card.md; models\frozen\ read-only frozen models + CURRENT.txt
results\               checks, logs, evaluation outputs, report_numbers.md
tests\                 unit tests; tests\synthetic\ generated test images only
```

The Arduino sketch `StripDockPanel.ino` is frozen and lives outside this folder. This software never modifies or uploads it.
