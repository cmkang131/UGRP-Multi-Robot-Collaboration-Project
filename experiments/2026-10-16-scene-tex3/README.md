# scenetex3 — 렌더 화질 우선 조사 · 벽/바닥 질감 3차

**NOT_READY. 3라운드 종료, 기본 off 유지.** 상자 검출 PNG/JPEG90/PIL82는 각각 88/88로 v1과 일치했지만, 바닥 특징·연속 매칭과 기존 selfmap 벽 경계 입력이 v1보다 낮은 시점이 남았다. JPEG90 구역 A 지원도 한 사건에서 2px 줄었다. 새 장면·화질을 제어기/ACT 기본값에 연결하지 않는다. [요약](summary.json), [누적 관문·거부표](rejection-table.json), [전체 분포](round3-final/summary.json).

실험 렌더 소스 `31286f8774e81a02aef016e95f3deb6edabff98e`, 장면 `walls_floor_textured_v3`, 비교 화질 `native` / `wall_no_mip_v1`. 최종 자산 manifest SHA256 `521b6fa532222267061127bd373cfd0d6032b502f4508caf6c51aa349300698d`, 장면 정의 SHA256 `c62414c947d0c93dcb730e230555b713756f138d6332da5e1c4fea2a62900631`이다. 같은 이름의 R2는 소스/manifest가 다른 탐색 후보이며 합산하지 않는다.

## 요청과 범위

2026-10-16 사용자: “근데, 실제 로봇 카메라는 바닥 특징점 되게 인식 잘 하던데? -> 시뮬 화질 높여보는 게 어때”. 이전 요청은 “벽에도 넣고, 벽 / 바닥 색 다르게 해 … 그 상황에 효율적일 수 있는 알고리즘으로 다시 설계 … 첨부터 다시는 말고”다.

gcp2의 같은 네 지도·같은 88 시점을 재사용했다. 물리 step·모델 호출·Mac 렌더·GUI는 모두 0이다. 각 시점에서 추가로 `atan(1/fx)`=약0.0925°만큼 자기 로봇 base yaw를 바꾼 **정적 평가 쌍**을 만들었다. SIM시간은 계속 0이며, 주행/VO 정확도·교사/ACT·운반 성공·실물 성능을 검증한 결과가 아니다. 정답·분할 ID는 평가 전용이다.

## 0) 수정 전 비교와 실제 위치 추정 신호

[수정 전 원본 재집계](before-change.json), [수정 전 거부표](before-material-rejection.json). 주행16 PNG 바닥 ORB는 v1 합271·중앙16.5 → v2 합249·중앙13.5로 **회귀**했다. 벽 합195→487로 바닥 회귀를 상쇄했다고 판정하지 않는다. 기존 scenetex2의 JPEG 상자 변화6/88·벽 내부support 부족13/16을 먼저 기록했다. 벽 미노출16/16은 별도 장면 한계다.

v1도 주행16 중14장이 바닥 내부 ORB20=0이었다. 경계에 걸친 descriptor와 표면 내부 특징을 분리했다. [selfmap 소스 대조](selfmap-signal-provenance.json): `selfmap4_geometry.observe`는 벽–바닥 경계 컬럼/선분, `PlaneFlow.step`은 `e2e_rgb_vo.ground_pair`의 Shi–Tomasi/LK+homography를 쓴다. 별도 natural-floor 경로에는 FAST7도 있다. `ground_pair`·`image_mask`·camera transform 함수 본문은 이번 소스와 map-selfmap checkout에서 동일했다. reloc15의43/45→6/45는 gcp1 기록이며 이번 개선 근거/분모로 사용하지 않았다.

최종 저장 RGB만으로 [실제 입력 성분](selfmap-signal-summary.json)을 다시 측정했다. PNG 기준:

| 조건 | 벽 경계 컬럼 중앙값, 적격56 | LK tracks 중앙값 | LK `measured` 출력 |
|---|---:|---:|---:|
| v1/native | 88 | 80 | 50/56 |
| v2/native | 62 | 238 | 44/56 |
| 최종 v3/native | 87 | 90 | 50/56 |
| 최종 v3/벽 전용 no-mip | 63 | 90 | 50/56 |

HIGH/가림32시점은 기존 `loaded_or_unknown_load_not_qualified` 카메라 가드를 그대로 받아 미적격이다. 상태50/56은 해당 성분의 출력이며 실제 위치 오차나 제어기 성공이 아니다. 특징 수가 늘어도 기존 균일 벽 경계 정합 입력은 줄 수 있다.

## R) 현재 렌더 경로와 단계별 손실

- `sim/masterpi_dynamics_v2.py`가 offscreen 버퍼를1280×720으로 설정한다. `MultiMasterPiProductionV2._create_renderers`의 로봇 viewport는 실제640×480이다. gcp2 기본 `offsamples=4`, GL 실제4·상한4다. MSAA8을 요청해도4로 제한됐다.
- `sim/masterpi_camera_profile.py`의 K(fx619.519454, fy622.165488, cx287.689106, cy218.696866)와 D4를 고정한다. `raw_fisheye_remap`이 raw pixel→ideal pinhole 역방향 map을 만들고, `multi_masterpi_production._render_rgb_direct`가 `cv2.remap(... INTER_LINEAR, BORDER_CONSTANT)`를 적용한다. sensor geomgroup4/5 제외 정책을 재사용했다.
- 기본 mount 갱신은 `MasterPiDynamicsV2._sync_real_camera_mount`다. 이 비교는 기존 scenetex2와 동일한 v3 mount를 명시한 `probe_scene_tex2.build_model`을 썼다. v3 실행 binding은 `sim/s2_realism_camera_binding.py`에 있다. v3는 사용자 관찰 목표의 고정 mount이며 독립 실물 보정 완료를 뜻하지 않는다. 카메라 위치·FOV·최종 K/D/640×480을 유지하고 카메라 소비 주기 코드를 바꾸지 않았다.
- MuJoCo3.12 classic은 2D/cube `GL_LINEAR` 확대, `GL_LINEAR_MIPMAP_LINEAR` 축소와 `glGenerateMipmap`을 쓴다. 실제 GL 설정을 각 run `models.json`에 저장했다.
- `MultiMasterPiProductionV2.render_jpeg` 기본은 PIL quality82이며 `CameraRobotPort.capture`가 이를 호출한다. 이전 관문은 OpenCV JPEG90이었다. 이번에는 PNG·OpenCV90·PIL82를 모두 비교했다. 조명은 기존 밝은 no-shadow·반사0 조건이고16개 최종 model variant에서 castshadow=0을 확인했다.

단계별 ORB20/7·내부support·라플라시안 분산은 [R1 모든 arm](round1/)에 있다. 같은 H1/view0/drive/r1의 바닥 ORB20 예:

| 무늬 | pinhole | fisheye/최종 PNG | JPEG90 | PIL82 |
|---|---:|---:|---:|---:|
| v1 | 38 | 32 | 30 | 26 |
| v2 | 27 | 34 | 31 | 26 |

remap이 특징을 새로 검출하게 할 수도 있어 개수가 단계마다 단조 감소하지 않는다. 이 시점의 내부support는 pinhole부터0이었다. 따라서 소실을 JPEG나 fisheye 한 단계만의 탓으로 결론내리지 않는다.

## 화질 후보 · 계산한 무늬 크기

R1은 세 기존 재질×6화질×88=1584 레코드다. 기준은 모두 v1/native다. 아래 ORB는 주행16 중앙값이며 검출은 전체88 시점의 종류별 개수 일치다.

| 화질 | 바닥 ORB v1/v2 | 벽 ORB v1/v2 | 상자 PNG v1/v2 | JPEG90 v1/v2 | v2 RGB 시간/기본 |
|---|---|---|---|---|---|
| native | 16.5/13.5 | 12/16.5 | 88/88 | 88/82 | 1.00× |
| 2× 렌더→고해상 remap→area 축소 | 13/13 | 17.5/59 | 80/78 | 86/84 | 1.80× |
| MSAA8 요청(실제4) | 16.5/13.5 | 12/16.5 | 88/88 | 88/82 | 1.00× |
| cubic remap | 18/17 | 12.5/20.5 | 88/88 | 78/58 | 1.02× |
| nearest mip level | 16.5/13 | 12/26.5 | 88/88 | 88/82 | 0.97× |
| mipmap 없음, 전체 texture | 27/22 | 12/332 | 88/88 | 88/82 | 0.93× |

2×는1280×960 viewport와 offheight960을 쓰고 최종640×480으로 돌아온다. 최종 출력 해상도/FOV를 늘리는 후보가 아니다. SS2의 렌더 시간 중앙 증가도 약80%였다. 사용자 제공 RGB 비중3.0%를 단순 대입하면 전체 시간 약2.4% 증가 추정이지만 **실제 E2E 시간 측정은 아니다**. 시간은 같은 시점의 warm3회 측정이며 동시 부하/호스트 중단 전후 자료가 있어 비용 우열 확증에 쓰지 않는다.

[텍셀 투영](texel-scale.json): 바닥 텍셀16m/3072=5.208mm, drive camera 높이0.230716m. 전방0.5/1/2/3m에서 한 텍셀의 가로×깊이 방향 크기는 각각5.87×2.44 / 3.15×0.706 / 1.61×0.183 / 1.08×0.0819px였다. 3m 깊이축에서5–20px 구조는 약0.318–1.272m가 필요하다. 벽6.5m/1024 한 텍셀의 정면 pinhole 근사는0.5m에서7.87px, 3m에서1.31px다. 실제 면/방향/FOV에 따라 달라지는 국소 투영값이다.

R2는 이 계산으로1/3/10/32/100cm 다중 규모 얼룩과 불규칙 마모를 만들었다. 원거리 작은 입자의 평균화·밉맵과 낮은 대비가 함께 작용하므로 고해상 자산의 ORB767–793을 카메라 특징 수로 취급하지 않는다. 무늬 길이와12% 장식 coverage는 설계값이며 새로운 수용 상수가 아니다. 반복 타일·문자·인공 마커는 없다.

## 색 회귀 수정과 최종 관문

R2/native는 PNG88/88·JPEG90 86/88, cubic은88/88·62/88이었다. [빨강 상자 진단](red-box-component-diagnosis.json): two_doors JPEG90의 red contour 면적888→884px, 기존 cuboid projection IoU0.6657→0.5231로 기존 하한0.58을 밑돌았다. 검출기 HSV/형상 상수를 넓히지 않았다.

R3는 바닥 PNG를 **v1 원본과 byte 동일하게 복원**하고 벽의 새 다중 규모 자연 무늬만 유지했다. 새 벽 HSV S4/V100–138이고 바닥은 v1의 중립 회색이다. 어두운 cool 벽과 밝은 중립 바닥을 구분한다. `wall_no_mip_v1`은 natural wall texture의 축소 필터만 GL_LINEAR로 바꾸고 floor/sky/robot/object 필터는 유지한다. 새 색 분류기는 명시된 장식의 중립(B−R≤0)/cool(B−R>0)과 저작 V 범위로 구분하며 기존 상자/끝/구역 검출기에 연결하지 않는다.

최종 기본 비교는 **v1/v2/v3 동일264프레임 전체**다. 벽 전용 필터88장을 추가해 R3 분석 레코드는352다. [전체 per-frame IoU 분포·중앙·p05/p25/p75/p95·micro IoU](round3-final/)를 보존했고, 보이지 않는 정답/예측 둘 다0인 union0은 IoU=null로 분리했다. 새로운 IoU 합격 수치를 만들지 않았다.

| PNG 지표 | v1/native | v2/native | v3/native | v3/벽 no-mip |
|---|---:|---:|---:|---:|
| 주행 바닥 ORB 중앙 / 합 | 16.5 /271 | 13.5 /249 | 10 /220 | 11 /224 |
| 주행 벽 ORB 중앙 / 합 | 12 /195 | 16.5 /487 | 13.5 /200 | 53.5 /927 |
| 주행 벽 내부support 양수 | 0/16 | 3/16 | 3/16 | 16/16 |
| 전체88쌍 바닥 match 합 | 942 | 712 | 781 | 793 |
| 전체88쌍 벽 match 합 | 441 | 883 | 432 | 2527 |

최종 두 후보의 상자/legacy beam 의미 출력은 PNG·JPEG90·PIL82 모두88/88 일치한다. 별도 색 지원112사건 비교는 PNG 손실0, JPEG90 손실1: H2/paint_A/r1에서20,727→20,725px였다(최종 벽 필터). PIL82는 두 사건에서각1px 감소했다. 이는 전체 구역 형상 검출 검증과 구분하며 **전체 색 관문 통과를 주장하지 않는다**. 미노출 양성 대상도 미검증으로 남긴다.

누적 관문은 v3/native **88→88→87→30→30**, 벽 no-mip **88→88→87→40→34**다(전체기록→상자 PNG/JPEG→끝/구역 색 지원→카메라 특징≥v1→연속 매칭≥v1). 각 거부의 범주·대상·최소 틈(null/영상 관문이라 해당 없음)과 원본/재현 명령을 JSON에 남겼다.

최종 벽 필터의 IoU는 PNG 벽 중앙0.9312/바닥0.9865, JPEG90 벽0.8372/바닥0.8684다. PNG micro는벽0.9150/바닥0.9884, JPEG90은벽0.8597/바닥0.9394다. 최솟값0과 null을 제외한 한 장면 수치로 대체하지 않았다. 분할264분포와 추가88분포를 따로 보존한다.

후처리는 v3 색 분류기 하나를 v1/v2/v3 전체에 동일 적용했다. v1의 원래 균일 벽 검출 성능과 혼동하지 않는다.

[바닥 경계 검사](floor-boundary-diagnosis.json): v1 floor byte를 복원했어도 표면 중심 ORB는 낮아졌다. v3/native PNG 차이24,524px는 모두 바닥 경계로부터3px 이내이고, 3px보다 안쪽 변화는0이다. descriptor 전체가 바닥 안에 드는 ORB20은 주행 합2·전체 합205로 v1과 동일했다. **경계를 걸친 특징의 감소와 바닥 내부 무늬 소실을 구분**한다. 관문을 임의 완화하지 않았으며, 실제 selfmap 경계/LK 입력도 위처럼 별도 측정했다.

벽 no-mip의 렌더 시간 비는 v3/native 대비 중앙0.99255, RGB는0.99257(p05–p95 약0.936–1.017)이다. 증가를 관찰하지 않았으나 유의한 속도 개선을 확증한 측정도 아니다. 그림자·마찰·동역학·카메라 배열은 네 지도16모델 비교에서 동일했다.

가림16시점의 벽 가시/특징은0이다. 이는 texture로 해결할 수 없는 시야 한계이며 **관문 제외**, reloc16 설계 범위다. 원본의 자기 RGB 이외 입력을 제어에 추가하지 않았다.

## 실물 프레임과 검토 범위

`docs/masterpi_physics_calibration.md`, calibration/experiments/outputs, 기존 archive 포인터를 조회했다. native640×480 실물 원본 ZIP/보관 경로는 현재 없다. Git blob `f3276961fd32e62e213b4287da9200d324445954`의 실물 비교판(320×240 thumbnail6장)을 찾았다. [동일 ORB20/7·라플라시안 지표](real-thumbnail-metrics.json)를 gcp2에서 측정했지만, 수동 표면 ROI의 ORB20은0, ORB7은0–3, 라플라시안 분산5.27–9.96이었다. 축소·재JPEG된 실험대/표면 사진이며 같은 바닥/거리/자세가 아니다. 이 수치로 실물 바닥 특징의 수준이나 회복을 판정하지 않는다. 사용자의 실물 관찰은 정성적 근거로 유지하며 native 실물 대비 관문은 미확인이다.

GCP에서 만든 [R1](review/round1.jpg)·[R2](review/round2.jpg)·[R3](review/round3.jpg) 같은 시점 몽타주와 [JPEG 빨강 반례/복구](review/red-jpeg-comparison.jpg)를 이미지 파일로 직접 확인했다. R2에는 더 큰 얼룩이 보이지만 빨강이 육안으로 남아도 기존 투영 검출은 실패했다. R3의 v1 바닥 복원 후 검출이 돌아왔고, 벽 필터는 작은 벽 입자를 더 남겼다. 정적 t=0과 미소 yaw 쌍이므로 동적 실패/성공 영상의2Hz 전체·마지막10초10Hz 재생을 했다고 주장하지 않는다. 이 과제에는 실제 이동 궤적/학습 카메라/실패 고리 버퍼가 없다.

## 원본, 중단, 재현

원본은 `/home/ugrp/ugrp-sim/runs/scenetex3-r1*`, `scenetex3-r2*`, `scenetex3-r3*`와 preservation 목록 경로에 있다. [보존 검사](preservation.json)의 기존 manifest 불일치는0이다. 중복 baseline 링크를 포함한 파일 참조 수이며 서로 다른 후보/라운드를 합산하지 않았다. 큰 JSON은64KiB 기준 zstd·복원 SHA 검사 후 저장했다. Mac은 요약·작은 원장·해시·몽타주만 회수했다. UGRP 기록은 로컬 프로젝트/GCP 영속 디스크에 보존한다.

초기 계수 JSON int64 저장 오류(R1a, 완료0)와 병렬 분할을 위한 중단(R1b,64/1584)을 별도 보존했다. R1b 원래 writer의 `MEASURED` 필드는 완결성을 검사하지 못한 결함이며 완주로 쓰지 않았다. 현재 writer는 계획 개수까지 확인한다. [외부 VM 정지](host-events.json)는2026-10-15 16:16:44 UTC에 다른 로컬 Claude Code의 gcloud stop으로 기록됐고, 예산 함수 로그는 해당 구간에 없었다. 사용자 규칙14로 gcp2를 다시 시작했다. 이전 미완료 원본을 덮어쓰지 않고 저장이 끝난 동일 자세·이미지 SHA 레코드만 새 사본에 연결해 빠진 시점만 재실행했다. resume 출처는 각 레코드에 있다. 소스 사본은 모두 공통 bare를 직접 reference했고 다른 사본의 alternates를 쓰지 않았다.

실험 코드는 렌더 전에 커밋했다. R1 초기2eaafdf7→복구573c1c8b(기존 재질/샘플러 계산 유지), R2는573c1c8b, R3는31286f87이다. 분석 스크립트 SHA도 각 요약에 있다. 동적 실행/학습/LLM 배치를 내지 않았고3라운드 뒤 추가 렌더는0이다. 후속 selfmap/픽셀 검사는 저장 이미지 읽기만 썼다.

재현은 raw `meta.json`에 전체 명령을 보존했다. 핵심 명령은 아래와 같다. 새 output을 쓰고, gcp2의 정확한 소스/기존 환경에서만 실행한다.

```sh
MUJOCO_GL=osmesa python -m scripts.probe_scene_tex3 --execute --source-sha 31286f8774e81a02aef016e95f3deb6edabff98e --materials floor_light_textured_v1 walls_floor_textured_v2 walls_floor_textured_v3 --qualities native --output <new-run>
MUJOCO_GL=osmesa python -m scripts.probe_scene_tex3 --execute --source-sha 31286f8774e81a02aef016e95f3deb6edabff98e --materials walls_floor_textured_v3 --qualities wall_no_mip_v1 --output <new-wall-run>
python scripts/combine_scene_tex3.py --inputs <new-run> <new-wall-run> --output <combined>
python scripts/summarize_scene_tex3.py --input <combined> --output <analysis>
python scripts/score_scene_selfmap_signal.py --input <combined> --output <signal-analysis>
```

렌더는31286f87 고정 사본에서, 후처리 분석은 이 PR 최종 scripts 또는 기록된 analysis-tools 파일 SHA의 코드를 사용한다.

`--resume-from`을 쓸 때 R3는 반드시 `--resume-materials floor_light_textured_v1 walls_floor_textured_v2`로 제한한다. R2의 같은 이름 v3 프레임을 최종 v3로 재사용하면 안 된다. 재질·화질·카메라 기본값은 변경하지 않았다. Mac 표적 PNG/XML/순수 시험은 **61 passed in10.02s**, 물리/렌더 검증은 위 gcp2 정적 관문과 구분한다.

## 참고 자료 (2026-10-16 원문 확인)

- https://raw.githubusercontent.com/google-deepmind/mujoco/3.12.0/src/render/classic/render_context.c
  2D/cube magnification GL_LINEAR, minification GL_LINEAR_MIPMAP_LINEAR,
  glGenerateMipmap. MSAA는 GL_MAX_SAMPLES로 clamp된다.
- https://raw.githubusercontent.com/google-deepmind/mujoco/3.12.0/src/render/classic/render_gl3.c
  texuniform/texrepeat와 면 좌표. 자산 해상도만으로 카메라 텍셀 크기를 판단하지 않는다.
- https://docs.opencv.org/4.13.0/da/d54/group__imgproc__transform.html
  inverse remap 보간과 area resize. 보간은 소실된 정보를 복원하지 않는다.
- https://tartanair.org/environments.html 및 https://tartanair.org/modalities.html
  다양한 실제감 환경·조명, PNG RGB와 noise/blur 도구. 5–20px 패턴을 권장한다는
  수치는 이 문헌에서 확인하지 못했다(이번 사용자 설계 범위).
- https://github.com/facebookresearch/Replica-Dataset 및 https://arxiv.org/abs/1906.05797
  고해상 HDR 재구성 텍스처·Habitat 호환. 이번 자연 질감이 실물을 재현한다는 근거 아님.
- https://aihabitat.org/datasets/hm3d/ : 실내 고해상 스캔, 시각적 현실감과 의미 주석.
- https://arxiv.org/abs/1703.06907 : texture/light/camera 도메인 랜덤화의 sim2real 연구.
  이번은 고정 카메라·조명·물리로 원인을 분리하므로 카메라 랜덤화는 적용하지 않는다.
