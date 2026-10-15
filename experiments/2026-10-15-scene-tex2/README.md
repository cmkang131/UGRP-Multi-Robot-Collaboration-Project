# scenetex2 — 벽·바닥 구분 자연 질감 v2

`walls_floor_textured_v2`, 기본 off. 사용자 요청에 따라 시각 재질만 바꾸는 새 장면 버전이다. 기존 `floor_light_v1`, `floor_light_textured_v1`, gcp1 결과와 합산하지 않는다. 아래 PNG 측정은 Mac 오프라인 계산이며 실제 자기 카메라/운반/회전 추정 성공을 뜻하지 않는다.

## 사용자 원문과 범위

2026-10-15: “벽에도 넣고, 벽 / 바닥 색 다르게 해. 쉽게 구분할 수 있도록. 그렇게 시뮬 바꾼 뒤에 그 상황에 효율적일 수 있는 알고리즘으로 다시 설계 ㄱ(첨부터 다시는 말고, 이거에 맞는 방식으로 하면 좋을듯)”, “일단, 시뮬 환경 먼저 세팅하고 / 그 환경에 맞춰서 다 병렬처리로 진행하면 좋을듯”. 이전 같은 날: “특징점 부족하면, 맵에 머 질감같은 거 넣어도 됨 … 현실은 그렇게 미끄럽지 않으니까”.

마커·반복 타일을 넣지 않고, 마찰·물리·충돌 형상·카메라/FOV·로봇·화물과 색 표식을 바꾸지 않는다. 사용자 지정 네 지도와 실제 HIGH/가림 자세를 별도 gcp2 정적 렌더 관문에서 비교한다. 정답은 setup/평가에만 쓴다. 제어기 재설계·관문·ACT 데이터 수집은 이 환경 검증 뒤 별도 작업이며, 기존 제어기를 이번 PNG 결과로 채택하지 않는다.

## 기존 거부 분포와 변경 근거

기존 PR #511은 균일 벽띠 판독 `max_band_std=3`을 살리려고 벽 밝기를 82–86으로 줄였다. 기존 저장 측정의 벽 150면 전부 ORB=0이다. [직전 거부 표](prior-rejection-table.json)는 해당 저장 JSON의 전체 SHA와 150→0 funnel을 남긴다. 이번 작업은 reloc15 원본 영상/실행을 재분석하지 않았으며, 사용자 제공 “실제 0.221°를 12.474°로 오수용”은 동기로만 인용한다. 새 질감이 그 오류를 고쳤다고 주장하지 않는다.

새 재질은 차가운 저채도 벽(H≈112)과 따뜻하고 밝은 바닥(H≈18)이다. S=16 설계는 포괄 페인트 하한 S=20을 피하고, 벽 V98–134/바닥 V146–180은 상대 검정의 최대 V=.38×255=96.9와 고정 흰 표식 V>180을 피한다. 모두 기존 검출식에서 유도한 설계 구간이며 실제 조명 허용 오차로 사용하지 않는다. 입자 크기·밀도는 저자가 만든 재질 설정이며 실물 표면을 측정한 값이 아니다.

## PNG 후보 비교

| 조건 | 벽 ORB 최소/중앙/최대 | 먼 유사 descriptor 중앙/최대 | 동일 32×32 패치 중앙/최대 | 바닥 640×480 ORB |
|---|---|---|---|---|
| 기존 v1 저장 기록 | 0/0/0 | descriptor 없음 | 기존 기록 참조 | 657–700 |
| A: 얼룩·마모 | 18/280/800 | 6.67%/25.10% | 1.17%/14.84% | 800×4 |
| B: 불규칙 미세 입자 추가 (비교) | 5/168/791 | 0%/2.30% | 0%/0% | 785,738,754,776 |
| **C: 면 매핑 수정·S8 (새 후보)** | **12/225.5/800** | **0%/1.69%** | **0%/0%** | **793,767,772,793** |

800은 기존 감사와 같은 ORB 검출 상한이다. “충분한 특징”의 새 수용 개수를 임의로 정하지 않았으며 실제 화면/가림 자세에 남는 벽 특징은 GCP에서 판정한다. 원거리 유사 descriptor는 기존 정의 그대로 거리≥64 px·Hamming≤24, 반복 패치는 byte 동일 32×32 비율이다. 이들은 소재 반복 진단이며 매칭 정답률·실제 회전 관측 가능성을 대신하지 않는다. B의 highpass NCC(32/64/128/256 px) 최대는 0.211이다.

비교 B의 manifest SHA256은 `7d65a69a2805af70bd2df4c7a0669ecf0e6210d670a853b8b05c75cdcfe444b5`이다. A 원본 PNG는 로컬 `outputs/scene-tex2/candidate-a-assets/`에 보존했으며 A manifest는 `89bd71ce48cdf983d36d869d2c6f3dae63f486cf712602be339ab2fc1f201d24`이다. [A 측정](png-audit/offline-audit.json), [B 측정](png-audit-final/offline-audit.json)과 각 image-metrics 파일에 모든 151장 SHA/측정이 있다. 생성기는 최종 B를 재현하며 배포한 PNG/manifest 바이트가 버전을 정의한다.

| 색 분리도 (B PNG 원본) | 값 |
|---|---|
| 벽 HSV | H110–116, S16–18, V98–134 |
| 바닥 HSV | H16–18, S16–17, V146–180 |
| 최소 V 간격 | 12 |
| Lab L 구간 | 벽 101–136 / 바닥 151–183 (OpenCV uint8) |
| 고정/상위집합 HSV·RGB·PIL 색 범위 | 108개, 바닥 9,437,184·벽 39,321,600 픽셀 모두 겹침 0 |

[전체 색 겹침 표](png-audit-final/color-ranges.md), [소스 전수 탐색](png-audit-final/color-source-inventory.md), [외부/직접비교/문맥 조건과 48개 소스 SHA](color_external_sources.json)를 함께 읽는다. 기존 81개 목록에 누락된 `white_markers(S<55,V>180)`·직접 비교·동적 dictionary 범위를 추가했다. PIL HSV는 PIL로 직접 계산했다. 주변 대비 흰 표식·채도 없는 화물 hue 후보·회색 로봇·바닥/VO 지지 마스크는 문맥/지지 조건으로 별도 남겼으며 픽셀 겹침 0을 주장하지 않는다. JPEG·조명 이후 최종 검출기와 원래 대상 지원 유지 여부는 별도 검증한다.

## 프로필 전용 벽 판독 후보

`harness/scene_tex2_perception.py`는 프로필을 명시해야만 쓸 수 있다. 재질의 명목 V 구간으로 벽/바닥을 나누고, 기존 벽 기하 후보의 std 한도는 PNG 휘도와 B−R의 범위에서 `sqrt(rangeL²+rangeC²)/2`로 계산한다. 범위 [a,b]에 든 변수는 `(X-a)(b-X)≥0`이므로 `Var(X)≤(b-a)²/4`이고, 가로 strip 평균도 같은 구간을 벗어나지 않는다. 단순히 std를 키우면 얼룩을 벽 경계로 받을 수 있으므로 기존 기하·후보 모호성 거부에 **벽→바닥 명목 구간 전이**를 함께 요구한다. 명목 구간 밖 조명·안티앨리어싱·가림은 기권한다. 렌더에 대한 확대 배율·새 각도/개수 수용값은 넣지 않았다.

기존 벽띠/`opencv_wall_observation`/`own_image_gates`를 전역 수정하지 않았고 기존 보정의 유효성을 v2로 승계하지 않는다. 이 후보는 아직 PNG 보정이며 실제 카메라에서 올바른 경계·오검출·기권을 비교한 뒤에만 연결한다. 소비자의 scene install/verify_model/nearclip 인자도 새 소스로 연결해야 한다.

## 재현과 원격 관문

Mac에서는 기존 환경으로 아래 PNG·XML·비물리 시험만 수행한다. MuJoCo 모델 생성/렌더/step·GUI·모델 호출은 하지 않는다.

```sh
python -m scripts.generate_scene_tex2 --output <새 자산 디렉터리>
python -m scripts.audit_scene_tex2 --output <새 측정 디렉터리>
python -m pytest -q tests/test_scene_tex2.py tests/test_natural_scene_texture.py tests/test_scene_tex2_probe.py
```

정적 관문 실행 소스는 먼저 커밋·push해 고정한다. `/Users/changmin/projects/ugrp/outputs/e2e18-admin/ops-alert.md`의 `gcp2setup: PASS`를 5분 간격, 작업 시작 후 최대 3시간까지 확인한다. PASS 뒤 `gcp2`만 사용한다(계정 `changmin5781@gmail.com`, 프로젝트 `ugrp-sim-b-1014`; 모든 gcloud에 두 인자를 명시). 첫 프로젝트의 23:02 KST 예산 정지와 후속 gcp2 이동 사용자 승인을 구분한다. 새 프로젝트의 budget-stop이 발동하면 즉시 중단하며 VM을 새로 만들지 않는다. 종료 시 다른 소유 작업이 없을 때만 VM을 정지하고 상태를 확인한다.

`scripts/probe_scene_tex2.py`는 Linux/PASS 증거/고정 소스를 확인하고 `mj_forward`만 쓰는 정적 평가다. 네 지도×벽을 보는 두 거리×주행/HIGH/가림×r1/r2×기존 두 프로필/v2를 비교한다. 카메라 위치/FOV·실제 fisheye 변환과 nearclip을 유지한다. 운반/가림 setup 좌표와 segmentation 정답은 평가 출력에만 있다. 청록/파랑 끝 색은 이 checkout에 교사 토글 소스가 없어 pinned 외부 색을 기존 band geom에 평가 setup으로 입히며, 실제 소비자 토글 통합을 대신하지 않는다. 프레임·컴파일 물리/카메라 배열·PNG/JPEG 색/ORB·분할·기존/후보 벽 판독과 funnel·전체 SHA를 보존한다. 정적 렌더는 물리 운반·ACT·자기 위치/회전 추정 성공이 아니다.

현재 진행/최종 판정·원격 실행 여부·소스 SHA·검증 수는 `summary.json`에서 관리한다. 진행 중·미회수 결과를 완료로 기록하지 않는다. 자료는 로컬 프로젝트에 보존한다.

## 참고 자료 (2026-10-15 확인)

- [OpenCV 공식 ORB 설명](https://docs.opencv.org/4.13.0/d1/d89/tutorial_py_orb.html): FAST/Harris와 방향 보정 BRIEF, 기본 WTA_K=2의 Hamming 비교를 확인했다. 새 학습 특징점을 도입하지 않고 기존 ORB로 재질을 비교했다.
- [MuJoCo 공식 XML reference, texture/material](https://mujoco.readthedocs.io/en/stable/XMLreference.html#asset-texture): 각 cube 면의 개별 PNG, `texuniform`과 2d `texrepeat` 매핑 의미를 확인했다. 이 문서는 실제 카메라 이미지의 검증을 대신하지 않는다.
- [OpenCV 공식 camera geometry](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html): 보정·왜곡 모델의 경계를 확인했다. 이번 작업은 기존 실제 카메라/FOV와 fisheye 변환을 재사용하며 제어기 yaw 수용 상수를 새로 정하지 않는다.
- 저장소 기존 근거: [v1 PR #511 검토·검출기 감사](../2026-10-15-scene-floor-texture/README.md), 고정 `experiments/2026-09-26-markerless-probe/markerless_probe.py`의 벽띠 알고리즘, `harness/e2e_rgb_gate.py`와 색 소스 목록. 외부 원본 영상은 이번 Mac 작업에서 재생하지 않았다.

## GCP B 결과와 C 수정 (2026-10-16 KST)

`3f5feb73` 첫 시도는 H1/H2 allow-list 오류로 프레임0·MODEL_HOST_ERROR였으며, 원본과 [실패 기록](host-error-static-a.json)을 보존했다. 기존 `zone_heldout_scene.install` 준비 어댑터를 쓰도록 고친 `7c45215e`는 **144/144 정적 조건 완료**, 컴파일 물리·카메라 동일성 12/12, 원본2,921파일과 압축146기록의 복원 SHA를 확인했다. 분포·funnel은 [B 관문표](camera-b-rejection-table.json), [원격 요약](gcp-static-b-summary.json), [실행 funnel](gcp-static-b-funnel.json)에 있다.

GCP에서 ffmpeg으로 만든 24장 비교 몽타주를 파일로 직접 봤다. 네 지도 r1 주행에서 v2 벽 무늬가 중심으로 모이는 방사형 늘어짐을 보였고, 가림 HIGH에서는 빔과 바닥만 보이며 벽이 없었다. 실제 48프레임 중 벽이 보인20, 벽 내부 descriptor support가 있는3이다. 가림16/16에서 빔/상대는 보였지만 벽은0·벽 ORB0이었다. 이 결과는 자세/가림의 관측 한계이며 질감만으로 회전 오류를 해결했다고 할 수 없다.

C는 이 검토 뒤 수정한 **새 해시 후보**다. `texuniform=false`로 개별 면의 unit-box PNG를 매핑하고 재질 채도는 S16→8로 낮췄다. [MuJoCo 3.12.0 공식 렌더 코드](https://github.com/google-deepmind/mujoco/blob/3.12.0/src/render/classic/render_gl3.c#L225)는 true일 때 cube TexGen에 geom size를 곱한다. 얇은 벽에서는 실제 면과 다른 cube 면이 선택돼 방사형 늘어짐이 생긴다. 기존 v1은 재생용으로 그대로 두고 v2만 고쳤다. [C 설계·PNG 결과](candidate-c.json)의 manifest는 `ea58773c500dd9bc5dbf3ede4edf5419535c306d3f9c3c11de935a5089af9858`, 프로필은 `f6d825b6a52b2c86a80b6a02ed697b1337888224d49aad47325691e8d44d710d`다. [C 전체 색 표](png-audit-c/color-ranges.md)는 108범위 겹침0이며 기존 B/C를 합산하지 않는다.

C의 새 정적 비교는 기존144조건에 실제 상자4색·빔 끝2색·구역A/B/C를 보는120조건을 더한264프레임이다. 추가 자세는 FOLDED와 원래 카메라/물리/색을 쓰고 객체 freejoint의 setup 위치만 평가용으로 배치한다. 미노출은 미검증으로 기록한다. 프레임의 full detector dictionary 차이는 추정/debug 수치까지 포함하므로 의미적 색/물체 검출 실패와 구분한다. 아직 실제 C 관문은 실행 전이며 최종 결과는 summary.json에 후속 기록한다.
