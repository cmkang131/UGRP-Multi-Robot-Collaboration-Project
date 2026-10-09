# Portable S2 contract inputs

Small JSON inputs for offline tests only. `source.json` records original local paths,
byte hashes and copies. No RGB, simulator trajectories, secrets or new physical result.

`start-template.json`, `start-result.json` and three calibration files are byte copies.
`v133-bundle.json` changes only the start-proof path to this repository and the resulting
bundle digest; runtime/options/source hashes are unchanged. Registration fixture copies
replace needed input paths and the fixture bundle digest. Other provenance paths are
records, not test inputs. The originals and production registrations are not edited.

`tests/s2_ci_inputs.py` selects these plans with pytest monkeypatch, scoped to the seven
contract test modules. All production admission, file hashes, fixed-source validation,
option rejection and start-proof checks still run. This is not a new executable bundle
or permission to run a physical experiment from fixture data.
