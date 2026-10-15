# crate19 — READY 유지와 전진 정착 후보

기준 `487579ea4b862465b4feb5e64ca55c2fabae9558`, PR #500. 관문과 새 후보 진단은 분리한다.

## 수정 전 GCP 원본 재집계

`analyze_baseline.py`를 gcp1에서 실행하고 요약만 회수했다. 원본: gcp1의
`~/ugrp-sim/runs/crate18-full-reproduction-79314-487579ea/raw`.

| 사유 범주 | 미정착 표본 수 |
|---|---:|
| 전후축 허용 밖 |147|
| 좌우축 허용 밖 |22|
| 회전축 허용 밖 |14|

표본은 축별 관측 수이며 독립 에피소드 수가 아니다. READY 진입 10회.
50 SIM초 이후 같은 부호 전진 펄스85회의 직후 실제 전진 중앙값1.635314mm,
다음 명령까지 남은 이동 중앙값−0.002611mm. δ=3.071185mm, 허용=1.842711mm.
단기 운동은 있으나 거의 되돌아오므로 단순 정지마찰로 확정하지 않는다.
정착 후 되밀림을 동반한 주기 반복을 우선 수정한다. 평가 위치는 이 분석에만 쓴다.
전체 펄스별 수치·입력 SHA는 `baseline-pulses.json`에 있다.

## no_clearance gate40 준비 완료

코드 변경 없이487579ea 고정 detached worktree:
`/Users/changmin/projects/ugrp-wt/crate-src-487579ea`.
큐: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-crate-gate40-noclear-487579ea.json`.
`crate18_v1` + `crate17_no_clearance_v1`; 새 시드112000–112051 중40개,
52개 완료 시작 제안 중 near-wall12개 제외(23.08%). 시작 조건 제안·LOS 거부 분모는 큐·계획에 보존.
새 시드 범위112000–112199는 외부 setup 전용 예약이며 고정 코드의 registry는 수정하지 않는다.
관문계획은 source 밖에 해시 검증 후 설치하도록 명시했고 큐에 무손실 포함했다.
상한 grasp90/release90 SIM초, 동시16/전체40, training_rgb=false, 기준38/40.
준비 시 승인·제출 플래그false, ops-alert 한 줄 추가. 진단/다른SHA/호스트와 합산 금지.

## crate19 후보

기본OFF `crate19_v1`: 실제 발행 펄스의 같은 부호 오차열에서6회 동안 δ의10%만큼도
진척이 없고 현재 오차가2×허용 안이면 자세를 수용한다. 가시 관측과 발행 이력만 사용한다.
2×허용 밖 무진척이면 펄스 폭을 단계적으로 늘리되100ms 이하, 기존 안전 검사를 통과해야 한다.
최소허용≥0.6δ와 반전3회 수용은 공통 PulseSettler에서 유지한다.
정확한 가시 파지·IK/들기 가능성 검사는 그대로 적용한다. release는 공통 모듈 변경 없이 유지한다.
계획 탐색은 기존 crate17의 tick당384 노드 예산이며 wall 시간 중단을 쓰지 않는다.
물리 검증·남은 문제는 실행 후 아래에 기록한다.

関連非物理試験116 PASS（crate17/18/19、pytest同時1）。Macのstep/forward/renderを例外で禁止。
DEVは各ラウンド full79314・77990・79317と no_clearance79314の4回、90/90 SIM秒。
開始時の24h STOPはユーザー指定の調整者設定を受け入れ、こちらからVM設定は変更しない。
