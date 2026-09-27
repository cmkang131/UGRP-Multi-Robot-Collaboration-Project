# dev11/dev12 stop-clock fixture

`reports.json` records all 79 + 79 r2 reports strictly inside the second
`align_relook_stop` interval (start, start + 8 s), with raw timestamps read
from the original per-frame input JSON. The original report fields are copied
without recomputing `last_fix_t`. No pixels, GT, provider calls or physics.

`host_v5g.py` is an exact two-method AST excerpt from the host at the recorded
source SHA. The manifest includes its SHA, the full host source SHA, the raw
root, command line numbers, full raw-file hashes and each input JSON hash.
Replay compares the old rounded host hold and the current raw host hold at the
same independently recorded raw stop event, keeping the saved drive unchanged.
It is not a claim that rewriting historical log rows validates physical success.

See `tests/test_zone_pair_v5h.py` and
`experiments/2026-09-27-zone-pair-dev/dev11_12_diagnosis.md`.
