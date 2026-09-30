# T09b: 자기 관측 뒤 두 문 우회 판단

2026-10-01 최신 보완: [독립 검토 I-330-1 수정](REVIEW_I_FIXES.md).
촬영 시각·250 ms 유효기간·취소 tick 이후 새 촬영을 요구하는 v2 후보다.
**608 passed, 280 subtests passed**, 제거 변이 **9/9 검출**. draft·물리 미실행을 유지한다.

아래 초기 제출 기록: 당시 main 통합 후 **356 passed, 280 subtests passed**, 다섯 제거 변이 모두 검출.
구현·오프라인 검증 범위의 draft이며 물리 준비 판정과 구분한다.
**물리·렌더·모델 호출 0회. E2E/물리 실행 준비 완료가 아니다.**
원본 시나리오·지도·봉인 제어기·등록 DRAFT·seed·성공 기준은 수정하지 않았다.
새 파일은 `harness/zone_observed_door_reroute.py`, 전용 fake 테스트와 이 기록뿐이다.
신규 bundle/workflow ID를 등록하지 않았다. 기존 실행기를 암묵적으로 전환하지 않는다.

## 선행과 소스

- 최초 main `ad496486271f441f00eb7d95fbd44dc454999004`와 T09a #314
  `9738a3d2feeae818162533326c64c75b3a557633`을 합친 로컬 merge는
  `7e134745b35895f177ac1a82f18c7aee6466d3a4`이다. 기존 구현을 이어서 작업했다.
- #314 최신 HEAD `994b269d97d05dd2159c1a78f2b9eae9955790f9`의 미완료 merge를
  관련 검사 후 `99e4b23`으로 마무리했다. #314는 조회 당시 **OPEN/DRAFT**이고
  **main 병합 SHA는 null**이다. 이 작업 브랜치에 선행을 합친 것과 구별한다.
- 재개 기준 main은 #328 병합 `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`다.
  오프라인 pytest는 기본 무잠금이며 물리/학습 잠금은 별도다. 이 main을
  `ae0aa5db27aff483eb5c40d75f29ae197e48ac6a`로 통합했고
  `.github/workflows/tests.yml`은 main과 바이트가 같다. 선행에 남아 있던 다른
  CI concurrency를 요구하는 검사·CONTRIBUTING 문단은 main으로 맞췄고,
  LITERATURE 충돌도 같은 취지의 최신 main 문단을 보존했다.
- #314 검증 범위는 정적 전체 편대 경로와 D1 carrier 제거 반례다.
  과거 283 passed나 물리 결과를 이번 결과에 합산하지 않는다. 이번 검증에는
  최신 `test_zone_own_executor_door_routes.py`를 다시 포함했다.
- 요구 출처 #302 HEAD `5d31f6c822a569b195ad7d0ea15a7d95de840974`,
  실제 main 병합 `09081b3c46f0d51e02ef625e4be8c7d6f6e67963`을 확인했다.
  `REQUIREMENTS.md`의 s2와 `TASKS.md` T09a/T09b를 따르며,
  inventory·feasibility·referee는 controller import/input으로 사용하지 않는다.

### CI 대기 중 main 후속 반영

최초 제출 HEAD `6cdfe47515e69d8e44ccbca3f044b8a1fa605385`의 CI
`36730563767`은 32개 job 통과 후 Ubuntu runtime 한 job이 두 시도 모두
10분 제한으로 자동 중단됐다. 수동 취소·코드 실패 감추기·원본 삭제는 없었다.
원본 log/annotation/상태 해시는 `ci_before_main_332.json`에 있다.

그 사이 main에 #307과 **#332**가 병합되어 `26545c2499f94c3f99a5d650f7cc8ea992f24196`이 됐다.
#332의 Ubuntu simulation 제한 10→15분을 main 그대로 반영했다. T09b 제어기·
fake 검사·변이 드라이버는 바꾸지 않았고, workflow는 이 최신 main과 동일하다.
추가된 mixed-job CI glob까지 포함한 통합 회귀·변이를 새 원본에 다시 실행했다.
이 재검증도 **356 passed, 280 subtests passed**, 필수 봉인 56개 통과와
동일한 5/5 제거 변이 검출을 확인했다. 소스는 실행 중 불변이었다.
최신 결과는 `verification_main_26545c24.json`, 기존 source/config/map 보존은
`protected_sources_main_26545c24.json`(928개 blob 동일)을 따른다.
출력 복사본은 `latest-main-tests.txt`이며 이전 검증 숫자에 합산하지 않는다.

## 실제 추가한 동작

`ObservedDoorReroute.tick`은 `OwnFrame`의 자기 RGB를 주입한 관측기에 넘긴다.
관측기에는 동결한 정적 geometry와 실제 자기 발행 명령 이력만 전달한다.
RGB 해시가 일치하는 확정 막힘 또는 실제 수신함의 메시지 뒤에만 해당 문을
자기 믿음에 기록한다. 비공개 사건 시각·장애물 좌표·파트너 실제 상태는 입력이 없다.
현재 알려진 막힘은 계속 보존하며, 시야 밖/침묵/clear 메시지로 자동 해제하지 않는다.

관측 전에는 기존 경로를 유지한다. 선택한 문이 막히면 하위 navigation의 기존
명령 큐 취소가 확인될 때까지 정지한다. solo는 T09a로 후보를 계산하고 다음
새 자기 RGB의 자세로 다시 계산한 뒤 같은 navigation에 wide 경로를 넘긴다.
양쪽 막힘, 잘못된 영상/추정/수치, 회전/문 안 출발 등 T09a 미지원 경로는 거절한다.
알려지지 않은 장애물의 모양을 정적 지도에 그려 넣지 않는다. 문 ID 제외는
장애물 주변의 안전 증명이 아니므로 하위 navigation은 계속 자기 RGB 안전 검사를 해야 한다.

공통 메시지 해석 v1은 한국어 문장 `<door ID> 막힘 확인`의 완전 일치와 기존
structured `inform/blocked/high`만 다룬다. 부정·추측·미지원 문장은 무시한다.
이는 자유 한국어 전반의 의미 이해가 아니다. 기존 transport가 실제 전달한
robot inbox를 연결해야 하며 send/pending/eval log를 넘겨서는 안 된다.
메시지는 타인의 주장으로 저장하며 직접 관측이나 심판 사실로 승격하지 않는다.

편대는 한쪽 실패·heartbeat 만료·선택 경로 막힘 때 기존 `zone_pair_status_v5`의 `abort`만
전달하고 양쪽이 멈춘다. 이동 중 새 경로가 필요하면 `PAIR_REPLAN_REQUIRED`와
후보를 반환하고 기존 job은 종료한다. **한쪽의 wide 후보만으로 재출발하지 않는다.**
양쪽의 독립적인 새 작업 제출·경로 일치·기존 barrier 인수가 필요하다. no_comm에서
한쪽만 막힘을 아는 경우 이 합의를 host가 대신 만들 수 없다. 새 상태 enum이나
상대 pose/route를 상태 채널에 넣지 않는다.

`ROUTE_FINISHED`는 하위 reached 주장과 자기 추정의 goal 오차(위치 2 cm,
yaw .02 rad)를 확인한 상태일 뿐이다. 실제 문 통과·물체 배달·referee 성공과 다르다.
명령 발행/큐 취소도 실제 이동/물리 정지의 증명이 아니다.

## 검증과 재현

`run_checks.py`는 #328 기본값에 따라 공용 잠금 없이 fake 검사만 수행한다.
잠금 상태는 읽기만 하며 timing-sensitive 잠금은 경고한다. MuJoCo/glfw/torch/
모델 SDK import와 socket connect를 차단한다. 기존 Python 3.12 환경을 사용한다.
baseline은 T09a·passage·모델 기하·상태 채널·메시지 protocol·CI fast-path와
아래 봉인 회귀를 함께 실행한다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-two-door-reroute/run_checks.py \
  --output /Users/changmin/projects/ugrp/outputs/2026-09-30-two-door-reroute/NEW-baseline
```

필수 회귀: `tests/test_zone_pair_registered_source.py`,
`tests/test_zone_study_source_pinning.py`. 새 테스트는 기존
`tests/test_zone_own_executor*.py` CI glob에 포함한다. 일반 GitHub CI를
건너뛰거나 취소하지 않는다. 로컬 physics/model 0회는 원격 CI 범위를 뜻하지 않는다.

mutation은 `--mutation ignore_observation|ignore_replan|skip_stop|ignore_messages|ignore_pair_failure`
중 하나를 붙여 새 output에 실행한다. 소스 파일을 바꾸지 않고 메모리에서만
관측 반영·재계획·정지·메시지 반영·파트너 실패 가드를 각각 제거한다.
baseline exit 0과 각 mutant의 **assertion 실패 exit 1**을 확인해야 한다.
`--mutation suite`는 baseline 뒤 다섯 mutant를 순서대로 실행한다.
수집 오류나 import 오류는 mutation 검출로 세지 않는다. 결과·SHA·raw 해시는
`verification.json`에 기록한다.

초기 baseline-01은 다른 작업 잠금을 기다리는 동안 테스트 파일 이름 오류를
발견해 직접 중단했다. baseline-02도 잠금 대기 중 소스 보완 후 전체 suite로
전환하기 위해 중단했다. checks-03은 여러 잠금 소유자가 교대하는 동안 계속
대기하여 잠금 확인 간격을 줄인 checks-04로 넘겼다(각 exit 130, 테스트 시작 전).
기존 로그를 보존한다. 다른 작업이나 GitHub workflow는 취소하지 않았다.
테스트 결과를 로봇 성공률로 바꾸거나 TensorBoard 물리 기록으로 만들지 않는다.
새 물리 결과/TensorBoard snapshot은 아직 없다.

### 이전 실패와 이번 재개

이전 인계 원본은 `verification_handoff.json`에 그대로 보존한다.
checks-04는 236 passed / 15 failed였고, 지휘자가 없는 조건의 fixture에도
`leader='r2'`를 넘긴 오류와 검사 도중 소스 변경 때문에 최종 검증으로 쓰지 않았다.
checks-05는 당시 공용 잠금 규칙으로 pytest 시작 전에 중단했다. 과거 실패 raw를
지우거나 수정하지 않았으며, #328과 재개 지시로 잠금 대기를 제거했다.

재개 baseline-06은 **253 passed / 1 failed**, 실행 중 소스 불변이었다.
T09b structured fixture가 기존 transport의 필수 10개 필드 중 4개만 보내
`schema`로 거절됐고, 파서도 정상 전체 필드를 무시하던 원인을 직접 재현했다.
fixture와 파서를 기존 규약에 맞추고 누락/추가 private 필드/추측/낮은 확신/
다른 act를 거절하는 반례를 보완했다. 수정 뒤 T09b 표적 검사 **62 passed**.
main 통합 뒤 관련 회귀·다섯 제거 변이의 최종 결과는 `verification.json`을 따른다.
기존 main의 `configs/maps/harness/sim/scripts` **921개 blob**은 모두 그대로다
(`protected_sources.json`). 새 T09a·T09b 파일은 이 과거 소스 분모에 포함하지 않는다.

최종 검사에서 baseline exit 0, mutant 각각 assertion failure exit 1, XML errors 0,
`source_unchanged=true`를 확인했다. 필수 봉인 회귀는 **22+34=56 passed**다.
관측 제거 9개, 재계획 제거 10개, 정지 제거 23개, 메시지 제거 3개,
편대 실패 가드 제거 7개 assertion이 실패했다. 변이별 분모는 T09b 62개이며
독립 물리 사례의 분모가 아니다. Git 표시용 출력은 `resume-final-tests.txt`에
줄 끝 공백만 제거해 보관했다. 원본 log/JUnit/manifest는 로컬 raw 경로와 해시로
그대로 보존한다. manifest 복사본은 `resume-final-manifest.json`, 이전 실패는
`resume-baseline-failure.txt`에도 있다. 네 조건의 JUnit properties에 있는
map/prior/config/controller/role-assignment 해시가 네 조건에서 각각 같은 것도 확인했다. 이전 검사·변이를
합쳐 성공률을 만들지 않는다. 소스/설정/테스트 해시는 커밋 직전에 다시 확인한다.
GitHub CI는 draft PR의 최종 SHA에서 별도로 확인하고 본문에 기록한다.
이 작업은 커밋·push·draft까지만 수행하며 **병합하지 않는다**.

## 남은 연결 작업

1. 최종 카메라 RGB에서 막힘을 직접 확인하고 cargo pose를 추정하는 실제 Observer.
   이번 tiny PPM fixture와 FakeObserver는 로직 검사만 한다.
2. 모든 조건에서 같은 실제 Navigation 구현을 연결하고, 큐 취소·자기 안전 가드·
   기존 pair barrier/heartbeat 및 새 제출 경로 일치를 인수한다. 기존 M1/M2와
   봉인 PairTeam의 source를 이 PR에서 수정하지 않았다.
3. 원본 s2의 heavy_crate는 T06 파지/운반 지원이 선행한다. beam fake로 crate의
   물리 지원을 대체하지 않는다. 한쪽만 아는 pair 우회는 합의가 없으면 안전 종료다.
4. T09a의 0.85 m×최대 8구간·고정 동/서 yaw 제한을 유지한다. 원본 출발지에서
   목적지까지 더 긴 경로/회전이 요구되면 지원 밖으로 기록하고 새 후보를 설계한다.
   경로를 몰래 잘라 성공으로 세거나 simulator가 정류장으로 옮겨 주어서는 안 된다.

## 코디네이터 물리 인수: 최소 4셀, 3,600 SIM초

실행 어댑터가 아직 없으므로 실행 가능한 것처럼 가짜 CLI를 적지 않는다.
위 연결 작업과 표준 `sim_cli` 등록·bundle 고정 뒤 다음 네 셀을 실행한다.
**이 표는 최소 진단 제안이며 사전 등록 봉인/실행 승인·4조건 효과·확증 코호트가 아니다.**

| 셀 | profile | 장면과 입력 | 확인할 결과 | cap |
|---|---|---|---|---:|
| S-N | solo cyan | 별도 dev 정상 비교 fixture, narrow 막힘 없음 | 원래 선택 경로 유지, 자기 navigation 도착과 별도 실제 crossing | 900 SIM초 |
| S-B | solo cyan | 원본 s2 45초 narrow 사건 그대로 | 발생/가시성/발견/정지/새 RGB/wide 실제 통과 각각 | 900 SIM초 |
| P-N | pair heavy_crate | 별도 dev 정상 비교 fixture, 공개 고정 역할 배정 | 같은 계획·상태 채널, 양측 holding/운반·실제 통과 | 900 SIM초 |
| P-B | pair heavy_crate | 원본 s2 45초 narrow 사건 그대로 | 양측 각각의 가시성/믿음, 실패 안전·새 제출 합의 가능 여부·wide 통과 | 900 SIM초 |

합계 **2 profile×2×900 = 3,600 SIM초**. 접근·준비·팔 전이·staging·관측·정지·
왕복·실패 종료 시간을 전부 cap에 넣는다. cap 도달은 실패/미도달로 남긴다.
정상 비교 fixture는 별도 dev 이름/해시를 사용하고 원본 s2를 편집하지 않는다.
첫 최소 진단의 제안 고정값은 원본 layout seed 611, `no_comm`, solo 대상
`cyan_1`→A(`west=r1`), pair 대상 `crate_1`→B(`west=r1,east=r2`)이다.
기존 실제 spawn shuffle 결과와 전체 물건/주문을 그대로 기록하고 대상 하나의
진단을 전체 s2 완주로 세지 않는다. 이 정적 고정 배정은 상대 private state로
고른 결과가 아니다. 정상 비교만 새 dev 파일에서 해당 사건을 끄고 나머지 값은
원본과 같게 보존한다. 4조건 비교나 추가 seed는 이 4셀 예산에 포함하지 않는다.
각 셀의 공개 goal pose·입력/어댑터·실제 초기 배치 해시까지 실행 전에 동결한다.
원본 seeds `[611,612,613]`나 본연구 성공 기준을 이 문서로 교체하지 않는다.

원본 crate 정적 계획은 이미 wide다(3.35→3.35 m). P-B에서 wide를 계속 갔다면
**pair 우회 성공으로 세지 않는다.** 좁은 문을 선택하는 별도 pair dev 진단이
필요하면 출발/goal/역할을 사전 고정하고 새 예산 승인을 받아 별도 셀로 기록한다.
T09a가 경로를 거절하거나 T06이 미지원이면 해당 셀은 실행 준비 차단으로 남긴다.

실행 전 다음 조건을 모두 고정·검증한다.

- 최종 3D `masterpi_v3`, `walls_v3`, 표식0, weld OFF, `cargo_noslip_v1`.
  실제 Scene/model/map 해시가 공개 정적 지도와 맞는지 확인한다.
- 최종 후보 커밋·controller 소스 closure·observer/navigation/config/센서/
  자기 기억 버전·상태 enum 해시를 고정한다. 네 조건에 같은 값을 적용한다.
  role→robot assignment 해시는 controller 해시와 별도 필드로 남긴다.
- 공용 잠금과 디스크 여유를 확인하고 자기 worktree에서 `ugrp_session.py`와
  표준 `sim_cli` 경로로 실행한다. 실패마다 새 raw 디렉터리, ENOSPC는 HOST_ERROR.
- raw는 `/Users/changmin/projects/ugrp/outputs/<NEW-run-id>`에 보존한다.
  시작·이벤트 실제 효과·관측·발행 명령·취소·판단·실패 원인을 시간순 기록한다.

S-B/P-B에서 45초를 아는 것은 평가/장면뿐이다. 실제 장애물 생성/물리 효과와
각 로봇 own RGB의 가시/비가시를 따로 확인한다. 발견 반경에 들어갔다는 host
판정으로 막힘을 통보하지 않는다. 생성 전 또는 비가시 프레임에서 갑자기 wide를
선택하면 입력 누출을 조사한다. 메시지 우회는 sender/recipient/message ID와
실제 delivery 이후의 첫 판단을 연결한다. no_comm은 수신 없이 선행 우회하면 실패다.

문 중심선 접촉·mouth 방문·waypoint 완료와 전체 물건+carrier의 실제 wide 통과를
분리한다. 실제 접촉·낙하·분리·미파지를 평가에 남긴다. 한쪽 fail/abort/heartbeat
상실 후 양쪽 명령 큐가 비고 더 이상 drive하지 않는지도 확인한다. 최종 배송은
별도 referee로 판정하며 그 결과를 controller에 되먹임하지 않는다.

모든 할당 실행·실행 불가·HOST_ERROR·cap 미도달의 분모와 성공률, staging 포함
SIM초, 명령/관측 수, 실패 원인, 모델 호출/비용(새 호출은 별도 승인)을 남긴다.
원본/영상 해시를 확인한 뒤 primary `outputs/tensorboard`에 **새** snapshot을
만들고 실제 데이터·영상·HParams/pinned 지표 로딩을 원본과 대조한다. 기존
`outputs/tensorboard-view.json`은 쓰기 직전 다시 읽고 자기 키만 바꾼다.

s2의 정적 거리 참고는 cyan_1 5.15→9.55 m, cyan_2 4.55→8.95 m,
green 3.30→4.50 m, crate 3.35→3.35 m이다. event 시점 실제 위치·탐색·왕복을
측정하지 않았으므로 이 차이로 실제 지연이나 wall 시간을 추정하지 않는다.

## 참고 자료

- [PR #314](https://github.com/kcm0127-dotcom/ugrp/pull/314), T09a 정적 API·D1 보완.
- [PR #328](https://github.com/kcm0127-dotcom/ugrp/pull/328), 오프라인 기본 무잠금 규칙.
- [PR #302](https://github.com/kcm0127-dotcom/ugrp/pull/302), 요구/능력 감사.
- `harness/zone_static_door_routes.py`, `harness/zone_pair_status.py`,
  `harness/zone_study_protocol.py`: 기존 정적 계획·고정 enum·실제 수신함 계약.
- `docs/execution_versioning.md`, `docs/tensorboard.md`, `CONTRIBUTING.md`.
  새 외부 OSS/모델/의존성 없음. 이 작업은 draft까지만 제출하고 병합하지 않는다.
