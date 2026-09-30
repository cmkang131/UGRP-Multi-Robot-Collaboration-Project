# P06 — 평가 전용 심판과 원본·TensorBoard 연결 검사

UGRP의 [READINESS S11/S14](../READINESS.md) 작업이다. 기준 감사 SHA는 `a8094cc14e098a55483f53a3c49bf6a0b116043d`. AGENTS.md·CONTRIBUTING.md·README.md·docs/current_status.md·docs/tensorboard.md를 읽고 fetch/열린 PR을 확인한다. 배정된 자기 worktree/codex 브랜치만 수정한다.

**범위:** synthetic truth·가짜 완료/실패 기록을 써서 referee→trial record→raw manifest→TensorBoard export의 일관성을 검증/보완한다. 물리/시뮬레이션/렌더/모든 모델 호출 금지. 실제 실험 결과를 새로 만들거나 기존 snapshot에 덮어쓰지 않는다. fake 자료는 임시 폴더에 두고 연구 결과로 공용 대시보드에 게시하지 않는다.

대상/출처:

- `harness/zone_study_referee.py`, `harness/zone_study_eval.py`
- `scripts/run_zone_study_integration.py::referee_truth/write_outputs/write_study`
- `sim/zone_hidden_events.py`, `sim/zone_eval_top.py`(읽기·fake 계약만)
- `scripts/tensorboard_tools/`, `scripts/export_tensorboard.py`, `docs/tensorboard.md`
- `tests/test_zone_study_referee.py`, `tests/test_zone_study_eval.py`, `tests/test_tensorboard_export.py`
- PR #257/#241/#291. 주의: `test_zone_study_referee.py`에는 MuJoCo 모델+`mj_forward` 검사도 있으므로 **파일 전체를 무조건 실행하지 말고** 순수 synthetic 테스트만 선택한다.

완료 기준:

1. item/order ID join, 전체 발자국·높이·속도·손에서 놓임·정착 시간을 synthetic truth로 검사한다. 경계 일부 포함·잡고 있음·늦은 완료·중복 배송·동색 다른 개체·시작 전 HOST_ERROR가 성공으로 잘못 세어지지 않아야 한다.
2. `eval_only` truth·TOP 설정/영상·hidden event만 바꾸고 own input/명령/수신 메시지를 고정했을 때 payload/request/wake가 불변임을 검증한다. 심판은 run 종료/평가만 결정하고 robot 완료 통보를 만들지 않는다.
3. terminal 성공/정책실패/API/HOST_ERROR/interrupted/not_evaluated의 분모·SIM cap·모델 비용·미상 usage·누락 여부를 manifest와 exporter에서 유지한다. 파일 누락/해시 변조는 거절한다.
4. 이벤트 파일을 다시 읽어 source 숫자와 대조한다. TOP camera JSON과 실제 video file 등록을 구분하고, GT 그림을 TOP RGB로 표시하지 않는다. 모델 요청 원문 이미지는 샘플링해 버리지 않는다.
5. D1의0.1초/1초 비교창은1Hz 기록만으로 재현할 수 없다는 캡처 계약을 명시한다. 입력이 없는 metric은0으로 만들지 않는다.
6. 코디네이터가 실제 첫 결과에서 수행할 snapshot→event readback→공용 logdir→영상→pin/HParams UI 검증 명세를 남긴다. 이 작업에서는 실제 결과/화면 완료를 주장하지 않는다.

pytest는 side effect를 확인한 대상만 공용 잠금 보호로 실행한다. 통과 후 커밋·push, 커밋 말미 빈 줄 다음 `Co-Authored-By: Codex <noreply@openai.com>`. DRAFT PR `--repo kcm0127-dotcom/ugrp`, `Refs #223, #224, #226`, `## 참고 자료`, 마지막 `Generated with Codex`. **병합 금지**, raw/기존 snapshot 보존·Drive 없음. 한국어로 synthetic 검증과 실제 결과/화면 미확인을 분리한다.
