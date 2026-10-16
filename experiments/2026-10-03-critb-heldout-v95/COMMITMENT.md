## V95_PRE_COLLECTION_COMMITMENT — v95 held-out 수집 전 고정 (수집 시작 전 게시)

- 사전검사(precheck, 렌더링 없음·수집 아님) 소스 SHA: `12c1e58c3ee129d5a635fe5f300145566656489a`
- 사전검사 폴더: `/Users/changmin/projects/ugrp/outputs/heldout-v95-precheck-20261003T085307Z` (로컬 보관, 원격 백업 아님)
- 상태: `PRECHECK_PASS`, 지도 2개 × 로봇 2대, 기준 B 판정 없음(null)
- 수집 SHA는 이 글 뒤의 브랜치 head다. 실행기는 binding.json(실행 소스·번들·일정·검증기 해시)이 아래 값과 같을 때만 수집한다.
- 고정(변경 금지): 기준 B `74c312b5…`, r4 `fa7d3aa2…`, r5 yaw `978727fc…`, 회전 부록 `6129f144…`.

| 항목 | sha256 |
|---|---|
| `precheck.json` | `868ffa29e1ee6e74366af0039796bbe87e43b99ebeb07928c26717a777a39dbe` |
| `SHA256SUMS.json` | `fd8d7f1127ec976728fef18bf5936dc273511bef8e1996f481753df6a054a461` |
| `binding.json` | `636fd14eb795b0a31397c4ff5cd735e00f04a141ec14631bfd658284326ef923` |
| `bundle zone_wide_door_geometry_v3` | `8f22f067a2480bc2fd18d9be48fef831ff4ca89d3b4f25071f6e187c9890cdf5` |
| `bundle zone_wide_corridor_final_v3` | `3f63ce8e7b4ba3c91e57c230af66308e2b277e88f08c86d55ee8f82c07309961` |
| `schedule zone_wide_door_geometry_v3` | `6afaf0b25d627a176ec7472e3002f9cc7585d6d486373c807e600110c5a94276` |
| `schedule zone_wide_corridor_final_v3` | `6afaf0b25d627a176ec7472e3002f9cc7585d6d486373c807e600110c5a94276` |
| `scripts/validate_consumer_criterion_b_v95.py` | `89d24d70f16f71add3a950a8262879dc6e3e93e75b3663e4d53a3fb97f9d6233` |
| `harness/kinematic_overlap.py` | `472f984afc5680dfed31781e8bfc6f036b68d029788ff4fff5f94949b12ae2bc` |
| `scripts/precheck_heldout_v95.py` | `f337534faf16fff17b0847170998e40f567f2b7bdd9a5dba2ac40e7427ff6042` |
| `configs/criterion_b_prior_kinematics_v95.json` | `7a6041c3371ad19eb3110ad42d1b24b2d6f731934a651a6f93cbfe229db1b9dc` |

수집 결과를 본 뒤 위 파일을 바꾸면 그 사실·diff·이유를 따로 기록한다. 기준 B는 바꾸지 않는다.

### 수집 사례(case)와 시작 자세

번들 `zone-final-pair-v95`, workflow `zone-final-pair-heldout-v95` 3.7.0. 확인 항목: `calibration-unloaded`, seed 911, 사례당 370 SIM s(reset 최대 5 SIM s), 0.05 s마다 `eval_only` pose 기록. 두 로봇 모두 구동한다. 명령 크기는 v88 unloaded와 같다(±0.01/0.02/0.03, 10 s step + 1 s coast; ±0.02 PRBS31 0.5 s chip + 2.5 s coast). 축 순서는 r1 left→turn→forward, r2 forward→turn→left. PRBS 순환 위상은 r1 7, r2 13. weld OFF, 초음파 off, `floor_light_v1`, `cargo_noslip_v1`.

| 사례 | r1 시작 (x, y, yaw) | r2 시작 (x, y, yaw) |
|---|---|---|
| `zone_wide_door_geometry_v3` | (3.75, −1.85, 0.35) | (0.65, −1.55, −0.55) |
| `zone_wide_corridor_final_v3` | (4.15, −1.40, −0.35) | (0.85, −1.10, 0.55) |

### 채점 규칙(수집 전 고정, 변경 없음)

1. **운동 관문 먼저:** 수집된 r1/r2 `pose.jsonl` 4개에 `scripts/validate_consumer_criterion_b_v95.py --pose …`(sha256 `89d24d70f16f71add3a950a8262879dc6e3e93e75b3663e4d53a3fb97f9d6233`, `harness/kinematic_overlap.py` `472f984afc5680dfed31781e8bfc6f036b68d029788ff4fff5f94949b12ae2bc`)를 실행한다. `t`·위치·회전이 1e-6 안에서 0.2 s 이상 이전 자료 38개 또는 서로와 겹치면 `PREVIOUSLY_SEEN`이고, 그 자료는 채점하지 않는다.
2. **기준 B(바꾸지 않음):** `consumer_criterion_B.json` sha256 `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`. horizon 0.2/0.5/1/2/3/3.2 s, 성분 forward/left/yaw를 모두 본다. 기준: p95(|오차|/σ) ≤ 2, 2σ 포함률 ≥ 0.9. 지도·사례·split(step/PRBS)·로봇마다 따로 판정하고 합치지 않는다. 축 결과 하나라도 실패면 전체 false, 실패 없이 미검증 축이 있으면 null이다. 검증 중 재적합은 하지 않는다.
3. **후보:** 전진·옆 r4 `fa7d3aa2e791086a9e73280b2dd4122bff5186d82503b56e17d5be27ca9bf071`(r4 회전은 영구 null). 회전 r5 `978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97`, 회전 부록 `6129f144c840510535de053ffcce325ef934e8192c6adf777b2df8d976f5da08`. 고정 B 검증기 `scripts/validate_consumer_criterion_b.py` `8d2a693a6e3bbca79a8214fd388bff79a0609400f07de831ad9be3cf22e85a88`.
4. **아직 없는 것:** v95 raw(두 로봇·새 시작점)를 위 B 계산에 넣는 채점 어댑터는 아직 없다. 그 어댑터는 수집 raw를 열기 전에 별도 PR로 만들고 검토한 뒤, 그 sha256을 #219에 따로 게시하고 나서 채점한다. 기존 v91 어댑터 입력 계약은 우회해 재사용하지 않는다.

### 수집 명령 (조정자 go 뒤에만)

```bash
# 이 글의 comment id를 <ID>에 넣는다. 다른 claude SIM 슬롯이 물리 coordinator를 잡고 있으면 V95_COORDINATOR_PID=<그 PID>도 준다.
cd /Users/changmin/projects/ugrp-wt/critb-heldout-v94 && git switch codex/critb-heldout-new-starts && git pull --ff-only
V95_SOURCE_SHA=$(git rev-parse HEAD) \
V95_PRECHECK_DIR=/Users/changmin/projects/ugrp/outputs/heldout-v95-precheck-20261003T085307Z \
V95_COMMITMENT_COMMENT=<ID> \
bash experiments/2026-10-03-critb-heldout-v95/collect.sh
```
