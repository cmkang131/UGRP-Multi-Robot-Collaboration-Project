# PR #245 CI 시드 분할 — 2026-09-28

기준 HEAD `597ac6e6504b78126891c7805b6e577bb4a2f69d`, 브랜치
`codex/zone-study-multiturn`. 검토 8의 단일 v64 비교 CI 취소(29분 40초, 12%)를
해결하는 미커밋 변경이다. 실제 모델 호출·MuJoCo step·커밋·push·새 CI 실행은 0회다.
사용자 허용에 따라 모델·물리가 없는 테스트만 잠금 없이 실행했다.

## 변경과 시드 보존

- 전용 job을 16개 matrix shard로 분할했다. 각 테스트 함수의 정렬된 시드에서
  `floor(seed_rank * 16 / seed_count)`로 소속을 정한다. 범위는 연속이고,
  같은 함수의 같은 시드는 같은 shard에 간다. 비시드 사례도 한 번씩 배정한다.
- 기존 시드 범위는 그대로다: no_comm/v64 0–299, 통신 3조건 0–299,
  binding budget 0–99, zero-send gap 0–11, 생성 v64 비교 0–999,
  독립 참조 모델 0–2999, no_comm/추가 스케줄 차등 0–199,
  mutation 시드 1·30·479·1235. 조건·900 tick·horizon·assertion도 유지했다.
- **기존 5,335개 node ID의 multiset이 16개 shard 합집합과 정확히 일치한다.**
  중복 0, 누락 0이며, 분할 로직 회귀 6개만 추가해 총 5,341개다.
  [기계 판독 기록](ci-shards.json)에 두 ID 목록의 동일 SHA-256과 비용을 남겼다.
- job 목표는 15분 이하, timeout은 설치·artifact 여유를 포함해 20분이다.
  `fail-fast: false`로 한 shard 실패가 다른 시드의 검증을 취소하지 않는다.
  각 shard는 선택된 ID·setup/call/teardown 비용을 artifact로 보존한다.
- plugin은 이 job의 `-p tests.zone_multiturn_ci`로만 활성화된다.
  수집 전부터 MuJoCo import와 socket connect/connect_ex를 차단한다.

## 병목 측정과 최소 수정

수정 전 대표 시드 0의 속성 3개·생성 1개·독립 모델 1개를 cProfile로 측정했다.
총 10.326초, `run_stream` 11회/9.498초 중 `payload_violations` 585회/6.674초였다.
가장 비싼 부분은 실제 입력 계약 검사이며 동결 모듈 로딩은 약 0.02초였다.
계약 검사를 생략하거나 payload/지도 크기·시드 수를 줄이지 않았다.

no_comm 차등 검사와 통신 공통 스케줄 검사가 각 시드의 동일한 완결 기준 실행을
다시 만들고 있었다. 두 검사의 `seed`를 module scope로 묶고 완결된 기준 실행을
공유했다. 두 소비자는 읽기만 하고, 다음 시드에서 fixture를 교체하므로 300개
실행을 모두 메모리에 보관하지 않는다. 시드 속성의 fixture 실행 수는
2,360 → 2,060회(중복 300회 제거)이며, 각 assertion은 계속 실행된다.

동일 대표 시드의 수정 후 프로파일은 `run_stream` 10회/8.413초,
`payload_violations` 495회/5.864초였다. 분할 회귀 6개를 추가한 전체 11개 검사도
통과했다(프로파일 전체 9.456초). 이 시간은 프로파일 오버헤드를 포함한 로컬
진단이며 Ubuntu 속도 향상 비율로 해석하지 않는다. runtime·설정·기존 fixture는
무변경이고 동결 v64 원본 3/3 해시도 유지됐다.

## 동일 CI 명령의 로컬 측정

환경: macOS 27.2 arm64, Python 3.12.13. 기존 `.venv-sim-worker-mac` 재사용.
NumPy 2.5.2, OpenCV headless 5.0.0.93, pytest 9.1.1, Pillow 12.3.0으로
`requirements-test.txt`와 일치한다. 새 환경을 만들지 않았다.

workflow의 명령을 직접 읽고 `${{ matrix.shard }}`를 0–15로 치환해 순차 실행했다.
PATH의 `python`만 기존 환경으로 지정하고 `OMP_NUM_THREADS=1`,
`PYTHONDONTWRITEBYTECODE=1`을 설정했다. 테스트 모듈·옵션은 Ubuntu job과 같다.
설치·checkout·artifact 업로드 시간은 로컬 표에 포함하지 않는다.
실행 간 부하 평균과 정확한 명령은 `ci-shards.json`에 있다.

```sh
export PATH="/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin:$PATH"
export OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
# shard=0부터 15까지 아래 명령을 순차 실행하고 매번 임시 디렉터리를 정리한다.
```

```sh
python -m pytest tests/test_zone_study_multiturn_properties.py tests/test_zone_study_multiturn_generated.py tests/test_zone_study_multiturn_exits.py tests/test_zone_study_multiturn_review5.py tests/test_zone_study_multiturn_review6.py tests/test_zone_study_multiturn_review7.py tests/test_zone_study_multiturn_model.py tests/test_zone_multiturn_ci.py -p tests.zone_multiturn_ci --multiturn-shard=0/16 --multiturn-report=outputs/ci-multiturn/shard-0.json --durations=20 --basetemp=./.pytest_tmp -q
python -c 'import shutil; shutil.rmtree(".pytest_tmp", ignore_errors=True)'
```

| Shard | 통과 | wall 초 | pytest 초 | 300시드 범위 | 1000시드 범위 | 3000시드 범위 |
|---:|---:|---:|---:|---|---|---|
| 0 | 338 | 57.54 | 57.35 | 0–18 | 0–62 | 0–187 |
| 1 | 333 | 54.89 | 54.68 | 19–37 | 63–124 | 188–374 |
| 2 | 336 | 55.96 | 55.71 | 38–56 | 125–187 | 375–562 |
| 3 | 330 | 48.96 | 48.73 | 57–74 | 188–249 | 563–749 |
| 4 | 338 | 56.48 | 56.24 | 75–93 | 250–312 | 750–937 |
| 5 | 333 | 55.92 | 55.64 | 94–112 | 313–374 | 938–1124 |
| 6 | 336 | 56.78 | 56.58 | 113–131 | 375–437 | 1125–1312 |
| 7 | 330 | 51.66 | 51.44 | 132–149 | 438–499 | 1313–1499 |
| 8 | 338 | 53.82 | 53.56 | 150–168 | 500–562 | 1500–1687 |
| 9 | 332 | 54.72 | 54.47 | 169–187 | 563–624 | 1688–1874 |
| 10 | 335 | 53.15 | 52.86 | 188–206 | 625–687 | 1875–2062 |
| 11 | 329 | 51.85 | 51.65 | 207–224 | 688–749 | 2063–2249 |
| 12 | 337 | 58.13 | 57.90 | 225–243 | 750–812 | 2250–2437 |
| 13 | 332 | 55.29 | 55.04 | 244–262 | 813–874 | 2438–2624 |
| 14 | 335 | 55.45 | 55.18 | 263–281 | 875–937 | 2625–2812 |
| 15 | 329 | 51.53 | 51.26 | 282–299 | 938–999 | 2813–2999 |

총 5,341개 통과. 최장 shard 58.13초, 순차 합계 872.14초다. 모든 shard가 로컬 15분 목표 이내다.

전체 실행의 비용 상위 테스트(phase 합계, fixture setup 포함):

| 테스트 | 개수 | 합계 초 | setup 초 | call 초 | 최대 사례 초 |
|---|---:|---:|---:|---:|---:|
| `test_three_communication_conditions_keep_common_schedule` | 300 | 442.28 | 0.04 | 442.21 | 2.03 |
| `test_no_comm_bitwise_equivalent_to_frozen_v64` | 300 | 287.45 | 141.81 | 145.62 | 1.33 |
| `test_generated_zero_send_gap_cannot_strand_messages` | 12 | 33.91 | 0.00 | 33.91 | 3.18 |
| `test_generated_binding_budgets_keep_no_comm_v64_parity` | 100 | 33.17 | 0.01 | 33.15 | 0.52 |
| `test_generated_default_caps_and_all_prewire_failures` | 1000 | 26.38 | 0.49 | 25.82 | 0.08 |
| `test_refundable_reservation_cannot_cancel_v64_reask` | 32 | 5.87 | 0.32 | 5.55 | 0.24 |
| `test_review3_zero_send_wakes_message_at_8s` | 8 | 5.29 | 0.00 | 5.29 | 0.76 |
| `test_generated_stream_matches_independent_reference` | 3000 | 4.09 | 0.29 | 3.65 | 0.03 |
| `test_review4_refunded_start_reaches_all_90_sends_at_default_caps` | 1 | 3.61 | 0.00 | 3.61 | 3.61 |
| `test_new_message_never_inherits_common_retry_allowance` | 18 | 2.36 | 0.00 | 2.35 | 0.15 |

공유 baseline setup 비용은 먼저 요청한 no_comm 검사에 귀속된다.
원본 비용/ID/log: 이 작업트리의 `outputs/ci-multiturn/`에 로컬 보관하며,
파일별 SHA-256은 `ci-shards.json`에 있다. 원격 백업으로 보고하지 않는다.
모든 pytest 종료 후 `.pytest_tmp` 제거를 확인했다.

## offline-regressions 영향과 남은 검증

이번 변경 전후 `offline-regressions` job 블록과 `scripts/run_ci_tests.py`는
바이트 단위로 동일하다. 현재 HEAD에서 선택되는 282개 모듈에 변경 파일은 0개다.
새 plugin·분할 검사는 그 목록에 들어가지 않고, 수정한 properties 모듈도
기존 offline 모듈에서 import하지 않는다. 기본 suite로 시드를 이동/복제하지 않았다.

[기존 Ubuntu 실행](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36355728616/job/108722955606)의
로그를 이번 작업에서 직접 읽었다. PR head `597ac6e6` + main `ba0eb4f5`의
검사용 merge SHA `952f1b3281a88bc12e2cdf805d00cd482618bf54`에서
**5,179 passed, 132 skipped, 417 subtests passed, pytest 1,056.93초(17분 36초)**다.
Ubuntu는 main의 `test_pilot_korean_dialogue_records.py`를 추가한 283모듈이고,
현재 feature HEAD의 282모듈과 구별한다. suite 뒤 fixture CLI 단계까지 마치고 job 전체가 `success`로 끝났다.
20분 제한의 여유가 작다는 기존 위험은 남지만 이번 diff로 작업량은 늘지 않는다.

새 matrix의 Ubuntu 완주는 미확인이다. 커밋 금지 요청으로 push/CI를 시작하지 않았으며,
로컬 통과를 Ubuntu 통과로 대체하지 않는다. 전체 offline suite의 새 로컬 재실행도
이 기록의 주장에 포함하지 않는다. 현재 검증은 위의 기존 Ubuntu 로그와 변경 영향
검사, 그리고 전체 전용 shard 실행이다.

`git fetch origin`은 공용 `.git/.../FETCH_HEAD` 쓰기 권한으로 실패했고 `gh`는
네트워크 제한으로 실패했다. 연결된 GitHub 도구로 열린 PR과 PR #245의 HEAD가
로컬 SHA와 같음을 확인했다. main 갱신·다른 작업의 프로세스 변경·Drive 작업은 없다.
