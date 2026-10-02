# PR #351 독립 재검토

**판정: MERGE AFTER FIXES.** 기존 R1–R4의 여섯 반례는 모두 닫혔지만,
R3와 같은 유형의 초기 서보 명령 NaN 시각 우회가 남아 있다. 아래 R3b 한 건을 수정한 뒤
해당 반례와 관련 검사를 다시 확인해야 한다. 이 검토에서는 PR을 병합하지 않는다.

- 대상: `9134d7e12de1d4748a85904dee63c12b682f2dca`.
- 이전 대상: `87aa99c337f700586f01039e40c6ad4dce410afa`.
- 비교 main: `11e9aa26954d3f1ce58c5116ddd14ec2b2738037`.
- 리뷰 시작점: `ef1320b164f337afa7f9d1a43967f8c5d86f46df`, `codex/review-351`.
- [이전 리뷰](REVIEW_351.md), [작성자 답변](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/351#issuecomment-5946093239).

재개 시 브랜치는 깨끗했고 staged 변경·진행 중인 merge/rebase/cherry-pick이 없었다.
기존 리뷰·테스트·증거 커밋을 보존했다. 원격 소스는 `git fetch`, `git diff`,
`git archive origin/codex/calib-measured-v88`로만 확인했다. archive의 관련
소스·테스트·설정·지도·실험 파일 2,467개를 대상 Git blob과 비교해 불일치 0개였다.
실제 수집 raw와 `/Users/changmin/projects/ugrp/outputs`는 읽거나 쓰지 않았다.

## 잔여 지적 — 한 묶음

### R3b · P2 — 초기 서보 명령의 NaN 시각은 여전히 승인됨

대상 [scripts/final_pair_calibration_io.py:166–173](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/9134d7e12de1d4748a85904dee63c12b682f2dca/scripts/final_pair_calibration_io.py#L166).

일반 명령은 frozen schedule과 비교하지만 `initial_servo_command`는 이 비교에서 제외한다.
초기 명령의 검사는 `abs(initial[0]['t']-t[0]) > 1e-7`뿐이므로 NaN을 거부하지 못한다.
beam/contact에 추가한 숫자형·유한성 검사가 여기에 적용되지 않았다.

실제 합성 `robots/{r1,r2}/commands.jsonl`의 첫 행 `t`를 `NaN`으로 바꾸고
artifact manifest를 다시 계산하면, **unloaded/fine/loaded × 두 로봇 6조건 모두**
`load_collection()`과 `inputs.verify()`를 통과한다. 해시 불일치나 mock의 우회가 아니다.

fine의 r1 반례를 전체 `a.run()`에도 넣었다. 최종 결과는 기존 held-out 제한 때문에
`PARTIAL`이지만 `fine.collection_audit=PASS`, `fine.motion.accepted=true`이며
`params.motion_profiles.fine.gain`에 대각 `[1.2, 0.85, 1.4]`가 기록된다.
따라서 최종 MEASURED_SIM 방출 문제와 별개로, 잘못된 시계 자료를 승인된 fine 필드로
출력하는 문제다. 원본 `87aa99c3`에도 있던 인접 결함이며 수정 커밋이 새로 만든 회귀는 아니다.

초기 명령을 포함해 소비하는 시각을 비교·변환하기 전에 숫자형·유한성으로 검사해야 한다.
[새 반례](../../tests/test_review_351b.py)의
`test_initial_command_nan_is_rejected_from_real_jsonl` 세 프로필과
`test_initial_nan_cannot_produce_accepted_fine_section`을 일반 통과 검사로 바꿀 수 있어야 한다.
현재 네 strict xfail은 **실제 AssertionError**만 허용하며 프로브 오류·timeout을 숨기지 않는다.
[파일 감사 반례](review-351b-evidence/initial-time.json),
[전체 조립 반례](review-351b-evidence/initial-time-pipeline.json),
[각 조건 출력](review-351b-evidence/probes.json).

## R1–R4 재현과 인접 변형

| 항목 | 직접 확인한 결과 |
|---|---|
| R1 | 기존 symlink 수집 내부 출력 반례가 쓰기 전에 거부된다. 기존의 파일/수집/case 동일·부모·자식 및 retarget 검사에 더해, 상대 입력·상대 출력·출력 부모 symlink를 조합한 root/collection/case/외부 하위 폴더/미완료 수집 5조건도 거부했고 출력이 생기지 않았다. |
| R2 | 기존 `.006` 양부호 제거 반례가 거부된다. 수정 suite의 축·부호별 24조건과 각 로봇/최장 horizon 검사도 통과했다. 다른 c0/u1의 정상 두 로봇 제어군은 적합되고, 한 로봇만 수준 누락·2초 조각만 유지·coast만 유지·fine/unloaded 명령을 loaded deadband 적합에 대입하는 5변형은 모두 거부됐다. |
| R3 | 기존 beam/contact NaN 두 반례는 닫혔다. pose·일반 command·frame·camera label·beam·contact에서 NaN/±Infinity를 검사했고 거부됐다. 일반 command는 두 로봇 모두 명령이 있는 loaded fixture를 사용했다. 초기 명령의 ±Infinity도 거부되지만 NaN은 위 R3b로 남았다. |
| R4 | 가져온 다섯 테스트 함수(시각 매개변수 포함 여섯 사례)의 본문은 이전 리뷰와 AST가 같고 strict xfail만 제거됐다. CI 목록에 정확히 한 번 들어간다. 전체 fit_profile PRBS 오염 불변성·조립 뒤 입력 변조 검사가 모두 통과한다. `inputs.verify()` 두 호출 제거(M4)와 잡음 적합에 PRBS 포함(M5)을 각각 재주입하자 편입된 검사가 각각 1 assertion failure, 오류 0건으로 검출했다. 원본 바이트 복원도 확인했다. |

M4/M5는 합성 archive에서만 수행했다. [변경·복원 해시](review-351b-evidence/mutations.json),
[M4 실패](review-351b-evidence/M4.txt), [M5 실패](review-351b-evidence/M5.txt).

## 고정 기준·등록·승인 경계

- criterion B는 main과 이전 대상 모두에 대해 바이트가 같다.
  SHA-256: `74c312b5eff11e27be2b30d103f6d955f03b0c4b91595dfc9843c366b2c49b5f`.
  frozen validator·r4 candidate·r4 report도 두 기준과 동일하다.
- **B′는 main에 없는 이 PR의 추가 파일**이므로 main과 같다고 보고할 수 없다.
  이전 검토 대상과는 바이트가 같고 SHA-256은
  `3f863f81bea8b4401d980e1c39ec8438b75b34d8f80792d41dbfbcd331f66b33`이다.
  B′의 parent SHA/본문은 현재 동결 B와 일치한다.
- v88 등록과 실행 설계는 main/이전 대상에 대해 동일하다. 비교 범위는
  `harness/rgb_execution_bundle.py`, `zone_final_pair_contract.py`,
  `zone_final_pair_excitation.py`, `zone_final_pair_calibration.py`,
  `configs/zone_final_pair_v88.json`, `zone_final_pair_v88_clearance.json`,
  `calibration/zone_final_pair_v88_contract.json`,
  `simulation_workflows.d/final_pair_v88.json`, 공통 workflow 및 지도 registry다.
- 두 문 지도에서 세 프로필 수집을 모두 합성한 전체 조립도 **PARTIAL**이다.
  세 collection audit는 PASS지만 unloaded `axis_pass`는 세 축 모두 null이며
  unloaded 필수 필드 10개는 frozen B 사유와 함께 null로 남는다.
  `run()`의 unloaded section도 명시적으로 `accepted=False`를 유지한다.
  두 문 자료를 held-out 검증으로 승격하거나 MEASURED_SIM을 방출하는 경로는 확인되지 않았다.

[파일별 비교·해시](review-351b-evidence/static.json),
[archive 검증](review-351b-evidence/archive-verification.json).

`87aa99c3` 이후 제품 코드 차이는 assembler/IO/motion 세 파일이며,
CI 목록·테스트·durations 변경과 main에서 들어온 과거 리뷰 기록도 확인했다.
위 R3b 외의 추가 결함은 재현하지 못했다. `.github/workflows`는 main과 동일하다.

## 검사와 CI

기존 `/opt/anaconda3/bin/python3`를 재사용했다. Python 3.13.5,
NumPy 2.4.4, SciPy 1.17.1, pytest 8.3.4이며 설치·환경 변경은 없다.
BLAS/OMP thread 1, `PYTHONDONTWRITEBYTECODE=1`, pytest cache 비활성화,
임시 basetemp와 physics/render/network/model 차단을 적용했다.
로컬 검사는 CI의 Python 환경이나 실제 물리 검증을 대신하지 않는다.

- 후보의 관련 6개 suite **338 passed** + sharding **68 passed** = 단일 실행 **406 passed**.
- 리뷰 브랜치의 원본 여섯 반례를 `--runxfail`로 독립 재실행: **6 passed**.
  위 338개에 들어 있는 동일 사례이므로 합계에 중복 가산하지 않는다.
- 추가 리뷰 검사: 사례별 최신 결과 합계 **14 passed / 4 strict xfailed**.
  첫 실행의 1 failure는 unloaded r2에 두 번째 명령이 없는 테스트 fixture 오류였다.
  일반 명령 시각 검사만 loaded fixture로 고쳐 재실행해 통과했다. 제품·assertion은 완화하지 않았다.
  초기 명령 ±Infinity/전체 조립 두 검사는 별도 실행했다. 단일 전체 실행으로 표현하지 않는다.
- M4/M5는 의도한 mutant 실패 두 건이며 정상 후보 실패 수에 섞지 않는다.
- durations: **407/409 = 99.51% ≥ 90%**. 유한·음수 아닌 값, shard 합집합도 확인했다.
  작성자가 사용한 CI `36967231516`의 JUnit artifact 8개를 직접 다운로드해
  기존 `refresh_ci_durations.py`로 재생성했고 커밋된 JSON과 **바이트가 동일**했다.
- 대상 head의 [CI 36968509536](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36968509536):
  `offline-regressions` 포함 **33개 check 모두 SUCCESS**.

[관련 JUnit](review-351b-evidence/related.xml),
[원본 반례 JUnit](review-351b-evidence/original.xml),
[첫 변형 실행](review-351b-evidence/variants-initial.xml),
[명령 fixture 수정 후](review-351b-evidence/command-variant.xml),
[추가 초기 시각 검사](review-351b-evidence/initial-extra.xml),
[durations 재생성 근거](review-351b-evidence/durations.json),
[원격 CI 조회](review-351b-evidence/pr-ci.json).

재현은 위 대상 SHA를 새 임시 폴더로 archive한 뒤, 리뷰 브랜치에서 실행한다.

```sh
REVIEW_351_ROOT=<archive> OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python3 -B -m pytest -q \
  tests/test_review_351.py --runxfail -p no:cacheprovider --basetemp=<temporary-1>
REVIEW_351_ROOT=<archive> OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
PYTHONDONTWRITEBYTECODE=1 /opt/anaconda3/bin/python3 -B -m pytest -q -rx \
  tests/test_review_351b.py -p no:cacheprovider --basetemp=<temporary-2>
```

물리·렌더·모델 호출 0회. 실제 수집·성능 검증이나 학생 실행 승인이 아니다.
새 실험 코호트가 없고 공용 outputs 접근 금지 범위이므로 TensorBoard를 시작하지 않았다.
검토용 `/private/tmp/ugrp-review-351b.r28ot662`는 작은 증거를 보존한 뒤 삭제하고
경로 부재를 확인했다. 실제 수집 자료·다른 작업의 프로세스·기본 checkout은 변경하지 않았다.
