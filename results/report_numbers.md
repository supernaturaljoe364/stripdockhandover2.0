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
| Unit tests | 86 passed | PROGRESS.md (pytest summary) |

## PENDING (filled by the scripts, then copied here with the source)

| Quantity | Will come from |
|---|---|
| Missed nitrate (spiked tap, 60–100 mg/L): not held / 20, UNKNOWN count, 95% CI | `results/round3_results.md` |
| Baseline TDS rule misses / 20 (from the answer key's TDS) | `results/round3_results.md` |
| False holds (compliant 0–10 mg/L) / 20, UNKNOWN count, CI | `results/round3_results.md` |
| Within one block, unseen standards / 30, CI; eye baseline; phone-photo baseline | `results/round3_results.md` |
| Conservative zone (25–44 mg/L) held / 10 | `results/round3_results.md` |
| Degraded captures → UNKNOWN / 30, by type | `results/round3_results.md` |
| START-to-verdict time, median and max | `results/round3_results.md` (expected ≈ 67 s: 60 s read time + 6 s window + processing) |
| Rejection threshold (ΔE00), borderline band (mg/L), primary method, LOSO results | `models/model_card.md`, `results/train_loso.csv` |
| Quality thresholds as frozen | `results/threshold_suggestions.md`, frozen model JSON |
| HIL 4–6 (phone off Wi-Fi, drawer opened, dry strip) | `results/hil_log.md` |

## Changes since Round 2 (for the report)

- **Camera:** the ESP32-CAM was replaced by an Android phone running **IP Webcam** over Wi-Fi. Exposure, white balance and focus are locked over HTTP: fixed manual exposure, a fixed white-balance preset, and single-shot autofocus, because the strip is closer than the phone's manual-focus range.
- **Lighting:** the phone torch, held constant for the whole session, never flashed per shot.
- **Panel:** an **Arduino Nano** (`StripDockPanel.ino`) with a 0.96" SSD1306 OLED, HOLD LED, green CONFIRM LED and a physical CONFIRM button. The hold is latched in EEPROM and survives power loss. Clearing it needs a PASS plus a button press within 60 s. UNKNOWN never clears a hold. A 10 s link-lost display.
- **Strips:** eSHa AQUA QUICK TEST **7-in-1** (NO₃⁻ chart 0/10/25/50/100/250/500 mg/L, read at 60 s, lot 7833).
- **Standards:** made from fertiliser-grade KNO₃ (**Stanes Hugo 13-0-45, ≥94% by label**).
- **Software:** a PC app with a quality gate (light leak, exposure, glare, blur, timing and drift, strip seated, strip present, phone fresh), 3-point reference-patch colour correction, a calibration curve trained on our own standards with unknown rejection, frozen and hash-checked models, blind test sessions locked with a SHA-256 manifest, and an evaluation with Clopper–Pearson intervals.
