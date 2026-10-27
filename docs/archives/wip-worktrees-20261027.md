# WIP worktree archive branches (2026-10-27)

HAN-30. Dirty Mac worktree files preserved as-found on dedicated branches (original branches untouched).
Secrets were excluded from commits; none found in this pass (see agent log). Large files deferred to Drive when >95MB.

| worktree | source branch | archive branch |
|----------|---------------|----------------|
| beamact3 | codex/drivecheck | import/wip-beamact3-20261027 |
| e2e18 | codex/e2e18-end-assignment | import/wip-e2e18-20261027 |
| e2ewarp-contract | dsh/e2ewarp-contract-v1 | import/wip-e2ewarp-contract-20261027 |
| gcp6setup | codex/warpfit | import/wip-gcp6setup-20261027 |
| llmhost | codex/llmhost | import/wip-llmhost-20261027 |
| macprune | codex/macprune | import/wip-macprune-20261027 |
| mapbuild1 | codex/egomem1 | import/wip-mapbuild1-20261027 |
| mast3rcmp | codex/mast3rcmp | import/wip-mast3rcmp-20261027 |
| reloc21 | claude/reloc21 | import/wip-reloc21-20261027 |
| rl-act | claude/rl-act | import/wip-rl-act-20261027 |
| warp-act | claude/warp-act | import/wip-warp-act-20261027 |
| warp4 | codex/warp6 | import/wip-warp4-20261027 |
| warp5 | claude/warp5 | import/wip-warp5-20261027 |

Do **not** merge without review. Draft umbrella PR only.
