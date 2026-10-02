# PR #355 독립 검토 — MERGE AFTER FIXES

- 대상: **54d5e28b3439a4ba3624d7fee01d02b083ac33ae**, `codex/calib-fast-guard`.
- 비교 main: **6f8460ad61ed858025a9e1d5d6ce77d7b92d9b1f**.
- 검토자: Codex, `codex/review-355`. 구현 브랜치와 분리하여 `git fetch`, `git diff`, `git archive` 추출본을 검사했다.
- 판정: **MERGE AFTER FIXES**. 아래 P1 두 건을 수정한 새 SHA에서 재검토해야 한다. 현재 SHA의 병합·v91 수집 시작을 승인하지 않는다. 사용자 지시대로 병합하지 않는다.
- 렌더링·모델 호출·새 코호트·CPU/wall 성능 측정 없음. 기존 raw는 완료된 unloaded/r6 fine만 읽었으며 실제 실행기·공용 잠금·다른 작업 프로세스에 조작을 가하지 않았다.

## P1 R1 — 같은 v88/v90 ID의 실제 provenance가 바뀌며, 옛 해시 치환이 회귀를 가린다

지적 위치(대상 SHA): `scripts/agent_lock.py:48`, `tests/test_review_352.py:49`, `tests/test_zone_final_pair_heldout.py:88`.

`harness/zone_final_pair_contract.py:192–220`의 정적 import closure는 함수 안의 `scripts.agent_lock` import까지 포함한다. `harness/zone_final_pair_heldout.py:84–98`도 그 closure를 상속하고 현재 파일을 다시 해시한다. 따라서 **v88/v90 모두 `source_sha256["scripts/agent_lock.py"]`를 실제 기록한다.** plan에는 별도의 파일별 목록 대신 이 값을 포함한 실행 bundle의 `bundles_sha256`이 들어간다.

변경된 실제 파일 SHA-256은 다음과 같다.

```text
scripts/agent_lock.py
old 709db3d87e4d2369171aba10ce3c64b7c8be254e2de7115ae608a022b1783dce
new 9fd7ef3dc9a2f781b542342c81a4067be88a001c1b01a4fd83c26dbd48adc458
```

v88의 P03 1지도·carry 3지도·보정 3종, v90의 unloaded 2지도, 총 **9개 유효 조합**을 base와 PR에서 독립 생성했다. 이 PR이 바꾼 파일 중 해당 bundle closure에서 달라지는 파일은 모두 **위 한 파일뿐**이다. 각 조합의 bundle writer SHA, canonical bundle digest, plan writer SHA, plan의 실행 bundle digest가 모두 달라진다. 모든 원값은 [hash-diff.json](review355/hash-diff.json), 전체 inventory는 [base-hashes.json](review355/base-hashes.json)과 [head-hashes.json](review355/head-hashes.json)에 있다. `source_sha` 인자는 두 실행 모두 `a` 40개로 고정했으므로 커밋 식별자 차이를 잘못 세지 않았다.

완료된 실제 unloaded/r6 fine bundle에도 옛 `709db3d8…`가 있으며, 둘 다 수집 SHA `747d2b9f1eb43e21804ccef58fff4db241d1a844`다([raw-source-hashes.json](review355/raw-source-hashes.json)). 기존 raw를 새 main에서 읽는 것 자체가 기존 raw 해시를 바꾸지는 않는다. 문제는 병합 후 main에서 **새 v88/v90 실행**을 만들 때 같은 ID로 다른 closure가 생성되는 것이다.

`historical_lock_receipt`는 생산 경로가 내보내는 새 해시를 테스트 안에서 옛 해시로 바꾼다. 치환 없이 기존 3종 bundle/plan writer 검사를 실행하면 **6/6 실패**한다. 실제 closure를 비교하는 추가 9개 반례도 실패한다. PR 문서가 소스 변경을 공개한 점은 확인했으나, 기본 acquire/status/release 반환값 비교로 **동결된 실행 바이트 보존**을 입증할 수는 없다. R2처럼 기본 배타 의미도 슬롯이 존재할 때 달라진다.

### execution_tree와 소비자 영향

- `sim/workflow_manager.py:74–108,493,529`의 `source.execution_tree`는 넓은 실행 파일 inventory다. 기존 항목 중 `agent_lock.py`, `run_ci_tests.py`, `ci_test_durations.json`이 바뀌고 v91 파일 8개가 추가된다. 정확한 11개 경로·해시는 hash-diff에 있다. 이번 두 트리의 해시는 `76873b6b09e2ec1bf5e9f41abea7a9f867594b1f1b5f8f074e1024ab6d8da930` → `d670bdaba0530d7afef81e841d3ba8b242d1b7e0aa5f88eb637b5637c3081d71`; 누락 tracked 실행 파일은 양쪽 0개다. 이 전체-tree 변경은 새 파일 추가만으로도 생기며, 그 자체를 별도의 물리 회귀로 해석하지 않는다. 과거 실행 tree를 재현하려면 과거 SHA를 고정해야 한다.
- **#351**: `scripts/final_pair_calibration_io.py:152–163`은 v88 ID·물리 설정과 plan↔bundle 내부 digest를 검증하지만 `source_sha256`을 등록 소스와 대조하지 않는다. 합성 v88 bundle의 lock 해시를 0 64개로 바꾸고 plan/manifest를 일관되게 갱신해도 `load_collection()`이 통과했다. 따라서 새 해시를 자동으로 거부해 주는 소비자가 아니다. 이 결과는 raw audit 통과이며 MEASURED_SIM 조립/승인 성공을 뜻하지 않는다.
- **동결 criterion B**: `scripts/validate_consumer_criterion_b.py:118–125`는 v88 ID와 40자리 source SHA 형식을 확인할 뿐 파일별 source hash 비교가 없다. v88 합성 입력에 임의 lock hash를 넣어도 `load_case()`가 통과한다. 반면 **v90와 v91 ID는 둘 다 `criterion B requires a v88 unloaded collection`로 즉시 거부**한다. 이는 v90부터 남아 있던 소비자 연결 문제이며 R1과 구분한다. v91 수집을 B가 수용했다고 보고하거나 v88로 이름만 바꿔서는 안 된다.

### 필요한 수정

1. 우선안은 `agent_lock.py`를 원래 바이트로 되돌리고, v91 슬롯 구현을 **새 모듈**로 분리하는 것이다. 옛 파일에서 새 모듈을 import하면 legacy closure가 다시 늘어나므로 피한다. 가짜 옛 해시를 생산 코드에 넣지 않는다.
2. R2도 동시에 해결해야 한다. 새 모듈로 옮기는 것만으로는 충분하지 않다. 예를 들어 v91 그룹 전체 수명 동안 기존 `physics` 잠금을 보유하는 명시적 coordinator를 두면, 옛 실행기도 공용 자원 점유를 볼 수 있다. 기존 잠금이 비어 있을 때만 그룹을 열고, 그룹 가입·실제 소유 PID·마지막 종료·stale 정리를 검증해야 한다.
3. 공용 helper 자체 변경이 필요하면 실행 source closure의 새 버전을 등록하고 옛 v88/v90 실행 경로·영수증을 유지해야 한다. 동결 소비자의 변경은 별도 명시적 호환 계약과 독립 검토 대상이다.
4. 옛 해시 치환/파일 제외를 제거하고 실제 writer 바이트 검사를 복구한다. [반례 테스트](../../tests/test_review_355.py)의 R1 검사가 새 SHA에서 실제 통과해야 한다.

## P1 R2 — 기존 배타 physics 잠금이 SIM 슬롯을 배제하지 못한다

지적 위치(대상 SHA): `scripts/agent_lock.py:55–59,108–119`; `tests/test_agent_sim_slots.py:25`.

기존 `acquire()`의 `timing_sensitive` 기본값은 false다. 이 표시는 기존에는 오프라인 테스트에 경고하기 위한 값이고, 기존 physics 디렉터리 잠금은 배타적이다(`CONTRIBUTING.md:96`, 기존 PHYSICS_HANDOFF 명령에는 해당 플래그가 없다). 새 코드는 다음을 모두 허용한다.

1. 기본 인자로 `physics`를 획득한 다른 실행이 살아 있는데 v91 `acquire_sim_slot()` 성공.
2. v91 슬롯이 살아 있는데 기본 `acquire()`로 다른 실행의 `physics` 획득 성공.
3. v91 슬롯 뒤, main/base SHA에 고정된 **옛** `agent_lock.py`가 `timing_sensitive=True`로 `physics`를 획득해도 성공. 옛 도구는 `sim-*`/`.admission.lock`을 모르며 확인할 `physics` 디렉터리도 없다.

3개 모두 임시 디렉터리와 자기 테스트 PID만으로 재현했다. 실제 공용 잠금은 건드리지 않았다. PR의 timing 양방향 race 검사는 **새 helper끼리**만 검사하므로 세 번째 경우를 놓친다. 기본 lock compatibility 검사도 슬롯 없는 경우만 대조한다.

필요한 동작은 모든 기존 배타 실행과의 상호 배제다. 단순히 새 문서에 `--timing-sensitive`를 추가하거나 새 helper의 `if` 두 군데만 바꾸면 이미 SHA가 고정된 옛 실행기의 역방향 획득 문제는 남는다. R1의 파일 보존과 함께, 옛 도구에서도 볼 수 있는 배타 소유권과 그룹 수명을 설계하고 세 반례를 통과시켜야 한다.

## 나머지 요구사항 검증

### Guard

[raw-equivalence.json](review355/raw-equivalence.json): PR이 지목한 완료 raw 두 개에서 verifier를 `--benchmark` 없이 다시 실행했다.

| 원본 | 비교 행 | 행별 불일치 / abort | 50 ms 순차 비교 |
|---|---:|---:|---|
| unloaded r1 | 7,401 | 0 / 0 | 7,401 일치, 합성 변위 abort 7,286 |
| fine r6 | 7,401 | 0 / 0 | 7,401 일치, 합성 변위 abort 7,286 |

각 행의 예외 종류/문자열, `clearance_min`의 float hex, hold 호출, eval_only abort 경로/내용, 이전 geometry 좌표 바이트를 비교했다. raw/bundle/result SHA도 PR 기록과 같다. `render=False`, `world.renderer is None`, full qpos/qvel 설치 후 `mj_kinematics`만 호출했다. 50 ms 기록은 0.25 ms substep을 복원하지 않으며, 순차 변위 abort를 실제 수집 실패로 계산하지 않는다. 처리율/속도 주장은 재측정하지 않았다.

추가 반례 테스트에서 정확히 **0.35 m**, 그 양쪽 상태, 정확히 **0.01 m** 변위와 바로 다음 float, NaN geometry, geometry 개수 증가, loaded의 beam wall/NaN/jump를 검사했다. 모두 기존 가드와 동일한 중단 이유와 eval_only 기록이다. loaded는 guard 비교용이며 v91 실행기가 loaded 수집을 허용한다는 뜻이 아니다.

`sim/final_pair_fast_guard.py:137–164`: model/data 객체, 수치 time, qpos/qvel 원시 바이트, geometry/body 위치, geometry 개수·반경이 같아야 post 상태를 재사용한다. time 한 ulp 변화·qpos/qvel의 signed zero 변경에서도 pre-check 생략이 취소된다. post-check는 매 substep 실행하고, 캐시는 `advance_to()` 호출 내부로 한정한다. 기존 PR의 invalidation/post-step-abort 검사도 재실행했다.

### 출력·기록·stale

- 두 슬롯은 별도 이름으로 공존하며 owner/branch/live-PID 확인을 유지한다.
- 두 지도에 같은 출력 경로를 전달한 TOCTOU 반례에서, 첫 exists 검사 뒤 다른 실행이 경로와 plan을 만든 상황을 주입했다. `mkdir(exist_ok=False)`가 두 번째 실행을 차단했고 첫 plan 바이트가 보존됐다. 기본 인계 명령도 서로 다른 지도 경로를 사용한다.
- 기존 fake 완료/중단 수집 테스트에서 plan의 host_start, 사례/전체 result의 host_start/end, loadavg 3개, concurrent holder 목록과 종료 result 해시를 확인했다. 새 실제 동시 수집 결과는 없다.
- 살아 있는 다른 owner의 슬롯은 `--stale`로 해제되지 않는다. 죽은 슬롯은 실행 진입·동일 이름 재획득·새 timing-sensitive physics 획득을 막고, 명시적 stale 해제 뒤에만 재개된다. 불완전 owner 기록은 자동 복구하지 않고 차단한다.
- 슬롯이 없는 기본 API의 반환/오류/해제 영수증 비교는 통과하지만, 전체 배타 의미 보존은 R2 때문에 실패다.

### 등록·일정·라벨

- v90/v91 fake 전체 수집에서 두 지도 모두 schedule writer 바이트 SHA-256 **`8e9a126cfdcbc5961cacac4165b76ac65da3310aa40b758f0590d999917813db`**, 명령 순서, pose **7,401개/0.05 s**, RGB **1,851회/0.2 s**가 같다.
- measurement/timing/runtime_interlock/clearance_preflight, seed 911, 370 SIM s/reset ≤5 s, floor_light_v1, cargo_noslip_v1, weld OFF, sensors OFF가 v90과 같다.
- plan/bundle/사례·전체 result의 `HELD_OUT_VALIDATION`, `training_eligible=false`, `teacher_only=true`를 유지한다. 학생/실물/criterion B 성공 판정은 없다.
- [numbering.json](review355/numbering.json): main 및 열린 #355/#353/#339/#309/#293의 정확한 head를 다시 조회했다. #355 제외 최댓값 v90 / workflow 3.2.0이며, **v91 / 3.3.0 충돌 없음**. harness의 선언과 configs의 모든 workflow fragment도 확인했다.

## 실행 기록과 범위

검증 집계는 [verification.json](review355/verification.json)에 기록한다. 관련 **358 passed**, 리뷰 정상 동작 검사 **21 passed**, workflow **3 passed**로 중복 없는 최종 정상 검사는 **382 passed**다. `counterexamples.xml`의 **18 strict xfail**은 미해결 결함이며 통과로 합산하지 않는다. `--runxfail`로 R1/R2 **18개 모두 실제 실패**를 별도 확인했다([unmasked.txt](review355/unmasked.txt)). 리뷰 테스트는 main에 v91이 없으면 모듈 단위 skip하며, 대상 PR archive에 복사하여 실행한다.

재현 예시(기존 Python 환경 재사용):

```bash
SCRATCH=$(mktemp -d /private/tmp/ugrp-review355.XXXXXX)
git archive 54d5e28b3439a4ba3624d7fee01d02b083ac33ae | tar -x -C "$SCRATCH"
cp tests/test_review_355.py "$SCRATCH/tests/test_review_355.py"
cd "$SCRATCH"
# git show만 필요한 역사/반례 테스트에만 GIT_DIR을 지정한다.
GIT_DIR=/Users/changmin/projects/ugrp/.git /opt/anaconda3/bin/python3 -B -m pytest -q tests/test_review_355.py
GIT_DIR=/Users/changmin/projects/ugrp/.git /opt/anaconda3/bin/python3 -B -m pytest -q tests/test_review_355.py --runxfail -k 'legacy_registered_source or legacy_writer_bytes or exclusive_lock_excludes or pinned_legacy_timing'
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m scripts.verify_final_pair_fast_guard --output /private/tmp/review355-raw-equivalence.json
# git init/add를 수행하는 workflow fixture에는 GIT_DIR을 넘기지 않는다.
/opt/anaconda3/bin/python3 -B -m pytest -q tests/test_simulation_workflow_manager.py -k 'catalog_has or every_catalog or source_fingerprint'
```

초기 검토 실행 문제도 보존한다. sim 환경에 SciPy가 없어 소비자 검사 3개가 import 실패했고, 기존 Anaconda 환경으로 바꿨다. 그 뒤 리뷰 fixture 반환값을 잘못 unpack한 오류 1개를 수정했다. 두 초기 JUnit은 각각 `counterexamples-missing-scipy.xml`, `counterexamples-fixture-error.xml`이다. workflow fixture의 첫 실행에서는 상속한 GIT_DIR 때문에 합성 `calibration/important.json`이 기본 checkout index에 추가됐다. 원래 HEAD에 없는 해당 fixture 항목만 제거하고 기본 checkout clean을 확인했으며, GIT_DIR 없는 격리 fixture로 3개 검사를 다시 통과했다. 기본 소스/HEAD 변경은 없다.

새 학습·평가 코호트가 아닌 코드 회귀/완료 raw의 재생 검토이므로 TensorBoard 변환·서버·대시보드를 새로 만들지 않았다. Drive도 사용하지 않았다. `.github/workflows` 변경은 대상 PR 및 리뷰 작업 모두 없다. 대상 head의 GitHub CI **33 checks SUCCESS**를 조회했으며 [pr-checks.json](review355/pr-checks.json)에 보존했다. CI 성공은 이번 실제 provenance/잠금 반례를 해소하지 않는다.

추출 디렉터리 `/private/tmp/ugrp-review355.rvwkdn`은 모든 검사 종료 후 삭제했고 부재를 확인했다. 삭제 전 PR 변경 31개 파일이 대상 SHA와 바이트 동일함을 다시 확인했다. 병합은 수행하지 않았고 기본 checkout 갱신도 수행하지 않았다. 기본 checkout은 `2523269857596ffdd1a8cda9814a6e92f399f1da` 그대로이며 clean 상태를 확인했다.

## 실제 writer 해시 변경표

전체 canonical/실행 bundle digest는 hash-diff.json에 있으며 아래는 파일 writer SHA-256이다.

### zone-final-pair-v88/zone_wide_door_geometry_v3/p03

```text
bundle_writer_sha256
old c4695cc724fdc5c3c0925075eebe18db316f4af2cc43b2f4d63a50f9e3ec4865
new f07ec9cfd4aaa19b297b05f90cdeead6bafca87afdb1f82bb9f7b06836af6c26
plan_writer_sha256
old bbdc74576d88271dde0bad6390e186ee56ba0393cfa163b0e3c076a14fb26c93
new 81f6b75fd839c1c17a7ebdaaebaf253dde8ffd0ca2c2d03fcdd459810949397e
```

### zone-final-pair-v88/zone_wide_corridor_final_v3/carry

```text
bundle_writer_sha256
old 55e6fb03c8e962a60e498c298a001f27f257e8111d325e4e52bc6dc8ab8d48a7
new fb2f7e247fb16811a5035c0fa9666db9ea6b6400688971483245ed607896c847
plan_writer_sha256
old c9bfe90bf8b513f99e1c33127eeb82781e20664ec7c28c2a860bebe113c7acd1
new 2362619abb598d6db6951aaa5d6c46a12e07b03148fce5a9494f41701c2a9c28
```

### zone-final-pair-v88/zone_wide_door_geometry_v3/carry

```text
bundle_writer_sha256
old c5c064ff6a835ce8987019a9eb37456ab1e7f439bf2801a4c100308a01dfaf12
new 4bd6964764feb2f83f4252f21dd6d76fec25bed282461bac57bf3bce7bf58201
plan_writer_sha256
old 2dd1df653db33a8950d46a7e5e0165d90f4f65a34c88cd29fd3d2430959d3e62
new a60edada48b2e1a46f808c05cd99a1ebbd5481c131eb0cfd88c9afb1df65cd64
```

### zone-final-pair-v88/zone_wide_two_doors_final_v3/carry

```text
bundle_writer_sha256
old 6c7dbb3902f560022b9666a1419718b819aa762648df7a7b6192ea61e51a2bcc
new 6224fbe28462501bfb6b72f9e0756d6b90278c23fa733000f330c50e437b2cab
plan_writer_sha256
old 2bdf6fd08f30f275c0216b7b1fd458d407f5e2e160304d1bf4a3838960836c03
new b1bc444197e3e3464db1c1a28d2dec6ec041ff3c864ae6e9ee8240538d9192f2
```

### zone-final-pair-v88/zone_wide_two_doors_final_v3/calibration-unloaded

```text
bundle_writer_sha256
old 1f4685fe5240ab91bb1982b6db8e3ec63b5689959e9afc787b2c38f55aaf3d94
new e0fd84b56ea346d056d42efd853a86603bd020ddb5610fd16a68f58fd5666958
plan_writer_sha256
old 7f6d665104d953ce3ea8751b652963c31ab902ac33574d7acdcd86e54e8d8d36
new 87c687578dbf6ff03fefcd915efb07f4e0ce11c8a8afc26340e7fb0dfbcca79c
```

### zone-final-pair-v88/zone_wide_two_doors_final_v3/calibration-loaded

```text
bundle_writer_sha256
old 10605b2b433f8acb923e6802b490cb32c19d9c7222324b9ebe74f470ca7721d3
new 6587ed33c70b98fbe68f716229fdefbd5c98594cf252793f48a63f985b9be506
plan_writer_sha256
old ac640e5b194da11d1b58df676630aee058b0b8c9f0a89eff8e42984fd7b8c5dd
new d6d29b29069a98f9ecebfe4cc7e01aece52454339fd31bb2598eeeb44d2558fe
```

### zone-final-pair-v88/zone_wide_two_doors_final_v3/calibration-fine

```text
bundle_writer_sha256
old ab0bb9a4ba91a88ba316906ffc59e01b42ed882b676101ccda5019f71fae6bd5
new 1bbf2a2b3da32efe4de610cee3662488e595566ec88aca862b908c0aebd1a0c7
plan_writer_sha256
old fea4037700fa0a67305968fdef1f653e24321358fb13babf2fe8280848a8c176
new 61c8c03711925206ac469bf5fa704837ca409bb8a285a4f83143de99a7c372ad
```

### zone-final-pair-v90/zone_wide_door_geometry_v3/calibration-unloaded

```text
bundle_writer_sha256
old 5945a4cc618131e712e95e0786e6cc6e0ad159bd766544eb634a5868bccfda81
new ff523d6ffe72df88e0e9d85702e2bee1420f00b6d590f8350e947df7a1ed2e72
plan_writer_sha256
old 01ef1aee0e69785e44790b6ff55a8538d7a7eaeaa760d010cab122409de920c5
new fca21f425e8184572643c5965e9722072c0b8f54dfc651257a09353b885a079f
```

### zone-final-pair-v90/zone_wide_corridor_final_v3/calibration-unloaded

```text
bundle_writer_sha256
old 1a2e7cad42fa9ec8b7f9a2114236fd325ea94ac99b247ccaae9c4c2d6b4f9601
new 41ce050ed91a22d3ff6ba8d13a25e7974f4355b98df3f4a13f17ee4bf3c8c264
plan_writer_sha256
old f75be8420c05957a1d383736b220789a5b233ed7f5d026a222c6b5c5f54ac5a3
new 75fff781bd143c5159c1b6b9d7a537ea554d55a293770f9020113f1af0095298
```
