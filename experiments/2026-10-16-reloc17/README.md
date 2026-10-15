# reloc17 — 위치 추정 원인 분리

진행 중, DRAFT PR [#536](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/536). 시작 SHA `5f63909becb63edc633ab3ad243a4b694fb38846`, 부모 PR #532.
장면은 `walls_floor_contrast_v5_indigo110_s80 + v1 floor + no_mip_v1`로 고정한다.

순서: (1) gcp2 원본 R1/R2/R3·이전 장면 관문 재집계와 영상 검토,
(2) 같은 시드 93584/93583의 명령만·이전장면/reloc15·새장면/reloc15·새장면/reloc16 분해,
(3) 표준 방법의 원문·공개 구현 확인. 세 단계가 끝나기 전 제어기 수정 금지.
분해를 위한 측정 wrapper는 실험 전용이며 기본 제어기에 반영하지 않는다.
이후 가장 큰 원인 하나만 기본 off 후보로 고치고 최대 3라운드 폐루프로 잰다.

gcp2 CPU만 사용, 자기 동시 ≤8·임대 합계 ≤40. Mac 물리·렌더·GUI 0.
정답은 분석기의 오차 계산에만 쓴다. 원본은 gcp2 영속디스크에 보존한다.
DEV 예상 저장: 분해 8회×150MB + 후보 최대12회×250MB + 분석 300MB < 5GB.
Mac은 표·요약·실패 프레임·≤8MB 영상만 회수한다. 모델 호출·학습 없음.

관문표·분해표·상수 근거·참고 자료·재현 명령·원본 SHA256은 이 디렉터리에 기록한다.

## 조사 자료

- [수정 전 1–3 완료 결론](investigation-complete.md), [관문표](funnel.md)·[프레임 CSV](funnel-frames.csv)·[사유/원본 JSON](rejection-table.json)
- [4조건 분해표](decomposition.md), [압축 원본 요약](decomposition.json.zst)·[왕복 해시](compression.json)
- [참고 자료와 미확인 범위](references.md), [상수 근거 점검](constants.md)
- [명령 취소 재현](servo-audit.json), [저장 RGB likelihood 진단](likelihood-audit.json), [영상 직접 검토](playback-review.md)
- [비물리 시험](tests.md)

후보는 `reloc17_servo_wait_v1` 기본 off이다. 관측·공분산·수용 문턱을 바꾸지 않는다.
후보 소스 `47670d1428abfbb09756627c1a2be31caf650465`, 후보 폐루프 진행 중이다.

## 참고 자료

- [Nav2 AMCL 공식 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [PF convergence/공분산 공개 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c).
- [Boniardi 등(2019), 알려진 평면 지도+단안+odometry의 layout-edge MCL](https://arxiv.org/pdf/1903.01804). III-C 픽셀 거리 관측식 확인, 저자 실행 코드 위치 미확인.
- [ORB-SLAM3 재위치 공개 코드](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/master/src/Tracking.cc), [hloc map localization](https://github.com/cvg/Hierarchical-Localization/blob/master/hloc/localize_sfm.py). 각 대응·RANSAC·최적화 호출을 확인했으며 우리 센서의 공분산 보정 보장은 미확인.
- [ROS2 joint trajectory의 취소/선점 정책](https://control.ros.org/rolling/doc/ros2_controllers/joint_trajectory_controller/doc/userdoc.html). 서보 명령 접수·취소·완료를 구분하는 참고다. 상세 열람 범위와 적용 한계는 [조사표](references.md).
