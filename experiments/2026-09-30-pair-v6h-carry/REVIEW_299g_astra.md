# PR #299 수정 확인 독립 검토 — 2026-10-01

**판정: MERGE AFTER FIXES.** 검토 대상 `3a136bc821f912af893f414ea2224db8742b880e`는
[이전 검토](REVIEW_299d_astra.md)의 구체적 반례 10건을 실제 원인 검사로 막는다.
그러나 **기록 사이의 시간 선후관계 누락 1개 P1**이 남았다. 실행 전 entry/submit을
운반 시작 뒤로 옮겨도 PASS를 주며, 등록 reader와 새 manifest reader 모두 집계한다.
별도 run manifest 경로의 계획·명령 해시 검사는 통과했으며, 이 경로가 증거 규칙을
완화한 것은 아니다. 공통 per-case 시간 검사의 남은 문제다. **미봉인 실행을
사전 등록된 확증으로 승인하거나 실제 블라인드 결과를 판정한 것은 아니다.**
표준 러너 대신 쓴 드라이버와 실행 당시 미봉인 상태는 아래 내용대로 prereg/seal에 밝혀야 한다.

| 대상 | 고정 값 |
|---|---|
| 비교 기준 | `58dc07e7607e86dd526bc0defe9374489f0ce931` |
| 두 P1 수정 | `d434fba95364bcf4a994ccf01943301c23989a7e` |
| 최종 검토 후보 | `3a136bc821f912af893f414ea2224db8742b880e` |
| 메타데이터 원 커밋 | `e78ef70fb5004fed1dfef1866aaf99bbf0bdda41` (`origin/claude/v6h1-confirm-run`) |
| 메타데이터의 실행 source | `4c6b439f3f7c9a147c901f8b260a1e214d4eb396` |
| 리뷰 브랜치의 이전 HEAD | `a090317851811360815b3f8be9f8388764a3e2fe` |

이하 `C`는 `analysis/classify_placements.py`, `A`는 `analysis/recorder_v4c6b.py`이며
줄 번호는 최종 검토 후보 기준이다. `git fetch`, `git diff`, 후보의 `git archive` 사본과
기존 Mac Python 환경에서 검사했다. 물리·렌더·모델 실행, 호스트 잠금, workflow 편집은 없다.
블라인드 raw 디렉터리를 열거하거나 읽지 않았다. 허용된 메타데이터의 경로 문자열도 따라가지 않았다.
D1–D5의 결정은 그대로 적용했다.

## P1 / 299g-R1 — 실행 전 snapshot·제출이 운반 시작 뒤여도 PASS

위치: **`C:921–931,932–970`**. 새 chronology 검사는 stage snapshot끼리와
각 로봇의 timeline/boundary끼리만 순서를 검사하고 두 묶음의 선후관계를 연결하지 않는다.
`submit_t`도 이 순서 검사에서 빠져 있다. 실제 고정 producer
`scripts/run_pair_stage_probes.py:641–651`은 teacher lift → submit 예약 → entry snapshot
→ `host.run` 순서이며, `448–452`는 submit 시각 이후에만 pair 명령을 발행한다.
따라서 이 producer의 entry/submit이 이미 기록된 L0 시작보다 뒤일 수 없다.

공개 S01 복사본의 원래 시각은 teacher/entry **5.85 s**, submit **6.05 s**,
L0 start **6.10 s**, L1 start **35.90 s**, L1 end **60.30 s**다.
좌표·원 leg 경계·trace·거리 요약·계획·식별자는 유지하고 다음만 바꿨다.

| 합성 변형 | 최종 후보 결과 |
|---|---|
| `gt_at_entry.t`만 60.20 s로 | **PASS_CLEAN / evidence_valid=true / issues=[]** |
| teacher와 entry의 t를 모두 60.20 s로 | **PASS_CLEAN / evidence_valid=true / issues=[]** |
| result와 row의 `submit_t`를 모두 60.20 s로, result.row도 일치 | **PASS_CLEAN / evidence_valid=true / issues=[]** |

이는 서로 다른 시각의 좌표가 같아야 한다는 요구가 아니다. producer가 실행 전에
남긴 시각이 이미 실행한 carry 뒤에 놓이는 불가능한 순서다. 세 변형 모두 trace 창
안이고 stage snapshot 자체의 순서도 맞으므로 현재의 독립된 검사들을 통과한다.
실행창 밖의 61.3 s 반례를 고친 것만으로 이 안쪽 시간 역전이 막히지는 않는다.

실제 reader 경로에서도 확인했다. 등록 schema의 합성 기록에서 entry만 늦추면
**pass_placements=1**, 새 run manifest 경로에서도 entry를 L0 시작 0.25 s보다
늦은 **2.91 s**로 바꾸면 **pass_placements=1**이다. 후자의 source/plan/commands
pin은 그대로 유효하고 cohort issues도 없다. 두 재현 모두 72슬롯 중 1개 기록과
71개 미분류이므로 전체 verdict는 NOT_EVALUABLE이다. 전체 확증 PASS를 만들었다고
주장하지 않는다.

수정 조건: 실제 저장된 teacher/entry/submit과 각 로봇의 첫 carry 시작을 같은
SIM clock의 의미상 선후관계로 연결해 모순을 INVALID/null로 남긴다. 없는 관측을
만들거나 정상 비동기 로봇을 같은 시각으로 강제하지 않는다. HOST 부분 기록과
양성 하드 위반 우선순위는 유지한다. 공개 11건·정상 합성 기록이 계속 통과하고
아래 5건이 올바른 사유로 거부되는지 다시 확인한다.

재현: `test_current_cross_stream_time_reversal_cannot_pass` 3건,
`test_current_registered_reader_cannot_count_late_entry` 1건,
`test_current_run_manifest_reader_cannot_count_late_entry` 1건. 모두 **현재 후보의
strict xfail**이며 xfail 해제 시 판정 assertion으로 실패한다.
구체값은 `analysis/review_299g_validation/cross_stream_counterexamples.json`에 보존했다.

## (a) d434fba9 — 두 P1 수정 확인

| 이전 반례 | 현재 결과와 직접 거부 사유 |
|---|---|
| 원 L1 끝 좌표만 1 m 이동 | INVALID/null; `source/derived end_error_m contradiction` |
| 원 L1 시작 좌표만 1 m 이동 | INVALID/null; `source/derived travel_m contradiction` |
| r1/r2 × L0/L1 시작 증거 삭제 4건 | INVALID/null; 어댑터에서 해당 start 키 부재를 직접 검출 |
| L1 원 시작 61.3 s, 끝 60.3 s | INVALID/null; `r1 leg_start: outside recorded window` |
| 더 이른 로봇 끝 시각 −1 s | INVALID/null; 원 경계의 기록창 위반 |
| gt_at_stop이 trace보다 100 s 뒤 | INVALID/null; 원 stage 시각의 기록창 위반 |
| 등록 reader에서 끝 좌표 모순 | PASS 집계 1→0; 해당 시도의 source/derived 거리 모순 |

새 리뷰 테스트는 위 **10건을 현재 코드에서 모두 통과**시키고 거부 사유도 검사한다.
동일한 데이터와 정상 양성 대조를 수정 전 classifier/adapter 두 Git blob에 넣으면
**10/10 판정 AssertionError**다. import/인수 오류를 결함 검출로 세지 않았다.
`tests/test_classify_review_299g.py`의 역사적 strict xfail 10개는 명시적으로 **수정 전
58dc07e7**에만 붙였다. 위 299g-R1의 현재 후보 xfail 5개와 별도로 구분한다.

`C:853–898`은 실제 `pair_chain_probe.chain_legs`와 같은 더 늦은 snapshot 선택 및
XY 계산을 사용해 거리 7항목을 대조한다. 동시각에는 정렬된 robot 순서가 유지된다.
`C:900–970`과 `A:140–146`은 양쪽 start/end, timeline, GT, derived 경계와 stage
시각을 검사한다. 비동기 로봇·같은 시각 전이·매핑/leg 배열 순서 변경 양성 대조는 유지된다.
거리 tolerance 1e-9 m는 직렬화 비교용이며 100 mm 과제 문턱을 바꾸지 않는다.

`check_299d_mutations.py`를 별도로 실행해 거리 guard 2개, 시간 guard 2개,
어댑터 start 요구 1개의 **5/5 mutation 검출**을 확인했다. 검사 제거 시에만
기대 판정/계약 assertion이 깨지고 원 소스 파일은 바뀌지 않았다.

공개 acceptance는 전체 원본과 CI projection의 판정 객체가 **11/11 동일**하다.
lag-on 10건은 PASS_CLEAN, lag-off sanity 1건은 FAIL이며 정상 등록 recorder 형식을
계속 받아들인다. 원 start/end XY와 route를 독립 `math.dist`로 다시 계산했다.
OFF 대조의 L1 끝점 오차는 **0.124338662 m**로 0.10 m를 넘는다(leg 길이 오차
0.043938719 m). 파일 이름으로만 FAIL을 기대한 것이 아니다. ON 10건의 두 leg
거리도 실제 원 끝점과 일치한다. 입력 **36파일의 전후 SHA-256이 동일**하다.

과거 공개 완료 16코호트는 **308/308 개별 판정·집계 동일**, cA/cB 각각 **24/24**다.
부분 tX1은 별도 12 PASS / 2 HOST 미분류를 유지한다. reader 재해시와 별도 마지막
재해시로 **697개 입력·분석 소스 파일**이 변하지 않았음을 확인했다.
이는 과거 결과 재계산이며 새 물리·확증 표본이 아니다.

## (b) 3a136bc8 — run manifest 어댑터

허용된 두 Git blob과 candidate의 metadata fixture가 바이트 단위로 같다.

| 항목 | SHA-256 |
|---|---|
| RUN_MANIFEST.json | `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210` |
| plan.json | `d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026` |
| manifest가 식별한 driver | `7a35229e431409904dffec27b5e9572f290cd900f0595c8e0babc5ef92cf3e56` |

- **신원 출처:** `A:30–87`은 메타데이터의 source SHA, driver hash, 전체 plan hash,
  시작/종료 clean 및 source 불변 기록을 검사한다. manifest bytes도 CLI에 별도로
  준 pin과 일치해야 한다(`C:1154–1190`). raw 경로에서 신원을 추측하지 않는다.
  드라이버 본문을 새로 읽거나 실제 프로세스의 동등성을 확인한 것은 아니다.
- **계획과 파일 연결:** `C:1224–1236`은 plan의 72개 목록만 admitted slot으로 쓴다.
  `A:120–125`는 case 설정을 labels 외에는 정확히 대조하고, 계획에 있는 해당
  case의 `commands.json` 실제 파일 해시를 manifest의 그 case hash와 비교한다.
  `cases.jsonl`과 plan 전체 파일도 검사하고 마지막 `reader.verify()`로 다시 읽는다.
- **계획 밖 사례:** 다른 ID로 대체하거나 extra row를 더한 합성 검사에서
  `UNAUTHORIZED_ATTEMPT`가 남고 PASS 집계는 0이다. extra는 selected가 아니며
  60곳/72슬롯 분모에 들어가지 않는다. 알려진 하드 위반은 별도 veto로 계속 보존한다.
- **명령·설정 모순:** 다른 case의 설정/명령으로 교체, 명령 bytes 변경, 계획 bytes 변경,
  row/result seed 동시 변조는 해당 기록 또는 코호트를 INVALID/null로 만든다.
  읽기 후 명령 파일을 바꾼 검사도 `INPUT_CHANGED`로 selected 결과를 무효화했다.
  단순 누락은 미분류 슬롯으로 남아 분모 60/72가 유지된다.
- **per-case 규칙:** `C:1315`에서 같은 `adjudicate_attempt(..., confirmatory=True)`로
  들어간다. 원 start/거리/시각, handover, PF, trace·coverage·receipt,
  HOST 미분류, 하드 위반 우선순위를 기존 검사와 합성 custom-driver 검사로 확인했다.
  없는 acquisition count/period/receipt와 registration ID를 만들어 넣지 않는다.
  공통 chronology의 299g-R1도 그대로 남아 있으며 새 어댑터의 완화로 분류하지 않는다.
- **검사의 필요성:** 새 리뷰의 메모리상 mutation 2개에서 commands hash 비교 또는
  plan/case 설정 비교만 각각 제거하면 해당 합성 모순이 PASS_CLEAN으로 돌아온다.
  원 검사에서는 INVALID다. 이 두 guard도 실제 차단에 기여한다.
- **등록 상태:** `--sealed-manifest`와 혼용을 거부하며(`C:1158–1159`), 모든 합성
  기록이 정상이어도 `unsealed_stage_probe / NOT_EVALUABLE`를 유지한다(`C:1361–1364`).
  `finished=72`를 성공 72건으로 해석하지 않는다.

## prereg/seal에 명시할 실행 차이

**공개해야 한다.** 등록 계획 `REGISTRATION_PLAN.md:65`의
`scripts.run_pair_stage_probes --prereg` 대신 별도 드라이버로 수행한 것은 실제
실행 경로와 등록 시점에 관한 차이다. 같은 worker 호출이라는 설명만으로 생략할 수 없다.
분류기 병합과 별개로, 결과를 개봉·보고하기 전 prereg/seal의 날짜가 있는 변경 기록에
다음을 적어야 한다.

1. 실제 실행 source SHA, custom driver의 보존 위치·전체 SHA-256, 호출한 worker
   진입점과 표준 runner 대비 역할 차이. 이번 검토는 metadata/consumer 연결만
   검사했으며 driver 본문·블라인드 실제 commands 동등성은 확인하지 않았다는 범위.
2. 실행 당시 **`--prereg` 없음, `prereg_v6h.json` 미봉인,
   `registration_run_id`를 뺀 계획, `unsealed_stage_probe`**였다는 사실.
   실행·메타데이터 커밋·판정기 봉인·개봉의 실제 순서를 기록하고, 새 봉인이 과거 실행에
   등록 receipt나 사전 등록 이력을 소급 생성한다고 쓰지 않는다. 향후 입장 자격 결정은
   실행 경로 공개 및 그 한계를 포함한 별도 결정으로 남긴다.
3. 위 manifest/plan/driver 세 hash와 전체 72개 case ID·case별 command hash 목록의
   고정 참조. 주 시드 941×60곳, 보조 943×첫 12곳, 재실행 0이라는 메타데이터와
   HOST 재시도 규칙을 구별한다. 누락·불일치·계획 밖 기록의 처리와 분모 유지도 명시한다.
4. 실제 설정: b-v6h1/axial lag ON, teacher-held 진입의 chain L0–L1 종료,
   SIM, weld OFF, 모델 호출 0, floor_light_v1, PF/contact ON,
   800 SIM초/1500 wall초 예산, workers 4/OMP 1 및 plan의 개별 설정.
   이 경로의 검증을 E2E 또는 실물 성공으로 확대하지 않는다.
5. 최종 classifier/adapter SHA와 파일 hash, 고정된 D1–D5 판정 규칙,
   공개 acceptance·과거 탐색·블라인드 자료의 구분. 결과를 본 뒤 기준을 정한 것으로
   오해되지 않도록 이번 수정·검토가 공개/합성 자료만 사용했음을 명시한다.

`CLASSIFY_NOTES.md`에는 실행 경로 설명이 이미 추가됐다. 위 사항을 실제 prereg/seal과
연결하는 것은 조정자의 후속 기록 사항이며 이번 리뷰에서 문서 봉인을 수행하지 않았다.

## 검증 기록과 재현

새 리뷰 파일: **22 passed / 15 strict xfailed**(수정 전 10 + 현재 P1 5). xfail 해제 실행:
**15 failed / 22 deselected**, 모두 판정 AssertionError.
첫 리뷰 실행은 21 passed / 10 xfailed / 1 failed였다. 시작 61.3초 반례가 timeline보다
먼저 기록창 검사에 걸렸는데 테스트가 timeline 사유만 기대한 오류였다. 실제 거부 사유를
확인해 기대 문구만 수정했고, 첫 로그도 보존했다. 후보 구현은 수정하지 않았다.

전체 관련 기존 14파일은 **544 passed**, 실패/skip/xfail 0이다. 실행 결과는
`analysis/review_299g_validation/related_tests.txt`와 `tests_commands.json`에 보존한다.
새 메타데이터 검사 45건, 이전 리뷰 57건,
source/pinning 56건과 10,000개 생성 사례가 이 묶음에 포함된다.

GitHub 조회에서도 #299 HEAD는 위 후보 그대로였고 check **33개 모두 SUCCESS**였다
(`github_checks.json`). 기존 검사 성공은 새 299g-R1을 해결했다는 뜻이 아니다.

작은 근거·실행 로그·입력 해시는 [review_299g_validation](analysis/review_299g_validation/)에,
상세 17코호트 재분류는 `/Users/changmin/projects/ugrp/outputs/review-299g-3a136bc8/published/`에
로컬 보존한다. 마지막 소스·공개 입력 재해시도 같으며 archive scratch는 삭제하고
부재를 확인했다(`cleanup.json`). 전체 raw의 원격 백업을 주장하지 않는다.
pytest 출력 원본은 같은 로컬 결과 폴더의 `logs/`에 보존했고, 커밋용 TXT는 줄 끝
공백만 제거했다. 두 해시를 `log_projection.json`에 연결했다.

```sh
# git archive origin/codex/v6h-classifier-fixes | tar -x -C <새 scratch>
# 리뷰 파일을 scratch/tests/에 복사하고 scratch에서 실행한다.
export PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export GIT_DIR=/Users/changmin/projects/ugrp/.git GIT_WORK_TREE="$PWD"
PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python
"$PY" -m pytest -q -p no:cacheprovider tests/test_classify_review_299g.py
"$PY" -m pytest -q -p no:cacheprovider --runxfail -m xfail tests/test_classify_review_299g.py
# 두 번째 명령은 역사적 10건과 현재 P1 5건을 드러내므로 exit 1이 기대값이다.
"$PY" experiments/2026-09-30-pair-v6h-carry/analysis/check_299d_mutations.py --output /tmp/299g-mutations-NEW.json
"$PY" experiments/2026-09-30-pair-v6h-carry/analysis/verify_recorder_contract.py --output /tmp/299g-acceptance-NEW.json
"$PY" experiments/2026-09-30-pair-v6h-carry/analysis/revalidate_published.py --output /tmp/299g-published-NEW
```

새 실험 결과가 없는 오프라인 수정 검증이므로 TensorBoard 재변환·viewer 실행 없이
기존 snapshot을 보존했다. Drive 작업도 없다. 리뷰 브랜치에 문서·테스트·작은 근거만
commit/push하고 #299에 한 묶음의 한국어 코멘트로 전달한다. PR 병합과 main 갱신은
이번 독립 검토 범위에 포함하지 않는다.
