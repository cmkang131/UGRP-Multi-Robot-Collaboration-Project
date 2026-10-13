# 경로 입력 기록과 footprint 후속 (DEV, 기본 off)

## 구현과 범위

`--route-input-record on_v1` → `e2e_options.route_input_record=on_v1`. 실제 `route_to_B` 직전에 자기 점유 odds와 floor/wall 출처, support, 해상도, TF, covariance, 자기 RGB/봉/목표와 관측 B polygon, 팽창/미지 처리 옵션, endpoint override, compiler profile을 저장한다. 같은 파일에 실제 결과/실패/진단/계산 시간을 넣는다. 평가 정답을 이 입력에 합치지 않는다.

실행당 첫 128시도, 압축 파일당 2MiB, 압축 총 64MiB, 비압축 레코드당 16MiB. index는 최대 512행이며 이후 누락도 summary 누계에 남긴다. 모든 저장 파일은 zstd 왕복 바이트 검증과 압축/원문 SHA-256을 기록한다. 예산 초과는 제어를 계속하되 누락을 표시하며, 저장 오류는 HOST_ERROR다. 기존 파일을 덮어쓰지 않는다. off는 파일도 만들지 않는다. 경로 계산 시간은 캡처/압축 시간을 제외한다.

번들 v381은 유지한다. 예약: v387=v375+기록, v388=v381+기록, v389=footprint_v2, v390=v389+기록. 부모 해시/옵션을 검증하며 모두 기본 off다. 번호 스캔과 최초 예약 코멘트는 PR #461에 있다. grasp1의 뒤이은 v387 예약 충돌을 알렸으며 staging 번호 조정은 PR #475에서 진행한다.

## 구체적 기하

`goal-geometry-followup.json`은 r80 v375/61009 마지막 실패 277.2s의 자기 값이다. σ=1.3499m로 엄격한 여유는 4.0697m였지만 실제 실패 시에는 이미 0.02m까지 완화했다. 목표 운반 외곽 occupied 34셀, unknown 8셀이다. 봉 yaw=1.35682rad; 회전한 운반 외곽 투영 길이도 JSON에 적었다. B detector의 예전 bounds는 partial_extent=true이며 현재 완전한 경계와 동일시할 수 없다. **격자 위치와 당시 map TF가 기록되지 않아 어느 벽/경계와 충돌했는지는 여전히 미확인**이다. 정답 좌표를 끌어와 원인으로 단정하지 않는다.

v381의 셀 여유(양 축에 해상도×0.71 추가)를 수정한 별도 후보 v389는 실제 방향 직사각형과 셀 정사각형의 SAT 교차를 쓴다. 1.25×0.40m 물리 외곽과 2cm 명목 여유를 줄이지 않는다. 최종 모든 선분의 연속 swept polygon을 검사한다. NavFn처럼 tolerance 사각형 내 도달 가능한 후보에서 목표와의 제곱거리가 가장 작은 셀을 선택한다. 실제 목표 위치 자체의 footprint도 확인한다. 목표 이동은 관측된 완전한 B polygon에 고정 봉 0.60×0.04m가 들어갈 때만 허용한다(`sim/zone_cargo.py` beam_1 치수). 1.25m 로봇 쌍 전체가 0.8m B에 들어가야 한다는 조건은 두지 않는다. 시작점 이동과 운반 yaw 회전은 하지 않는다.

미지는 실행 경로에 허용하지 않고 기존 frontier_v1 정보이득 힌트로만 쓴다. σ 완화는 DEV 전용이다. 실제 장면이 회전을 요구하거나 위치 추정이 어긋난 경우 이 고정 yaw 계획기만으로 해결되지 않는다.

## 오프라인 사용

```sh
PYTHONPATH=. python -m scripts.run_e2e_route_stage_probe \
  --recordings <run1/route-inputs> <run2/route-inputs> \
  --evaluation-dir <separate-eval-directory> --output <new-output-directory>
```

기준 off, 보존 v381/frontier_v1, 새 footprint_v2를 모든 동일 입력에서 비교한다. source 성공/실패 부분집합, 성공 n/N, 실패 이유 분포, 계산 시간 중앙/최대, 저장 누락 수를 기록한다. 과거 v1 snapshot manifest도 읽는다. 기록한 원래 제어기의 결과/실패/route 재현 여부도 검사한다. 평가 파일은 `<snapshot canonical digest>.json`으로 별도 연결한다. schema는 기존 `ugrp.route_eval_rectangles.v1`이며 평가 파일을 planner에 넘기지 않는다. collision_free와 geometric_passable은 전체 운반 swept polygon의 **정적 기하 평가**다. 마찰/접촉/하중을 포함하는 실제 통과 비율은 물리 단계 전까지 0/0 미측정이다. 평가 파일 부재·오류는 계산 성공과 분리한다.

## 단계 제출

PR #475 공용 `e2e_stage_checkpoint.py` / `run_e2e_stage_probe.py`를 재사용한다. r80 자체에 과거 점유 격자가 없으므로 이 어댑터는 과거 자기 RGB와 발행 명령만 시간순 재생하여 지도를 복원하고 기록된 자기 pose/B/beam과 대조한다. 그 검증과 checkpoint hash가 같은 기준/후보를 짝짓는다. 정답은 TEST_SETUP_GT 시작 배치와 eval_only에만 쓴다. 같은 과거 물리 integration state의 완전한 복원이라고 부르지 않는다.

요청: seed61006–61009 × v387/v390 총 8개, mapping 중간 cutoff부터 최대 60 SIM초, 경로 첫 생성에서 종료. VM3 전체 동시16 안에 grasp 8개와 분할, 게이트3.5. 기록 파일 최대 8×64MiB=512MiB + bounded index/summary; RGB·staging 원본 예산은 감독자가 공용 어댑터와 합산한다. OpenRouter 잔액/자원/저장 여유 확인은 조정자. Mac 순수 재생 외 물리 실행은 하지 않았다. 원본이 준비되지 않으면 HOST_ERROR/미실행을 전체 분모에 남긴다.

## 참고 자료

2026-10-13 공식 원문 확인:
- [NavFn 구현](https://api.nav2.org/nav2-rolling/html/navfn__planner_8cpp_source.html): tolerance 사각형 내 유효 potential 중 목표와 제곱거리가 최소인 점. 이를 기존 A*의 도달 가능 component에 적용했다.
- [Nav2 footprint checker](https://api.nav2.org/nav2-rolling/html/footprint__collision__checker_8cpp_source.html): pose의 yaw로 footprint를 회전해 costmap에서 충돌 검사한다. 이번 셀 전체 SAT 및 연속 sweep는 perimeter raster보다 보수적인 적용이다. Nav2 구현과 바이트 동일하다는 주장이 아니다.
- [Smac 2D 설정](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/planners_plugins/smac/smac_2d/configuring_smac_2d/): tolerance, allow_unknown. 미지는 정보획득 힌트에만 허용한다.
- 최신 논문/공개 frontier 코드의 확인 범위와 미확인 문헌은 기존 [README 참고 자료](README.md#참고-자료)에 보존했다. 이번 성능 개선의 증거로 인용하지 않는다.
