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

`zone-pair-v68-beam-relative-recovery`를 main/열린 PR 전체 최대 v67 다음으로 예약했다.
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
