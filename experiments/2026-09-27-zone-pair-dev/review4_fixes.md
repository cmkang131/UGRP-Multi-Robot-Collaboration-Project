# PR #240 review4 반영 — 2026-09-27

기준 HEAD `3839555dc0de0880f74a40c831044e2b5be2d2d7`, 브랜치
`codex/zone-pair-grasp-relook`. **미커밋 수정 · 비물리 회귀 · prepare-only**다.
물리 step·실모델 호출·Git 커밋/push/병합은 하지 않았다.

## P1: 정지 이후 유효 보고를 확보한 뒤 PF 초기화

`align_relook_stop`에서 다음 tick이라는 이유만으로 초기화하지 않는다.
발행한 hold 이후 시각의 initialized·fresh·유한한 자기 자세 보고, 기존 gate OK와
HIGH 이하의 불확실성, 같은 보고로 채운 guard의 정지 캐시가 모두 필요하다.
기다리는 동안 PF를 유지하고 hold만 발행한다. 이 시간은 기존 회당 8초·누적 40초에
포함되며 재관측 횟수·방향 수·원래 align deadline도 바꾸지 않았다.

실제 PairTeam/M2 어댑터·저장 자기 RGB·실제 `DelayedPoseSource(0.16 s)`를 사용한
회귀를 추가했다. 2.00초 admission부터 시작하여 2.10초 허용된 이동 명령을 실제
guard/host 발행 경로로 전달하고, checkpoint 이전 align 진입을 검사한다.
무이동 대조군과 기존 checkpoint 재관측/READY/GO 회귀도 유지한다.
새 구간은 20 Hz 자기 RGB 전달을 사용한다. 자세 결과·지연·guard를 stub으로 바꾸지 않는다.

| 조건 | 2.20초 | 2.30초 (`t_est=2.14`) | 2.35초 | 2.40초 (`t_est=2.24`) |
|---|---|---|---|---|
| 검토 HEAD 메서드, 이동 있음 | hold, 캐시 없음 | PF 초기화, 캐시 없음 | r1 POSE_UNCERTAIN / r2 PARTNER_ABORT | 종료 유지 |
| 검토 HEAD 메서드, 이동 없음 | hold, 기존 캐시 있음 | PF 초기화 | 중단 없음 | 중단 없음 |
| 수정본, 이동 있음/없음 | hold | 초기화 대기 | 초기화 대기, 중단 없음 | 정지 이후 보고·캐시 확보 후 초기화 |

[재현 영수증](review4_align_replay.json)은 검토 HEAD의 해당 메서드 bytecode와 수정본을
별도 프로세스 안에서 비교한다. 기존 메서드의 `super()` class cell만 실제 mixin에
연결했다. 회귀 테스트 본체는 수정한 production 경로 그대로 실행한다.
양쪽은 2.60초까지 중단 없이 guard를 거친 팔 명령을 발행한다.
별도의 유효성 회귀는 정지 이전·미초기화·HIGH·NaN·stale·미래 보고, 닫힌 gate,
아직 끝나지 않은 명령을 거절하고 기존 상한에서 양쪽 abort/큐 정리를 확인한다.

이것은 가짜 clock/port의 프로토콜 재생이다. 전체 접근·운반 궤적, 정지의 물리적 달성,
새 시선에서의 실제 재위치추정 성공을 입증하지 않는다.

## P2: 유효한 current-source fixture에서 정확한 거부 원인 확인

변조 전 fixture를 현재 scene/grasp 계약으로 만들고, dev09/dev10 각각
`load_config` 성공을 먼저 확인한다. 한 항목씩 바꾼 뒤 전체 오류 문자열을 대조한다.

| 변조 | 기대하는 정확한 ValueError |
|---|---|
| criteria | `v3 must preserve v2 criteria` |
| seed | `v5 fixes [('dev09', 905), ('dev10', 906)]; do not reuse prior IDs` |
| grasp hash | `grasp contract/hash mismatch` |
| stage_rules | `v3 must preserve v2 stage rules` |
| supersedes hash | `previous prereg hash mismatch` |

변조 5종 × 2회차 모두 통과했다. 원본이 이미 무효라 임의의 ValueError로 통과하는
경로를 없앴다. 기존 dock 테스트도 현재 등록 v5b와 정확히 대조하며, 과거 등록의
prepare 성공을 기대하거나 과거 소스 해시를 다시 쓰지 않는다.

## 등록과 prepare

새 [prereg_v5b.json](prereg_v5b.json)의 `registration_version=5`,
`registration_revision=v5b`로 구분한다. [실행 버전 관리](../../docs/execution_versioning.md)의
변경·검증 순서 2–4에 따라 기존 v5 바이트를 보존하고 정확한 `supersedes` 해시로 연결했다.
main 병합 후 scene 계약과 이번 PF 초기화 수정의 grasp 소스 해시를 새로 고정했다.
workflow 0.4.0과 실행기 profile은 그대로이며 revision과 해시로 이번 후보를 식별한다.
v5는 아직 물리 실행 전이므로 dev09/905·dev10/906을 재등록했다. 실행 결과는 승계하지 않는다.

v5 대비 `runs`, `criteria`, `stage_rules`, `planned_setdown`, `limits`, `timing`,
`safety_coverage`, `environment`, `inputs`, `scene_instances`, `contact_profile_contract`는
동일하다. 설명의 seed 표기 903/904만 실제 dev09/dev10의 905/906으로 바로잡았다.
`grasp_v5.md`의 준비·실행 명령과 raw 디렉터리 템플릿은 v5b를 가리킨다.

MuJoCo·torch·tensorflow·openai·anthropic import를 차단한 프로세스에서 두 회차 모두
`prepared_not_executed`, `applied=null`, `physical_success=null`, `model_calls=0`을 확인했다.
등록 파일 복사 바이트와 정적 setup scene hash가 일치하고 실행 trace는 생성되지 않았다.
준비 결과는 `/private/tmp/ugrp240-v5b-prepare-5xn46ohd/{dev09,dev10}`에 보존했고,
파일별 해시·현재 실행 소스 fingerprint는 [검증 영수증](review4_validation.json)에 있다.

## 최종 검증과 범위

- **545 passed, 14 skipped, 4 deselected / 53.74초.** pair 전체 회귀,
  own guard/sweep, 지연 제공자와 등록/평가 테스트를 포함한다.
- 14개는 MuJoCo import를 전제하는 fake-world/정적 검사여서 건너뛰었다.
  4개 모델 어댑터 호출 fixture 검사는 이번 선택에서 제외했다. 실모델 호출은 없다.
- 모든 pytest는 `OMP_NUM_THREADS=1`, `PYTHONDONTWRITEBYTECODE=1`,
  `--basetemp=./.pytest_tmp`, `-p no:cacheprovider`로 실행했고 종료 후 `.pytest_tmp`를 삭제했다.
- 과거 등록·결과·보호 소스/번들 **112개**를 HEAD와 바이트 비교했다.
  v3/v4/v5 원본, 동결 M2, 기존 안전 임계값·STATUS, workflow 카탈로그는 변경하지 않았다.
- 변경 Python AST 및 `git diff --check` 통과. GT·접촉·측정 관절·eval_only의 제어 유입 없음,
  **weld OFF / cargo_noslip_v1** 유지. 비물리 검사만 실행하여 잠금을 획득하지 않았다.

최초 확장 회귀에서 dock 테스트의 과거 v5 소스 참조 때문에 5개가 실패했다.
v5b 현재 계약과 정확히 대조하도록 수정한 뒤 위 최종 선택 전체가 통과했다.
초기 유효성 fixture의 unloaded gate 설정과 진단용 메서드 class cell 오류도 수정·재확인했다.

Git fetch는 공유 FETCH_HEAD 쓰기 권한, gh PR 조회는 네트워크 제한으로 실패했다.
원격 PR/CI의 최신 상태를 확인하지 못했고 기본 checkout은 변경하지 않았다.
물리 검증, 코디네이터의 소스 커밋·동결과 dev09/dev10 실제 실행은 남아 있다.
새 물리/학습/평가 결과가 없어 TensorBoard 변환·서버 시작·재개방은 하지 않았다.
UGRP 예외에 따라 Google Drive는 사용하지 않았으며 모든 기록은 로컬이다.
