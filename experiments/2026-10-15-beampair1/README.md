# beampair1 — long_beam 두 로봇 근거리 교사

2026-10-15. `claude/beam-pair-teacher`, base `3bd9e013ed99ea0b05982bb90e2a6852529eb2a8`.
**R3 짧은 탐색 6/6 성공, 40회 대기열 준비 완료·미제출. 정식 관문 미실행.**
학습용 RGB·학습·학생 실행은0이다. [초안 PR #522](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/522).

## 기존 관문 감사

gcp1에서 ARM의 `native-grasp-teacher-gate-*` 원본 사본을 스크립트로 읽었다.
Mac에는 요약과 실패 몽타주만 회수했다. 원본은 ARM에 그대로 남아 있다.
[원본 재집계](history.json), [순차 관문표](historical-rejection-table.json).

| 소스 | 계획 | 시작 | 완료 성공 | 완료 실패 | 중단 | 미시작 | 3초 공동 유지 증거 |
|---|---:|---:|---:|---:|---:|---:|---:|
|078cbb45|40|16|16|0|0|24|0|
|1f177950|40|16|11|1|4|24|0|

두 옛 교사는 legacy 정답 교사이며 성공 판단은 1초 유지였다. 3초 미기록을
물리 실패로 소급하지 않는다. 기존 `1f177950` 11/11 표는 마지막 종료된 실패
episode-002를 빠뜨렸다. 이 실패에는 개별 raw manifest가 없지만 상위 SHA256SUMS 전체 검사가 통과해 결과와 원장을 확인했다.
078cbb45는16개 raw manifest가 모두 통과했지만 상위 SHA256SUMS에 episode003 최종화 전 값이 남아 있어 전체 원본의 바이트 일치를 주장하지 않는다.
episode-001/002/007에서 6프레임씩 총18장(0–59/59/56 SIM초)을 직접 보았다.
양 로봇은 서로 다른 끝으로 접근하고 그 자리에서 기다렸다. 같은 끝 경쟁으로 분류하지 않는다.
평가 좌표 기반 최근접 끝도 원장에 따로 기록했고 제어 입력에는 사용하지 않았다.

[act9](act9-scope.json)는 상자 1대 교사다. seed8316902는 교란 뒤 대상 상실,
569틱 정지 시선 탐색 실패 뒤 접근 60.6 SIM초 timeout으로 같은 소스 실행을 중단했다.
빔 관문 수에 포함하지 않는다. `beam-gate-los-23a2a113.json`은 정적 시선 가능40/40,
38/40 요구의 필요조건만 통과했으며 동적 접근·정렬·파지·들기는 검증하지 않았다.

## 후보와 실행 경계

- 근거리 경로는 PR #484의 `26f84d0f0ada1c33473c83cca2d3415ce51bd247`을
  깨끗한 고정 의존성으로 재사용한다. ACT 코드와 패키지를 격리하며 fallback import를 금지한다.
- `--mode beampair1_v1` 기본 off. `held_object_hidden_v1`: 어느 로봇이든
  닫기 PWM을 발행한 뒤 양 로봇의 화물 위치 측정을 만들지 않고 기존 위치 기억을 지운다.
  상태 판정은 자기 발행 명령만 사용하며 정답·접촉은 평가에만 남긴다.
- v7 장면은 PR #519 `13f50f31a40f2e87e3964137c8c2d6d3075ba4e1`의
  s7 원본 JSON을 그대로 고정했다. heavy_crate/tile/can 없음, 청록·파랑 끝,
  기존 long_beam 형상·질량·접촉·v3 카메라와 weld OFF 유지.
- 계획 예산은 기존 search24의98304 검사다. search25의30 wall초는 선택에 영향을
  주는 타이머가 아니라 HOST 안전 cap_end로만 쓴다. 에피소드 상한60 SIM초는 기존 탐색과 동일하다.
- 잡기 경로와 허용오차를 새로 조정하지 않았다. 기존12mm·10도·양집게0.5N·3초를 별도 평가한다.
- 교란은 기존 `RecoveryPerturb`를 재사용한다(.35 duty, .1 SIM초, 관측된 접근·정렬만).
  R1은1/3/5/8/10/12틱과 짝의 보수 길이를 섞는다. 이는 사용자 요청의 범위 검사이며
  물리 잡음 분포의 추정값이나 최적 DART는 아니다. 들고 있는 동안 교란 없음.

첫 라운드는 과거 실패·중단 seed71001/71002/71003/71006/71007을 먼저 두고
성공71000을 붙인6회다. 시작 좌표는 과거 자료에서 가져오되 나머지 화물은 v7이므로
과거 물리 재생과 구분한다. 최대로3라운드, 동시6·호스트 전체40 이하.
4/6 이상 및 입력/무결성 확인 뒤에만 새40회 검토용 대기열을 만든다. 관문은 실행하지 않는다.

## 참고 자료

- [Nav2 공식 튜닝 안내](https://docs.nav2.org/jazzy/configuration_and_development/tuning_guide/):
  2026-10-15 본문 확인. 실제 footprint와 inflation 비용의 분리 원칙을 참고하며
  기존 search24/25 구현을 재사용한다. Nav2 자체 이식이나 안전 보증은 아니다.
- [Reuleaux 저자 논문](https://arxiv.org/abs/1710.01328): 초록 확인.
  도달 가능한 팔 자세에서 기지 위치를 역산하는 기존 IRM 방법의 근거다.
- [DART 저자 논문](https://arxiv.org/abs/1703.09327): 초록 확인.
  시연 중 교란과 복구를 평가하는 원칙만 참고했다. 우리 교란 크기는 최적화하지 않았다.
- 정적 시선 원본: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/beam-gate-los-23a2a113.json`.
- 과거 원본: ARM `/home/ubuntu/ugrp-archive/runs/native-grasp-teacher-gate-{078cbb45,1f177950}`;
  gcp1 사본 `/home/ugrp/ugrp-sim/outputs/beampair1-historical/`.

## 검증과 남은 일

로컬 비물리 단위 검사 **12개 통과**. R1의 실제 잘린 교란을 관문으로 승격하려 하면 거부하고,
rejection_table 파일이 없을 때도 거부하는 검사를 포함한다. 제어 경로는 최종 물리 소스
`d79f04a39e3eec9d418e5c44929182e0ec79f51c`와 같다. 분석·대기열 코드는 별도 커밋이다.

| 라운드·고정 SHA | 공동 들기 | 실패/중단/HOST_ERROR/cap_end | 실제 r1 교란 틱 | 판정 |
|---|---:|---|---|---|
|R1 cdbdc4b0|6/6|모두0|1,3,5,3,7,3|시야 상실→search 전환이 버스트를 잘라 관문 후보 제외|
|R2 b53183b7|6/6|모두0|1,3,5,3,7,3|READY 전환 수정만으로 부족, 후보 제외|
|R3 d79f04a3|6/6|모두0|1,3,5,8,10,12|40회 준비 조건 통과|

R3에서는 r2도12/10/0/0/3/0틱을 실제 발행했다. 시작은 보이는 접근·정렬에서만 하고,
이미 시작한 버스트는 search/relook에서도 끝낸다. pick·닫기·들고 있는 동안은 취소한다.
세 라운드는 같은6시드의 탐색이며 독립 관문으로 합산하지 않는다. R3 시간은27.7–40.3 SIM초,
wall/SIM 중앙 **2.426**(동시6 전용)이다. 두 로봇 준비→집기→발행 시퀀스 완료→3초 공동 유지→입력 적합도는
각각 **6→6→6→6→6**이었다. `held_world_reads=0`, `invisible_measurements=0`,
held 차단이 실제 발동한 틱도 모두 양수다. 세 라운드의 전체 원본 SHA256SUMS가 모두 통과했다.

- [R3 원본 재집계](r3-summary.json), [후보·프레임·이벤트 관문표](r3-rejection-table.json), [시간 기록](r3-runtime.json).
- R3 자기 RGB는 실행당6시각×2로봇, 총72프레임을 직접 보았다. 전체0–27/40 SIM초 범위이며,
  첫30초와 처음·중간·끝을 포함한다. 색이 확인되는 근접 구간에서 두 로봇은 청록/파랑의 서로 다른 끝을 잡았다.
- [R1](r1-summary.json)·[R2](r2-summary.json)도 실패/중단 포함 원본과 별도 관문표를 보존했다.
- [대표 영상·원본 프레임 SHA](representative.json): 영상은 gcp1에만 남겼고 Mac에는 몽타주와 요약만 회수했다.
  GCP raw는 영속 디스크 보관이며 별도 ARM 백업 완료를 뜻하지 않는다.

[40회 대기열](gate40-queue.json)은 `approved=false`, `submitted=false`다. 운영 원본은
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-beampair1-d79f04a3.json`.
고정 worktree는 `/Users/changmin/projects/ugrp-wt/beam-pair-gate-d79f04a3`,
전체 source_sha와 dependency_sha, source hashes, 절대경로 rejection_table을 넣었다.
새 시드8318600–8318639는 정적40/40이며, 과거 로컬 큐와 gcp1 raw plan에서 중복0을 확인했다.
동시 최대16·호스트 합계40 이하, 학습RGB OFF다. 40회 물리 관문은 **0/40 미실행**이다.

남은 범위: 현재 후보의 동시16 속도와 첫30 원본 확인 후에만 큐를 채운다.
후보 거부가 없었던 이번6개는 IRM의 장애물 거부·후반 탐색 소진을 입증하지 않는다.
회전 보정 on/off 효과와 내려놓기 뒤 지형지물 재확인은 이 접근·정렬·집기·들기 관문에서 검증하지 않았다.
정식 관문≥38/40 전에는 데이터 기록·ACT 학습을 시작하지 않는다.
