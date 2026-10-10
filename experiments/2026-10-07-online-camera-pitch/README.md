# egomap13 — 조건별 pitch 감사와 온라인 Manhattan 소실점

## 구현·영상 계산 전 사전 등록 (2026-10-07)

시작 SHA `d857d79b`, PR #405 `claude/ego-wall-map`. 이번이 자기 지도 트랙의 마지막
개발 반복이다. `floor_boundary_v1`, `servo_fk_v1`, egomap12 실패를 보존한다.
MuJoCo 실행·렌더·모델 호출0. #406은 egomap12에 보존한 `dc65cf6f` 소스만 읽는다.

### 조건 감사 (평가 전용)

- s1045–1047과 s1050의 모든 저장 own 프레임을 시각으로 camera-pose/trajectory/supervisor와
  정확히 join한다. 자기 명령 팔 자세: SEARCH `740,2320,1320,1500`, HIGH `896,2035,1894,1500`,
  real CARRY `600,2200,1400,1500`, 나머지 PICK/transition(각 PWM 키도 별도 보존).
- 실제 적재 평가는 양쪽 손가락 접촉+블록 최하점>0.01m이면 held-airborne,
  접촉 없음+최하점≤0.005m이면 unloaded-ground, 나머지는 ambiguous로 남긴다.
  명령 집게 닫힘을 실제 적재로 간주하지 않는다. GT 분류는 추정기에 전달하지 않는다.
- 평가용 GT xy·yaw에 중앙 차분: 이동=속도>0.01m/s 또는 회전>1deg/s,
  가속/감속=속력 변화율>+0.05/<−0.05m/s², 나머지 steady. 임계는 구간 표기용이며 튜닝하지 않는다.
  팔 PWM3–6 변경 후0.5s 미만은 settling, 나머지 settled로 분리한다.
- 각 조건 및 자세×적재×이동×가감속×정착 교차표에 n, actual−unloaded pitch의
  P05/중앙/P90/P95, 실제 pitch, unsigned 차체 tilt를 기록한다. #406 loaded 표 차이도 평가용으로만 병기한다.
  signed 차체 roll/pitch·실측 관절은 기록에 없으므로 팔 처짐과 차체 pitch의 인과 분해는 하지 않는다.
  차체 tilt는 pitch 기여의 상한이며 잔여 |pitch 차|−tilt 하한도 기록한다.
  s1050 운반(71–236.8s)의 기존1.53cm 결과는 다른 자세·분모의 비교이며 합산하지 않는다.

### 고정 방법과 옵션

Lu et al. WACV2017의 Manhattan 소실점 방법을 고른다. 공개 Python 구현
`rayryeng/XiaohuLuVPDetection@56b8a2b3c5a12f02430d3d4c4612aaff79d2e6ed`의 MIT 원문을
그대로 보존한다. 고정 카메라 K, 기존 fisheye undistort, 자기 RGB만 사용한다.
바닥 texture 대응/벽 높이 대응/정답 선분이 필요 없는 점이 선택 이유다.

- `camera_pitch=off` 기본: 기존 출력 bytes 동일, 영상 판독/VP 실행 추가 없음.
- `camera_pitch=online_vp_v1`: 기존 `v3_unloaded_extrinsic_v1` 기하에 적용.
  원문 LSD 최소30px, 구면1° 격자·가설 생성·점수 그대로, RNG seed1337 고정.
  K의 fx/fy가 다르면 x만 fx→fy로 rescale하여 원문의 단일 focal 입력을 충족한다.
  원문의 VP 부호/축 순열만 명령 기반 nominal 수직축에 가장 가까운 것으로 결정한다.
  수직축 차≤30°, 원문6° 선분 cluster 기준으로 수직≥2선분과 다른 축≥2선분일 때만 사용.
  수직 ray의 z 성분에서 pitch=asin(z), nominal yaw/roll/카메라 원점은 유지한다.
  선분 부족/모두 평행/비유한 값/축 모호/지지 부족이면 abstain→nominal 반환, 이유 기록.
  원문 수치/threshold를 개선하거나 오차에 맞추는 보정·평활화·시간 튜닝은 하지 않는다.
  단일 프레임 추정이므로 미래 프레임/지도/다른 로봇/GT 입력0.

### 관문 (egomap11/12 그대로)

봉인 수동 접점36프레임·96열·ignore·baseline 양의 깊이/4m 고정 분모를 그대로 쓴다.
**각6건** 고정 점≥50, 양의 깊이100%, 4m 유효율≥95%, 중앙≤0.10m, P90≤0.25m,
baseline 중앙 비악화, 뒤 교점0, off bytes 동일, GT 입력0. abstain도 nominal로 채점하여 분모를 줄이지 않는다.
s1042/1043 개발 → 설정/소스 동결 commit → s1044–1047 확인 재생1회. 이미 본 자료는 새 확증이 아니다.
사전 고정된 방법은 개발 실패여도 튜닝 없이 확인하고, **6/6 관문 실패 시 트랙 중단**.
모두 통과 시에만 RBPF100+positive_depth+pose_graph+wall_confidence 재생/지도 그림을 갱신한다.
§17·§19/positive-depth 기준 불변. 온라인 VP 실패 그림/조건 표는 지도 갱신과 구분한다.

raw `/Users/changmin/projects/ugrp/outputs/online-camera-pitch-v1/`; 원본·미추적4파일 보존.
입력/소스/예측/결과 hash 보존, ENOSPC=HOST_ERROR. 의존성 설치/venv 변경 없음
(기존 OpenCV5에 원문이 실제 사용하는 LSD가 있음; contrib API 사용 없음).
시험 통과 후 commit/push, Codex trailer, DRAFT 유지·병합 없음. TensorBoard 기존 면제/Drive 미사용 유지.
실패 시 마운트 외부 보정, 각 자세·하중별 실측 관절/차체 signed attitude 등 필요한 실물 측정만 정리한다.
