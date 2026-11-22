# StripDock: move to a new PC and finish Round 3

This file has two parts:
- **Part 1** is for the **team** to do by hand before starting Claude Code (about 30–45 min).
- **Part 2** is the **prompt for the new Claude Code chat**. It has no memory of earlier work; everything it needs is in the repo plus this file.

Deadline: **atomQUEST 2026 Round 3 closes Thu 26 Nov 2026, 11:59 PM IST.** Today is Sun 22 Nov.

---

## Part 1: team checklist (do this first, by hand)

### On the OLD PC (if you can still reach it)
1. Make sure everything is pushed: in `C:\stripdock_r3`, run `git status`. It should say "nothing to commit". If not, commit and push.
2. Note the Windows user name and the `adb.exe` path. Old: `C:\Users\Hp\AppData\Local\Android\Sdk\platform-tools\adb.exe`.

### On the NEW PC
1. **Install:**
   - **Git for Windows**
   - **Python 3.11 or newer** from python.org (tick "Add python.exe to PATH")
   - **Android SDK Platform-Tools** (Google's standalone zip; unzip to `C:\platform-tools\`)
   - **Claude Code**
   - The **Arduino IDE is NOT needed.** The panel's program stays on the Arduino and must never be re-uploaded.
2. **Clone the repo into exactly `C:\stripdock_r3`:**
   ```
   git clone https://github.com/Vaisakh-2k6/stripdockhandover.git C:\stripdock_r3
   ```
3. **Copy this file into `C:\stripdock_r3\`.**
4. **Plug in the Arduino panel** (USB). Windows should show it under Device Manager → Ports as "USB Serial Port (COMx)". It's an FTDI chip, and Windows normally installs the driver itself. Note the COM number. The OLED shows the panel screen with "LINK LOST" until the app runs; that's normal.
5. **Phone (Samsung S24 with IP Webcam):**
   - Plug it into the new PC with its USB cable.
   - It asks **"Allow USB debugging?"** for this new computer. Tick **Always allow** and tap **Allow**.
   - Open IP Webcam and tap **Start server**.
6. **Start Claude Code from Windows PowerShell, NOT WSL/Ubuntu.** Under WSL it can't reach the COM port or adb. Run:
   ```
   cd C:\stripdock_r3
   claude --dangerously-skip-permissions "Read MIGRATION_PROMPT_NEWPC.md, Part 2, and follow it."
   ```
   Check the header line shows a Windows path like `C:\stripdock_r3`, not `/mnt/c/...`.
7. **Physical dock fixes** (HANDOVER.md step A; do these while Claude Code sets up):
   - Glue an **L-shaped stop** on the tray floor. The strip tip goes into its corner every time.
   - Give the **tray a hard stop**, so "fully in" always ends at the same place.
   - **Glue the reference patches flat and permanently:** white paper, a **printed 50% grey** square, and **matte black card**. Marker ink is shiny under the torch.
   - **Tape the phone** into its place on the lid.
   - **Count the strips left** (eSHa 7-in-1, lot 7833). There were about 42 on 20 Nov.

---

## Part 2: prompt for Claude Code

You are taking over **StripDock**, Team Undampori's (RSET) entry in atomQUEST 2026, Track 2, Round 3, on a **new Windows PC**. The software was built on another PC on 19–20 Nov and is in this repo (`C:\stripdock_r3`). Your jobs: **(1)** migrate and verify the setup on this PC, **(2)** fix the few known stale items, **(3)** guide the team through the remaining data collection, training, testing and evaluation before the deadline (**26 Nov 2026, 11:59 PM IST**; the team needs results by **24 Nov** to film and write the report on 25 Nov).

### 0. Read first (in this order) before touching anything
1. `HANDOVER.md`: status, hardware, next steps A–J. **This is your main brief.**
2. `RUNBOOK.md`: operator procedure.
3. `DECISIONS.md`: D-01 to D-40, especially D-35 to D-40.
4. `PROGRESS.md`: build log and the final self-check.
5. `StripDock_R3_MASTER_PROMPT.md`: the original brief. **Its section 1 (ground rules: scope, safety, honesty) and section 4 (decision rules) still bind you.**

Summarise in 10 lines what you understood, then continue. Don't wait for approval unless a rule below says to ask.

### 1. Hard rules (unchanged from the original brief)
- Work only inside `C:\stripdock_r3`. No system changes except installing Python packages into `.venv`.
- **Never modify or re-upload the Arduino sketch** (`firmware/StripDockPanel/StripDockPanel.ino` is a byte-identical reference copy of what is on the board). It passed its hardware safety tests.
- **Never fabricate data.** Synthetic images only under `tests/synthetic/`. Every reported number must come from a script run on real captures.
- Decision rules are frozen: HOLD at ≥ 25 mg/L block (or in the borderline band); any doubt → UNKNOWN; UNKNOWN never clears a hold; never say "safe".
- **Don't tune thresholds after seeing blind-test results.** Closed sessions are hash-locked (`MANIFEST.sha256`); never edit them.
- No git pushes unless the team asks. Commit locally at milestones with clear messages.
- Ask the team only for physical actions (plugging, placing strips, pressing buttons, making solutions), for observations you can't make yourself (what the OLED shows), and for decisions that change the plan or the rules.

### 2. Facts about the setup (already verified on the old PC)
- **Panel:** Arduino Nano clone, **FTDI** USB-serial (VID:PID 0403:6001), 115200 baud. Protocol: commands HOLD / PASS / UNKNOWN / PING / STATUS; replies `OK <ADAPTIVE|HOLD|CONFIRM_WAIT>`; `READY <STATE>` about 2.2 s after the port opens (opening resets the board); events `EVT CLEARED`, `EVT CONFIRM_TIMEOUT`, `EVT BUTTON_IGNORED`. OLED + HOLD LED (D3) + green CONFIRM LED (D4) + CONFIRM button (D2). The hold is in EEPROM. **The COM number will be different on this PC.**
- **Phone:** Samsung Galaxy S24 (SM-S921E), IP Webcam, reached over **USB via `adb forward tcp:8080 tcp:8080`** at `http://127.0.0.1:8080` (D-36; Wi-Fi dropped frames). Endpoint `/shot.jpg`. Torch on (`lighting_mode: phone_torch`). Camera locked with manual exposure 4.548 ms, ISO 25, daylight WB, single-shot AF (`data/calib/camera_settings.json`).
- **Strip:** eSHa AQUA QUICK TEST 7-in-1, lot 7833. Nitrate = pad 1 at the tip. Read at 60 s. Units mg/L NO₃⁻. Chart blocks 0/10/25/50/100/250/500.
- **Stocks (made 20 Nov):** A ≈ 9,207 mg/L (16 g Stanes Hugo 13-0-45 in 1 L); B ≈ 921 mg/L (100 mL A + 900 mL water). Recipes in `data/labels/STANDARDS_PREP.md`: `V_stock_B (mL) = target × 250 / 921` per 250 mL. If the stocks are older than ~5 days or were left open or warm, ask the team whether to remake them.
- **Pilot data:** session `20261120_1120_train`, 7 strips, one per level, closed. It was taken with a dock layout that has since changed, so after recalibration `train.py` will (correctly) refuse it. Keep it as pilot evidence only. It showed: 10 → 25 mg/L is a clear colour step (Δa\* ≈ 4); 25–55 is nearly flat (Δa\* < 1); 70–100 rises again.

### 3. Migration tasks (do these first, verify each, log them in PROGRESS.md under "Day 4 (2026-11-22): migration to new PC")
1. **Environment:**
   - Record the OS, Python version and free disk space.
   - Create `.venv` and install `opencv-python numpy pyserial requests flask pyyaml pandas matplotlib pytest`.
   - **Write `requirements.txt`** with the versions you actually installed, and commit it.
   - Run `.venv\Scripts\python -m pytest -q tests`. **Expect 89 passed.** Two tests (`test_model.py::test_save_freeze_load_and_tamper`, `test_session.py::test_session_lifecycle`) check that files are read-only, so they fail if run as administrator/root. Don't run Claude Code elevated. If those two fail, check for that before anything else.
2. **Verify the data survived the move:** `close_session.py --list`, then `--verify` both closed sessions. Both must say INTACT. `.gitattributes` keeps `data/`, `models/` and `results/` byte-for-byte; if a manifest fails, check `git config core.autocrlf` and re-clone with `-c core.autocrlf=false`.
3. **Fix machine-specific paths:**
   - `config.yaml`: `adb_path` → this PC's `adb.exe` (find it; ask the team if not installed). `serial_port` → `auto`.
   - `start_app.bat`: same `adb.exe` path. Better: make it read `adb_path` from `config.yaml` via a tiny Python one-liner, so there's one place to edit.
   - Search the repo for `C:\Users\Hp` and fix any other occurrence. Leave historical records (PROGRESS.md, camera_settings.json `phone` field) as they are.
4. **Panel check:** `tools\panel_check.py --watch 10`. Expect READY then `OK <STATE>` every 2 s. Ask the team to confirm the OLED bottom line says **Link OK**. If "Access is denied": something else holds the port (Arduino IDE Serial Monitor).
5. **Phone check:**
   - `adb devices` must list the phone as `device`. If it says `unauthorized`, ask the team to accept the USB-debugging prompt.
   - Then run `tools\phone_check.py`. Expect `/shot.jpg` latency well under 0.5 s.
6. **Camera lock:** `tools\lock_camera.py --check`.
   - If the phone and dock are physically unchanged since 20 Nov (unlikely after moving them), it may pass. Otherwise follow HANDOVER step B: `lock_camera.py --new`, recalibrate on `/calibrate` (empty-tray capture first), `lock_camera.py --new` again, then `--refresh-focus-ref`.
   - **Do the recalibration only after the team has finished the physical dock fixes** (L-stop, tray stop, glued matte patches, phone taped). Ask them to confirm first.
7. **Start the app** (`start_app.bat`) and confirm the startup checklist is green (except "Session open" and "Model frozen"). Take a screenshot to `docs/screenshots/main_startup_newpc.png`.

### 4. Stale items to fix (small edits; record each in DECISIONS.md or PROGRESS.md)
1. `results/report_numbers.md`, "Changes since Round 2":
   - It says the phone is reached **over Wi-Fi**. It's now **USB via adb forward** (D-36).
   - It says **3-point** colour correction. It's now **white_gain** (D-37).
   - Fix both.
2. `RUNBOOK.md` and `tools/hil_check.py` step 4 say "phone off **Wi-Fi** mid-read". With the USB link, the realistic test is "**stop IP Webcam's server, or unplug the phone's USB cable, mid-read**". Update the wording, and the code prompt if needed. The expected result is still UNKNOWN.
3. `RUNBOOK.md` §5 says 3 strips per level. HANDOVER says at least 2. D-38 recorded the team's 20 Nov decision of 1. Replace with the strip plan in section 5 below, once the team confirms the strip count.
4. **D-39 strip tolerance:** implement it **only if**, after the physical L-stop and tray stop, 3 test placements of a dry strip still land more than 15 px from calibration. Measure first, then decide. If you implement it, add tests and a DECISIONS entry.

### 5. Remaining work plan (propose it to the team with the real strip count, then pre-register it)
Strip budget: about 42 on 20 Nov. **Get the exact count from the team.** Suggested allocation for 42 strips:

| Stage | Strips | Notes |
|---|---|---|
| Dry runs (HANDOVER step D) | 3 | E1–E3 empty tray (no strip), D1 dry strip (keep it for HIL step 6 and degraded reads), W1 distilled, T1 tap. Then `suggest_thresholds.py`, review the table, then `--apply`. |
| HIL steps 4–6 (step E) | 0 | Reuse D1 |
| Training (step F) | **14** | 0, 10, 25, 35, 45, 55, 100 mg/L × **2 strips**, each level in its own rinsed cup (250 mL recipe). **Randomised order** (fixes the D-40 ascending-order confound). The chemistry person fills `train_labels.csv` first. |
| Train + freeze (step G) | 0 | Read `models/model_card.md` with the team. With 2 strips per level the spread estimate is weak: say so. |
| Blind test (step H) | **22** | 8 spiked tap (60–100 mg/L in tap water with TDS < 300), 6 compliant (0–10), 6 unseen standards (0, 25, 35, 45, 55, 100 × 1), 2 conservative (30, 40). Coded by the chemistry person, who alone writes `test_answer_key.csv`. |
| Degraded (step H) | 0 new | Reuse used strips. Drawer open, torch through seam, blur, early read, no strip, phone moved: ~2–3 each, ~15 reads. |
| Demo for filming (step J) | 3 | One spiked (HOLD), one compliant (PASS + CONFIRM), one spare |
| **Total** | **42** | If fewer strips remain, cut from the blind unseen standards first, then the conservative pair. Never cut training below 2 per level. |

Write the plan as `data/labels/collection_plan_20261122.csv` **before** any read (pre-registration, like the 20 Nov plan), and commit it.

**Timeline to propose:**
- **Sun 22:** migration, dock fixes, recalibration, dry runs, thresholds, HIL 4–6.
- **Mon 23:** training + freeze (morning); blind + degraded tests (afternoon); evaluate (evening).
- **Tue 24:** demo filming (RUNBOOK §10), `results/report_numbers.md` complete.
- **Wed 25:** report writing (outside your scope unless asked).
- **Thu 26:** buffer only.

### 6. How to work with the team
- They're non-experts. Give **one short numbered instruction block at a time**, wait for "done", then check the result yourself (logs, saved frames, `meta.json`) before moving on.
- Before each read session: run `lock_camera.py --check`, confirm the app checklist is green, and remind them: dip 1 s, blot the edge, tip into the L-stop, tray fully in, press START at once, don't touch the dock until the verdict.
- After each session: **Close session** in the app, then `close_session.py --verify`.
- Look at a few saved frames per session (`data/sessions/<s>/<sample>/frames/read_0.jpg`) to confirm the ROI boxes sit on the pad and the patches, and that there's no glare.
- Keep `PROGRESS.md` updated with times. Every number destined for the report goes into `results/report_numbers.md` with its source file.

### 7. Final self-check before saying a stage is done
- Tests pass (paste the pytest summary).
- Closed sessions verify INTACT.
- The frozen model's ROI, camera and threshold hashes match the current config before any test session (the app enforces this; confirm).
- No synthetic data in `data/` or `results/`. No "safe" wording anywhere.
- `report_numbers.md` has no number without a source.

Start now with section 0, then section 3.
