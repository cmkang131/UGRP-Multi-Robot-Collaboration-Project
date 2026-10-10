# 표준 규칙과 적용 경계

- [Ulrich & Nourbakhsh, AAAI 2000](https://www.cs.cmu.edu/~illah/PAPERS/abod.pdf),
  §3 p.2: 평면 지면 투영은 물체의 높은 부분일수록 거리를 과대 추정하므로 열별 가장
  낮은 obstacle 화소만 사용하는 방법을 제시한다. §2는 Lorigo–Brooks–Grimson 1997의
  영상 하단10행 참조영역을 설명하며, 하단에 장애물이 없다는 가정과 외형 대표성 한계를
  지적한다. 원문 PDF 직접 확인. 저작권 원문을 복제하지 않고 링크/규칙만 기록했다.
- Lorigo–Brooks–Grimson 1997 원문 직접 확인은 미완료다. 이 기록에서 구체적인 코드
  이식 근거는 직접 읽은 Ulrich §3이며, '연결성만으로 실제 바닥 분류가 된다'는 결론은
  어느 논문에도 귀속하지 않는다. 본 요청은 HSI 분포 학습이 아니라 연결 규칙만이다.
- 기존 `height_free_wall.py:159–193`의 `surface_run_top`을 재사용한다. 명도/색차 step
  tol10과 양쪽3행 평균을 그대로 쓰며, 학습된 바닥 색/새 임계값/GT 입력0.
  기존 `:307–339` 후보 판정은 low→high지만 첫 경계가 wall 조건에 실패하면 더 높은
  경계를 찾았다. 이제 `:341–347`에서 하단 연결 경계의 응답 band만 허용한다.
  `harness/wall_bottom_connected.py:12–40`이 열별 연결/무효영역/첫 경계를 처리한다.
- 차이: 문헌은 분류된 obstacle을 사용하지만, 여기서는 **사용자 요청대로 새 외형 모델
  없이 기존 edge run을 연결성의 장벽으로 사용**한다. 처음 만난 경계가 checker/색 바닥이면
  그 뒤의 진짜 벽도 버린다. 밝기가 비슷한 바닥/벽은 연결될 수도 있다. 성능 보장 아님.
- remap support는 기존 white-image undistort 패턴, self-mask는 기존 명령 기반 경로다.
  하단 가림을 건너뛰어 새 seed를 만들지 않는다. 연속 edge 응답행을 한 경계로 묶는 것은
  기존3행 smoothing 때문에 생기는 응답폭을 보존하기 위해서이며 새 픽셀 여유값은 없다.
- egomap36 다중시점은 `harness/self_wall_pr.py`의 `grid_support/segment_support/apply`
  그대로, N1/30°·N2/0° 고정. egomap37의 paired confidence/pose 평가기를 재사용했다.
  비어 있는 관측은 원장에 보존하되 support API에는 전달하지 않는다. 신규 증거를 만들지 않는다.
- 점 recall은 평가 전용 saved-camera column floor trace + AABB/box/peer envelope occlusion.
  기존 `markerless_probe.ColumnModel`과 egomap37 `Labels.surface`를 재사용했다.
  peer 세부 형상/동적 이동을 완벽히 재현한 semantic segmentation GT가 아니다.
