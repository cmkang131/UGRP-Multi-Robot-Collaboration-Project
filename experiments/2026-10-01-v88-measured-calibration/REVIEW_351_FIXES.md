# PR #351 검토 수정

2026-10-02 재개 시 `87aa99c3` 위에 남아 있던 미커밋 수정과 리뷰 파일을 보존했다.
독립 리뷰 원본은 `ef1320b164f337afa7f9d1a43967f8c5d86f46df`의
[REVIEW_351.md](https://github.com/kcm0127-dotcom/ugrp/blob/ef1320b164f337afa7f9d1a43967f8c5d86f46df/experiments/2026-10-01-v88-measured-calibration/REVIEW_351.md)이며,
이 폴더의 사본은 바이트가 같다. 리뷰의 상대 증거 링크는 원본 리뷰 브랜치에서 확인한다.

- R1: 입력 파일·수집·case의 경로와 심볼릭 링크 대상을 등록한다. 미완료 수집도 보호하고,
  조립 전과 출력 직전에 모든 등록 경로의 동일·부모·자식 겹침을 거부한다.
- R2: 하중 선별 후 각 로봇·축·부호·horizon의 실제 step 적합 창에 `.006`, `.015`,
  `.025`, `.04`가 모두 남아야 한다. 0 명령 coast·PRBS·짧은 조각으로 대체하지 않는다.
  적합된 c0/u1이 정지·두 ramp·포화 수준을 구분하는지도 검사한다.
- R3: beam과 접촉 시각의 숫자형·유한성을 검사한다. NaN·무한대·문자열·null·bool은 거부한다.
- R4: 리뷰의 여섯 검사를 CI 목록에 편입했다. strict xfail 네 건을 일반 검사로 바꾸고,
  전체 `fit_profile()`의 PRBS 오염 시 잡음 불변성과 조립 후 입력 변조 거부 검사를 유지했다.

동결 B SHA-256은 `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`,
B′는 `3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33`로
`87aa99c3`과 같다. 현재 두 문 수집만으로 실제 MEASURED_SIM을 발행할 수 없다는 README의
제한도 유지했다. 물리·렌더·모델 호출 및 공용 `outputs/` 접근 없이 합성 오프라인 검사만 수행한다.
`.github/workflows`는 변경하지 않는다. PR 병합은 이번 요청 범위에 없다.

## 검증

기존 `/opt/anaconda3/bin/python3`(Python 3.13.5, NumPy 2.4.4, SciPy 1.17.1,
pytest 8.3.4)을 사용하고 BLAS/OMP thread를 1로 제한했다.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  /opt/anaconda3/bin/python3 -m pytest -q \
  tests/test_final_pair_calibration_assembly.py tests/test_review_351.py \
  tests/test_consumer_criterion_b.py tests/test_final_environment_unloaded_fit.py \
  tests/test_zone_final_pair_v3.py tests/test_zone_final_pair_review_fixes.py \
  --basetemp=/private/tmp/ugrp-fix-351-tests \
  --junitxml=/private/tmp/ugrp-fix-351-related.xml
```

시간 자료 갱신 전 `tests/test_ci_sharding.py`는 67 passed / 1 failed였다.
실패는 기존 시간 자료의 부족(409개 중 367개, 89.73%)이며 기준은 90%로 유지한다.
push 뒤 이 PR의 `offline-shard-*` JUnit만 받아 `scripts/refresh_ci_durations.py`로 갱신한다.

관련 검사는 **중복 제외 338건 통과**이며 리뷰 여섯 건도 모두 통과했다.
첫 실행은 332 passed / 6 failed였다. 새 계단 누락 검사의 선별식이 같은 크기의 PRBS까지
제거해서 다른 거부 조건을 먼저 만난 테스트 오류였다. 계단 구간 안에서만 제거하도록 고치고
해당 매개변수 검사 24건을 재실행해 모두 통과했다. 거부 assertion과 제품 코드는 완화하지 않았다.
검사별 최신 결과를 합쳤으며 단일 실행의 전체 통과로 표시하지 않는다.

- [첫 관련 검사 JUnit](fix-351-evidence/related-initial.xml)
- [수정한 계단 선별 검사 JUnit](fix-351-evidence/step-selection-final.xml)
- [시간 자료 갱신 전 샤딩 JUnit](fix-351-evidence/sharding-before.xml)
- [검사 요약과 파일 해시](fix-351-evidence/verification.json)

`git diff --check`, 필수 frozen fixture 3개와 shard 합집합 409파일도 확인했다.
