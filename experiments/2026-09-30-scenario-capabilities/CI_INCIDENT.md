# P09 CI 취소 이력과 지침 정정

## 현재 지침 — 2026-09-30 B3 정정

**정상 GitHub CI는 허용되며 필수 검증이다. workflow를 취소하지 않는다. 커밋 지시어로 CI를 건너뛰지 않는다.** 로컬 물리/렌더/모델 실행 금지를 원격 CI에도 적용해 당시 ACT 시험을 범위 이탈로 해석한 것은 잘못됐다. 이후 정정 커밋도 정상 CI를 끝까지 확인하며, 로컬 정적 검사로 최신 HEAD의 CI를 대체하지 않는다.

로컬 감사의 실행 경계는 유지한다. 원격 CI에는 ACT 추론/학습과 시뮬레이션 검사가 포함되므로 작업 전체를 모델 실행0으로 보고하지 않는다. CI 통과는 C6/C7 학생·물리 성공 승인이 아니다.

## 과거 실행 사실 — 원본 증거 보존

- 정적 감사/검사 커밋: `9040e17bbb7200e34b1c77fe255fb91c7479611b`; 로컬 정적 pytest124 통과, 금지 import0, 렌더/물리/모델0, 공용 잠금 반환. 이 증거는 그대로 유효하다.
- [Draft PR #302](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/302), main 대상, 병합하지 않았다.
- 자동 CI [push 36707631477](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36707631477)와 [pull_request 36707656445](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36707656445)를 확인한 뒤 각각 cancel, 이어 force-cancel했다. 최종 둘 다 `completed/cancelled`다.
- 명시적인 `ubuntu-simulation-runtime`, `ubuntu-simulation-scenarios`, `multi-object-scenes` job은 queued 상태에서 취소 요청했다. 자동 CI 전체를 정적 전용으로 검사한 것은 아니다.
- `.github/workflows/tests.yml:66–86`의 `reference-act-smoke`는 ACT CPU 설치 후 실제 RGB inference/backward/checkpoint 시험을 한다. 취소 처리 중 그 시험 단계가 시작됐고 최종 cancelled다. 구체적인 모델 호출 수/수행 완료 범위는 미확인으로 남긴다. 외부 LLM 호출이나 새 연구 성공의 증거로 집계하지 않는다.
- [최종 CI 상태와 step 시각](data/ci_cancellation.json). 전체 job/step 응답 원본은 그 JSON의 primary `outputs/` 경로와 해시에 남겼다. 별도 원격 백업 완료로 주장하지 않는다.
- 과거 기록 커밋 `dec67997815e4cdc564a9848ed6020eede45cbfa`에는 `[skip ci]`가 사용됐고 자동 workflow가 없었다. 이 사실은 보존하며 후속 작업 지침으로 사용하지 않는다.
- `bd95530a2d5a8b8467620809749273068a7ed55d`에서 정상 CI를 재시작했다. 초기 취소 실행과 재시작 실행, 이후 정정 HEAD의 검사 결과를 각각 구분한다.

취소 사실·시각·원본 JSON/해시는 그대로다. 이 정정은 과거 cancelled 실행을 성공으로 바꾸지 않는다. 최신 수정과 검증 범위는 [REVIEW_FIXES.md](REVIEW_FIXES.md)에 기록한다. C6/C7의 물리/학생 성공은 여전히 전부 미측정이다.
