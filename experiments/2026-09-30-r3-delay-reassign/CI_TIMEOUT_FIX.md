# T12 CI 시간 초과 후속 수정

기준 `330e650e6dc2959d33d917fec31f40a18acc7656`, 첫 정상 CI
[36744665856](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/actions/runs/36744665856).
30개 job이 성공했으나 shard 6은 10분 제한을 넘겨 취소됐고 필수 집계가 실패했다.
Ubuntu 시나리오 job도 실제 시나리오 실행 전 `Install Ubuntu rendering and recording tools`
단계에서 15분 제한을 넘겼다. 두 원인은 GitHub annotation으로 확인했다. 직접 취소하지 않았다.

T12의 역할 host fixture가 같은 고정 소스 해시를 host마다 반복 계산했다.
`tests/test_zone_pair_rendezvous_t07.py`에서 실제 `controller_source_record()`를 module fixture로
한 번 계산하고 매 host에는 깊은 복사본을 돌려주도록 했다. 각 테스트 뒤 원래 함수를 복원하므로
T07 기하/출처 검사와 두 pin 파일은 원래 구현으로 실행한다. 가짜 해시를 넣지 않았다.

5개 테스트 함수의 본문과 모든 매개변수/조건/assertion은 AST로 동일함을 확인했다.
45개 통합 사례를 그대로 유지했고 skip·삭제·workflow·shard 분할·시간 제한 변경은 없다.
제어기 전체 의존 소스 202개도 이전 검증본과 바이트가 같다. CI shard의 최종 통과 여부는
후속 정상 CI에서 별도로 확인하며 로컬 벽시계 시간을 성능 개선 근거로 사용하지 않는다.

- 핵심 6파일 **447 passed / 0 failed / 0 errors / 0 skipped**를 다시 확인했다.
- 변이 전과 원본 복구는 각각 **79 passed**다. 다섯 변이는 assertion 실패 18/32/1/12/6개로
  모두 검출됐고 errors/skipped는 0이다. 이전 통과 수에 반복 검사 수를 더하지 않는다.
- 기존 main 합성 463 + 280 subtests 기록은 [Batch F 수정 기록](REVIEW_FIXES.md)에 보존한다.
  이번 변경은 위 T12 fixture뿐이며 새 실험/학습/평가 cohort를 만들지 않았다.
- 정확한 명령·JUnit·해시·첫 CI 시간 초과 annotation은
  [ci_timeout_verification.json](ci_timeout_verification.json)에 연결했다.

로컬 host lock·물리·MuJoCo 렌더·외부 모델 호출은 0이다. 정상 push로 CI를 다시 실행한다.
DRAFT와 PR 미병합을 유지한다. 실제 hold·자기 RGB 인지·물리 집결은 여전히 미검증이다.
