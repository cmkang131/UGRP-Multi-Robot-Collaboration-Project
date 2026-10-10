# S3 s14201 오프라인 원인 분리 (2026-10-09)

**물리 실행 0회, 아직 S3 위치 수렴 0/3.** HOST_ERROR 두 계약을 수정했고, S3가 S2의 런타임 v3 카메라 바인딩을 누락한 것을 찾았다. 마운트 보정만 한 저장 입력 재생에서 r2/r3의 최종 위치 오차가 0.065/0.074m로 줄지만 σ 기준은 통과하지 못한다. r1은 반대 방향의 잘못된 모드가 남는다. 성공으로 승격하거나 문턱을 낮추지 않았다.

- 수정 코드: `f965ad158a68add5654559fcb069a792ebb24f47`; HOST 수정 `da7059b2`. 원본 소스 `6c6571244e33a6e9e39b00afcd38d805035aed7d`, seed14201.
- 기준 원본: `/Users/changmin/projects/ugrp/outputs/s3-no-prior-6c657124-s14201-v142`; 파생 결과: `/Users/changmin/projects/ugrp/outputs/s3diag-20261009`.
- 원본 **2561개 파일 SHA-256 전부 일치**. 프레임 각846개·명령3356개 전체 호스트 재생 일치. 수정 후 runtime/trial JSON 모두 생성, 직렬화 오류0. 과거 원본 파일은 추가/수정하지 않았다.
- 코드 시험: `python -m pytest -q tests/test_s3_no_prior.py` **11 passed**. 공통 frozen S2/v107/v108 파일과 카탈로그는 바이트 동일; 새 옵션은 기본 off이며 실제 물리 검증은 없다.

## 가장 큰 연결 오류: XML 카메라와 실제 렌더 마운트가 다름

`sim/multi_masterpi_production.py`의 `_bind_controller`는 `_configure_measured_robot_camera()`를, `_render_rgb_direct`는 매 프레임 `_sync_real_camera_mount()`를 호출한다. 두 기본 메서드는 `masterpi_camera_profile`의 legacy 마운트를 쓴다. S2는 `sim/s2_realism_camera_binding.bind_camera`로 두 메서드를 v3에 고정하지만 S3 v142는 XML 변환만 하고 이 연결을 누락했다. 따라서 같은 `scene.xml` 카메라 항목은 실제 렌더 카메라가 같다는 증거가 아니었다.

마운트 차이는 **20.20569mm, 2.540823°**다. K/D·해상도·제어기 파라미터는 같다. 기존 v3 보정의 그리퍼 변환을 분리하고 알려진 legacy 마운트를 합성했으며, GT·피팅·영상 생성/변형은 쓰지 않았다. 같은 원본·명령·seed에서 첫 벽 단서가 **0/0/0 → 96/96/35**로 바뀐다. 특히 S2 1066과 S3 r2는 같은 시작 위치·pan970·관측시각2.25초·servo pose인데, S2는96개/S3는0개였고 이 한 요인 보정으로96개가 복구된다.

| 로봇 | 원본 마지막 XY 오차 / σ (m) | 마운트만 보정한 전체 재생 XY 오차 / σ (m) | 마운트 보정 후 정확 수렴 |
|---|---:|---:|---|
| r1 | 4.201968 / 0.263903 | 4.262512 / 0.270649 | 없음 |
| r2 | 2.056983 / 0.028012 | 0.064795 / 0.145810 | 없음 |
| r3 | 0.210872 / 1.544389 | 0.073825 / 0.080392 | 없음 |

전체 재생 끝은 원본43.55 SIM초이며 새로운 물리 시간은 아니다. 정확 수렴은 기존 `σxy≤0.05m` 및 eval 오차 `XY≤0.25m, yaw≤15°`를 유지했다. r2의 원본 첫 허위 수렴은13.95초/오차2.05698m다. 점 추정이 가까워진 것과 수렴 인증은 구별한다.

## 요청한 네 후보의 로봇별 분리

| 로봇 | (a) 타 로봇 가시성 진단 | (b) 시작/가설 모드 | (c) 첫5개 pan·벽 단서 | (d) 정적 환경 |
|---|---|---|---|
| r1 | 0/767개 해석 가능 프레임에서 주황 표면 검출;측정에 쓰인 peer 마스크0 | S2 1065와 시작XY 차이0.0242mm, yaw0.0013°; 원본 마지막 연결모드6개 | 970→2030→1770→1500→1230; 벽 0,32,8,0,0; 색상선 1,3,3,2,1 | 동일 지도/지형; 런타임 카메라 불일치 |
| r2 | 14/716개 해석 가능 프레임에서 주황 표면 검출;13.75초 하한0.7223%/제외상자10.1982% | S2 1066와 시작XY 차이0.0241mm, yaw0.0016°; 원본 마지막 연결모드2개 | 970→1500→1230→1770→2030; 벽 0,0,0,0,0; 색상선 4,0,1,1,4 | 동일 지도/지형; 런타임 카메라 불일치 |
| r3 | 0/767개 해석 가능 프레임에서 주황 표면 검출;측정에 쓰인 peer 마스크0 | S2 1069와 시작XY 차이0.0240mm, yaw0.0016°; 원본 마지막 연결모드6개 | 1500→1770→970→1230→2030; 벽 0,0,47,21,0; 색상선 2,1,4,4,1 | 동일 지도/지형; 런타임 카메라 불일치 |

모드는 기존0.5m/10° 연결-bin 정의이며 정확한 기하학적 대칭 개수로 간주하지 않는다. XY/yaw/질량의 모드별 목록은 `summary.json:baseline_final_modes`에 모두 보존했다. 처음에는 넓은 전역 분포도 연결모드1개일 수 있어 모드 수만으로 수렴을 인증하지 않는다.

(a) [프레임별 값](peer-pixel-bounds.jsonl)은 **정확한 semantic segmentation GT가 아니라 하한/보수 제외상자**다. 정적 모델에서 얻은 전체 관절체 포락 반경0.373733m, eval robot pose, 기록 마운트로 합성한 own camera를 이용해 타 로봇 ROI를 제한했다. 주황 표면 HSV 범위와20px 여백은 오프라인 주석 도구일 뿐 제어 문턱이 아니다. 측정 joint/camera pose·segmentation은 원본에 없으며 이동 중 미보정 posture r1/r2/r3의79/130/79개 프레임은 미확정으로 남겼다. 제어 필터가 실제 점수 계산에 사용한 모든 프레임은 이 범위에 포함된다. r2의13.75초에서 peer 상자와 겹치는 **벽5개·색상선1개**를 제거했으나, 위치·yaw·σ 변화 최대값은 **0.0**이다. r1/r3의 측정 패킷은 마스크 전후 동일하다. 따라서 이 자료에서 peer 가림을 실패의 주원인으로 주장하지 않는다.

(b) 세 시작은 S2의 북/중앙/남쪽 시작과 모두 거의 같다. 위치가 다르다는 설명만으로 S3 차이를 설명할 수 없다. 시작 위치만 바꾼 새 카메라 영상을 기존 raw에서 만들 수는 없으므로, 가상 렌더/GT 영상을 만들어 인과 재생이라고 부르지 않았다. 같은 위치의 S2 1065/1066/1069 첫 σ 수렴은6.95/10.55/8.45초다.

(c) 모두 reset1.30→startup 종료10.50(9.20초), 첫5 측정2.25/3.75/5.25/6.75/8.25와 검색자세10.10초를 사용한다. 초기 능동 몸체 회전은0회다. S3의 각자 저장된 첫5 시야 패킷을 S2 1065의2030→1500→1770→1230→970 순서로만 바꾼 비교도0/3이다. 이는 기록된 body-frame 측정 패킷의 순서 실험이며 새로운 pan 실행/시야 생성이 아니다. 고정 원본 명령 중 비영 base 명령은0이고 원본 실제 drift는 수mm였다. 관측시간 부족이나 순서만으로 복구된다고 주장하지 않는다.

(d) 지도 SHA `2302d273bcd30a9cc9d3166c753f2d40fcf3f03654369d23cd00324b4ca4688d` 및 floor/zone 지형 geom 속성 전부 동일하다. 동일 바이트 지도 교환은 필터 입력을 바꾸지 않는 항등 비교다. S2 idle freeze/sleep와 S3 3대 활성 차이는 남지만, 새 물리 재생 없이 접촉 영향을 분리했다고 주장하지 않는다. **실제 차이를 확인한 것은 위 카메라 마운트 계약**이다.

## 한 요인 비교와 수정 전/후

모든 수치 기준은 동일하고 아래 공통 비교창은 원본14.00초까지다. 추가로 기준선/마운트 보정은 각846프레임 전체를 끝까지 재생했다. 다른 조건의 성공 횟수를 합산하지 않는다.

| 조건 | 정확 수렴 n/3 | 허위 수렴 로봇 수 | 해석 |
|---|---:|---:|---|
| 기준선 | 0/3 | 1 | r2 σ만 축소, 오차2.06m |
| eval 타 로봇 제외 | 0/3 | 1 | 측정 일부 제거 후 추정값 완전 동일 |
| 첫5 시야 순서만 S2순 | 0/3 | 0 | 오류 해결 아님; σ가 큰 채로 남음 |
| PF seed만1065로 공통화 | 0/3 | 0 | 시드 차이만으로 정확 수렴 회복 안 됨 |
| 색상 랜드마크 점수만 제거 | 0/3 | 0 | σ 2.15/2.24/2.11m; 벽만으로 부족 |
| 다중모드/전체 입자 인증만 ON | 0/3 | 0 | σ·입자·명령 불변, r2 허위 인증 거부 |
| 기록된 마운트로 외부 파라미터만 합성 | 0/3 | 0 | r2/r3 점 추정 개선; 전체 수렴 회복은 아님 |
| 마운트 합성+인증 | 0/3 | 0 | 0/3 유지; false claim 없이 미수렴 처리 |

재표본화만 제거한 SIS 패킷 비교도0/3이며 최종 유효표본수2.49/1.88/2.99였다. 재표본화 제거 자체를 해결책으로 채택하지 않았다. 원본 r2는 첫 입력 시 참 위치 부근 입자25개/100000개(질량0.025%)에서 가중치 갱신 후0.0078%로 줄고 다음 관측 전0개가 된다. 첫 관측에서 최고 잘못된 가설의 센서 점수는 실제 자세 점수의7291.8배다. 최초 색상선4개 중 지도 대응 오차는0.074/1.869/2.783/2.096m이며, 작은 σ는 올바른 가설을 보존했다는 증거가 아니었다. 이것은 평가용 원인 크기 측정이며 GT 좌표를 필터에 주입하지 않았다.

## 구현과 남은 경계

- `carry_yaw_fallback=None`의 기록은 빈 통계로 처리하며 기존 통계를 보존한다. 전체 호스트 재생으로 runtime/trial 두 JSON의 직렬화 오류0을 확인했다.
- 심판 z는 평가 전용 MuJoCo `xipos`(세계 COM)를 사용한다. beam 원점은 바닥에 있고 COM 오프셋은16mm다. 음수/비유한 COM은 계속 거부한다. 원본 roll/pitch가 없어 과거906개 심판 표본을 임의 상수로 변환하거나 HOST_ERROR를 소급 성공 처리하지 않았다.
- `sim.s3_camera_binding.attach(camera_binding="v3_persistent_v1")`: S2의 검증된 바인딩을3대에 재사용하며 기본 off. 실제 legacy configure/sync 메서드의 반복 호출에도 v3 마운트가 유지되는 회귀를 fake model로 검사했다(물리 step0).
- `recorded_camera_mount="legacy_centered_replay_v1"`: 과거 legacy 마운트 영상의 오프라인 재생 전용, 기본 off. 앞으로 v3 렌더를 고정한 물리 실행에서는 켜지 않는다.
- `localization_certification="posterior_consensus_v1"`: 기존 σ/5° yaw 조건 + 기존 Nav2 전체 입자0.5m 범위 검사 + 연결모드1개. 기본 off, 판정 기록 전용이며 DEV 제어/분포/명령을 바꾸지 않는다. 원본 r2는 σ0.028m이나 연결모드2개여서 거부된다. S2 1065의6.95초 정확 수렴 인증은 유지된다.
- 새 물리 옵션은 이 오프라인 작업에서 기존 v142 실행 번들에 재등록하지 않았다. 다음 실행에는 새 번호/출처/카메라·COM 계약을 명시한 번들이 필요하며, 원본 v142 단일 시행의 봉인은 유지한다.

**다음 물리 실행 제안:** 감독이 새 번들을 승인한 뒤 v3 persistent binding·프레임별 eval 카메라/관절/segmentation 기록·다중모드 인증을 켠 3대 스모크1회로 남은 r1 반대-yaw 모드를 확인한다. 이 작업에서는 실행하지 않는다.

## 재현과 참고 자료

`replay_inputs.py`는 `PYTHONPATH=<worktree>`와 기존 Python 환경에서 `--raw <원본> --out <새 폴더> --robot r1`처럼 실행한다. `--recorded-mount --certify`는 새 옵션을, `--packets <peer-mask-r2.json 또는 order-r2.json>`은 오프라인 요인 비교를 선택한다. 출력 폴더가 존재하면 거절한다. `visibility.py`, `peer_mask.py`, `analyze.py`, `importance_replay.py`, `report.py`는 원본 파생 폴더 안에서 실행하는 이 단일 감사의 스크립트이며 실험 드라이버가 아니다. Git 복사본의 `__file__` 기준 경로를 유지하려면 위 `outputs/s3diag-20261009` 폴더에 두고 실행한다. 순서 비교용 `order-r*.json`도 보존했다. `host_replay.py`는 전체3356명령 일치와 직렬화를 확인한다. 파생 raw를 GitHub에 전부 백업했다는 뜻은 아니다.

- [OpenCV 좌표계/강체 변환](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html): 기존 마운트를 분리하고 기록 마운트를 합성하는 표준 변환을 사용, K/D와 문턱 변경 없음.
- [Nav2 pf.c](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c): `pf_update_converged`는 모든 입자의 평균 주위 공간 범위를 검사한다. 프로젝트의 기존 구현/상수0.5m를 그대로 재사용했다.
- [Doucet/Johansen SMC 튜토리얼](https://www.stats.ox.ac.uk/~doucet/doucet_johansen_tutorialPF.pdf): 가중치 퇴화와 재표본화의 입자 중복을 구분한다. 재표본화 삭제만으로 문제가 해결된다고 가정하지 않았다.
- [Fox/Burgard/Thrun 1999](https://arxiv.org/abs/1106.0222), [AAAI98 동적 환경 연구](https://www.ri.cmu.edu/pub_files/pub1/fox_dieter_1998_3/fox_dieter_1998_3.pdf): 동적 장애물 관측 거부의 표준 근거. 이번 마스크 비교가 실패를 복구하지 못했으므로 distance filter를 원인 해결책으로 추가하지 않았다.
- [MuJoCo xipos](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html#mjdata): 평가 높이의 COM 기준.

원본 대표 [4배속 영상](/Users/changmin/projects/ugrp/outputs/s3-v142-recovery-6c657124-20261009/s14201-mixed-4x/execution.mp4)은 그대로 보존한다. 이 진단을 위한 새 물리 영상은 없다.


## TensorBoard

새 스냅샷 `outputs/tensorboard/1009-s3diag-v2`에 오프라인 비교8개를 등록하고 **80개 scalar를 EventAccumulator로 원본과 대조**했다. 첫 export의 schema 누락은 실패 manifest로 보존하고 수정된 새 스냅샷을 사용했다. 기존 서버 PID52016·공용 logdir를 유지하고 `tensorboard-view.json`의 자기 키 `s3diag_offline_20261009`만 추가했다. 시뮬레이션 실행 시간과 오프라인 처리 시간을 섞지 않았다. 대표 영상은 이전 등록본을 재사용한다.

[고정 카드 대시보드](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22evaluation%2Freported_success%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcorrect_convergence_n%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Ffalse_convergence_n%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fr2%2Fxy_error_m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fr3%2Fxy_error_m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fphysical_runs%22%7D%5D&smoothing=0&runFilter=%5E1009-s3diag-v2%2F#timeseries)에서 비교8개 선택·고정6카드와 실제 값(정확 수렴0, 기준선 허위1/수정0)을 확인했다. HParams는 공용 metadata가 지원하는 `case/family/outcome/evaluation/reported_success` 열로 맞췄고, 사용자 정의 오프라인 지표는 Time Series에 표시한다. 화면 증거는 `outputs/s3diag-20261009/tensorboard-ui.jpg`에 보존했다.
