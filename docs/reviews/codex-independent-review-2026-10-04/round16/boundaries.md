# 16차 좁은 경계 — PF, recovery, column

새 구현 결함0개다. 같은 source라도 수식 일치·기록 보존·좌표 정합과 실제 pose 정확도·task 성공은 별도 질문이다. 상세 source 원고·재현·golden·독립 QA는 Mac `round16/evidence/`에 보존했다.

## PF

66ff의 새 roughening은 resample된 subset의 range에 `K·m^(-1/3)`을 곱한 축별 Gaussian jitter를 더한다. 새 injected 후미 입자는 제외한다. Exact source로 resample 없음→particle/RNG 불변, K=0→기존 경로, K=.2→동일 systematic-resampling prefix 뒤 정확한 다음 Gaussian draw와 일치함을 독립 확인했다.

한 입자로 완전히 collapse하면 range=0이라 roughened count가 늘어도 jitter=0·unique pose1개다.144회 같은 authored full-rank scan의 receipt144개와 exponent 합1.9862068966도 유지된다. Count만으로 다양성 회복·독립 정보량·실제 uncertainty calibration을 인증할 수 없다. Gate 함수가 같아도 particle cloud/RNG가 변하면 실제 후속 frame 판정이 같다는 보장은 없다.

넓은 원형 cloud의 순열이 `unwrap` spread를 바꿀 수 있는 수학 반례도 있지만, actual selected robust override는{}이고 기본 recovery는None이다. 현재 uniform injection이 그 상태를 만든다는 추론은 기각했다. Broad-yaw의 실제 trajectory 도달성은 미입증이라 새 P2로 세지 않는다. 원고 `pf-v3-delta-boundary.md`, script/result·독립 QA를 보존한다.

## Recovery

실제 `LookRecovery`와 stage reporter/JSON writer를 합성 clock·완료 job에 연결했다. 두 시도 exhaustion 뒤 active prefix는 `STAGE_PROBE_FAILED`와 조기 종료를 남긴다. 일반 bounded 경로는300 fake clock까지 `COLLECTED_UNQUALIFIED`로 수집하면서 상세 exhaustion을 보존한다. 양쪽 physical success는None, research/promotable은False다. 수집 완료를 task 성공으로 읽을 근거가 없다.

별도 actual job-end bookkeeping 대조는 같은 attempt ID와 outcome을 연결해 한 번만 정리하고 pans_only를 해제한다. 종료된 같은 job을 반복 관찰해도 시도가 추가되지 않는다. Admission/30초 relook 소요 시간·전체 command batch/dispatch·실제 guard cleanup·physics를 검증한 것은 아니다. Done와 failure 동시 tick 우선순위는 source-only 범위로 남겼다. 상세 두 원고는 `recovery-reporting-boundary.md`, `recovery-job-end-boundary.md`다.

## Columns

현재66ff HIGH의 기본96열/strip half2에서 실제 detector center 목록과 measured camera column model의K·배열 순서가 맞는지7개 source hash와 실제 producer/consumer를 교차 확인했다. 추가 실행을 만들지 않은 source-only negative다.

Mean-intensity strip 검출과 center-ray predictor는 같은 좌표 identity를 공유하지만, 유한 strip의 평균 영상 반응이 항상 center ray의 정확한 관측이라는 증명은 아니다. 실제 RGB·undistortion/HSV·occlusion·pose uncertainty 정확도나 physical camera 일치는 검사하지 않았다. 원고 `column-strip-coordinate-boundary.md`와 독립 QA를 함께 보존했다.

이번 결과는 [현재 camera posture 문제](posture.md)와 [carry-align 통계 해석](research.md)을 판단할 때 어떤 설명을 이미 배제했고 무엇이 남았는지를 좁힌다. 실제 실패율이나 개선 효과는 계산하지 않았다.
