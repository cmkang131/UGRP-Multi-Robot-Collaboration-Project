# s3fix13 — 양자화 한계와 정착 후 시각 정렬 (2026-10-10)

## 실행 전 고정

host=oracle-x86 / OSMesa / MuJoCo3.12.0, 최대10개 동시, 각60 SIM초/dev_light.
Mac에서는 편집·관련 pytest만, 물리/렌더/저장 제어 재생0. CI 대기·병합 없음.
main과 열린11PR 원격의 최댓값v158/7.51.0을 확인하고 v159/7.52.0을 예약했다.
기존 baseline7a4bda7a·보정259f17e1 원본과 기각 trim 모델을 그대로 보존한다.
이번 후보는 기각 모델을 사용하지 않고 기존 승인된 pulse profile/port만 사용한다.

## 수치와 양자화 한계

정렬 성공 허용치는 기존 x/y 각각±3mm, pair yaw±.035rad(±2.005°) 그대로다.
이는 오차 0 주위의 반폭이며, 고정 스텝의 보장 가능성은 전체 폭6mm/.07rad와 비교한다.
한 스텝이 반폭보다 크다는 사실만으로 모든 초기 조건에서 진동한다고 단정할 수 없지만,
전체 폭보다 큰 고정 스텝에는 그 구간에 도달할 수 없는 초기 나머지 오차가 존재한다.
따라서 P gain만 조절해 모든 조건의 정확 정렬을 보장할 수 없다.

|pulse|실제/보정 응답|허용 반폭 대비|제어 사용 범위|
|---|---:|---:|---|
|기존 turn +35/.10s|중앙값.101978rad, 범위.082933–.123743rad(n839)|2.91배|현재 합법|
|기존 turn -35/.10s|절댓값 중앙값.103288rad, 범위.083159–.123657rad(n838)|2.95배|현재 합법|
|기존 forward ±35/.10s|중앙값12.2246/12.4387mm(n30/9)|4.07/4.15배|현재 합법|
|기존 left ±35/.06s|6.918/7.323mm(기존 보정)|2.31/2.44배|.10s 최소 계약 위반으로 사용 안 함|
|기존 left ±65/.65s|168.504/167.856mm(기존 보정)|56.17/55.95배|합법이나 최종10cm 오차에는 맞지 않음|
|기각 trim left ±35/.10s|11.494/11.295mm(x86 보정)|3.83/3.76배|진단 표 전용, 이번 제어에 사용 안 함|

[원본 프레임의 명령별 실제 응답과 run 시간 분해](quantization.json).
GT는 위 사후 측정에만 사용한다. selector는 실행 시 자기 RGB 오차와 기존 보정 profile만 읽는다.
새 정렬 후보의 실제 성공률을 아직 주장하지 않는다. 최소 펄스 미만 잔여 오차는
정렬 성공으로 통과시키지 않고 `below_calibrated_resolution` hold로 기록한다.

## 표준 방법과 옵션 (결과 보기 전 고정)

각 bool 토글의 기본값은 False이며 전부 off면 기존 함수/명령/기록 경로를 그대로 반환한다.
새 입력·목표 추정·PF·카메라·모터 최소 출력·최소 명령 시간을 바꾸지 않는다.

- `deadband_hysteresis`: 축별 정지 진입은 기존3mm/.035rad, 제어 재개는1.5배인4.5mm/.0525rad. 성공 판정은 원래 엄격한 문턱·서로 다른 연속 RGB 프레임을 유지한다. 제어 latch가 grasp receipt를 만들지 않는다.
- `move_settle_look`: 발행 펄스의 끝과 보정 coast 이후까지 기다리며 최소.50s의 정착 창을 둔다. 그 시각 이후 촬영된 다른 자기 frame_id여야 다음 결정을 허용한다. native motor expiry는 그대로이며, 속도/GT 정착 판정은 입력하지 않는다.
- `proportional_pulse`: gain1의 요청 길이 `|오차|/(기존 응답/기존 duration)`를 계산해 그 이하의 기존 보정 길이로 내림 선택한다. 가능한 최소 길이보다 작으면 명령을 내지 않는다. 없는 길이를 늘리거나 보간 보정을 만들지 않는다. 현재 합법 vocabulary가 축/부호별 사실상 한 길이이므로 이 토글은 주로 미세 오차에서 명령 생략으로 작동한다.
- `separate_axes`: pair는 물체 yaw를 먼저 맞추고 그다음 전후/좌우 중 정규화 오차가 큰 축, cyan은 전후/좌우만. 집게 오차의 bearing을 매번 목표 yaw로 삼지 않는다. 한 명령 한 축 계약을 유지한다. 최종0.10m 밖은 기존 heading, 공동 빔운반 예외는 그대로다.

네 옵션을 모두 on으로 아래10개 전체를 한 번에 제출한다. 같은 라운드 중 재튜닝/추가 seed/조건 변경 없음.
옵션별 분리는 회귀에서 확인하며 이번 물리 묶음은 전체 방법 대 기존 baseline의 개발 비교다.
채택은 원래 문턱 도달·hover/하강/닫기·접촉 상승 증가와 기존 cyan c0 실패 증가 없음으로 판단한다.
회전 반전만 줄고 문턱 미도달이면 성공으로 채택하지 않는다. beam 상승은 별도 평가 전용 접촉/COM 기록으로 판정한다.

## 고정 실행 목록

[batch-plan.json](batch-plan.json)이 기계가 읽는 전체 목록이다. pair6개 + 실패 cyan c3/c5 + 이전 HOST_ERROR c4 + 기존 성공 c0 회귀1개, 총10개.
seed14201+C, 이전과 동일 자기 차체 오프셋6개:
`(0,0,0),(.012,0,0),(-.012,0,0),(0,.012,0),(0,-.012,.04),(0,0,-.04)`.
시작 위치는 eval-only 장면 구성이고 학생은 새 자기 RGB 전역 PF를 유지한다. dock prior/GT제어/topRGB/weld 없음.

|이름|case|C|seed|
|---|---|---:|---:|
|s3fix13-pair-c0-r1|pair|0|14201|
|s3fix13-pair-c1-r1|pair|1|14202|
|s3fix13-pair-c2-r1|pair|2|14203|
|s3fix13-pair-c3-r1|pair|3|14204|
|s3fix13-pair-c4-r1|pair|4|14205|
|s3fix13-pair-c5-r1|pair|5|14206|
|s3fix13-cyan-c0-r1|cyan|0|14201|
|s3fix13-cyan-c3-r1|cyan|3|14204|
|s3fix13-cyan-c4-r1|cyan|4|14205|
|s3fix13-cyan-c5-r1|cyan|5|14206|

각 child 명령은 다음과 같고 SHA는 실행 전 commit/push한 하나의 소스로 고정한다.

```sh
python -m scripts.run_s3_settled_probe --expected-source-sha "$SHA" \
 --output "outputs/$NAME/raw" --case "$CASE" --condition "$C" \
 --deadband-hysteresis --move-settle-look --proportional-pulse --separate-axes --execute
```

실제 전체 전송은 `ORACLE_HOST=oracle-x86 oracle_run.sh "$WT" s3fix13-batch-r1 -- .venv-sim/bin/python -m scripts.run_s3_settled_cohort --expected-source-sha "$SHA" --output outputs/s3fix13-batch-r1/cohort --execute`.
경로 확인은 코드/시험 완료 뒤 딱1회 `s3fix13-pathcheck-r1`, pair/C0/seed14201/동일 네 flags에 `--path-check`를 추가한다.
5SIM초(초기화 포함7.35), 본10개에 합산하지 않는다. 경로 오류만 있으면 수정 후 다시≤10초1회.
모든 실행 종료 뒤 raw 전체를 한꺼번에 평가하고 수정도 한 묶음으로 한다. 한 시간 진전 없으면 중단·보고한다.

## 시간 분해 (최적화 없음)

기준 pair c0 wall335.773초: 3대 RGB3600렌더98.238초(29.3%), capture전체108.021초(32.2%), 물리진행95.357초(28.4%), JSONL append1.031초(0.31%), eval1.019초(0.30%).
렌더는 capture에 포함돼 더하지 않는다. 남은 약131.375초는 제어·초기화 등 별도 미분해 시간이다.
단일30SIM 벤치마크2.2와 3대·매.05초 관측의 이 probe는 workload가 다르며, c4/c5는 자체 pause260초도 포함했다. 기록 I/O를 주원인으로 볼 수 없고 이번 라운드는 최적화하지 않는다.

## 참고 자료

- [Weiss/Sanderson/Neuman 1987, Static look-and-move, p407](https://www.cs.cmu.edu/~lew/PUBLICATION%20PDFs/VISUAL%20SERVOING/JRA%201987.pdf): 관측→명령→동작 완료를 직렬로 반복한다. 우리 정착/새 프레임 게이트는 고정 명령과 보정 coast만 사용한다.
- [Hutchinson/Hager/Corke 1996 tutorial](https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf): 시각 제어의 이산 샘플/지연과 위치 기반 제어. 기존 full-pose 좌표계와 한 축 명령을 유지한다.
- [Nav2 AdaptiveToleranceGoalChecker, hysteresis buffer](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/core_servers/controller_server/controller_server_plugins/adaptive_tolerance_goal_checker/adaptive_tolerance_goal_checker/): 진입 후 buffer 안에서 latch, 밖에서 해제. 여기서는 제어 정지 latch만 적용하며 coarse success 경로는 도입하지 않는다.
- [Nav2 Rotation Shim](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/controller_plugins/configuring_rotation_shim_controller/): 회전 단계와 병진 단계 분리.
- [Liberzon, Nonlinear control with limited information](https://liberzon.csl.illinois.edu/research/legacy.pdf), pp43–46: 유한 양자화 정밀도에서 일반적인 정확 수렴 대신 오차 집합으로의 수렴을 분석한다. 입력 양자화도 같은 문제를 갖는다. 이 문헌이 본 로봇의 성공을 보장한다고 해석하지 않는다.

## 결과

미실행. 고정 소스와 관련 회귀 완료 후 위 목록을 실행한다.

실행 전 검증: 변경 controller/runner와 workflow의 관련2파일 선별9개 PASS(18.03s). 처음 pair motor-stub 회귀에서 감사 dict의 중복 errors키를 발견해 control_errors로 분리한 뒤 전부 재통과했다. 실제 물리로 결함을 탐색하지 않았다.
