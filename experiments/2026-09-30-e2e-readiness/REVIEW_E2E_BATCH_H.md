# E2E Batch H — 독립 재현성 검토, 2026-10-01

검토자: Codex. 작성자의 검증 수치를 대신 인용하지 않고 아래 PR tree에서 다시 실행했다.
물리 step·렌더·모델 호출 0, 호스트 잠금 미사용(#328). 구현/봉인/workflow 파일은 수정하지 않았다.
이 기록과 `tests/test_review_e2e_batch_h.py`만 검토 브랜치에 추가한다.

| PR | 검토한 정확한 HEAD | 판정 | 남은 수정 |
|---|---|---|---|
| #333 T08b | `cb0735efcd79ebaefd511eb7cd123979512dd0ed` | **MERGE AFTER FIXES** | P1 H333-1: 실제 발행 PWM/채널 계약 불일치. #315 선행 병합 및 최종 통합본 검사도 필요 |
| #334 T05 | `a4a0bacb51d46d69c1107277c4d11e67b60e4693` | **MERGE AFTER FIXES** | P1 H334-1: 주행 이력의 시간 필드 불일치. P2 H334-2: 같은 촬영을 두 번 확인으로 인정 |

판정은 후보 코드의 병합 검토다. T08b 실제 출발→정렬, T05 실제 접근→C 방출,
4조건 물리 비교, E2E/실물 성공의 승인이 아니다. 두 PR 모두 현재 draft다.

## 기준·재현 방법

- 기준 main 및 검토 브랜치 시작: `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`.
  기본 checkout은 main/clean이며 같은 HEAD였다. 기본 checkout과 다른 작업은 변경하지 않았다.
- `AGENTS.md`, `README.md`, `docs/current_status.md`, `CONTRIBUTING.md`,
  `experiments/2026-09-30-scenario-capabilities/REQUIREMENTS.md`와 `TASKS.md`를 기준으로 삼았다.
  PR 본문/댓글/CI, 두 후보의 README·PHYSICS_HANDOFF·변이 스크립트와 관련 의존성도 확인했다.
- `git fetch origin`, 열린 PR 목록과 정확한 HEAD 확인 후 각각
  `git archive origin/codex/beam-approach | tar -x -C <scratch>` 및
  `git archive origin/codex/tile-skill | tar -x -C <scratch>`로 추출했다.
  `git worktree add`는 사용하지 않았다.
- historical provenance 검사는 Git 객체가 필요하므로 추출 폴더에서 `git init -q` 후
  `.git/objects/info/alternates`를 원본 `.git/objects`로 연결하고 `.git/HEAD`에 해당 PR SHA를 썼다.
  따라서 과거 blob 조회와 HEAD ancestry도 정확한 PR을 가리키며 main 소스로 대체하지 않았다.
- 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python` 사용:
  Python 3.12.13, pytest 9.1.1, NumPy 2.5.2, OpenCV 5.0.0.
  `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`.
  baseline/관련 검사/추가 반례는 #333의 `offline_guard`를 pytest plugin으로 사용해
  MuJoCo·모델 SDK import와 네트워크 연결을 거부했다. 작성자의 mutation 스크립트도 직접 재실행했다.
- 추가 반례는 기본적으로 위 SHA의 필요한 Python blob만 `git show`로 읽는다.
  현재 checkout의 공통 의존성은 이번 후보와 같은 bytes인 기존 코드다.
  수정본 검토는 `UGRP_REVIEW_H_PR333_ROOT`, `UGRP_REVIEW_H_PR334_ROOT`에 새 PR tree 경로를
  지정한다. import/설정 오류는 예상 실패로 삼지 않고, 지적한 assertion만 `xfail(strict=True)`다.

```sh
git fetch origin codex/beam-approach codex/tile-skill
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest \
  tests/test_review_e2e_batch_h.py -q -rx
# 3 xfailed; --runxfail을 더하면 아래 원인으로 3 failed, 수집 오류 0
```

## 지적 한 묶음

### P1 H333-1 — 실제 PWM 이력을 거절하여 연속 인계를 시작할 수 없음

위치: **`harness/beam_approach.py:69`, `:79`, `:113`** (#333 HEAD).

`OwnApproachMemory`는 채널 1–6 모두와 pulse 0–1000을 요구하고,
`BeamApproach.__init__`의 `search_servo`도 같은 범위를 요구한다.
그러나 실제 공통 `harness/owncam_drive.py:44`의 `SEARCH_POSE`는
`{1:2000, 3:740, 4:2320, 5:1320, 6:1500}`이며,
`harness/visual_arm.py:27`의 안전 PWM 범위는 500–2500이다.
자기 명령을 받는 `OwnCamPoseSource.on_command`도 이 PWM을 그대로 보존한다.

반례: 이 표준 `initial_servo_command` 한 행을 그대로 전달하면
**`BAD_ISSUED_SERVO`**가 나서 memory 생성부터 실패한다.
range만 고쳐도 불필요한 channel 2 요구와 생성자의 같은 guard가 남는다.
기존 양성 fixture는 `{1:500,2:400,3:300,4:400,5:500,6:500}`로 이 문제를 가린다.
실제 열린 집게의 2000을 500처럼 바꿔 전달하면 동일 provider/servo/history 인계라는
T08b 계약을 충족하지 못한다. 열린 집게 기준 400 역시 native PWM 기준으로 맞춰야 한다.

수정 요구: native 명령의 채널·PWM·열림 기준을 입력과 출력 전체에서 일치시키고,
표준 자기 이력으로 생성→접근→인계하는 양성 회귀를 추가한다. 다른 단위를 쓰려면
실제 port/provider까지 연결된 명시적 변환 및 연속 이력 검증이 있어야 한다.

반례: `test_beam_accepts_native_issued_search_history_without_rescaling`.

### P1 H334-1 — native 주행 이력의 `duration_s`를 읽지 못함

위치: **`harness/tile_own_skill.py:134–137`** (#334 HEAD).

`on_command`는 발행 완료한 자기 명령을 받는 API인데 mecanum에서 `duration`을 요구한다.
실제 `harness/zone_own_team_host.py:409–412`의 명령 이력과
`harness/owncam_localizer.py:187`의 소비 계약은 **`duration_s`**다.
상위 action의 `duration`과 native 발행 이력의 필드가 혼동됐다.

반례: 기존 양성 Port로 정상 `holding`까지 진행한 뒤
`{robot_id:'r1', t:4.4, kind:'mecanum', forward:.05, left:0., turn:0., duration_s:.1}`
형식의 native 행을 주면 **`TILE_MOTION_COMMAND_INVALID`**가 발생한다
(반례에서 시각은 실제 holding 도달 시각을 사용한다).
따라서 문서가 요구한 자기 navigation 연결은 첫 운반 명령부터 그대로 사용할 수 없다.
기존 성공 검사는 holding→release로 바로 넘어가며, base-motion 반례도 `duration`을 만들어 준다.

수정 요구: canonical 발행 이력 필드를 읽고, 실제 navigation/port 형식으로
운반 중 `motion_until`과 새 관측 대기를 검사한다. 별도 adapter가 필드를 바꾸는 설계라면
그 변환을 구현·명시·검증해야 하며 현재처럼 연결 완료로 추정해서는 안 된다.

반례: `test_tile_consumes_native_navigation_command_history`.

### P2 H334-2 — 촬영 시각이 같은 중복 영상으로 holding 확정

위치: **`harness/tile_own_skill.py:157–158`, `:263–271`** (#334 HEAD).

frame ID 증가는 요구하지만 촬영 시각은 `t < self.frame_time`만 거절한다.
`verify_hold`에서 첫 양성 촬영을 센 직후 **같은 JPEG·같은 촬영 시각·새 ID**를 주면
그것을 두 번째 확인으로 세어 `holding` 및 `carry_permitted=True`가 된다.
재현 시각은 **4.2 SIM초**이며 추가 시간 진행이나 새로운 촬영은 없다.
T05의 두 새 영상 확인은 번호 변경만으로 우회되면 안 된다.

수정 요구: 확인에 쓰는 capture identity/시각을 엄격히 증가시키거나 중복 capture를
count하지 않도록 하고 holding과 release 양쪽에 같은 재전달 반례를 둔다.
이 반례는 fake RGB 판정으로 제어기의 시간 계약을 분리 검사한 것이며 인식 정확도 측정이 아니다.

반례: `test_tile_same_capture_cannot_supply_two_holding_confirmations`.

## 독립 실행 결과

| PR / 검사 묶음 | 직접 재실행 결과 |
|---|---|
| #333 신규 T08b + 선행 T08a + 필수 source 두 파일 | **183 passed** = 63 + 64 + 22 + 34 |
| #333 기존 approach / passage / fixed-status 회귀 | **72 passed** = 12 + 44 + 16 |
| #334 신규 tile + 필수 source 두 파일 | **121 passed** = 65 + 22 + 34 |
| #334 기존 perception v3 / v3.1 / own executor 오프라인 회귀 | **167 passed, 1 deselected** |
| 추가 반례 기본 실행 | **3 strict xfailed**, 수집 오류 0 |
| 추가 반례 `--runxfail` | **3 failed**, 정확히 위 세 assertion, 수집 오류 0 |
| 임시 사본에서 지적한 해당 조건만 변경한 원인 분리 검사 | **3 passed** (`--runxfail`); 후보 소스/PR에 수정 적용하지 않음 |

PR별 서로 다른 파일의 합은 #333 **255**, #334 **288**이다. 양쪽에 공통 source 검사 56개가
포함되므로 이를 서로 독립된 로봇 trial 분모로 합산하지 않는다. 추가 반례는 이 통과 합계에 넣지 않는다.

정확한 baseline 파일:

- #333: `tests/test_pair_navigation_beam_approach.py`,
  `tests/test_pair_navigation_beam_initial_pose_plan.py`,
  `tests/test_zone_pair_registered_source.py`, `tests/test_zone_study_source_pinning.py`.
- #334: `tests/test_zone_own_executor_tile.py` 및 같은 source 검사 두 파일.
- #333 관련: `tests/test_pair_owncam_approach.py`, `tests/test_pair_passage_plan.py`, `tests/test_zone_pair_status.py`.
- #334 관련: `tests/test_zone_own_perception_v3.py`, `tests/test_zone_own_perception_v3_1.py`,
  `tests/test_zone_own_executor.py`; native host 물리 테스트
  `test_team_host_feeds_each_executor_only_its_own_camera` 한 건은 명시적으로 제외했다.

범위 선택 중 최초 #334 관련 검사에 `tests/test_visual_arm_v3.py`를 포함한 시도는
MuJoCo import를 offline guard가 막아 **collection error 1 / exit 2**로 중단됐다.
물리 함수는 실행되지 않았다. 이 로그도 보존했고 해당 물리 의존 파일을 빼고 위 오프라인
회귀를 실행했다. 이를 후보 코드 실패나 통과로 세지 않았다.

### 제거 변이 재현

#333의 `experiments/2026-09-30-beam-approach/mutation_check.py`를 재실행:
원본 **63 passed**, 변이 **8/8 검출**, 모두 pytest exit 1 / collection error 0.

| 제거/변조 | 실패한 테스트 수 |
|---|---:|
| navigation 제거 | 25 |
| pose gate 제거 | 8 |
| relative alignment 제거 | 17 |
| 인계 시 posterior 재초기화 | 6 |
| command guard 제거 | 10 |
| JPEG hash 검사 제거 | 1 |
| 배달된 abort 처리 제거 | 1 |
| SIM cap 경계 완화 | 1 |

#334의 `experiments/2026-09-30-t05-tile/mutation_check.py`도 재실행해
**6/6 검출**: role guard 제거, 상자 높이 대입, holding 확인 제거,
release 근거 제거, own-camera 검사 제거, background boundary 제거.
모두 assertion 실패에 의한 exit 1이며 수집 오류를 검출로 세지 않았다.
변이는 테스트가 일부 논리를 검사함을 보이며, 위 누락된 native 경계까지 보장하지 않는다.

## 요구사항·입력 경계·봉인·인계 판단

| 점검 | #333 T08b | #334 T05 |
|---|---|---|
| TASKS 범위 | 남/북 heading·prestation·불확실/무효 영상·교차 거절·상대 정렬·동일 memory 인계는 fake로 확인. 실제 native 이력은 H333-1 때문에 연결 불가 | west-only 제한·25 g/치수·7 mm IK 및 범위 거절·holding/release·심판과 완료 분리는 구현. native 운반 H334-1 및 확인 H334-2 수정 필요 |
| 입력 경계 | 직접 입력은 own JPEG, 정적 map/sheet/order, 자기 이력, 배달된 STATUS. private envelope 변화 비간섭 확인. 주입되는 provider/observer/guard의 실제 어댑터는 아직 미검증 | own JPEG와 issued PWM, 공개 order/role만 사용. private eval/partner/actuator 필드 변화 비간섭 확인. 정적 v3 FK/IK는 측정 관절이나 GT가 아님 |
| 네 조건 동등성 | condition은 allowlist/audit에만 사용; 같은 CONFIG/센서/기억/STATUS. 실제 provider/observer/guard 동일 배치는 인수 시 hash 검증 필요 | condition은 allowlist에만 사용; 동일 제어/vision/센서/기억. 네 조건과 private 변형의 전체 fake trace 동일 |
| sealed/pinned bytes | PR tree에서 두 필수 파일 **22+34 passed**, v6e **85/85 SHA 동일** | PR tree에서 두 필수 파일 **22+34 passed**, v6e **85/85 SHA 동일** |
| workflow | `origin/main` 대비 `.github/workflows` **diff 0** | 동일 **diff 0** |
| 보존 | maps/configs/sim, 두 필수 source 테스트, `scripts/run_ci_tests.py` PR 변경 없음 | 동일 |
| 물리 인계 | 원본 s1/s3/s6 × 정상/무효 영상 2 × 900 = **5,400 SIM초**, spawn부터 staging/팔 전이 포함. 정렬/접촉/오차 별도 판정; 배송 success null | C로 고정한 정상/미파지 2 × 900 = **1,800 SIM초**, 전체 episode/staging 포함. west/원본 tile pose/actuator fault/eval-only/심판 기준 분리 |
| 남은 연결 | 최종 v3 observer/provider/full-body guard·표준 adapter. #315 HEAD `86847071f0332c23e5858c93607e2b0bbeb6dc98`는 OPEN/draft, 실제 merge SHA 없음 | native adapter·자기 navigation·최종 RGB/접촉 보정. B 목적지와 네 조건 물리 비교는 별도 |

두 인계 문서는 구체적인 미실행 cap이며 물리 성공을 주장하지 않는다.
시험 결과가 없으므로 TensorBoard에 로봇 성공률 snapshot을 새로 만들지 않았다.
실제 후속 6셀/2셀 결과가 생기면 실패·미도달을 포함한 raw hash/영상과 native TensorBoard 검증이 필요하다.

workflow tree object는 main/두 PR 모두 `d16776ce7b241a0ab49132f65bfa6a5ac17895e7`이다.
#333에 포함된 T08a 구현 bytes는 #315와 같으며, CI 파일 대신 기존 glob에 들어가는
bridge를 사용하도록 T08a의 수집 assertion만 바뀌었다. T08a 64개가 실제 수집·통과했다.

## GitHub CI의 별도 상태

- #333: 같은 SHA에서 **32 success / 1 cancelled**. 재시도 job
  [109973860359](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36733359971/job/109973860359)의
  API annotation은 `The job has exceeded the maximum execution time of 10m0s`다.
  설치 단계의 시간 제한을 제어 논리 실패로 분류하지 않는다. 그러나 해당 job의 후속 검증은
  완료되지 않았으므로 CI 전체 통과라고도 하지 않는다. #332가 반영된 현 main과 workflow bytes는 같다.
- #334: 같은 SHA에서 **33/33 success**.
- H333-1/H334-1/H334-2의 수정 후 관련 검사·반례·source pin 및 최종 CI를 다시 확인해야 한다.
  #333은 #315의 최종 병합본도 반영해야 한다. 이번 검토에서 CI 설정 수정·취소·재실행·병합은 하지 않았다.

## 원본 기록

로컬 raw: `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-h-20261001/`.
`evidence.json`에 PR/CI 조회 원본, 파일별 SHA-256, baseline/관련 검사 JUnit 집계,
변이 결과, 후보 bytes 불변 확인을 보존했다. 원인 분리용 작은 patch도 이 위치에만 남긴다.
이 로컬 자료를 원격 백업이라고 표현하지 않는다. UGRP 예외에 따라 Drive는 사용하지 않았다.

| 파일 | SHA-256 |
|---|---|
| `pr333-baseline.log` | `bf470c85719f48f9b9330c8aa745b20ba2f5c9af5304772c908364d4b279edf9` |
| `pr333-related.log` | `a92d252637076e140c59ac7428b1d920bc356eae4762bc5eb274ead6f9557d3e` |
| `pr334-baseline.log` | `cd53dbb8723fed0a21e188911fde8d8e4ff11787b9bdf46a81da8fa8ca70890a` |
| `pr334-related-offline.log` | `f20784cf6d1a1cce5d01b581c4b00396ff8f6009abc2a6d185e54eb3328c2c8c` |
| `counterexamples-unmasked.log` | `0c78a0ab9a300e1930a55cbe9ac4b529bbbd9a1b0460c7a416e0139e853653c5` |
| `pr333-mutations/results.json` | `9100041b76cc1d40dcb4a0e4cd33fa91f83bf07f88190f616c664d28cedef376` |
| `pr334-mutations/mutation.json` | `a2831b63f09a96f3ed09aa512ed24f02c63317b29e8ec350674f098858585073` |
| `evidence.json` | `1237bff645a86c9f33fa8e9237573473165657f2d782431beb2041f86017ef24` |
| `final-verification.json` | `32b77b5ce32e759ad5e5835efbc0479901561bce0fa918d7778da681ea7e4a95` |

최종 반례 파일 SHA-256은 `415edd801fa5bc923119aa76a0790484916394d6e0a79ffb641f8c8ea81885fc`다.
최종 재실행도 3 xfailed / 원본 unmasked 3 failed / 원인 분리 사본 3 passed였으며
`final-verification.json`에 각 로그 해시를 연결했다.

이 한 묶음의 지적을 각 PR에 한국어 댓글 한 건으로 전달한다.
원본 실험/성공 번들/raw는 보존했다. 검토용 `/private/tmp` 추출 폴더 두 개와 그 안의
원인 분리 사본은 삭제하고 부재를 확인했다(`cleanup.json`).
