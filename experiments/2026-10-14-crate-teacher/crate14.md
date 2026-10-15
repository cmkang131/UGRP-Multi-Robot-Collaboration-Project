# crate14 — 시작 분포·정렬·쌍 시한 (기본 off)

기준 `727de2af0e5ec10dda0b954e757c2fe42e694766`(crate13), PR #500. 사용자 지정 설계 A를 `--crate-profile crate14_v1`로 묶었다. 계획 생성기도 같은 프로필을 명시해야 한다. **이전 프로필·시작 분포·머신 결과와 합산 금지. 새 물리 실행 0, 학생 성공·학습 관문 판정 없음.**

- 시작: r2는 맡은 파랑 끝 기준으로 추출한다(other_end=자리, near_own=자리 주위 ±0.45m, approaching/absent=바깥 방향 원뿔). 양방향 상대 자리 0.34m 이내를 거부하고 `start_assigned_los_v1`을 강제한다. 이는 **시작 분포 정의**이며 결과를 본 뒤 판정 대상을 줄이는 필터가 아니다. 원래 제안·거부 원본은 계획과 해시가 있는 zstd 부속 파일에 보존했다.
- 정렬: 목표 197.4mm, 거리 후보는 이 값 하나. inner=(0.5mm,2mm,0.005rad), outer=(1mm,4mm,0.01rad). READY 불가·전축 비활성 때 최대 정규화 오차 축을 다시 켜며 READY 대기에도 서보를 유지한다. 미세 요청이 duty 인코더에서 0이 되지 않게 기존 정렬 40ms 최소 펄스를 적용하고 기존 swept 안전 검사를 거친다. 스탠스는 중심과 outer 밴드 8모서리의 반대칭 파지·실제 계획 들기 경로를 모두 검사한다(±17.5° 취약 후보 거부).
- 쌍 시한: staging과 기존 peer-wait의 12초 예산에서 상대 원판 차단 시간을 빼며, 다른 원인은 계속 센다. staging은 **같은 허용 관측에서 상대 원판만 뺄 때 경로가 생기는지**로 이유를 구분한다. 이 비교는 시한에만 쓰고 실제 경로·명령의 상대/벽 제약은 유지한다. 탐색·단계·에피소드 상한은 유지된다.

## 오프라인 검증

관련 시험만 단일 pytest 프로세스로 **41 passed (4.27s)**. [원장 재생](crate14_offline.py), [시작 감사](crate14_start_audit.py), [요약·해시](crate14-summary.json). MuJoCo step/forward/Renderer를 금지한 수치·정적 광선 검사이며 실제 물리 실행·렌더가 아니다.

79317은 **402/402**, 중단 원본 79316은 **594/594** robot-tick의 기존 명령·단계를 그대로 재현했다. 같은 저장 관측/상태의 독립 정렬 판정에서 79317 r1은 정렬 129틱 중 무명령 **102→3**(99틱 보정), 79316 r2는 68틱 중 **33→1**(32틱 보정); 후자의 기존 스탠스는 **68/68 거부**. 보고서의 “99/129 무명령”과 원장 전체 정렬 무명령 102는 일치하지 않는다(남는 3틱은 relook/진행 없음 전환). 새 READY는 이 저장 상태들에서 0이므로 성공 개선으로 해석하지 않는다. 후보 연속 재생은 최초 차이(t=2.5/5.7s, 펄스 폭)에서 중단했으며 이후 효과는 독립 상태 비교뿐이다.

실행에 쓰는 8번째 하강 명령의 pitch 유지 PWM→닫기 1500→기존 들기 전체 경로로 창을 재확인했다. 원장 345개 정렬/READY 상태의 z=23.963624614–23.963624677mm에서 x 창은 y=0: **194.2–200.8mm**, y=16.7mm: **193.2–199.7mm**(0.1mm 격자). PWM 1500만 임의로 놓은 별도 자세 검사가 아니다. 실제 동적 안정·정지 뒤 이동은 미검증이다.

기존 진단 10개에 새 필터를 적용하면 LOS **7/10 통과**, 자리 차단 **1/10 거부**(LOS 거부와 겹침), 합집합 **3/10 거부**다. 동일 10개 seed/층 인덱스를 새 분포로 재추출하면 LOS·자리 모두 **10/10 통과**. 12개 전체 인덱스의 제안은 26개 중 자리 1·LOS 13 거부(14/26). 이는 과거 실행을 바꾼 결과가 아니다.

## 비활성 GCP 대기열

재현 **77990·79314·79317**은 crate13 배치 원본 그대로, 새 진단 **79450–79457·79460–79461**은 별도 분모다. 새 시작 후보 **23개 중 11개 거부(47.83%, LOS 11·자리 0)**; 완성 배치 **12개 중 벽 근처 2개 제외(16.67%, 79458/79459)**, 진단 10개 모두 LOS 통과. 기존 벽 0.45m 규칙 유지.

[생성기](crate14_queue.py)는 clean·push SHA 확인 뒤 `outputs/e2e18-admin/vm3-queue/20261015-crate14-diag-<SHA8>.json`을 새로 만들고 이전 큐 해시를 대조한다. approved/enabled/ready/stage_ready 및 gate·runs_enabled는 전부 false, 관문 작업 0. [시드 예약](crate14-seed-reservation.json): fetched main+열린 PR 22개 HEAD·기존 큐 102개·저장 원격 재고 9개에서 예약 구간 79450–79474 충돌 0. **원격 서버 접속·제출·live 재고 확인은 하지 않았다.** 실행 전 운영자의 비용·디스크·슬롯·live 시드 확인이 남는다. 기존 visible-relative 교사 어댑터를 유지했으며 RGB-only 위치 추정 검증으로 표현하지 않는다.

## 참고 자료와 확인 범위

직접 근거는 사용자 지정 Claude 저장 분석 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate13-727de2af/report.md`, 같은 폴더 `scripts/`·JSON(파일별 해시는 요약), 저장 원장이다. 79317 t=0/4/6/8/12/16/18/20, 79316 t=0/6/12/17/18/23/24/29 영상 프레임도 열어 로봇 관계를 확인했다. 자료는 로컬 프로젝트에 보존했다.

보고서 출처를 2026-10-15 다시 확인했다: [Dias 등 2005](https://publications.ri.cmu.edu/market-based-multirobot-coordination-a-survey-and-analysis) 서지·초록, [Gerkey & Matarić 2004](https://cse-robotics.engr.tamu.edu/dshell/cs689/papers/gerkey04formal.pdf) 서론·초록(배정과 실행 구분), [McGreavy 등 2016](https://research.birmingham.ac.uk/en/publications/next-best-view-planning-for-object-recognition-in-mobile-robotics/) 서지·초록, [Chen 등 2017](https://www.scitepress.org/Papers/2017/62258/) 서지·초록, [Gregoire 2014](https://arxiv.org/abs/1410.0879) 초록만. **쌍 대기 12초·정렬 밴드·40ms 펄스를 직접 정당화하는 문헌은 미확인**이며 이 값들의 물리 타당성은 주장하지 않는다. [Burridge 등 1999](https://repository.upenn.edu/handle/20.500.14332/33914)는 이번 웹 접근 실패로 미확인; Aydemir·Kuhn 1955·Connolly 1985도 보고서의 미확인 상태를 유지한다. 본 구현은 보고서 설계 A이며 이 논문들의 전체 알고리즘 재현이 아니다.
