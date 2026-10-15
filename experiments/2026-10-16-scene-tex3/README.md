# scenetex3 — 화질 우선 조사

진행 중. 기본 off 후보이며 v1/v2·호스트·렌더 조건을 합산하지 않는다.
Mac 렌더/물리/GUI0, gcp2 정적 mj_forward만 허용. 최대 3라운드.

## 수정 전 측정

[원본 재집계](before-change.json): 같은 gcp2 16 주행 시점의 PNG 바닥 ORB
v1 합271·중앙16.5, v2 합249·중앙13.5. **바닥 특징 회귀**다.
벽 ORB 합195→487. 이 값은 경계에 걸친 descriptor도 포함하며,
내부support와 연속 정합을 따로 잰다. 원본은 1e9594a9 static-e.

reloc15의 43/45→6/45는 gcp1 기록이며 여기서 재현·합산하지 않는다.
현재 map-selfmap 코드의 selfmap4_geometry.observe는 wall-floor 경계 컬럼을
정적 지도 정합 입력으로 쓰고 PlaneFlow는 LK+homography를 쓴다.
별도 natural-floor 경로의 reloc11_features는 FAST7(기본20)을 쓴다.
따라서 ORB20 개수 하나로 과거 주행 개선의 원인을 설명할 수 없다.

## 유한 실행 계획

R1: 기존 floor_light_v1/v1/v2 × native/2x SSAA/MSAA8/cubic/nearest-mip/no-mip.
같은 88 시점, 단계별 ORB20/7·내부support·라플라시안 분산·PNG/JPEG90/PIL82
검출·분할 분포·1픽셀 각도 증가 정적 연속쌍 정합·렌더 시간을 기록한다.
마지막 연속쌍은 mj_forward fixture이며 실제 주행/VO 성공이 아니다.
2x는 사용자 예시, MSAA8은 비교 요청이며 새로운 수용 기준이 아니다.
드라이버가 clamp한 실제 samples도 기록한다. 물리·카메라 배열 해시는 동일해야 한다.
R2/R3: R1 거부 분포 후 필요한 최소 재질 수정 및 전체 비교. 실패도 보존한다.

상자 색 검출기는 수정하지 않는다. 기존 PNG/JPEG 대비 88/88 이상이 필수.
분할 IoU는 모든 프레임의 분포를 기록하며 임의 합격 하한을 만들지 않는다.
v1 대비 특징·정합 감소가 남으면 NOT_READY. 벽 미노출은 장면 한계다.

## 실물 자료 조회

docs/masterpi_physics_calibration.md, 2026-10-06-robot-camera-review 기록,
기본 checkout calibration/experiments/outputs와 보관 포인터를 조회했다.
real_traces ZIP과 Project-Archives의 기존 경로는 현재 없고, recovered 디렉터리에는
이벤트/요약만 남았다. 원본 이미지 발견 시 동일 지표로 gcp2에서 분석한다.
과거 ORB/선명도 값은 발견하지 못했다. 사용자의 “실물 바닥 특징이 잘 인식된다”는
관찰은 동기이며 정량 비교의 대체 측정값이 아니다.

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
