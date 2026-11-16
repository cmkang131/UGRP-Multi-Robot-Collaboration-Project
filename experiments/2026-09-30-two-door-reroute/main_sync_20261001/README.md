# PR #330 최신 main 충돌 해소

2026-10-01 KST. 검토 I 수정 완료 HEAD `9363997ca32c26bf6e2e0196f8b5a126c5328104`에
#314 병합을 포함한 main `0d45ef8c2afb55e3e4ac9f8a61ac519f41e92e4f`를 통합했다.
T10a #310, T10b #331, T04 #335, T06 #336, CI apt cache #340도 포함된다.

**API 조정은 없다.** T09b 제어 코드·기능 테스트·기존 검증기는 검토 완료 HEAD와
바이트가 같다. 충돌 두 곳은 다음과 같이 해결했다.

- `tests/test_review_e2e_batch_i.py`: main의 I-335-1 팔 이동 반례와 #330의
  I-330-1 촬영 지연 반례를 모두 유지했다. 두 함수 본문·assertion과 기존 probe
  함수의 AST 일치를 확인했다. 두 반례 모두 xfail 없이 현재 소스를 검사한다.
- `scripts/run_ci_tests.py`: main의 테스트 목록을 유지하고 해당 주석에 두 반례를
  함께 표시했다. 테스트 파일은 한 번만 등록된다.

main의 harness/sim/scripts/configs/maps/workflow 973개 파일 중 972개가 바이트 동일하며,
나머지 하나는 위 CI 목록의 주석뿐이다. T09b 파일은 main에 없던 추가 파일이다.
`.github/workflows` 전체와 필수 source-pinning 테스트 두 파일은 main과 동일하다.

## 오프라인 검증

기존 Python 3.12 환경과 물리·모델 import/네트워크를 차단하는 검증기를 재사용했다.
host lock 없이 **794 passed, 280 subtests passed**, 실패·오류·skip·xfail 0을 확인했다.

- 지정 묶음 519개: T09b 223, T09a 76, Batch I 두 반례 2,
  passage 44, 모델 기하 6, pair status 16, 등록 소스 22, source pinning 34,
  메시지 protocol 86, CI 정책 10. subtest 280개는 별도다.
- 관련 묶음 275개: T10a 55, T10b 78, team jobs 41, 기존 두 문·지도 경로 11,
  CI 분할 66, CI 무잠금 24.
- v6e 봉인 소스 85/85 해시 일치, 검사 중 보호 파일과 T09b 소스 불변,
  frozen fixture 3개 존재, main 대비 공백 검사 통과.
- 검증 뒤 fetch에서도 main SHA가 동일했다. 동작 코드는 바뀌지 않아 과거 제거
  변이 검사를 반복하지 않았으며, 과거 결과를 이번 검사 수에 합산하지 않았다.

명령·소스 및 raw 해시는 [verification.json](verification.json)에 있다.
raw 로그/JUnit/manifest는 `/Users/changmin/projects/ugrp/outputs/2026-10-01-t09b-main-sync-01/`에
로컬 보관한다. `/private/tmp` 추출 디렉터리는 만들지 않았다.

물리·렌더·모델 실행은 0회다. 새 실험·학습·평가 코호트가 없어 TensorBoard 변환은 없다.
실제 Observer/Navigation 연결과 물리 인수는 검증하지 않았다. 일반 push로 CI를 요청하며
PR #330은 병합하지 않는다.
