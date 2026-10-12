# 방법 선택·원본 코드 대조

- [Ulrich & Nourbakhsh, AAAI 2000 원문](https://www.cs.cmu.edu/~illah/PAPERS/abod.pdf)
  §3(p.2): 바닥 평면으로 장애물 내부를 투영하면 거리 과대가 생기므로 열별 최하단
  장애물 픽셀을 쓴다. §4(p.3): Gaussian5×5→HSI→바닥 참조 H/I histogram→비교.
  2026-10-08 원문 확인. 벽 의미 분류기가 아니라 바닥/장애물 외형법이라는 한계 유지.
- 기존 로컬 재구현 `harness/wall_floor_boundary.py:17–20,23–48,73–125`를
  **상수·알고리즘 변경 없이** 재사용한다. 원 저자 코드 복사가 아니라 egomap10에
  기록한 논문 재구현이다. 상세 출처/원문 수치와 공학상 선택 구분은
  [기존 REFERENCES](../2026-10-07-wall-floor-boundary/REFERENCES.md) 그대로.
- 기존 `height_free_wall.py:280–294`의 `floor_boundary_v1` ABI 변환·명령 self-mask를
  거쳐 연결한다. 새 `harness/wall_contact_detector.py`는 옵션 이름/현행 active 경로만
  연결한다. `active_wall_vision.observe`와 `self_wall_segment_points.contact_points`
  양쪽 같은 scan을 쓴다. 이전 egomap10 실패는 삭제/수정하지 않으며 새 조건 결과로 승계하지 않는다.
- PR406 `codex/s2-realism` **9fb8e46f864c3f413a23e830ad8327da46924e3a**의
  `harness/zone_solo_cyan_floor_contact.py:18–70`도 읽기 전용 대조했다.
  고정 H/I 표와 양쪽3×5 pixel이 모두 바닥이면 지우는 floor/floor veto다.
  이번 지배 원인은 **벽 내부 무늬**라 이 veto만으로는 해결되지 않는다.
  따라서 기존 자기 RGB 참조+최하단 접점 구현을 고르고 PR406 코드/보정표 복사·변경0.

기하 자동 분류는 GT 차체/카메라·벽 AABB·상자 OBB·RGB를 사용하는 **평가 전용**이다.
GT 차체에서>.15m이면서 실제 카메라로 재투영해≤.15m가 되는 점은 기타/투영 잔차.
벽 높이>.015m의 벽 내부에서 검은 무늬 대비가 있는 접점은 wall_tape 후보,
주위5광선 모두 바닥이면 RGB saturation으로 체크/색 경계를 구분한다.
주변 광선이 문틀에 맞고 중앙은 저장된 개구부를 통과하면 문 개구부 후보다.
각 후보의 상위2 RGB 예시(5초 이상 간격)를 직접 확인한다. 자동 유형은 완전한 semantic GT나
전 점 수동 정답이 아니다. peer는 저장 링크 GT가 없어 envelope 후보를 미판별로 두며,
가장자리0은 유효 remap support 검사 기준이지 렌즈 잔차가 완전히 없다는 뜻이 아니다.
