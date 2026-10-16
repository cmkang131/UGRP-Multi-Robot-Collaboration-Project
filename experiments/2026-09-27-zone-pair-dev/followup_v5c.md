# PR #240 dev09/dev10 후속 수정 — 2026-09-28

작업 HEAD `3ea2edc08e5addafaf3cedc934c463ad8e1635c8`, 브랜치 `codex/zone-pair-grasp-relook`.
기준 진단은 `origin/codex/zone-pair-parity` (`3b2e19e7b2181036d951d4c7c69813fe43a01c17`)의
`experiments/2026-09-27-zone-pair-parity/dev09_10_diagnosis.md`다.
원본 `outputs/zone-pair-dev-v5b-3ea2edc08e5addafaf3cedc934c463ad8e1635c8`는 primary에서 읽기만 했다.
Git fetch는 공유 FETCH_HEAD 쓰기 제한, gh PR 조회는 네트워크 제한으로 실패했다.
원격 최신 상태를 확인했다거나 PR을 갱신했다고 주장하지 않는다. 커밋·push·병합 없음.
공통 `owncam_pose_source.py`와 `zone_own_perception.py`는 이번 요청으로 의도적으로 수정했다.
과거 M2/perception 실행 manifest·소스 pin은 그대로 두고 테스트에 정확한 후속 해시만 추가했다.
과거 실행 소스 전체가 현재 코드와 같다는 주장을 하지 않으며 기존 M2 CLI/제어기는 보존했다.

## P1과 저장 판단 재생

`last_tag_t`는 localizer가 수용한 자기 태그의 원시 capture 시각이다. 별도로 반올림되는
`t_est - since_tag_s`로 capture를 복원하지 않는다. align은 `last_tag_t > look_start`를 엄격 적용한다.
pregrasp와 일반 look은 기존의 시작 시각 포함 정책을 유지하되 시작 이전 태그는 허용하지 않는다.
원시 capture가 현재보다 미래인 경우도 계속 거부한다.

공통 `harness/owncam_time.py`의 `POSE_TIME_ROUNDING_S=1e-4`를 zone 계약에서 재수출한다.
보고 신선도는 `-tol <= now - t_est <= max_age + tol`, capture/정지 시각과 보고 비교는
`raw_time <= t_est + tol`이다. 양방향 양자화만 허용하며 5 cm/3°/7 cm/35 mm는 그대로다.
실패 이벤트는 `checks`, `failed_checks`, accepted capture/report/start 시각을 남긴다.

[fixture](../../tests/fixtures/zone_pair_v5c/manifest.json)는 10건의 저장 보고·capture metadata와
JPEG 3장(두 blockage와 σ 초과 재관측), 원본 파일 해시, 당시 판정 함수 발췌를 담는다.
JPEG는 재인코딩하지 않았다. 저장 보고의 gate hysteresis를 자기 보고 순서로 재구성했다.
수정 전 **0/10**, 수정 후 **9/10**. dev10 r1 첫 판단은 XY σ **0.05601 m**이며
`std_xy`, `sigma_reserve`, 당시 `gate_ok`가 거부한다. PF 입자/RNG 전체나 이후 행동의 재생이 아니다.
특히 첫 분기 뒤 원본 pan 경로는 수정 제어기의 새 행동 경로를 대신하지 않는다.

## 같은 계열 시각 비교 전수 감사

`rg`로 `harness/`와 `scripts/`의 `t_est`, `since_tag_s`, `last_tag_t` 비교를 전부 조사했다.

| 경로 | 처리 |
|---|---|
| align fix·pregrasp fix | 공통 accepted capture conjunct, 양방향 보고 허용오차, 실패 항목 기록 |
| PairCommandGuard 정지 캐시·align_stop_ready | 보고 대 원시 명령 종료/hold 시각 비교에 같은 허용오차 |
| pair admission·before_control·명령 guard | 공통 freshness를 사용하므로 미래·stale 양 끝에 같은 허용오차; admission에는 기존 failed_checks 유지 |
| 일반 own look_around | 반올림 age 대 경과시간 비교 제거; accepted capture와 보고 포함 여부로 판정 |
| owncam_pose_source.check_limits | 같은 보고 freshness 경계, 비유한·큰 미래 보고도 거부 |
| memory-v3 frame admission·grasp/release boundary gate | 엄격 1e-8 보고 비교를 공통 1e-4 계약으로 변경 |
| align의 tag-gap 스케줄 | 실행 중 accepted capture로 age 계산; 저장보고 진단용 fallback만 rounded age 사용 |
| owncam_pose_guard_v3 보고 순서 | 같은 종류의 보고 시각끼리 단조성/중복 검사이므로 유지 |
| pair approach/GuardedPairApproach last_tag_t ≥ look_t0 | 양쪽 원시 시각. pre-look 태그 허용 방지를 위해 그대로 유지 |
| owncam_pose_guard_v3 measured tag 시각 | 같은 원시 capture와 now가 같은 측정인지 검사하므로 유지 |
| TRUSTED_TAG_AGE_S·LOOK_IF_NO_TAG_S | 보고 age와 고정 정책 한도의 비교; capture 시각 재구성이 아니므로 유지 |
| RGB sim_time·명령/STATUS GO·arm deadlines·beam anchor 시각 | 원시 capture/명령끼리 비교. PF 보고 반올림 허용오차를 확장하지 않음 |

## P2 목표 화물과 장애물 구분

활성 자기 `pair_carry` 작업과 주문서의 `long_beam` 1개가 일치해야 한다. 첫 pickup에서만
고정 coarse order와 자기 자세를 쓰며, 이후에는 같은 segment의 신선한 자기 RGB anchor와
자기 발행 명령 예측이 필요하다. 계획된 후속 checkpoint를 실제 화물 위치로 사용하지 않는다.
σ가 loaded HIGH(7 cm/3°)를 넘거나 source/segment/age/예측 시각이 맞지 않으면 제외하지 않는다.

현재 자기 JPEG의 black grip band·색·축/위치 및 전체 영상 성분의 지지가 모두 맞는 성분만
`expected_target_occupancy`로 기록한다. 다른 색, 알려지지 않은 물체, 합쳐진 빨간 물체,
잘못된 주문서, 없는/만료된 앵커는 계속 장애물 후보다. beam/wall 충돌 및 35 mm guard는 그대로다.
perception의 BGR 계약에 맞게 `_judge`는 보존된 JPEG를 전달한다(RGB 배열을 BGR로 오해하지 않음).
색/그림자/성분 지지 수치는 이 dev 영상에 대한 association 기준이며 일반 물체 인식 정확도의 검증이 아니다.

두 저장 blockage 프레임에서 목표 빔만 후보에서 빠지고 다른 성분은 남는 것을 검사했다.
따라서 전체 `route_blockage=yes`가 남을 수 있다. dev09 실제 사건은 이미 job 종료 후였으므로
새 코드에서도 활성 작업이 없으면 제외하지 않는다. 그 영상의 제외 회귀는 활성 작업을 가정한
성분 식별 검사이며 과거 사건을 소급 삭제하거나 원래 실패 원인을 바꾸지 않는다.

## 새 등록과 검증 범위

[prereg_v5c](prereg_v5c.json): dev11/907 정상 시도, dev12/908 carry-GO abort.
setup 화물·주문서·개입, criteria/stage_rules/planned_setdown/limits/timing/safety_coverage/environment/inputs는
v5b와 동일하다. `supersedes`는 v5b 파일의 정확한 해시다. scene 및 grasp 계약은 새 수정 소스를 묶는다.
workflow 0.4.0/profile과 STATUS를 유지하고 새 revision/해시로 구분하며 새 dispatch 번들은 만들지 않는다.
코디네이터 실행 명령은 [grasp_v5.md](grasp_v5.md)에 갱신했다.

검증 영수증은 [followup_v5c_validation.json](followup_v5c_validation.json)에 기록한다.
관련 전체 **1,144 passed / 15 skipped / 101 subtests passed**(97.13 s). 마지막 비유한 입력 거부 보강 뒤
변경 영향 범위 **167 passed**(6.47 s, 신규 v5c 58건 포함)를 다시 확인했다. 두 집계는 중복이므로 합산하지 않는다.
15개 skip은 MuJoCo import가 필요한 fake-world 검사이며 물리 실행은 아니다.
dev11/dev12 모두 `prepared_not_executed`, `applied=null`, `physical_success=null`, 모델 호출 0;
prereg 바이트 복사와 setup-only scene 해시를 확인했다. 원본 21개 파일 해시 일치, JPEG 3장 포함
fixture 전체 98,250 bytes, 과거 v3/v4/v5/v5b 등록 바이트 보존을 확인했다.
기존 Mac venv, `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`,
pytest `--basetemp=./.pytest_tmp -p no:cacheprovider` 사용. 테스트 부모/자식에서 MuJoCo·모델 모듈
import를 차단하고 종료 시 `.pytest_tmp`를 삭제한다. 물리 잠금은 획득하지 않는다.

물리 step·모델 호출 0. GT·eval_only 제어 유입 없음. weld OFF·cargo_noslip_v1 유지.
새 물리/학습/평가 결과를 만들지 않은 코드 회귀이므로 TensorBoard 재변환·서버·화면 재개방은 생략한다.
이전 진단의 TensorBoard 표시 미완료를 해결했다는 뜻이 아니다. dev11/dev12의 소스 검토·별도 커밋/고정,
유한 물리 실행, 영상·완주 평가와 TensorBoard 등록은 아직 수행하지 않았다.
UGRP 예외에 따라 Drive를 사용하지 않았다. fixture 로컬 보존은 raw 원격 백업이 아니다.
