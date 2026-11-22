# Quality threshold suggestions (2026-11-22 14:53:48)

From 13 good reads and 3 empty-tray reads in: 20261122_1252_dry, 20261122_1348_dry, 20261122_1411_train, 20261122_1433_train

| threshold | current | suggested | basis |
|---|---|---|---|
| black_L_max | 27.5 | 27.7 | max black L* in good reads 21.7 + 6 |
| black_jump_max | 2.0 | 2.0 | 3 x max frame-to-frame jump 0.42 (min 2.0) |
| white_L_min | 71.0 | 71.0 | white L* seen 79.0..79.2, -8/+4 |
| white_L_max | 83.2 | 83.2 | white L* seen 79.0..79.2, -8/+4 |
| blur_min | 54.5 | 5.7 | half the lowest sharpness in good reads (11.4) |
| drift_max_dE | 3.0 | 3.0 | max(current 3.0, 2 x max drift 1.27); dry strips do not develop, so re-check with --with-train before freezing |
| strip_min_dE | 3.0 | 4.8 | midpoint: strips >= 8.6, empty tray <= 1.1 |
| strip_min_absdiff | 4.3 | 1.2 | midpoint: strips >= 1.4, empty tray <= 1.0 |
| grey_chroma_max | 10.6 | 10.9 | 2 x max grey chroma 5.47 (min 4) |

**Not applied (2026-11-22 14:55).** Purpose: re-check drift_max_dE with wet training strips before freezing (max drift 1.27, limit stays 3.0). The tool counted reads that failed the gate (S45-A, blurred frame, sharpness 11.4) as good reads, so its blur/strip suggestions are not valid; thresholds stay as applied at 14:00 plus D-45.
