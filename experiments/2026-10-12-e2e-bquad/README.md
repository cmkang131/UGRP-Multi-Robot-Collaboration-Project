# B quad detection (`not_convex_quad`) — 2026-10-12, Refs #453 #456

Toggle: `b_marker_detect=contrast_v2` (default off; `--b-marker-detect contrast_v2`). No bundle ID registered.
Mark pixels are the same as `contrast_v1`. Only the B region/quad stage changes (`harness/e2e_b_quad.py`).

## What `not_convex_quad` is (saved frames)
- Wall and B floor are both in the blue HSV band (wall hue ≈105, S 73–78; B floor hue 112–113, S 118–144; measured on v213 frames).
  They merge into blobs of 50 % of the frame (144k–175k px²). v2 uses hue ≥109 for the region mask.
- B is large and the robot is at or beside it: all 42 saved B-visible frames (e2e11, labeled) have the B patch cut by the lens circle/image edge,
  0/42 with all four corners. A complete 4-corner quad therefore does not exist in these frames.
- A body mask applied before `findContours` can carve a bite (not confirmed on frames).

## v2
undistort contour (fisheye model) → convex hull (fit only) → `approxPolyDP` with growing epsilon (1–4 %) → corners distorted back for the ray lookup.
Guards: reject image border, lens circle (`lens_valid`), solidity < 0.9, fit area error > 10 %, floor area/aspect outside 0.04–4 m² / 5. Hull is never promoted to a complete B.

## Offline result (394 labeled e2e11 frames + 120 unlabeled e2e14 frames; labels used only in evaluation)
| | off | v1 | v2 |
|---|---|---|---|
| accepted, e2e11 | 0/394 | 0/394 | 0/394 |
| false accepts (B not in view) | 0/352 | 0/352 | 0/352 |
| accepted, e2e14 (unlabeled) | 0/120 | 0/120 | 0/120 |

v2 reasons on the 42 partial-B frames: lens_clipped 42/42. So v2 does **not** make B confirmable; it removes the wall merge and the lens-bend vertices and
reports the true cause (clipping). The next lever is view planning (a viewpoint where all four corners are inside the lens circle), not polygon tolerance.
Only 2 v213 JPEGs were available locally; the rest were not fetched (`ssh arm` does not resolve). Not scored.

## References (checked = read here)
- OpenCV `approxPolyDP`, `convexHull`, `minAreaRect`, `fisheye.undistortPoints/distortPoints`: used and run (cv2 4.13); docs text not re-read.
- ArUco quad candidate: `polygonalApproxAccuracyRate` default 0.03 (checked in cv2 4.13); corner refinement default 0 = none. AprilTag line fitting: unverified (from memory).
- Undistort before quad fitting: standard for rectified detection; unverified citation.

---
# 후속: 시점 계획(A) + 부분 마커 추정(B), 둘 다 기본 off — 2026-10-12

번들 ID는 등록하지 않았다. 토글과 권장값:

| 토글 | 값 | 기본 | 권장 |
|---|---|---|---|
| `boundary_views` (`--boundary-views`) | `standoff_fullquad_v1` | off | 이 값(실제 실행 전 검증 필요). 번들 등록 전까지 기존 `candidate_views_v1`과 별도 비교 |
| `b_marker_detect` | `partial_known_size_v1` | off | 평가·진단용. 게이트/`boundary()`에는 연결하지 않음 |

## A) `standoff_fullquad_v1` (`harness/e2e_b_standoff.py`, `harness/e2e_boundary_views.py`)
입력은 정적 지도(B 0.8×1.4 m, 벽, 슬롯 표식)와 고정 카메라(SEARCH 자세 FK: 높이 0.231 m, 피치 −18.1°, 어안 K/D, 렌즈 원, 몸체 마스크)뿐이다.
격자(0.1 m × 10°)로 자세를 훑어, B 윤곽(네 모서리+모서리 사이 40점씩, 어안 왜곡 반영)이 모두 쓸 수 있는 영상 안(경계에서 ≥14 px)에 들고,
몸체 마스크와 겹치지 않으며, 슬롯 표식이 ≥9 px이고, 벽(0.40 m > 카메라 0.23 m)이 가리지 않고, 몸체 사각형이 지도에서 비어 있고(`Costmap.pose_clear`), 정적 지도에서 도달 가능한 자세만 채택한다.
자기 위치 오차(±5 cm, ±4°) 8방향에서도 유지되는 자세만 남긴다.
- 결과: 후보 6561 위치 중 322 자세 채택, 위치 오차 내성 통과 85 (`standoff-plan.json`). 모두 B 북쪽 구역 쪽(x 2.3–3.7, y −0.8–0.7), B 중심에서 2.2–3.2 m, 대략 −40°(남동) 방향.
  최선 자세 (2.3, 0.0, 320°): 네 모서리 픽셀 (466,73) (356,62) (146,76) (246,87), 경계 여유 50 px, 슬롯 표식 15 px.
- 대조: e2e11식 근접 시점(near edge 0.7 m 앞)은 `outline_off_image`로 탈락 → 기존 시점은 구조적으로 불가능했음.
- 실제 경로: `choose_view(standoff=…)`가 위 자세(지도→자기 좌표 변환)를 고정 방향으로 후보화, 경로·충돌 검사는 기존과 동일. 시뮬레이션은 돌리지 않았다(이 경로의 실제 도착·확인 성공은 **확인 안 됨**).
- 주의: 승인 자세가 전부 문(2.2, 0.05) 근처~구역 안쪽이라 문 통과 경로가 전제다. 렌더된 실제 영상에서 네 모서리가 보이는지는 시뮬레이션 전에는 투영 계산뿐이다.

## B) `partial_known_size_v1` (`harness/e2e_b_partial.py`, `scripts/eval_b_partial.py`)
렌즈·테두리·몸체에 잘린 파란 패치에서 잘리지 않은 실제 윤곽점만 골라 어안 역왜곡 → 명령 FK 카메라 자세로 바닥 평면에 투영 → 정적 지도의 알려진 크기(0.8×1.4)의 직사각형(x, y, yaw 3자유도)을 격자+강건 최소제곱으로 맞춘다.
수락 조건: 잔차 RMS ≤3 cm, 인라이어 ≥70 %, 가우스–뉴턴 공분산(두 변 이상이 보여야 x·y·yaw 고정; 위치 ≤6 cm, yaw ≤6°), 차순위 가설과 비용비 ≥1.5, 사각형 재투영 IoU ≥0.85, 패치가 사각형 밖으로 ≤10 %.
`solvePnP`는 점 ≥4개(모서리)가 필요하므로 모서리가 1개만 보이는 이 경우에는 쓸 수 없어 선 기반 적합을 썼다.
`boundary()`/`ArrivalGate`는 바꾸지 않았다: 추정은 `complete=False, estimated_from_partial=True`인 별도 증거이고 B 전체 경계 확인으로 승격하지 않는다(게이트의 기존 금지 유지).
평가(e2e11 저장 프레임 394장, 라벨·참값은 탐지 뒤 평가 출력에만 사용; `partial-eval-summary.json`):
- 부분 B 42장: 수락 42/42. 로봇 좌표계 중심 오차 중앙 4.2 cm(p90 4.7, 최대 4.9), yaw 오차 중앙 1.8°(최대 2.2°).
- B 없음 352장: 오수락 0/352. 완전 B 0장.
- 한계: 42장은 2개 실행·사실상 한 시점(B가 정면 0.73–0.99 m, 모서리 1개 보임)이라 독립 표본이 적다. 오차는 +4 cm 전방/−1.6 cm 측방으로 일정(표준편차 2–3 mm) → 무작위가 아니라 계통 편향(카메라 장착 미검증, 파란 마스크 경계)일 가능성이 있고 원인은 확인 안 됨. 공분산 표준편차(2 mm)는 형식값이라 과소.
- 합성 영상 시험(다른 위치/각도 3개 복원 <6 cm, <4°; 한 변만 보임·크기 다름·파랑 없음은 거부)은 `tests/test_e2e_b_partial.py`.

## 참고 자료 (읽음/미확인)
- 읽음(로컬 OpenCV 5.0.0 docstring): `solvePnP` — SOLVEPNP_IPPE는 점 ≥4개·동일 평면, IPPE_SQUARE는 마커 자세용 4점; `fisheye.projectPoints/undistortPoints`는 코드에서 실제 사용.
- docs.opencv.org 웹 페이지는 HTTP 403/빈 응답으로 열지 못했다 → 웹 문서 인용은 **미확인**. 알려진 크기 평면 마커의 선 기반 자세·가시 변 적합이 표준이라는 서술(ArUco/AprilTag, 평면 PnP 문헌)도 기억에 의존, **미확인**.
- 원격(ARM) 저장 프레임: `arm` ssh 별칭이 없어 가져오지 않음. 로컬 394장만 사용.
- 기존 테스트 `tests/test_e2e_boundary_repair.py::test_native_artifact_correction…`는 이번 변경과 무관하게 실패(E2E17 기록 파일 바이트 수 1362≠1450); 이번 변경은 해당 파일을 건드리지 않음.
