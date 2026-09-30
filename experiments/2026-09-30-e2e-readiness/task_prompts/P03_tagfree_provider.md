# P03 — 무표식 위치 제공자와 재측위의 상태 보존

UGRP main 기준 감사 `a8094cc14e098a55483f53a3c49bf6a0b116043d`의 [READINESS S02/S03](../READINESS.md)를 처리한다. AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md를 읽고 fetch/열린 PR을 확인한다. `/Users/changmin/projects/ugrp`의 배정된 자기 worktree/codex 브랜치만 수정한다. 다른 작업의 소스·공용 설정은 바꾸지 않는다.

**CI:** 아래 실행 금지는 이 Mac의 로컬 작업 범위다. 정상 GitHub CI는 실행하고 결과를 확인한다. CI를 취소하거나 `[skip ci]`를 쓰지 않는다.

**범위:** 실제 추론 대신 fake worker/저장된 관측 JSON을 써서 provider 생성·dock prior·명령 이력·재측위·fix 지연·close와 모델 자산 명세를 연결한다. 물리/시뮬레이션/렌더/학습/비전 추론/LLM 호출 금지. 로컬 기존 모델 bytes의 해시는 확인할 수 있으나 모델을 로딩/실행하거나 Release를 업로드하지 않는다.

출처/대상:

- `harness/vision_pose_source.py`, `harness/vision_motion_init.py`, `harness/vision_loc_protocol.py`
- `harness/m2_provider_adapter.py`, `harness/zone_study_pose_delay.py`, `scripts/run_zone_study_integration.py::StudyTeamHost`
- `configs/vision_loc_worker.json`, `configs/zone_study_integration/pose_providers.json`, `configs/model_artifacts.json`
- `experiments/2026-09-29-carry-relocalization-b1/README.md`(#279), `experiments/2026-09-29-seg-lightfloor/README.md`(#282)
- `tests/test_zone_pair_provider_init.py`, `tests/test_zone_study_pair_delay.py`, `tests/test_zone_pair_tag_boundary_matrix.py`, `tests/test_zone_study_source_pinning.py`

중요한 차이: B1은 정지 프레임·GT 근처에서 새 PF를 만들어 위치 p90 3.7cm였지만, runtime `begin_relocalization()`은 예측 belief를 유지하고 과거 fix만 무효화한다. GT 초기화나 oracle 분할을 runtime으로 복사하면 안 된다. 현재 worker의 모델은 seg-v2이고 밝은 바닥 C_mix_rgb는 runtime/Release에 연결되지 않았다.

완료 기준:

1. own dock prior는 시작 전 딱 한 번만 주며 출처를 기록한다. 재측위 때 dock/GT로 되돌리려는 시도는 거절한다.
2. 접근→정렬→grasp/lift→carry→lower/open→p20 scan→regrasp 동안 PF 객체/명령 clock/분산/servo history가 이어진다. stale·future·누락·worker 실패 응답은 fix가 되지 않아야 한다. 상대 frame/GT에 접근할 수 없는 fake 객체로 검사한다.
3. 고정0.16 SIM초 wrapper와 worker 설정의 미부과 표기를 대조해 실효값을 bundle/기록에 명확히 남긴다. 중복 지연 부과·늦은 frame의 과거 시각 재사용을 반례로 잡는다.
4. 모델/렌더/로봇/카메라 보정 조합을 명시적으로 pin한다. P01과 registry 파일을 공유 편집하지 않는다. C_mix_rgb 선택은 별도 opt-in 준비 항목으로 만들고 미배포·미검증을 그대로 표시한다. 모델 성능이 좋아졌다고 기본 채택하지 않는다.
5. 코디네이터에게 실제 이전 leg를 거친3체크포인트×120 SIM초 검증, 모델 Release의 다운로드·해시·로딩 검증과 최종 모델 보정 검증을 남긴다.

검사 파일에 MuJoCo/추론 side effect가 없는지 읽고 공용 pytest 잠금을 재사용한다. 통과 후 커밋·push, 말미 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. DRAFT PR은 `--repo kcm0127-dotcom/ugrp`, `Refs #216, #219, #223`, `## 참고 자료`, 마지막 `Generated with Codex`. **병합/봉인 금지.** 기존 raw·모델·번들 bytes 보존, Drive 없음. 한국어로 검증한 계약과 아직 안 잰 실제 재측위/재파지를 구분한다.
