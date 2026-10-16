# R18 — reference 자산 identity로 유지할 수 있는 비교

**이 경로가 뒷받침하는 것은 선언한 로컬 자산 bytes와 backend 생성 prefix에서 읽은 입력의 연결이다.** reference mode를 사용했다는 이유만으로 모델·참조 이미지가 runtime에서 바뀌었을 것이라고 가정할 근거는 이번 대조에서 나오지 않았다. 반대로 같은 자산 hash만으로 같은 렌더링·실행 궤적·학습 노출 이력을 인증하지는 않는다.

대상은 main `b23fc0875b72f4b55f399a252a1575b7e8b43cb5`의 보존된 `communication-study` / D3 `--asset-mode reference` 경로다. 현재 HIGH pair pilot과 별개다. 기본 preparation은 `dispatch_open`, `physical_replay`, `claim_scope=development_connection_smoke`이며 **solo/joint 두 trial, 모두 condition=none**를 만든다. Pair 모델 슬롯은 r1/r3이며 lower/upper 역할로 선택한다. 학습 slot 이름을 실제 실행 actor ID와 동일시하지 않으며, 3-actor runtime의 solo 경로와도 구분한다. 이 자산 검토 자체는 통신 조건 효과를 검증하지 않는다.

## 비교를 보존하는 필드

| 확인하려는 동등성 | 이 caller의 실제 provenance / gate | 유지 가능한 해석과 경계 |
|---|---|---|
| 준비한 모델·reference bytes가 소비됐나? | `local-assets.json.files`의 절대 경로→SHA, 모델 manifest의 slot/stage→path/SHA, frozen `backend_descriptor.input_hashes`, child preflight 후 `_read_models`와 reference read | catalog는 descriptor의 모든 모델/reference를 포함해야 한다. 아래 합성 대조는 consumer가 선언한 내용을 읽는 지점까지 확인했다. **13 catalog files와 11 backend inputs의 차이 2개는 training report**다. policy 모델 입력이 아니어도 provenance catalog에서는 hash/존재 검사를 받는다. |
| 두 기록이 같은 준비/실행 계약에 속하나? | manifest의 `source.git_sha/clean`, `source_files`, `config_sha256`, `scheduler_id`, `execution_bundle_id`; descriptor의 bundle SHA·map instance/group·camera·reset SHA; trial `run_id/condition/seed` | 이 필드는 자산·설정·map/reset의 선언적 동일성을 구분한다. **descriptor/config hash 불일치만으로 모델 변경이라고 단정하면 안 된다.** reference catalog는 절대 경로로 로컬 host에 묶이고, child는 `output_dir`를 자기 run 경로로 바꾸므로 descriptor의 config digest도 그 경로를 포함한다. 모델 비교에는 정확한 slot/stage/reference hash를 함께 본다. 다른 host의 새 receipt는 원래 로컬 admission을 그대로 승계하지 않는다. |
| 실제 생성된 실행 환경까지 같나? | 실제 backend 생성 후 `backend-provenance.json`: `scene_xml_sha256`, `map_to_scene.scene_xml_sha256`, `effective_execution`, `execution_source`, `execution_environment`; `require_effective`가 scene/model/camera 계약 비교 | preparation은 별도의 static scene XML 증거를 만들지만 descriptor의 scene XML SHA는 처음에는 null이다. live 생성 뒤 채워지는 필드와 applied-contract check가 별도 증거다. 환경 fingerprint는 Python/platform 및 MuJoCo·NumPy·OpenCV·Pillow 버전의 hash이며 rendered pixel이나 전체 기계 상태의 hash가 아니다. **이번 fixture는 scene 생성 직전에 멈춰 이 단계의 실제 pass를 입증하지 않았다.** |
| 같은 관측·행동 시퀀스까지 같나? | backend의 `skill-inputs.jsonl`은 `observation_id`와 이미지 SHA/path를 저장; `worker-timing.jsonl`과 `runtime.jsonl`은 별도 실행 기록. live 단계는 provider policy 비교 후 planner 호출, replay 단계는 명시된 `replay_actions` 사용 | 같은 reference JPEG는 같은 **정렬 참조 입력**이지 매 시점 카메라 영상이 같다는 뜻이 아니다. 같은 asset/bundle은 worker의 실제 소비 시점이나 외부 모델 응답도 고정하지 않는다. 관측/실행 시퀀스를 비교하려면 해당 실행의 입력 ID/hash·시간·action 기록이 필요하다. 이 메모는 그 원시 기록을 읽거나 동일성을 판정하지 않았다. |
| 학습 노출과 일반화 근거까지 같나? | preparation의 exposure 기록은 legacy grasp/alignment lineage를 `origin=unknown`으로 남김. `assess_environment`는 reviewed source/data/checkpoint/prompt와 map/stratum을 별도 확인 | report hash는 **어느 보고서 bytes를 썼는지** 보존한다. 보고서 내용의 사실성·원래 학습 데이터·미노출 여부를 새로 인증하지 않는다. 이 preparation의 regression/development label을 새 heldout/generalization evidence로 바꿀 수 없다. unknown lineage를 동일 hash로 지우지 않는다. |

## 확인된 대조와 제안의 경계

Coverage 담당의 [source 감사](boundaries.md#reference-assets), `reference-assets-repro.py` (Mac 전달본 증거)과 `reference-assets-result.json` (Mac 전달본 증거)를 source와 대조했다. 기존 모델·이미지·결과 대신 새 authored bytes와 임시 Git/manifest를 사용했다. reference는 JPEG 시작/끝 표식만 갖춘 합성 bytes이며 이미지 decoding 검증도 아니다. 실제 `prepare_assets → prepare_manifest/preflight → run_trial → build_rgb_skill_backend`의 자산 read까지 실행했고, scene 생성은 sentinel로 중단했다. environment/bundle/audit/runtime-limit 협력자는 명시적 대역이므로 **full study admission이나 실제 물리 실행의 검증이 아니다**. learned-model 내부 추론 schema와 이후 replay action 실행 적합성도 이 fixture가 확인한 범위가 아니다. 나는 재현을 다시 실행하지 않았다.

- 원래 자산은 13개 catalog/11개 backend 입력과 네 provenance receipt가 연결됐고 consumer 직전 모델 내용·reference bytes가 일치했다.
- 모델 bytes만 변경, 모델과 그 내부 manifest를 함께 변경, reference 변경, training report 삭제는 고정된 외부 catalog/descriptor에 의해 child consumer 전에 차단됐다. 내부 manifest를 일관되게 고쳐도 이미 준비된 identity를 승계할 수 없다는 대조다. “hash가 같지만 다른 자산이 통과했다”는 결과가 아니다.
- D3의 `local_assets`와 descriptor evidence를 제거한 대조도 차단됐다. 따라서 모델 hash 검사만 있고 training report/reference binding이 빠졌다는 가설은 이 범위에서 기각된다.

기존 기록을 정리할 때는 **자산 identity**, **실제 applied execution receipt**, **관측/행동 시퀀스**, **exposure/claim scope**를 따로 표시하면 된다. 첫째가 확인되고 뒤의 자료가 없으면 “동일 자산을 선언·검증한 development 입력”이라는 비교는 보존하되 실제 실행 동일성은 미확인으로 남긴다. 실제 run의 수정·재채점·재실행을 이 메모에서 요구하거나 수행하지 않는다. 새 구현 finding도 추가하지 않는다.

## 1차 소스와 읽은 범위

논문 일반론을 덧붙이지 않고 이 caller의 공식 저장소 코드를 1차 근거로 사용했다. `reference-identity-research-source-manifest.json` (Mac 전달본 증거)에 exact 6개 파일 hash를 보존했다.

- [prepare_rgb_communication_replay.py](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/scripts/prepare_rgb_communication_replay.py): `prepare_assets`, preparation의 scene/reset/provenance 및 최종 config. `prepare()` 전체나 그 안의 pytest/scene XML 생성은 실행하지 않았다.
- [rgb_communication_study.py](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/rgb_communication_study.py): reference/local asset 검증, manifest, environment/preflight의 관련 분기, `run_trial`의 consumer/provenance/write, `run_study`의 environment writer.
- [rgb_skill_execution.py](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/rgb_skill_execution.py): `_read_models/backend_descriptor/_applied_contract`, `build_rgb_skill_backend`의 assets·scene·frame/worker writer·provenance. 실제 renderer/skill 실행은 안 했다.
- [rgb_execution_bundle.py](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/b23fc0875b72f4b55f399a252a1575b7e8b43cb5/harness/rgb_execution_bundle.py): `environment_fingerprint/source_identity/require_effective` 및 identity 관련 상수. workflow registry/D3 안내는 지원 entrypoint 확인 범위다.
