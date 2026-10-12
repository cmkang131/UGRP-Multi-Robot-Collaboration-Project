# S3 s3fix2 — 명령 계약·정확 가속·S2 오차 (2026-10-09)

실행 전 결정: 기존 v147 원본/기본 off 모듈을 보존하며 새 v148/7.41.0에만 pair heading/명령 계약 및 정확 가속 옵션을 넣는다. seed14201(+0/+1/+2), σxy≤.05m/yaw≤5°, posterior 인증·평가 XY≤.25m/yaw≤15°는 유지한다. DEV 가드 log-only, 실제 실행/GO 오류는 정지. 다음 물리 스모크1회, SIM1800/wall10800초, raw3GiB+10GiB reserve, dev_light·v3 host binding·heading on·#420 speed. cProfile은 저장 입력만 우선 사용하며, 최종 스모크는 프로파일러 없이 wall/SIM≤3 달성을 측정한다. 종료 원인/단계가 다른 v146/v147 전체 비율을 속도 효과로 단순 나누지 않는다. ENOSPC는HOST_ERROR, 자동 재시도 없음.

현재 egomap58 실행은 건드리지 않고 종료 뒤 잠금을 acquire한다. 사용자 순서로 대기 중인 자기 지도9회보다 S3가 먼저다. 코드/회귀/저장 입력 검증→초록 커밋/push→한 번 실행. CI 완료 대기0.

## 원인과 표준 근거

원인 한 줄: **별도 기존 pair 제어기가 내는 연속 혼합 축 명령을 S2의 측정된 단일 축 finite-pulse PF에 그대로 넣었으며, 공통 heading on은 이 pair 제어기에 연결되지 않았다.**

- [Nav2 RPP](https://github.com/ros-navigation/navigation2/blob/main/nav2_regulated_pure_pursuit_controller/README.md): 경로 carrot 방향으로 회전 후 추종하는 공통 selector를 재사용한다. 옆걸음은 집기·놓기·문 정렬의 최종0.10m만 허용한다. pair 현재 빔 route에는 긴 횡이동이 있으므로 단일 축 예외를 무조건 허용하는 것으로 해결 완료를 주장하지 않는다. 짝 들기 중 적용 범위는 사용자에게 별도 확인 중이며 그 전에는 엄격 적용 경계로 개발한다.
- [Python cProfile](https://docs.python.org/3/library/profile.html): 누적/자체 시간을 분리한다. 프로파일러 overhead가 포함된 시간을 실제 wall/SIM으로 제시하지 않는다. 입자/관측/기록을 별도 함수 집계하며 원본 영상 재생은 렌더가 아니므로 렌더 시간은 최종 실행의 별도 호스트 계측으로 구분한다.
- [Fox2003 KLD](https://www.robots.ox.ac.uk/~cvrg/hilary2005/adaptive.pdf): 기존 v147은 첫 정보 관측 후400000→약8001로 이미 감소한다. 무작정 다시 줄이면 표본/RNG/출력이 달라지므로 결과 동일 가속과 분리한다. 실제 프로파일에서 필요한 정확 캐시·벡터화·I/O buffering만 채택하며, 후보 전후 포즈/명령/필터 state의 hash를 비교한다.
- [Python buffered I/O](https://docs.python.org/3/library/io.html): JSONL 바이트와 순서를 보존하는 버퍼를 사용하고 평가 읽기/종료 전에 flush한다. 기존 원본은 변경하지 않는다.

## S2 재생의 실제 오차

고정된14.00 절대SIM초 창의 같은RGB/발행명령 비교다. 새 물리0. v147 전후 원본은 [기존 해시](../s3fix/replay-summary.json)에 연결한다. 후보14초 XY오차는 모든6seed에서 감소했다. 따라서 이번 지시의 **실제 위치가 틀릴 때만 다중모드 감지로 범위를 좁히는 조건은 발동하지 않는다.** S2 기본값은 계속off, 후보 옵션은 새 S3 번들에서만ON. 수렴 지연을 해결 완료로 표시하지 않으며 첫 σ와 실제 오차/인증을 나눠 보고한다.

|seed|14초 XY오차 전→후(m)|14초 σxy 전→후(m)|첫 σ수렴 절대SIM초 전→후|고정창 허위수렴 전→후|
|---|---|---|---|---|
|1065|0.047109→0.041584|0.037078→0.048771|6.95→13.95|0→0|
|1066|0.052222→0.048952|0.030122→0.041408|10.55→13.65|0→0|
|1067|0.041732→0.024252|0.092656→0.098001|미수렴→미수렴|0→0|
|1068|0.152345→0.059546|0.016358→0.212777|12.70→미수렴|0→0|
|1069|0.082934→0.039578|0.005228→0.096613|8.45→미수렴|0→0|
|1070|0.033573→0.019901|0.086722→0.117925|미수렴→미수렴|0→0|

첫 σ수렴4/6→2/6, posterior 인증3/6→1/6. 후보 미수렴4개의 실제 XY오차.0199–.0595m로 작은 점오차와 넓은 posterior를 구분한다. 14초 이후 전체 운반 성공/허위수렴0이라는 주장은 아니다.

## 오프라인 구현 검증 (물리 실행 전)

- `zone_s3_pair_heading`은 기존 접근 driver의 상태·정적 경로·자기 추정을 유지하고 발행 직전 공통 heading selector의 측정 펄스로 바꾼다. 펄스 전체 시간+coast+지연된 자기 포즈까지 기다린다. 기본 off는 원래 인스턴스를 반환한다. **아직 새 혼합 실행 전체 경로에 연결·인수한 결과는 아니다.**
- 원본 v147의 비영(非零) 차체 명령2개를 재생했다. 원래 단일 축 계약 오류2/2→변환 후0/2. 이 비교는 정적 최종 접근 목표를 carrot으로 한 계약 단위 반사실 재생이며, 새로운 물리 이동·운반 성공이 아니다. [입력 해시와 명령](command-replay.json), [실행 스크립트](command_replay.py).
- 순수 posterior summary를 particle/weight/label/offset 내용 해시로 memoize한다. 배열의 in-place 변경, 가중치 변경, pan offset 변경은 캐시를 무효화하고 시각·건강 상태·감사 기록은 매 호출 갱신한다. 필터 분포·RNG·KLD 문턱은 바꾸지 않는다. 전체 원본 재생 해시 비교는 통과했다. cProfile 채택 판정은 잠금 후 진행한다.
- JSONL은 같은 JSON 인코딩/행 순서의64KiB buffer로 기록하고 referee 읽기 및 close 전에 flush한다. 후속 실제 smoke의 render/capture/physics/eval/JSONL 타이머는 제어기로 전달하지 않으며, nested timer를 단순 합산하지 않는다. 기록 버퍼의 바이트 동일성과 read-before-evaluate 회귀를 고정했다.
- 변경 모듈 시험 `tests/test_s3_pair_heading.py tests/test_s3_exact_cache.py`: **14 PASS (2파일)**. 실제 `GuardedDriver`의 넓은σ DEV 경로에서도 단일 축 heading 펄스가 생성되고, 기존 σ를 줄여 보고하지 않는다. 버퍼 off 위임 보강 후 해당4개 추가 확인.
- [S2 원본 수치·해시](s2-error-comparison.json):6개 전부 실제 XY오차 감소, σ4/6→2/6·인증3/6→1/6. 이전 재생을 재집계했으며 새 물리나 새 확증 코호트로 합산하지 않는다.

### 접근·집기 전 전체 명령 연결 보강

추가 정적 계약 문제: 기존 r1/r2 `CameraRobotPort`는 forward≤.15/left≤.10/turn≤.15인 반면 S2 측정 heading 펄스는 turn/forward±.35 및 final lateral±.35/.06s이다. 제어기만 바꾸면 다음 호스트 상한 오류가 확정적이다. 새 `sim/s3_motion_ports.py` 옵션은 r1/r2에도 S2와 같은 `FinePulsePort(real_v1, real_fine_v1)`를 사용한다. 기존 v147과 옵션off 포트는 바꾸지 않는다.

`zone_s3_motion_runtime`의 실제 pair API 제출 경로에서 접근 driver 및 집기 전 RGB 정렬을 연결했다. 정렬은 기존 RGB 도착 판정만 사용하고, 아직 정렬되지 않았으나 펄스 해상도상 이동을 고르지 못한 경우는 `None(정렬 완료)`로 바꾸지 않는다. 최종0.10m lateral에는 동일 시각의 자기 RGB 오류/명령 근거를 요구한다. no-view 탐색·후진은 단일 turn/forward 펄스로 바꾸며 혼합 축을 묵시적으로 허용하지 않는다. 네이티브 만료·전체 coast·지연 자기 관측을 기다리고 GO/abort 확인은 기존 endpoint 바깥 루프에 유지한다.

관련 최종 시험은 heading/실제 pair session/RGB 정렬/호스트 포트10 PASS와 내용 캐시/버퍼4 PASS(2파일)다. **공동 loaded carry의 기존 연속 혼합 축 schedule은 아직 새 pulse 계약에 이관하지 않았으며, 새 실행 번들은 runnable로 등록하지 않았다.** 2.15m loaded lateral에 대한 결정3 적용 범위를 확인한 뒤 이관 방식을 확정해야 한다. 알려진 다음 단계 계약 오류를 남긴 채 허용된1회 smoke를 소모하지 않는다.

### 전체 저장 입력의 정확 캐시 동일성

[재생 원장](equality-summary.json)의 두 독립 프로세스는 구현 `3ad3bdc88c6e3eec745ab19c63822ce840699bc2`에서 로봇별442프레임을 처리하고 원본 혼합 명령 오류에서 똑같이 종료했다. 캐시 전후 생성 명령 SHA-256 `95c7bb1babc22263fd45c83e16f352b6ba746a5f97a9cf8ecf93bcca838d4065`, 포즈 전체·최종 입자/가중치·RNG 상태 SHA-256 `6138376fcdab9317a77c4ef47ac1625beaa71b4f4d04311f0b0160e06762bb8a`가 같다. 원본 v147의 오류도 보존하는 가속 전용 비교이며, heading 수정의 물리 인수가 아니다. 다른 비시간측정 실행과 겹친 정확성 검증이므로 시간 수집을 명시적으로 끄고 `profiled_wall_s=null`로 남겼다. 물리 실행0, 속도 개선 주장0.

TensorBoard 새 snapshot `1009-s3fix2-verified`에 계약/동일성 두 기록을 추가하고 기존 `1009-s3fix-replay`와 함께 열었다. EventAccumulator의10개 스칼라, UI의 계약2→0·해시 동일1/1, 고정 카드8개, HParams `case/policy/seed/source_sha` 선택을 확인했다([표시 검증](tensorboard-verification.json), [고정 링크](tensorboard-link.json)). 새로운 물리 영상은 없으며 v147 대표 영상은 기존 snapshot에 보존한다. cProfile와 새 smoke는 아직 완료하지 않았다.

### would_stop 기록 비용의 측정 전 구분

[원본 계수](would-stop-accounting.json)의511회는 검사 훅 호출 수다. 새 pair 훅421회에서 materialized audit row는18개이며 `Audit.note`는 메모리 리스트에 추가하고 호출마다 파일을 쓰지 않는다(직접 disk write0). 따라서 “511회 동기 파일 쓰기 때문에 느려졌다”는 가설은 코드/원장과 맞지 않는다. 실제 summary·복사·직렬화 비용의 시간 비중은 cProfile 전에는 확정하지 않는다. 호스트의 매 프레임 JSONL은 별개이며 해당 버퍼 후보를 시험했다.


### 후속 완료 기록

사용자 공동 운반 예외 결정 이후 공통 PR #422를 먼저 분리·merge했고, cProfile 및 v148 혼합 DEV1회를 완료했다. reset 포트 HOST_ERROR, 속도 목표 미달, 후속 오프라인 수정과 원본은 [s3fix3 결과](../s3fix3/README.md)에 있다. 위의 미실행/대기 문구는 해당 기록 시점이며 결과를 소급해 덮어쓰지 않는다.
