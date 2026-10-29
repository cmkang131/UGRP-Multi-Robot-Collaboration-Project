# Solo ACT checkpoint archive (2026-09-16)

HAN-30. Large weights are **not** in git (no LFS). Stored on Google Drive under `UGRP/archive-20261027/`.

Source tree (Mac, pre-archive):
`outputs/retired-worktrees/act-feasibility-training/outputs/act-expanded50-balanced-10000-seed{16,17}/`

Training code / experiment records: branch `claude/act-solo-teacher` @ `6f057f7e9` (`experiments/2026-09-16-act-feasibility`).

Protocol: `ugrp.act_feasibility.v1`, sampling `balanced`, planned steps `10000`, selection = lowest development `selection_score`.
Data: expanded50 balanced. Source SHA `361695c31569fb2004304fbcafe6cf0b5738fc7a`.

## Tarballs (Drive)

| file | bytes | sha256 |
|------|------:|--------|
| act-expanded50-balanced-10000-seed16.tar.gz | see exact sizes below | 9fa18fcf34c66ade0648c4bd2b8d52e38fbefd622f1d7af70af5e7dbb017ad7c |
| act-expanded50-balanced-10000-seed17.tar.gz | see exact sizes below | 6188550f4aace255a572f05722bc2399d93154be765c73ef132de8121b889bea |

Drive folder: https://drive.google.com/drive/folders/1WmUAVSu7kkpcWjodc7tCNSeV1s5FkB04

## Selected models (inside tarballs)

| path | seed | run | selected step | trained wall (KST mtime) | model.safetensors sha256 |
|------|-----:|-----|-------------:|--------------------------|--------------------------|
| .../seed16/r1/act/model.safetensors | 16 | r1 | 9500 | 2026-09-16 20:50:28 KST | 359d66dd92f2a963af789c0cfe625abade14025c6922c5a0114e6ba5e7772b25 |
| .../seed16/r3/act/model.safetensors | 16 | r3 | 9500 | 2026-09-16 20:59:08 KST | c59ddeecb650e78f273dd0530668451498951d9bdb2f34541c8d1c31eb4a0697 |
| .../seed17/r1/act/model.safetensors | 17 | r1 | 9500 | 2026-09-16 20:54:55 KST | 0f2d2ae60a227e1212c26b5f3c5bad74a4c6900e7847a25a8b9e851d54776f07 |
| .../seed17/r3/act/model.safetensors | 17 | r3 | 8500 | 2026-09-16 21:03:22 KST | ae95dcae4a91fe4f33e26ddfb583f17d7e5be551b82feaad17630dcfa4e279d2 |

Note: on-disk `model.safetensors` is the selected checkpoint (selection_score), not necessarily step 10000 weights.

## Related experiment branch

- `claude/act-solo-teacher` @ 6f057f7e9 (already on origin; prior PR #502 closed)

## Exact tar sizes (local staging)

- `act-expanded50-balanced-10000-seed16.tar.gz`: 85165714 bytes
- `act-expanded50-balanced-10000-seed17.tar.gz`: 85166252 bytes


## Companion tarballs (same Drive folder; sha256 re-download verified 2026-10-27 KST)

| file | bytes | sha256 |
|------|------:|--------|
| act-old20-uniform-3000-v2.tar.gz | 85045760 | 021c329faf5cf7b6dd9ffc8400ef66bdcaf9b69c939e2e59c33d86c772096b23 |
| act-old20-balanced-3000.tar.gz | 85045198 | ac199f7a0bdc6b148dc8b667e59e9899eb518831c01fbb611d613f581494f8a0 |
| final-physics-seed16.tar.gz | 3930162 | 4fbb8e18341e7c42561860f4e7804a3eeba9fcf89e4c5a162b6568a971c7bfbd |
| final-physics-seed17.tar.gz | 1886149 | 4ed91a6830d95674ccd77abf28453fd28c62ea54e77c267dee2471b9bec61dee |
| teacher-expand30-v1.tar.gz | 1770559 | 26b22c1107e06227ec89be6d669a7d020ec04d286555e120812f803f4381bec8 |
| final-analysis.tar.gz | 924729 | c5c600c70f8147dc1ce83db2c0280f2080630178eee404a859bb9d9c7961ba71 |
| development-physics-old20-balanced.tar.gz | 285138 | 8ce7c692f4c121e7b6c37c4733379eac7bfc316b3540af7618ec788931c8b9f5 |

Mac copies of the above (and seed16/17) were deleted after verification. Log: `~/ugrp-upload-delete-log-20261027.txt`.
