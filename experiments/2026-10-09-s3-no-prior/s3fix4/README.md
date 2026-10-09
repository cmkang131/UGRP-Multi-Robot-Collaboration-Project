# S3 v149 — 단계별 오프라인 통합 검사 후 DEV 1회

2026-10-09 s3fix4 요청. v148은 reset이 포트를 다시 만들어 21.9 SIM초에 HOST_ERROR로 끝났다. 물리를 다음 오류 탐색에 쓰기 전에 합성 단계 시작 상태에서 실제 S3 runtime, pair controller, fixed-enum GO, arm queue, native port.apply와 모터 stub을 연결한다. 영상 인식의 고정 응답과 합성 자기 위치는 시험 fixture이며 위치 추정·파지·운반 성공 근거가 아니다. 모델 호출0, sweep 물리0.

범위는 세 로봇의 startup/접근/포트 reset·재시도, r1/r2 정렬·hover·하강·집기·HIGH·GO·모든 axial/lateral leg·하강·놓기·후퇴, r3 단독 집기·운반 자세 전환·heading·놓기, 문 대기와 소유권 인계다. 기존 S3 호스트에는 놓기 이후 출발지 귀환이 없다. 귀환은 미구현으로 별도 표시하며 통과/완주에 합산하지 않는다. 원래 주문의 B 운반 범위를 유지한다.

실행 전 선택: 새 번들 `zone-s3-sweep-v149` / `7.42.0`, seed14201 고정, v3 **호스트 렌더** 마운트 on, 공통 heading 기본 on(#422 포함), 두 로봇 공동 파지 carry만 기존 옆걸음 허용, DEV light, 기존 v98 exact speedups와 기록 버퍼링 유지. `posterior_content_v2`를 명시적으로 켠다. σ/수렴/성공 문턱·입자·RNG·관측 순서는 변경하지 않는다. 전체 단계 검사 오류0과 변경 시험 초록 후 커밋/push한 SHA로 스모크1회. CI를 기다리지 않고 main 병합하지 않는다. agent_lock 현재 실행이 끝나면 S3 우선, nice0. ENOSPC는 HOST_ERROR, raw 예산과 물리 실패 정지는 기존 계약 그대로다.

첫 통합 오류: `carry_go_N`은 채널에서 `lift`로 정규화된다. 두 GO가 소비된 뒤 첫 carry 제어 틱의 선행 로봇은 후행 로봇의 GO enum을 보므로 기존 `carry` 전용 예외가 거부했다. 같은 segment와 시각의 **실제 소비 GO**를 받은 경우만 허용한다. 일반 lift, 다른 segment, 미소비 GO, stale/abort는 허용하지 않는다. 기존 PairExecution.check의 두 GO 상호 확인은 유지한다.

캐시는 순수 posterior/cluster 요약만 변경된 배열에서 다시 계산한다. 관측이 없더라도 명령 예측으로 입자가 바뀌면 반드시 무효화한다. 배열 identity/시각만으로 캐시하지 않으며 uint64 비트 비교와 소유한 snapshot으로 제자리 변경·부호 있는0까지 확인한다. 반복 암호학적 digest 계산을 제거한다. 시각·health·pan offset·프레임 기록은 원래 호출마다 갱신한다. 이전82.6초는 **캐시 전** cProfile 수치이며 v148 후보는 이미0.83초였다. 추가 절감 대상은 남은 내용 해시 비용8.49초다.

표준 방법: 실제 구성요소를 stub 하드웨어에 연결하는 통합/lifecycle 검사는 [ROS launch_testing](https://docs.ros.org/en/ros2_packages/iron/api/launch_testing/)과 같은 경계 분리이며, 본 검사에서는 동기 Python 상태 주입으로 구현한다. 캐시 범위는 [Python functools](https://docs.python.org/3/library/functools.html)의 순수 계산 원칙을 따르며 가변 posterior 결과는 복사해 반환한다. GO 해석은 저장소 `harness/zone_pair_status.py`의 기존 fixed-enum 규약을 그대로 따른다.

결과는 완료 후 별도 JSON/표로 추가한다. 오프라인 명령·상태 동일성과 새 물리 성공 여부를 구분한다.

## 실행 전 오프라인 결과

단계 검사 **55건 / 실제 native issue 3161건 / 예상 밖 오류0**. 동시 GO 첫 carry 오류1건을 기존 승인 조건에서 재현한 뒤 수정했다. 고정 시야·합성 단계 진입으로 생성한 명령이며 실제 파지/운반 성공이 아니다. GO 미소비는 실제 endpoint에서 `PARTNER_MISSED_GO`로 계속 정지한다. reset 재시도는 세 로봇 모두 검사했고 최종 record도 strict JSON 직렬화를 통과했다. [검사별 결과](sweep-cases.json), [원본/소스 해시](sweep-green.json).

저장 v147 원본442프레임/로봇 재생에서 명령 SHA `95c7bb1babc22263fd45c83e16f352b6ba746a5f97a9cf8ecf93bcca838d4065`, 포즈/입자/가중치/RNG SHA `6138376fcdab9317a77c4ef47ac1625beaa71b4f4d04311f0b0160e06762bb8a`가 기존 off/v1 결과와 동일하다. 비교창 끝의 옛 혼합 축 오류도 그대로이며 새 오류가 아니다. [동일성](replay-equality.json). 로컬 S3 변경 시험26개 및 공통 PR422 시험34개 PASS, CI 대기0. 잠금 내 새 cProfile과 물리 결과는 아직 미완료다.

## 대기 중 추가 경계 검사 — 물리 전

첫 후보3d04ff32는 물리0이며 잠금 대기 실행기를 자체 종료하고 추가 검사했다. 최종 RGB 옆오차1cm/2cm에서 경로용3cm 반경 때문에 pair 명령이0이었고, solo step은 최종10cm 안의 불법0.06초 제안을 반복 생략했다. 공통 PR422 `256a1b0c6633609f2fb91584e01f77f133afb642`에서 호출자의 기존 position 허용치를 받으며, 실제 solo step도 현재 RGB 목표가 있으면 적법한 펄스로 대체한다. S3 pair는 기존 ALIGN_TOL_X/Y(3mm)를 넘긴다. 경로3cm·집기3mm·σ/인증 문턱 모두 그대로이며 모델 보정/seed 교체0. 단독과 pair 각1cm/2cm를 실제 native 포트까지 통과시키는6건을 sweep에 추가했다. 최소 펄스보다 작은 오차의 양자화 한계·실제 파지는 별도 관찰 대상이다.
