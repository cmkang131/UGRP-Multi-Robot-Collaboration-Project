# beampair9 — 기록200 새 시드 실패 원인과 기본 off 후보

beampair8의 원래 기록200을 별도 분석한다. 성공185, teacher_failure9, cap_end6, HOST_ERROR0이다. 기존 관문40/40과 합산하지 않는다. 기반은 beampair8 HEAD `65da04efe4d9d51d013cb2fbb755bc52364b8589`다. 새 관문 통과는 아직 주장하지 않는다.

[수정 전 거부 표](rejection-distribution.md), [후보·프레임·이벤트 funnel](rejection_table-before.json), [실패9/cap_end6 표](failure-table.md), [15회 상세 요약/시드 분포](before-summary.json), [정적 인증 자세200회 전수](static-census.json), [직접 영상 검토](visual-review.json).

큰 빈도는 cyan_1 current_geometry10884 + memory_margin5083, red_1 current_geometry6708 + memory_margin572다. 검사 빈도는 인과 비율이 아니다. 각 실패의 종료 사유·상대 위치·사유별 최소 틈을 별도로 보존한다. 15개 전부 처음·중간·끝을 포함한6개 실제 시각의 자기 카메라12장을 gcp2에서 몽타주로 만들었다. 실패8328015/8328010과 성공8328003의 기존 gcp2 제작3배속 영상 및 전체2Hz/실패 전10SIM초10Hz 띠를 직접 읽었다. Mac 물리·렌더·GUI0.

정적 원본 배치의 실제 상자 직육면체와 기존185×160mm 차체를 대조하면8328068 blue,8328183 teal은 기존 인증 파지 자세91개 모두 상자와 겹친다. 다른198회는 양 끝 모두 적어도 한 자세가 존재한다. 기존 배치 관문은 벽만 검사했다. 이는 고정91자세에 대한 결과이며 모든 가능한 조작의 불가능 증명은 아니다. 두 장면을 재배치하거나 제외해 교사 성공으로 세지 않는다.

관문40과 기록200은 같은 생성기이나 유한 표본 지지가 다르다. 빔 y 최소 -2.500→-2.747m, 최대 .895→1.051m, 로봇 간 최소 거리 .462→.267m, 담당 끝 거리 최대1.974→2.099m다. 분포 중앙값/백분위·역할/peer_case 표는 before-summary.json에 있다. 이 차이가15회 전부의 원인이라는 주장은 하지 않는다.

## 후보와 상수 근거

- `beampair_box_geometry_v1` 기본 off: 허용 자기 관측의 상자 xy/yaw와 고정 `zone_arena.BOX_HALF=(.017,.020,.016)` 사양을 이용해 차체 검사의3차원 외접 구를 평면 직육면체로 바꾼다. 기존5mm 화물 패딩·confidence margin·팔의 구형 충돌 검사·물리·카메라·장면은 유지한다. 알려지지 않은 화물은 기존 형상이다. 새 좌표/정답 조회는 없다.
- `beampair_checks_only_v1` 기본 off: 기존98,304 logical checks를 유지하고30 wall초 계획 안전 cap을 제거한다. 원래8328188은22SIM초에서 이 상한으로 종료했다. VM 비용/유휴/런타임 안전 장치는 그대로다.
- `beampair_gate_cargo_v3` 기본 off: 배치 생성의 기존k=91 및5mm 조건에 고정 화물 footprint를 포함한다. 거부 순회의 end 변수 누출도 이 옵션에서만 고쳐 r1 역할20/20을 유지한다. 원래 관문은19/21, 기록은92/108이었다. 원래 배치/데이터는 불변이며 켠 배치는 새 분포 버전이다. 이번 실패 시드 재실행에는 이 옵션으로 재배치하지 않는다.

명령·결과 원본이 고정된 뒤15실패+5성공을 실행하고 원본으로 다시 센다. 전부 통과한 경우에만 기존 관문/기록과 중복되지 않는 새40을16동시로 제출한다. 최대3라운드이며 결과를 합산하지 않는다. 새 기록은 교사 관문 뒤 별도 버전으로만 판단한다. 기존185개 성공 데이터는 유지한다.

## 표준 방법 조사 (2026-10-16 본문/공식 구현 확인)

- [OMPL SE(2) 공식 예제](https://github.com/ompl/ompl/blob/main/demos/GeometricCarPlanning.cpp): 상태와 형상 충돌 검사의 분리. 실제 형상 사용 원칙만 적용하며 OMPL 구현 이식/완전성 주장은 없다.
- [OMPL IterationTerminationCondition](https://ompl.kavrakilab.org/classompl_1_1base_1_1IterationTerminationCondition.html): 반복 횟수 기반 종료. 기존 검사 수를 유지하는 근거이며98304 자체는 기존 교사 값이다.
- [Nav2 obstacle layer 공식 문서](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/obstacle/)와 [원본 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_costmap_2d/plugins/obstacle_layer.cpp): 관측 marking/clearing 구분. TTL로 장애물을 지우거나 추정 여유를 임의로 줄이지 않는다.
- [Silver2005 원문 초록](https://ojs.aaai.org/index.php/AIIDE/article/view/18726): 시공간 예약. 현재 교사의 정적 목적 자세 예약과 구분하며 전체 peer 계획의 공유를 추가하지 않았다.

원본은 gcp2 `/home/ugrp/ugrp-sim/runs/beampair8-record-<seed>-72c0e83d/`, 분석은 `/home/ugrp/ugrp-sim/ops-reviews/beampair9/`다. Mac에는 요약·몽타주만 회수한다. 원본·데이터의 전체 별도 백업은 없다.

## 실제 run-first 라운드 (진행 기록)

R1 `267f8ed6`:16시작/20계획, 성공1·교사실패8·cap_end5·감독중단2·미시작4. 별도 원본 재계수와 raw/adapter manifest 확인. 감독중단2는 실행기 저장 분류가HOST_ERROR였으나 자기 PID/중단 기록으로 구분했다. 실제 인프라 HOST_ERROR0이다. 실패 회복0이며 이 부분 코호트를20회 완료나 새 교사 성공률로 표현하지 않는다. [원본별 재계수](round1/summary.json), [funnel](round1/rejection_table.json).

8328152의 한 틱이400초 넘게 머무른 원격 스택은 `rectangle_gaps → measure → pose_segment → grid_path`였다([스택](round1-slow-stack.txt)). 한 번의 벡터 호출이 여러 위치×장애물 검사를 해도1로 집계되는 것이 원인이었다. 자기 실행2개만 SIGINT로 최종화했고 다른 작업은 건드리지 않았다([중단 원장](round1-owned-stop.json)).

R2는 `1fe9450a`, 같은 원래20개 계획이다. `beampair_geometry_work_v1` 기본off는 기존98,304를 위치×(원/직사각형/경계) 검사량의 한도로 쓴다. 검사 의미가 달라진 엄격한 계산 예산 후보이며 기존 clearance/성공 허용오차를 바꾸지 않는다. Nav2 footprint와 inflation 비용 분리를 구현한 기존 `search25_soft_v1`도 별도로 켠다(candidate=soft). 결과는R1·beampair8과 합산하지 않는다. R2 대기열은 직전R1 funnel 절대경로·SHA에 연결되어 있다.

R1의 정상 종료14회는 기존 beampair8과 전체 명령·SIM시각·PWM·phase·done·adapter 명령 원장이14/14 정확히 일치했다([대조](round1-trajectory-comparison.json)). 형상 후보만으로 성공이 늘었다는 근거는 없다.

새 배치 후보는 물리 없이40개를 생성해 화물 footprint 검사와 청록/파랑20/20 및 기존 시드와의 비중복을 확인했다([설정 검사](setup-v3-verification.json)). 94제안 중 beam-cargo9, 인증 자세9, robot-environment27, robot-peer2, 시선7이 순서대로 거부됐다. 실제 관문은0회이며 원래 실패 장면을 이 배치로 대체하지 않았다.
