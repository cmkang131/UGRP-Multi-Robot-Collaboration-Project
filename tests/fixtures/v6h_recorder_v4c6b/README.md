# Registered recorder consumer fixtures

These are consumer-field projections of the 11 explicitly public acceptance
cases from `v6h1-acceptance-3c4fe30e-claude-20260930`, not new confirmatory data.
`provenance.json` pins the source files, producer hash and reviewed golden
classifications. No values are rounded and no missing fields are filled.

Reproduce into a NEW directory (never overwrite these fixtures or raw):

```sh
python experiments/2026-09-30-pair-v6h-carry/analysis/verify_recorder_contract.py \
  --output /tmp/recorder-contract-NEW.json --fixture-dir /tmp/recorder-fixtures-NEW
```

The verifier compares all 36 original file hashes before/after, verifies that
the #292 and acceptance recorder files are byte-identical, and requires the
full original input and projection to yield identical adjudication objects.
The expected ten lag-on PASS_CLEAN and one lag-off FAIL were specified by the
coordinator. CI consumes these checked-in fixtures without access to local raw.
This is format/golden regression coverage, not validation of the blinded cohort.
