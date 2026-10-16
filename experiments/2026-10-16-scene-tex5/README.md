# scenetex5 — 장면 색과 경계 검출 단계를 함께 변경

**NOT_READY. 최대 3라운드를 마쳤으며 채택 장면은 없다. 장면·경계 토글은 기본 off다.** v1 바닥 질감과 no_mip_v1을 유지하고 벽색·밝기를 바꿨다. 기존 96컬럼/strip2 구조에서 경계 검출 단계만 색 분할·전이·직선 합의로 교체했다. 경계 오차와 바닥 특징·매칭 분포는 개선했지만 경계 컬럼 수, LK 하위 분포와 일부 후보의 색 오검출이 남았다.

[요약](summary.json) · [누적 관문·거부표](rejection-table.md) · [사유·원본·재현 경로](rejection-table.json) · [전체 분포/벽 색 범위 침범](rounds.json.zst) · [R3 같은 자세 몽타주](round3/comparison.jpg) · [경계 그림](round3/boundary-review.jpg)

## 요청과 구현

사용자(10/15): “벽에도 넣고, 벽 / 바닥 색 다르게 해 … 그렇게 시뮬 바꾼 뒤에 그 상황에 효율적일 수 있는 알고리즘으로 다시 설계 … 첨부터 다시는 말고”. 10/16: “이거는 방식을 바꿔야 할듯”, “벽과 바닥 색을 좀 더 구분되게 하던가”.

scenetex4 README·거부표·R2/R3 기록·boundary-review.jpg·review-notes, scenetex3 기록과 관련 검출 소스를 읽었다. [수정 전 원인 표](before-change.json)를 만들고 균일 무채색 벽에 맞춘 경계 알고리즘을 보존하던 관문을 새 장면에 강제하지 않았다.

- sim/scene_contrast_v5.py: v1 바닥 PNG·매핑을 유지한다. 초기 보라 후보3개, 어두운 남보라3개, 중간 채도 남보라2개를 별도 이름으로 보존한다. 무늬는 없거나 원래 v1 벽의82–85레벨 공간 변화를 새 RGB에 공통으로 더한 낮은 진폭이다. 텍스처 manifest·파일 SHA를 검사한다. 기존 색 검출 범위를 변경하거나 지우지 않았다.
- harness/scene_colour_boundary.py: Lab 분포로 벽/바닥을 분할하고 벽 HSV 분포로 기존 구역색과 구분한다. 각 컬럼 아래→위 첫 전이를 찾고 기존3px 지지 창 주변의 최대 밝기 변화 행을 반환한다. 비주황 컬럼에서만2점 직선 모델을 만들고 관측된 전이의 합의를 검사한다. 기존 이웃 거리/방향 연결도 유지한다. 가린 컬럼을 채우거나 선을 외삽해 반환하지 않는다.
- harness/wall_contact_detector.py의 scene_colour_transition_v1과 공통 active_wall_vision.modules()의 선택 facade를 제공한다. frozen height_free_wall 모듈/전역은 수정하지 않는다. 기본 off는 기존 모듈 객체 그대로다. 자기 RGB·자기 명령 기반 카메라와 고정 보정 파일만 사용한다.
- selfmap4_geometry는 PR #506 소스644289a755ee60df99e916224931c2dec80298eb에서 modules()->hfw.detect를 호출함을 확인했다. 96컬럼·strip2·ColumnModel·scan keys/shape·원래 link_segments·PlaneFlow·하류 인터페이스를 유지한다. 기존 API가 새 facade를 받는 연결은 저장 RGB8자세×3인코딩 **24/24**에서 직접 경계 호출과 NaN 포함 배열이 일치했다. 실제 selfmap 폐루프 위치 추정이나 임무 성공 검증은 아니다.

런타임 선택은 프로세스 시작 전에 UGRP_SCENE_COLOUR_BOUNDARY=scene_colour_transition_v1, UGRP_SCENE_RENDER_PROFILE=정확한v5이름, UGRP_SCENE_COLOUR_CALIBRATION=해당R3보정파일, UGRP_SCENE_COLOUR_CALIBRATION_SHA256=파일SHA를 함께 지정한다. 장면/화질도 해당 실행기의 명시적 v5/no_mip_v1로 맞춰야 한다. 이 변수는 장면 자체를 바꾸지 않는다. v1의 정상 기본 경로는 기존 검출기이며, 새 선택기에 v1 또는 다른 보정 파일을 지정하면 거부한다. **현재 후보는 진단 재현용이며 기본 전환하지 않는다.**

## 상수 근거와 관문

색 임계는 저장된 실제 벽·바닥 픽셀 분포에서만 정했다. 기존 strip2에서 나온5×5 내부 마스크로 표면 경계 혼합을 빼고 PNG/JPEG90/PIL82 픽셀을 모았다. Lab 분류 범위는 p00/p100, 벽 HSV 범위는 p01/p99, 색 전이 축은 벽·바닥 중앙의 a/b 차이, 분할점은 바닥 투영 p99와 벽 투영 p01 사이의 중점이다. 같은88자세로 보정하고 채점했으므로 **탐색 결과이며 독립 holdout이 아니다**. 평가 분할/정답 좌표는 런타임 검출 인자가 아니다.

직선 잔차1.5px는 이 gcp2 v1/native 원본의 PNG/JPEG90/PIL82 경계 오차 p95이다. 색 임계나 수용 오차를 자세마다 맞추지 않았다. strip2·band10·window3·최소4컬럼·기존 거리/방향 연속성은 기존 값이다. 2점 모델은 가능한 쌍을 유한하게 검사한다(최대24×96×95/2쌍). 벽시계 기반 탐색 종료나 부하에 따라 달라지는 계획 예산은 없다.

관문은 사용자가 지정한 **같은88자세 분포**다. 자세별 바닥 회귀는 기록만 하고 “0개”를 강제하지 않는다.

1. 동일 자세/물리/카메라.
2. 기존 검출 종류·개수 PNG/JPEG90/PIL82 각88/88, 새 오검출0. 상자·기존 어두운 빔 띠 외에도 원래 구역 A/B/C·주황 장애물·자홍 동료의 component, floor_goal B patch, B quad/흰 섬 관문 출력을 실제 함수로 비교했다. 끝 띠·보존된 과거 규칙 등 전체 HSV/RGB 범위의 벽 침범 자세 수는 별도로 기록한다. 픽셀 범위 검사와 완전한 객체 검출을 혼동하지 않는다.
3. 경계 컬럼 중앙/p10 ≥ v1/native, 오차 중앙/p95 ≤ v1/native, 인코딩 각각.
4. ORB20/7·내부support·연속 매칭 중앙/p10 및 LK tracks/inliers 중앙/p10 ≥ v1/native. v1/no-mip 비교군도 별도로 기록했다.
5. 벽/바닥 IoU 분포 기록. 가림에서 벽 미노출은 장면 한계다.

경계/LK의 기존 카메라 자격은56자세이며 HIGH/unknown-load32자세는 그대로 미적격이다. 색 component는88자세를 비교하지만 floor_goal/B의 카메라 미적격32건은 unknown 상태 비교이며 양성 검출 성공이 아니다. 가림 전용16자세는 벽 노출0이다.

## 결과와 남은 결함

R1 보라색은 기존 구역 C/자홍 규칙과 충돌했다. 단순 Lab 분할은 파랑 B/보라 C의 앞선을 벽 접점으로 반환했다. [직접 본 실패2/정상1 포함 비교](round1/failure-review.jpg). R2는 hue 지지를 추가해 이 오류를 줄였지만 주황 컬럼 전체 제외와 JPEG 지지 부족으로 컬럼 수가 크게 줄었다. [R2 비교](round2/boundary-review.jpg).

R3의 대표 비교 조건 indigo110_s80/no_mip_v1은 **채택 후보가 아니다**.

| 인코딩 | 기존 색 출력 | 컬럼 중앙/p10 v1 → 새 | 오차 중앙/p95 px v1 → 새 | 벽/바닥 IoU 중앙 |
|---|---:|---|---|---|
| PNG | 88/88 | 88/73.5 → 78/59.5 | .5/1.5 → .5/1.5 | .98945 / .98791 |
| JPEG90 | 88/88 | 88/72.5 → 78/60 | .5/1.5 → .5/1.5 | .92508 / .96345 |
| PIL82 | 88/88 | 87/72.5 → 76/52 | .5/1.5 → .5/.5 | .90020 / .95773 |

PNG 전체88자세 바닥 ORB20 중앙/p10은 **14.5/0 →23/1**, 연속 floor20 매칭 중앙은 **10→17**이다. drive16자세 ORB 중앙은 **16.5→27**이다. 모든 인코딩의 바닥 특징·매칭 분포 관문은 통과했다. 같은 자세에서 낮아진 사례가 없다는 뜻은 아니다. 벽/바닥 밝기 차이 ΔL 중앙은65(8-bit OpenCV Lab)였다.

남은 결함:

- **주황 구역 A를 로봇 가림으로 오인해 직선 시드가 사라진다.** H1/view0/paint_A/r1은 실제 접점96컬럼, 벽·바닥 색 지지 모두96인데 기존 주황 컬럼 마스크가96컬럼 전부에 걸려 비주황 시드0, 최종 반환0이다. [확인 수치](round3/coverage-diagnosis.json), [세 지도 반례와 정상 drive](round3/coverage-review.jpg). 중립 바닥 지지가 없다는 초기 가설은 이 검사로 반증했고 파일에 명시했다. 주황 마스크는 로봇 인식기가 아니라는 원래 제한을 새 직선 시드에도 가져온 결함이다.
- s80 PNG의 거부 컬럼은 색 전이 지지 부족741, 비가림 직선 합의 부족301, 이웃 연결55다(56×96 검사). 반환4279, 평가용 실제 접점 컬럼의 중앙/p10은96/82다. 현재 알고리즘의 낮은 coverage를 장면의 이론적 한계로 돌리지 않는다.
- LK 중앙은 늘지만 하위 분포는 부족하다. s80 PNG tracks 중앙/p10은80/4→91/2, inliers는79.5/4→91/0이다. 고채도 벽은 원래 LK의 S>100 제외 규칙에도 걸린다. [원본 진단](round2/LK-diagnosis.json)의 corridor/paint_A/r1에서 v1 초기 Shi–Tomasi59점은 평가상 **전부 벽·바닥0**이었고 고채도 벽에서는 마스크/점0이었다. LK 수를 실제 바닥 추적·이동 정확도로 보고하지 않는다. PlaneFlow 상수/마스크는 바꾸지 않았다.
- s65는 PNG LK 하위 분포를 회복했지만 JPEG inliers p10이0이며, **PIL82에서 B 패치 오검출2개**가 생긴다. corridor/view0/paint_A/r1의 두 component는 각각67px가 전부 평가 벽이고 바닥0이다. PNG와 v1/PIL은0이다. [RGB와 검출 윤곽](round3/pil-counterexample.jpg), [픽셀 근거](round3/pil-counterexample.json). s65의 기존 색 출력 일치는88/88/87이다.

3라운드 이후 이 결함을 고친 새 후보나 네 번째 알고리즘 평가를 실행하지 않았다. 기본 off 상태로 원인과 반례를 인계한다.

## 실행·보존·검증

- gcp2 ugrp-sim-b-1014, 계정 changmin5781@gmail.com, n4-highcpu-64. 완결 렌더는 R1 5조건440자세, R2 3조건264자세, R3 새2조건176자세: **총880자세/2640 인코딩 RGB**다. 각 조건88자세이며 장면/알고리즘/호스트 결과를 합산한 성공률은 없다. R3 고채도 비교는 R2 원본 해시를 재사용해 검출 단계 변화만 평가했다.
- 렌더 소스: R1 비교군3b36eb9d, R1 후보 허용 목록 복구32e36dfe, R2 3724052a, R3 a68106fd86c314d7c1d10cd321475b0c86c93310. 경계 본체는 R3 이후 AST 동일이다. 공통 facade/연결 확인 소스63f14fda073c051b454a71877770e2a6654cf5af.
- 물리·마찰·카메라 위치/FOV/K/D 불변. 모델 fingerprint **40/40 일치**, 원본 manifest 불일치0. mj_forward 정적 SIM0과 atan(1/fx)만큼 yaw를 바꾼 평가 영상 쌍이다. 물리 step·LLM 호출·Mac 렌더·GUI 모두0. 실제 주행·위치 추정·ACT·운반·실물 성공 근거가 아니다.
- 초기 nearclip 허용 목록 누락은 후보3조건 모두0프레임 HOST_ERROR로 보존했다. HIGH 카메라 자격 처리가 빠진 초기 확장 색 감사도 미완료로 구분했고 unknown을 보존해 다시 집계했다. 집계기의 import/압축 manifest 경로 오류는 결과 렌더와 별개이며 최종 scenetex5-final-v2만 완결 기록이다. cap_end0. [보존](preservation.json).
- 원본은 /home/ugrp/ugrp-sim/runs/scenetex5-r*, 최종 집계는 scenetex5-final-v2다. dev 원본을 삭제하지 않았다. 대표 정적 비교/실패 자료700파일은 별도 scenetex5-representative-v1에 복사·해시 검증하고 milestone로 영구 보존했다. 이는 성공 표기가 아니다. [대표 보존](representative-preservation.json). 영속 디스크 보존이며 별도 호스트 백업 완료를 뜻하지 않는다.
- 모든 소스 사본은 공통 /home/ugrp/ugrp-sim/git-shared.git을 직접 --reference한 clone이다. 전체 이력 복사, 사슬 alternates, gc/prune, gcp1 접근을 하지 않았다. 제출 전 gcp2 가용339GiB/메모리123GiB·Mac40GiB를 확인했고 raw6GiB+분석/임시2GiB, Mac fetch-lite32MiB를 예약했다. 최대 자기 동시 실행5, 호스트 상한40이다.
- Mac은 요약·가벼운 원장·해시·비교 이미지 파일만 받았다. **151개 참조 해시·45개 zstd 원문 복원 해시 검증**, 이미지9개/2,077,082bytes로 미디어 한도를 통과했다. [회수 검증](retrieval-verification.json). 결과·원본·참고 기록은 로컬/GCP에 보존했다.
- 시작 전 정지는 유휴 종료라는 초기 설명과 달리, 임대 생성 전 다른 Claude Code의 gcloud stop 호출이었다. [프로젝트/VM 한정 감사 로그](startup-stop-audit.json). 규칙14로 재시작했고 그 시점에는 실험 프레임이 없어 원본 손실0이다. 종료 시에는 다른 warp1 임대가 남아 자기 임대만 지우고 공유 VM을 정지하지 않았다. [종료 확인](vm-lifecycle.json).
- Mac 표적 시험 **56 passed in4.23s**: test_scene_tex5.py, test_wall_contact_types.py, test_wall_floor_lorigo.py. 새 시험은 CI shard 목록에도 등록했다. [직접 본 범위](review-notes.md). 종료 임대/프로세스 확인은 vm-lifecycle.json에 남긴다.

재현은 기록한 소스 clone·기존 GCP 환경에서 새 output을 사용한다. 라운드별 run-round*.py, 원본 meta.json과 거부표에 전체 argv가 있다. 핵심 경로는 scripts.probe_scene_tex5 → scripts.score_scene_tex5 → scripts.audit_scene_tex5_colours다. 모두 gcp2에서만 실행한다.

## 참고 자료 (2026-10-16 원문 확인)

- [OpenCV inRange/HSV](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html): 색 공간 변환과 범위 분할.
- [OpenCV cvtColor/Lab](https://docs.opencv.org/4.13.0/d8/d01/group__imgproc__color__conversions.html): Lab 변환. 조명에 대한 완전한 불변성을 보장하지 않는다.
- [OpenCV fitLine](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html): L2/강건 M 추정 직선의 표준 접근을 검토했다. 실제 구현은 아래 모델/합의 집합의 유한 전수2점 방식이며 fitLine을 호출했다고 주장하지 않는다.
- [Fischler & Bolles 1981 RANSAC 원문](https://www.sri.com/wp-content/uploads/2021/12/ransac-publication.pdf): 최소 표본 모델·합의 집합. 이번96컬럼에서는 난수·벽시계 제한 대신 가능한2점 가설을 유한하게 검사하고 기존 이웃 연결을 재사용했다.
