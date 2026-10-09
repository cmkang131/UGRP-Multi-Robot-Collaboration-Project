# simspeed — 결과 불변 가속 후보 (2026-10-09)

감독 요청: 궤적·판정·기록을 유지하고 Python 비용만 줄인다. PR #405의
`4851b313a6280f7f089b8320c18c479ccf421fc1` 위 후보이며 DRAFT 유지, 병합하지 않는다.
물리·제어·임계값·카메라·기본값 변경 없음. 새 RGB 실행 번들 없음.

## 조사와 적용 범위

- [MuJoCo 공식 simulation loop](https://mujoco.readthedocs.io/en/stable/programming/simulation.html#simulation-loop):
  `mj_step`은 forward dynamics 후 적분한다. 적분 직후의 파생 상태는 새 qpos에 대해 재계산된 값이 아니다.
  따라서 카메라 경로의 `mj_forward`를 단순 제거하지 않는다. `wall_parallax_strafe.bind_camera.apply`
  → `MultiMasterPiProductionV2._render_rgb_direct`에서 호출되며, 초기화/상태·카메라 수정 호출도 유지한다.
  `mj_step` 내부 C `mj_forward`와 Python의 별도 호출을 구별한다. 동기 재생에서 호출자/횟수를 계측한다.
- [Python 공식 bounded memoization](https://docs.python.org/3/library/functools.html#functools.lru_cache):
  순수 함수의 동일 인자를 캐시한다. 기존 `DriveParameters.command_step` 자체를 계산기로 쓰며
  dtype/shape/전체 바이트(부호 있는 0 포함)를 키로 한다. 파라미터 인스턴스별 최대 256항목,
  반환 배열 복사로 캐시 오염 방지. v7 매 스텝의 `np.isin` 검증·relay 재계산을 줄인다.
  새 파라미터·산술 근사·solver 생략 없음. 입력 변경·relay 반전·reset 후 상태는 다른 키이다.
- [Python logging 최적화](https://docs.python.org/3/howto/logging.html#optimization):
  불필요한 문자열 계산을 늦추는 원칙을 조사했으나 이 경로는 필수 JSON 기록이어서
  직렬화 자체를 생략하거나 가변 객체의 참조를 큐에 넣지 않는다. 선택 버퍼는 직렬화된 문자열만
  64 KiB로 모으고 매 eval_sample 끝/close에서 flush한다. 비정상 강제종료 시 현재 프레임 유실 가능성은
  기본 off 옵션의 제한이다. 정상 완료 기록의 내용·순서·공백·필드·빈도는 동일하다.
- `own-contacts.jsonl`은 물리 접촉이 아닌 영상의 벽/바닥 관측이다. 필드 축약/샘플링은 적용하지 않는다.
  접촉·관측 로그를 줄여 얻은 속도를 불변 가속으로 세지 않는다.

## 옵션

`sim.v7_exact_speedups.install(backend)`의 기본 `off`는 객체·함수를 바꾸지 않는다.
`relay-cache-v1`은 캐시만, `relay-cache-buffered-v1`은 캐시와 프레임 단위 flush를 설치한다.
호출 시점은 backend 구성 뒤 reset/로그 쓰기 전이다. 기존 연구 러너는 자동으로 켜지지 않는다.
기존 scene/runner/frozen source를 고치지 않고 다음 실행의 명시적 admission에서 설치할 수 있다.

## 오프라인 cProfile

실행 소스 `fc516480`의 `code/profile_saved.py`, `code/profile_relay.py`.
raw: `/Users/changmin/projects/ugrp/outputs/simspeed-20261009/` (로컬, 원격 raw 백업 아님).
다른 연구가 잠금 보유 중인 **진단 프로파일**이므로 wall/SIM 비교에 사용하지 않는다.

- 완료된 egomap49 seed49001의 첫 61 RGB 중 51회 제어 입력 재생: trace **51/51 bytes 동일**.
  원본 image sha256도 확인. 물리·렌더·모델 호출 0.
- v7 relay: seed49001에 기록된 발행 모터를 0.00025초 주기로 계산, 144,000회. 물리·렌더 0.
  매 명령 구간은 저장된 프레임 간격으로 고정한 계산 비용 진단이며 실제 물리 시간 측정이 아니다.
- 최초 teach seed49001 재생은 0/51 불일치여서 동일성 증거에서 제외. 해당 원본은
  `081fcfdb`의 `ADAPTER_CAPTURE_BYPASSED` 중단 기록이며 현재 `4851b313`과 teach adapter가 다르다.
  실패 프로파일/원본은 보존하고 수정·성공 재분류하지 않았다.

상위 10개는 [오프라인 표](results/offline-profiles.md)에 있다. 최종 물리 비교는 잠금 해제 후 추가한다.

## 고정 검증 계획

같은 완료 원본 seed49001의 초기 12 SIM초, 초기 arm부터 회전/hold를 저장된 순서대로 재생한다.
원래 표준 Scene/mesh/off/접촉/카메라/IntegerClock/평가 경로를 그대로 사용한다.
한 agent_lock 아래 cProfile 1회 + 계측 동일한 A1/B1/B2/A2, n=2씩. cProfile은 속도 평균에서 제외.
연구가 잠금을 반환할 때까지 대기, nice 0, 다른 프로세스 조작 없음.
원본 command/frame/bundle 해시와 전후 부하 평균을 기록한다.

매 스텝 `mjSTATE_INTEGRATION` 전체 상태를 누적 SHA-256에 넣고 스텝 수·시작/종료/최종 상태를 기록한다.
원본 JSON·JPEG·장면·평가 판정·명령·trajectory·contacts·누적 상태 로그를 파일별 바이트 비교한다.
누락 필수 기록, 불완전 프레임 수·시간, 이미지 해시/평가 행 수 불일치는 거부한다.
시간/부하/프로파일·소스 provenance는 비교 데이터 바깥 sidecar에 둔다.
**짧은 고정 입력 재생이지 전체 teach/return 임무나 실물 성공이 아니다.**

실행 경로: `scripts/sim_cli.py workflow run egomap-sim-speed-replay -- --source <완료 원본> --output <새 절대 outputs> --expected-source-sha <push된 SHA> --sim-seconds 12 --wait-seconds 3600 --execute`.
공통 workflow 기록을 기본 checkout outputs 아래에 지정한다. ENOSPC는 HOST_ERROR이며 재시도로 숨기지 않는다.

## 현재 검증

`tests/test_v7_exact_speedups.py`: 7 passed (물리 없음). 기본 off 무변경,
입력 경계/NaN/잘못된 state 거부, 비연속 배열, 파라미터 분리, 반환값 오염, 완료 로그 바이트를 검사했다.
workflow 계획의 필수 입력/소스 SHA·자식 실행 0·입력 보존 검사까지 **관련 8 passed**.
새 workflow의 공통 catalog 시험 샘플도 추가했다. 처음 작성한 계획 시험의 Mac 임시 경로
`/var`/`/private/var` 기대값 불일치는 `resolve()`로 바로잡은 뒤 다시 통과했다.

오프라인 스냅샷 `outputs/tensorboard/1009-simspeed-offline`은 7개 진단을 포함한다.
원본→event→실제 서버 **36개 수치 일치**, 영상 신규 등록 0, Chrome 강 프로필 화면에서
7개 run 선택·7개 pinned card·bytes=1·rows=51 및 지정 HParams 열을 확인했다.
[화면 설정·주소](results/tensorboard-offline-view.json), [수치 검증](results/tensorboard-offline-verification.json).
HParams 전역 표의 run 필터는 적용되지 않으므로 자기 수치 확인은 필터된 Time Series에서 했다.

CI `37891574488`/`6f070bf8`의 실패를 [첫 두 shard](results/ci-failures-6f070bf8.json)와
[추가 네 shard](results/ci-more-failures-6f070bf8.json)에 남겼다. VIS3 markerless source의
실제 SHA는 base `4851b313`과 같아서 해당 봉인 불일치는 상속된 문제임을 확인했다.
나머지 실패 전부를 base에서 재실행한 것은 아니며, 봉인 해시를 속도 작업에서 고치지 않는다.
DRAFT 유지, 전체 CI 통과/병합을 주장하지 않는다.

`managed-abba-v2`는 연구 PID 3349의 정상 잠금을 3600초 기다린 뒤 물리 0으로 종료했다.
[대기 종료 기록](results/queue-timeout.json)을 보존하고 더 긴 유한 대기로 재등록한다.
앞선 짧은 SHA 거절·자기 대기 실행 중단·sparse texture 누락도 원본을 보존했다.
누락 PNG 24개는 저장소 원본 및 layout 해시로 복원했다. 물리 A/B는 아직 미완료이다.
