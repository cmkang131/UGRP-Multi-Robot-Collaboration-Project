# 확증 배치 초안 보존·추가 probe 중복 확인 (2026-09-30)

`placements_confirmatory_DRAFT.json`은 **60개, 바이트 변경 없음**이다. SHA-256은 `bb8044058377d86efc658ce3a7458c8afc141680acfd98542260e0efda018454`, 생성 시드는 20260941이다. 기존 생성기의 x/y/yaw 범위·24개 탐색 배치 제외·배치 간 근접 제외·hR2 사전분포 10개 추첨 규칙을 바꾸지 않았다. `make_confirmatory_placements.py --check`로 같은 산출물을 확인한다.

후속 ON probe **29개 구성**(tS 12 + tR 10 + tX1 완료 6 + tX1b 1)의 실제 `case.json` 시작 좌표를 읽어, 확증 60곳과 **거리 <0.01 m AND yaw 차이 <0.5°**인 근접 중복이 **0건**임을 확인했다. [`analysis/sizing_20260930/placement_freshness.json`](analysis/sizing_20260930/placement_freshness.json)에 29개 시작 구성·원본 경로·해시·검사 조건을 남겼다. 기존 tX1의 결과 없는 X06 두 건은 probe 완료 배치로 세지 않고 tX1b 재실행과 구분했다. 이 중복 검사는 29개를 독립·대표 모집단 표본으로 검증한 것이 아니다.

현재 60곳의 수치 설계는 [`analysis/sizing_20260930/COHORT_SIZING.md`](analysis/sizing_20260930/COHORT_SIZING.md)를 따른다. gain+axial lag ON의 조건부 기대 통과 수는 59.741/60이며 기본 주 기준은 **≥48/60 관측률**로 유지한다. 모집단 주장용 권고 **N=225, ≥192/225**(참 p=0.88, 양측 정확 95% 하한>0.80, 검정력≥90%)는 별도 조정자 결정이다. 확대 배치를 생성하거나 기존 목록을 재추첨하지 않았다.

인수 재생용 골든은 [`analysis/acceptance_replay_DRAFT.json`](analysis/acceptance_replay_DRAFT.json)의 **5개 lag ON 케이스/시드 911**이다. 원본 명령 해시만 보존했으며 새 등록 정책의 바이트 동일 재생은 실행하지 않았다. 이 골든이나 probe 배치는 확증 60개의 통과 분모에 넣지 않는다.

후속 검토 반영: 현재 60곳은 앞서 채택한 확증 배치와 근접한 추첨도 거부하므로 독립 동일분포 추출이 아니다. 모집단 수치 보장은 별도 추출 설계/추론이 필요하다. ON 29구성의 좌표는 26개, 근접 연결 묶음은 20개이며 prior/준비 상태가 달라 20을 유효 n으로 대체하지 않는다. p=0.88은 보수성이 검증되지 않은 설계 가정이다. 기존 배치 바이트와 원본 수치 산출물은 보존했다.
