# egomap32 — v122 양방향 회전 모델 진단

2026-10-08 결과 전 사전 등록. egomap31 실행/결과462473cb/e7b28ee4,
seed31001 고정 녹화를 개발 재생으로 사용한다. 기본 off, PR405 DRAFT,
PR406 파일 변경0. TensorBoard 생략 유지. 모델 호출/원격 자원0.

## 표준과 변경 범위

Borenstein & Feng, UMBmark (1994 기술보고서; 확인한 공개 원문은 1995 SPIE판)
§3.2–3.4/p5–8: 양방향 각5회 평균과 반복 산포를 분리한다.
[원문](https://www.cs.columbia.edu/~allen/F17/NOTES/borenstein.pdf).
원본은 차동구동 4×4m 사각 주행이다. 이번에는 사용자 지정 메카넘 회전 펄스만의
**축소 진단**이며 완전 UMBmark/바퀴 간격 추정으로 부르지 않는다.
두 방향의 편향을 합쳐 상쇄하지 않는다. 물리/마찰/롤러 파라미터를 바꾸지 않는다.

v122는 PR406 45b0c173에서 복사한 finite-pulse response,
`harness/data/s2_motion_v7_pulse_cal_v122.json` SHA256
`2245bb9fdcb69d872893dd6ffafb57151750dd42916394a287b6d10bab11d69d`.
PR406 `scripts/fit_s2_pulse_calibration.py`의 펄스 응답 평균/잔차 분리와 같은 배치 추정이다.
현재 모델은 무하중 turn±0.35/0.10초, 꼬리 포함0.20초,
−5.9348°/+5.3691°를 예측한다. egomap27의112.75°/124.98°는 가설 출처일 뿐
새 계수 적합에 쓰지 않는다. SEARCH·강성 on의 새 전용 측정만 적합 자료다.

## 고정 측정 계획·판정

- seed32001, 기존 egomap31 scene/spawn/tape/SEARCH/강성/v7/port, 무하중.
  시작2초 정착 후 좌/우 × 단발1펄스/연속10펄스 × 각5반복 =20블록/110펄스.
  명령±0.35, on0.10초, cycle0.20초, 블록 뒤1.8초 정착.
  반복 홀짝에서 방향/블록 순서를 반대로 하여 순서 효과를 줄인다.
  모두 미리 정한 clock 명령이며 GT에 따른 자세/명령 재설정0.
  20Hz 평가 yaw/차체/휠 상태, 1Hz RGB를 저장한다. 각 블록 시작·0.20/2.00초·
  추가1초에서 평가하여 모델 horizon 이후 회전 잔류도 분리한다.
- 반복1–3 적합, 반복4–5 확인(방향×모드마다2개, 작은 DEV 자료).
  각 방향에서 `실측 yaw/펄스 수 = gain × 기존 예측 yaw/펄스 수` 원점 통과 최소제곱.
  평균·표준편차·방향별 gain 및 단발/연속 차이를 모두 기록한다.
  두 모드의 평균 gain 차이가5% 초과하거나 두 방향 중 하나라도 gain의95% 신뢰구간
  하한이1 이하이면 **일관된 회전 이득 과소 가설 미확인**. 속도 의존/접촉/롤러 영향은
  진단만 기록하며 gain으로 덮지 않는다. 시뮬 결함 자체는 실물 비교 없이 확정하지 않는다.
- 위 가설 확인 + 확인 세트 두 방향 각각 yaw RMSE 감소일 때만
  `motion_model=s2_pulse_v122_rot_v1` 후보를 연결한다(기본off).
  기존 두 turn profile의 yaw mean만 각 방향 gain으로 조정. XY·다른 profile·잡음·
  RBPF/CSM/graph/탐색 문턱은 불변. 실행 입력은 자기 명령만, 평가 GT는 런타임 금지.
- egomap31 전체891 제어프레임 off/on 재생. off full trace bytes 동일 검사.
  회전/yaw RMSE, 종료오차/σ 비율, 영역P/R·덮임·전체벽 RMSE/표본 수 보고.
  새 seed 물리 조건: yaw RMSE·종료오차·과신 비율 모두 감소,
  영역P/R·덮임 비감소 및 벽RMSE 비증가. 하나라도 미달하면 추가 물리0.
  통과 시에만 seed32002/180초 물리1회, egomap31 조건+새 모션 옵션, 결과 후 변경0.

agent_lock null에서만 단독 측정/물리, ugrp_session/표준 workflow, freeze0.
측정60 SIM초 이내/호스트15분, 탐색180초/30분. raw 예산700MiB,
`outputs/pulse-rotation-audit-v1`, 여유10GiB 미만/ENOSPC=HOST_ERROR.
원본/raw 삭제0, 초록 관련 시험 후 커밋·push. supervisor 단계별 확인.
결과는 PR406 코멘트로 공유하되 그 소스/보정표 수정0.

## 측정 전 검증

사전 등록 `6fcde9b4`. 관련 시험8개(측정3/기존 odometry4/workflow plan1) 통과.
off byte golden/기존 profile means·공분산 검사 포함, 물리와 평가 입력 분리 fake backend 확인.
PR406 최신 읽기 전용 `da3d2eb8`의 v122 JSON은 복사본과 SHA256까지 동일하다.
`self_pulse_odom.py:44–48,73–98`에서 .05초씩 response curve를 누적하며,
원본 `fit_s2_pulse_calibration.py:32–43,95–102`는 profile 평균·산포를 별도로 산출한다.
계수·드라이버·평가 코드 hash는 [freeze](freeze.json), PR406 근거는 [source audit](source-audit.json).
물리 실행 전 여유46.66GiB, agent_lock null 확인. 실제 획득 직전에 재확인한다.
