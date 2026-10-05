# R25 — REAL trace 문서·지원 경로의 독립 해석 QA

main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 문서와 선정 source를 읽었다. 실제 하드웨어·카메라·외부 통신·과거 trace·이미지·모델은 열거나 실행하지 않았다. 이 검토의 대상은 기록의 의미와 현재 연결 범위이며 물리적 원인이나 실제 운영 상태가 아니다.

**문서/호출 범위 해석은 PASS다.** `real_trace_system.md`의 요청 단위 run 생성·planner 기록·자동 분석을 표준 CLI의 모든 실행에 자동 적용된 기능으로 읽어서는 안 된다. `harness.cli.main`은 `run_loop`를 호출하지만 run을 create/activate/finish하지 않는다. 반면 보존된 `harness.web.py`에는 execute+agent_intent 및 REAL 분기의 create_run, context 활성화, finish_run이 있다. 이 차이는 모든 skill trace의 부재를 뜻하지 않는다. `robot_actions._run_skill_process`는 이미 활성인 run context를 자식 env에 전달할 수 있고, remote deploy의 `_trace_context`는 standalone run ID도 만들 수 있다.

| 혼동하기 쉬운 계약 | 유지할 해석 |
|---|---|
| 구형 UI 퇴역 | `browser_ui_retirement_20260923.md`는 화면/표준 `--chat`/런처를 제거하고 내부 HTTP API·상태 처리는 보존했다고 명시한다. web 전체가 금지·삭제됐거나 내부 API도 존재하지 않는다고 쓰지 않는다. 보존 API가 곧 현재 GUI 또는 모든 CLI의 기본 경로인 것도 아니다. |
| 운영 문서의 위치 | `docs/README.md` 22행은 trace 문서를 실물 운영 참고로 유지한다. 날짜/진입점을 확인하며 사용해야 한다는 맥락이다. 이 인덱스만으로 특정 자동 연결이나 실제 장치 운영 완료가 증명되지는 않는다. |
| 프레임 보존 | recorder 문서의 4Hz sampling과 causal-trace 문서의 all-consumed-frame 설명은 각 caller의 env/default를 함께 확인해야 한다. 기록 시점 정책과 이후 선별 보존 정책도 다르다. 이 QA는 현재 저장된 frame 수를 검사하지 않았다. |
| command completion | 문서 자체가 PWM·차체 발행 명령을 실제 joint 위치·이동 거리와 구분한다. completion/stop event 이름만으로 물리 정착이나 실제 정지를 인증하지 않는다. |
| RCA와 인과 | `TARGET_LOST_AFTER_*`는 선택된 관측 사이의 기록 명령을 기반으로 한 진단이다. 어느 물리 메커니즘이 원인인지 또는 그 명령을 하지 않았으면 결과가 달랐는지를 확정하지 않는다. best-effort 로깅도 오버헤드가 0이거나 모든 자료가 완전하다는 보증은 아니다. |

## clock 후보에 대한 source challenge

`scripts/red_block/recorder.py:event`는 Pi 프로세스의 `time.time()`과 `time.monotonic()`, event_seq를 기록한다. `scripts/red_block/deploy.py`는 caller host에서 `time.time()`을 측정하고, remote trace 복사 후의 host `ended_wall_s`를 span result에 쓴다. `trace_analysis.analyze_run`은 실패 span의 이 값으로 Pi 이벤트의 wall_time_s를 제한한다. `_event_time/_last`에는 clock domain 변환이 없다. 양쪽 API 이름이 같다고 동일 clock domain이나 offset=0이 보장되지는 않는다.

따라서 **Pi의 양의 offset이 host 종료·회수까지의 시간 여유를 넘어서는 경우** 일부 마지막 이벤트가 summary 선택에서 제외될 수 있다는 조건부 후보는 source와 맞는다. 일반적인 offset 존재만으로 항상 누락된다고 하거나 실제 장치에서 그 차이가 측정됐다고 쓰지 않는다. 변수명 `failure_time`도 정확한 Pi 실패 발생 시각이 아니라 host wrapper 종료 cutoff다. archive의 이벤트 보존과 분석 summary에서의 미선택은 별개다.

선정 recorder/deploy/analysis/execution_trace와 REAL trace/recorder/network runbook에서 NTP/chrony/time-sync/offset 보정 계약은 확인하지 못했다. 이는 운영 OS 전체가 동기화되지 않았다는 증명이나 전 저장소의 전수 부재 증명이 아니다. 다른 호스트의 monotonic 값을 바로 비교하는 대안도 정당화되지 않는다. 향후 수정 선택은 같은 remote domain의 종료 receipt/event_seq, 명시적인 clock mapping과 그 불확실성, mapping 미확인 시 증거는 보존하되 시간 관계를 unavailable로 남기는 분석 정책 등에서 판단할 수 있다. 마지막 선택은 **분석 증거 보존**이며 로봇 guard를 완화한다는 뜻이 아니다.

## 독립 재실행과 최종 원고 검토

`real-trace-clock-repro.py`를 별도의 새 `TemporaryDirectory`와 Python subprocess에서 실행했다. 원래 세 Git blob의 hash guard를 유지했고, 독립 출력은 `real-trace-clock-result.json` (Mac 전달본 증거)와 **byte-identical**이었다. exit code는 0, 결과 SHA256은 `de5a9fa25c63c2cfba29e96f30c2f1f8ecfa74b5b9f44378d591047ee30f68c0`이다. 재현 코드 SHA256은 `76110da498e57fc7b5dc36306d6f17fa2646877335a50e248805c675c73d8406`이다. 카메라 frame/명령은 작성한 metadata이며 이미지 bytes, detector, actuator, SSH·복사·배포 또는 기존 run을 실행·열람한 것이 아니다.

7개 사건의 sequence·monotonic 값·wall time 이외 내용과 `FAILED` 상태는 네 조건에서 유지된다. offset 0/Pi −5초/공통 epoch +50초에서는 마지막 frame과 visible→lost 전이가 선택되고, Pi +5초가 작성한 host cutoff 여유를 초과하는 경우에만 해당 요약 근거가 빠져 `UNCLASSIFIED_FAILURE`가 된다. 따라서 **선택된 실패 요약의 clock-domain 의존성**은 독립 실행으로 확인했다. 원본 event 삭제, 실제 장비의 skew, 물리 원인, 과거 분석 오류 빈도 또는 모든 stderr 분류의 변경으로 확대하지 않는다.

`real-trace-clock-independent-check.json` (Mac 전달본 증거)에 재실행과 16개 source-manifest 항목의 Git blob hash 일치를 기록했다. hash 전수 대조는 16개 파일의 전체 동작을 새로 감사했다는 뜻이 아니며, 의미 검토 범위는 위 문서·선정 caller·writer/consumer 시간 연결이다. [최종 원고](clock.md) SHA256 `c29bae8571471ea534193f584610654995cb73ea4f8e10935c7779a8e289aa14`의 조건부 P2 범위와 수정 방향을 **PASS**로 확인했다. 구현 변경·물리 실험은 수행하지 않았다.

## 이슈 선정표의 한정된 일관성 검토

[16개 이슈 선정표](acceptance.md) SHA256 `9abc0811e8efd9c0deedd6f6ff83158a6633404e99ea7a775daba24edc2d982d`의 문서 의미만 교차 검토했다. 표는 R19 공식 조회 시점과 이번 미재조회·미해결 처리를 명시하고, source/작성자 DEV/교사 예외의 제한된 근거를 실물 인수·최종 학생 수행·등록 연구 완료로 바꾸지 않는다. #214와 #226은 동일 R25 trace 경계를 한 번만 검토한다고 명시한다. 이 범위는 **PASS**다. 전체 이슈 상태를 새로 조회하거나 각 인수항목의 모든 원문·실행 증거를 다시 검증한 QA가 아니며, 저장소 전수 검토 완료나 실제 인수 증거 부재를 선언하지 않는다.

선정표 끝에 추가된 결과 원고 링크와 선정 당시 범위 보존 문장도 확인했다. 새 실행이나 범위 확장 없이 위 판정을 유지한다.
