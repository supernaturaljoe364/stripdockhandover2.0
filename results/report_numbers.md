# Numbers for the 4-page report

Each number gives its source file. Numbers marked **PENDING** do not exist yet. Don't put anything in the report until it has a source here.

## Measured so far (2026-11-19, real hardware)

| Quantity | Value | Source |
|---|---|---|
| Phone frame endpoint used | `/shot.jpg`, 1920×1080 | `results/phone_check.json` |
| `/shot.jpg` latency | 0.081 s mean, 0.122 s max (10 frames) | `results/phone_check.json` |
| `/photo.jpg` latency (not used) | 0.820 s mean, 1.566 s max | `results/phone_check.json` |
| Frame-to-frame colour stability, `/shot.jpg` (phone not yet docked, auto settings) | ΔE00 0.19 mean | `results/phone_check.json` |
| Locked camera | exposure 4.548 ms, ISO 25, daylight WB, single-shot AF, torch on, 1920×1080, JPEG q90 | `data/calib/camera_settings.json` (hash 231eb85694496d11) |
| White-patch colour stability with the camera locked, in the dock | ΔE00 0.18 mean, 0.22 max (10 frames) | `results/camera_lock_check.json` |
| Panel: board reset-to-READY after opening the port | 2.22 s | measured with pyserial, PROGRESS.md Phase 1 |
| Panel HIL 1–3 | Link OK while pinging; UNKNOWN on HOLD stays HOLD; PASS on HOLD → CONFIRM_WAIT → button → ADAPTIVE | `results/hil_log.md` |
| Unit tests | 86 passed (19 Nov); 93 passed (22 Nov, after D-43/D-44) | PROGRESS.md (pytest summaries) |

## Measured 2026-11-22 (new laptop; real captures)

| Quantity | Value | Source |
|---|---|---|
| Phone over USB (`adb forward`), `/shot.jpg` latency | 0.048 s mean, 0.067 s max (10 frames) | `results/phone_check_20261122_newpc.json` |
| Quality thresholds (frozen) | black_L_max 27.5, black_jump_max 2.0, white L* 71–83.2, blur_min 54.5, drift 3.0 ΔE00, strip_min_dE 3.0 (D-45), grey chroma 10.6; seated: tray 30 px, strip 40 px with tip match ≥ 0.75 (D-44) | `results/threshold_suggestions.md`, `config.yaml`, frozen model JSON |
| HIL 4: phone USB cable pulled mid-read | UNKNOWN ("no read frames"); panel stayed HOLD; verdict after ≈ 3 min (timeouts) | `results/hil_log.md` (2026-11-22 14:07) |
| HIL 5: drawer opened mid-read | UNKNOWN (light leak: black-patch jump 2.7 L* > 2.0) | `results/hil_log.md` (2026-11-22 14:09) |
| HIL 6: dry undipped strip | recorded before a model existed (UNKNOWN: no model); dry pad colour (95.5, −4.1, 14.8) ≈ wet 0 mg/L strips; **repeat with the frozen model** | `results/hil_log.md`, `data/labels/collection_log_20261122.md` |
| Training | 8 reads (0, 10, 25, 35, 45, 55, 100 mg/L; 0 ×2), 2 reads excluded by the gate (seated, blur); series B skipped (team, D-46) | `models/model_card.md` |
| Frozen model | curve; UNKNOWN if ΔE00 > 2.73; borderline HOLD from 4.5 mg/L; sha256 29933a5c… | `models/model_card.md`, `models/frozen/model_20261122_150113.json`, `results/freeze_log.md` |
| LOSO on training data | 0 missed, 0 false holds, 0 UNKNOWN, 4/8 within one block, mean abs log error 0.67 | `models/model_card.md`, `results/train_loso.csv` |
| Blind test | 13 coded samples (B01–B13), 18 reads, 2 sessions (closed, intact) | `results/round3_results.md`, `results/test_reads.csv` |
| Missed nitrate, spiked tap ≥ 60 mg/L (74–154 mg/L added) | **0/4 not held** (95% CI 0–60%), 4 HOLD, 0 UNKNOWN | `results/round3_results.md` |
| Compliant 0 mg/L (tap B02, distilled B08) | **held 2/4 reads** (CI 7–93%), 2 UNKNOWN (blur); per sample (final read): 2/2 held — false holds, expected from the 4.5 mg/L band (D-46) | `results/round3_results.md`, `results/test_reads.csv` |
| Conservative zone 25–44 mg/L (30.3, 38.8, 40.5) | **held 3/3** (CI 29–100%) | `results/round3_results.md` |
| Within one block, "unseen" samples (18.1, 60.3, 94.3, 133.8 mg/L) | 4/7 reads (CI 18–90%; the 3 misses are B01's UNKNOWN reads); per sample (final read): 4/4 | `results/round3_results.md`, `results/test_reads.csv` |
| Every blind sample, final verdict | **13/13 HOLD**, including both 0 mg/L samples and the 18 mg/L sample (borderline band) | `results/test_reads.csv` |
| UNKNOWN reads in the blind test | 5/18 reads (B01 ×3: seated, blur, blur; B08 ×2: blur, blur) — the camera sat at the frozen blur limit after a post-freeze phone disturbance | `data/labels/collection_log_20261122.md` items 9–10 |
| START-to-verdict | median 66 s, max 66 s (18 reads) | `results/round3_results.md` |
| Reference method (centroid, logged only) | within one block 6/7 reads | `results/round3_results.md` |

Caveats that must go with these numbers: sample sizes are tiny (see the CIs); one strip per training level except 0 (D-46);
spiked and "unseen" samples went above the planned 60–100 mg/L and the answer key holds the **added** nitrate (tap water's own
nitrate looked ≈ 0 from T1); the phone was disturbed and re-aligned after freezing (≈ 0.6° residual turn), so blind reads were
taken with slightly different optics than training (log item 9).

## Still PENDING

| Quantity | Will come from |
|---|---|
| Baseline TDS rule misses (needs tap-water TDS for B01–B07) | answer key `tds_ppm`, then `evaluate.py` |
| Eye and phone-photo baselines | not recorded (strips used) |
| Degraded captures → UNKNOWN | **not completed (team decision 23 Nov):** only early_read was run, 3/3 UNKNOWN (session `20261123_1512_degraded`, v2 limits). Drawer-opened and phone-lost fail-safes are covered by HIL 4–5 instead (`results/hil_log.md`). |
| HIL 6 with the frozen model (dry strip D1) | `tools/hil_check.py --steps 6` |
| Demo (HOLD, PASS + CONFIRM, drawer pulled, USB pulled) | filming; needs 2 new strips |

## Changes since Round 2 (for the report)

- **Camera:** the ESP32-CAM was replaced by an Android phone running **IP Webcam**, reached over a **USB cable** (`adb forward`; Wi-Fi was tried and dropped 8 of 30 frames, DECISIONS D-36). Exposure, white balance and focus are locked over HTTP: fixed manual exposure, a fixed white-balance preset, and single-shot autofocus, because the strip is closer than the phone's manual-focus range.
- **Lighting:** the phone torch, held constant for the whole session, never flashed per shot.
- **Panel:** an **Arduino Nano** (`StripDockPanel.ino`) with a 0.96" SSD1306 OLED, HOLD LED, green CONFIRM LED and a physical CONFIRM button. The hold is latched in EEPROM and survives power loss. Clearing it needs a PASS plus a button press within 60 s. UNKNOWN never clears a hold. A 10 s link-lost display.
- **Strips:** eSHa AQUA QUICK TEST **7-in-1** (NO₃⁻ chart 0/10/25/50/100/250/500 mg/L, read at 60 s, lot 7833).
- **Standards:** made from fertiliser-grade KNO₃ (**Stanes Hugo 13-0-45, ≥94% by label**).
- **Software:** a PC app with a quality gate (light leak, exposure, glare, blur, timing and drift, strip seated, strip present, phone fresh), colour correction by a per-channel **white-patch gain** (`white_gain`; the grey and black patches are used for checks, DECISIONS D-37), a calibration curve trained on our own standards with unknown rejection, frozen and hash-checked models, blind test sessions locked with a SHA-256 manifest, and an evaluation with Clopper–Pearson intervals.
