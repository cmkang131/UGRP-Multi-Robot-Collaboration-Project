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
도착1cm는 기존 safe_prefix 샘플 간격,3회 반복은 사용자 규칙이다.
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
