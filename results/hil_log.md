# Hardware-in-the-loop log

| time | step | result | detail |
|---|---|---|---|
| 2026-11-19 21:36:48 | setup | FAIL | panel not linked: COM8 is in use by another program (Access is denied). Close the Arduino IDE Serial Monitor / Serial Plotter and any other serial tool, then retry. |
| 2026-11-19 21:39:05 | 1 ping keeps Link OK | PASS (software side; OLED: see operator line) | link_ok=True, operator saw Link OK=None |
| 2026-11-19 21:39:06 | 2 UNKNOWN on HOLD stays HOLD | PASS | HOLD->HOLD, UNKNOWN->HOLD |
| 2026-11-19 21:39:13 | 3 PASS on HOLD -> CONFIRM_WAIT -> button -> ADAPTIVE | PASS | PASS->CONFIRM_WAIT, mirrored state now ADAPTIVE, operator confirmed=None |
| 2026-11-19 21:40:03 | 1 ping keeps Link OK (operator) | PASS | Operator, asked while tools/panel_check.py --watch 90 was pinging: OLED bottom line "Link OK". (Their earlier "LINK LOST" answer was given after the step-1 script had exited; >10 s without commands shows LINK LOST, as designed.) |
| 2026-11-19 21:40:03 | 3 PASS on HOLD (operator) | PASS | Operator: green LED lit with OLED "CONFIRM?"; after pressing the physical CONFIRM button the OLED showed ADAPTIVE and the HOLD LED went off. App mirrored ADAPTIVE from EVT CLEARED. |
| 2026-11-22 14:07:46 | 4 phone link lost mid-read (USB cable pulled / server stopped) | PASS | verdict UNKNOWN; reasons ["phone unreachable / stale frame: monitor25: frame request failed (/shot.jpg): HTTPConnectionPool(host='127.0.0.1', port=8080): Max retries exceeded with url: /shot.jpg (Caused by ConnectTimeoutError(<HTTPConnection(host='127.0.0.1', port=8080) at 0x20bff95d710>, 'Connection to 127.0.0.1 timed out. (connect timeout=2.0)'))", 'no read frames received from the phone']; panel HOLD (read_time 60 s) |
| 2026-11-22 14:09:42 | 5 drawer opened mid-read | PASS | verdict UNKNOWN; reasons ['light leak: black patch jumped 2.7 L* between frames (drawer/seam?)'] (read_time 60 s) |
| 2026-11-22 14:11:07 | 6 dry undipped strip | RECORDED | verdict UNKNOWN; est None; reasons ['no calibration model loaded (not confident)']; features {'pad_L': 95.523, 'pad_a': -4.11, 'pad_b': 14.799000000000001, 'pad_C': 15.359117845761846, 'pad_h': 105.52111573414182, 'n_frames': 5, 'nitrite_L': 98.39219999999997, 'nitrite_a': -4.772799999999999, 'nitrite_b': 11.692000000000002, 'nitrite_C': 12.628637449859744, 'nitrite_h': 112.20581026327257} |
| 2026-11-23 15:51:48 | 3 PASS on HOLD -> CONFIRM_WAIT -> button -> ADAPTIVE | FAIL | PASS->CONFIRM_WAIT, mirrored state now HOLD, operator confirmed=None |
| 2026-11-23 15:53:00 | 3 note | INFO | The 15:51:48 FAIL row is a CONFIRM timeout: the operator did not press the button within 60 s (team was messaging), so the panel returned CONFIRM_WAIT -> HOLD as designed (EVT CONFIRM_TIMEOUT behaviour). Not a hardware fault; step 3 repeated below. |
