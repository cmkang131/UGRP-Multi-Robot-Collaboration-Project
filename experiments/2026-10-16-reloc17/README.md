# reloc17 — 위치 추정 원인 분리

**NOT_READY — 조사·분해8회 + 후보2라운드8회 종료, 원본16/16 해시 검증.** DRAFT PR [#536](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/536). 시작 SHA `5f63909becb63edc633ab3ad243a4b694fb38846`, 부모 PR #532.
장면은 `walls_floor_contrast_v5_indigo110_s80 + v1 floor + no_mip_v1`로 고정한다.

시작 시 고정한 순서: (1) gcp2 원본 R1/R2/R3·이전 장면 관문 재집계와 영상 검토,
(2) 같은 시드 93584/93583의 명령만·이전장면/reloc15·새장면/reloc15·새장면/reloc16 분해,
(3) 표준 방법의 원문·공개 구현 확인. 세 단계가 끝나기 전 제어기 수정 금지.
분해를 위한 측정 wrapper는 실험 전용이며 기본 제어기에 반영하지 않는다.
이후 가장 큰 원인 하나만 기본 off 후보로 고치고 최대 3라운드 폐루프로 잰다.

gcp2 CPU만 사용, 자기 동시 ≤8·임대 합계 ≤40. Mac 물리·렌더·GUI 0.
정답은 분석기의 오차 계산에만 쓴다. 원본은 gcp2 영속디스크에 보존한다.
DEV 예상 저장: 분해 8회×150MB + 후보 최대12회×250MB + 분석 300MB < 5GB.
Mac은 표·요약·실패 프레임·≤8MB 영상만 회수한다. 모델 호출·학습 없음.

관문표·분해표·상수 근거·참고 자료·재현 명령·원본 SHA256은 이 디렉터리에 기록한다.

## 결과와 검증 범위

R3가0이 되는 곳은 **PF resolved**다: 검출268/287 → sensor update124/108 → resolved0/0 → 등록0/301씩.
raw yaw σ 최솟값6.719°/9.114°가5° 조건을 넘는다. SIGMA_SCALE6은 근거 없는 잔차 탐색 배율이지만
이 raw PF 조건을 직접 만들지 않는다. R1은 기하 유일2/1 다음 PF 일치0, R2는 등록219/221프레임이다.

새로 찾은 결함은 정상 대기 `hold`가 진행 중 서보 보간을 취소하는 것이었다. 명령 FK는최종PWM을
유지하고 실제 목표는1899PWM(35.91°)에 멈출 수 있다. 자기 명령만 재생해 원본2,408프레임 모두의
평가 목표를 정확히 재현했다. 기본off `reloc17_servo_wait_v1`는 명령으로 계산한 이동시간 동안
정상 대기만 기존0속도 mecanum 명령으로 보낸다. 종료·중단 hold의 취소 동작은 유지한다.
속도2000PWM/s·0.1초는 기존port/primitive 값이며 수용·공분산 상수는 바꾸지 않았다.

|시드|이전장면 주행xy 중앙/p95 m|reloc16 R2 주행xy|수정 후 R2 주행xy|reloc16 R2→수정 후 yaw 중앙/p95 °|등록 프레임|
|---|---:|---:|---:|---:|---:|
|93584|.0444/.1082|.1015/.1056|.0465/.1066|9.996/10.466→.975/1.793|219/301|
|93583|.0853/.1102|.0933/.1563|.1269/.1721|1.817/6.779→.785/6.342|221/301|

같은gcp2·시드·장면의 짝 비교이며 경로/주행 프레임 수는 다르다(63→86,75→140).
관문/프레임을 독립 성공률로 합산하지 않는다. 원래 지표와 같은 stage/issued-drive 정의이며
초기 정답 정렬의 명령적분 local drift는 절대 등록 오차와 별도로 기록했다.

- R1(벽 거리장): 서보 수정 뒤에도 두 시드 등록0/301. 센서 갱신의 pan 오차>5°는0/124·0/106으로 해소됐지만 수렴은 복구되지 않았다.
- R2(색 랜드마크): 센서 갱신 pan 오차>5°는0/129·0/120, 최대.00025°/.00034°. **초기 오등록93583의13.09cm는 남음**.
- 실제 정적 위치 보정 yaw 오수용(>5°): 기존R2 6/40·5/81 → 후보R2 **1/94·5/87**. 운반compass의0/58·0/39와 구분한다.
- 운반: R1 수용8/28, R2 수용58/39에서 절대/증분 yaw 오수용0. 각라운드 **place0/2**. 운반 실행기는 이번 selfmap 대기 수정의 적용 대상이 아니다.
- 새16회 중14회cap_end,2회는 분해의 재위치 계산/SIM예산 소진(writer상HOST_ERROR). 실제 호스트 오류0. 후보8회는 모두cap_end다.
- 분해 첫30 중앙6.561로새배치를 막고 병목을 분리했다. 최종장면/마스크 경로의 후보동시4에서R1=4.666,R2=5.068로6.0 차단 기준 통과(3.5 기록 경고).

**28 비물리시험·27 subtests 통과**, Mac 물리·렌더·GUI0, 모델/학습0, weldOFF.
입력 감사의 invisible_measurements·held_world_reads는0이며 selfmap의 truth/top 입력은0이다.
운반 교사는 기존 visible-only/held-hidden 경계를 유지한다. 학생/실물 성공은 검증하지 않았다.
2라운드에서 종료한다. 초기 오등록·RGB 관측 노이즈와 공분산의 불일치·벽 거리장 수렴·place가 남았으며,
이번 자료는 이미 본 시드의 DEV 원인 분리이므로 확증자료로 승격하지 않는다. 토글은 기본off로 유지한다.

[짧은 전체 요약](summary.json), [전체 지표 압축](summary-full.json.zst), [후보 관문/거부](rejection-table-candidate.json),
[R1](round1.md)·[R2](round2.md), [원본/manifest 해시](inventory.json), [회수16파일 검증](retrieval-verification.json).
원본은gcp2 영속디스크에 있고 전체백업/다운로드는 하지 않았다. [종료 확인](lifecycle.json):
자기워커0·자기임대제거, beampair8/release25 임대와 다른 프로세스가 있어 VM은 정지하지 않았다.
대표 실패 영상은[직접 본 범위](playback-review.md)·[영상/해시](representative.json)에 보존했다.
완주 성공 영상은 없으며 정상 부분구간으로 대체하지 않았다.

## 조사 자료

- [수정 전 1–3 완료 결론](investigation-complete.md), [관문표](funnel.md)·[프레임 CSV](funnel-frames.csv)·[사유/원본 JSON](rejection-table.json)
- [4조건 분해표](decomposition.md), [압축 원본 요약](decomposition.json.zst)·[왕복 해시](compression.json)
- [참고 자료와 미확인 범위](references.md), [상수 근거 점검](constants.md)
- [명령 취소 재현](servo-audit.json), [저장 RGB likelihood 진단](likelihood-audit.json), [영상 직접 검토](playback-review.md)
- [비물리 시험](tests.md)

후보는 `reloc17_servo_wait_v1` 기본 off이다. 관측·공분산·수용 문턱을 바꾸지 않는다.
후보 소스 `47670d1428abfbb09756627c1a2be31caf650465`, 후보 폐루프 2라운드를 종료했다. 추가 후보·세 번째 라운드는 제출하지 않았다.

## 참고 자료

- [Nav2 AMCL 공식 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [PF convergence/공분산 공개 구현](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c).
- [Boniardi 등(2019), 알려진 평면 지도+단안+odometry의 layout-edge MCL](https://arxiv.org/pdf/1903.01804). III-C 픽셀 거리 관측식 확인, 저자 실행 코드 위치 미확인.
- [ORB-SLAM3 재위치 공개 코드](https://github.com/UZ-SLAMLab/ORB_SLAM3/blob/master/src/Tracking.cc), [hloc map localization](https://github.com/cvg/Hierarchical-Localization/blob/master/hloc/localize_sfm.py). 각 대응·RANSAC·최적화 호출을 확인했으며 우리 센서의 공분산 보정 보장은 미확인.
- [ROS2 joint trajectory의 취소/선점 정책](https://control.ros.org/rolling/doc/ros2_controllers/joint_trajectory_controller/doc/userdoc.html). 서보 명령 접수·취소·완료를 구분하는 참고다. 상세 열람 범위와 적용 한계는 [조사표](references.md).
