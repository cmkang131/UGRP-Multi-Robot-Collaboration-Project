# v92 D5 측정 보정 조립 (2026-10-03) — 결과: PARTIAL

방금 끝난 v92 높은 운반 자세(HIGH) 하중(loaded) 수집과 v88 무하중(unloaded)·미세 이동(fine, r6) 수집을 v92 전용 조립기(assembler)로 한 번 조립했다. 목표 상태는 `MEASURED_SIM`이었다. 결과는 **`PARTIAL`(rc=2)**이며 **필수 항목 31개가 비어 있다**. 기준 B″·임계값·적합 설정은 바꾸지 않았고 조립기는 한 번만 실행했다. 이 기록은 오프라인 보정 결과이며 학생 실행·P03·운반 임무 성공이 아니다.

## 입력과 실행 소스

| 항목 | 값 |
|---|---|
| 실행 소스 | `257953ec36353c37acc61c4cb86563db7c937de2` (PR #361 수집 소스). 깨끗한 분리 HEAD(detached), `working_tree_dirty=false` |
| 고정 해시 대조 | [#219 수집 전 고정 코멘트](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5967154276)의 7개 파일(조립기 `a61ac39d…`, io `18bfc0c4…`, motion `20532aec…`, camera `d66cc6eb…`, 계약 `164f3212…`, B″ `5f7d8905…`, 일정 `47b0e1f3…`)이 실행 전 작업 트리와 조립기가 실제로 읽은 입력 명세(input manifest)에서 **모두 같은 바이트**였다 ([result_summary.json](result_summary.json)의 `pinned_hash_check`) |
| v92 loaded | `outputs/final-pair-v92-loaded-257953ec-20261003` (720 SIM초, `protocol_complete=true`, 로봇당 3,601프레임, 발행 명령 22,302개, 모델 호출 0) |
| v88 unloaded | `outputs/final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded` |
| v88 fine (r6) | `outputs/final-pair-v88-cal-747d2b9f-20261001-r6/calibration-fine` |
| 선택 근거(결과에 영향 없음) | #361 README의 문서화된 호출대로 r5 회전 후보(`978727fc…`, 조립기 내부 고정 해시와 일치)와 v91 기준 B 채점 JSON 2개(1차 `e58e6457…`, 2차 `8e452f25…`)를 넣었다. 조립기는 이 JSON만 읽고, 무하중 통합 프로필 승인 근거로 쓰지 않는다(`axis_candidates_qualify_full_profile=false`). v91 held-out 원본은 읽지 않았다 |

v88 경로는 심볼릭 링크 묶음(`…-assembly-links`)이 아니라 실제 폴더를 넣었다. v92 조립기는 세 경로를 따로 받고 별칭을 스스로 해석한다. 실행 명령은 [assembly_command.sh](assembly_command.sh)에 있다.

**#358 주의 사항은 이번 실행에 해당하지 않았다.** v92 경로의 `fit_cameras`·`pair_rows`는 처음부터 프레임 시계로 `sim_time`을 읽는다. v88 파일에서 가져오는 함수는 `fit_pair` 하나뿐이고, #358은 이 함수를 바꾸지 않았다. 그래서 main을 병합하지 않고 257953ec 그대로 실행했다. 실행 뒤 #361이 main(`00eafd63`)에 병합됐다. 확인해 보니 고정 파일 7개는 main에서도 같은 바이트였다. #358 때문에 달라진 v88 `final_pair_calibration_io.py`·`final_pair_calibration_camera.py`에서도, v92 경로가 가져오는 `loaded_mask`, `selected_segments`, `file_sha`, `Inputs`, `fit_pair`의 소스는 두 커밋에서 같다. 바뀐 곳은 v92가 쓰지 않는 기존 `load_collection`과 새 보조 함수뿐이다.

사전 검사: 관련 테스트 `tests/test_final_pair_calibration_v92.py`와 `tests/test_final_pair_calibration_assembly.py`가 257953ec에서 **407 passed in 1416.52s**였다 ([pretests_stdout.txt](pretests_stdout.txt)). 다른 작업 때문에 호스트 부하가 높았다(부하 평균 15~31).

## 결과

조립 시간은 09:18:16~09:20:21 UTC(125초)였다. 출력은 `outputs/final-pair-v92-measured-20261003T091812Z/assembly/`에 있고, 모든 파일의 sha256은 [outputs_measured.SHA256SUMS](outputs_measured.SHA256SUMS)에 있다. `calibration.json`(`852426d2…`)의 사본은 [calibration.json](calibration.json)이다. `fit_report.json`(`1b4ff559…`, 0.7 MB)과 `input_manifest.json`(`fee2cea5…`, 4 MB, 입력 14,871개)은 실험 폴더 용량 기준 때문에 outputs에만 두었다.

### 필수 108개 중 77개 측정, 31개 빠짐

257953ec의 `required_fields()` 기준으로 필수 항목은 108개다. 이 중 77개가 측정·수락됐다(fine 운동 10, 팬 2, 카메라 13자세 × 5 하위 항목 = 65). 항목별 표는 [required_fields_257953ec.json](required_fields_257953ec.json)에 있다.

빠진 31개 항목 전체와 이유는 다음과 같다.

| 항목 | 개수 | 조립기가 기록한 이유 |
|---|---|---|
| `params.motion.{gain, tau_s, tau_axis_s, tau_stop_s, noise_rel, noise_abs, scale_std, scale_walk, use_scale, rest_noise}` | 10 | `r4/r5 are axis-only candidates; no accepted complete three-axis/scalar-stop unloaded product. Supplied v91 results do not validate a new combined profile.` |
| `params.motion_loaded.{gain, tau_s, tau_axis_s, tau_stop_s, noise_rel, noise_abs, scale_std, scale_walk, use_scale, rest_noise}`, `params.motion_loaded.load_transition.{scale_std, unloaded_scale_std}`, `params.motion_loaded.deadband.{c0, u1}`, `params.motion_loaded.{drift_ratio_std, yaw_bias_std_rad_s}` | 16 | `motion identification: fit convergence/rank/boundary failure: rank 13/13` |
| `pair_model.slope_to_yaw_ratio`, `pair_model.b_rad_s.{"", pm, edge, pm+edge}` | 5 | `measurement not available` |

### 원인은 두 가지

1. **무하중 운동 프로필 `params.motion.*` 10개: 설계상 미충족.** r4/r5는 축별 후보일 뿐이고, 승인된 세 축 공통 정지 시간상수(scalar stop tau) 통합 프로필이 없다. #361 README가 미리 밝힌 대로 현재 조립기는 이 항목을 항상 PARTIAL로 둔다.
2. **하중 공통 적합(shared fit) 거부: 1건이 21개 항목으로 번졌다.**
   - `params.motion_loaded.*` 16개(평균·잡음·전이·불감대(deadband)·표류(drift)·회전 편향 포함). 적합이 거부되어 퍼짐(spread)과 불감대 지지 검사는 실행되지 않았다.
   - `pair_model.*` 5개. "measurement not available"은 받아들여진 하중 프로필이 없어서 `pair_rows`가 **실행되지 않았다**는 뜻이다. 빔 모서리를 관측할 수 있는지에 대한 판단이 아니다.

조립기 보고서에는 오류 문자열 `fit convergence/rank/boundary failure: rank 13/13`만 남았다. 그래서 **같은 설정 그대로** 하중 경로만 다시 돌리는 진단(diagnostic)을 따로 실행했다([diag_loaded_optimizer.py](diag_loaded_optimizer.py), [diagnostic.json](diagnostic.json)). `verify_fit`을 감싸 최적화 상태만 기록했고 범위·반복 한도·기준은 바꾸지 않았다. 이 진단은 같은 오류 문자열과 같은 선별 수(13,926/475)를 재현했다. **보정 결과가 아니다.**

- 최적화는 수렴했다(`ftol` 조건 충족, success, 평가 11회, 계수 13/13, RMSE 0.00189).
- **세 축의 불감대 시작값(c0)이 모두 탐색 하한에 붙었다.** 전진 0, 옆 0, 회전 0.006이다. `verify_fit`은 경계에 닿은 해(`active_mask≠0`)를 거부한다.
  - **전진·옆:** B″는 c0 하한을 이미 0까지 낮췄는데도 해가 0에 붙었다. 이 두 축에서는 하중 HIGH 자료가 **양수 정지 수준을 지지하지 않는다**. 더 낮출 하한도 없다.
  - **회전:** 하한은 고정값 0.006 그대로였다. 적합은 **0.006보다 작은 값을 원한다**는 것까지만 알 수 있다. 그 값이 양수인지 0인지는 이번 고정 규칙으로는 판단할 수 없다.
- 나머지 값은 내부해였다(진단 전용, 승인 아님): 이득(gain) 1.355/0.964/0.907, 축 시간상수 0.966/0.968/0.656 s, 공통 정지 시간상수 0.0852 s, u1 0.0266/0.0282/0.0297.

### 실제로 평가된 B″/B′ 검사

| 검사 | 결과 |
|---|---|
| fine B′ 운동 프로필 | **통과**. 훈련 18/18, PRBS 검증 18/18 행 통과. 이득 대각 1.234/0.847/1.058, tau 0.859 s, 축 tau 0.859/0.855/0.163 s, 정지 tau 0.0697 s, 계수 7, RMSE 0.0050 |
| unloaded 카메라 25개 자세 | **모두 통과**. 광학 원점 잔차 최대 9.8e-6 m, 회전 최대 0.0042°. 기준은 1 mm, 0.1° |
| loaded HIGH 카메라 3개 자세 (`896,2035,1894` × 팬 1480/1500/1520) | **모두 통과**. 원점 잔차 최대 3.0e-6 m, 회전 최대 0.0015°, 프레임 80/400/80. 8초 준비 + 8초 측정 창 |
| 팬-차체 회전(pan_base_yaw) | unloaded **통과**(1.5e-8 rad/PWM, 사실상 0, p95 0.0038°), loaded **통과**(−0.00118 rad/PWM, p95 0.0068°) |
| loaded 선별(B″ loaded_selection) | 상승·네 집게 접촉 표본 13,926 / 비상승 475 (전체 14,401) |
| loaded B″ 훈련·검증 수치 판정, 퍼짐, 불감대 지지, 쌍 모델 | **평가되지 않음**. 공통 적합 거부로 실행되지 않았고, 0으로 기록하지 않았다 |

## TensorBoard

기준 스냅샷은 **`outputs/tensorboard/1003-v92-measured-r2`**이고 실행(run)은 4개다. `v92-collection`(수집 요약·영상 경로), `v92-assembly`(상태, 필수 108·측정 77·빠짐 31), `v92-fit-gates`(실제 평가된 검사만), `v92-loaded-diag`(진단 전용)이다. 생성기는 [gen_tb_views.py](gen_tb_views.py), 파생 뷰는 [tb_views_r2/](tb_views_r2/)에 있다. 처음 만든 `1003-v92-measured`([tb_views/](tb_views/))에는 필수·측정 항목 수가 없어서 대체됐다. 변환기가 기존 스냅샷에 덧붙이지 않으므로 새 ID로 다시 변환했고, 첫 스냅샷은 지우지 않았다. 기존 뷰어 `tb-calib-v91`(PID 54924, logdir `outputs/tensorboard`)은 재시작하지 않았다. HTTP API로 r2의 4개 실행과 37개 스칼라를 원본과 대조해 **불일치 0**을 확인했다([tensorboard_api_values.json](tensorboard_api_values.json)). 고정 링크에서 4개 실행과 12개 고정 카드가 열리는 것도 확인했다. `outputs/tensorboard-view.json`에는 자기 키 `v92_measured_assembly_20261003`만 추가·수정했다.

제약: 공용 logdir의 HParams 표는 기존 9개 열과 14개 지표만 보여준다. 새 실행은 세션 그룹에 있지만 새 지표는 열로 나오지 않으므로 Time Series 고정 카드로 본다. 오프라인 감사 변환기는 영상 등록을 지원하지 않는다. 그래서 영상 경로와 해시는 `v92-collection`의 `media/videos` 텍스트 카드에 적었다.

## 대표 영상

`outputs/v92-loaded-videos-20261003/`에 두 영상이 있다. 해시는 [videos.SHA256SUMS](videos.SHA256SUMS)에 있다.

- `v92_loaded_own_rgb_r1_r2_4x.mp4`(`f7afad40…`): r1|r2 자기 카메라 RGB(5 Hz, 각 3,601장)를 나란히 놓고 20 fps(4배속)로 만들었다. 180초, 다시 렌더링하거나 덧씌운 것이 없다.
- `v92_loaded_top_REPLAY_of_recorded_poses_4x.mp4`(`494b463f…`): `eval_only/trajectory.jsonl` qpos를 4행마다 `mj_forward`로 다시 그린 **기록 자세 재생(replay)**이다. 물리 재실행도 로봇 입력도 아니다. 차체 free joint 주소는 장면 XML의 이름으로 찾았다(r1=0, r2=17). 스크립트는 [topview_replay.py](topview_replay.py)다.

## 결정이 필요한 것

- #219 고정 문구에 따라 결과를 본 뒤 B″를 바꾸지 않는다. 하중 c0 하한·경계 판정·적합 범위를 바꾸면 이번 v92 자료는 그 새 규칙에 대해 **탐색 자료**가 된다. 승격하려면 새로 고정한 규칙 아래에서 새 수집이 필요하다. 선택지는 축마다 다르다. 회전은 하한을 0.006 아래로 내리면 내부해가 나올 수도 있다. 전진·옆은 이미 0에 붙었으므로 하한을 더 내릴 수 없고, "정지 구간 없음(c0=0)을 허용하는 모델" 같은 다른 규칙이 필요하다.
- 무하중 통합 프로필 미승인은 이와 **별개인** 두 번째 차단 요인이다.

## 참고 자료

- [#219 D1–D5 결정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5966171204), [수집 전 해시 고정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/219#issuecomment-5967154276)
- [PR #361 v92 HIGH 수집·B″·전용 조립기](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/361), 조립기 README `experiments/2026-10-03-v92-loaded-schedule/assembly/README.md` (257953ec)
- [PR #358 프레임 시계 `sim_time`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/358), [PR #360 r5 회전 후보](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/360), [PR #356 v91 기준 B 채점](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/356)
- [SciPy `least_squares`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html): `status=2`는 `ftol` 종료, `active_mask≠0`은 경계 제약 활성을 뜻한다
- [docs/tensorboard.md](../../docs/tensorboard.md) 오프라인 감사 파생 뷰 절차, 영상 재생 패턴 `outputs/v91-heldout-videos-20261003/topview_replay.py`
