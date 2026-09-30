# 검증 기록 — 2026-09-30

기준 SHA `d17ca4345affef8cf027e121cf1f3197b36c23e0`, 작업 브랜치
`codex/seal-dependency-decouple`. 기존 Mac `.venv-sim-worker-mac` Python 사용.
실제 코드 파일의 해시는 [validation.json](validation.json)에 기록한다.

## 관련 회귀 검사

`scripts.run_ci_tests.run_locked`로 공용 잠금을 획득한 뒤 아래 6개 파일만 실행한다.
다른 작업이 점유 중인 동안 pytest를 시작하지 않았으며 그 프로세스/잠금을 변경하지 않았다.

```sh
python -m pytest -q \
  tests/test_execution_dependency_contract.py \
  tests/test_zone_pair_registered_source.py \
  tests/test_zone_study_source_pinning.py \
  tests/test_zone_pair_v6.py \
  tests/test_rgb_execution_bundle.py \
  tests/test_ci_sharding.py
```

초기 구현: **202 passed / 76.23 s**. 이후 `__import__` fromlist의 명시적 submodule
선언 검사와 JSON exponent overflow 거부 검사를 보강했다. 최종 결과는 아래와 JSON에
기록한다. 시간은 검사 실행 기록이며 성능 비교나 절감 측정이 아니다.

최종 결과: **204 passed / 88.91 s** (Python 3.12.13). 실행 뒤 테스트 프로세스
정리와 자기 잠금 반환이 완료됐다. 코드 오류/실패 없이 종료 코드 0으로 끝났다.

검사 범위:

- 새 빌더/CLI의 v2 기본값, 예전 스키마 자동 변환 거부, 기존 파일 덮어쓰기 거부.
- 무관한 registry 행 추가/수정/재정렬과 JSON 공백은 digest/receipt가 동일함.
- 사용한 행의 version/args/entry/runner 변경, schema·공용 defaults 변경은 거부함.
- 중복 JSON key·선택 id 중복/삭제·NaN·overflow를 거부함.
- import된 모듈·package 초기화·중첩 상대 import·worker·자산·검증기 변경 및
  import 추가/삭제를 거부함. import되지 않은 파일·등록 설명 변경은 허용함.
- 문자열 동적 import/별칭을 추적하고 비상수·fromlist는 명시적 선언을 요구함.
- 외부 봉인의 기대 digest와 비교하고, 누락 소스만 자기 해시로 다시 봉인해도
  closure 재계산으로 거부함.
- 실제 UGRP runner의 오프라인 preview: **222개 소스 + workflow entry 1개**.
  teacher ArmSequence·provider·scene/host 의존성을 포함함. 다른 입력은 최소한만
  선언한 검사 fixture이며 완전한 실행 등록 또는 #292 pin 수 측정은 아님.

## 기존 봉인의 바이트 보존

5개 등록 JSON을 기준 SHA의 `git show <SHA>:<path>`와 byte-for-byte 대조했다.
v6e의 현재 `v6_contract.source_sha256` **85/85**도 현재 파일과 일치한다.
관련 기존 테스트가 v3~v5h 역사 감사, v6~v6d 등록 commit blob 감사, 현재 v6e
계약/scene 일치, RGB v63 source closure와 은퇴 bundle 검증을 수행한다.

| 등록 | 원본 파일 SHA-256 (이 작업 후 동일) |
|---|---|
| v6 | `649a00e65d1f53bf38014ac4a1f5e93094dad3ee11acccf3d1343cefa1298b42` |
| v6b | `3fecc73b7b44c6dab1e752d276fe8b2442be7119016ff2b5783599579ffc9605` |
| v6c | `64acc04a8c08af61b0fa488440c70a8bec4338881c7a32b4895d4b07970ca95e` |
| v6d | `cbdb4b2503d928e141131b893cb56060fd6fe54292ef1667da9f57bdeea39972` |
| v6e | `64c2680781f1b989312c3ac091c6e0458579ced7ed65d9e9730aadbc416f4bfd` |

## 정적 검사와 한계

`git diff --check` 통과. `scripts/run_ci_tests.py --shard-count 8 --list-shards`는
**329개 파일 / 8 shard / coverage_verified=true**이며 새 테스트를 한 번 포함한다.
GitHub CI와 독립 검토는 draft PR에서 별도로 확인한다.

물리·렌더·모델 호출·신규 로봇 평가·기존 seal 재작성·#292 브랜치 수정·병합은
수행하지 않았다. 기존 source SHA/dirty/approval admission은 바꾸지 않았다.
이 계약을 #292에 실제 연결하는 일과 classifier/인수 재생·봉인은 조정자의 후속 범위다.
TensorBoard/Drive 작업 및 raw 삭제/압축/이동은 없다.
