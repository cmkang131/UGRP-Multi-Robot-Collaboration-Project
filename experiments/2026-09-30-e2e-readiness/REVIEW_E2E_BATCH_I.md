# E2E Batch I 독립 검토 — 2026-10-01

검토자 Codex. 기준 main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`.
AGENTS.md, README.md, current_status.md, CONTRIBUTING.md와 P09의
REQUIREMENTS.md / TASKS.md를 대조했다. **물리·MuJoCo·렌더·모델 호출 0회**.
아래 판정은 독립 모듈의 오프라인 구현 범위이며 물리 인수나 E2E 지원 승인이 아니다.
검토 대상 PR을 수정하거나 병합하지 않았다.

| PR / 검토한 전체 SHA | 판정 | 이유 |
|---|---|---|
| #330 `f5d5af557525c9aa6d7fff043d933d2fc2c67967` | **MERGE AFTER FIXES** | 오래된 촬영분도 새 순번이면 주행에 사용한다(I-330-1). |
| #331 `25beb0694027b2d6d8db646a043de51fabc479dc` | **MERGE** | 이번 범위에서 차단 결함 없음. 선행 #310 병합/통합과 최신 base 검증은 병합 담당자가 별도로 확인해야 한다. |
| #335 `e9665534782811870482086768d2c88d681fd865` | **MERGE AFTER FIXES** | 안전 검사한 팔 경로와 실제 발행 경로가 다르다(I-335-1). |

## 한 묶음의 지적

### I-330-1 / P1 — 촬영 시각이 없어 지연된 clear 영상으로 다시 주행한다

- 위치: [`harness/zone_observed_door_reroute.py:35`](https://github.com/kcm0127-dotcom/ugrp/blob/f5d5af557525c9aa6d7fff043d933d2fc2c67967/harness/zone_observed_door_reroute.py#L35),
  [250](https://github.com/kcm0127-dotcom/ugrp/blob/f5d5af557525c9aa6d7fff043d933d2fc2c67967/harness/zone_observed_door_reroute.py#L250),
  [307](https://github.com/kcm0127-dotcom/ugrp/blob/f5d5af557525c9aa6d7fff043d933d2fc2c67967/harness/zone_observed_door_reroute.py#L307).
- 정상 첫 프레임을 t=0에 처리한다. t=.01에 촬영하고 아직 소비하지 않은
  sequence=1의 clear 프레임이 t=1에 도착하면 `RUNNING`, 새 navigation 호출 1회,
  stop 호출 0회다. 순번 재사용이나 해시 위조가 필요하지 않다.
- `OwnFrame`에 capture time이 없고 observer에도 현재 시간이 전달되지 않는다.
  새 순번과 이미지 해시만으로 990 ms 지연과 새 촬영을 구별할 수 없다.
  하위 navigation도 동일한 timestamp 없는 프레임을 받으므로 이 API만으로는
  과거 clear/pose를 현재 안전 관측으로 쓰는 것을 막을 수 없다.
- T09b의 관측 뒤 우회·정지와 README의 fresh own RGB 계약에 빈틈이 있다.
  촬영 시각/유효기간을 입력 계약에 넣고 stale/future capture를 navigation 전에
  정지시켜야 한다. 큐 취소 뒤 재출발에도 같은 기준을 적용하고 네 조건에 고정한다.
  실제 장애물 충돌을 실행하거나 관측했다는 뜻은 아니다.
- 재현: `test_t09b_delayed_own_capture_cannot_issue_a_new_drive`.

### I-335-1 / P1 — 60 PWM 경로 검사 후 다른 40 PWM 자세를 발행한다

- 위치: [`harness/zone_can_skill.py:160`](https://github.com/kcm0127-dotcom/ugrp/blob/e9665534782811870482086768d2c88d681fd865/harness/zone_can_skill.py#L160).
  의존하는 기존 [`harness/zone_own_guards.py:298`](https://github.com/kcm0127-dotcom/ugrp/blob/e9665534782811870482086768d2c88d681fd865/harness/zone_own_guards.py#L298)는 관절당 60 PWM 이동을 샘플링한다.
- `_arm_to`는 전체 목표까지의 **60 PWM씩 움직이는 경로**를 검사한 뒤
  관절별로 **40 PWM씩** 움직인다. 변화량이 작은 관절은 먼저 목표에 도달하여
  두 경로의 중간 관절 조합이 달라진다. 단순히 더 작은 속도의 같은 경로가 아니다.
- 반례의 자기 발행 이력은 `{1:2000,3:1164,4:2321,5:2080,6:1174}`,
  접근 목표는 기존 `VIEWS[0]`이다. 정적 post의 중심
  `(.27446602791450786,-.11115416383666454)`, half extent `(.0001,.0001)`,
  높이 `.025 m`, 자기 추정 `(0,0,0)`, 표준편차 `(.002 m,.002 rad)`를 사용한다.
  초기 팔 여유 **+2.757 mm**, 차체 여유 **+136.094 mm**로 시작한다.
- 검사 경로의 최소 여유는 **+0.933 mm**라 통과하지만 실제 발행 자세
  `{1:2000,3:1124,4:2300,5:2040,6:1214}`의 여유는 **−0.389 mm**다.
  실제 `step()`이 이 명령을 반환한다. 가짜 guard로 판정을 강제하지 않았다.
  이 수치는 정적 guard의 보수 여유이며 실제 접촉/충돌 측정이 아니다.
- 발행할 다음 PWM을 먼저 계산하고 **그 명령의 실제 동시 전이**를 검사하거나,
  can 전용 guard와 발행기의 증분 규칙을 하나로 맞춰야 한다.
  기존 봉인된 공용 guard를 바꿔 과거 소스 핀을 깨면 안 된다.
- 재현: `test_t04_issued_arm_increment_passes_the_same_static_sweep`.

## TASKS.md 및 입력 경계

### #330 / T09b

- 직접 관측/실제 수신 뒤 narrow→wide, no_comm 선행 우회 금지, 두 문 모두 차단,
  편대 한쪽 실패·heartbeat·기존 큐 취소 검사는 재현됐다. 오래된 영상 반례는 별도다.
- `Observer`는 자기 RGB, 정적 지도 사본, 자기 발행 명령만 받는다. 블록 믿음은
  해당 RGB 해시 또는 실제 전달 메시지 ID로 기록한다. private event/pose/심판을
  읽는 경로는 찾지 못했다. 기존 enum endpoint는 전달 상태만 포함한다.
- 네 조건은 같은 controller/map/prior/navigation/version을 쓰고 차이는 상류 inbox다.
  실행된 통신 수신 검사와 동일 입력의 명령/해시 동등성 검사를 확인했다.
- 선행 #314 `994b269d97d05dd2159c1a78f2b9eae9955790f9`는 후보의 ancestor이며
  `zone_static_door_routes.py` 바이트가 같다. #314는 OPEN/DRAFT, main 병합 SHA 없음.
- 실제 Observer/Navigation 연결은 미완료다. pair 우회는 기존 job을 abort하고
  새 일치 제출을 요구한다. 이 PR의 단위검사로 pair 재출발/운반을 완료했다고 볼 수 없다.

### #331 / T10b

- 진입·후퇴·bay 대기·재진입, 동/서 방향, full footprint 출구 확인을 검사했다.
  한쪽 이탈/holding 상실/heartbeat 만료/대기 timeout/반복 대치/불가능 경로는
  안전 종료 또는 거절한다. waypoint 도달을 배달 완료로 올리지 않는다.
- actor별 RGB/촬영 시각/해시와 자기 발행 명령, 정적 geometry, 전달된 고정 enum만
  소비한다. peer controller/현재 좌표/접촉/심판을 입력으로 쓰는 경로는 찾지 못했다.
  별도의 actor bus에 실제 전달된 wire를 넣는 fake 왕복 검사를 확인했다.
- 같은 `CorridorController`와 `ControlConfig`, map/route hash, 역할 매핑, 상태 채널을
  네 조건에 쓴다. pair 통신 trace와 방향별 body 명령 동등성 검사를 재현했다.
- 선행 #310 `5d363335a286247a58d19652771b7ecddb21ef05`는 후보의 ancestor이고
  정적 `zone_corridor_contract.py`가 같다. #310는 OPEN/DRAFT, main 병합 SHA 없음.
  후보에 상속된 workflow-manager admission은 corridor를 조용히 실행하지 않고 거절한다.
- pair pivot/bay 후퇴, 빈 로봇 복귀, red/green 등 미지원 하중은 명시적으로 거절한다.
  실제 RGB/actuator 어댑터·새 번들은 미등록이다. MERGE는 이 제한을 보존한
  독립 제어 후보에 대한 판정이며 원본 s4의 전체 운반 지원 판정이 아니다.

### #335 / T04

- 별도 can registry에 직경 .038 m, 높이 .050 m, 80 g, any 역할, .024 m 파지 높이를
  연결한다. 원통/가림/바닥/상자/누운 can·빈 집게·미파지·방출 실패·허용 밖 자세와
  기존 색 상자 API 회귀를 검사했다. I-335-1 때문에 안전한 팔 전이 항목은 미충족이다.
- 해시가 맞는 자기 JPEG를 직접 decode하고 등록된 own-camera provider에 전달한다.
  관절값 대신 실제 발행 PWM 이력을 사용한다. 주입한 eval/setup/peer 정보는
  명령에 영향을 주지 않았으며 sim/world/GT 입력 소비를 찾지 못했다.
- 네 조건의 factory/profile/controller/state/명령은 같고 condition별 override가 없다.
  s6 서쪽 전용 규칙을 추가하지 않았다. 단일 can kind와 specific identity는 구분된다.
- .200 m 접근 반경과 두 lift 높이의 rim 인식은 후보이며 실제 보정/가시성 증거가 아니다.
  목적지 navigation과 새 workflow 연결은 별도다. `released_visual`과 물리 배송은 구분된다.

## 독립 재현 결과

Python 3.12.13, 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python` 사용.
`git archive origin/<branch> | tar -x -C <scratch>`로 각 지정 SHA를 추출했다.
새 git worktree/환경/host lock을 만들지 않았고 `.github/workflows`를 수정하지 않았다.

| PR | 기능 + 선행 계약 | 과거 등록 소스 | 현재 source pinning | 중복 제외 총 통과 | 제거 변이 검출 |
|---|---:|---:|---:|---:|---:|
| #330 | 138 | 22 | 34 | **194** | **5/5** |
| #331 | 132 | 22 | 34 | **188** | **6/6** |
| #335 | 50 | 22 | 34 | **106** | **4/4** |

- 기능 묶음은 각각 `test_zone_own_executor_observed_reroute.py` + `...door_routes.py`,
  `...corridor_control.py` + `...corridor_contract.py`, `...can.py`다.
  필수 두 파일은 `tests/test_zone_pair_registered_source.py`와
  `tests/test_zone_study_source_pinning.py`다.
- 최초 archive에는 Git 이력이 없어 PR마다 등록 검사 16개가 `git log/show`에서 실패했다.
  원본 로그를 보존했다. 후보 HEAD를 가진 **별도 임시 bare GIT_DIR**에 기존 object store를
  읽기용 alternate로 연결한 후, 추출 소스는 그대로 두고 등록 검사 22개를 모두 재통과했다.
  이 환경 실패를 제품 결함이나 제거 변이 검출로 세지 않았다. source pinning 34개는
  최초 실행에서도 모두 통과했다. 위 총계는 재실행/중복 통과를 합산한 숫자가 아니다.
- #330 변이별 assertion 실패 수: 관측 제거 9, 재계획 제거 10, stop 제거 23,
  메시지 제거 3, 편대 실패 검사 제거 7. 각 변이는 원래 62개 테스트를 실행했다.
- #331: 제어 제거 2, 양보 제거 1, heartbeat 검사 제거 2, timeout 제거 2,
  전체 출구 검사 제거 1, 경로 거절 제거 1. 해당 동작 검사를 각각 실행했다.
- #335: floor 인식 제거 4, lift 증거 게이트 제거 1, release 증거 게이트 제거 1,
  own-camera 경계 제거 1. 해당 동작 검사를 각각 실행했다.
- 15개 변이 모두 import/collection/setup 오류 없이 **행동 assertion**으로 실패했다.
  메모리에서만 변이했고 검사 후 변경 파일과 필수 봉인 테스트의 바이트를 후보 Git blob과 대조했다.
- 새 반례는 `pytest -q -rx tests/test_review_e2e_batch_i.py`에서 **2 xfailed**.
  `--runxfail`에서는 의도한 assertion **2 failed**, 수집/실행 환경 오류 0이다.
  테스트는 지정 SHA를 임시 추출하고 종료 시 삭제한다. 수정 SHA 재검토용 환경 변수는 파일에 적었다.

세 후보 모두 기준 `origin/main`과 `.github/workflows`의 **직접 tree diff와 PR diff가 0**이다.
조회한 최종 SHA CI는 모두 **33/33 success**다. 과거 10분/15분 설치 timeout은
현재 코드의 실패로 판정하지 않았다. 선행 #314/#310의 과거 preflight 실패와
최신 main을 통합한 #330/#331의 통과를 구별했다.
main에 나중에 추가된 다른 기능 파일이 오래된 후보에 없는 것은 후보의 삭제 변경으로 세지 않았다.

## 물리 인계와 남은 범위

| PR | 명시된 진단 셀과 staging 포함 cap | 실행 전 남은 관문 |
|---|---|---|
| #330 | solo/pair × 정상/막힘 = 4 × 900 = **3,600 SIM초** | I-330-1 수정, 실제 관측/navigation/T06 연결, 새 번들. 원본 crate는 원래 wide이므로 이 셀을 pair 우회 성공으로 세지 않는다는 제한이 있다. |
| #331 | solo/pair × 동/서 × 정상/대치 실패 = 8 × 900 = **7,200 SIM초** | 실제 관측·속도 보정·lease 정지, 표준 workflow/번들. W/J/E/B와 상대 편대/최대 3대/실패 hold job을 구체적으로 명시했다. |
| #335 | s1/s5 공통 배치의 단독 dev 정상 1 + can 부재 실패 1 = 2 × 900 = **1,800 SIM초** | I-335-1 수정, 원래 카메라에서 실제 rim/holding, can navigation·표준 workflow. s6는 T11 별도이며 부재 실패가 모든 미파지/낙하 고장을 커버하지 않는다고 명시했다. |

세 인계 문서는 최종 v3/walls_v3/표식 0/weld OFF/cargo_noslip_v1, 소스·입력 고정,
실패/미도달 분모와 raw·평가·TensorBoard 후속 확인을 요구한다. cap과 정적 거리를
실제 성공·지연·wall 시간으로 주장하지 않는다. 이번 단위회귀를 새 물리/평가 실험으로
변환하지 않았고 TensorBoard 서버/스냅샷을 만들지 않았다.

원본 로그는 `/Users/changmin/projects/ugrp/outputs/review-e2e-batch-i/`에 로컬 보관한다.
개별 로그 SHA-256·후보 파일 해시·CI 및 변이 결과는
[`REVIEW_E2E_BATCH_I_EVIDENCE.json`](REVIEW_E2E_BATCH_I_EVIDENCE.json)에 있다.
Git에 보존한 검토/반례/요약과 로컬 원본 로그의 원격 백업 여부는 별개다.
사용한 `/private/tmp/ugrp-review-e2e-i-lgq5d8s2`를 삭제했고, 반례 테스트의 임시 추출 디렉터리도 남지 않은 것을 확인했다.
