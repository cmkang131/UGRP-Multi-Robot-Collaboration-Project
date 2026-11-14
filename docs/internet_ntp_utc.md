# 인터넷 NTP와 UTC 예약 실행

각 로봇은 chrony로 인터넷 NTP 서버에 직접 동기화한다. 공통 후보는 `time.cloudflare.com`, `ntp.kriss.re.kr`, Debian NTP pool이다. 로봇은 서로를 시간 서버로 쓰지 않으며, 후보 중 선택된 서버가 달라도 기준 시간척도는 UTC다. chrony 설정과 이전 설정 백업·검증 로그는 `scripts/set_internet_ntp.ps1`에서 관리한다.

## 예약 합의

1. 현재 NTP UTC보다 충분히 뒤인 실행 시각 T와 고유 action_id를 정한다.
2. 같은 참여자 목록·T·action_id로 PREPARE를 보내고 모두의 READY를 확인한다.
3. 모두 준비되면 같은 내용으로 COMMIT한다. 각 로봇은 T까지 자기 monotonic 시계로 기다린다.
4. 시계 동기화 실패, 시계 변화, 중복 명령, 준비 누락, 시한 초과는 실행을 거부하고 기록한다.

`scripts/utc_reservation_agent.py`와 `scripts/run_utc_reservation_check.py`의 기본 시험은 **신호 기록만** 한다. SSH 인증을 마친 뒤 10초 뒤 T를 선택한다. PC 프로그램은 인터넷 NTP UTC를 monotonic 시계에 연결하므로 PC의 운영체제 시계를 변경하지 않아도 된다. NTP 응답은 인증된 시간 증거가 아니며 네트워크 비대칭에 따른 오차가 남는다.

PREPARE/COMMIT는 모든 참여자가 준비됐는지 확인하는 절차다. 마지막 순간의 통신 단절에도 모든 로봇이 함께 실행하거나 함께 취소한다는 보장은 없다. 이 신호 시험을 공동 들기 성공으로 해석하지 않는다. 실제 공동 들기에는 동작별 지연 보정, 영상 확인, 비상 정지 및 통신 단절 대응을 별도로 검증해야 한다.

## 실물 명령에 적용

수정된 `masterpi_control.py`와 `utc_clock.py`를 같은 폴더에 배포한다. 기존 로봇 제어 파일은 보존하고 별도 실행 번들을 사용한다. 기존 PWM·동작 시간을 그대로 쓰되 예약 시각은 전역 옵션으로 **servo/motor/drive 앞에** 지정한다.

```text
python3 masterpi_control.py --execute-at-utc-s <T의 UTC epoch초> --action-id <고유ID> --clock-budget-ms <허용오차ms> servo <검증한ID> <검증한PWM> --duration <검증한이동초>
```

이 명령은 개별 예약 실행이다. 양쪽에 제각각 명령을 보내는 것만으로 PREPARE/COMMIT 합의가 생기지는 않는다. 실제 동작을 연결하는 상위 실행기는 합의를 먼저 완료하고 개별 명령을 발행해야 한다. stop은 즉시 처리한다. 이 작업에서는 실제 서보·주행 명령을 실행하지 않았다.

신호 점검의 기본 시계 오차 예산은 250ms이며, 공동 파지 허용치로 채택한 값이 아니다. 실제 명령에는 `clock_budget_ms`를 명시해야 한다. 이는 각 시계의 오차 **추정값**이며 확정 상한이 아니다. 서로 다른 로봇의 오차와 운영체제 예약·서보 지연을 합쳐 허용치를 판단한다. 실행 시각은 명령 발행 기준이고 물체가 움직이기 시작하는 시각과 다르다.

## 시뮬레이션·통신 코드에 적용

- `run_rgb_communication_ntp(..., asynchronous=False)`는 기존 순차 통신에 UTC 송수신 기록과 실제 시간 TTL을 적용한다. `asynchronous=True`는 기존 비동기 경로에 같은 UTC 통신을 적용한다. 예전 SIM 시간 TTL 결과와 구분해 평가한다.
- NTP UTC 증거는 300초까지 사용한다. 만료되면 실행을 중단하며 새 에피소드·예약 전에 다시 동기화한다. 오래된 시각을 묵시적으로 계속 사용하지 않는다.
- WebSocket 워커의 명령에 `id`, `execute_at_utc_s`, `clock_budget_ms`를 넣으면 같은 UTC 대기 기능이 적용된다. 병렬 묶음은 모든 자식이 동일한 T와 서로 다른 ID를 가져야 한다. 제한이 가장 엄격한 오차 예산을 사용한다.
- 워커 계약은 `masterpi-v2-coela-traffic-budget-utc-v10`으로 갱신했다. 브리지와 워커를 같은 소스로 배포해야 한다. 과거 워커에는 UTC 예약 명령을 보내지 않는다.
- UTC는 통신·예약 경계에서 쓴다. MuJoCo 물리 계산은 기존 정수 SIM 단계를 유지한다. 원격 워커의 물리 실행 및 실제 공동 운반은 이번 신호 점검의 검증 범위에 포함되지 않는다.

공식 문서: [chrony 설정](https://chrony-project.org/doc/4.8/chrony.conf.html), [chronyc 상태 확인](https://chrony-project.org/doc/4.8/chronyc.html), [Cloudflare NTP](https://developers.cloudflare.com/time-services/ntp/usage/), [KRISS 시간 서비스](https://www.kriss.re.kr/menu.es?mid=a10305000000).
