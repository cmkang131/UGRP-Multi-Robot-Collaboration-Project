# T05 오프라인 검증

제어·인식·최종 테스트 소스 커밋: `157d655a33cf196cdcfc2fd854e1b0cb642d4b97`. 이후 기록 커밋은 문서/JSON만 바꾼다.

물리 step 0, renderer 0, 모델 호출 0. 호스트 잠금을 획득하지 않았다.
실행 Python은 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`이다.
환경·source closure·파일별 SHA-256은 [verification.json](verification.json)에 있다.
이 숫자는 코드 회귀검사이며 로봇 trial/성공률이 아니다.

## 통과한 검사

| 검사 | 결과 | 범위 |
|---|---:|---|
| tile + 필수 두 source pinning 파일 + 공개 입력 | 165 passed | base `6a57435e`, 두 필수 파일 전체 실행, runtime 최종 내용과 동일 |
| 최종 tile + 기존 v3.1 인식 + 기존 executor | 205 passed, 1 deselected | 실제 host 물리 시험 1건을 명시적으로 제외; 최종 tile 65건 포함 |
| 최신 main base에서 tile + 현재 v6e pin + study bundle pin | 67 passed | base `26545c24`, source pinning 대표 2건 재확인 |
| mutation 재검사 | 6/6 killed | pytest exit 1 및 실제 지정 assertion 실패를 확인; 수집/import 오류 제외 |
| CI 파일/봉인/원본 보존 | 차이 없음 | `.github/workflows`, `scripts/run_ci_tests.py`, 원본 scenarios/maps, 기존 tracked 소스 수정 없음 |

첫 165건은 최종 배경 fixture 보강/정적 catalog 검사 추가 전의 테스트 파일이다.
제어·인식 소스는 동일했고, 최종 테스트 파일은 205건과 67건 실행에서 다시 검사했다.
중복된 검사를 합쳐 하나의 독립 표본 수로 보고하지 않는다.

실행 명령:

```sh
python -m pytest -q tests/test_zone_own_executor_tile.py \
  tests/test_zone_pair_registered_source.py tests/test_zone_study_source_pinning.py \
  tests/test_zone_study_inputs.py

python -m pytest -q tests/test_zone_own_executor_tile.py \
  tests/test_zone_own_perception_v3_1.py tests/test_zone_own_executor.py \
  -k 'not test_team_host_feeds_each_executor_only_its_own_camera'

python -m pytest -q tests/test_zone_own_executor_tile.py \
  tests/test_zone_pair_registered_source.py::test_v6e_records_current_scene_and_full_source_closure \
  tests/test_zone_study_source_pinning.py::test_registered_speech_caps_and_llm_driver_are_pinned_in_the_run_bundle

python experiments/2026-09-30-t05-tile/mutation_check.py --output /absolute/new/directory
```

제출 전 main에 #307·#332가 병합되어 base를 fast-forward했다. 그 차이와 후보의
146개 정적 Python 의존성 및 기존 관련 테스트의 교집합은 비어 있었다. 현재 v6e/
study pin은 최신 base에서 다시 검사했다. CI workflow의 timeout 변경은 #332의
main 변경이며 이 PR의 diff에는 포함하지 않는다. 기존 CI glob이 새 테스트를
선택하는 것도 `run_ci_tests.py --shard-count 8 --list-shards`로 확인했다.

## mutation — 판단을 빼면 실패하는지

| 제거/변조 | 잡는 검사 |
|---|---|
| west 역할 거절 삭제 | east/any/north/end_neg/None 생성 거절 |
| 기본 7 mm를 상자용 24 mm로 교체 | 정상 조작 흐름이 holding까지 도달하지 못함 |
| holding 두 영상 확인 삭제 | 첫 영상만으로 holding 승격됨을 검출 |
| 방출 영상 조건을 True로 교체 | grip 부재만 있고 바닥 tile이 없어도 완료하는 오류 검출 |
| 자기 camera 제한 삭제 | top_cam 거절 회귀 |
| tile 경계 밖 색 검사 삭제 | 화면 전체 magenta 배경을 holding으로 읽는 회귀 |

`mutation_check.py`는 임시 module 사본만 바꾼다. 원본/봉인 소스는 변경하지 않는다.
최초 결과 [mutation-01.json](mutation-01.json)은 **5/6**, 보강 뒤
[mutation-02.json](mutation-02.json)은 **6/6**이다. 첫 배경 fixture는 3.3% 줄무늬라
P5/P95 정보량 검사에서 먼저 막혔다. 줄무늬를 10%로 만들고 정보량 gate를 통과한다는
assertion을 추가해 경계 분기 자체를 검사하도록 했다. 생산 문턱을 느슨하게 하지 않았다.

초기 별도 pytest는 59 passed/1 failed였다. 근접 tile fixture를 기존 낮은 각도의
관측 PWM으로 투영해 화면 밖에 그렸기 때문이다. 실제 카메라/FOV를 바꾸지 않고
합성 fixture의 발행 관측 PWM을 고쳤으며 실제 검출기 정상/반례를 다시 통과했다.

## 원본·남은 확인

- 로컬 로그/JUnit/mutation 원본: `/Users/changmin/projects/ugrp/outputs/t05-tile/offline/`.
  `regression-01`과 `latest-base-01`은 stdout/JUnit 전체를 보존했다.
  최초 165건은 도구가 반환한 종료 코드/요약만 보존했고 전체 stdout 파일은 없다.
- Git에는 JSON 요약·source/log hash·이 문서·재실행 스크립트를 보존한다.
  raw 로컬 로그를 원격 백업으로 표현하지 않는다. Drive 조회/업로드 없음.
- GitHub 정상 CI는 push 뒤 별도로 확인한다. local physics 금지를 CI 취소/skip으로
  확대하지 않는다. CI 통과도 이 후보의 물리 인수가 아니다.
- 독립 검토, native adapter/workflow 등록, 자기 RGB navigation 연결, 최종 카메라
  보정/가시성, 접촉·마찰, C 정상/미파지 2셀 및 TensorBoard는 남아 있다.
  [PHYSICS_HANDOFF.md](PHYSICS_HANDOFF.md)의 1,800 SIM초는 실행 상한 제안이다.
