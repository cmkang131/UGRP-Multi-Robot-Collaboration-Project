# S4 LLM 연결 사전 구현 (시뮬레이션 없음)

- 기준 main: `da92d91dbf4af193d3aa3559de9efe55653ec5c0`, #371 병합 포함.
- 계획: [S4 행](../2026-10-05-scenario-e2e-gap/README.md), DEV `dev_s1lite`만.
- S3: [DRAFT #394](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/394), 읽은 SHA `2669eee28b56cd54f655c285a5e57d0916a895c9`에는 계획만 있음. 다른 브랜치 수정 없음.
- 단독 cyan/r3는 v106의 `deliver`, 동서 빔 r1/end_neg·r2/end_pos는 `pair_carry`로 전달. 일반 claim과 짝 carry_decision/post_look_decision을 한 호스트에서 처리.
- 기존 RobotLink·IntegratedTrial·#371 StopAdapter·PairLiveLedger(MainStudySendLedger)·비용/메시지/완료 검사를 재사용한다.
- 이 작업은 stub 실행기와 저장된 합성 모델 응답만 시험한다. 실제 모델·시뮬레이션·MuJoCo compile/reset/render·물리 실행 금지. S4 졸업(실제 no_comm 3 seed 완주)은 미확인이다.
- 새 실행 경로/번들/workflow 번호 없음. 실제 실행 CLI는 이 작업에서 열지 않는다. DRAFT 유지·병합 금지.
- worktree 기본 명령은 기존 Codex 16개/상한 8개로 1회 거절. 사용자의 전용 worktree 생성 및 다른 worktree 보존 요청을 따라 관리 스크립트의 `--allow-over-cap --reason`에 사유를 남겼다. 다른 worktree를 정리하지 않았다.

## 참고 자료 (2026-10-06 확인)

- [Python Protocol](https://docs.python.org/3/library/typing.html#typing.Protocol): 구체 실행기 대신 작은 동작 인터페이스를 받는 표준 방법. RobotLink와 stub 주입 경계에 적용.
- [RoCo 논문 초록](https://arxiv.org/abs/2307.04738), [공개 코드 README](https://github.com/MandiZhao/robot-collab): 로봇별 언어 판단과 실행 층을 분리하는 선행. 상세 알고리즘/성능 재현은 하지 않음.
- [Hi Robot 저자 설명, 2025](https://www.pi.website/research/hirobot): 상위 의미 판단/하위 실행 분리. 우리 고정 제어기 위의 연결 구조만 참고하며 VLA를 도입하지 않음.

## 초기 검증

`tests/test_pair_llm_s4_routing.py`: **7 passed in 0.47s**, exit 0 (초기 경계 시험). 후속 요청/응답 보존·이미지 해시·호출/토큰/시간·429 정지 시험을 같은 PR에 추가한다.
새 실험·훈련·평가 결과가 없으므로 TensorBoard snapshot을 만들지 않는다.
