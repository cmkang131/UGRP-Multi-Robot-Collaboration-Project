# CHECKPOINT (커밋 금지) - 2026-09-29 통합(v6e carry + v6f place) 갱신

- 병합 커밋 4c94138f (로컬만, push/PR/등록 없음). PROBE_VERSION 0.6.0. 정책: 대조 b-v6d, carry 절제 b-v6e-dr / b-v6e-lag, place 절제 b-v6f-a / b-v6f-b / b-v6f(b-v6c 기반), 통합 후보 b-v6e = b-v6d + carry_dr_model + carry_lateral_lag + own_image_ob + bounded_retreat. 모든 플래그 기본 OFF.
- 타깃 테스트 470 통과 / 9 실패: 봉인 해시 5(test_zone_pair_registered_source) + 기존 main 동일 실패 4(v5c 태그 ID 1, study_pair_delay 3; main f5da3c6d에서 동일 재현). 물리/probe/모델 호출/전체 스위트 미실행.
- 통합 측정 계획(배터리 연결 후, agent_lock 잡고, 워커 2·--omp-threads 1, 디스크 10 GiB 확인):
  1. 단계 4(carry): 아래 (구) 절차 3~5 그대로. policy는 b-v6d(대조), b-v6e(통합), 필요 시 b-v6e-dr/-lag 절제. 보정 코호트(cal, --pf-track) 먼저.
  2. 단계 5(place): 같은 러너로 --stage <place 단계 id> --policies b-v6c(기준 0/13) b-v6e; 절제가 필요하면 b-v6f-a/-b. place 단계 id와 셀 격자는 claude-v6e-place 쪽 CHECKPOINT.md를 따른다.
  3. 결과 확인 뒤 번들 v81 / 워크플로 2.14.0 / revision v6e를 한 번만 등록·봉인(v82 / 2.15.0 / v6f 사용 안 함). scripts/zone_pair_v6_contract.py 봉인, v6c/v6d 은퇴 목록, 봉인 해시 5건 해결.
  4. README(한국어), TensorBoard 스냅샷, 최종 상태에서만 push 1회 + PR.

# CHECKPOINT (커밋 금지, 삭제 후 worktree 정리) - 2026-09-29 코드 완료 갱신

- main f5da3c6d(#265 b-v6d, 번들 v80)로 ff 후 코드를 다시 얹어 커밋 6effa8ce(로컬만, push/PR 없음). v6e 정책은 이제 b-v6d + 플래그: b-v6e-dr, b-v6e-lag, b-v6e. 번들/워크플로/revision 미등록(v81 / 2.14.0 / v6e는 마지막에 한 번).
- 타깃 테스트 통과: test_zone_pair_v6e(+v6d 합성 테스트 1개), bootstrap_v6b, zone_pair_executor, zone_pair_v6d, zone_pair_v6, markerless_probe, owncam_localizer, pair_stage_probe = 200+97 통과. 예상된 실패 5건만 남음(test_zone_pair_registered_source.py, v6d 소스 봉인 해시; 최종 등록 때 해결).
- 물리·probe·모델 호출·전체 스위트는 실행하지 않았다. 측정 재개 절차는 아래 (구) 절차 3~7을 따르되 policy 기준선은 b-v6d(대조)와 b-v6e 계열이다.

# CHECKPOINT (커밋 금지, 2026-09-29 중단 시점)

worktree: /Users/changmin/projects/ugrp-wt/claude-v6e-carry, 브랜치 claude/pair-v6e-carry, 기준 main 1e7bdfe0. 아무것도 커밋·push하지 않았다. 물리 시뮬레이션은 한 번도 실행하지 않았다(raw 없음). agent_lock은 잡지 않았다(status = null).

## 중단 시점에 하던 일
- 전체 CI 테스트 묶음(약 300개 모듈)을 로컬 pytest로 돌리던 중 조정자 중단 지시로 SIGINT로 멈췄다(내 프로세스 PID 24668만; claude-v6e-place의 pytest는 건드리지 않음). 중단 전까지 5619 통과 / 5 실패 / 16 건너뜀 (615 s). 뒤쪽 모듈은 돌지 않았으므로 전체 통과는 확인하지 못했다.
- 실패 5건은 모두 `tests/test_zone_pair_registered_source.py`(v6c 소스 봉인 해시 불일치)다. 소스를 바꿨으니 예상된 실패이고, 최종 등록 단계(revision v6e, `scripts/zone_pair_v6_contract.py` 봉인, v6c 은퇴 목록)에서 한꺼번에 해결한다.
- 첫 실행(-x)에서 발견한 실제 버그는 고쳤다: `OwnCamLocalizer.bias` 속성이 markerless probe 하위 클래스의 `bias()` 메서드를 가렸다. 속성 이름을 `yaw_bias`로 바꿨다(`tests/test_markerless_probe.py` 통과 확인).

## 코드 상태 (모두 미커밋)
- `harness/owncam_carry_v6e.py` (신규): 보정 프로필 로드, 가시 PF 교체, 횡 leg 길이 역산(`leg_duration`).
- `harness/owncam_localizer.py`, `harness/owncam_recovery_v6.py`: 선택 키(`motion_loaded.load_transition` 등)가 있을 때만 동작하는 수정. 키가 없으면 출력 바이트 동일(골든 비교 + 테스트). 프로즌 M2 임포트 해시 테스트에 post-freeze 해시 추가(`tests/test_zone_pair_executor.py`, 현재 파일 해시 36fd50c0...).
- `harness/zone_pair_v6_policy.py`: 플래그 `carry_dr_model`(막힘 1), `carry_lateral_lag`(막힘 2); 정책 `b-v6e-dr`, `b-v6e-lag`, `b-v6e`. `EXECUTION_BUNDLE_ID`, `REVISION_POLICIES`는 아직 안 바꿨다(등록은 마지막에 한 번).
- `harness/zone_pair_executor.py`: `door_schedule` lag 분기, `PairTeam` 활성화·기록.
- `harness/pair_stage_probe.py` 0.6.0: 정책 3개 추가, `SETUP_VARIANTS`(`cal`, `hA`, `hB`, `hC`) + `setup_variant()`, 케이스 id에 `:V<이름>`.
- `scripts/run_pair_stage_probes.py`: `--pf-track`, `--omp-threads`, `--setup-variant`. `scripts/build_pair_stage_probe_views.py`: 약어 ED/EL/E, placement 태그. `scripts/run_ci_tests.py`: `tests/test_zone_pair_v6e.py` 추가.
- `tests/test_zone_pair_v6e.py` (신규, 16개 통과), `tests/test_owncam_bootstrap_v6b.py` 수정.
- `experiments/2026-09-29-pair-v6e-carry/`: `fit_carry_dr.py`, `carry_dr_fit.json` (미추적). README는 아직 안 썼다.

## 완료된 셀 / 남은 셀
- 완료된 물리 셀: 없음. 33셀 격자(플래그별 3구성), 보정 코호트(cal), held-out 코호트 전부 남았다.

## 재개 절차 (조정자 지시 반영: 변경 사항 합쳐서 한 번만 등록, 최종 후보에서 한 번만 전체 측정)
1. 소스 커밋(테스트 전부 통과 후, `;` 연결 금지). 러너가 tracked 소스 clean을 요구한다.
2. `agent_lock.py status` 확인 후 잠금(owner claude), 디스크 여유 10 GiB 이상, `ugrp_session.py run`으로 실행, 워커 2개·`--omp-threads 1`.
3. 보정 코호트: `--setup-variant cal --pf-track`, policy `b-v6e`, legs 0..7, cells `nominal`, `yaw+/same`, `lat-/opp` (33셀과 겹치지 않음). NEES/커버리지로 PF 정직성 확인, 불일치하면 보정 코호트로만 재적합.
4. 최종 후보에서 33셀 격자: `--stage carry --sources teacher --prior-std e2e --seeds 911 --nominal-seeds 911 912 913`,
   - L0: 셀 전부(19), legs 0
   - L1·L3·L6·L7: `--cells nominal lat+/same yaw+/same along+/same corner++/same --legs 1 3 6 7`
   - policies: `b-v6e-dr`, `b-v6e-lag`, `b-v6e` (기준선 `b-v6c` 0/33, 분모 33 = 19-6 + 4x(7-2)).
5. held-out: `--setup-variant hA hB hC`(하나씩), legs 0 1 3 6 7, cells `nominal`(`--nominal-seeds 914`) + `yaw-/opp`, policies `b-v6c`(대조), `b-v6e`.
6. 조정자 지시: 내려놓기(v6f, claude/pair-v6e-place) 코드가 끝났으면 그 변경(등록 파일 제외)을 병합해 통합 플래그로 단계 4·5 probe를 한 번 더 돌린 뒤 번들 v81 / 워크플로 2.14.0 / revision v6e를 한 번만 등록·봉인(v82 / 2.15.0 / v6f는 쓰지 않음). v6f가 안 끝났으면 내 코드까지만 draft PR.
7. README(한국어), TensorBoard 스냅샷(`docs/tensorboard.md`; view.json은 내 키만, 쓰기 직전 다시 읽기), push는 최종 상태에서만 1회.
