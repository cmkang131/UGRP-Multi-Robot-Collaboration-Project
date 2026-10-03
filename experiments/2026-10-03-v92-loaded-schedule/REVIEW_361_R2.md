# PR #361 독립 재검토 R2 — MERGE AFTER FIXES

2026-10-03, Codex. **검토 범위는 `a9481446d9c7c503bdbc53941d3538cd5ec5ee12..9583d3cb7ef2d6f30a5d47fa73ec92964c94eeb0`만**이다.
[조정자 D1–D5](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204)와
[고정 해시·인계 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361#issuecomment-5966310640)을 직접 읽었다.
9583d3cb 이후의 조립기 커밋은 검토·승인하지 않는다.

**판정: MERGE AFTER FIXES.** 이전 P1 카탈로그 회귀는 해결됐다. HIGH 수집 설계·B″의
탐색 하한·8초 창·해시는 D1–D4에 부합하며 이번 diff에서 새로운 P0/P1 구현 결함은 찾지 못했다.
그러나 **정확한 대상 SHA의 필수 CI가 실패**했고, 요청된 **288개 조합의 실제 lifted 선별 후 지지**는
아직 증거가 없다. 후자를 일정상의 명령 지지나 짧은 팬 재현으로 통과 처리하지 않는다.
이 판정은 UNQUALIFIED 교사 수집 경로에 한정하며 D5·새 로더/학생 번들·보정/운반 성공 승인이 아니다.

## 한 묶음으로 전달하는 남은 조건

### P1 — 필수 CI 실패: 보존된 기존 SIM 슬롯 동시 진입 경쟁 조건

- 대상 SHA의 [shard 6](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37102992747/job/111146165209):
  `test_concurrent_admissions_cannot_both_succeed`에서 **1 failed, 1263 passed, 19 skipped, 139 subtests passed**.
  [필수 집계 offline-regressions](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/37102992747/job/111149071164)는 **FAILURE**다.
  전체 check는 33개 중 성공31·실패2(해당 shard와 집계). 기존 카탈로그 shard 2는 성공했다.
- 위치: `scripts/agent_lock.py:39`, `scripts/agent_lock.py:57`,
  `scripts/agent_sim_slots.py:72`, `scripts/agent_sim_slots.py:104`, `tests/test_agent_sim_slots.py:65`.
  이 세 파일은 **a9481446..9583d3cb에서 바뀌지 않았다**. 새 HIGH/B″ 회귀로 오인하지 않는다.
- 구체적 반례: legacy `physics` 잠금의 `owner.json` 생성/쓰기가 끝나기 전에
  SIM 슬롯의 `_require_physics`가 파일을 읽으면 빈 문자열에 `json.loads`가 적용되어
  `JSONDecodeError`가 난다. SIM admission의 flock은 legacy 작성자를 직렬화하지 않는다.
  정당한 거부 예외인 RuntimeError가 아니어서 기존 동시 진입 테스트도 실패한다.
- 원격 로그만 인용하지 않고 **변경하지 않은 테스트 함수를 격리된 임시 root에서 최대100회** 실행했다.
  처음28회 통과, **29번째에 동일한 예외·동일 호출 경로 재현** 후 중단했다. 실제 공용 잠금·기존 프로세스를 사용하지 않았다.
  이 증거는 이중 물리 실행이 성공했다는 뜻은 아니다. 불완전 잠금을 읽는 오류와 필수 CI 실패를 확인했다.
- 완료 조건: 기존 잠금 보존 범위를 조정자와 연결해 별도 수정하거나 해당 의존성을 수정한 소스를 반영하고,
  미완성 metadata 상태의 안전한 거부와 경쟁 회귀를 검증한 뒤 **최종 후보 SHA의 필수 CI 전체 통과**를 확인한다.
  재시도 한 번의 통과를 경쟁 조건 해소 증거로 쓰지 않는다. 검토자는 구현을 수정하지 않았다.

### 검증 미완료 — HIGH의 288개 조합은 명령 지지만 확인됨

- 위치: `tests/test_zone_final_pair_loaded.py:87`의 검사와 `harness/zone_final_pair_loaded_schedule.py:52`의 일정.
  2로봇×3축×2부호×4수준×6 horizon = **288개**가 모두 HIGH에 있고,
  각10초 plateau에 가능한 창은 horizon .2/.5/1/2/3/3.2초 순서로 **197/191/181/161/141/137개**다.
  이는 **선별 전** 수치다. 테스트도 이를 `command support only`라고 명시한다.
- 실제 lifted/contact mask를 적용한 288개 전부의 수치는 제공된 70초 prefix와 이번66초 팬 검사로 만들 수 없다.
  70초 prefix는 원래 네 크기의 step 구간에 도달하기 전이며, 이전 hover/v88의 지지를 HIGH로 승계할 수 없다.
- 사용자 범위는 짧은 무렌더 검사다. 전체 motion 구간 끝까지490 SIM초의 prefix 재생 허용 여부를 별도로 요청했으나
  이 보고서 작성 시 답이 없어 긴 재생은 시작하지 않았다. **`command_support.json`의 post_filter_windows는 null**로 남겼다.
- 완료 조건: 사전 고정된 후보의 motion prefix/수집 결과에서, 로봇·축·부호·수준·horizon별 전체 창에
  frozen loaded gate를 적용한 생존 개수와 제외 사유를 보고한다. 낮은 .001/.002/.004 수준도 관측 후 정지로 분류한다.
  입력 rank3과 명령 지지는 13모수 Jacobian rank·내부해·정지/두 램프/포화 지지의 대체물이 아니다.
  B″ 임계값을 새 결과에 맞춰 변경하지 않는다.

## 요청 항목별 확인

### 1. 이전 P1과 CI 관련 로컬 회귀

`tests/test_simulation_workflow_manager.py:188`의 카탈로그48개와 `:251`의 v92 plan 입력을 확인했다.
두 기존 실패 테스트를 포함해 아래5파일을 **한 번의 pytest 묶음**으로 실행했다.

| 파일 | 결과 |
|---|---:|
| `test_zone_final_pair_loaded.py` | 27 passed |
| `test_zone_final_pair_fast.py` | 20 passed |
| `test_final_pair_fast_guard.py` | 31 passed |
| `test_agent_sim_slots.py` | 27 passed |
| `test_simulation_workflow_manager.py` | 17 passed, 1 failed |

합계 **122 passed, 1 failed in 153.26s**. 로컬 실패는 `test_parent_exit_cleans_background_child`의
`subprocess.run(['ps', ...])`에 대한 sandbox `PermissionError`다. 변경 범위 밖 환경 제약이며
그 테스트가 검증하려던 자식 PID25521은 이후 존재하지 않음을 확인했다. 이 실패를 통과로 바꾸지 않았다.
위 P1의 별도 동시 진입 재검사는 원격 CI 실패가 나타난 뒤에만 수행했다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
  tests/test_zone_final_pair_loaded.py tests/test_zone_final_pair_fast.py \
  tests/test_final_pair_fast_guard.py tests/test_agent_sim_slots.py \
  tests/test_simulation_workflow_manager.py
```

`git diff --check`, `bash -n collect.sh`, CI frozen fixture3개 검사도 통과했다.
CI workflow·제외 목록을 바꾸거나 실패 테스트를 제외하지 않았다.

### 2. D1/D2 — HIGH 측정, 바닥 자세 분리, 보존과 번호 개정

`harness/zone_final_pair_loaded_schedule.py:52–91,110–120`에서 모든 motion/pair segment와
7개 camera window가 **HIGH `896,2035,1894,1500`**다. 발행 servo state를 직접 누적하는 회귀도 통과했다.
24 mm 바닥은 초기 파지/들기 준비와 측정 종료 후 하강/방출에만 쓰인다.
중간110/130 mm와 기존 hover는 준비용이다. 마지막 loaded 측정 이후700초에만 내린다.

카메라 위치/FOV·외형·물리·접촉·render profile·weld·샘플링·인터록 보호파일29개를
등록 해시 및 a9481446 실제 바이트와 대조해 모두 일치했다.
v88/v90/v91 등록, 학생 `zone_final_pair_vision/skill`, r4/r5 기준·기존 fitter가 그대로다.
본 범위에서 변경된20파일 목록에도 기존 물리/카메라/fast guard 변경은 없다.

이번 새 무렌더 산출물 중 `scene.xml`, `scene.json`, `eval_only/applied.json`,
`eval_only/render.json`, `eval_only/setup.json`, `inputs/static_map.json` **6개 바이트를 허용된 v88 r8 loaded raw와 대조해 전부 일치**했다.
scene XML SHA-256은 `24a4c1d00b01e50f2a3c53d503459dd85d08c420056f828ab792e642c5a063de`다.
640×480, `floor_light_v1`, `cargo_noslip_v1`, masterpi_v3, 실제 timestep .00025초,
pose/command .05초·RGB .2초, weld OFF·초음파 OFF와 v91 abort-only FastGuard를 유지한다.
v91 비교는 소스/계약으로만 했으며 **v91 heldout raw는 읽지 않았다**.

**번호 개정은 조정자의 ‘본 수집 전 개정’ 범위에서 타당하다.** 06:31:27 UTC의 metadata inventory는
기본 `outputs/`, 기본/review worktree `experiments/`의28,224개 실행 관련 metadata를 확인했고 오류0이었다.
금지된 `final-pair-v91-heldout-*`는 진입 전에 제외했으며 symlink를 따라가지 않았다.
v92의 본 수집 `plan execution_started=true`/완료·실패 `result`는 발견하지 못했다.
찾은 v92 bundle은 이미 공개된 `v92-loaded-d1-d4-20261003/headless-revised/bundle.json` 하나이며,
70초 무렌더 prefix의 DRAFT_UNSEALED 기록이다. **‘v92 관련 기록 자체가 전혀 없다’는 문자 그대로의 주장은 틀리다.**
짧은 진단과 본 수집·적합 결과를 구분한 제한된 결론이다. 이름이 바뀌거나 metadata가 없는 모든 바이트의 부재까지 증명하지 않는다.
이번 검토가 이후 만든 execute=false 계획과66초 팬 진단도 본 수집으로 세지 않는다.

### 3. D3/D4 — B″ 근거와 바이트

B/B′ 원본 SHA-256은 각각
`74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`,
`3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33`이며 이전과 같다.
B″에서 B′의 기존 key를 비교하면 바뀐 것은 schema/criterion/frozen_at/freeze_scope metadata4개뿐이다.
새로 더한 것은 parent hash·두 변경 설명·loaded motion bounds·loaded camera selection이다.
잔차/coverage/최소 표본/PRBS split/loaded contact/pair/promotion 등 기존 판정은 동일하다.

탐색 근거 `v88_c0_basis.json`은 f2fc0cc3의 `motion.json`과 해시가 같고,
전진/옆32개 step row가 정확히 복사되어 있으며 raw provenance도 같다.
추가로 **허용된 v88 r8 raw의 pose에서32개 끝5초 속도를 독립 재계산**했다.
각 tail 시작 자세 기준 좌표계로 계산했고 기록값과 최대 오차1e-10 미만이다.
`.006`에서 전진은2.536432–2.541771 mm/s, 옆은0.076775–0.173733 mm/s다.

`.006` 아래 비영 입력을 관측하지 않았으므로 양수 deadband 하한을 측정했다고 주장할 수 없다.
**0은 비음수 c0의 탐색영역 하한**이라는 설명은 타당하다. 임의의 v92 통과용 수치를 끼워 넣은 흔적은 없으며,
v88은 명시적으로 탐색자료다. HIGH의 실제 c0 추정·신뢰하한이나 두 자세의 동역학 동일성 주장이 아니다.
회전 하한 .006, c0 상한 .015, u1 .025–.04, 초기값, 내부해 거리1e-6,
관측된 양수 정지·두 램프·포화 지지는 유지한다. 기존 fitter를 그대로 사용해 c0만 풀어 통과시키는 변경은 이 범위에 없다.
D5 새 분석기가 이 의미를 구현해야 하며 후속 구현의 수락은 본 검토 범위 밖이다.

loaded camera는 마지막 arm/look 변화 또는 비영 lease 종료 후8초 이상 준비하고,
**8초 반열린 측정창7개**만 받는다. fine의1초, 최소5프레임,1 mm/0.1° 및 pan잔차 gate는 그대로다.
D2 HIGH 전용 loader 계약은 별도이며 바닥 loaded 보정을 자동 채운 것으로 간주하지 않는다.

| 댓글5966310640의 항목 | 실제 SHA-256 / 크기 |
|---|---|
| B″ | `5f7d8905c49625a7125647eaf713575e4e659ca658274b8734fd2a4952da4d4a` |
| 일정 JSON | `b6ebf872ac1f47bb6f13c336ca49c74343ffe592c5cb1bbd0916449a6208bcbe` / 5,051,841 bytes |
| gzip | `47b0e1f3fc52ed94fb737e5b7a90c1f75035c74d198b8bcce3036890fc9d8b62` / 62,247 bytes |

세 해시 모두 일치했다. gzip 해제 바이트와 `schedule_bytes()` 생성 바이트가 같으며 **22,302명령**이다.
이전 일정의 해시/기록도 보존되어 있다.

### 4. 팬 접촉 재현, FastGuard, 조정자 명령

커밋된 `probe_headless.py --mode posture`를 **새로66 SIM초 실행**했다.
HIGH 도달과1500→1480→1500→1520→1500 팬 순서는 사전 고정이며, 측정값은 출력에만 쓴다.
이 진단은 본 일정의506–570초 누적 운동 상태 재현이 아니므로 두 결과를 혼동하지 않는다.

| 범위 | 독립 결과 |
|---|---|
| 전체 | 1,321표본: lifted1,239, 초기 not_lifted82 |
| [8,66)초 | **1,160/1,160** 상승·네 집게 접촉·외부 지지 없음·weld 없음 |
| HIGH 팬 구간[34,66)초 | **640/640** 유효; 최소 빔 바닥114.814765 mm |
| HIGH 기하[32,40,48,56,64]초 | 두 로봇 모두 경계90열; 실제 RGB 검출 아님 |
| 명령/렌더/모델 | 52명령 / 렌더0 / 외부 모델 호출0 |

frozen `loaded_mask`로 raw를 다시 분류해 같은 카운트를 확인했다. 작성자 수치나 R1과 합산하지 않았다.
부하 평균 시작 `[19.11328125,15.8701171875,15.8173828125]`, 종료 `[17.78857421875,16.64697265625,16.123046875]`.
검토자의 `sim-codex-review361-r2`만 사용했고 종료 후 `concurrent_holders=[]`, `physics_holder=null`을 확인했다.
기존 실행 프로세스에는 종료/변경 신호를 보내지 않았다.

`collect.sh`와 실제 execute 없는 표준 CLI/runner 계획은 올바른 v92/3.4.0,
`execution_started=false`, `lock_mode=sim_slot`, `sim-codex-v92-loaded`,720+5초를 표시한다.
HEAD/branch/clean tree/새 출력·10GiB/owner·coordinator PID/자식 종료 후 슬롯 해제와
상속된 v91 FastGuard 경로는 유지한다. 단, 위 P1의 기존 동시 metadata 오류는 남는다.

```bash
cd /Users/changmin/projects/ugrp-wt/v92-loaded
V92_SOURCE_SHA=9583d3cb7ef2d6f30a5d47fa73ec92964c94eeb0 \
  bash experiments/2026-10-03-v92-loaded-schedule/collect.sh
```

이는 **정확히 이 SHA가 HEAD일 때의 구문·경로 확인**이며 실행하지 않았다.
D5 커밋이 추가된 HEAD에서 이 명령은 SHA 검사로 거부되어야 정상이다.
수집 전에 최종 실행 소스를 다시 고정하고 **B″·일정·새 조립기 해시를 #219에 함께 공개**해야 한다.
D2 새 loader 계약·D1 새 학생 번들과 실제 RGB/전체720초/적합/학생 인수는 별도다.

## 증거와 전달

시작에 fetch했다. 검토 branch `codex/review-361`에서 대상 SHA를 병합해 고정한 실행 소스는
`b9cc9f4dcd9a64fe2880e059a79a0aecfd63fe06`이다. 이 SHA와9583d3cb의 tree 차이는 기존
`REVIEW_361.md` 한 파일뿐이며 **실행·테스트·설정 바이트는 정확히 같다**. 구현 파일은 수정하지 않았다.
기본 checkout은 당시 main/origin/main `db37ee4aae073dbd1c2d1a206b31dd64412fbea5`로 같았다.
PR 병합·기본 checkout 갱신은 수행하지 않았다.

raw·로그·hash 대조·CI·계획·선별 전288행은 로컬
`/Users/changmin/projects/ugrp/outputs/review-361-r2-9583d3cb-20261003/`에 보존한다.
핵심 파일: `static_audit.json`, `record_inventory.json`, `v88_basis_check.json`,
`command_support.json`, `tests.xml`, `ci_checks_final.json`, `ci_shard6.log`,
`slot_race_recheck.json`, `pan_check.json`, `v88_scene_comparison.json`.
팬 raw manifest SHA-256은 `141681da34be355b0b1416d624e4cc79178b1a714be000eaa8e5e1fd2669521d`다.
리뷰 문서는 GitHub에 보존하되 raw 전체의 원격 백업을 주장하지 않는다. Google Drive 작업은 없다.

새 native TensorBoard snapshot `1003-v92-review361-r2/high-pan`을 공용 logdir에 추가했다.
원본·기존 snapshot 보존,9개 scalar의 실제 EventAccumulator/서버 API 재로딩·값 일치,
새 영상0개를 확인했다. 기존 서버를 변경하지 않았다.
Chrome 강의 기존 검토 탭에서 R2/이전 posture 두 run을 구분해 선택하고90/0/1160 카드값을 확인했다.
HParams 기본4열을 다시 적용했으며 새 행 개별 UI 확인과 나머지 카드 개별 UI 값 확인은 남았다
(모든 값은 이벤트/API 대조 완료). 운반 성공·wall 시간·모델 응답 시간을 만들지 않았다.

[검토 대시보드](http://127.0.0.1:6006/?runFilter=%5E1003-v92-%28review361-r2%2Fhigh-pan%7Creview361%2Fposture%29%24&scalarSmoothing=0#timeseries).
정확한 pin 링크·표시 범위는 `tensorboard_verification.json`과 공용 view의 `v92_review361_r2_20261003` 키에 있다.

**병합 전: CI 경쟁 오류 해소·최종 SHA 필수 검사 통과. 요청한 물리 지지 검사: HIGH288개 선별 후 증거 보완.**
후속 assembler·loader·수집·학생 인수에는 이 리뷰를 자동 승계하지 않는다.
