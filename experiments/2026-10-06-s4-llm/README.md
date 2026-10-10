# S4 LLM 연결

## 2026-10-10 s4grip 저장 영상 감사

[자기 RGB·접촉 라벨 오프라인 감사](s4grip/README.md): 물리·렌더·모델0, 현재 S4 LLM 응답 부재로 정확도 미측정. 집기184프레임(고유92), 영상 있는 이탈0; 기존 log-only CV는 별도 진단으로 구분한다.

## 2026-10-10 s4live4 오프라인 준비

[빔 LLM GO/ACK·이탈 정지·다음 네 조건 묶음](s4live4/README.md)을 준비했다. 기본 off, 물리/실제 모델 호출0, S3 확정 SHA 대기이며 PR #425 draft 유지.

## 2026-10-10 s4live1 재개

[실제 모델·Oracle x86 네 조건 단계 배관 확인](s4live1/README.md)에서 네 조건 각90 SIM초를 완료했다. 조건당 실제 모델7호출, claim→출발→r3 약1m 운반 명령 연결을 확인했다. research_result=false이며 배송/E2E 성공은 아니다. 호스트 중단4시도와 재실행을 별도 보존했다. 기존 오프라인 기록은 아래에 보존한다. Mac 물리 금지, 네 조건 동시 묶음, 병합은 감독.

## 2026-10-06 오프라인 사전 구현 이력

**현재: 오프라인 사전 구현·시험 완료, DRAFT 유지·병합 금지.**
사용자가 중단 원인을 확인하고 재개를 지시하여, 미전송 검사와 오류 원장 저장을 고쳤다.
같은 세 시험 파일을 `--maxfail` 없이 실행한 최종 결과는 **45 passed in 1.38s**다.
[재개·검증·S3 연결 기록](RESUME_RECORD.md)을 따른다. [STOP_RECORD](STOP_RECORD.md)는 재개 전 이력으로 보존한다.
실제 모델·물리 실행과 S4 졸업은 미확인이다.

- 기준 main: `da92d91dbf4af193d3aa3559de9efe55653ec5c0`, #371 병합 포함.
- 계획: [S4 행](../2026-10-05-scenario-e2e-gap/README.md), DEV `dev_s1lite`만.
- S3: [DRAFT #394](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/394), 읽은 SHA `e4b72aaffb0d756560397b7f0a30995da12da89f`의 OwnLink API에 S4의 `S3Link` 어댑터를 맞췄다. S3 자동 claim을 끄는 연결 API는 아직 없어 실제 호스트 인계는 미완료다. 다른 브랜치 수정 없음.
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

`tests/test_pair_llm_s4_routing.py`: **7 passed in 0.47s**, exit 0 (초기 경계 시험). 후속 요청/응답 보존·이미지 해시·호출/토큰/시간·429 정지와 S3 어댑터까지 포함한 최종 검증은 RESUME_RECORD를 따른다.
새 실험·훈련·평가 결과가 없으므로 TensorBoard snapshot을 만들지 않는다.
