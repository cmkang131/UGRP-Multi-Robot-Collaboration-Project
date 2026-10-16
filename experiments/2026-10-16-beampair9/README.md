# beampair9 — 기록200 새 시드 실패 원인과 기본 off 후보 — **NOT_READY**

[초안 PR #542](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/542)는 beampair8 위에 열었다. 병합하지 않았다. 실행 뒤 최신 parent의 영상 색인 충돌을 양쪽 기록을 보존해 해소했고 실행 제어 모듈8개 해시가 `67d65d8e`와 같음을 확인했다.

최종 소스 `67d65d8e`의 실패 회복은 **0/15**, 성공 비교는 **5/5 유지**다. 3라운드 한도에 도달해 새 관문40회는 제출하지 않았다. 최종 원본20회는 성공5·교사실패10·cap_end5·HOST_ERROR0이며 입력 감사 두 항목은0이다. 이20회는 실패15+성공5를 의도적으로 고른 회귀 묶음이므로 모집단 성공률이 아니다. [최종 요약](summary.json), [원본 재계수](round3/summary.json), [funnel](round3/rejection_table.json).

|독립 코호트|계획/시작|성공|교사 실패|cap_end|감독 중단|HOST_ERROR|미시작|
|---|---:|---:|---:|---:|---:|---:|---:|
|원래 beampair8 기록|200/200|185|9|6|0|0|0|
|R1 `267f8ed6`|20/16|1|8|5|2|0|4|
|R2 `1fe9450a`|20/16|1|6|5|0|4|4|
|R3 `67d65d8e`|20/20|5|10|5|0|0|0|

표의 행은 합산하지 않는다. R1 감독 중단2의 실행기 원래 HOST_ERROR 분류는 그대로 보존하고, 자기 PID/신호 기록으로 분석에서 구분했다. 기존185 성공 데이터의 아카이브 SHA-256이 원래 값과 일치한다. 새 교사가 미통과했으므로 재기록·학습은 보류한다. 이후 관문을 통과한 변경 교사의 데이터는 새 버전으로 기록해야 한다.

두 로봇 관계는 [전체15회 표](robot-relations.md)를 먼저 본다. 담당 끝은 항상 다르지만8328010/8328038에서는 각각360/396·439/543 프레임에서 두 로봇의 최근접 끝이 같았고 최소 간격은 약0.155m였다. 이는 의도/접촉 판정이 아닌 평가 거리다. 접근 중 교차/가림과 이후 정체는 영상으로 확인했다.

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

R2 원본 재계수:16시작/20계획, 성공1·교사실패6·cap_end5·HOST_ERROR4·미시작4. 입력 감사는 두 항목 모두0이다. 기존 soft 경로가 보간 edge의 `gap_m`/`margin_m` 기록을 `slack_m`이 있는 기록과 섞어 재사용할 때KeyError가 났다([4회 오류](round2/errors.json), [재계수](round2/summary.json), [funnel](round2/rejection_table.json)). 새 후보는 해당 감사 필드를 정확한 차 `gap_m-margin_m`으로 복원한다. 충돌 판정/허용 상수는 바꾸지 않으며 단위 회귀로 확인했다. 최종R3 소스는`67d65d8e`다. R3는 같은 원래20개를 다시 실행하고, 이 라운드 뒤에는 추가 튜닝/관문 제출을 하지 않는다(모두 통과한 경우의 새 관문은 별도 판단).


정렬8328015는 관측만 재구성한 진단에서 x잔차6.75mm·y잔차-10.92mm·yaw잔차-0.0258rad였다. 기존40ms 최소 전진 펄스가 `cyan_1` 원형 여유에 막히고, 그 시작 틈은1.925mm이고 펄스 경로 최소 틈은 명목/보정 모델에서각각-1.538/-0.699mm다. 원본의 `alignment_axes_blocked`90회 및 영상의 정지 상태와 일치한다([입력 재구성](alignment15-visible-world-replay-v2.json), [분리된 진단 funnel](alignment15-diagnostic-funnel.json)). 이 진단은 원본 VisibleWorld와 실제 발행 이력을 재구성했으며 FreeSpace/재관측 ghost 전체나 물리를 재생한 것은 아니다. y/yaw 방향도 모두 실제로 허용됐다는 완전한 제어 재생 주장은 하지 않는다. 현재 box 옵션은 body navigation 경로에 적용되고 기존 원형 정렬 펄스 가드에는 적용되지 않는다. 일관된 충돌 형상의 적용이 남은 수정이며, 최대3라운드 뒤 추가 미검증 제어 패치를 넣지 않는다.


최종 R3의 첫30SIM초 정확 표본12회 중앙 wall/SIM=4.080(3.5 경고,6.0 미만); 30SIM초 전에 완주한4회까지 실제 완주 시간을 포함한 제출 판단 중앙값은4.252다. 모든20회를 완료했고 원본/adapter manifest 총 5069파일, 명령 16512행을 연결했다. 모델 호출0이며 공유 GCP 비용은 별도 배분하지 않았다. 대표 R3 실패/정렬 정체/성공의 자기 몽타주도 직접 확인했다. 원본15회 각6시각 검토와 고속 띠 검토 범위는 visual-review.json에 있다.

남은 핵심은 (1) 고정 인증 자세가 없는 배치의 임무 수준 처리, (2) 계획과 실제 정렬 펄스의 충돌 형상 일치, (3) 가까운 동료/가림 이후 재관측·대기와 물리 공동 유지다. 기존40/40이나185개 데이터 적합도를 새 교사 관문 통과로 승계하지 않는다.

회수 요약·표·몽타주40파일의 GCP↔Mac SHA-256은 전부 일치했다([회수 검증](retrieval-verified.json)). 원래20개 계획의 배치·역할·카메라·교란이 새 raw와 같고 원래 파일 해시도 유지됨을 별도로 확인했다([계획](run-first-plan.json), [20개 대조](plan-integrity.json)). 비물리 관련26시험(마지막22 + 설정4) 통과.

작업 종료 시 자기 실행0을 확인하고 자기 임대를 삭제했다. `reloc19` 임대와 실행6개가 남아 VM 정지는 시도하지 않았다([정리 확인](lease-released.json)). 새52개 실행의 바깥 RUN_META만 초안PR542에 연결했으며 raw/manifest는 바꾸지 않았다([보존 원장](evidence-retention.json)).
