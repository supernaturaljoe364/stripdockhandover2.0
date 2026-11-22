# Quality threshold suggestions (2026-11-22 14:00:45)

From 3 good reads and 3 empty-tray reads in: 20261122_1252_dry, 20261122_1348_dry

| threshold | current | suggested | basis |
|---|---|---|---|
| black_L_max | 25.0 | 27.5 | max black L* in good reads 21.5 + 6 |
| black_jump_max | 4.0 | 2.0 | 3 x max frame-to-frame jump 0.34 (min 2.0) |
| white_L_min | 60.0 | 71.0 | white L* seen 79.0..79.2, -8/+4 |
| white_L_max | 97.0 | 83.2 | white L* seen 79.0..79.2, -8/+4 |
| blur_min | 15.0 | 54.5 | half the lowest sharpness in good reads (109.0) |
| drift_max_dE | 3.0 | 3.0 | max(current 3.0, 2 x max drift 1.17); dry strips do not develop, so re-check with --with-train before freezing |
| strip_min_dE | 6.0 | 7.0 | midpoint: strips >= 12.9, empty tray <= 1.1 |
| strip_min_absdiff | 12.0 | 4.3 | midpoint: strips >= 7.7, empty tray <= 1.0 |
| grey_chroma_max | 8.0 | 10.6 | 2 x max grey chroma 5.31 (min 4) |
