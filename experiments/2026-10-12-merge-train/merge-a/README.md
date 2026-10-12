# E2E merge-a: PR #452–#458
- Frozen E2E18 source: `cf805b77555f079ec65d49c49a33c47bdc36673e`; #459 excluded.
- Branch integration preserves workflow bytes; existing raw evidence is unchanged.
- Local integration failures: missing beam fixture; mutable text checked against historical hashes.
- Historical text is copied from its recorded SHA into `native-artifact-snapshots/`.
- CI and independent read-only review are recorded in `summary.json` and the PR.
- No new physical, model, browser, or VM execution.
