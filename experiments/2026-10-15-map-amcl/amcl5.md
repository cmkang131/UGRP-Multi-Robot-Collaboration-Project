# AMCL 기록 5차 — 실제 기록 제어기 프로파일과 계산 최적화

기준 `1aa3589a3cacde763fe59d05d6ac151c8b7f84c8`, `claude/map-amcl`, PR #507. 저장 입력 계산만 수행했다. 새 물리 실행·카메라 렌더·원격 호스트 접속·모델 호출은 0이다. **not-ready**다. 결과 보존 최적화와 정확도 검증은 완료했지만, Mac 부하 급증으로 반복 속도 비교를 완료하지 못했다. 유효 첫30 예측값은null이며 새 대기열은 생성하지 않았다.

## 입력과 재현

- 원본: `/Users/changmin/projects/ugrp/outputs/gcp1-runs/map-amcl-record-b2387ac1/recordings/map-amcl-record-s65101/raw`. r1/r2 각각 `[0,30]`의 301 JPEG, 합계602장을 모두 해시 검사한다. 프레임 제외·재구성·정답 입력은 없다.
- 사용자가 알린 원격 회수 647/647과 별개로 이번 로컬 검사는 `SHA256SUMS.tsv`의643개 항목 모두 일치, JPEG602/602 일치다. 원본 `artifacts.sha256.json`의636개 항목도 압축 해제 내용을 포함해636/636 일치했다. 현재 폴더에는 이전 lite 회수본·압축 해제 사본도 있어 전체 파일 수와 이 목록의 분모를 혼동하지 않는다.
- 재생기는 발행 원장의 초기 서보5개·0.2초 명령 주기를 확인하고, 매 프레임 새로 계산한 명령을 저장 명령과 비교한 **뒤에** 저장 발행 명령을 적용한다. 마지막 정리용hold는 제어 피드백에서 제외한다. 전체 제안 명령602/602, 실제 발행 시점300/300 일치다.
- 실제 기록기는 `Robot → GoalRoute`다. `map_amcl` 필터를 대신 측정하지 않았다. 기존 재생에 누락됐던 `PhysicsBackend.reset`의 `controller_exact_speedups` 초기화를 물리 객체 없이 복원했다. 원본의 applied/fallback·scan·visibility 설정과 일치해야 실행한다.
- Mac과 GCP의 전체 추정 원장은 부동소수점 차이 때문에 비트 동일하지 않다. 최적화 전후 동일성은 같은 Mac에서 canonical JSON 원장 전체와 pose·명령을 각각 비교한다.
- 두 로봇 제어가 모두 끝난 뒤에만 평가 궤적을 읽는다. 이 제어기의 좌표는 자기 시작점 기준이므로 GT의 최초 SE(2)로 평가 좌표계만 고정한다. 전체 경로 최적 정합으로 절대 오차를 가리지 않으며 median/p95에는 미수렴·실패·정지 프레임도 포함한다.

## 함수별 누적 시간 상위20

원본 방식(`legacy`, amcl3 이전 사각형 계산)과 기록 당시 공통exact-v1 초기화를 재현한 cProfile 결과다. 두 로봇 합계263.730초이며 프로파일러를 끈 속도 측정과 구분한다. 누적 시간은 부모·자식이 겹치므로 더하지 않는다.

| 함수 | 호출 수 | 누적초 | 자체초 |
|---|---:|---:|---:|
| `map_recording_audit.py:89 receive` | 602 | 263.690 | 0.004 |
| `e2e_live_mapping.py:106 receive` | 602 | 263.686 | 0.004 |
| `e2e_live_mapping.py:110 _receive` | 602 | 263.673 | 0.056 |
| `e2e_explore_deadlock.py:111 received` | 602 | 250.077 | 0.003 |
| `e2e_rgb_vo.py:465 received` | 602 | 250.071 | 0.016 |
| `e2e_boundary_association.py:89 received` | 602 | 238.197 | 0.001 |
| `e2e_boundary_views.py:285 with_diagnostics` | 602 | 238.195 | 0.003 |
| `e2e_exploration.py:135 receive_progress` | 602 | 238.190 | 0.002 |
| `ego_pose_continuity.py:274 receive_pose` | 602 | 238.188 | 0.009 |
| `e2e_setdown_relook.py:97 receive_rgb` | 602 | 237.697 | 0.011 |
| `grid_acceleration.py:105 receive` | 602 | 233.644 | 0.004 |
| `e2e_goal_route.py:66 receive` | 602 | 233.634 | 0.018 |
| `goal_route_continuous.py:246 receive` | 602 | 231.082 | 0.046 |
| `e2e_boundary_association.py:86 observed` | 602 | 101.943 | 0.002 |
| `e2e_goal_route.py:80 own_rgb_received` | 602 | 101.941 | 0.004 |
| `e2e_rgb_gate.py:203 observe` | 602 | 101.839 | 0.022 |
| `active_wall_recovery.py:143 receive` | 602 | 98.165 | 0.028 |
| `e2e_rgb_gate.py:110 boundary` | 1,204 | 92.348 | 0.058 |
| `e2e_b_partial.py:185 detect_partial` | 602 | 84.543 | 0.041 |
| `e2e_b_partial.py:67 estimate` | 247 | 77.125 | 3.015 |

r1은183.145초(69.4%), r2는80.586초(30.6%)다. 프레임별 원본은 각 실행의 `r1-timing.jsonl`·`r2-timing.jsonl`에 있고, 분포·로봇별 상위20은 `amcl5-baseline-profile.json`에 있다.

| 로봇 | 프레임 수 | median초 | p95초 | 최대초 |
|---|---:|---:|---:|---:|
| r1 | 301 | 0.620253 | 0.796345 | 5.693417 |
| r2 | 301 | 0.212737 | 0.286216 | 7.545899 |

B 경계 전체101.839초 중 partial 검출84.543초, coarse rectangle fit77.125초였다. 격자 셀 변환은11,706,008회/23.005초, 차체 마스크 투영20.717초, `from_observed_grid`1,204회/12.072초다. 경로 보정 후 기존 관측의 ray 재삽입도 포함되며, 이 중첩 시간을 총시간으로 합산하지 않는다.

## 변경 구분

- `exact_v1`: 이미 있는 `e2e_exact_speedups.Options`의 고정된 10개 옵션을 기록 로봇 인스턴스에 적용한다. 같은 영상의 벽 검출 공유, 입력 비트 기반 차체 마스크 캐시, 벡터 ray/cell·costmap 쓰기, 검사 경로의 불필요한 사본·문자열 계산을 재사용한다. 기존 rectangle_batch 64도 유지한다. 전체 602행 canonical JSON과 명령·pose가 기준과 같다. 기록 전용 spec은 이 결과 보존 프로필을 선택하며, 공용Robot 기본은 바꾸지 않는다.
- `squared_v1`: 위exact 옵션에 기존 `e2e_speed5.rectangle_grid_cost`의 float64 제곱거리 계산을128후보씩 연결한다. hypot로 거리를 구한 뒤 다시 제곱하던 계산을 합치고 큰 임시 배열을 제한한다.300개 내부점·최대 80개 경계점·1,681개 중심×24개 방향·임계값·least-squares refinement는 유지한다. 기존 lean 프로필의 80개 내부점 축소는 적용하지 않는다. 산술 순서가 달라 **기본off, 기록spec 미채택**이다.
- 640×480/FOV/보정·10Hz 영상·5Hz 발행·입자·VO·정답 경계는 그대로다. 다운샘플·관측 생략·명령 기반 미세 구동 보정은 이번 패치에 넣지 않았다.

## 시간 예측과 판정

기존GCP 첫30의98.810100초(물리·카메라·평가)를 유지하고, 나머지386.682117초에 Mac 전체30초 제어 재생 절감률을 적용한다. 이 비율의 호스트 간 이전은 가정이다. 잔여에 포함된 미계측 기록I/O를0으로 두고 모두 줄인 값은 **낙관적 조건부 예측**이며 실제 속도 관문 통과가 아니다. 미계측 잔여 중H초를 그대로 남기는 민감도는 `(98.810100 + H + (386.682117-H)×비율)/30`이다.

프로파일러를 끈 완료 측정은 다음과 같다. 각 값은 전체 602프레임을 한 번 재생한 값이며, 독립 반복이 아니다. `legacy`와 현행 1aa의 `batch`에 대한 비프로파일 반복 기준값은 확보하지 못했으므로, 아래 값으로 amcl5의 전체 절감률이나 GCP 예상 속도를 확정하지 않는다.

| 후보 | 제어합계초 | r1초 | r2초 | 전체재생wall초 | 전체CPU초 |
|---|---:|---:|---:|---:|---:|
| exact_v1 | 133.464854 | 99.153187 | 34.311667 | 134.332722 | 141.607873 |
| squared_v1 | 95.728567 | 61.288753 | 34.439813 | 96.548861 | 103.945679 |

`exact_v1` 프레임median/p95는 r1 0.374686/0.435159초, r2 0.096858/0.169614초다. `squared_v1`은 r1 0.211951/0.268433초, r2 0.100228/0.162588초다. 두 후보 측정의 1분 부하는 약 2.6–4.2였다.

이후 `legacy` 비프로파일 기준 재생 중 1분 부하가 129→140으로 올랐고, 마지막 확인 progress는 tick100/wall114.316초였다. 자신의 재생만 SIGINT로 중단했다. 관련 시험 완료 뒤 새 디렉터리에서 다시 시도했으나, 부하 207, 첫 프레임 progress 275.357에서 다시 중단했다. 다른 프로세스에는 신호를 보내지 않았다. 두 중단은 `INTERRUPTED.json`과summary에 보존하고 완료 분모에서 제외한다. 최초 짧은 입력 검사와 runtime 초기화 누락 프로파일도 검증·예측의 정식 기준에서 제외했다.

따라서 `predicted_wall_per_sim=null`, `actual_speed_verified=false`, 모든 ready/실행 권한 false다. **amcl5 신규 큐 파일 0개**이며 기존 큐는 수정하지 않았다. `project_first30`은 최소 2회씩의 완전한 비프로파일 재생·같은 입력·원본 명령 일치가 없으면 계산을 거부한다. cProfile 시간은 속도 예측의 분모로 쓰지 않는다.

정확도는 두 후보 모두 r1/r2 위치median·p95, 방향median·p95 증가가정확히0이었다. 허용상한은 위치+0.02/+0.05m, 방향+2/+5°다. 기본 상태의 시작 좌표계 절대오차는 r1 위치median0.093535m/p95 0.106713m·방향5.104061°/6.688396°, r2 0.351964m/0.510631m·0.878194°/9.328101°다. 비열화는 절대 위치 추정의 합격을 뜻하지 않는다.

`squared_v1`의 pose·명령은 602/602 일치하고, 원장 전체는 r1 68/301·r2 294/301 일치했다. 차이는 `boundary_diagnostics`의 부동소수점 값이다. 따라서 결과 보존 최적화로 분류하지 않는다.

남은 측정·수정 방향은 다음과 같다.

1. 같은 부하에서 legacy/batch/후보의 전체 재생을 반복하고 첫30 예측을 계산한다.
2. 후보 자체를 다시 프로파일해 r2의 34.44초 잔여를 분리한다. B 제곱거리 최적화만으로 r2 비용은 줄지 않았다.
3. 같은 프레임의 dense/costmap 중복 생성과 pose-graph 보정 뒤 전체 ray 재삽입을 revision/content 검증이 있는 증분 갱신으로 검토한다.
4. 움직임/keyframe 관문을 추가한다면 기본 off로 분리한다. 오래된 경계 검출을 새 관측으로 재사용하지 않고 같은 정확도 허용치를 다시 검사한다.

## 검증과 재실행

관련 3파일 **93 passed**, 종료코드0(417.34초)다. 시험은 숫자·합성 비트맵·모의 backend만 쓴다. 전체 저장 원장 동일성과 실제 새 주행은 별도다. 원본·소스·산출물·시험 로그 SHA는 `amcl5-validation.json`, 모든 실행과 실패·시드 분모는 `amcl5-summary.json`에 있다.

```sh
MPLCONFIGDIR=/private/tmp/ugrp-amcl5-mpl /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.profile_map_recording \
  --raw /Users/changmin/projects/ugrp/outputs/gcp1-runs/map-amcl-record-b2387ac1/recordings/map-amcl-record-s65101/raw \
  --output /Users/changmin/projects/ugrp/outputs/map-amcl5/NEW-UNIQUE-DIRECTORY \
  --mode legacy
```

`--mode batch`는 1aa의 사각형 블록만 켠 기준, `exact_v1`과`squared_v1`은 후보다. `--profile`을 붙이면 함수별·로봇별 상위 20을 기록하며 속도 예측에서는 제외한다. 출력 디렉터리가 존재하면 덮어쓰지 않는다. 모든 301프레임/로봇을 끝내기 전의 값은 완료 측정이 아니다.

## 의존성과 미확인 범위

- 구동 데드밴드: `claude/drive-model-deadband`, 이번 확인 ref `01703ed2790dadad666e53d1b276b97f2b510bda`, 사용자 통보 토글 `drive_model_deadband_v1`. 중복 구현·병합 없음.
- 바닥·벽 질감: `claude/scene-floor-texture`, 이번 로컬 ref `328b4e1d2a4abe245620a58b35ea96ddc1450ef1`. 사용자 허용 프로필 작업이며 이번 데이터에 소급 적용하지 않는다.
- 두 의존성은 향후 명령 전파·영상 분포를 바꿀 수 있어 새 번들에서 기록 속도·정확도를 다시 확인해야 한다. 현재 색·텍스처 자료의 성능을 해당 프로필로 일반화하지 않는다.
- 과거 65101은 HOST_ERROR/전체 60초 미완료로 보존한다. 새 65102–65141은 40회/80구간 모두 미제출이다. 실제 첫 기록 1개→전체 601장·속도·정확도·감사 확인→후속 39개 순서와 승인 false 원칙을 유지한다.

## 참고 자료

- [Python cProfile/pstats 공식 문서](https://docs.python.org/3.12/library/profile.html): 누적/자체 시간과 profiling 오버헤드. 병목 식별과 benchmark를 분리했다.
- [NumPy broadcasting 공식 문서](https://numpy.org/doc/stable/user/basics.broadcasting.html): 배열 벡터화와 큰 broadcast 임시 배열의 메모리 비용. 64/128행 블록과 기존 벡터 커널을 사용했다.
- 기존 공개 코드 연결은 `harness/e2e_exact_speedups2.py`, `harness/controller_exact_speedups.py`, `harness/e2e_speed5.py`를 재사용한다. 새로 가져온 알고리즘이나 패키지 의존성은 없다. 상세 열람·사용 범위는 `amcl5-references.json`이다.
