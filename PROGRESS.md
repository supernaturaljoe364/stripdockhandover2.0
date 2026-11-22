# PROGRESS

Build log, one entry per phase: what was built, what was verified and how, what is still open. "Verified on hardware" means it was run on the real phone and panel on 2026-11-19.

---

## Phase 0: environment audit (2026-11-19, 19:55)

- **OS:** Windows 11 Home Single Language 10.0.26200, x64, 23.6 GB RAM.
- **Python:** 3.14.3 (`C:\Users\Hp\AppData\Local\Python\pythoncore-3.14-64`). No `py` launcher. Venv at `C:\stripdock_r3\.venv`.
- **Packages:** Flask 3.1.3, matplotlib 3.11.2, numpy 2.5.5, opencv-python 5.1.0.95, pandas 3.1.1, pyserial 3.5, pytest 9.2.0, PyYAML 6.0.3, requests 2.34.2. scikit-image was not installed; ΔE00 is our own implementation, tested.
- **Disk:** C: 103 GB free, D: 168 GB free.
- **COM ports:** `COM8: USB Serial Port (COM8)`, manufacturer FTDI, VID:PID 0403:6001, serial A5069RR4A. This Nano clone uses an FTDI chip, not a CH340.
- **Round 2 folder:** `D:\atomquest round-2\work` **does not exist** (searched D:\ and the user folders). Nothing was reused; the pipeline was written fresh.
- **Arduino sketch:** found at `Desktop\StripDockPanel\StripDockPanel.ino` (identical copy in Downloads). **Read only, never modified or uploaded.** Its protocol matches section 3. Small note: its wiring comment says the HOLD LED is **amber** (D3); the prompt says red.
- **Strip:** eSHa AQUA QUICK TEST 7-in-1 (bottle photos copied to `data/chart/`). Operator confirmed: units **NO₃⁻ mg/L**, read time **60 s**, nitrate = pad 1 at the tip, lighting = **phone_torch**, phone IP 192.168.29.229.

## Phase 1: connectivity

**Built:** `app/panel.py` (auto-detect, open, wait up to 3 s for READY, STATUS with retry, a 2 s PING thread, line parser, thread-safe mirrored state + event log, "Access is denied" message, reconnect on USB unplug, watchdog after 3 missed PINGs), `tools/panel_check.py`, `app/phone.py`, `tools/phone_check.py`.

**Verified on hardware:**
- `panel_check.py --watch 14`: READY ADAPTIVE → STATUS → OK, then OK ADAPTIVE every 2 s. `link_ok=True`.
- READY arrives **2.22 s** after opening COM8 (measured with pyserial), inside the 3 s wait.
- Operator confirmed the OLED shows **Link OK** while pinging (asked during a 90 s ping run).
- Seen once: an app start where the board answered STATUS but not the PINGs that followed. It could not be reproduced in two later starts. The watchdog (D-33) now reconnects by itself; a unit test covers it.
- Phone: `results/ipwebcam_status.json` saved. Endpoints `/shot.jpg` (200, 0.08 s) and `/photo.jpg` (200, 0.8 s) exist; `/video` is MJPEG. `/photoaf.jpg` is never used. `phone_check.py` chose **/shot.jpg** (ΔE00 0.19 vs 0.69, latency 0.08 vs 0.82 s): DECISIONS D-06.

## Phase 2: camera locking

**Built:** `tools/lock_camera.py` (`--new`, re-apply, `--check`, `--refresh-focus-ref`) and `app/camlock.py`.

The phone reports `video_size, photo_size, quality, night_vision, scenemode(hdr), flashmode, torch, manual_sensor, exposure_ns, iso, frame_duration, whitebalance, focusmode, focus_distance` but **no exposure_lock or whitebalance_lock** (both 404). They are locked with manual sensor, a fixed WB preset and single-shot AF: DECISIONS D-08.

**Verified on hardware (in the dock):**
- Manual focus is clamped at 10 diopters and blurry at this height. Single autofocus: sharpness 33.2 → 32.7 over 20 s after one trigger, so `focus_method=single_af`.
- Frozen 21:23: exposure 4.548 ms, ISO 25, `daylight`, torch on, 1920×1080, q90 (hash 231eb85694496d11).
- White-patch stability **ΔE00 0.18 mean / 0.22 max** over 10 frames (< 1.0 target): `results/camera_lock_check.json`.
- `lock_camera.py --check` → CAMERA LOCK OK. With the phone off it fails with a clear message.

**Open:** none for the lock itself. After any IP Webcam restart, run `tools\lock_camera.py` (re-apply + one refocus).

## Phase 3: region calibration

**Built:** `app/roi.py` (save/load/hash, template re-location ±15 px tolerance, ±30 px search, 20% shrink, "strip not seated"), the web page `/calibrate` (drag rectangles, empty-tray capture required), and `tools/calibrate_roi.py` (OpenCV fallback).

**Done on hardware:** reference patches iterated with the team. The first versions were glossy plastic and a green pencil scribble, rejected after measurement: DECISIONS D-31. Final layout: strip across the top half, tip at the left; patches glued below. ROI saved with reference + empty-tray frames, **hash 362b035ba62b2381** (`docs/screenshots/roi_layout_20261119.jpg`). Empty vs strip frames re-locate at (1, −3) px, score 0.997.

**Open:** the `/calibrate` web page was tested only through the Flask test client and unit tests, not clicked through by an operator. The regions were drawn from measured coordinates.

## Phase 4: quality gate

**Built:** `app/quality.py`: light leak (level + frame-to-frame jump, monitored about once a second through the countdown), exposure (L* range + clipped fraction), glare (relative to the white patch, D-13), blur, timing, drift ("still developing"), strip present (vs empty tray), phone reachable / frame fresh (latency, byte-identical frames), seated, and reference consistency. `tools/suggest_thresholds.py` derives thresholds from dry runs.

**Verified:** every check has unit tests on synthetic images (`tests/test_quality.py`, `tests/test_readflow.py`). Found and fixed during testing: an absolute glare rule flagged a white 0 mg/L pad as glare.

**Open:** thresholds in `config.yaml` are still **placeholders**. Measured tonight, the raw black patch is L\* 27.3, above the placeholder `black_L_max` 25, so every read would currently be UNKNOWN "light leak". **Dry runs (RUNBOOK §4) must be done, then `suggest_thresholds.py --apply`, before training.**

## Phase 5: colour correction and features

**Built:** `app/colour.py` (sRGB↔linear, Lab D65, CIEDE2000, white-gain + stable 3-point per-channel fit with fallback) and `app/features.py` (per-frame raw RGB / raw Lab / corrected Lab for every region, clip, glare and sharpness; per-capture pad L\* a\* b\*, hue, chroma averaged over the 5 read frames; nitrite logged only).

**Verified:** ΔE00 matches 6 Sharma 2005 pairs to 1e-4. Under a synthetic cast the corrected grey comes out neutral (chroma < 0.5) and the pad is within ΔE00 1.5. On hardware, a frame of the dock gave method `three_point` with grey chroma 2.25 after correction.

## Phase 6: classifier and unknown rejection

**Built:** `app/model.py`: CurveModel (ordered Lab polyline, log interpolation), CentroidModel, LOSO, rejection threshold, borderline band, primary selection, save + SHA-256, freeze (read-only + CURRENT pointer), hash-checked load. Plus `train.py` (camera-lock check, session camera and ROI hash match, label cross-check, model card, LOSO CSV, curve figure) and `freeze_model.py`.

**Verified:** the whole path on synthetic data in `tests/test_model.py` and `tests/test_pipeline.py` (21 synthetic strips → LOSO → thresholds → freeze → tamper detection).

**Open:** no real training data yet. Real thresholds and band will appear in `models/model_card.md` after training.

## Phase 7: read flow and app

**Built:** `app/readflow.py`, `app/station.py`, `app/web.py`, templates, `run_app.py`, `start_app.bat`. Modes train / test / degraded / demo / dry. The startup checklist blocks START with the reasons shown. CONFIRM banner with a 60 s countdown; EVT CLEARED / EVT CONFIRM_TIMEOUT / reboot messages. Panel state shown large. Wording limited to "HOLD: RO+UV", "Adaptive mode (TDS logic)", "UNKNOWN: re-test". The service panel cannot send PASS.

**Verified on hardware:** the app starts, links the panel on COM8, streams the phone preview, and shows a correct checklist. With camera lock + ROI done, everything was green except "Session open" (21:44). Screenshot: `docs/screenshots/main_startup.png`. The end-to-end read flow is verified only with the fake phone and panel (12 scenarios).

**Open:** **no real read has been done yet** (the operator stopped for the night before the dry runs; IP Webcam was then closed). The first real reads are the dry runs.

## Phase 8: dataset protocol tooling

**Built:** label templates and README (`data/labels/`), `close_session.py` (read-only + MANIFEST.sha256, `--verify`, `--list`), baseline template. The app never reads the answer key (guard test).

**Verified:** session close, verify and tamper detection unit-tested.

**Note:** an empty dry session `20261119_2145_dry` (opened by the operator, no reads) exists. It is harmless and left as is.

## Phase 9: evaluation

**Built:** `evaluate.py`: frozen model only, closed + intact sessions only, scores the verdict actually sent at read time, recomputation consistency check, all six target rows with UNKNOWN counts, Clopper–Pearson intervals (verified 29/30 → 82.8–99.9%), baseline TDS rule, eye and phone-photo baselines, per-test tables, degraded-by-type table, confusion matrix and colour-curve figures, `--tag` versions without overwriting.

**Verified:** end to end on synthetic sessions in `tests/test_pipeline.py`.

## Phase 10: tests and HIL

**Unit tests:** final full run after all edits: `86 passed in 168.84s (0:02:48)`.

**HIL (`results/hil_log.md`):**
1. Ping keeps Link OK: **PASS** (operator saw "Link OK" while pinging).
2. UNKNOWN on HOLD stays HOLD: **PASS** (HOLD→HOLD, UNKNOWN→HOLD).
3. PASS on HOLD → CONFIRM_WAIT → button → ADAPTIVE mirrored: **PASS** (EVT CLEARED received; operator saw the green LED and then ADAPTIVE).
4. Phone off Wi-Fi mid-read → UNKNOWN: **pending: needs operator.**
5. Drawer opened mid-read → UNKNOWN: **pending: needs operator.**
6. Dry undipped strip: **pending: needs operator.** Until measured, the limitation "a dry strip can read as 0" stands (DECISIONS D-30, RUNBOOK).

## Phase 11: handover documents

RUNBOOK.md, README.md (architecture, install, tests), DECISIONS.md (D-01 to D-34), `results/report_numbers.md` (every measured number with its source; the rest marked PENDING; changes since Round 2), and `models/model_card.md` (generated by train.py).

---

## Final self-check (master prompt section 8)

| Item | Status |
|---|---|
| The Arduino protocol in code matches section 3 exactly, including reset-on-open and the 2 s PING | **Yes.** 115200, newline ASCII, commands HOLD/PASS/UNKNOWN/PING/STATUS, `OK <STATE>` parsed, `ERR` handled, READY wait ≤ 3 s then STATUS, PING every 2 s, EVT CLEARED/CONFIRM_TIMEOUT/BUTTON_IGNORED mirrored, state never assumed while unlinked (set to None). Tested against a fake board running the sketch's logic; verified on the real board. |
| Decision rules match section 4; UNKNOWN never mapped to PASS | **Yes.** `app/decision.py`. An exhaustive grid test, a guard test (no `UNKNOWN → PASS` mapping in the code), and any read-flow crash → UNKNOWN. |
| No file under `data/` or `results/` contains synthetic data | **Yes.** Guard test `test_no_synthetic_data_in_data_or_results`. Synthetic data lives only in `tests/synthetic/` (and pytest temp dirs, cleaned up). |
| Test mode never reads the answer key; evaluation only loads frozen models | **Yes.** Guard tests: only `evaluate.py` references `test_answer_key`; it uses `load_frozen()` with a hash check. |
| Training and testing refuse if the camera lock check fails or the ROI changed since freezing | **Yes.** `train.py` runs the lock check plus per-session camera and ROI hash matches. Test, degraded and demo sessions refuse to open, and START is blocked, unless the camera is locked and the frozen model's ROI hash, camera hash, thresholds and read time match the current ones. |
| No screen, log or file says "safe to drink" | **Yes.** Guard tests over app, tools, templates and results output. |
| All unit tests pass | **Yes.** `86 passed in 168.84s (0:02:48)` |
| HIL steps that need the operator are listed as pending | **Yes.** Steps 4–6 pending. |
| RUNBOOK.md can be followed by someone who has never seen the code | Written for that: numbered steps, exact commands, what to expect, troubleshooting table. Not yet tried by a team member. |

### Proposed firmware change

None needed.

---

## Day 2 (2026-11-20): recalibration, link fix, pilot data, handover

- **Dock layout changed overnight** (phone/tray moved, patches moved). Re-locked the camera and recalibrated three times
  as the team rearranged the dock. The final layout of 11:05 (ROI hash `ef3c1dd3e11afbd8`) has its empty-tray frame captured.
- **Wi-Fi unreliable** (8 of 30 frames failed, ~30 s outage). Switched to a **USB link via adb port forward** (D-36):
  30 of 30 frames in 0.06–0.11 s. Added a single retry per frame (D-35) with tests.
- **Colour correction fixed to white_gain** (D-37), frozen into the model.
- **Evaluation** targets judged as proportions, with reduced n flagged (D-38).
- **Pilot data:** 7 strips, one per level, single-cup ascending series (D-40, `data/labels/collection_log_20261120.md`).
  The strips were measured correctly (checked visually), but placement varied by 10–42 px, so the strict seated check failed.
  Proposed fix: physical stops plus D-39.
- Stocks made (`data/labels/STANDARDS_PREP.md`). Pre-registered collection plan written before any read.
- New: `tools/guided_read.py`, `app/adbfwd.py`, `firmware/` reference copy, `HANDOVER.md`.
- Tests: 89 passed (full run 2026-11-20, before the handover commit).
- **Not done:** dry runs / thresholds, HIL 4–6, real training set, model, blind tests, evaluation.

---

## Day 4 (2026-11-22): migration to new PC

- **11:20 Environment:** Windows 11 Home Single Language 10.0.26300, x64. C: 47.6 GB free. Python **3.11.6** (was 3.14.3 on the old PC, D-28; ≥ 3.11 is all the code needs). Git 2.51.0. Claude Code runs elevated (High integrity); the read-only tests still pass, because Windows honours the read-only attribute for administrators too.
- **Venv** `.venv` created; packages pinned in `requirements.txt` (opencv-python 5.1.0.95, numpy 2.4.6, pyserial 3.5, requests 2.34.2, Flask 3.1.3, PyYAML 6.0.4, pandas 3.1.1, matplotlib 3.11.2, pytest 9.2.0).
- **Tests:** `89 passed in 323.78s (0:05:23)`.
- **Data survived the move:** `close_session.py --verify` → `20261120_1058_train` INTACT, `20261120_1120_train` INTACT. (`git config core.autocrlf` is `true` on this PC; `.gitattributes` `-text` on data/models/results kept the bytes.)
- **adb:** `winget install Google.PlatformTools` hung (cdn.winget.microsoft.com timed out from this network). Instead Google's official `platform-tools_r37.0.3-win.zip` was downloaded from dl.google.com, its SHA-1 checked against Google's `repository2-1.xml` (7fea85bc…496e5a, match), and unpacked to `C:\stripdock_r3\.platform-tools\` (git-ignored). adb 1.0.41 / 37.0.3.
- **Paths:** `config.yaml` `adb_path` → `C:/stripdock_r3/.platform-tools/platform-tools/adb.exe`, `serial_port: auto`. `start_app.bat` now reads `adb_path` from `config.yaml` (one place to edit) and uses its own folder. No other `C:\Users\Hp` in code (only historical records, left as they are).
- **11:36 Panel:** `panel_check.py --watch 10` → auto-picked **COM7** (FTDI 0403:6001, same serial A5069RR4A; the phone's modem shows as COM9 and is correctly ignored). READY ADAPTIVE ~3 s after opening, then `OK ADAPTIVE` every 2 s; a 240 s watch ended `link_ok=True`. OLED "Link OK": awaiting operator.
- **11:40 Phone:** after the team accepted USB debugging, `adb devices` → `RZCY820AG0F device model:SM_S921E`. `adb forward tcp:8080 tcp:8080` OK. `phone_check.py`: `/shot.jpg` 1920×1080, latency **0.048 s mean / 0.067 s max**, central dE00 0.98 mean (camera unlocked, auto settings, phone not docked). Saved as `results/phone_check_20261122_newpc.json` + `results/ipwebcam_status_20261122_newpc.json`; the 19 Nov files cited in report_numbers.md are kept unchanged.
- **Camera lock:** `lock_camera.py --check` FAILS as expected (IP Webcam back on defaults: torch off, auto exposure/WB, quality 49). To be redone with recalibration after the physical dock fixes (HANDOVER step A/B).
- **Stale items fixed:** report_numbers.md "Changes since Round 2" (Wi-Fi → USB adb forward, D-36; 3-point → white_gain, D-37). HIL step 4 is now "phone link lost mid-read: unplug the phone's USB cable (or stop IP Webcam's server)" in `tools/hil_check.py` (prompt, log label, reconnect instructions) and RUNBOOK. RUNBOOK COM8 → COMx, "Phone reachable" hint updated for USB.
