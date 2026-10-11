# 점프 원인 (egomap70 실행 SHA f26d9322c48eadbe2b28777ac1f07684ca03e124)

- `harness/self_map_rbpf.py:157-159`의 CloudOdometry.pose는 평균이 아니라 `poses[best]` 한 입자를 보고한다. covariance는 같은 파일 162-169에서 전체 입자 산포+pending Q를 보고하므로 2.5~3 sigma라는 크기만으로 재초기화를 뜻하지 않는다.
- `harness/rbpf_manhattan.py:99-107`은 벽 방향 likelihood로 **CSM 거부 판정 전에** weights와 best를 바꾼다. `harness/rbpf_rejection.py:109-150`은 거부 프레임의 CSM increment를 취소하지만 이미 바뀐 yaw-prior best는 유지한다. 수락 프레임은 CSM increment로 best를 다시 고른다.
- 63002 calib_traversed: t165.7→165.9/frame823→824, best30→48, XY 0.693384m. 동일 기존 lineage 이동은 0.003355m, 선택된 두 후보 간 거리는 0.690993m. command prediction XY0.000351m/yaw0.103543rad. high_residual=.220314m로 CSM 거부·sensor_weight_update=false였어도 yaw conditioning 후 입자48이 출력되었다. resampled=false, route offset 없음.
- 63002 calib_traversed_zone: t156.9→157.1/frame779→780, best32→66, XY0.767250m. 기존 lineage 이동0.026227m, 두 후보 간0.791032m. CSM accepted/residual=.049440m, sensor_weight_update=true, resampled=false, route offset 없음. raw만으로 yaw 단계와 CSM 단계 중 어느 단계가 처음66을 선택했는지 분리할 수는 없다.
- `harness/rbpf_motion_gate.py:43-67`의 **GMapping 게이트가 이미 실제 경로에 적용**되어 있다. 두 프레임 모두 누적 angular .520437/.518305rad가 .5rad 문턱을 넘었다. AMCL vendor의 .25m/.2rad 게이트는 이 경로의 게이트가 아니다. `pulse.predicted_delta`는 다음 발행 명령의 예측이므로 이번 프레임의 운동량은 이전 driver state 차이로 계산했다. translation≈0은 회전까지 정지라는 뜻이 아니다.
- `harness/goal_route_continuous.py:346`의 tracking_reset=False는 상수이다. 입자 교체·정합 보정 탐지기로 사용하면 안 된다. 원본 결정·online cloud를 ARM에서 읽어 숫자만 추출했으며 전체 원본은 변경하지 않았다.

오프라인 후보는 최초 8기록으로 선택했다. 이후 ARM에서 읽을 수 있는 본 실행 3개와 smoke 1개를 추가 재생했으며, 최초 8개 수치가 동일함을 확인했다. 본 실행 11개와 다른 SHA의 smoke는 따로 집계한다. ARM incoming 13개는 필수 원본이 없고 원 실행 호스트의 읽기 전용 SSH도 연결되지 않아 회수 완료로 표시하지 않았다. checkpoint prefix 중복과 프레임 상관이 있다. 본 연구 성공률·독립 검증 통계로 사용하지 않는다. 전체 숫자와 source SHA-256은 summary.json이 연결한 로컬 분석에 있다.

S3 적용 범위: `zone_s3_no_prior.py:44-59` → `run_s2_unknown_start.py:20-28`은 별도 S2 PF localizer를 구성하고 `zone_s3_no_prior.py:65-83`의 OwnPosePort로 같은 추정을 pair actor에 전달한다. `zone_solo_cyan_best_cluster.py:72-121`에는 이미 AMCL 최대 질량 클러스터 보고가, `zone_solo_cyan_amcl_update.py:86-92`에는 최소 운동 갱신 게이트가 있다. egomap의 `CloudOdometry.poses[best]` RBPF 출력 경로를 직접 공유하지 않으므로 이번 토글이 S3에 자동 적용되지 않는다. S3 시작 scan 생략·σ≈2.2m는 사용자 제공 진단이며 여기서는 실행하지 않았다. 읽은 SHA·파일 해시는 s3-scope.json.

Azure v1 추가 오류: 63001 cluster는 t130.1에서 실제 B 내부 도착 선언 후 t130.3에서 HOST_ERROR(AttributeError: pose). active_information_gain.py:97–101은 현재 odometry의 type만 할당하고 owner/driver만 채워 PoseView.base/reporter가 없는 private 객체를 만들었다. 이 오류를 실제 forecast 호출 회귀 시험으로 재현했고 v2는 underlying CloudOdometry와 wrapper를 deepcopy memo에서 같은 private odometry로 연결한다. 원본 cloud·driver·reporter·RNG 불변을 확인한다. v1 수치와 v2 비교 코호트는 합치지 않는다.

S3 재확인(2026-10-12 KST): `ec87ee73577a096eae07aeee6c10522238934cdd`의 `zone_s3_no_prior.py:42`는 새 `zone_s3_pulse_odometry.py:22-24`를 거쳐 같은 S2 factory로 연결된다. pulse calibration 선택과 pair missing-pose wait가 추가됐고, 별도 S2 PF/기존 클러스터·운동 게이트라는 결론은 같다. S3 파일·프로세스 변경과 재실행은 0회다.
