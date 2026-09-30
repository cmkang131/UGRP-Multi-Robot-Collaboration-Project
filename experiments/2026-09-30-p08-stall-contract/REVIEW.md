# #293 읽기 전용 검토표

검토 SHA `d86cc82eedbe0c6693eaf808c54ce43387723f1d`, PR 상태 DRAFT, GitHub 승인 리뷰 없음.
main 연결부 기준 `d17ca4345affef8cf027e121cf1f3197b36c23e0`. P0 없음. **실제 controller 연결은 준비되지 않았다.**
이 표는 #293 오프라인 참조의 계약과 연결 전 차단점을 구분한다. 원본 파일은 수정하지 않았다.

아래 `d1_*`, `PREREG_DRAFT`, `STAGING_PLAN`은 #293의
`experiments/2026-09-30-stall-detector-d1/` 아래 파일이다.

| 등급/항목 | 정확한 위치 | 검토 결과·반례·남은 계약 |
|---|---|---|
| 확인 — 허용 입력 | `d1_detector.py:160`, `PREREG_DRAFT.md:19` | `detect(frames,timestamps,commands,parameters)`와 NumPy뿐. simulator/GT/contact/peer/joints/file I/O import 없음. RGB와 명령 이외 상태를 읽는 내부 경로 없음 |
| P1 연결 차단 — 소유 provenance | `d1_detector.py:45`, `d1_detector.py:107`, `d1_detector.py:160` | 배열과 구간에는 robot/camera ID가 없어 같은 shape의 peer/top RGB도 함수 자체로 구별 못 함. 승인된 자기 입력 생산자와 strict adapter가 필요. P08의 fake 타입 검사만으로 실제 생산자의 정직성까지 증명하지 않음 |
| 확인 — 기준 부족/시작 정체 | `d1_detector.py:206` | 기준 <5개면 INSUFFICIENT_REFERENCE, 기준 ≤1e−12면 INSUFFICIENT_SIGNAL. 시작부터 일정한 어두운 영상은 무경보/신호 부족. 실제 시작 정체 성능을 증명하는 영상은 아님 |
| 확인 — ROI/결측/지터 | `d1_detector.py:197`, `d1_detector.py:213`, `d1_detector.py:225` | 예정 check를 지우지 않고 MISSING_FRAME/INVALID_ROI로 남기며 연속 횟수 초기화. ≥95% 미달이면 사후 INSUFFICIENT_COVERAGE; 인과적 경보는 보존하되 평가 TP로 구제하지 않음 |
| P1 연결 차단 — 잘못된 시각 분모 | `d1_detector.py:172` | 중복 `[0,0]`, 역행 `[1,0]`, NaN은 ValueError이고 IntervalResult가 없음. 원본 보존 후 명령 단위 UNKNOWN_INPUT/관측 실패로 남길 외부 ledger가 필요. 예외를 삼키고 해당 명령을 빼면 분모 축소 |
| P1 연결 차단 — 짧은 명령 평가 | `d1_detector.py:187`, `d1_evaluation.py:59` | `[0,4)`는 UNSUPPORTED_SHORT_COMMAND, checks=(). `score_interval(result,[])`는 전체 예정 grid 부족으로 ValueError. 문서는 실패 분모 보존을 요구하지만 cohort aggregator/오류 ledger는 아직 없음. 짧은 구간을 정상 무경보로 세거나 drop하면 안 됨 |
| 확인/미결 — 저속·구간 분할 | `d1_detector.py:45`, `d1_detector.py:170`, `PREREG_DRAFT.md:38` | 탐색의 ≥0.03 m/s cutoff는 없음. 다만 CommandInterval에는 속도·방향이 없으므로 발행 이력에서 일정한 비영 병진 구간을 분리하는 생산자는 별도 필요. 기준 부족인 저속은 미검출/관측 실패로 유지 |
| 확인 — 30/60와 전체 90% | `PREREG_DRAFT.md:69`, `PREREG_DRAFT.md:132` | 5기전×6=30 고정, 독립 정상 3leg×5속도×4=60. 영향 로봇 모두 검출해야 case TP. 시작 정체 6개를 놓치면 24/30=80%, ≥27/30 및 기전별 ≥5/6 모두 실패. 24건/4기전으로 줄이지 않음 |
| 확인 — 불완전/실패 구분 | `d1_evaluation.py:15`, `PREREG_DRAFT.md:77` | 기전 6개 미달/예비 소진은 INCOMPLETE. 수집된 정체의 기준 부족·ROI·지터 미검출은 30건에 남는 FAIL. 출력 실패로 예비를 고르거나 관측 기간을 늘려 구제하면 안 됨 |
| 확인 — 탐색과 확증 | `PREREG_DRAFT.md:11`, 연구 `README.md:81` | 기존 18/18은 9케이스×2로봇의 사후 선택 결과이며 새 확증 아님. 주 (0.4,2), 보조 (0.5,3) 고정. 보조 threshold·부분 잡음 조합 통과로 주 threshold 실패를 대체하지 않음 |
| P1 알려진 적용 한계 — 전체 잡음 범위 | `PREREG_DRAFT.md:159` | #293 기록의 시각 ±0.1초 지터만으로 유효율 약78–81%, 95% 실패. 이 수치는 #293의 이전 합성 결과 인용이며 P08에서 새 측정한 감도가 아님. 12조합×3 RNG의 AND 기준과 시작 정체 문제는 봉인 전 연구 목적/가설 결정 필요; 개발 영상에 맞춘 재선택 금지 |
| P1 연결 차단 — 중단 순서 | `harness/zone_pair_executor.py:287`, `harness/zone_pair_executor.py:589` | 기존 abort는 enum→내부 큐 제거→자기 실패 사건이고 host 예정 명령 취소는 poll에 있음. hold 적용과 host 취소 완료 전에 사건을 받는 호출 순서를 별도 검증해야 함. P08 fake가 통과해도 이 경로의 실제 순서를 고쳤다는 뜻이 아님 |
| 확인/미결 — 다음 결정 | `harness/zone_own_executor.py:470`, `harness/zone_study_integration.py:442`, `scripts/run_zone_study_integration.py:492` | 자기 job_failed→failure trigger/available 연결은 있음. 실제 시간은 host chunk, 기존 호출/최소 간격/예산 관문에 따름. fake scheduler 검사는 실제 LLM 호출이나 즉시 복구 증명이 아님 |

## 탐색 원형을 실시간으로 재사용하지 않는 이유

`experiments/2026-09-30-stall-detection-research/stall_detector_offline.py:32`의 탐색 수집은
명령 ≥0.03 m/s와 길이 ≥5초만 선택하고, `:63` 이후 lift/jaw GT로 창을 거른다.
ROI/결측 창도 `continue`로 빠진다. 따라서 이 파일의 `process()`를 runtime 입력 adapter로
그대로 쓰면 안 된다. #293은 이 gate를 제거한 별도 NumPy 참조이고 미래 프레임도 선택하지 않는다.
P08은 탐색 원형을 import/실행하거나 개발 영상을 재분석하지 않았다.

## 수치와 관찰의 범위

`review_d1.py`는 정확한 Git blob을 메모리에 읽고 pure NumPy의 일정 영상/결측/잘못된 시각만 넣는다.
시작 정체의 합성 대리 입력, ROI 무효, empty 입력, 짧은 명령 평가 예외, 세 가지 시각 예외,
gap의 예정 25창 보존과 30/24 기전 수 관문을 확인한다. 실제 성능 분모에 넣지 않는다.
문서/블롭 SHA·출력 원본 해시는 `verification.json`에 남긴다. 인터페이스가 달라지면 새 head를 다시 검토해야 한다.
