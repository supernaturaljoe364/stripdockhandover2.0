# Labels

- `train_labels.csv` - filled by the chemistry person for TRAINING strips.
  Columns: sample_id, concentration_mg_L (mg/L NO3- nitrate ion, not NO3-N), standard_batch,
  strip_lot, tds_ppm, made_by, date. sample_id must equal the code typed into the app.
- `test_answer_key.csv` - written by the chemistry person ONLY, kept away from the operators
  until the test session is closed. Columns: sample_id, true_concentration_mg_L, type
  (spiked_tap | compliant | unseen_standard | conservative), tds_ppm.
  The app never reads it; only `evaluate.py` reads it, after the test sessions are closed.
- `baseline_readings.csv` - copy `baseline_readings_TEMPLATE.csv`. For the 30 unseen
  standards a person records the chart block they see by eye against the bottle (eye_block_mg_L),
  and the block read from a plain phone photo of the strip held next to the bottle
  (phone_photo_block_mg_L), at 60 s, without seeing StripDock's result.
