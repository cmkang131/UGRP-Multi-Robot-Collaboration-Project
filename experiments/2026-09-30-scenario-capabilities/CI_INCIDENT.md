# P09 자동 CI 범위 이탈 및 종료

사용자는 물리/시뮬레이션/렌더와 모든 모델 호출을 금지했다. 로컬 감사는 이 경계를 지켰지만, **push/PR 전에 저장소 자동 CI의 ACT 모델 시험을 차단하지 못했다.** 따라서 이 작업 전체를 모델 실행0이라고 보고하면 안 된다.

- 정적 감사/검사 커밋: `9040e17bbb7200e34b1c77fe255fb91c7479611b`; 로컬 정적 pytest124 통과, 금지 import0, 렌더/물리/모델0, 공용 잠금 반환. 이 증거는 그대로 유효하다.
- [Draft PR #302](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/302), main 대상, 병합하지 않았다.
- 자동 CI [push 36707631477](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36707631477)와 [pull_request 36707656445](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36707656445)를 확인한 뒤 각각 cancel, 이어 force-cancel했다. 최종 둘 다 `completed/cancelled`다.
- 명시적인 `ubuntu-simulation-runtime`, `ubuntu-simulation-scenarios`, `multi-object-scenes` job은 queued 상태에서 취소 요청했다. 자동 CI 전체를 정적 전용으로 검사한 것은 아니다.
- `.github/workflows/tests.yml:66–86`의 `reference-act-smoke`는 ACT CPU 설치 후 실제 RGB inference/backward/checkpoint 시험을 한다. 취소 처리 중 그 시험 단계가 시작됐고 최종 cancelled다. 구체적인 모델 호출 수/수행 완료 범위는 미확인으로 남긴다. 외부 LLM 호출이나 새 연구 성공의 증거로 집계하지 않는다.
- [최종 CI 상태와 step 시각](data/ci_cancellation.json). 전체 job/step 응답 원본은 그 JSON의 primary `outputs/` 경로와 해시에 남겼다. 별도 원격 백업 완료로 주장하지 않는다.
- 후속 기록 커밋은 `[skip ci]`로 자동 workflow를 건너뛴다. 공용 workflow/다른 작업/기존 시나리오/controller는 수정하지 않고, CI 재실행·병합도 하지 않는다.

이 기록은 요청 범위 이탈을 숨기지 않고 남기는 것이며 사후 승인이 아니다. C6/C7의 물리/학생 성공은 여전히 전부 미측정이다.
