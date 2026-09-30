# b-v6h1 분석 봉인 독립 재현성 검토

**판정: FIX BEFORE UNBLINDING.** 코드·등록 pin과 72개 사례의 재현성 검사는 통과했다. 그러나 봉인한 기록 당시 raw 파일 목록을 분석 입력에 연결하는 검사가 없다. 합성 자료에서 동일한 manifest·plan·cases·명령 해시를 유지하고 PF trace만 수정해 최종 판정을 FAIL에서 PASS로 바꿀 수 있었다. 개봉 전에 이 경로를 막고 변경 범위를 다시 검토해야 한다.

- 검토 대상: PR #292, `266118d2c2337bbf1cff507690da131c63e2db11`.
- 실행 기준: `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`.
- 분류기 기준: #299 병합 `1f0e4eb501a8f1b87077df943382fc1f0777dc69`. 이번 fetch에서 `origin/claude/b-v6h-gain`도 같은 SHA이며 후속 커밋은 없었다.
- 허용된 블라인드 메타데이터: `origin/claude/v6h1-confirm-run`의 `e78ef70fb5004fed1dfef1866aaf99bbf0bdda41`, `experiments/2026-10-01-v6h1-confirm-blinded/`의 커밋 파일 3개만 대조했다.
- `AGENTS.md`의 빠른 진행 규칙·실행 버전 관리와 `docs/execution_versioning.md`를 읽었다. shared scratch clone에서 검사했으며 물리·렌더·모델 호출·host lock·블라인드 raw의 목록/내용 접근은 없었다. 아래 PASS/FAIL 반례는 모두 합성 자료의 재현성 검사다. 실제 코호트 결과가 아니다.

## P1 — 기록 당시 raw 무결성을 확인하지 않고 분석 판정을 낼 수 있음

정확한 위치는 모두 검토 SHA 기준이다.

- `analysis/apply_sealed_analysis.py:52–65`: 등록·분석 소스 pin과 raw 경로를 검사한 다음 바로 `classifier.analyse()`를 호출한다. acquisition inventory 확인 단계가 없다.
- `analysis/classify_placements.py:1193–1203`: 기록 당시 값과 대조하는 입력은 plan과 cases.jsonl이다. commands.json은 `analysis/recorder_v4c6b.py:123–126`에서 대조하지만 result/trace의 기록 당시 해시는 검사하지 않는다.
- `analysis/classify_placements.py:1158–1168`: `EvidenceReader.verify()`는 **이번 분석에서 최초 읽은 바이트와 분석 종료 시점**을 비교한다. 분석 시작 전에 바뀐 바이트는 잡지 못한다.
- `analysis/seal/RUN_MANIFEST.json:83`에는 `raw_manifest_json_sha256=07f623b7b30374da25cd0a8d2df62a70bbfdcae47b80279be6e310d7def27950`가 이미 있지만, 현재 분석 경로는 이 파일을 읽거나 해시를 검사하지 않는다.

두 반례를 `tests/test_review_seal_v6h1.py`에 `xfail(strict=True, raises=AssertionError)`로 남겼다. subprocess 오류나 준비 실패를 xfail로 숨기지 않는다.

1. 72개 합성 worker 기록을 만들고 acquisition inventory 파일이 없는 상태로 고정된 분류기와 새 gate를 적용한다. 현재 코드는 `cohort_evidence_issues=[]`, `PASS_A_B_SAFETY`를 낸다.
2. 72개 합성 기록에서 주 시드 60개 trace의 PF x를 1로 두고 inventory와 manifest를 고정한다. 처음에는 B가 FAIL, 전체도 `FAIL_A_B_SAFETY`다. 그 뒤 PF x만 0으로 바꿔 다시 분석하면 B와 전체가 PASS다. manifest·inventory·plan·cases.jsonl·72개 commands.json 해시는 전부 그대로이며, 두 분석 모두 `cohort_evidence_issues=[]`다. 기록 때 inventory를 다시 쓰지 않아도 통과한다.

두 번째 반례의 inventory는 최소 합성 형식이다. 보지 않은 실제 raw-manifest의 schema를 추정한 것이 아니다. 현재 구현은 inventory 파일 자체를 읽지 않으므로 형식과 무관하게 이 구멍이 존재한다. 새 보고서에는 새 trace 해시가 기록되지만 봉인 때 해시와 자동 비교되지 않는다. 따라서 이것은 단순한 보고서 누락이 아니라 **같은 봉인으로 다른 입력의 분석을 승인할 수 있는 재현성 문제**다.

수정 요구: 결과를 분류하기 전에 이미 고정한 acquisition inventory의 바이트 해시를 검사하고, 실제 소비하는 result/trace/case/commands 등 모든 입력을 그 목록의 기록 당시 해시와 대조해야 한다. 목록 누락·미등록 입력·해시 불일치는 분석 통과를 막아야 한다. 기존에 확인한 분석 도중 변경 검사도 유지한다. 실제 inventory 내용 확인은 별도 허용된 개봉 단계에서 수행해야 하며, 이번 검토에서는 읽지 않았다. 현 봉인을 덮어쓰지 말고 필요한 분석 어댑터 변경을 새 봉인 기록으로 남겨 독립 재검토한다.

## 요청한 항목별 재현성 검사

| 항목 | 독립 재계산/검사 결과 |
|---|---|
| 실행 pin | 274/274 파일(추가 6개 포함)의 SHA-256 및 Git blob SHA를 `4c6b439f` Git 객체에서 직접 계산해 일치. 봉인 작업 트리 바이트로 대체하지 않았다. |
| 분석 pin | 288/288 파일의 두 해시를 `266118d2` Git 객체에서 직접 계산해 일치. 분류기·recorder·정의·gate·분석 적용기·봉인 검증기 포함. |
| build() 사례 | registration_run_id만 제거하고 원래 키 순서·숫자 표기를 유지한 literal JSON 배열이 committed plan과 일치. 양쪽 SHA-256 `f476c3d3103daa86fcab4553e9e2cfaf3b0abf500b71b6151554de7cbd2a4269`. |
| 표본 | 941의 C01–C60 60개, 943의 C01–C12 12개, 순서와 설정 일치. 총 72개. |
| A·결측 | 합성 48/60은 PASS, 47/60은 FAIL. 주/보조 시드 결측은 NOT_EVALUABLE, 분모 60 유지. 주 시드 결측 시 Wilson 구간 없음. HOST_ERROR:ENOSPC는 class=null / HOST_SAFE로 남고 성공으로 승격되지 않는다. |
| B·안전 | gate는 pinned classifier의 주 시드 L0/L1 × x/y/yaw 여섯 검사를 호출한다. 943은 별도 집계. 전체 시도의 하드 위반을 유지하며, 합성 안전 위반 veto는 기존 봉인 검사에서 통과. |
| #299 이후 코드 | classify_placements.py·recorder_v4c6b.py·CLASSIFY_NOTES.md·gain_cohort_analysis.py는 `1f0e4eb5` 및 조회한 gain branch tip과 바이트 동일. 이후 미검사 분류기 변경 없음. 새 apply_sealed_analysis/gate는 이번에 따로 검사했다. |
| 봉인 상태 | 원본 Git commit의 등록 값과 비교한다. gate를 48→47로 바꾸고 외부 registration digest까지 재계산해도 거절한다. 기존 tests의 pin 누락/변조·case/state 변경·기존 seal 덮어쓰기 거절도 통과. |
| 분석 명령 | REGISTRATION_PLAN.md:43–52에 정확한 `apply_sealed_analysis --seal-commit … --prereg … --raw … --output …` 명령이 있다. 적용기는 로드할 분석 파일 288개의 현재 SHA-256까지 확인한다. 다만 위 P1 raw 검사 연결이 빠져 있다. 실제 명령은 블라인드 raw에 실행하지 않았다. |

실행 closure를 별도로 확인하려고 worker entry point에서 AST import graph를 만들었다. literal dynamic skill `harness.wrist_zone_skill_v9`를 포함한 실행 쪽 205개 및 분석 쪽 211개 Python 경로에서 pin 누락은 없었다. 문자열로 선택되는 분류기·recorder·chain/gain 분석기는 명시적으로 포함했다. 이것을 임의 동적 import의 완전성 증명으로 보지 않는다.

정확한 `4c6b439f` checkout에서 seed 941/943 사례 두 개의 `run_case()`를 **MultiMasterPiProductionV2.__init__ 본문 진입 직전** 중단하는 Python audit/profile 추적도 했다. 실제 읽힌 저장소 파일 122개는 모두 실행 pin에 있었다. 그중 비 Python 입력은 `maps/zones/zone_wide_door.json`, `zone_wide_door_tags_v2.json`, `zone_wide_door_tags_v2_dock_v3.json`, `sim/masterpi_scene.xml`이다. 물리·렌더 함수 호출은 0건이며 같은 중단 검사를 제출 테스트에서도 재현한다.

관측 범위의 **저장소 입력 누락은 0개**다. 외부 읽기 202개 중 200개는 Python 표준 라이브러리/설치 패키지(83/117), 2개는 검토용 committed plan/prereg 사본이다. 저장소 외부 읽기 경로 전체는 `analysis/review_seal_v6h1/evidence.json`의 `worker_trace.external_file_reads`에 남겼다. 이들은 274개 저장소 pin으로 고정되지 않으며, Python audit는 native loader의 모든 파일 접근을 관측하지 않는다. 따라서 전체 worker 실행·native 라이브러리·환경의 완전 재현을 승인하지 않는다. 설치 환경의 동일성과 드라이버 본문도 이 블라인드 검토에서 검증하지 않았다.

정적 조건도 확인했다. 고정 cases는 등록된 b-v6h1/teacher chain, diag_patch·door_relax·progress_relax·staging_bypass 없음이며 CameraRobotPort의 raw motor/servo 경로를 쓴다. 별도의 REAL high-level action 경로를 강제로 import하면 pin 밖의 red_block 관련 파일이 나오지만, 해당 고정 cases가 그 경로를 호출했다는 근거는 없으므로 실행 누락으로 판정하지 않았다. 동적 문자열 로더가 존재한다는 이유만으로 완전 closure를 주장하지도 않는다.

## 공개 내용 대조

봉인 전 블라인드 기록, 얇은 driver, `--prereg` 없는 unsealed_stage_probe admission, 새 실행 권한 없음, 실행 전 사전 등록으로 소급하지 않는다는 공개는 허용된 metadata와 일치한다. 다음 해시를 Git 객체에서 직접 확인했다.

| 메타데이터 | SHA-256 |
|---|---|
| RUN_MANIFEST.json | `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210` |
| plan.json | `d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026` |
| placements_seed943_first12.json | `9c2cc220901084f4211952b57ccb4779570d61c926cc8bbbbf9c1f25be310b0a` |

cases.jsonl `8e7837cbc948abcd7a29a6b81272870ec7ab716c1aba87f018cd3aca655d1836`와 driver `7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56`는 **커밋 metadata의 진술**로만 확인했다. 실제 파일·명령 궤적·코호트 결과는 확인하지 않았다. 기록자가 결과를 보지 않았다는 진술도 metadata 공개 내용이며 독립적인 행위 감사로 바꾸지 않는다.

274개 실행 경로를 봉인 tree와 비교한 차이는 10개이며 `notes.working_tree_differences`의 목록·원본/봉인 해시와 정확히 일치한다.

- main 변경 6개: `harness/zone_main_budget.py`, `harness/zone_study_llm_driver.py`, `harness/zone_study_llm_transport.py`, `scripts/agent_lock.py`, 이후 추가된 `harness/vision_loc_protocol.py`, `sim/workflow_manager.py`. 모두 공개한 main 병합 부모 `f5cd3a2b` 바이트와 같다.
- 등록 metadata 변경 4개: `PREREG_DRAFT.md`, `REGISTRATION_PLAN.md`, `build_prereg_v6h.py`, `scripts/zone_pair_v6_contract.py`의 CURRENT_REVISION. 실행 pin은 계속 `4c6b439f`를 가리킨다.
- 현재 preview의 `--verify`는 72 runs / 276 sources를 반환한다. 추가된 main 의존성 2개 때문이다. 이를 실행 274개와 섞지 않았다.

## 오프라인 검사와 보존 범위

기존 환경 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`(이번 검사 Python 3.12.13)을 재사용했다. 새 환경이나 host lock은 만들지 않았다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q -rx tests/test_review_seal_v6h1.py
# 6 passed, 2 xfailed (두 xfail은 위 P1의 현재 재현성 반례)

/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q --runxfail \
  tests/test_review_seal_v6h1.py -k 'missing_acquisition or trace_edit'
# 의도적으로 xfail을 해제하면 동일한 두 AssertionError가 발생
```

기존 봉인·blinded-manifest·#299/299b/299c/299d/299g·classifier properties·recorder·classification 검사 456개도 실행했다. 최초 440 passed / 10 xfailed / 6 failed였고, 6건은 검토용 sparse clone에 없던 `prereg_v6e.json`과 공개 `recorder_audit.json` 두 fixture 때문이었다. 해당 SHA의 원본만 복원한 뒤 그 6건 모두 통과했다. 따라서 이 선택 집합의 검증 결과는 **446개 통과, 과거 수정 전 SHA `58dc07e7`의 알려진 반례 10개 expected failure**다. 재실행을 새 사례로 합산하지 않았다. 기존 suite의 물리 step·실모델 worker·network guard 집계는 모두 0이었다. PR 작성자의 555개 전체 검사 재현으로 표현하지 않는다.

변경 파일은 검토 문서·독립 검사·작은 재현성 증거뿐이다. 구현·등록 JSON·`.github/workflows`는 수정하지 않았다. scratch clone/합성 자료는 결과를 보존한 뒤 삭제했다. 리뷰 브랜치만 커밋·push하며 #292에 한 번에 전달한다. 병합·개봉·기본 checkout 갱신은 이 검토 범위가 아니다. 새 코호트 결과가 없어 TensorBoard 변환/표시도 하지 않았다. UGRP의 Google Drive 제외 지침을 지켰다.
