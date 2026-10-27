
## 2026-10-16 coordinator: B 조건은 gcp3 L4로
공유 L4에서 A가 1.45 s/step(남은 ~15.7k step ≈ 6.3h). 세 번째 프로젝트 ugrp-sim-c-1016의 L4 `ugrp-act-l4-gcp3`를 gcp3setup이 준비 중(ops-alert "gcp3setup: READY" 줄 확인). READY가 뜨면 B는 기다리지 말고 gcp3에서 시작(같은 데이터·시드·설정, 호스트 다름은 기록에 표시). A는 지금 자리에서 계속. budget-stop 확인 전에는 gcp3에 올리지 않는다.

## 2026-10-16 coordinator: 앞 메모 철회 — B도 gcp2
A가 5.6 step/s로 회복(남은 ~7.5k step ≈ 20분대). A/B 비교는 같은 호스트가 맞으므로 B는 A 끝난 뒤 gcp2 같은 L4에서 그대로 진행. gcp3 이관 지시는 취소(참고: 세 번째 프로젝트는 사용자가 "프로젝트 그럼 하나 더 만들어"로 승인한 것이지만, 이번 A/B에는 쓰지 않는다).

## 2026-10-16 coordinator: C 조건 추가 (copycat 대응, B 끝난 뒤 같은 L4·같은 데이터·같은 시드)
사용자 질문 "직전 명령을 그대로 반복함 — 이건 어떻게 해결하지"에 대한 표준 해법을 시험한다(기본 off 토글, A/B와 합산 금지):
- C1 원래 ACT 방식: 명령 이력 입력 제거(자기 RGB + 스킬/물건/자리 표만, Zhao et al. 2023 ACT는 과거 행동을 입력으로 받지 않음). 
- C2 이력 드롭아웃: 학습 때 이력을 확률 p로 통째로 가림(p 근거 기록) + 명령이 바뀌는 전환 프레임 가중(전환/안정 비율 근거).
판정은 전체 MAE가 아니라 전환 프레임 정확도·첫 바퀴 변화율(cold-start)·폐루프 보류20의 정렬 통과 n/N. 참고: Wen et al. 2020 "Fighting Copycat Agents in Behavioral Cloning from Observation Histories", de Haan et al. 2019 "Causal Confusion in Imitation Learning".
- 사용자 승인(2026-10-16): 위 C 조건 설명에 "ㄱㄱ". 확인 질문 없이 B 뒤에 C1·C2를 같은 L4에서 진행한다. 결과 줄은 "beamact3: A .. B .. C1 .. C2 ..".

## 2026-10-16 18:40 coordinator: C1·C2 병렬 (사용자 "쳐낼 거 쳐내고, 빠르게 할 건 더 빠르게")
B 학습이 끝나면 C1은 gcp2 L4에서 바로 시작한다. C2는 다섯 번째 프로젝트 L4 `ugrp-act-l4-gcp5`(ugrp-sim-e-1016, gcpctl 별칭 gcp5, gcp5setup이 준비 중, ops-alert "gcp5setup: READY")에서 동시에 학습한다. 데이터·시드·스텝 같음, 호스트만 다름(호스트 표기, 학습 GPU 위치는 합산 기준과 별개). gcp5가 B 끝날 때 아직 준비 안 됐으면 C1 먼저, 준비되는 즉시 C2. 평가는 기존대로 gcp2 CPU. 8h 상한은 사용자 결정으로 없음(다시 넣지 말 것), 유휴20분·budget-stop 유지.

## 2026-10-16 19:00 coordinator: 더 빠르게 (사용자 "빨리빨리 해줘") — 앞 C1·C2 배치 대체
C1·C2는 B와 독립이므로 B를 기다리지 않는다. C1은 gcp5 L4(ugrp-sim-e-1016), C2는 gcp6 L4(ugrp-sim-f-1016, 다른 계정 kcm5781kcm5781@gmail.com — 이 프로젝트 gcloud는 --account kcm5781kcm5781@gmail.com)에서 각 setup이 READY 되는 즉시 동시에 시작. gcp2 L4는 B 평가가 끝나면 act16w 학습에 넘긴다. 셋 다 같은 데이터·시드·스텝, 호스트만 표기.

## 2026-10-16 19:20 coordinator: gcp5 READY — C1 지금 시작
gcp5(ugrp-sim-e-1016 / ugrp-act-l4-gcp5, zone asia-northeast3-a, 계정 changmin5781) READY. ACT 환경·beamact3 데이터(1,482 파일 SHA 일치)·50 step 저장/재로딩 확인 완료. gcpctl 별칭 gcp5는 브랜치 codex/gcp5setup(PR #560, worktree /Users/changmin/projects/ugrp-wt/gcp5setup)에 있다 — 필요하면 그 gcpctl을 쓰거나 gcloud로 직접. 지금 C1 학습을 gcp5에서 시작하라. C2는 gcp6 READY 뒤.

## 2026-10-16 19:3x coordinator: gcp6 READY — C2 지금 시작
gcp6(ugrp-sim-f-1016 / ugrp-act-l4-gcp6, 계정 kcm5781kcm5781@gmail.com — 이 프로젝트 gcloud는 반드시 --account kcm5781kcm5781@gmail.com) READY. ACT 환경·데이터 1,483 파일 SHA 일치·50 step 확인. gcpctl 별칭 gcp6는 PR #561(codex/gcp6setup, worktree /Users/changmin/projects/ugrp-wt/gcp6setup). 지금 C2 학습을 gcp6에서 시작하라(C1은 gcp5).

## 2026-10-16 19:35 coordinator: C1·C2는 별도 작업자(beamact3c)가 맡는다
병렬을 위해 C1(gcp5)·C2(gcp6)는 worktree /Users/changmin/projects/ugrp-wt/beamact3c(codex/beamact3c)의 별도 Codex 작업자가 맡는다. 너는 B 마무리(Release·기록·PR)까지만 하고 C는 시작하지 말 것. gcp5·gcp6에 손대지 말 것. 끝나면 gcp2 L4를 act16w 학습이 쓸 수 있게 임대를 정리.

[조정자 20:04] 충돌 방지 규칙(필수): /Users/changmin/projects/ugrp/outputs/e2e18-admin/agent-ownership.md 를 읽고 따를 것. 자기 VM·자기 파일 범위 밖은 건드리지 말 것. 다음 ops-alert 보고 줄 끝에 'ownership-ack' 를 붙일 것.
