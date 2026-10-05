# PR #312 독립 리뷰 C312-1 수정

2026-09-30, 로컬 물리·시뮬레이션·렌더·학습·비전 추론·LLM 호출 없음.
정상 GitHub CI는 허용하며 취소하거나 건너뛰지 않는다.
새 실험/학습/평가 코호트가 없으므로 TensorBoard 변환·서버를 만들지 않는다. Drive 작업도 없다.

## 기준과 원인

- 검토 HEAD: `919f78ef6ebaf2495633338bcb1b9510f46399bd`.
- 먼저 병합한 main: `b10907c5f2c84f2712030f48fb38061fd4f51281` (텍스트 충돌 없음).
- [독립 검토 #318](https://github.com/kcm0127-dotcom/ugrp/pull/318)의 C312-1 및
  [#312 리뷰 댓글](https://github.com/kcm0127-dotcom/ugrp/pull/312#issuecomment-5911187606)을 처리한다.

등록 JSON은 그대로였지만 그 JSON이 고정한 세 소스가 변경되어 있었다.
검토 HEAD의 Git blob으로 각각 해시 불일치를 확인했다. 기존 검사를 지우거나
등록 해시를 다시 쓰는 대신 다음 파일을 main의 원래 바이트로 복원했다.

| 고정 소스 | 복원 뒤 SHA-256 (v6e 등록값과 일치) |
|---|---|
| `scripts/run_zone_study_integration.py` | `85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd` |
| `harness/vision_pose_source.py` | `dc5d5f8d0c0eafae500992ef82635ee6810ba1f71e49f04dc21a298955f6aba7` |
| `harness/zone_study_pose_delay.py` | `5d8cdca5f4b734b640945c49a3e6aeb519b207c4dfb80cb72982ae0c066d2894` |

## C312-1 → 기존 경로 보존과 별도 후보

- PF 수명·prior·clock·늦은 frame 처리는 `harness/vision_pose_source_p03.py`로,
  지연/재측위 명령 보존은 `harness/zone_study_pose_delay_p03.py`로 옮겼다.
  두 후보 클래스는 기존 인터페이스 클래스를 상속해 타입 호환성을 유지한다.
- 조합 검사는 `harness/vision_loc_contract_p03.py`, 호스트 생성·정리와 후보
  bundle/기록 연결은 `scripts/zone_study_provider_p03.py`로 옮겼다.
  공용 객체나 전역 factory를 교체하지 않는다.
- 후보 provider ID는 `vision_zero_tag_v2_p03_v1`이다. 기존
  `vision_zero_tag_v2` factory/ID, 공용 registry와 worker 설정은 그대로다.
  공용 protocol에는 boolean/float seq를 정수 request seq로 오인하지 않는 검사만 남는다.
- 후보 미리보기는 `candidate_id=zone-study-provider-p03-v1`, `execution_bundle_id=null`,
  `runnable=false`, `physical_ready=false`다. 내부 study label도 후보 ID를 쓴다.
  실행 CLI·workflow·runnable 번호는 등록하지 않았다. #292 역사 이관에 의존하지 않는다.
- 기존 등록 JSON·봉인·raw·모델 bytes를 바꾸지 않았다. P03의 미봉인 조합 JSON만
  후보 ID와 복원한 worker 설정 해시를 가리키도록 바꿨다.
- 회귀 검사 `test_candidate_preserves_v6e_bytes_and_prepare_admission`은 후보를 읽은 뒤
  v6e 전체 소스 해시와 현재 계약을 비교하고 기존 `load_config` 준비 허용까지 확인한다.
  기존 `test_zone_pair_registered_source.py`와 `test_zone_study_source_pinning.py`는 수정하지 않았다.
  새 후보가 기존 factory를 덮지 않는 검사와 legacy 지연 wrapper 중첩 거절도 추가했다.

## 관련 C311-1 → 설정·참조 파일의 명시적 계획 해시

- 기존 runner는 이제 P03 JSON을 사용하지 않으므로 기존 ID의 실행 내용만 조용히 바뀌지 않는다.
- P03 후보 모듈의 `RUNTIME_ASSETS`에 JSON·worker·모델 registry·보정 파일을
  리터럴로 공개하고, `runtime_files()`가 JSON의 모든 `active.files_sha256` 참조를 수집한다.
- `run_bundle()`은 이 파일들을 실제 후보 해시에 포함한다. `check_preview()`는
  저장한 미리보기와 현재 입력을 다시 비교한다. C_mix_rgb는 계속 미선택·미배포다.
- 회귀 검사는 저장한 preview를 읽은 뒤 임시 P03 JSON의 camera mount만 변경해
  전체 해시와 해당 파일 해시가 모두 달라지고 이전 preview가 거절되는지 확인한다.
  카메라 참조 소스 자체가 바뀌면 조합 검사에서 거절된다. 실제 작업 파일은 변경하지 않는다.
- #311의 후속 P03 후보 지원은 이 명시적 진입점/자산을 선택해야 한다. 기존 P07 경로에
  후보를 자동 채택하거나 v3 환경의 실행 준비 완료를 부여하지 않았다.
  #311 수정 SHA `f7a3ac29678af5a2b5639504572679d20a1adf56`의 읽기 전용 P03 입력 검사로
  이번 JSON과 참조 파일 15개를 확인했다. 상태는 의도대로 `blocked`다.
  이 검사는 전체 PR 합성이나 후보 실행의 검증은 아니다.

## 검증

`offline_checks.py`에 누락됐던 registered-source와 door-relax 회귀 및 P03 후보
검사를 추가했다. 기존 공용 잠금을 사용하고 MuJoCo/torch/실제 worker/network/
schematic render/태그 검출 guard를 유지한다. 로컬 금지 대상 10개 검사의 제외는
최초 검사와 동일하며 GitHub CI의 테스트 목록은 제외하지 않는다.

main의 새 preflight가 요구한 frozen gzip fixture 3개는 sparse 체크아웃에서 빠져 있었다.
추적 중인 원본 파일만 `git sparse-checkout add`로 다시 포함했고 preflight 통과를 확인했다.

첫 이관 검사에서 **319 passed, 8 failed, 10 deselected**였다. 실패 3개는 후보 클래스가
기존 provider 타입 검사를 만족하지 못한 것이고, 5개는 날짜가 붙은 실험 폴더의 Python
파일을 일반 패키지 이름으로 처리한 것이다. 기존 타입을 상속하고, 명시적으로 동적 로딩하는
실험 소스는 직접 파일 해시로 수집하도록 고쳤다. 기존 85개 소스의 등록 해시는 이때도 일치했다.

최종 로컬 결과: **327 passed, 0 failed, 10 deselected (92.00초)**.
요청된 `tests/test_zone_pair_registered_source.py`와 `tests/test_zone_study_source_pinning.py`는
전체 실행했다. 최종 검사 동안 후보 소스 해시가 바뀌지 않았으며,
신규 테스트 두 파일이 정상 CI의 `test_vision_loc*.py` 목록에 들어가는 것도 확인했다.

검증 결과와 원본 해시는 `review_fix_verification.json`에 기록한다.
로그/JUnit 원본은 `/Users/changmin/projects/ugrp/outputs/e2e-p03-review-fixes-20260930/`에
로컬 보관한다. 최초 구현의 `verification.json`과 raw는 이전 기록으로 보존한다.

실제 이전 leg 이후 3체크포인트 × 120 SIM초, Release 다운로드·로딩, 최종 카메라/모델
보정, 후보의 새 workflow 등록·봉인·인수는 여전히 후속 작업이다.
오프라인 계약 검사는 재측위 정확도·재파지 성공이나 물리 실행 승인이 아니다.
