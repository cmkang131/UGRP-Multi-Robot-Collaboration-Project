# 확인한 표준 방법과 적용 차이 (2026-10-11)

- [REP-105 원문](https://raw.githubusercontent.com/ros-infrastructure/rep/master/rep-0105.rst): odom은 연속, 전역 보정은 map→odom. 현재 코드는 command odom(encoder 측정 아님)을 쓰며 shared heading의 pose/path/goal을 함께 변환한다. 지도 계획·목표 판정은 map 좌표다. map RMSE와 raw command-odom drift를 구분한다. 기존 graph TF와 이 제어용 local-map→command-odom TF는 서로 다른 변환이다.
- [Nav2 Jazzy AMCL](https://raw.githubusercontent.com/ros-navigation/navigation2/jazzy/nav2_amcl/src/amcl_node.cpp): update_min_d=.25m/update_min_a=.2rad, shouldUpdateFilter의 x/y/yaw 변화 OR; getMaxWeightHyp의 클러스터 총가중치와 publishAmclPose의 평균. 기존 GMapping 1m/.5rad 누적 게이트 바깥에 AMCL 순변위 게이트를 추가한다. 이 토글은 stationary 관측 억제이며 제자리 회전 .2rad 이상은 허용한다.
- [AMCL kd-tree](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_amcl/src/pf/pf_kdtree.c): .5m/.5m/10도 occupied-bin 이웃 flood fill. [pf.c](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_amcl/src/pf/pf.c)의 총가중치, XY 평균, sin/cos yaw 평균을 사용한다. Python 재구현이며 yaw 경계 bin만 modulo36으로 연결한다. RBPF 지도는 평균하지 않고 기존 입자 지도를 유지하므로 이 변화는 클러스터 pose 보고의 DEV 비교다.
- [robot_localization EKF](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/rolling-devel/src/ekf.cpp)와 [FilterBase](https://raw.githubusercontent.com/cra-ros-pkg/robot_localization/rolling-devel/src/filter_base.cpp): innovation, S=P+R, Mahalanobis, Kalman gain, Joseph covariance update. XY 자유도2의 [NIST χ² 99%](https://www.itl.nist.gov/div898/handbook/eda/section3/eda3674.htm)=9.21034로 게이트한다. PF 출력과 predictor는 상관되어 있으므로 독립센서 EKF의 일관성 보장을 주장하지 않는다. 온라인 uncertainty 출력은 reporter P+PF R로 ambiguity를 보존한다.
- 혁신 후보는 게이트와 Kalman/Joseph 보정을 함께 쓴다. 확장 본 실행 11개에서 측정 수락 2,242회·Mahalanobis 거부 13회이므로, 점프 감소 전체를 χ² 거부만의 효과로 해석하지 않는다. 클러스터 후보도 출력 공분산은 기존 전체 PF 산포를 유지한다.
- 보정 크기 토글은 동일 χ² 타원으로 누적 운동 Q에 대한 XY 보정을 거부한다. 이는 운동공분산으로 제한하라는 사용자 요구의 명시적 조합이며 EKF/REP-105의 필수 규정은 아니다. Q는 현재 RBPF가 쓰는 OpenSLAM motion_variance와 동일하다.

확인 범위: 위 공개 원문/공개 구현을 직접 열람했다. REP ros.org와 일부 docs URL은 접근 거부여서 공식 GitHub 원문으로 확인했다. 최신 main 구현도 대조했으며 새로운 논문의 검증되지 않은 개선을 추가하지 않았다. 이미 본 DEV 로그의 후보 선택은 확증 결과가 아니다.

Azure CPU 제한: [systemd AllowedCPUs](https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.resource-control.xml)의 cgroup cpuset으로 자기 scope만 0–11에 제한한다. taskset 이후 Mesa helper가 affinity를 확장하는 것을 관측했으므로 thread affinity도 확인했다. [Mesa LP_NUM_THREADS](https://docs.mesa3d.org/envvars.html)는 렌더 스레드 수이고 CPU 허용 범위 제한을 대신하지 않는다.

온라인 가상 경로 복제 오류: [Python deepcopy memo](https://docs.python.org/3/library/copy.html)에 따라 wrapper와 underlying odometry의 cyclic owner를 같은 private 복제 객체로 연결한다. 기존 forecast는 object.__new__(type(grid.odom)) 뒤 owner/driver만 넣어 PoseView의 base/reporter를 빠뜨렸다. 가상 particle rollout은 private CloudOdometry를 사용하고 실제 reporter·driver·RNG·cloud를 변경하지 않는 회귀 시험으로 검증한다.

원본 회수: [GNU tar 압축 지원](https://www.gnu.org/software/tar/manual/html_section/Compression.html)의 `-I zstd`로 영속 디스크에 운송 복사본을 만들고 ARM에서 직접 해제·전체 파일 SHA-256을 검증한다. SSHFS에서 수천 파일을 각각 해시할 때의 900초 시간 초과를 피한다. 전송 전후 Azure 원본 inventory/state와 ARM inventory가 같아야 완료이며 검증 뒤 운송 복사본만 제거한다. 원본 두 사본은 보존한다. 별도 0회 물리 실행 fixture의 파일·symlink 왕복과 lifecycle marker 수락을 확인했다.

선택적 물리 의존성: [Python import FAQ](https://docs.python.org/3/faq/programming.html#what-are-the-best-practices-for-using-import-in-a-module)의 필요한 범위에서 import하는 방식으로 MuJoCo를 실행 경로 안에서 불러온다. 숫자 점검과 번들 공정성 계약 시험은 simulator 설치 없이 11개 모두 통과했다. 실행 중인 Azure worker는 기존 고정 SHA를 유지한다.
