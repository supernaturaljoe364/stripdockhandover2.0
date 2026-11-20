# Hardware-in-the-loop log

| time | step | result | detail |
|---|---|---|---|
| 2026-11-19 21:36:48 | setup | FAIL | panel not linked: COM8 is in use by another program (Access is denied). Close the Arduino IDE Serial Monitor / Serial Plotter and any other serial tool, then retry. |
| 2026-11-19 21:39:05 | 1 ping keeps Link OK | PASS (software side; OLED: see operator line) | link_ok=True, operator saw Link OK=None |
| 2026-11-19 21:39:06 | 2 UNKNOWN on HOLD stays HOLD | PASS | HOLD->HOLD, UNKNOWN->HOLD |
| 2026-11-19 21:39:13 | 3 PASS on HOLD -> CONFIRM_WAIT -> button -> ADAPTIVE | PASS | PASS->CONFIRM_WAIT, mirrored state now ADAPTIVE, operator confirmed=None |
| 2026-11-19 21:40:03 | 1 ping keeps Link OK (operator) | PASS | Operator, asked while tools/panel_check.py --watch 90 was pinging: OLED bottom line "Link OK". (Their earlier "LINK LOST" answer was given after the step-1 script had exited; >10 s without commands shows LINK LOST, as designed.) |
| 2026-11-19 21:40:03 | 3 PASS on HOLD (operator) | PASS | Operator: green LED lit with OLED "CONFIRM?"; after pressing the physical CONFIRM button the OLED showed ADAPTIVE and the HOLD LED went off. App mirrored ADAPTIVE from EVT CLEARED. |
