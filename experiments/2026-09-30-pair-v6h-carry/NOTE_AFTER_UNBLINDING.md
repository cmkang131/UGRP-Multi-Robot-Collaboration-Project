# 개봉 뒤 역사 기록 병합 안내

2026-10-01에 `5be4330eca9b23d2cbde3657dcbb215ee1923b25` checkout에서
b-v6h1 코호트를 개봉했다. 결과는 PR #349에 별도로 기록했다.
이후 main의 harness 버전은 봉인된 분석 소스와 다르다. #292는 역사 기록을
보존하는 PR이며, 현재 작업 트리로 과거 실행·분석 결과를 승계하지 않는다.

`REGISTRATION_PLAN.md`도 분석 pin에 포함된다. 시작 HEAD `5cdac89b`에 있던
그 파일과 `analysis/seal_v2/README.md`의 후속 안내 수정은 `5be4330e`의 원래
바이트로 복원했다. 기존 봉인·prereg·plan·pin·RUN_MANIFEST는 그대로 보존한다.
이 안내는 봉인 집합 밖에 둔다.

현재 병합 브랜치에서도 다음 명령으로 봉인 커밋의 Git 객체를 감사한다.
실제 과거 분석 재현에는 계속 `5be4330e` checkout을 사용한다.

```sh
python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h \
  --verify-seal --seal-revision v2 \
  --seal-commit 5be4330eca9b23d2cbde3657dcbb215ee1923b25
```

병합 검증: `origin/main=dce9700f`의 공용 harness 18개를 그대로 반영했다.
기존 봉인 관련 50파일의 바이트 보존, 실행 274개·분석 293개 Git pin을 확인했다.
seal/v6h·영향받은 pin 검사와 `tests/test_ci_sharding.py`를 포함한 30파일에서
**1,430 passed / 기존 13 xfailed / 실제 실패 0**이다. 물리·렌더·모델 워커·
네트워크 호출 시도는 0회이며 workflow 변경은 없다. 원본 로그는 로컬
`outputs/pr292-historical-merge-20261001/latest_main/`에 보존한다.

첫 CI에서 새 main의 #344·#346 역사 감사 두 곳도 현재 파일을 과거 해시에
대조하는 문제를 확인했다. 각각 기록된 리뷰/적합 커밋으로 감사하도록 바꿨다.
기록과 harness는 보존했고, 변경한 두 테스트 파일과 CI 분할 검사 **105개가
통과**했다(위 검사와 중복 포함). 실패 로그와 대응 기록은 같은 작업 기록의
`ci_fix/`에 보관한다.
