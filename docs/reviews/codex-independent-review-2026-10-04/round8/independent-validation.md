# 8차 독립 반증 검토 — 2026-10-04

편집·검증 담당이 각 분석 담당의 코드 경로·반례·부정 대조를 별도로 읽었습니다. 아래에서 **독립 재실행**은 실제 저장소 함수를 사용하는 합성 입력 실행을 뜻합니다. 실제 로봇·MuJoCo·모델·과거 raw 영상을 다시 실행한 결과가 아닙니다. 연구 원문도 아래 명시한 범위만 대조했습니다.

## 검증한 새 경계

### R8-R1 — 전송 뒤 실패한 모델 호출의 이미지 SIM 비용 누락

기준: PR #371 `1883c56a749dc89597d57f570d4a2243cbb9595d`.

`PairTrial.finish_call`은 text+image를 포함한 `total_billed`를 쓰지만, 공유 `ModelCallTransport._failure`는 `total_text_billed`로 실패 Attempt를 만듭니다. scheduler는 실제 전송 횟수를 대조해도 이 token 수를 이미지 포함 값으로 되돌리지 않습니다. production completer·ledger·budget·transport·scheduler와 본문을 바꾸지 않은 AST `PairTrial.finish_call`을 사용한 fake-wire 재현을 독립 실행했습니다. 전체 physics trial 재현은 아닙니다.

정상 protocol 응답은 archive/status가 실제 `ok`, 잘못된 schema 응답은 `invalid`로 각각 끝나며 둘 다 합성 text 100 + image 2×1490 = 3080을 청구합니다. 그에 비해 post-send non-normal completion·timeout·HTTP500·잘못된 envelope는 100만 청구해 2980이 누락됩니다. 이 fixture의 `zone_sim_cost.v1`에서 raw 차이는 0.596초, quantized 차이는 0.6 SIM초입니다. timeout의 고정 20초 항은 그대로 존재합니다. 전송 전 실패는 wire 0·call 0·unsent 1로 환불됩니다.

초기 재현에서 이름만 normal이던 control도 schema-invalid였던 점을 편집자가 지적했습니다. 담당자가 이를 수정하고 `outcome == 'ok'` assertion을 넣은 **최종 버전**을 위와 같이 독립 재실행했습니다. 실제 provider usage 6100은 non-normal fixture에서도 보존됩니다. 이 finding은 deterministic SIM 청구의 누락이며 공급자 비용 전체 소실이나 모든 모델 오류의 결과 소실이라는 과거 주장을 되살리지 않습니다.

### R8-R2 — quota 신호가 긴 HTTP error body 뒤에 놓인 경우

실제 ledger의 저장 body 해시는 유지되지만 rate-limit 분류가 앞부분 excerpt에만 의존합니다. synthetic 정상 reply 뒤 error JSON의 quota signal 앞에 700문자를 넣으면 403/500의 `check_health`가 계속 진행하고, 짧은 403 또는 status 429는 `RateLimited`로 중단되는 대조를 독립 재실행했습니다. 실제 provider가 이 body 배치를 보냈다는 증거는 없습니다. 현재 우선 blocker 대신 **조건부 P3 hardening** 부록으로 분리합니다.

### R8-R3 — finalization 실패와 영속 실행 분류의 불일치

기준은 같은 #371 `1883c56`입니다. 평가 담당이 runtime 담당과 별도로 최종 재현을 실행하고 실제 `scripts/run_pair_llm → pair_llm_live → run_pair_case → run_attempts` caller를 대조했습니다. 원래 case/finally 함수 본문과 실제 ledger·budget·run_attempts를 사용하고 세계·모델 wire·평가 작업은 fixture로 분리했습니다.

정상 fake POST 1회(공급자 100 token 보존) 뒤 student record·LLM artifact·finalize callback·backend close 중 한 군데에만 ENOSPC를 주입하면 `status=HOST_ERROR`와 구체적 error field는 남지만 `failure_class=None`, SQLite run `finished`, attempt failure `None`이 됩니다. clean control은 정상 `COLLECTED_UNQUALIFIED/finished`이며 전송 전 host-error control은 `infra:HOST_ERROR/failed`로 분류됩니다. 두 독립 결과는 측정 wall latency 외에는 같았습니다.

한정 범위를 유지합니다. CLI는 status를 보고 오류 종료하며 실패 전체가 숨겨지지 않습니다. 요청 뒤 재시도하지 않는 것은 정상 계약입니다. `protocol_complete=True`는 bounded loop 완료를 뜻하므로 자체 결함으로 세지 않습니다. 이 fixture는 단일 finalization 오류 뒤 최종 result/metrics 쓰기가 성공하는 조건입니다. 지속 ENOSPC로 마지막 write까지 실패하면 바깥 exception 분류가 작동할 수 있으므로 모든 disk-full 상황이 `finished`라고 일반화하지 않습니다.

### R8-G1 — 잘린 ROI 끝이 실제 beam lower edge로 채택되는 조건

기준: PR #363 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`의 `harness/own_beam_edge.py`.

`_first_run_end`는 연속 True run이 입력 배열 끝까지 이어져도 마지막 index를 반환합니다. `edge_line`은 `mask[40:300, c]`만 전달하므로, 실제 lower boundary가 300행 밖에 있어도 299행을 경계로 채택합니다. 실제 edge가 중심 340행·기울기 ±0.04인 두 합성 영상 모두 기울기 약 0, 중심 y=299, inlier 90개로 바뀌는 반례를 독립 재실행했습니다. 두 영상에서 300행도 같은 foreground이며, blank 영상은 검출되지 않고 실제 299행에서 끝나는 영상은 300행 background라는 부정 대조도 확인했습니다.

실제 HIGH caller는 `HighPoseSource.on_frame → BeamEdgeTracker.observe`이며 loaded·settled·issued HIGH 조건에서 tracker를 활성화합니다. `HighController._wait_carry`가 그 `beam_edge.available`을 읽습니다. 현재 HIGH 경로와 연결된 **조건부 edge-reference/yaw 측정 오류**입니다. steady한 잘림 입력에 default settle/reference 과정을 적용한 tracker가 available 상태가 되는 것도 재실행했습니다. 물리 실행에서 이 영상 조건의 빈도·제어 영향·실패율은 측정하지 않았습니다. availability 하나가 true라고 부모 carry barrier의 나머지 조건까지 통과하는 것은 아닙니다.

이 반례의 잘못된 점 90개는 한 직선에 모두 놓입니다. 따라서 residual 기반 robust fit으로만 해결된다고 해석하지 않습니다. 299행의 진짜 경계까지 일괄 버리는 제안도 아닙니다. 실제 경계와 관측창에 잘린 run을 구분하는 검출 계약이 먼저입니다. grip monitor를 필수 센서나 단계 전환 조건으로 바꾸자는 주장이 아닙니다.

### R8-E1 — 과거 발화 truth가 미래 departure에 종속되는 조건

기준: main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`; 관련 evaluator/referee 코드는 분석 checkout `f2577bb5`와 동일합니다.

`Referee.trial_rows`는 종료 때 아직 standing인 item의 confirmation만 남깁니다. 실제 runner의 `write_study → apply_to_record`가 이 값을 trial의 deliveries로 쓰고, `check_claim`은 이를 발화 시각 기준 truth 근거로 사용합니다. 발화 t=3, confirmation t=2까지 동일한 입력에서 이후 t=4 departure 여부만 바꾸면 truthful_share가 1 → 0이 되고, 다시 배송하면 1이 되는 반례를 실제 `Referee → apply_to_record → parse_trial → dialogue_metrics/summarise`로 독립 재실행했습니다.

두 주문 중 한 주문만 완료한 구성이라 첫 confirmation 뒤에도 실행이 이어질 수 있습니다. 최종 delivery_rate의 0.5 → 0 → 0.5는 이 반례에서 올바릅니다. 문제는 `check_claim`이 명시한 **발화 당시 truth**가 미래 사건 때문에 바뀌는 것입니다. 최종 standing을 위한 projection과 과거 시각의 claim evidence를 분리해야 하며, 모든 confirmation을 기존 deliveries에 단순 합치면 최종 배송 판정이 바뀔 수 있습니다.

범위는 표준 zone-study 자연어 평가입니다. 현재 두 로봇 first-E2E blocker나 실제 연구 결과의 오류 빈도로 확대하지 않습니다. 선택 API의 `slot_states` 배열 순서 반례는 runner 생성 경로가 확인되지 않았으므로 보조 근거로만 남깁니다.

## 기존 지적과 새 수정의 현재성

### #363의 start-relief 수정은 현재 반례를 실제로 바꿉니다

`0d7c5eb3`의 guard 함수와 공개 테스트 입력을 사용하는 pure geometry 재현을 독립 실행했습니다. 공개 0865 진단의 첫 8.7초 R2 candidate는 현재 `start_outside_pair_enters`로 거부되고 R1 candidate는 허용됩니다. 새로운 enters 검사를 메모리에서만 제거한 mutation control은 R2를 다시 허용합니다. pair scope에서는 거부가 유지되며 검사 후 내부 residual/loaded flag 복원도 확인했습니다. 원본 source는 변경하지 않았습니다.

그러므로 공개 0865의 뒤이은 9.0초 실패를 현재 head의 실행 결과로 반복하지 않습니다. 이것은 알려진 한 candidate의 새 거부 확인이지 최신 head의 전체 E2E 성공 검증이 아닙니다.

### 같은 tick peer abort 뒤 dispatch는 현재도 별도 경계로 남습니다

최신 source에서 추출한 원래 method와 실제 `CameraRobotPort`, synthetic motor sink로 재실행했습니다. 같은 tick에 R1 명령이 수집된 뒤 R2 실패/Team.poll이 두 actor를 terminal로 만들지만, 수집된 R1 명령이 이후 issue되어 motor `[.1, .1, .1, .1]`을 받습니다. 다음 0.05초 hold에서는 모두 0이 됩니다. 이는 최종 dispatch 직전 terminal/abort veto 누락이라는 기존 finding의 현재성 확인입니다. 0.15초 lease 전체 잔여 주행이나 실제 충돌을 입증한 결과가 아닙니다.

## 연구 해석의 독립 제한

- [OpenCV 4.13 fitLine 공식 문서](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html)의 fitLine 절을 직접 확인했습니다. M-estimator는 점과 직선 사이 residual에 따른 손실을 사용합니다. 따라서 ROI 잘림이 만든 완벽한 가짜 직선과 sparse outlier contamination은 별개라는 판단은 UGRP 합성 반례와 결합한 **우리의 추론**입니다.
- [ATAP v1](https://arxiv.org/html/2609.23504v1)의 문제 정의·방법 절을 직접 확인했습니다. 입력에는 RGB-D와 end-effector pose가 있고, verification과 competing-hypothesis disambiguation을 함께 고려합니다. 논문은 disambiguation likelihood를 surrogate로 명시하므로 이를 보정된 확률이나 UGRP의 안전 보장으로 옮기지 않습니다. UGRP에 대한 적용은 허용 입력으로 가설을 구분하는 다음 관측을 고른다는 설계 제안에 한정합니다.

## 증거 범위

독립 재실행 로그는 전달본의 round8 증거 묶음에 별도 보존합니다. 원본 production source는 수정하지 않았습니다. 각 finding의 상세 절차와 source hash는 해당 분야 메모를 기준으로 합니다. 1–7차 13개 동결 원고는 수정하지 않습니다.
