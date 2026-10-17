# mapbuild10 — 측정모델 감사와 시작 구역 사전

진행 중. 새 물리0. 기본 off 후보만 준비하며 결과 미완료를 성공으로 보고하지 않는다.
mapbuild8/9 원본·요구표는 유지한다. 시작 구역 범위·대략 방향은 외부 운영 사전이어야
하며 평가 정답/spawn을 반올림하여 만들지 않는다. 아직 구역 값은 미지정이다.

## 먼저 확인한 참고 자료

- [Nav2 공식 AMCL 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/):
  sigma_hit .2m, z_hit/z_rand .5/.5, max_beams 60, laser_max_range 100m,
  laser_likelihood_max_dist 2m. RGB 가상 스캔에 라이다 성능을 승계하지 않는다.
- [공식 likelihood_field 원문](https://api.nav2.org/nav2-rolling/html/likelihood__field__model_8cpp_source.html):
  p=1+sum(pz^3), NaN/max-range 건너뛰기. 기본 모델은 독립 빔의 곱이 아니다.
- mapbuild9의 고정 Nav2 SHA 235fc5ce55bdf94d9be360fdbca39d89dc0e4f74와
  LGPL-2.1-or-later 이식/원문/NOTICE는 harness/mapbuild_amcl_vendor/에 보존.
  새 scan matcher를 만들지 않는다.
- PR #571은 시작 구역 사전을 허용한 사용자 결정의 기록이며 2026-10-17 열람 시 OPEN.
  해당 결정은 이번 사용자 지시가 직접 승인했다. .5m/±30°는 조정자 설계다.

## 순서와 판정

측정모델 프레임별 잔차·로그우도·빔수·지도 밖 수·자기 FK 감사를 먼저 봉인한다.
그다음 운영 시작 구역 사전과 Nav2 기본 가산 likelihood_field를 동일 저장 입력으로
판정한다. OFF 대비 개선 전 새 물리는 제출하지 않는다. GT는 예측 봉인 이후 별도
평가만 읽는다. gcp5 R1–R3와 gcp3 418뷰는 합산하지 않는다.
