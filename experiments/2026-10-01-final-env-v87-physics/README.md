# 최종 환경 v87 물리 수집 기록: P01 3×30 SIM초 + 무하중 보정 3×120 SIM초 (밝은 렌더)

작성: Claude (Sonnet 5.5 하위 에이전트), 2026-10-01. 대상은 PR #342(`codex/final-env-floor-light`)가 등록한
번들 `zone-final-environment-v87`, workflow `zone-final-environment-floor-light-check` 2.20.0.

**이 기록은 자료 수집 결과다.** 상태는 모두 `COLLECTED_UNQUALIFIED`(수집 종료)이며 환경 적합 PASS,
위치 추정 정확도, 파지, 연쇄 완주, 사전 등록 봉인이 아니다. P03은 실행하지 않았다(v3 공동 운반 어댑터 없음).
동기(synchronous) SIM이며 시간/속도 결론은 내지 않는다. 학생·LLM·교사 주행 명령은 0이다.

## 고정한 소스와 실행 조건

| 항목 | 값 |
|---|---|
| 소스 커밋 | `04eb11c6a001f2a7d2ab916765d59b3661c06efe` (PR #342 브랜치 `codex/final-env-floor-light`) |
| 실행 worktree | `/Users/changmin/projects/ugrp-wt/phys-v87-p01cal`, 커밋 고정·작업 트리 깨끗 |
| 잠금 | `agent_lock.py acquire --owner claude --branch claude/phys-v87-p01cal`, 실행마다 획득·해제(trap) |
| 시드 | 911 |
| 렌더 | `floor_light_v1` (sha256 `e3ea8aebc473f99def92fa368f8aaa11e5872dc5b2a8ec8ba9a308641d2b6ec5`) |
| 번들 해시(P01) | door `c3fb67f8e472706ae589a60c21a9962e449898e446a4fc28465739c77cda0713`, two_doors `266a6157fd331a41fd024720662867194f646fb9d59af5054b59ff7087390664`, corridor `61129b5c296255fea3411a0aa915c5847cb96031c18b9a7126393920174be025` |
| 번들 해시(보정) | door `69223ff466b2aded6983f299c9408cbbc738d02b14edc2b60915052378bc256e`, two_doors `7d3076cc223e44bc0c3dd0198b8f41c116f3540bec6e8ea3aef00c1825d768bf`, corridor `ba69f23db8dbb3a6087192741af43ff5ddba01355190134af376e0349e4b251d` |
| 디스크 | 실행 전 여유 약 38 GiB (10 GiB 기준 통과) |

### 이탈 사항 (인계 문서 대비)

- 인계 문서대로 `--detach` worktree로 시작했으나, 실행기는 `git branch --show-current`가 잠금의 branch와 같아야
  한다(`live owned host lock for this branch required`). 분리 HEAD는 빈 문자열이라 **두 번 거부**됐다
  (세션 기록 `…043901-af228e2b`, `…043926-05c227aa`, 둘 다 `process_failed` exit 2, 출력 폴더·물리 시작 전).
  같은 커밋에서 `git switch -c claude/phys-v87-p01cal`로 이름 있는 브랜치를 만들고(HEAD 동일, 소스 바이트 동일)
  그 이름으로 잠금을 잡아 다시 실행했다. 소스는 바꾸지 않았다. 후속 인계 문서에는 "분리 HEAD 불가, 이름 있는 브랜치 필요"를
  적는 것이 좋다.
- 기존 문서의 `--branch codex/final-env-floor-light`는 그 브랜치가 다른 worktree에 있어 쓸 수 없었다.

## 명령 (둘 다 `set -euo pipefail` subshell + 해제 trap)

```bash
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
FINAL_SHA=04eb11c6a001f2a7d2ab916765d59b3661c06efe
RUN_ROOT=/Users/changmin/projects/ugrp/outputs/final-env-v87-04eb11c6-20261001
# 정적 확인: 두 check 모두 runnable:true, blocked_on [] (P01 90 s 상한, 보정 360 s 상한)
"$PY" -m scripts.run_final_environment_floor_light --check p01 --expected-source-sha $FINAL_SHA --output $RUN_ROOT/p01
"$PY" -m scripts.run_final_environment_floor_light --check calibration --expected-source-sha $FINAL_SHA --output $RUN_ROOT/calibration-unloaded
# 실행 (lock 획득 → 세션 실행 → 해제)
"$PY" scripts/agent_lock.py acquire --owner claude --branch claude/phys-v87-p01cal --purpose '…' --pid $$ --expected-minutes 30|60
"$PY" scripts/ugrp_session.py run final-env-v87-p01|final-env-v87-calibration -- \
  "$PY" -m scripts.sim_cli workflow run zone-final-environment-floor-light-check -- \
  --check p01|calibration --seed 911 --expected-source-sha $FINAL_SHA --execute --lock-owner claude --output $RUN_ROOT/<p01|calibration-unloaded>
```

## 부하 평균 (uptime, 1/5/15분)

다른 Codex 작업이 동시에 돌고 있어 부하가 높았다. 동기 SIM이므로 SIM 결과에는 영향이 없다고 보지만 시간 비교에는 쓰지 않는다.

| 실행 | 시작 | 지도 끝 (door → two_doors → corridor) |
|---|---|---|
| P01 | 10.8 / 15.1 / 16.7 | 11.0 / 14.6 / 16.4 → 12.0 / 14.6 / 16.3 → 10.0 / 13.8 / 16.0 |
| 보정 | 9.8 / 13.3 / 15.7 | 18.5 / 22.1 / 19.5 → 20.6 / 21.6 / 19.7 → 18.5 / 21.1 / 19.7 |

(잠금을 잡을 때 기록된 값: P01 10.4 / 15.1 / 16.7, 보정 8.8 / 13.3 / 15.8.)

## P01 결과 (3×30 SIM초)

`result.json`: `COLLECTED_UNQUALIFIED`, 분모 3, `unattempted` 없음, `source_unchanged: true`, `physical_success: null`.
맵마다 reset 1.30 SIM초(상한 5), 정지 관찰 30.00 SIM초(총 31.3), 모델 호출 0, 실패 없음.

| 지도 | 상태 | 렌더 적용 | 초기 겹침 | 정지 drift | 자기 RGB |
|---|---|---|---|---|---|
| `zone_wide_door_geometry_v3` | COLLECTED_UNQUALIFIED | floor_light_v1, 그림자 0 | 벽/상자/로봇 접촉 0 | 0.0 m, yaw 0.0° | 로봇당 7장 |
| `zone_wide_two_doors_final_v3` | 〃 | 〃 | 〃 | 〃 | 〃 |
| `zone_wide_corridor_final_v3` | 〃 | 〃 | 〃 | 〃 | 〃 |

- **렌더 적용 확인:** 세 지도 모두 `bundle.json`(`render_profile_contract`), `scene.json`(`render_profile`),
  `eval_only/applied.json`(`render_profile`, `render_profile_applied`)에서 프로필 이름·해시가 일치한다.
  실제 적용값: 조명 4개, `light_castshadow [0,0,0,0]`, `light_cutoff [180×4]`, 반사 재질 없음,
  바닥 텍스처 평균 RGB (124.5, 122.0, 118.0).
- **접촉:** `eval_only/contacts.jsonl` 601행(0.05초 표본)에서 바닥 접촉(바퀴 12개, 침투 최대 약 0.16 mm)만 있고
  벽·상자·로봇 간 접촉은 없다. weld 활성 없음. 이 trace는 모든 내부 substep을 기록한 것이 아니다.
- **초기 배치:** 세 지도 모두 r1 (−0.898, 0.55), r2 (−0.898, −0.85), r3 (−0.898, −2.25), yaw 0, 상자 5개 위치 동일.
  (P01은 기본 색 상자 reset이라 지도와 무관하게 같다.)
- **drift:** 로봇 3대 모두 7개 표본에서 기준 위치·자세가 같다(소수 6자리까지 0).
- **자기 RGB를 눈으로 본 내용:** 640×480, 밝은 균일 조명, 바닥은 청회색과 베이지 회색 체크 무늬. 그림자 없음.
  카메라는 차체 앞쪽 낮은 위치에서 앞을 약간 내려다보며 렌즈 왜곡(통 모양)이 있다. 정지 구간이라 로봇마다
  7장이 모두 같은 해시다(시간에 따라 안 변함, 정상). 공중 물체는 없고 작은 상자(빨강·초록·청록)가 멀리 보인다.
  화면 아래쪽 약 25%의 회색 띠는 바닥 체크 무늬의 이음선이 이어지므로 바닥 타일로 보이며 자기 팔이 시야를 가리는 모습은 없었다.
  로봇마다 놓인 y 위치가 달라 r1, r2, r3 가 보는 상자가 다르다.
  door와 corridor 지도는 위쪽 먼 벽 모양만 조금 다르고 나머지는 거의 같다.

## 무하중 보정 수집 결과 (3×120 SIM초)

`result.json`: `COLLECTED_UNQUALIFIED`, 분모 3, `unattempted` 없음, 지도마다 reset 1.30 + 관찰 120.00 SIM초(상한 5 + 120),
모델 호출 0, 실패 없음. **원시 수집만이며 fitting·보정 채택·성공 판정이 아니다.**
`configs/final_environment_measurement_v1.json`의 이벤트 48개(행동 144개: arm 96, look 24, mecanum 24)와 대조했다.

| 확인 | 기대 | 실제 (3개 지도 모두) |
|---|---|---|
| r1 `commands.jsonl` | 144 + 초기 servo 명령 1 | 145 (arm 96, look 24, mecanum 24, initial 1) |
| r2·r3 `commands.jsonl` | 초기 1 | 각 1 |
| 자기 PNG | 120 s ÷ 0.2 s + 1 | 로봇당 601장 (frames.jsonl 601행), 지도당 1,803장 |
| `eval_only/r*/camera_labels.jsonl` | 프레임마다 | 601행 |
| `eval_only/contacts.jsonl` | 0.05 s 표본 | 2,401행, 바닥 접촉뿐, weld 없음 |
| r1 이동 | ±0.03 명령 0.25 s ×4 | 기준 위치 최대 변화 1.6 cm, r2·r3 정지(0.0) |

- 자세 구간: 탐색(servo 3/4/5=740/2320/1320), p20(1072/2400/1482), 빈 carry(777/2053/1646), 각 자세마다
  pan 8단계(1500→1230→970→700→1770→2030→2300) 등 frames.jsonl의 `commanded_servo`와 일치한다.
- **자기 RGB를 눈으로 본 내용(보정):** 탐색 자세 pan 중 왼쪽/가운데 프레임에서 다른 로봇(r2 계열, 주황 메카넘 바퀴 + 주황 팔)과
  빨강·청록 상자가 보인다(예: `samples/cal_door_r1_frame180_partner_visible.png`). 밝고 그림자 없는 장면이며
  한쪽으로 pan하면 벽 모서리와 베이지 타일만 보이는 프레임도 있다. 이번 자세에서는 자기 팔이 시야를 가리지 않았다.

## 이상 징후

- 실행기의 분리 HEAD 거부(위 "이탈 사항"). 소스 문제는 아니며 물리·출력 전 단계에서 닫혔다.
- 측정 계약 문서의 `not_measured`(loaded_camera, loaded_motion, fine_profile)는 이번에도 측정되지 않았다.
- 세 지도가 (P01은 같은 reset, 보정은 r1 움직임이 작아) 거의 같은 관측을 주므로 이 자료만으로 지도별 차이를 말하지 않는다.
- 부하 평균이 10~24로 높았다. 성공/실패 판정에는 쓰이지 않는다.

## 원본 위치와 해시 (삭제·덮어쓰기 없음)

원본은 기본 체크아웃 `outputs/`에만 있다(원격 백업 아님).
`/Users/changmin/projects/ugrp/outputs/final-env-v87-04eb11c6-20261001/` (총 5,592개 파일, 191,864,497 바이트)

| 경로 | sha256 |
|---|---|
| `p01/result.json` | `312ba8a16cbd69fc2aa92325fe6ad6432539130906d54355e83dbbd578707391` |
| `p01/plan.json` | `151518045b13dcc9996b3cfe123ce36b9e53f40707263262115239e267ee3927` |
| `calibration-unloaded/result.json` | `5741d8796bfae7615d97305df3084ecdbac57115ba2940f27494510e9bed7835` |
| `calibration-unloaded/plan.json` | `2a8e434355a1823bfadb2a232dda7829cf7efb1de211a69aad6c925060652aa2` |

- `raw_manifest.tsv.gz`: 위 폴더의 **모든 파일**(p01, calibration-unloaded, sim-run-records)의 상대 경로·바이트·sha256
  (sha256 `59cca3c1e78c7142b0218447150dabb8e1f011d044fa19983bcf100040b3a310`).
- `sim-run-records/`: 표준 관리자 실행 기록 4개(복사본). 성공은 P01 `…043941-49d43cbc`, 보정 `…044151-e9591a9f`;
  앞의 두 개는 위 분리 HEAD 거부(`process_failed`). 원본은 worktree
  `/Users/changmin/projects/ugrp-wt/phys-v87-p01cal/outputs/simulation-runs/`에도 있다(이 worktree는 폐기하지 않음).
- `samples/`: 대표 PNG 3장(각 < 1 MiB, 원본의 복사본). 원시 영상 전체는 커밋하지 않는다.
  `p01_door_r1_t1.3.png`(sha256 `a73fd772103e91be83120f3786bd2b7d98e6a67c3c6a405139328634b6dfcac6`), `p01_door_r2_t31.3.png`(`ffe225def581b9119923ca73d280e22aca6056e36bfaa6ef5cfb6ce67716dd9b`),
  `cal_door_r1_frame180_partner_visible.png`(`109095fd0686366370e76e4efdf781eae5315847ed8774ebddcd9abd722a8966`).
- TensorBoard 변환은 하지 않았다(수집 자료이며 성공률 지표 없음). 필요하면 후속으로 한다.

## 참고 자료

- PR #342 `codex/final-env-floor-light`, `PHYSICS_HANDOFF.md`(커밋 `04eb11c6`)의 "실행 전", "P01", "v3 보정" 절
- [P01 v84 관찰 #341](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/341)
- [실행 버전 관리](../../docs/execution_versioning.md), 측정 계약 `configs/final_environment_measurement_v1.json`
