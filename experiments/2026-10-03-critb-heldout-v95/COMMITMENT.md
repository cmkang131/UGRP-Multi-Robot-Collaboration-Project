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
