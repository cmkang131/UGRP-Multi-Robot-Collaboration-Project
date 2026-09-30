# PR #292 독립 적대적 검토 — 2026-09-30

**판정: SEAL AFTER FIXES. 현재 head를 그대로 봉인하면 안 된다.**

검토 대상은 PR #292 `2c863fda3fd2de2f0fc714c2367c3e81b440b530`, 비교 main은 `a8094cc14e098a55483f53a3c49bf6a0b116043d`이다. 최신 탐색/계획은 `origin/claude/b-v6h-gain`의 `76e0f9ce793f8cbbff2349b2be2bbaa359250a42`(PR #294 병합 후)를 읽었다. 검토 종료 전 fetch와 열린 PR 재조회에서도 이 SHA들은 같았다. 구현에 참여하지 않았으며 PR 코드는 수정하지 않았다. 이 파일과 `/private/tmp/review292-astra/`의 검사 사본만 작성했다. 물리·시뮬레이션·외부 모델 실행은 0회다.

정상 입력에서 다섯 옵션의 주요 수식·상수에 구현 오류는 발견하지 못했다. 아래 문제는 **봉인한 계획과 실제 실행의 연결, 평가 정의/소스 고정, 회귀 검사의 빈틈**이다. 아직 미봉인인 것 자체나, 이미 명시하고 수용한 p2f fail-open을 새로운 결함으로 세지 않았다. 수정 뒤 재검토와 조정자의 실제 인수 재생이 필요하다.

**등급순 발견 사항**

1. **BLOCKER — 60+12건 확증 계획을 받아 검사하는 실행 계약이 없다.**
   - 근거: `experiments/2026-09-30-pair-v6h-carry/build_prereg_v6h.py:55`는 72건을 생성하지만, `scripts/zone_pair_v6_contract.py:312`는 기존 v6 메타데이터를 요구하고 `:343`은 정확히 6건/두 시드/세 정책만 허용한다. `tests/test_zone_pair_v6.py:326`의 승격 fixture도 실제 builder 대신 과거 v6e의 6건을 복사한다.
   - 재현: scratch JSON과 메모리 내 `CURRENT_REVISION='v6h'`로 builder 출력을 `load_config()`에 넘기면 `v6 registration contract changed`. 기존 dev 메타데이터·현재 scene/source 계약까지 채워도 72건에는 `v6 requires two matched seeds times three conditions`. 출력 폴더는 생성되지 않았다.
   - 대체 stage-probe 경로도 봉인 JSON을 읽지 않는다(`scripts/run_pair_stage_probes.py:1247`–`:1277`). b-v6h1 + 확증 배치 목록으로 `build_cases()`만 호출하면 60건이 만들어지지만 `render_profile`, `chain_stop_leg`, `contact_track`, `pf_track`가 모두 없다. 각각 별도 CLI 옵션이며, builder의 floor_light_v1/L1 종료/trace 요구와 대조하지 않는다. 미봉인 인수 재생용 probe가 존재하는 것은 타당하지만 이것을 봉인된 확증 실행 경로로 간주할 수는 없다.
   - 최소 수정: 실제 builder 산출물을 받는 v6h 전용 admission/adapter를 연결한다. 60개 주 시드 941 + 지정 12개 보조 943, 배치·prior·정책·소스 해시·floor_light_v1·L1 종료·두 trace를 실제 생성 case와 대조하고 불일치를 거부해야 한다. JSON 저장과 CURRENT_REVISION 변경만으로 끝난다고 쓰지 말고, 실제 72건 준비 성공 및 설정 변조 거부를 단위 검사한다.

2. **MAJOR — 최신 평가 정의와 분류기가 후보에 반영되지 않았다.**
   - 근거: 로컬 `PREREG_DRAFT.md:127`은 BLOCKED_BY_CONTACT와 전체 연쇄의 배치 단위 하드 한계 처리를 아직 구현할 일로 적는다. builder `:69`는 그 문서를 그대로 삽입하고 `:76`은 분류 이름만 나열한다. `scripts/zone_pair_v6_contract.py:121`–`:132`는 chain_analysis만 고정하며 실제 배치 분류기는 없다.
   - 최신 `76e0f9ce:experiments/2026-09-30-pair-v6h-carry/PREREG_DRAFT.md:152`는 같은 폴더 `analysis/classify_placements.py`를 사용한다고 명시하고, `:158`–`:168`은 접촉 창·중단·HOST_ERROR·보조 시드 안전 거부 등 11개 정의를 구체화한다. 일반 setdown 관문과 teacher 준비 창 포함 여부(6·7)는 여전히 OPEN이다. 이 분류기는 PR #292 tree에 없고 104개 pin에도 없다. PR #290은 `main`이 아니라 **claude/b-v6h-gain**에 병합됐다(`gh pr view 290`으로 확인).
   - 영향: 같은 raw에 대해 leg 밖 접촉·하드 위반, 주/보조 시드, 미완료 분모를 어떻게 처리할지 후보의 실행 가능한 평가 코드로 재현할 수 없다. 오래된 OFF 정책 서술도 남아 있다(`PREREG_DRAFT.md:15`, `:39`–`:41`). 맨 위 axial ON 한 줄로 새 평가 정의까지 반영되지는 않는다.
   - 최소 수정: #294의 최신 계획과 #290 분류기/관련 검사를 명시적으로 가져와 대조한다. OPEN 6·7, A=48/60 또는 다른 주장/문턱, C의 지위를 봉인 전에 확정하고 최종 문서·평가 코드·해시를 함께 고정한다. 기존 탐색 결과나 29/29를 확증 결과로 승계하지 않는다.

3. **MAJOR — 104개 source pin은 실제 명령 생성 의존성을 모두 닫지 않는다.**
   - 근거: `harness/zone_pair_executor.py:138`, `:243`은 `scripts.zone_teacher.ArmSequence`를 실제 학생 명령 생성에 사용한다. `scripts/zone_teacher.py:224`–`:243`은 보간 주기·ease·반올림·settle과 발행 시점을 결정한다. 그런데 `candidate_contract()['source_sha256']`와 builder의 scene/contact source 목록 어디에도 `scripts/zone_teacher.py`가 없다.
   - 영향: 이 파일의 arm 보간만 바뀌면 인수 기준인 commands.json 바이트가 바뀔 수 있는데 해당 파일 해시는 등록 계약의 비교 대상이 아니다. 실행 manifest의 Git SHA/전체 source fingerprint가 남는다는 사실과 **봉인 계약이 해당 변경을 거부한다**는 것은 다르다. 이전 수동 목록에서 물려받은 누락이지만, 새 chain 후보의 완전한 소스 고정으로 승인할 수 없다.
   - 최소 수정: ArmSequence 소스를 추가하고 chain 실행에 실제 사용하는 의존성 목록을 감사한다. arm 보간 변경이 봉인 계약 불일치로 거부되는 검사를 추가한다. 평가 분류기 누락은 발견 2와 함께 해결한다.

4. **MAJOR — 잘못된 axial gain 연결을 새 테스트가 놓친다.**
   - 근거: `tests/test_zone_pair_v6h.py:223`–`:239`은 일정이 OFF와 달라졌는지만 검사한다. helper 자체의 올바른 gain 계산은 검사하지만 실제 `door_schedule()`의 시간과 그 정답을 비교하지 않는다(`harness/zone_pair_executor.py:219`–`:222`).
   - 재현: scratch 사본에서 그 호출의 `timing_calibration(params, axis, self.policy.carry_fwd_gain)`를 `params`로 바꾸어도 **64 passed**. 실제 코드가 지금 잘못됐다는 지적은 아니다. 보호해야 할 잘못된 구현이 회귀 검사를 통과한다는 지적이다.
   - 수치 영향: 실제 fake-team 보정으로 0.55 m는 11.596531059644938 → 11.036175973245516 s, 0.85 m는 17.51282131543404 → 16.64681859535868 s가 된다. L1 차이는 약 **0.866 s**이며 0.1 s tick에서도 사라지지 않는다.
   - 최소 수정: r1/r2의 실제 RoutedM2 일정 끝점과 고정 probe 수식/골든을 직접 비교한다. 여러 L0 길이와 L1, κ 한 번 적용, lateral 불변, 서로 다른 PF x, 실제 `_carry()`의 0.1 s 정지 tick을 검사하고 이 mutation이 실패하도록 한다.

5. **MINOR — ‘loaded’ 범위와 chain의 팔 동작 설명을 정확히 나눠야 한다.**
   - 근거: `REGISTRATION_PLAN.md:32`(최신 원격 문서 `:33`도 동일)는 chain이 loaded로 시작하므로 접근·팔 스윕 완화를 한 번도 시험하지 않았다고 설명한다. 그러나 `harness/pair_chain_probe.py:6`–`:8`과 `scripts/run_m2_pair.py:561`–`:587`은 L0 뒤 lower/open/재파지/lift를 실행한다. 읽은 tS/S01/seed911 raw에서도 r1은 24.7 lower, 26.6 cp_open, 28.2 pregrasp_look, 34.4 lift 상태를 거쳤다. ‘초기 접근을 생략했다’와 ‘팔 스윕을 실행하지 않았다’는 다르다.
   - 등록 σ 완화는 의도대로 **confirmed grasp 상태의 base motion만**이다(`zone_pair_guards.py:425`, `:775`; `zone_pair_geometry.py:26`, `:121`). 반면 yaw gate/p2f의 기존 단계 구분은 `not approach`다(`zone_pair_guards.py:230`, `:614`, `:701`). 파지 전 align과 재파지에도 5°/4° gate가 적용된다. 파지 receipt 없는 align·yaw σ=4°의 fake endpoint에서 b-v6g `before_control=False`, b-v6h1 `True`를 재현했다. 이는 probe의 gate 선택과 같지만 ‘물건을 든 순간에만 모든 완화가 적용된다’고 읽으면 틀린다.
   - 최소 수정: σ 범위와 yaw/p2f 단계 범위를 각각 명시하고 실제 chain 팔 동작을 문서에 반영한다. k를 다시 전역 완화할 이유는 없다. 강화된 2σ arm/preclose 가드가 원본 명령에 영향을 주지 않았다는 것은 인수 재생에서 확인한다.

**질문별 답과 검증 범위**

1. **Flags-off 동등성:** 18개 기존 정책의 옛 필드와 새 기본값을 확인했다(`zone_pair_v6_policy.py:88`–`:101`; `test_zone_pair_v6h.py:62`–`:86`). frozen main 사본과 현재 사본을 별도 Python 프로세스로 실행해 18개 PF particle bytes/난수 상태/loaded params, 18×2×8 일정, 18×2×7 fake guard 결과를 비교했다. JSON 바이트가 같고 예외 0개였다(아래 재현 기록). 정상 제어 경로의 회귀는 발견하지 못했다. **모든 가능한 입력·전체 에피소드의 동등성은 not verified.** 또 bundle ID, 새 정책 필드가 들어가는 기록, 과거 v6e admission의 차단은 의도적으로 달라졌으므로 전체 파일/API까지 ‘전부 byte-identical’이라는 주장은 성립하지 않는다.
   - b-v6h1 인스턴스 구성 후에도 4개 모듈 GATE_LOADED는 같은 옛 객체/3°이며 K_SIGMA=2, LAG_AXES=('lateral',)였다. 등록 코드에는 class monkeypatch/rebind가 없다. PairSweepGuard의 `_loaded_motion`은 인스턴스 값이며 finally에서 복구한다(`zone_pair_geometry.py:118`–`:139`). 일반 접근·preclose·독립 arm sweep은 2/2다.

2. **다섯 옵션과 probe의 대응:** 원격 probe 4개와 현재 등록 코드를 직접 대조했다. 이 probe 파일들은 실제 tS/tR source `5bfd95f0`와 최신 탐색 head 사이에서도 바이트 변경이 없었다. 관련 기본 제어기 파일도 main과 탐색 head 사이에 차이가 없었다.

   | 옵션 | 대조 결과 / 명령이 달라질 수 있는 차이 |
   |---|---|
   | gain | κ=0.9483378899463337 정확히 같음. loaded gain[0][0]만 복사·곱셈, profile rebind/plant draw **뒤** 적용 순서도 같음(`owncam_carry_v6e.py:177`–`:187`; 원격 `zone_pair_carry_gain_fix.py:48`, `:66`). 재사용 때 이중 적용 금지, fit hash 검증은 등록 쪽이 더 엄격함. |
   | k=1/1 | 수식·caps·고정 35 mm·command pad는 동일. probe `zone_pair_door_relax.py:84`는 모든 SweepGuard 호출, 등록은 `zone_pair_geometry.py:26`의 loaded base-motion만. 팔·unloaded·preclose에서는 **수치가 다르고 명령을 바꿀 수 있음**. 의도된 축소이며 전체 chain 동등성은 아직 주장할 수 없음. |
   | yaw 5°/4° | XY/dwell 유지, 동일 radians 값. 등록은 인스턴스 전달이며 4개 전역 이름을 바꾸지 않음(`zone_own_guards.py:71`; `zone_pair_guards.py:216`, `:614`). 단계 범위는 발견 5 참고. |
   | p2f | 정상 finite 시각은 같은 ‘first move보다 fix_t가 엄격히 늦음’ 규칙과 reset 순서. probe `zone_pair_progress_relax.py:79`는 +inf(조건에 따라 bool도)를 허용하지만 등록 `zone_pair_guards.py:180`–`:197`은 비유한·bool 시각을 거부함. 이 입력에서는 명령이 달라질 수 있고 등록 계획이 요구한 방어적 차이임. probe의 최대 60개 상세 로그 대신 등록은 robot별 누적 수를 기록함(제어 수식 차이 아님). |
   | axial lag | 같은 gain 보정 사본으로 기존 lag_duration을 역산. 정상값·계산 순서·lateral 불변 확인(`zone_pair_executor.py:199`–`:228`; `owncam_carry_v6e.py:71`, `:199`–`:229`; 원격 `zone_pair_carry_axial_lag.py:60`). LAG_AXES 전역 수정 대신 해당 정책 분기로 구현됨. |

   frozen main+4개 실제 probe 패치와 b-v6h1을 별도 프로세스에서 비교한 loaded PF bytes/난수 상태/params 및 2로봇×8 leg 일정은 정확히 같았다. `_carry()`를 fake port와 0.1 s 시계에서 직접 호출한 L0/L1 명령열도 같았다(영상 검사는 이 순수 시간 검사에서 제외). t0=10일 때 두 로봇 모두 L0 계획 종료 28.09653105964494 → hold tick 28.1, L1 34.01282131543404 → hold tick 34.1. `_carry()`의 .15 s command lease와 `start <= now < end`는 그대로다(`scripts/study_owncam_pair_beam.py:409`–`:421`). **실제 SIM 부동소수 시계·새 영상·가드까지 포함한 commands.json 전체 재생은 not verified.**

3. **두 로봇 시간 대칭성:** 사용 거리는 `plan['route']`의 두 점 차이이며 자기 PF x가 아니다(`zone_pair_executor.py:200`–`:219`). role sign은 명령 부호만 바꾸고 `leg_duration()`은 abs(speed)를 쓴다(`owncam_carry_v6e.py:228`). r1 x=-100, r2 x=+100으로 달리 주고 y/yaw도 다르게 한 fake schedule에서 0/1/2/3/7번 leg의 시작·종료 시간이 정확히 같았다. 상위 정렬 구간은 PF y/yaw를 쓰지만 고정 길이 DOOR_ALIGN_S+.5다(`scripts/run_m2_pair.py:589`–`:611`). #286의 own-x 기반 최대 0.23 s 차이를 만드는 구조는 없다. 프레임/guard 실패로 한 로봇이 먼저 멈추는 다른 원인까지 배제한 것은 아니다.

4. **번호·봉인 bookkeeping:** fetch 후 origin remote ref **159개**의 `harness/`, `scripts/`, `sim/`, `configs/`, `config/`, `maps/`를 git grep했다. v83/2.16.0 실제 등록 사용은 #292 브랜치뿐이며 열린 #285/#293의 head도 확인했다. 기존 probe 이름 b-v6h와 예약 문서 언급은 번호 충돌로 세지 않았다. v81 retired 추가와 workflow/통합 ID가 일치한다. CURRENT_REVISION=v6e + historical 차단, PENDING=v6h, prereg_v6h.json 없음은 의도된 미봉인 상태다.
   - builder `--dry-run`/`--verify` 통과: 72건, **104 pins = 기존 85 + 신규 19**. `source_changes_UNSEALED.json`과 재계산 delta가 정확히 같다(기존 pin 변경 12 + 추가 19 = 31행). **기존 sealed 파일을 바꿨는데 delta에서 빠진 것은 0개**다. 기존 old hash가 있는 12개 중 실제 PR diff가 아닌 항목도 0개다.
   - PR에서 수정하지 않았지만 새로 고정한 8개는 calibration_loop_v2, door_relax_analysis, hR2_samples, chain_analysis, pair_chain_probe, 두 tag 지도, render_profile이다. old=null의 신규 pin이므로 잘못된 변경 주장으로 보지 않는다. REGISTRATION_PLAN의 예상 목록에는 zone_own_executor가 있지만 실제로는 수정하지 않았고 정확한 JSON delta에도 없다.
   - changed runtime 파일 중 pin 밖인 build_pair_stage_probe_views/run_ci_tests는 각각 표시/CI 도구다. 반면 실제 ArmSequence와 새 분류기 누락은 발견 2·3이다. **dry-run 통과는 최종 봉인 검증이나 72건 admission 통과가 아니다.**

5. **안전/fail-open:** p2f 0/208은 `PREREG_DRAFT.md:140`, `REGISTRATION_PLAN.md:34`에 명시돼 있다. 코드 주석 `zone_pair_guards.py:165`, README `:14`, PR 본문도 “no reliable stall detection for the loaded pair”/fix 없으면 fail-open이라고 솔직히 적는다. README/PR 본문 자체에는 0/208 분모가 반복되어 있지 않지만 정지 감지가 된다고 주장하지 않는다. 208건 전체 로그에서 그 수치를 새로 재집계한 것은 **not verified**다. k0/advisory override를 등록 경로에 옮긴 흔적은 없고 global/consistency K_SIGMA는 유지된다. yaw/p2f의 ‘non-approach’ 범위는 발견 5의 문서 보완이 필요하다.

6. **테스트와 mutation:** 핵심 세 파일 **154 passed**(18.35 s), 아래 관련 열 파일 **243 passed + 92 subtests passed**(11.98 s). 모두 한 스레드 설정으로 순차 실행했고 pytest cache/bytecode를 끄고 임시 출력은 scratch에 뒀다. 시간은 성능 비교가 아니다.

   | scratch에 넣은 오류 | test_zone_pair_v6h 결과 |
   |---|---|
   | M1: scaled_gain의 곱을 `*= 1.0`으로 변경 | 2 failed, 62 passed — 검출 |
   | M2: `_loaded_motion = bool(loaded)`를 `True`로 변경 | 1 failed, 63 passed — 검출 |
   | M3: 실제 일정 호출부의 corrected params를 원본 params로 변경 | **64 passed — 미검출** |

   저장 골든은 과거 commit을 명시하며, PF byte 비교는 옛 carry 모듈을 별도 namespace/provider로 실행한다. 현재 localizer/beam-edge 의존성도 해당 commit blob과 같은지 검사하므로 단순 자기 비교는 아니다(`test_zone_pair_v6h.py:29`–`:45`, `:77`–`:86`). 다만 같은 현재 policy를 양쪽에 사용하므로 별도의 옛 필드 골든 검사가 함께 필요하며 실제로 존재한다. PairCommandGuard 골든은 4정책의 한 짧은 장면에 한정된다. builder `verify(build())`는 현재 소스에서 다시 만든 값과 비교하는 preview 검사라, 승인된 고정 seal과의 회귀 비교를 대신하지 않는다. 발견 4의 호출부 공백은 그대로 남는다.

7. **확증 유효성:** 생성 시드 20260941 및 60개 파일 해시 `bb8044058377d86efc658ce3a7458c8afc141680acfd98542260e0efda018454`를 재생성 검사했다. 주 시드 941/보조 943 12건은 분리되어 있다. 최신 #294 freshness 자료의 **29개 실제 case.json과 4개 cases.jsonl 해시**를 다시 읽어 검증했고, 거리<0.01 m AND yaw차<0.5° 근접 중복은 **0건**이었다. hR2 prior 10개 재사용은 명시된 제한이며 새 독립 prior나 모집단 일반화의 증거는 아니다.
   - floor_light_v1은 builder operation(`:82`)과 sim/render_profile.py의 source hash에 **정적으로 포함**된다. 따라서 ‘아예 pin이 없다’는 지적은 맞지 않는다. 그러나 실제 case/적용 profile을 그 값에 묶어 검사하는 확증 admission은 발견 1처럼 없다.
   - PR #292 인수 참조 6건(S01/S02/S03/S07/hR2_01/X06, 모두 911)의 기존 commands.json 해시 6/6을 재확인했다. 최신 #294는 S01/S07/hR2_04/X01/X06의 5건 및 전체 접촉/하드 판정 동일성을 요구한다(`76e0f9ce:REGISTRATION_PLAN.md:76`–`:78`). 목록을 한 개로 확정해야 한다. README `:65`–`:71`의 예시는 명령 hash+leg_checks만 검사하며 전체 접촉/하드 판정은 비교하지 않는다. **원본 hash 확인은 새 구현의 인수 통과가 아니다.**

**재현 기록**

Python은 기존 `/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용했다. 환경 변수는 PYTHONDONTWRITEBYTECODE=1, OMP_NUM_THREADS=1, OPENBLAS_NUM_THREADS=1, MKL_NUM_THREADS=1, VECLIB_MAXIMUM_THREADS=1. pytest는 `-q -p no:cacheprovider --basetemp=/private/tmp/review292-astra/<검사별경로>`로 실행했다.

- 핵심: tests/test_zone_pair_v6h.py, tests/test_zone_pair_registered_source.py, tests/test_ci_sharding.py.
- 관련: tests/test_zone_pair_v5h.py, test_zone_pair_v6c.py, test_zone_pair_v6d.py, test_zone_pair_v6e.py, test_zone_pair_v6e_yaw.py, test_zone_pair_v6g.py, test_zone_pair_executor.py, test_zone_pair_door_relax.py, test_zone_own_executor_guards.py, test_owncam_localizer.py(모두 tests/).
- scratch mutation은 원본 harness를 복사한 뒤 위 세 문자열을 하나씩 교체하고 새 테스트 파일 전체를 별도 프로세스로 실행했다. 매번 원복했다. 저장소 소스에는 적용하지 않았다.
- 독립 off 대조: main의 변경 대상 harness 파일들을 git blob으로 복원한 scratch와 PR tree에서 같은 순수 PF/fake endpoint 입력을 실행했다. 18정책 JSON bytes 공통 SHA-256 `fecacddb331628c1aeafb1f2f60f4954bb12a8e729faa3a2258d32743bb866c4`.
- probe ON vs 등록 ON의 PF/일정 JSON 공통 SHA-256 `38be2ace43ac4e0ef728f23c2ec02198191fcdf34acece66b906ec143d135f9e`.
- 0.1 s `_carry()` fake-port L0/L1 명령열 공통 SHA-256 `3d364c1cbe149276b455f3a08d228d59974dd9a795954e342d7b3e0905e707a6`.
- 검사 스크립트와 로그는 `/private/tmp/review292-astra/`에 있다. 영구 검토 기록은 이 파일이며, scratch hash를 물리 실행 원본이나 원격 백업으로 표현하지 않는다.

**수행하지 않은 검사 (not verified)**

- 조정자 소관의 실제 물리/SIM 인수 재생, 원본과 새 commands.json 전체 일치, 새 영상·가드·재파지 동작의 연쇄 동등성.
- 확증 60+12건, E2E/실물/새 환경 성능, 벽 끼임에 대한 안전 정지 능력, 외부 모델 호출.
- 새 seal 생성/승격/admission의 성공, 최신 평가 OPEN 정의 확정, 현재 PR에 없는 classifier를 통합한 뒤의 평가 검증.
- 전체 로컬 CI 재실행, 가능한 모든 정책 상태/입력의 완전 동등성, 208건 p2f 원시 로그 전체 재집계.
- 새 TensorBoard 변환/화면 검증은 하지 않았다. 이 작업은 소스 검토와 단위 검사이고 새 물리 실험 결과를 만들지 않았다. 사용자 범위에 따라 PR 생성·코드 수정·병합·기본 체크아웃 갱신도 하지 않는다. UGRP 지침에 따라 Google Drive는 사용하지 않았다.

**최종 판정: SEAL AFTER FIXES.** 발견 1–4의 계약·평가·고정 목록·검사 보완과 범위 문서 정리 후 최종 소스에서 재검토한다. 독립 검토 통과와 조정자의 실제 matched-ON 인수 재생은 별도 관문이다.
