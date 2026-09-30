# P06 — 평가 전용 심판과 원본·TensorBoard 연결

Refs #223, #224, #226. READINESS S11/S14의 **synthetic 계약 검사**다.
물리·시뮬레이션·렌더·모델 호출·실제 실험 코호트는 수행하지 않았다.
공용 대시보드 게시, 기존 raw/snapshot 변경, Drive 작업, 병합은 없다.

독립 검토 A303-1/2/3 후속은 [REVIEW_FIXES.md](REVIEW_FIXES.md)를 따른다.
최초 203개 검사에 빠졌던 식별값 교환·terminal 누락·v6e 고정 소스 검사를 추가했다.
정상 GitHub CI는 실행하며 생략·취소하지 않는다.

- 기준 감사 SHA: `a8094cc14e098a55483f53a3c49bf6a0b116043d`.
- 시작 소스: `d17ca4345affef8cf027e121cf1f3197b36c23e0`.
  감사 SHA 이후 차이는 process-review 기록뿐이며 P06 대상 코드는 같다.
- 작업: `/Users/changmin/projects/ugrp-wt/e2e-p06-evidence`, `codex/evidence-referee`.
- PR #257/#241/#291과 READINESS/열린 PR을 읽고 fetch했다. #298에 범위를 알렸다.
  P05/P02/P09의 제어·드라이버·host_spec 구현은 바꾸지 않았다.

## 발견과 변경

1. `efficiency_metrics`가 `orders_complete` 문자열만 보고 성공을 셌다.
   이제 주문 ID/개체 ID·종류·목적지의 최종 배송 상태, 평가 상태, failure class를
   함께 확인한다. 중복 order/item ID를 거절한다. 같은 색 다른 개체는 named 주문을
   채우지 않고 반복 배송은 같은 item ID 1개로 센다.
2. 정착 시작을 배송 시각으로 기록하는 기존 정의에서 확인 시각이 사라지면 cap 뒤
   확인을 cap 안 성공으로 소급할 수 있다. 심판 v3는 `confirmed_sim_s`와
   `observed_end_sim_s`를 함께 보존하고, 확인이 종료/cap 뒤면 배송으로 세지 않는다.
   전체 발자국·높이·선속도·손에서 놓임·2초 연속 정착의 기존 기준은 유지한다.
   truth 누락 표본은 연속 정착/기존 배송을 무효화하고 비유한 시각·개체 종류 변조를 거절한다.
3. 러너의 `result=None`/`trial=None` 종료에는 trial record가 빠질 수 있었다.
   별도 후보 `scripts/zone_study_evidence_writer.py`는 HOST_ERROR·API·정책실패·중단/
   미평가의 터미널 기록을 남기고 불완전성을 표시한다. 기존 runner는 v6e가 고정한
   바이트로 복원했으며 이 후보를 자동으로 호출하지 않는다. 새 실행기에서 예외·중단을
   잡고 실제 SIM cap·scenario ID·attempt를 전달하는 연결은 후속 등록 때 필요하다.
   실패 기록을 만들기 위해 scheduler를 추가 실행하지 않는다. 시작 전 실패도 같은
   scenario/seed 비교에 남기며 불완전 모델 기록은 알려진 하한과 미상 총계를 구분한다. 외부 강제 종료·ENOSPC로 기록 쓰기 자체가
   불가능한 경우까지 디스크 기록을 보장하는 수정은 아니다.
4. 통합 run의 전용 TensorBoard adapter를 추가했다. raw manifest의 전체 파일/해시,
   bundle digest, trial/result/evaluation/manifest 연결을 검증하고 숫자를 다시 계산한다.
   파일 누락·변조·변환 중 변경은 이벤트 미게시로 끝난다. 성공·실패·중단/미평가는
   시도 단위 분모에 남긴다. 알 수 없는 값은 scalar로 만들지 않는다.
5. 요청 원문과 모든 요청 원본 이미지 검증은 미리보기 표본 수와 독립적이다.
   TOP 설정 JSON과 영상 파일 등록을 분리하고 `top_rgb`와 `gt_visualization`을 구분한다.
   synthetic 결과는 명시 opt-in + 임시 output만 허용한다.

공용 registry 변경은 `scripts/run_ci_tests.py`의 새 테스트 파일 **한 줄**뿐이다.
실행 번들/workflow 번호는 예약하지 않았다. 실행 전에 코디네이터가 새 심판 profile과
합성된 소스/번들을 고정해야 한다. 현재 PR은 새로운 실행 승인이나 과거 성공 판정의 승계가 아니다.

## 검증 범위

[검증 기록](VERIFICATION.md)에 최종 명령·선별 node ID·결과·JUnit 해시를 남긴다.
모든 fake JSON/JPEG/MP4/event는 OS 임시 폴더에서만 생성한다. 이 폴더에는 테스트
코드/검증 문서만 있으며 fake 자료를 연구 결과로 커밋하거나 공용 snapshot에 게시하지 않는다.

`referee_truth`는 가짜 MuJoCo 모듈·가짜 body/contact/velocity 값으로 변환 계약만 검사한다.
MuJoCo 모델 생성·`mj_forward`·물리 step·렌더를 실행하지 않는다.
네 조건의 실제 study 입력/요청 builder와 scheduler에 고정된 자기 프레임·명령·수신
메시지를 넣고, fake 평가 truth/TOP 설정·영상/hidden event만 바꿔 payload/request/wake가
같은지 대조한다. 심판 완료는 loop 정지만 바꾸고 로봇 완료 통보를 생성하지 않는지 검사한다.
이는 실제 물리 외란의 효과나 카메라 재배치의 영상 불변성을 증명하는 실험이 아니다.

## 코디네이터에게 남은 실제 확인

[TensorBoard의 P06 절](../../docs/tensorboard.md#zone-study-통합-실행-평가--원본--event-계약-p06)에
첫 실제 결과의 snapshot → event readback → 공용 logdir → 영상 → pin/HParams 검증을 적었다.
D1 0.1초/1초 비교창은 1 Hz 기록만으로 재현할 수 없다. 실제 사용 프레임 쌍의 원본·촬영
시각·해시를 보존하고 빠진 쌍은 `insufficient_evidence`로 남겨야 한다.

현재 미확인: 새 고정 소스의 실제 배송·hidden event·terminal 종료, 실제 provider 정산,
새 실제 snapshot/event, 공용 logdir와 영상 재생, 브라우저 pin/HParams 화면.
이 문서는 S11/S14 전체 또는 E2E 파일럿 완료 선언이 아니다.

## 참고 자료

- [READINESS / P06 원문](https://github.com/kcm0127-dotcom/ugrp/pull/298)
- [심판·hidden event PR #257](https://github.com/kcm0127-dotcom/ugrp/pull/257)
- [캡처 정책 PR #241](https://github.com/kcm0127-dotcom/ugrp/pull/241)
- [D1 탐색 기록 PR #291](https://github.com/kcm0127-dotcom/ugrp/pull/291), [사전 등록 초안 #293](https://github.com/kcm0127-dotcom/ugrp/pull/293)
- [평가 지표](../../harness/zone_study_eval.py), [심판](../../harness/zone_study_referee.py),
  [기록 후보](../../scripts/zone_study_evidence_writer.py), [변환기](../../scripts/tensorboard_tools/zone_study.py)
