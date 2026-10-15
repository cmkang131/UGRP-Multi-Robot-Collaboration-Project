# scenetex4 — 벽·바닥 색 대비 우선

**NOT_READY, 3라운드 종료. 채택 후보 없음.** `luma/native`는 기존 selfmap 경계 컬럼·오차와 LK를 보존했지만 바닥 특징·연속 매칭, 렌더/JPEG 색 범위 관문을 모두 통과하지 못했다. 기본 장면·제어기·ACT에 연결하지 않는다. [요약](summary.json), [누적 funnel와 독립 거부 원인](rejection-table.md), [전체 판정 색인](rejection-table.json).

## 요청·시작 조건·검증 단위

2026-10-16 사용자: “이거는 방식을 바꿔야 할듯”, “벽과 바닥 색을 좀 더 구분되게 하던가”. 10/15의 “벽에도 넣고, 벽 / 바닥 색 다르게 해 … 그 상황에 효율적일 수 있는 알고리즘으로 다시 설계 … 첨부터 다시는 말고”를 따른다. 벽 ORB 개수를 목표로 두지 않고, 실제 selfmap 벽 경계와 바닥 입력을 비교했다.

첫 확인 때 scenetex3 판정 줄이 없고 scenetex3b Codex가 실행 중이었다. 읽기만 하며 기다린 뒤, 5분 간격 첫 재확인인 2026-10-16 02:05:54 KST에 NOT_READY 줄과 프로세스 종료를 모두 확인했다. 그 전 수정·커밋·gcp2 실행은 없었다. 먼저 scenetex3 README·summary·거부표·몽타주를 읽었다.

네 지도, **동일한 88 자세 × PNG/OpenCV JPEG90/실제 경로 PIL82 = 조건당264 RGB 프레임**이다. R2는3벽 후보×2화질=528자세, R3는2후보×2화질=352자세를 완료했다. 과거 gcp2 v1/v3 저장 영상은 자세 qpos·이미지·전체 manifest 해시를 확인하여 같은 자세 기준으로 재사용했다. 서로 다른 재질·화질·소스·호스트 결과는 합산하지 않는다. reloc15의 과거43/45→6/45를 재실행하거나 이번 gcp2 결과의 분모로 쓰지 않았다.

물리 step·SIM 시간·모델 호출은0이다. `atan(1/fx)`(약0.0925°)의 평가용 정적 yaw 쌍을 비교했으며 주행·위치 오차·ACT·운반·실물 성공 결과가 아니다. HIGH/unknown-load의 기존 보정 가드를 유지해 경계/LK는56/88자세가 적격이고, 미적격32는 따로 남겼다. IoU는264 RGB 전체 분포를 기록한다.

## 설계와 라운드

모든 후보는 v1 바닥 PNG와 바닥 XML 바인딩을 그대로 재사용한다. 마찰·충돌·형상·질량·카메라 위치/FOV/K/D·로봇·화물·색 표식을 바꾸지 않는다. 원래 floor 재질/텍스처를 다시 만들거나 색칠하지 않았다. 기본 off 프로필을 재생 가능한 탐색 후보로만 보존한다.

- R1: 초기 MuJoCo/NumPy material ID 인덱싱 오류로6조건 모두 렌더0 HOST_ERROR. 수정 뒤 첫 시각 비교판에서 uniform geom RGBA가 material 색을 덮어 백색 벽이 나온 것을 확인했다. 정확한 자기 PID6개에 SIGINT를 보냈고287개 부분 자세를 보존·제외했다. 이 불완전 비교를1라운드로 세어 총3라운드 상한을 지켰다.
- R2(`10f2a7b7e35f3a0cf807a1b23c28c158ca8adca9`): dark RGB78/81/83, light131/136/140, light+8cm skirting. 모두 무늬 진폭0. RGB/S16·걸레받이8cm는 저작 재질 설계값이며 실측 규격·새 수용 상수가 아니다. PNG/JPEG 후 기존 색 범위의 실제 히트를 재검사했다.
- R3(`e7b90b7f934abf77a6b9b8e03279018249ff1679`): `flat`은 RGB83/84/87 균일 벽, `luma`는 v1의82–86 벽 무늬·기존 매핑을 그대로 두고 RGB에(-1,0,+3)를 더했다. OpenCV의Y=.299R+.587G+.114B에서 명목 변화는0.043레벨이다. 150장 저작 PNG의 회색조가 v1과 byte 동일하고 S<20임을 확인했지만, 이를 렌더/JPEG 후 동일성으로 확대하지 않았다. 더 큰 새 벽 무늬는 기존 균일 면 조건과 충돌하므로 이 라운드에서는 넣지 않았다.

화질은 native와 scenetex3의 `no_mip_v1`을 별도 비교했다. 이전 v1에서 주행 바닥 ORB 중앙16.5→27로 늘었던 후보만 선택했다. 이번에도 총특징/매칭 증가가 관찰됐으나 모든 자세의 회귀0은 아니어서 채택하지 않았다.

## 관문 결과

기존 상자 종류 검출은 **모든 새10조건에서 PNG/JPEG90/PIL82 각각88/88** v1과 일치했다. legacy beam 의미 출력도 같았다. 이것만으로 전체 색 호환을 통과시켰다고 보지 않는다. 원래 대상의 의도된 범위만 색 지원으로 세고, 관계없는 색 마스크 감소는 손실로 세지 않도록 최종 집계를 수정했다. 초기 집계는 `round2/`, 최종은 `round2-final/`이며 덮어쓰지 않았다.

아래는 PNG 지표다. 컬럼은 적격56자세의 중앙/p10, 경계 오차는 반환별 중앙/p95/max(px), ORB는 주행16 중앙, match는88쌍 합이다. 바닥 회귀는 **PNG/JPEG90/PIL82 중 어느 하나라도** ORB20/7·내부support 또는 match20/7가 v1보다 낮은 자세 수다.

| 조건 | 경계 컬럼 중앙/p10 | 경계 오차 중앙/p95/max | 바닥 ORB | 바닥 match | 특징/매칭 회귀 자세 |
|---|---:|---:|---:|---:|---:|
| v1/native | 88/73.5 | .5/1.5/28.5 | 16.5 | 942 | 0/0 |
| v3/native | 87/63 | 1.5/83.5/352.5 | 10 | 781 | 53/55 |
| v3/벽 no-mip | 63/54.5 | 3.5/83.5/352.5 | 11 | 793 | 54/59 |
| R2 dark/native | 88/75.5 | .5/81.5/351.5 | 14.5 | 873 | 52/46 |
| R2 light/native | 88/74 | 2.5/71.5/244.5 | 11.5 | 767 | 59/59 |
| R2 skirt/native | 88/62.5 | 18.5/72.5/230.5 | 13 | 896 | 42/42 |
| R3 flat/native | 88/77.5 | .5/83.5/352.5 | 13.5 | 889 | 52/45 |
| **R3 luma/native** | **88/73.5** | **.5/1.5/28.5** | **16.5** | **935** | **16/16** |
| R3 luma/no-mip | 88/73.5 | .5/1.5/28.5 | 27 | 1474 | 23/12 |

`luma/native`의 JPEG90 경계는 중앙/p10=88/72.5(v1동일), 오차 중앙/p95/max=.5/1.5/42.5(v1=.5/1.5/47.5)이며 전체0–100백분위가 v1 이하라 PNG/JPEG 모두 경계 관문을 통과했다. 이 후보의 LK tracks/inliers는 회귀0/56이다. 그러나 바닥 특징·매칭 회귀는 각각16/88이며 인코딩별 특징 회귀 PNG8/JPEG13/PIL9, 매칭 PNG8/JPEG13/PIL2다. 총량·중앙값이 비슷해도 이 회귀를 무시하지 않았다. luma/no-mip PNG는 표의 세 오차 요약값은 같아도 중간 백분위가 커져 전체 분포 관문을 통과하지 못했다.

색 범위 히트가 v1보다 늘어난 자세는 luma/native PNG24/JPEG60/PIL60이다(전체 OR60/88). 원래 양성 색 지원 손실은3자세: H2 paint_A/r1 JPEG20,727→20,725px, paint_B/r2 JPEG33→31·PIL32→31, paint_C/r1 PIL43,635→43,634다. 전체 범위별·대상별 기록과 반례는 `round3/*-cases.json.zst`에 있다. 미노출 물체는 검증된 양성으로 세지 않는다. 원래 상자·빔·구역·콘 검출기의 범위를 넓히지 않았다.

IoU는 새 평가 전용 색 규칙(S<20, 기존 검정/흰 제외, B>R 벽/중립 바닥)을 모든 조건에 동일 적용했다. 제어기에는 연결하지 않았다. v1 균일 무채색 벽의 기존 검출 성능과 혼동하지 않는다. `luma/native`의 분포:

| 인코딩 | 벽 IoU p10/중앙 | 바닥 IoU p10/중앙 |
|---|---:|---:|
| PNG | 0/.9204 | .9514/.9864 |
| JPEG90 | 0/.8057 | .2996/.8688 |
| PIL82 | 0/.7612 | .2490/.8529 |

각 조건의264개 IoU 원소, null/0, min/p05/p10/p25/중앙/p75/p95/max를 모두 보존했다. 미노출·예측도0인 union0은 null로 분리하고, 미노출인데 오검출된 경우의0은 남긴다. 새 IoU 합격 수치를 만들지 않았다. 벽 ORB는 기록용이며 가림16/16의 벽 미노출을 질감 개선으로 해결했다고 보지 않는다.

## 실제 신호·직접 검토

[selfmap 출처](selfmap-provenance.json): 열린 #506의 소스 `644289a755ee60df99e916224931c2dec80298eb`와 active_wall_vision/e2e_rgb_vo/active_camera/height_free_wall 파일이 byte 동일함을 확인했다. selfmap4_geometry의96컬럼·strip2, floor_patch_max_m=.81/run_step_window3/top_edge4와 PlaneFlow의 ground_pair homography_v1을 그대로 사용했다. 새 오차 허용값·분산 상한은 넣지 않았다.

[R2 몽타주](round2-final/comparison.jpg), [R3 같은 자세 몽타주](round3/comparison.jpg), [실제 경계/반환 비교](boundary-review.jpg), [직접 본 범위](review-notes.md)를 남겼다. H1에서 skirting이 실제 바닥 접점보다 위쪽 띠를 고르고, 밝은 균일 벽에서는 로봇/하단의 다른 반환이 생기는 것을 직접 봤다. R3의 H1/H2 주행·상자·가림6자세도 v1/v3/후보와 비교했다. 정적 t=0이므로 동적 실패/성공 영상2Hz·마지막10SIM초10Hz나 실제 진동을 검토했다고 주장하지 않는다. Mac에서 화면 앱·렌더·GUI는0이다.

## 보존·재현·운영

Mac XML/PNG/순수 표적 시험 **38 passed in10.13s**. gcp2 후보×지도 모델의 물리·카메라 fingerprint는40/40 v1과 같았다. [원본 보존](preservation/summary.json): 새 완료10조건880자세, 초기0프레임 HOST_ERROR6조건과 중단287자세를 각각 포함했고 기존 원본 manifest 불일치0이다. 전체 파일 해시는 `/home/ugrp/ugrp-sim/runs/scenetex4-preservation/`에 있다. raw는 영속 디스크에 보존하고 삭제/원본 덮어쓰기/gcp1 접근을 하지 않았다.

Mac에는 요약·가벼운 case/signal 원장·해시·작은 비교판만 회수했다. [회수 검증](retrieval-verification.json)의142개 묶음 참조와 추가6개 검토/보존 파일 해시가 맞았다. 큰 JSON은 zstd 복원 SHA 확인 뒤 압축했고, 기존 중간 집계도 보존했다. 연구 결과·원본을 Drive에 올리지 않았다.

gcp2 n4-highcpu-64, 실행 전 디스크343GiB·가용메모리122GiB 확인. R2는6조건×512MiB+타 작업8GiB 예약, R3는4조건×512MiB였다. Mac fetch-lite32MiB 예산과 여유38GiB 이상을 확인했다. 벽시계 기반 계획 탐색은 없고 정해진 자세·검사 개수만 사용했다. SIM0이므로 wall/SIM은 정의하지 않는다. 실제 클라우드 청구액은 회수하지 않았다.

모든 소스 사본은 공통 git-shared.git을 직접 reference했고 사슬 alternates·gc/prune을 쓰지 않았다. [종료 확인](vm-lifecycle.json): 자기 실행 프로세스0, 자기 임대 제거, 다른 `simalt5.json` 임대가 남아 VM을 정지하지 않았다. 기존 비용/유휴 장치를 바꾸지 않았다.

재현은 정확한 소스 사본/기존 환경에서 새 출력 경로를 사용한다. 전체 argv와 raw 위치는 각 실행 meta·라운드 요청·거부표에 있다.

```sh
MUJOCO_GL=osmesa python -m scripts.probe_scene_tex4 --execute --source-sha e7b90b7f934abf77a6b9b8e03279018249ff1679 --materials walls_floor_contrast_v4_luma --qualities native --output <new-raw>
python -m scripts.score_scene_tex4 --inputs /home/ugrp/ugrp-sim/runs/scenetex3-r3-complete <new-raw> --output <new-analysis>
```

`--cached-analysis`는 원본 RGB/qpos SHA와 측정 함수 AST가 같은 저장 입력만 재사용한다. 최종 분석 소스 SHA는 각 summary와 함께 실제 analysis-source.py를 보존했다. 경계 오차는 정적 분할 ID로 평가만 하고 제어 입력에 정답을 넣지 않는다.

## 참고 자료 (2026-10-16 원문 확인)

- [OpenCV HSV inRange](https://docs.opencv.org/4.10.0/da/d97/tutorial_threshold_inRange.html): 기존 의미 색 범위를 고정하고 평가 분할과 구분.
- [OpenCV 특징점](https://docs.opencv.org/4.12.0/dd/d1a/group__imgproc__feature.html), [LK](https://docs.opencv.org/4.7.0/dc/d6b/group__video__track.html): 실제 Shi–Tomasi/LK 입력을 그대로 측정.
- [OpenCV RGB→Gray](https://docs.opencv.org/3.4.17/de/d25/imgproc_color_conversions.html): 명목 Y계수와 색/휘도 분리의 근거. 색 오프셋을 렌더 후 동등성 보장으로 취급하지 않음.
- [Khronos cube-map 축](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_texture_cube_map.txt): 걸레받이를 기존 벽 cube면에만 표현.
- 기존 height_free_wall.py의 uniform band + horizon + edge 방법을 먼저 확인했다. 벽 특징 수를 늘리는 것이 이 입력을 보존한다는 가정을 버리고 균일·저진폭 후보를 비교했다.
