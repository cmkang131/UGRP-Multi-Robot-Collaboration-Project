# #371 v100 판단 층 구현 기록 (2026-10-05)

범위: 가짜 응답·기록 재생·단위 시험만. 실제 LLM 호출, 물리·렌더링 실행, 병합은 하지 않는다.
이 기록은 새 운반 실험이나 확증 결과가 아니다. TensorBoard에 변환할 새 실험 결과가 없다.

## 1. 재기반

- 원래 머리: `11ee964b3db8a5257987b0c477e927e8888b5aac`.
- fetch 후 #363 머리: `14ba8b5e0b8e58fc6bc9d4b97c5efb337a0c76db`.
- `scripts/run_ci_tests.py`의 추가 항목 충돌은 #363 시험 목록과 #371 패턴을 모두 보존했다.
  자동 병합된 workflow 시험의 예상 등록 수는 양쪽 추가를 합쳐 49 → 50으로 고쳤다.
- main과 열린 PR 11개를 조회했다. `RUNNABLE_ID`만으로는 분리된 등록 파일의 번호가 빠져서
  `configs/`의 ID·workflow 버전도 대조했다. 상세 SHA는 `implementation_20261005_scan.json`.
  최대 번호는 #376의 보정 경로 v101(1.0.0), 최대 workflow 버전은 #371의 3.12.0이다.
  이미 예약된 `zone-pair-llm-v100` / `3.12.0`과 충돌하는 다른 등록은 없고 v100 실행 기록도 없으므로 유지한다.
  v97·v99 은퇴 등록 파일은 바이트 그대로 보존한다.
- 시험 명령은 `nice -n 10 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest ...`를
  한 번에 한 묶음 사용한다. 이 실행 환경은 `setpriority: Operation not permitted`를 출력했다.
  우선순위가 10으로 변경됐다고 주장하지 않는다.
- 첫 넓은 묶음은 호스트 부하 평균 144에서 685.49초 동안 **170 passed**까지 진행한 뒤
  내가 중단했다(exit 2). 전체 통과로 세지 않는다. 이후 단계별 관련 시험으로 범위를 좁힌다.
- workflow 전체 묶음에서도 환경 제약을 확인했다. `test_parent_exit_cleans_background_child`의
  `ps` 실행이 `PermissionError`로 거절됐다. 이 묶음은 **1 failed, 39 passed, 280 subtests passed**에서
  중단했다. 제품 코드나 시험을 우회하도록 바꾸지 않았으며, 프로세스 정리 확인은 이 환경에서 미검증이다.

## 참고 자료 (이번 구현에서 확인한 범위)

- 고전: Sha, *Using simplicity to control complexity*, IEEE Software 18(4), 2001,
  [저자 소속 기관 서지](https://experts.illinois.edu/en/publications/using-simplicity-to-control-complexity/).
  서지 확인, 본문 **U(미확인)**. 단순 제어기가 복잡한 판단 층의 허용 범위를 지키는 구조를 참고한다.
- 고전 구조: [CMU SEI의 Simplex 설명](https://insights.sei.cmu.edu/history-of-innovation/setting-a-foundation-for-software-architecture/).
  설명 확인. 판단 층과 제어기의 책임 분리만 참고하며, 우리 제어기가 형식 검증됐다는 뜻은 아니다.
- 최신: Shi 외, *Hi Robot*, 2025,
  [논문 HTML](https://arxiv.org/html/2502.19417v1). 초록·계층 구조 설명 확인.
  상위 언어 판단과 하위 동작을 분리한다는 구조만 참고한다. 우리 10초 창·상한 수치의 근거로 쓰지 않는다.
- 다중 로봇: Mandi·Jain·Song, *RoCo*,
  [저자 논문 초록](https://arxiv.org/abs/2307.04738). 서지·초록 확인, 본문 **U**.
  대화와 자기 행동 계획의 분리를 참고하되 상대 추정치를 자기 추정기에 합치지 않는다.
- 적용하는 구체적 계약: 설계 노트 v3.1(e1–e9, 12절), #363 코멘트
  [5980026688](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5980026688),
  [5982047194](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5982047194),
  [5982637588](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5982637588),
  [5983174345](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5983174345),
  [5983763178](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/363#issuecomment-5983763178).
  전부 직접 읽음. 뒤 코멘트와 현재 코드가 앞 제안을 대체한 부분은 별도로 명시한다.
- 재기반 최종 관련 검사: workflow 등록·읽기 전용 계획 2개 + `test_ci_fast_path.py` + 은퇴 번들 바이트 시험,
  **13 passed, 280 subtests passed**(10.61초, exit 0). 위 두 중단 묶음과 구분한다.
