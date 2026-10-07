# egomap19 — 시뮬 서보 강성과 v122 이동 모델 (사전 등록)

2026-10-07 사용자 변경 지시: 명령각에서 처짐을 보정하는 `servo_sag_v1` 작업을 취소한다.
취소 시 source 변경/새 미커밋 파일0, 기존 사용자 미추적4파일 보존. 사용자 판단은
“실물 MasterPi 팔은 무게로 거의 처지지 않는다”이다. 이를 시뮬 후보의 근거로 쓰되
실측 강성/카메라 정확도를 확인한 것으로 표시하지 않는다. 시작 SHA `410b056a`.

## 고정 후보와 출처 경계

- A `servo_stiffness=real_v1`, 기본 off. 전용 Scene wrapper에서 r3의 회전 서보4개만 변경.
  off는 XML 동일 객체 반환. S2 공용 소스·#406 파일·집게 slide·중력·질량·접촉·카메라 mount는 보존.
- 제조사 MasterPi 표: LD-1501MG와 LFD-01M. 레포 v3 도면 분류를 따라 yaw/어깨는 LD,
  팔꿈치/손목은 LFD로 모델링한다. 실물 개체의 라벨·전압은 미측정이며 LDX-218 변형도 존재한다.
- LD 공식 파라미터 이미지: 위치 정밀도0.3°, 정지 토크13kgf·cm@6V /17@7.4V.
  LFD 공식 표:1.8kgf·cm@6V. **LFD의 수치 데드밴드는 공식 자료에서 확인하지 못했다.**
  아래0.3°는 LD 정밀도를 공통 설계 목표로 사용한 가정이며 LFD datasheet 값/실제 deadband로 부르지 않는다.
- 6V 후보, 회전 torque cap=각 공식 정지토크×0.0980665 N·m. 선형 PD `kp=cap/radians(.3)`:
  LD243.480 N·m/rad, LFD33.713 N·m/rad. 이는 토크/위치 사양을 연결한 **보수적 시뮬 설계**이며
  실제 torque-angle 곡선의 식별 결과가 아니다. 포화 유지, 무한 토크/position weld/중력상쇄 없음.
  MuJoCo `position dampratio=1`(reference inertia 기반 임계 감쇠)을 그대로 사용,
  기존 joint damping과 implicitfast 적분·timestep 유지. 파라미터 재튜닝 없음.
- B `motion_model=s2_pulse_v122`, 기본 off. #406 `45b0c173`의 고정 finite-pulse mean curve와
  prediction variance를 복사한다(원본 JSON bytes/hash 유지). source의 initial-body-frame 곡선 보간과
  정지 tail을 그대로 사용. 누락/복합/조기 중단 명령은 오류로 기록하고 M1으로 묵시 fallback 금지.
  명령 시간당 독립 증분 잡음과 Jacobian으로 covariance 전파; 정답은 입력이 아니다.
  s1052 1.015배는 #406의 별도 무하중 평가이며 새 강성 조건에 승계하지 않는다.

## 실행 순서·고정 관문

1. 이 README/REFERENCES를 관련 기존 시험 통과 후 먼저 commit/push. 구현도 시험 후 commit/push.
2. 정적/집기 진단 off/on 각각1회, seed19101, north와 같은 시작. SEARCH→HIGH→hover를
  각6초 관측(마지막2초 통계), 그 다음 기존 `grasp_postures` 7단계(각1초), close2초,
  hover4초→`raise_path` 각4/4/8초→좌우.65/.65s 운반 펄스 각각1회, 총≤56 SIM초(+reset5초).
  블록은 시작 시 고정 CAD의 floor-grasp pad 중심 아래 바닥에 놓는 **설정용 fixture**다.
  이후 위치 수정·weld·GT 행동 피드백0. 이것은 기계 진단이며 자율 집기/운반 성공으로 부르지 않는다.
  GT qpos/카메라/블록은 평가 로그와 안전 abort만. 집기 실패도 그대로 기록한다.
3. 정적 관문: SEARCH/HIGH/hover의 마지막2초에서 body-relative optical pitch 오차
  절댓값 P95≤0.3°, 각 관절 오차 P95≤0.3°, 관절 peak-to-peak≤0.3°.
  비유한/차체기울기>10°/지속 진동/블록 낙하 실패0. 집기 성공은 block z>.06m 후
  운반 내내 유지로 평가. off도 집기에 실패하면 fixture/집기 안정성 **미검증**이며 성공으로 대체하지 않는다.
  정적 관문 미달이면 횡이동 취득 중단. 하중 진단 실패는 분리 보고하며 빈손 관문과 합산하지 않는다.
4. 정적 관문 통과 시 **강성 on+tape_v1** 북/남2개를 기존 egomap16과 동일
  seed15101/15102·spawn·18초·8펄스·SEARCH·RGB10Hz로 다시 취득. 다른 로봇 freeze0.
5. 같은 주석 선정 규칙: eligible frame의 중앙6분위, 예측 전 RGB 수동 주석·봉인.
  old egomap16 데이터는 기존 결과 그대로. 새 녹화는 M1/원 보정표, M1/명령FK,
  v122/원 보정표, v122/명령FK 네 조건을 나란히 재생한다. 명령 FK는 기존 `servo_fk_v1`,
  새 처짐 보정/바닥 검출/시차 설정 변경0. 기존 보정표는 무른 서보의 평형을 포함하므로 분리 비교한다.
6. 바닥 투영 관문은 egomap11 그대로: 고정 주석≥50, 양의 깊이 전부,4m 내≥95%,
  GT body 투영 중앙≤.10m·P90≤.25m·기준 중앙 비증가. 시차는 egomap14 그대로:
  전체P≥.90, 주석P≥.90/R≥.70, 중앙≤.10m/P90≤.25m, 주석≥50/TP≥30,
  같은-frame 바닥P 비감소, off bytes·자기 입력·양의 깊이. 공분산/특징/threshold 튜닝 없음.
7. 둘 중 한 방법이 **북/남2/2** 관문 통과하고 하중 안정성 실패가 없을 때만
  별도 tape+강성 on 짧은 탐색1개(seed19103,30초, egomap16 사전 경로의 전진은 기존
  RealPrimitivePort 허용어휘 forward±.35/.10s로 명시). 통과한 쪽(둘 다면 중앙오차 작은 쪽)으로
  v122+RBPF100+pose_graph 및 GT 회색/지도 신뢰도/경로 그림 생성. 실패 시 추가 취득/지도0.

관문은 수정하지 않는다. 새 자료는 플랫폼 변경 DEV이며 기존 녹화와 합산/확증 승계하지 않는다.
agent_lock status null→자신 PID acquire→ugrp_session/관리 workflow→release, 한 번에 하나.
총≤190 SIM초·raw≤350MiB, 여유10GiB 필요. ENOSPC=HOST_ERROR/부분raw 보존,
같은 원인 두 번이면 중단. 모델 호출0·freeze0. 실행 소스/명령/환경/원본 hash 저장.
raw `/Users/changmin/projects/ugrp/outputs/servo-stiffness-v1/`, TensorBoard 생략 지시/Drive 예외 유지.
시험 후 commit/push·Codex trailer, PR405 DRAFT·병합/force/reset0·#406 수정0.

## S2에서 선택할 때 필요한 재보정 (이번에는 #406 변경 없음)

21자세 무하중 camera extrinsic, HIGH/집기/운반 자세별 하중 extrinsic, servo 이동·정착시간,
그리퍼 접근/집기/들기·낙하/진동, v7 finite-pulse 평균/공분산(하중·팔높이별), RGB 위치추정
관문을 새 plant hash에서 다시 확인해야 한다. 종전 table/RMS·s1052 pulse 비율을 그대로 승계하지 않는다.
intrinsic/FOV/mount는 바꾸지 않지만 camera-body transform은 새 실제 평형에서 확인해야 한다.
초음파는 제안만 유지, 판독 활성화/제어 연결0.
