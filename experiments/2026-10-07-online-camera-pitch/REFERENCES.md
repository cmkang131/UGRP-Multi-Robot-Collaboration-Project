# 확인한 표준 방법·공개 코드

- [Lu et al., WACV 2017, 2-Line Exhaustive Searching](https://xiaohulugo.github.io/papers/Vanishing_Point_Detection_WACV2017.pdf),
  §2: calibrated image에서 두 선으로 첫 VP, great-circle 검색으로 둘째, 외적으로 셋째를 얻고
  구면 누산기로 직교 triplet을 선택한다. 본 작업의 선택 방법. Manhattan 구조가 화면에 충분히 보여야 한다.
- [Raymond Phan의 Python/OpenCV 구현](https://github.com/rayryeng/XiaohuLuVPDetection/tree/56b8a2b3c5a12f02430d3d4c4612aaff79d2e6ed),
  **논문 저자의 공식 코드가 아닌 공개 포트**, MIT(c)2019 Raymond Phan.
  `vp_detection.py`/LICENSE 원문 byte 보존, 해시를 SOURCES.json에 남긴다.
  원문30px LSD·1° 구면 bin과 탐색을 그대로 사용한다. narrow FOV의 약한 직교선 지지는 위험 요소다.
  입력 유효성 검사, nominal로 축/부호 선택, 지지선 검사 및 pitch만 갱신하는 부분은 우리 어댑터다.
- [MIT Foundations of Computer Vision §42](https://visionbook.mit.edu/3d_scene_understanding_single_view.html):
  평행선 소실점은 카메라 intrinsic을 통해 3D 방향과 연결된다. 여기서는 수직 방향을 gravity ray로 해석한다.
- [OpenCV homography tutorial](https://docs.opencv.org/4.13.0/d9/dab/tutorial_homography.html):
  평면 대응점·intrinsic에서 pose/normal을 얻는 대안. 현 자료의 무늬 없는 바닥·정지 프레임에서는
  안정적인 평면 대응과 scale/solution 선택이 별도로 필요해 이번에는 선택하지 않는다.
  알려진 벽 높이 대안도 상단/하단의 동일 수직면 대응이 필요하므로 접점-only 입력을 넘는 추가 검출기가 필요하다.

출처는 2026-10-07 읽었다. 새 pitch 상수/GT 보정표/학습 모델을 만들지 않는다.
