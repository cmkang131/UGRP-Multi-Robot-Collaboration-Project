# egomap17 — 동결 시차 검출기의 이동 baseline 원인 분리

2026-10-07 사용자 요청. PR #409 결과 보고·push(313f3d32) 후 PR #405(0fcce36c)로 복귀.
**구현·GT-baseline 재생 전 사전 등록.** egomap16의 무늬 on north/south 두 녹화만 재사용한다.
원 RGB·명령·수동 주석·parallax_v1 17파일/문턱·기존 결과는 수정하지 않는다.
새 물리 실행/렌더/모델 호출 없이 원인 분리부터 한다. GT는 평가 진단에만 사용한다.

## 가설과 비교

평행 시선의 이상적인 stereo에서는 깊이가 baseline에 비례한다. 그러나 현재 카메라는 회전·
시간 지연·추적 오차가 있을 수 있으므로 전체 왕복 폭2.235/2.280배를 모든 track에 일괄 적용하지 않는다.
이 녹화의 replay는 M1 평균+V7 구조 잡음이며 #406 v122의 finite-pulse 보정 모델과 다르다.
이를 이미 알고 있어도 GT 이동량 진단 없이 모델을 채택하지 않는다.

1. 기존 명령 DR로 frozen RGB/LK/ROI 추적을 재생하고 저장 prediction bytes와 대조한다.
   삼각측량 호출 history(같은 uv/시각/명령 pose/cov)를 별도 저장한다. 추적 유지/seed는
   triangulate 수락 여부에 의존하지 않으므로 같은 history로 geometry만 재평가할 수 있다.
2. **주 진단 `eval_gt_translation_only`:** 각 history의 body XY를 GT 출발 좌표계의 상대 XY로
   바꾸고 **yaw·카메라 높이/pitch/roll/팔 보정·intrinsic·DR 공분산·픽셀·문턱은 유지**한다.
   GT yaw는 출발 좌표 정렬 한 번에만 사용한다. 현재 프레임의 body-local 출력은 기존처럼
   현재 GT 차체 pose로 채점하므로 전역 DR 누적 오차와 깊이 오차를 섞지 않는다.
3. **척도만 분리한 보조 진단 `eval_gt_length_only`:** history 끝점 간 GT body XY 거리 / 명령
   body XY 거리 비율로 history의 모든 camera-centre offset을 현재 camera centre 주위에서
   균일하게 조정한다. 회전/픽셀/문턱/공분산 그대로. GT 방향·시간별 궤적은 사용하지 않는다.
   카메라 lever arm은 pose 입력을 역산해 유지하며, 출력 좌표 원점은 현재 body 그대로다.
   명령 baseline0이면 척도 비율을 정의할 수 없어 그대로0으로 남긴다(임의 epsilon/pseudo baseline 없음).
4. 각2건의 전체 P/주석 R/오차 중앙·P90·RMSE, 수락점 수·거부 사유 및 기존 수락11점의
   같은 track/frame 결과를 따로 기록한다. 누락/거부를 오차0으로 처리하지 않는다.
   GT 진단은 `own_only=false`, **항상 비채택**이며 지도·제어 성공으로 보고하지 않는다.

## 사전 판정·조건부 진행

기존 관문(P≥90%, 주석P≥90%/R≥70%, 중앙≤.10m/P90≤.25m, 바닥투영P 비감소,
양성≥50열/주석TP≥30열, off bytes·own-only·양의 깊이)을 **변경하지 않는다**.
GT에는 수치 관문만 참고로 계산하고 own-only가 아니므로 운영 관문 통과로 간주하지 않는다.

이동량 가설은 전체 수치와 **같은 기존 수락점의 변화**를 함께 판정한다. 두 녹화에서 GT XY 진단의
거리 중앙≤.10m와 P≥90%로 회복되면 이동량 교정 단계로 간다. 이보다 못하면 baseline 단독으로
현재 오차가 해결되지 않은 것으로 기록하고 추가 후보 튜닝·지도 재생 없이 멈춘다.
이 조건은 기존 거리/precision 기준을 재사용한 원인 분리 분기이며 새로운 최종 성공 기준이 아니다.
회전은 고정하므로 실패가 추적만의 잘못이라는 인과 결론은 내리지 않는다.

회복 시에만 PR #406의 **v122 `v7_pulse_cal_v1`** 계수/응답 함수를 고정 SHA에서 복사하고,
자기 명령만 받는 새 옵션(기본 off)으로 연결한다. v122가 같은 횡이동을 여전히2배 과대하면
이 두 평가 녹화로 계수를 적합하지 않는다. 별도 보정 자료의 출처·분할·회귀식을 먼저 사전 등록하고
표준 명령–실측 회귀로 진행한다. 필요한 별도 자료가 없으면 새 취득은 별도 등록 후에만 한다.
#406 파일/다른 worktree는 수정하지 않으며 다른 버전(v125+)으로 바꿔 재튜닝하지 않는다.

고친 own-command 모델의 두 texture-on 재생이 기존 관문2/2일 때만 egomap16에 등록한
짧은 texture-on 탐색 녹화1개 및 RBPF100+pose_graph 지도/2D 그림 단계로 간다.
GT 진단 수치로 이 단계에 진입하지 않는다. 실패 시 멈추고 결과 그대로 기록한다.

## 출처·보존

- [OpenCV triangulatePoints: 두3×4 투영행렬로 homogeneous 3D 복원](https://docs.opencv.org/4.2.0/d9/d0c/group__calib3d.html).
  [OpenCV stereo geometry](https://docs.opencv.org/5.0/main_modules/stereo.html)의 baseline/disparity 설명.
  기존 DLT/LK 구현·표준 검사는 [egomap14 REFERENCES](../2026-10-07-wall-parallax/REFERENCES.md) 그대로.
- #406 읽기 전용 기준 SHA `45b0c173d34f53c2016e2560cdc70c9a908a8325`:
  `harness/zone_s2_realism_contract_v122.py`, `harness/zone_solo_cyan_pulse_cal.py`,
  `configs/s2_motion_v7_pulse_cal_v1.json`, `scripts/fit_s2_pulse_calibration.py`.
  원 모델 SHA256 `2245bb9fdcb69d872893dd6ffafb57151750dd42916394a287b6d10bab11d69d`.
  모델은 과거 S2 자료의 탐색적 평균 응답/분산이며 실물·독립 확증 보정으로 부르지 않는다.
- GT 진단 어댑터는 이 실험 폴더에만 둔다. harness에 GT 옵션/GT loader를 넣지 않는다.
- raw `/Users/changmin/projects/ugrp/outputs/wall-parallax-baseline-v1`, 원본 보존,
  ENOSPC=HOST_ERROR, 같은 원인 두 번 중단. wall-time 성능 측정/물리 실행이 없어 잠금 없음.
  결과/그림/해시는 로컬+Git, raw 원격 백업으로 주장하지 않는다. TensorBoard 기존 사용자 면제 유지.
- 관련 시험 통과 후 commit/push, `Co-Authored-By: Codex <noreply@openai.com>`, PR #405 DRAFT·병합 금지.
