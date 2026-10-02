# PR #351 시각 감사 수정 독립 재검토

**판정: MERGE.** 요청한 수정 범위에서 미해결 지적이나 새 결함을 찾지 못했다.
R3b 네 반례와 이전 반례는 모두 거부되며, 동결 B/B′와 v88 등록 바이트가 유지된다.
이는 아래 SHA의 오프라인 코드 검토 판정이다. PR은 draft/open 상태이며 병합하지 않았다.
실제 MEASURED_SIM 발행이나 물리 성능 승인을 뜻하지 않는다.

- 검토 대상: `3149a138acb2d362c088e861d31f38530f48efe3`.
- 수정 비교: `9134d7e12de1d4748a85904dee63c12b682f2dca` →
  `8034f410b58538901ec6377dc0b461b97d0a6a71`.
- 검토 브랜치: `codex/review-351`, 시작 커밋 `a1ed666f212f81ba77a6f5987c5ffb4f1d50a02a`.
- 앞선 판정: [REVIEW_351b.md](REVIEW_351b.md).

## 재개와 검사 결과

앱 종료 전의 커밋·미커밋 `tests/test_review_351c.py`·임시 archive·JUnit을 보존해 이어서 작업했다.
원본 반례와 새 변형은 이미 완료됐으므로 반복하지 않았다. 재개 후 archive의 **2,693개 파일**을
대상 Git blob과 비교했으며 불일치·추가 파일은 없었다. 누락됐던 fixture 한 개만 같은 SHA의
`git archive`로 복원한 뒤 해당 검사만 재실행했다. 후보 제품 코드와 assertion을 바꾸지 않았다.

| 검사 | 확인 결과 |
|---|---|
| 리뷰 원본 `test_review_351.py` + `test_review_351b.py`, `--runxfail` | **24 passed**. 기존 R1–R4 여섯 사례와 R3b 네 strict-xfail 사례를 포함한다. 후보 관련 suite와 중복이므로 총수에 더하지 않는다. |
| R3b 실제 JSONL + manifest 재계산 | unloaded/fine/loaded × r1/r2 모두 초기 NaN 시각을 거부한다. fine 전체 조립은 audit=FAIL, motion 승인 없음, gain=null이다. |
| 새 시각 변형 `test_review_351c.py` | **20 passed**, 내부 변형 **123개 모두 거부**. 정상 입력은 변조 전·복원 후 감사에 통과한다. |
| 후보 관련 8개 suite | 첫 실행 **603 passed / 1 failed**. 누락 fixture 복원 뒤 실패한 동일 검사 **1 passed**. 사례별 최종 **604 passed**이며 단일 전체 녹색 실행으로 표현하지 않는다. |
| CI·등록 | frozen fixture 3개 확인, shard 합집합 410파일·중복 없음, 리뷰 b 파일 정확히 1회 포함, durations 407/410=99.27%. 대상 HEAD의 원격 검사 **33개 모두 SUCCESS**. |

새 변형은 mock으로 시각을 바꾸지 않고 합성 JSONL과 artifact manifest를 함께 갱신한다.
pose/frame/camera label/초기 서보/arm/look/mecanum/beam/contact/알 수 없는 command의
10종에 숫자 문자열·`"NaN"`·true/false·null·NaN·±Infinity·`t` 누락 9종을 적용했다(90개).
pose/frame/label/command/beam/contact/schedule에는 시각 역전·중복·행 순서 역전을
적용했다(21개). 초기 명령은 세 프로필·두 로봇에서 ±0.05초 오프셋도 거부했다(12개).
알 수 없는 command는 유효 시각이어도 기존 schedule 계약상 허용하지 않는다.

초기 부분 archive에는 `experiments/2026-09-26-vision-loc/vision_motion.py` 의존성이 빠져
원본 24개·변형 20개 첫 시도가 probe 본문 전에 실패했다. 이전 실행에서 같은 SHA의
의존성을 복원한 후 두 suite가 통과한 로그를 보존했다. 관련 suite의 남은 한 실패는
`experiments/2026-10-01-v3-pair-adapter/identifiability_v2.json` 누락이었다.
재개 후 그 파일만 복원한 재실행이 통과했다. 이 준비 오류를 제품 결함이나 성공으로 숨기지 않는다.

최종 서로 다른 테스트 사례는 **624개(관련 604 + 새 변형 20)**다. 세부 입력 123개와
독립 재실행 24개를 이 수에 중복 가산하지 않는다. 기존 리뷰 테스트의 함수 본문은
후보에 편입된 본문과 AST가 같으며, xfail 해제 때문에 assertion이 완화되지 않았음을 확인했다.

## 수정 diff와 동결 경계

제품 변경은 `scripts/final_pair_calibration_io.py`의 시각 검사다.
`finite_time()`은 bool을 제외한 int/float와 유한성을 검사하고 큰 정수 변환 overflow도
ValueError로 거부한다. `record_times()`는 명령 종류 필터·round·float 변환·시간 비교 전에
초기 명령을 포함한 모든 소비 레코드를 검사한다. 완료 시각, schedule·명령 지속시간,
motion 시작·구간 시간에도 검사가 추가됐다. 기존 clock grid·schedule 순서·초기 시각 일치
검사를 대체하지 않으므로 유한하지만 틀린 시각도 기존 계약에 따라 거부된다.

`9134d7e1`, `8034f410`, `3149a138`의 다음 **15개 파일을 직접 바이트 비교**했다.

- B·B′, frozen validator, r4 candidate/report.
- execution bundle registry, v88 contract/excitation/calibration.
- v88 설정·clearance·calibration contract·workflow, 공통 workflow·지도 registry.

B SHA-256은 `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`,
B′는 `3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33`로 동일하다.
B′의 parent 본문·SHA도 B와 일치한다. 파일별 전체 경로·해시는 [static.json](review-351c-evidence/static.json)에 있다.
정상 두 문 합성 수집을 세 프로필 모두 제공해도 전체 PARTIAL,
unloaded 세 축 판정 null·필수 필드 10개 null을 유지한다.

나머지 수정은 리뷰 b 테스트 편입·시각값 180사례 추가·CI 목록 1행·검증 기록이다.
`8034f410..3149a138`의 차이는 main에서 들어온 shard timeout 15→25분 및 설명 문서뿐이다.
리뷰 작업은 `.github/workflows`를 수정하지 않았다.

## 환경·증거·남은 경계

기존 `/opt/anaconda3/bin/python3`(Python 3.13.5, NumPy 2.4.4, SciPy 1.17.1,
pytest 8.3.4)를 재사용했다. BLAS/OMP thread 1, bytecode·pytest cache·외부 plugin
자동 로딩 비활성화, 임시 basetemp와 physics/render/network/model 및 공용 outputs 접근
차단을 적용했다. [실행 명령 구성](review-351c-evidence/run_tests.py)과
[guard](review-351c-evidence/guard.py)를 보존했다.

후보의 관련 suite는 다음 8개다. 원본 리뷰와 새 변형은 리뷰 브랜치에서 이 후보 archive를
`REVIEW_351_ROOT`로 지정하고 `--runxfail`로 실행했다.

```text
tests/test_final_pair_calibration_assembly.py
tests/test_review_351.py
tests/test_review_351b.py
tests/test_consumer_criterion_b.py
tests/test_final_environment_unloaded_fit.py
tests/test_zone_final_pair_v3.py
tests/test_zone_final_pair_review_fixes.py
tests/test_ci_sharding.py
```

[검증 요약·해시](review-351c-evidence/verification.json) ·
[원본 반례 JUnit](review-351c-evidence/original.xml) ·
[새 변형 JUnit](review-351c-evidence/variants.xml) ·
[관련 첫 실행 JUnit](review-351c-evidence/related.xml) ·
[누락 fixture 복원 후 JUnit](review-351c-evidence/related-fixture.xml) ·
[조건별 probe 결과](review-351c-evidence/probes.json) ·
[대상 HEAD CI 조회](review-351c-evidence/pr-ci.json).

GitHub 조회 당시 PR은 OPEN/draft, mergeable=MERGEABLE, mergeStateStatus=BLOCKED였다.
코드 검토의 MERGE 판정과 GitHub의 최종 병합 절차는 구분한다. 요청대로 병합하지 않는다.
기본 checkout은 main에 `AD calibration/important.json` 변경이 있어 갱신하지 않았다.
물리·렌더·모델 호출 0회, 실제 수집 raw와 공용 outputs 접근 0회다.
새 실험·학습·평가 코호트가 없고 공용 outputs 접근 금지 범위이므로 TensorBoard를 실행하지 않았다.

검토용 `/private/tmp/ugrp-review-351c.7oc93yvr`는 작은 검증 증거 보존 뒤 삭제하고
경로 부재를 확인했다([정리 기록](review-351c-evidence/cleanup.json)). 다른 작업의 자료는 삭제하지 않았다.
