# 공동 운반 v6: 상대 조작 / 전역 안전 / posterior 보존 복구

2026-09-28 · `codex/zone-pair-beam-relative` · 기반 `f87921dc52f7a3f12d41b4bc6ab5c30227890e8e`.
미커밋 구현과 오프라인 검증이다. **물리 실행·모델 호출·완주 검증은 없으며 물리 dev 준비 완료가 아니다.**

[설계](design.md), [6회 사전등록 초안](prereg_v6.json), [저장 입력 재생](offline_replay.json),
[번들 번호 대조](bundle_reservation.json)를 함께 읽는다. 원본 v5h/M2 기록과 동결 실행기는 바꾸지 않는다.

1차 회귀(후속 수정 전): **853 passed, 0 failed, 198 subtests passed**. [전체 변경 목록](changes.md),
[검증 기록](validation.json), [pytest 로그](pytest.log), [RGB 잔차 대조](rgb_residual_validation.json).
`.pytest_tmp` 삭제 완료. MuJoCo step·네트워크 차단기 호출 0, 모델 호출 0, git 커밋 없음.
TensorBoard [로컬 snapshot](tensorboard-snapshot/)의 8개 scalar는 EventAccumulator로 재로딩했다.
공용 `outputs/tensorboard`·view 설정은 쓰기 허용 범위 밖이므로 게시하지 않았으며 신규 화면 확인은 남는다.

기존 `sim_cli workflow run zone-pair-dev` 관리 경로 / `run_zone_pair_dev.py`를 확장했다.
새 기본 실행기를 만들지 않았다. `PairTeam(policy=...)`, 호스트 정적 `spec.pair_policy`,
등록별 `pair_policy`, CLI `--pair-policy`가 같은 선택을 가리킨다.

| 조건 | 빔 상대 align·close 준비 | posterior 보존·관측 품질·pan 취소 | 전역 안전 |
|---|---|---|---|
| `v5h` (기본) | 기존 band/PF gate | 기존 동작 | 기존 gate·sweep |
| `b-only` | 기존 | v6 | 기존 gate·sweep |
| `a+b` | v6 형상 보고 | v6 | 별도 global envelope + full beam/body/arm 검사 |

`zone-pair-v68-beam-relative-recovery`를 main/열린 PR 전체 최대 v67 다음으로 예약했다. (2026-09-28 main 병합 뒤 v70으로 재등록, 아래 절 참조)
통합 실행 bundle도 이 ID를 사용하고 과거 v67은 이력으로 보존한다. 워크플로 버전은 0.6.0이다.
Git fetch는 공유 FETCH_HEAD 쓰기 제한, gh는 네트워크 제한으로 실패했다. GitHub GET의
main/열린 PR 7개 SHA와 로컬 origin 참조를 모두 대조했다. PR 코멘트는 도구 승인 정책 때문에
게시되지 않았다. **현재 번호 예약은 로컬 기록이며 원격 예약 게시가 아니다.**

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python scripts/run_zone_pair_dev.py \
  --prereg experiments/2026-09-28-zone-pair-v6/prereg_v6.json \
  --run-id v6-s911-ab --pair-policy a+b --output /private/tmp/zone-pair-v6-prepare-NEW
```

이는 prepare만 한다. `--execute`는 v6 DRAFT에서 항상 거부한다. 911/912 두 새 dev seed의
같은 배치·입력 주기·scene·접촉·예산에 대해 v5h/b-only/a+b, 총 6회다.
전부 정상 시도이며 과거 carry-GO abort 개입을 가져오지 않는다. 회당 900 SIM초, 재시도 0,
ENOSPC=HOST_ERROR, `execution_source_sha`·승인 null이다. `tags_temporary` 조작 진단이며 연구 결과가 아니다.

오프라인 재현:

```sh
OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python scripts/replay_zone_pair_v6.py \
  --raw-root /Users/changmin/projects/ugrp/outputs \
  --m2-index /Users/changmin/projects/ugrp-wt/codex-pair-parity/experiments/2026-09-27-zone-pair-parity/m2-input-contracts.json \
  --output /private/tmp/zone-pair-v6-replay-NEW.json
```

이 재생은 dev05–14의 자기 checkpoint 20개와 기존 M2 성공선정 49회/98 trace의 첫 align 입력을
각각 읽는다. PF 입자·RNG를 재구성한 전체 episode 재생이 아니다. 전역 보고가 없거나 과거
`accepted=true`밖에 없으면 새로운 informative fix로 승격하지 않는다. production relook 상태기계는
저장 pose report의 가설로 시선을 제안하는 가짜 provider와 재생한다. 새로운 view/명령/receipt가
필요한 첫 분기부터 **unknown**이며 이후 저장 영상을 이어 붙이지 않는다. M2 성공선정 자료를
holdout이나 v6 성공률로 쓰지 않는다. dev13/14 잔차·pan 회귀는 독립 checkpoint 검사다.

`tests/fixtures/zone_pair_v6`는 원본 자기 JPEG 4장, 자기 보고·검출·정적 보정과 해시를 보존한다.
원본 raw는 기본 checkout outputs에 그대로 있으며 새 원격 백업을 만들지 않았다. UGRP 예외에 따라
Drive는 사용하지 않는다. 테스트에는 MuJoCo step 및 네트워크 호출 차단기를 사용한다.

남은 위험: 상대 depth/FK/오차 bound와 전역 command reachability는 개발 가설이며 coverage 보정이 없다.
부분뷰 거부로 진행을 막을 수 있다. 실제 markerless provider의 v6 recovery는 아직 연결하지 않았다.
**상대 보고·align·close 준비에는 검은 band를 쓰지 않지만, 기존 M2의 post-close grip/hold/co-motion
receipt는 아직 band를 포함한다.** 전체 운반이 markerless라는 주장은 하지 않는다.
대안은 동일 카메라·외관에서 colour/edge-only grip·co-motion·hold receipt를 별도로 보정하고 새 cohort로
검증하는 것이다. 새 상대 형상 fit을 기존 post-close 성공 증거로 대체하지 않았다.

최종 후속 회귀: **2307 passed / 0 failed, 382 subtests passed**, 요청한 패턴 전체 62개 파일. MuJoCo step·네트워크 sentinel 0, 자식 step tripwire 0, 실제 모델 호출 없음. `.pytest_tmp` 삭제, 프로젝트 HEAD 유지.
[등록 소스 회귀 수정](source-regression/README.md) · [최종 로그](source-regression/final/pytest.log) · [최종 검증](source-regression/final/validation.json).

## PR #246 검토 1 후속 수정 (2026-09-28)

검토 기반은 `837a110ae15e46a45291100f161b3a33c83eb3d9`이다. 이번 변경은 미커밋이며
물리 step·실제 모델 호출 없는 코드 회귀다. [상세 변경·검증](review1-fixes/README.md)을 따른다.

- `a+b`의 approach/reapproach도 모든 발행 이동·팔 sweep의 최종 검사에 전역 envelope를 쓴다.
  PF 평균은 목표 계산에 남는다. σxy 1 cm 대 6 cm, 여유 약 19 mm에서 `.12 × .15 s` 이동 거부를 회귀한다.
- 전역 anchor 교체 시 XY와 원형 yaw 거리를 각각 발행 명령의 도달 범위와 불확실도에 대조한다.
  범위 밖 fix는 정지 상태의 서로 다른 informative fix 3회가 0.3초 이상에 걸쳐 3 cm/3° 이내로
  일치해야 수용한다. 정보 소실·명령·불일치·1초 초과 간격은 이 검증을 다시 시작한다.
  미검증 재획득은 `fix_t`와 anchor를 갱신하거나 전역 bound를 줄이지 않는다.
- 상대 형상의 전체 길이 관측은 초기 끝 식별에 계속 필요하다. (검토 3 정정) 검토 1의 **단일 부분뷰 갱신은
  검토 2에서 삭제했다.** 가림 경계를 끝으로 오인했기 때문이다. 현재는 base 명령 없이 4초 안에 찍은 서로 다른
  고정 자세의 부분뷰를 합쳐 전체 형상 조건을 다시 만족할 때만 갱신한다(`STATIONARY_MULTIVIEW_COMPLETE_SHAPE`).
  33 cm→30.6 cm 반례는 이 다중 뷰로 회복한다. 5 cm/3° 임계값과 고정 카메라는 유지한다.
  부분뷰는 원래 전체 형상 식별의 30초 수명을 연장하지 않는다. 단순 지지 픽셀은 bound를 줄이지 않는다.

### tags_temporary 전용 의존성

| 위치 | 잔존 의존성 및 이번 처리 |
|---|---|
| `harness/owncam_recovery_v6.py:RecoveryLocalizer.update` | tag ID→정적 tag 지도·PnP·tag likelihood·곡률·proposal을 쓰는 실제 복구 provider다. 형상 상대 보고로 전역 위치를 대체할 수 없다. provider-neutral `begin_observation` 계약과 가짜 markerless provider 회귀만 있으며 실제 markerless 전역 provider는 별도 #216 트랙이다. |
| `harness/zone_pair_obstruction.py:target_component` | 기존 band 기반 목표 association을 보존한다. `a+b`에는 **전체 길이·두 끝·양쪽 edge**의 형상 대체 경로를 추가했다. 목표 일치·색·전체 성분 지지 검사는 유지하며 부분뷰만으로 장애물을 제외하지 않는다. 전체 형상이 안 보이는 경우의 band 대체는 여전히 tags_temporary 전용이다. (검토 3) 형상 대체는 bound ≤ 5 cm가 필요해 **grip 약 .43 m 이상(검토 3 이전 모델), 현재 모델에서도 약 .47 m 이상에서는 band 대체에 의존한다.** |
| `scripts/run_m2_pair.py:grip_view_m2` | post-close 검은 band 비율 및 빔 색을 요구한다. frozen M2와 v5h/b-only 비교 기준은 수정하지 않았다. 닫힌 집게의 부분·가림 영상에서 resting-plane 형상으로 실제 grip/hold를 증명할 수 없으므로 형상으로 성공 receipt를 대체하지 않았다. |
| `harness/zone_pair_grasp.py:stationary_beam_estimate`, `harness/zone_pair_beam_track.py:standoff_estimate`, `harness/owncam_pair_beam_v2.py` 및 기존 held signature/hold 경로 | v5h/b-only의 band 기반 standoff·정렬·파지/유지 검사는 비교 기준에 남는다. `a+b`의 상대 align/close 준비는 형상 경로이나 post-close co-motion/hold는 기존 appearance receipt를 포함한다. |

따라서 전체 운반의 markerless 지원/성공은 아직 주장하지 않는다. #216의 실제 provider와 별도로
형상 grip/hold/co-motion receipt는 가림·미파지·미끄러짐 음성 예시를 포함한 보정·검증이 필요하다.
공정성은 같은 seed·입력·scene·예산에서 `pair_policy` 선택만 바뀌며,
`v5h→b-only`는 B, `b-only→a+b`는 A 동작 플래그 하나만 다르다.
`prereg_v6.json`의 현재 소스/scene 해시는 재계산하고 과거 등록 원문은 보존했다. DRAFT 실행 차단도 유지한다.

검토 1 수정 후 최종 회귀: **75개 파일, 2695 passed / 0 failed / 2 skipped(물리 전용),
382 subtests passed**. 요청한 모든 glob을 수집했다. 물리 step·실제 모델·네트워크 호출은 0,
`.pytest_tmp` 삭제·현재 등록 소스 65개 일치·6회 DRAFT 실행 차단·기반 HEAD 유지 확인.
[최종 로그](review1-fixes/pytest.log) · [무결성 검증](review1-fixes/validation.json).

## PR #246 검토 3 후속 수정 (2026-09-28)

기준 HEAD `a5b486eb`. 상세는 [검토 3 수정 기록](review3-fixes/README.md), 문헌 요약은 [lit_review.md](lit_review.md).
물리 step·모델 호출은 없다.

- 전역 envelope의 이동 거리 이중 합산을 없앴다. 예정 안전 재관측은 HIGH 복구 예산과 분리해 회당 6초·총 240초·80회로 `v6_contract`에 등록했다.
- a+b 정렬은 원거리에서 전진 전용 close-in을 한다. view 시도 기록은 다중 뷰 창 만료와 relook 뒤에 초기화한다.
- 형상 fit은 연관 성분만 쓴다. 가까운 끝면을 중간 높이 가설로 모델링했다. 저장 자기 프레임 중 정지·look 자세 4,928장에서 3,693장이 fit했고 GT 평가 오차는 모두 보고 bound 안이었다(최대 0.19배). 움직이는 중 프레임의 위반 4건은 제어 입력 조건 밖이다.
- 문헌 레시피에 따라 a+b 정렬 중에는 PF HIGH를 중단 조건에서 뺐다. 정적 빔 기준 bound로 벽·팔 여유는 계속 검사한다. 이 정의를 `v6_contract.flag_definitions`에 등록했다.
- **v5h 조건은 과거 frozen v5h와 동일하지 않다.** 공용 경로 변경 2건(`zone_pair_executor.py`의 차단 명령 처리, `zone_pair_obstruction.py`의 성분 마스킹)이 v5h와 b-only에도 적용된다. 세 조건 사이의 한 플래그 공정성은 유지된다.

## main 병합과 번들 ID v70 (2026-09-28)

PR #240이 main에 병합됐다(d5bd208e). 코디네이터가 #246의 base를 main으로 바꿨고, 이 브랜치에 origin/main을 병합했다.
물리 step·모델 호출은 없다.

- **번들 ID:** `zone-pair-v70-beam-relative-multiturn`, workflow `zone-study-integration-run` 2.3.0.
  - 병합으로 v6 소스 closure에 main의 v66 다중 턴 스케줄러가 들어왔다. 합성 소스는 v68(병합 전 v6 초안)·v69(main) 어느 쪽과도 다르다.
  - v68은 이미 [오프라인 재생 기록](offline_replay.json)에 쓰였다. 그래서 v68을 다른 소스에 다시 쓰지 않고 다음 빈 번호를 썼다.
  - 번호 확인: main 최대 v69, 열린 PR #248·#249는 v66까지이고 v68 이상이 없다. 그래서 v70이다.
  - v68·v69는 `RETIRED_BUNDLE_IDS`에 추가했다. `offline_replay.json` 등 과거 기록의 v68 문자열은 그대로 둔다.
- **prereg_v6:** `execution_bundle_id`(최상위·`v6_contract`)를 v70으로 바꾸고 `review3-fixes/update_prereg.py`로 `v6_contract`와 `registration_sha256`을 다시 계산했다(`a93caeb1…a9a2`). 상태는 DRAFT·승인 null 그대로다.
- **충돌 해결:**
  - v5h 관련 테스트는 main의 `tests/zone_pair_current_source.py` 방식(합성 current-source fixture + 커밋된 v5h 거부)을 따른다.
  - 이 브랜치는 v5h scene 계약 소스(`zone_own_team_host.py`, `run_zone_pair_dev.py`, `zone_pair_dev_runtime.py`)도 바꾼다. `load_config`가 scene 계약을 먼저 검사하므로, 커밋된 v5h 거부 사유는 scene 또는 grasp 불일치 둘 다 허용하도록 helper 한 줄을 고쳤다. 거부 자체와 출력 미생성 검사는 그대로다.
- **의미 변화:** 세 조건(v5h/b-only/a+b) 모두 main의 다중 턴 스케줄러 위에서 돈다. pair 조건 간 차이는 여전히 `pair_policy` 하나다.

## 최종 적대적 검토 수정 (2026-09-28)

검토: 기본 체크아웃 `outputs/review-246-final-20260928.md`(HEAD d5a8c5f2, P1 3건·P2 4건·P3 5건). 물리 step·모델 호출은 없다.

- **P1-1 (정렬 중 예정 재관측이 끝나지 않음):** `before_control`은 재관측 상태가 아니면 모든 분기보다 먼저 활성 예정 look을 끝낸다. 이제 align relook마다 회당 6초 허용량과 count가 따로 적용된다. 회귀 테스트는 align 예약 relook 3회를 강제해 index 1·2·3, HIGH 대기 0을 확인한다.
- **P1-2 (바이트 동일 새 프레임):** 자기 명령이 없었고 카메라 PWM·segment가 같은데 픽셀이 같으면, 직전 판정을 새 frame에 그대로 유지한다(`IDENTICAL_PIXELS_NO_NEW_COMMAND`). anchor·identity 시각은 갱신하지 않으므로 계속 나이를 먹고, close-in 근거가 되지 않는다. 명령 뒤 같은 픽셀이면 여전히 `DUPLICATE_IMAGE`다. 회귀 테스트는 저장 raw JPEG(dev09 r2 1491)를 두 frame으로 넣는다.
- **P1-3 (정지 빔 전제 미검증):** object anchor를 다음 세 경우에 버린다.
  1. 전역 envelope와 anchored bound가 K_SIGMA 원끼리 겹치지 않을 때(`GLOBAL_ANCHOR_DISAGREE`).
  2. anchor 이후 자기 발행 명령의 도달 범위(전역 envelope와 같은 절반 이득 중심·[0, 1.6] 반경)로 전파한 anchor 시점 빔과 현재 track 빔이 어긋날 때. 누적 기준 연관이다(`BEAM_MOVED_SINCE_ANCHOR`).
  3. 상대가 close/hold 단계를 메시지로 알릴 때(`close_*`·`ready`·`lift`·`carry` 등). 이 동안에는 새 anchor도 만들지 않는다.
  anchor가 없으면 기존 envelope 경로(relook·abort 규칙)가 판단한다.
  한계: 2번 검사의 폭은 자기 명령 이득 범위 도달 반경 + 2×(두 뷰 bound 합)이다. 정지 상태에서도 약 0.2 m이고, 자기 이동이 있으면 더 넓다. 이보다 작은 누적 이동은 1번(전역 envelope 유효 시)과 3번에 의존한다.
- **P2-1 (approach look 끝 무한 hold):** 전역 fix 확인 대기를 look 시작 뒤 6초(등록된 회당 허용량)로 제한했다. 그 뒤에는 frozen `look_done` 경로(no-fix → GATE_MAX_LOOKS/relocalize)로 넘긴다.
- **P2-2 (예산 범위·조건 비대칭):** HIGH 복구 10초와 align `MAX_LOOKS`·`MAX_TOTAL_LOOK_S`를 approach/reapproach/align 진입(regrasp 포함)마다 초기화한다. 세 조건에 동일하게 적용되고, relook 복귀는 채우지 않는다. 범위는 `v6_contract.reobserve_budgets.scope`에 등록했다.
- **P2-3 (not-ready 사유 즉시 실패):** 입력 유효성 사유(`DUPLICATE_IMAGE`, `OUT_OF_ORDER`, stale, `BEAM_MOVED…`)는 다음 frame을 기다린다. `SHAPE_AMBIGUOUS`·`END_ID_AMBIGUOUS`·`PAIRED_EDGES_UNOBSERVABLE`은 남은 고정 자세를 먼저 시도한다. 둘 다 align 마감이 제한한다.
- **P3-4:** `v6_contract.source_sha256`에 제어 경로 모듈 7개(`zone_own_sweep`, `pair_owncam_approach`, `owncam_drive`, `run_m2_pair`, `study_owncam_pair_beam`, `visual_arm`, `m1_owncam_delivery`)를 추가했다.
- **남긴 항목:**
  - P2-4: anchored bound는 가까운 거리에서만 reserve(0.10) 아래로 선택된다. 범위 주장은 README 검토 3 절의 "약 0.10–0.12 m" 그대로이며 거리별 시험은 하지 않았다.
  - P3-1: anchored 비-clear relook이 같은 bound로 곧 `GLOBAL_ENVELOPE_BLOCKED`로 끝난다(유한).
  - P3-2: 전경 행 밖 label 0 빔색 픽셀 포함(조사 위반 0).
  - P3-3: 정지 장면의 재획득 3회 미충족(HIGH 예산으로 유한).
  - P3-5: 통합 번들 이름이 pair ID를 가져온다.
- **번들 ID:** v70을 유지한다. main과 열린 PR 전체에서 v70은 #249·#250 설계 문서가 #246의 번호로 언급할 뿐이다. v70으로 기록된 실행·결과·prereg는 이 브랜치 밖에 없다. 이 브랜치의 prereg_v6도 DRAFT이고 실행 기록이 없다. `v6_contract`와 `registration_sha256`(`d200e5b3…2419`)은 다시 계산했다.
- **v5h 조건:** 예산 초기화 범위 변경도 공용 경로라 v5h에 적용된다. 이는 frozen v5h와의 차이에 하나 더 추가된다.
