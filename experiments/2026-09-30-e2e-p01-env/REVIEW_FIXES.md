# #305 독립 검토 A305-1/2/3 수정

검토 대상 `5a852fbfde3b0df836f3a423be29a774a9c54614`,
[독립 검토 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/305#issuecomment-5911311999).
먼저 `origin/main`의 `b10907c5f2c84f2712030f48fb38061fd4f51281`을 병합했다.
텍스트 충돌은 없었고, 변경 파일·검증 기록은 이 문서를 포함한 커밋으로 식별한다.

## 지적 → 수정

| 지적 | 수정 | 회귀 검사 |
|---|---|---|
| A305-1: 도크 지도에 일반 tagged validator를 적용해 factory 이전에 거절 | 도크 ID는 기존 `dock_map()`으로 검증한다. 기존 own-scene 경로와 새 어댑터 모두 같은 `DockTaggedCargoZoneScene`으로 위임한다. 미검증 final provider 거절은 유지한다. | `test_review_a305_1_dock_reaches_existing_factory`: 두 경로에서 fake factory 정확히 1회, 접촉 프로필 보존 |
| A305-2: runner/Scene provider 수정으로 v6e의 현재 소스 봉인 실패 | runner·Scene provider·scenario 모듈을 main bytes로 복원했다. 새 기능을 별도 파일로 옮기고 기본 경로에서 분리했다. 기존 등록부/기대 hash/검사 조건은 수정하지 않았다. | `test_review_a305_2_v6e_pinned_sources_and_legacy_closure_remain_unchanged`, 기존 registered-source/source-pinning/door-relax 검사 |
| A305-3: #292 후보에 숨은 registry/catalog/dynamic Scene 의존성이 빠짐 | 기존 경로에는 새 의존성이 남지 않게 했다. 환경을 선택하는 새 후보는 `candidate_contract(base_contract, map_id)`로 기반 계약과 환경 입력을 합성한다. 원래 기반 계약은 복사·보존하고 그 source pin도 검증한다. registry·catalog·선택/부모 지도·보정·선택 Scene과 Python closure가 모두 명시 입력이다. | 6개 지도 구성 확인, registry/catalog 2종/map/Scene/adapter 실제 파일 변조 6종 거절, 누락 pin/기반 계약 변경/오래된 기반 source hash 거절 |

새 API는 `harness.zone_environment_registry.validate/bundle_for`,
`sim.zone_environment_scene_provider.own_scene/scene_static_map`,
`scripts.zone_environment_bundle.run_bundle`이다. 기존 함수 전역을 patch하거나
기존 실행 진입점에 새 코드를 주입하지 않는다. 새 bundle은 별도 schema의 정적
미리보기이며 `execution_bundle_id:null`, `base_execution_bundle_id:<기존 ID>`,
`status:DRAFT_UNSEALED`, `runnable:false`, `research_result:false`다.

v6e 소스 85개와 #249 legacy 파일 26개, 기존 지도·시나리오·catalog·사전 등록 bytes를
보존한다. 복원한 runner SHA-256은
`85508cc58e1cba0f1fc11e3b7ef656c0c7648202ff1086c274c3dbaa64a99edd`,
Scene provider는 `68b3f649b957af34db30ebec39b93ee45d8f7aee7b84c479154cd2ffc833e48b`다.

## #292 합성 확인

#292 `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`의 정적 archive에 이번 새 환경 파일만
겹친 임시 트리에서 [check_p292_composition.py](check_p292_composition.py)를 실행했다.
실제 #292 브랜치·기존 등록 파일에는 쓰지 않는다. 검사 구분은 다음과 같다.

- 기존 #292 `candidate_contract('v6h')`와 도크 경로는 새 registry를 읽지 않는다.
  registry status를 바꾸어도 그 기반 계약과 기존 도크 fake factory 경로가 유지되어야 한다.
- `candidate_contract(base_candidate('v6h'), map_id)`로 환경을 선택하면 registry와
  동적 Scene이 pin에 포함된다. 같은 registry 변조를 검증기가 거절해야 한다.
- 이 합성은 파일/가짜 factory 검사다. #292 봉인·등록·실행 승인이나 최신 #292의
  물리 검증 결과를 상속하지 않는다. 최종 실행에서 새 환경을 채택하려면 이 계약과
  새 실행 어댑터를 별도 등록/봉인해야 한다.

## 검증 기록

**339 passed / 0 failed**, 99.44초. 요청된 두 소스 고정 검사와 기존 실패 6개를 포함한다.
#292 합성 검사도 통과했다(기반 source 274개, 환경 합성 280개, 도크 fake factory 2회).
검증 결과와 원본 해시는 [REVIEW_FIXES_VERIFICATION.json](REVIEW_FIXES_VERIFICATION.json)에 기록했다.
선택 회귀는 기존 Mac Python 3.12와 `scripts.run_ci_tests`의 공용 잠금을 사용한다.
7개 파일: environment registry, final environment, scenario, integration seams,
study source pinning, pair registered source, pair door relax.

처음에는 main이 추가한 사전 검사에서 sparse checkout의 고정 gzip fixture 3개 누락을
발견했다. Git의 원래 파일만 복원했다. 다른 작업이 잠금을 보유한 시도는 exit 3으로
pytest를 시작하지 않았다. 실패/대기 원문은 로컬 `outputs/e2e-p01-env*`에 보존한다.

일반 GitHub CI를 실행하며 취소/skip 표식을 사용하지 않는다. 새 소스의 검사 통과와
실제 운반 성공은 별개다. 물리·렌더·모델 호출·새 실험 cohort는 없으며 TensorBoard
재변환/서버 기동/Drive 작업도 하지 않는다. 최종 지도 reset/충돌/카메라와 v3 보정은
원래 [후속 인수 계획](README.md)에 남아 있다.
