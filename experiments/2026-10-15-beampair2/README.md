# beampair2 — visible peer rendezvous retry

2026-10-15. PR #522 / claude/beam-pair-teacher. 기본 off `peer_rendezvous_v1`.

## 수정 전 근거

gcp1 원본 `/home/ugrp/ugrp-sim/runs/beampair1-gate-8318604-d79f04a3`에서
자기 관측·자기 발행 명령만으로 **384/384 명령 일치**를 확인했다.
[사전 거부 분포·재현 명령](original-summary.json): r1 대기121틱 중 r2 목표영역
침범92틱, 다른 장애물0. 목표 signed gap 최저−0.133892m, 종료직전−0.002334m.
이는 기존 inflated 모델 간 틈이며 실물 충돌/침투량이 아니다.
운영 원장도 재확인했다: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/gcp-reports/beampair1-d79f04a3-ops/funnel.json`.
후속 회수 후 시작7·success5·실패1·중단1이며 최초 보고의 확정5·성공4와 시점이 다르다.

기존 몽타주를 직접 검토했다: r1/r2 각각0·4·8·11·15·19 SIM초, 총12장.
역할은 r1=teal, r2=blue다. r2가 teal 근처를 지나 반대 끝으로 가는 동안
r1 목표 영역을 막는다. 두 로봇이 같은 끝을 파지한 증거는 없다.
r2는 절대 SIM6.8–16.2에 search, 이후 approach이며 r1의 peer_wait는8.9에 시작했다.
절대20.9(에피소드19.1)에서 r2가 계속 이동해 틈이 거의 해소됐으나
r1의12 SIM초 고정시한이 재계획보다 먼저 terminal을 만들었다.
`handoff` 뒤 새 접근은 실행되지 않았다. runner가 r2에 peer_approach_handoff를
전파했다. 따라서 별도의 post-handoff 장애물을 만들어 설명하지 않는다.

## 후보

고정 의존성 `26f84d0f0ada1c33473c83cca2d3415ce51bd247`의 근거리 경로를
공통 mixin으로 확장한다. 교사만 적용하며 ACT 학생 경로는 바꾸지 않는다.
로컬 대기 시한에는 경로·진행 창을 무효화하고 재계획한다. 자기 카메라에서
연속 관측한 peer의 이동만 예측하고, 상대가 목표에서 멀어지면 재계획,
그렇지 않으면 뒤/좌/우의 검증된 양보 대기 위치를 재선택한다.
현재 장애물은 유지하고 예측 장애물을 추가한다. 선택이3회 반복되면 제외한다.
안 보이는 화물 위치로 대기 위치를 고르지 않는다. held 숨김·weld OFF·원래 RGB/FOV 유지.

상수 근거: 기존12 SIM초를 실패 판정 대신 재계획 주기로 재사용한다.
기존 route refresh1 SIM초가 예측 horizon, 실제 pulse0.1 SIM초가 재검사 horizon이다.
양보 거리0.34m는 기존 peer+own inflated exclusion 반지름 합이다.
도착은 현재 발행 pulse의 이동량으로 판단하며 새 허용오차가 없다.3회 반복은 사용자 규칙이다.
성공 기준·오차·속도·margin·계획 계산량은 새로 튜닝하지 않는다.
search24/25의98304 검사 예산과 기존 A* 노드 예산을 사용하고 wall초로
후보를 바꾸지 않는다.30 wall초 host safety는 cap_end일 뿐이다.
60 SIM초 episode cap도 유지하며 cap_end는 별도 계수한다.
거부/대기/재계획에는 사유·장애물 이름·signed gap을 기록한다.

## 조사

- [ORCA 저자 페이지](https://gamma-web.iacs.umd.edu/ORCA/): 본문 확인.
  관측된 상대의 이동을 예측하는 원칙 참고. ORCA 선형계획 전체 이식이나 안전 보증 아님.
- [PIBT 원 논문](https://www.ijcai.org/Proceedings/2019/76): 초록 확인.
  동적 우선순위·backtracking으로 막힘을 풀고 재계획하는 원칙 참고.
  본 구현은 연속 공간·부분 관측이므로 PIBT의 그래프 완전성 정리를 주장하지 않는다.
- [PIBT 저자 코드 안내](https://kei18.github.io/pibt/): 원문과 공개 코드 연결 확인.

## 실행 계획

최대3라운드. [R1 고정6시드](probe-plan.json)는8318604를 단독으로 먼저 실행하고
통과해야 이전 성공8318600/01/02/03/05를 시작한다. r1 burst5/1/3/8/10/12틱을 섞는다.
전체 호스트 동시40 이하, 본 작업 최대6. DEV이며 정식 관문과 합산하지 않는다.
원본 분석은 gcp1, Mac 회수는 요약·몽타주·실패 프레임만 한다.
정식40회는 탐색이 해결된 뒤 별도 대기열만 준비한다(기존 d79 결과 합산 금지).

검증: 로컬 비물리16개 통과. GCP 후보 결과는 아직 미측정이다.

## R1 실행 결과

물리 소스 `33e0e8c9ec04546b1dd12d4f284edbb63773de2a`: 실패seed8318604가48.6 SIM초에 성공.
시한20.9에서 fresh r2 속도(-0.0532,-0.0746)m/s로 재계획했고 양 로봇이 각기 맡은 끝을 잡았다.
[원본 재집계](r1-summary.json), [관문표](r1-rejection-table.json): 시작1·완료성공1·미시작5,
cap_end/HOST_ERROR/입력위반0. 실행기 barrier가 압축된 adapter 결과를 못 읽어
성공을 first_seed_failed로 잘못 표시했다(원본 batch 기록은 보존). 원본 physical_success와
3초 유지 재계산은 모두 성공이며 압축 결과를 판독하도록 고친 R2에서6회 다시 잰다.

## 최종 R2 결과와 전달

실행 소스 **`f84b2c8a436feff9775758876248c3054ff3553b`**,
의존성 **`26f84d0f0ada1c33473c83cca2d3415ce51bd247`**.
[원본 재집계](r2-summary.json), [후보·프레임·이벤트 순차 관문표](r2-rejection-table.json),
[첫30·시간·held 차단](r2-runtime.json), [정리·보존 확인](lifecycle.json).
탐색은2라운드로 끝냈다. R1의1/1과 R2의6/6은 합산하지 않는다.

|R2 관문|누적 통과/시작|거부|
|---|---:|---:|
|시작|6/6|0|
|both_align|6/6|0|
|both_ready|6/6|0|
|both_pick|6/6|0|
|both_command_complete|6/6|0|
|whole beam 3초 유지|6/6|0|
|입력 적합|6/6|0|

완료 실패·중단·HOST_ERROR·cap_end·누락 거부 원장·입력 위반 모두0.
`held_world_reads=0`, `invisible_measurements=0`; held 차단92/102/106/106/90/108틱.
r1 교란5/1/3/8/10/12틱 전부 완수. r2는8/0/10/5/0/1틱 발행했다.
두0은 시야/단계 조건상 버스트가 시작되지 않은 경우이며 r2의 전 길이 관문은 아니다.
SIM30.1–48.6초, wall/SIM 중앙2.359.
실제 실행은 첫1개 완료 후5개 동시(예약6자리, 제출 직전 호스트 총10자리)다.
동시16 성능이나 부하 재생을 검증했다고 해석하지 않는다.

[실패시드 반복](first-seed-repeat.json): R1/R2에서 각각r1/r2 487명령,
합974개 발행 명령·phase·done 불일치0. 각 run의 원본 SHA256SUMS 전체 검사 통과.
저장 원본은 gcp1 영속 디스크이며 ARM 별도 백업은 하지 않았다.
[영상 검토 기록](visual-review.json): R2 각6시각×2로봇×6실행=72프레임,
전체0–30/31/34/34/36/48 SIM초를 직접 보았다(첫30과 처음·중간·끝).
접근 후 근접 색 띠가 보이는 구간에서 각자 맡은 청록/파랑 끝으로 갔다.
프레임 표본 검토이며 연속 영상 전체 검토나 물리 접촉 거리 측정은 아니다.
[대표 영상·원본98프레임 해시](representative.json)는 gcp1에만 보존한다.
R1·R2 첫 성공 원본은 하위milestone 메타데이터로 보존하며 기존 해시 목록은 덮어쓰지 않았다.

[새40회 대기열](gate40-queue.json): 전체 SHA·소스 해시·기존40개 frozen setup,
8318604 맨 앞, 새 run 이름, 새 실행 토글, 절대경로 rejection_table을 연결했다.
운영 사본은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-beampair2-f84b2c8a.json`.
`approved=false`, `submitted=false`, `ready=false`, `gate_measured_N=0`.
**조정자가 pinned worktree를 만든다.** 예상 경로는
`/Users/changmin/projects/ugrp-wt/beam-pair-gate-f84b2c8a`.
기존d79 결과·R1/R2 탐색 성공은40회 결과에 더하지 않는다. 모든40개를 처음부터 다시 잰다.

남은 활성화 전 조건: clean pin/전체해시,16동시 첫30 속도·원본 확인,
VM8시간 상한 확인(이번 live VM scheduling은24시간이었고 본 작업 명령은별도8시간 timeout),
비용·유휴·메모리·디스크·호스트40 이하 재확인이다.
비용정지 함수budget-stop은ACTIVE, 최근KRW 순비용 payload0/1000 확인.
다른 작업 때문에 VM은 끄지 않았고 본 작업 worker0·lease/예약 해제를 확인했다.
양보 위치 재선택은 구현했지만 이번6개에서 분기가 실행되지 않았다(후보0).
측정된 복구는 moving_peer_replan1건이다. 독립40회·데이터·ACT 학습·학생·운반·놓기·실물은미검증.
로컬 관련 비물리 검사는18개 통과하고 새 시험을CI 목록에도 등록했다.
