# beamact5 READY/done 오프라인 재계수와 누적 관문

코드 수정 전 기준은 병합된 [beamdiag 요약](../2026-10-16-beamdiag/summary.json)과 원본 [robot 원장](../2026-10-16-beamdiag/robots.csv)이다. A/B는 합산하지 않고, 원본 RGB/명령/시작 프로토콜은 gcp2에 있어 이 작업자가 읽지 않았다. 원본 실행 경로와 파일 해시는 요약의 `runs[].raw`, `original_hashes`에 보존되어 있다.

## 기존 거부 분포 (기술 범주, 인과 아님)

|기술적 거부 범주|A /20|B /20|막은 물체|최소 간격|
|---|---:|---:|---|---|
|배정 끝 접근 미획득|4|7|UNKNOWN:not_observed|null|
|같은 끝 동시 근접 점유|1|3|UNKNOWN:not_observed|null|
|반대 끝 정렬 자리 먼저 방문|3|5|UNKNOWN:not_observed|null|
|한 로봇 몸통 시야가 절반 이상|4|3|UNKNOWN:not_observed|null|
|배정 끝 정렬 자리 미도달|4|1|UNKNOWN:not_observed|null|
|양쪽 자리 방문 후 자세 정렬 미완료|4|1|UNKNOWN:not_observed|null|

기존 원장에는 장애물/충돌/간격 계측이 없어 물체 이름을 만들지 않고 `UNKNOWN:not_observed`, `min_gap_m=null`로 남긴다. `target_finger_min_gap_m`는 평가용 대상-손가락 signed gap이며 장애물 여유가 아니다.

## READY 오프라인 재계수

저장된 protocol audit 집계는 A `GO_N=20`, B `GO_N=20`, 각 arm `GO_before_joint_alignment_N=20`이다. 따라서 원래 GO 시각에 정렬 조건을 요구하면 **0/40**만 READY/GO로 인정된다. 두 로봇이 실행 중 한 번이라도 각자 정렬된 실행은 **4/40** (A 1/20, B 3/20)이며, 이는 평가 truth 기하의 첫 정렬 시각을 쓴 **상한**이다. 2프레임 streak를 더한 가장 이른 witness READY는 각각 30.8 s(A8329000), 18.2 s(B8329000), 12.7 s(B8329003), 58.1 s(B8329015)이고 cap은 59.9 s다. 이는 성공률이나 실행 가능성 주장이 아니다.

정확한 후속 재-GO/ACK 시각, 정렬 후 실행 결과, 정렬 상실/재획득은 **계산 불가**다. 병합된 Mac 산출물에는 per-tick own RGB·issued command·GO 시각이 없고, 해당 원본은 gcp2 `ops-reviews/beamact3/{A,B}/heldout20-v1` 아래에 있어 이번 배정에서 접근 금지다. `analysis/ready_recount.py`는 요약에서 재계산 가능한 값만 만들고 저장된 protocol audit 집계는 출처를 표시해 그대로 인용한다.

## 이번 후보 누적 관문

|순서|관문|누적 통과|거부|근거|범위|
|---|---|---:|---:|---|---|
|1|단위 테스트·기존 replay 경로|18 passed, 1 skipped|0|`tests/test_beamact5.py` 외|합성, 런타임 증거 아님|
|2|원래 GO 시각의 READY witness|0/40|40/40|`ready-recount.json`|오프라인 저장 원장|
|3|양쪽 정렬 경험(후속 재-GO 상한)|4/40|36/40|`ready-recount.json`|상한, own-camera 관측성 미측정|
|4|정확한 후속 GO/ACK 및 실행 결과|미측정|미측정|-|gcp2 원본 없이는 불가|

새 물리 실행·추론·렌더·학습은 0이다. 새 런/큐가 아니므로 current-stack 검사는 `replay` 흐름으로만 기록했고 `admission=historical_replay`, `current_compliant=false`다. 이는 현재 스택 적합 주장이 아니다.
