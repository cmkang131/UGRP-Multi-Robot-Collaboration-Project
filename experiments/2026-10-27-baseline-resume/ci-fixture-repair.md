# CI 테스트 fixture의 디스크 의존성

GitHub run40404092623/shard2에서1,695통과·4실패가 나왔습니다. LLM 모의 live 실행3건은 첫 요청 전 HOST_ERROR/원장 없음, Azure 수신1건은 ready JSON 없이 EOF였습니다. 실패한 생산 코드와 테스트 파일은 이 베이스라인 브랜치가 수정한 파일이 아니었습니다. 당시 runner의 free 바이트는 로그에 없어 정확한 잔량은 미확인입니다.

| 실패 경로 | 건수 | 분리한 원인과 재현 |
|---|---:|---|
| module 범위 clean LLM fixture |3|function 범위 no_disk_probe보다 먼저 실행되어 실제10GiB 검사를 받음. 디스크 검사에 실패를 주입한 동일 clean test가 수정 전 HOST_ERROR로 실패·2번 probe 호출됨|
| native archive child receiver fixture |1|실제25GiB+64MiB 임시 공간 검사를 받음. 별도 자식에서 free0을 모의하면 ready 이전 EOF와 같은 ARM projected free below25GiB 예외를 재현|

수정은 테스트2파일만입니다. clean fixture 자체의 제한된 MonkeyPatch.context에서 가짜 디스크 검사를 적용합니다. 수신 무결성 테스트의 자식 프로세스에는 기존25GiB 바닥+64MiB 임시 예약+payload에 맞는 가상 공간을 제공합니다. 원본 수신 프로토콜·파일/해시 보존 검사는 계속 실행하고, 부족한 공간을 거부하는 별도 테스트도 유지합니다. subprocess 실패 시 stderr가 보이도록 검증 메시지를 추가했습니다.

운영 실행기·디스크 보호 수치·사전등록·실제 C/S 입력/제어 코드는 이 수정의 범위가 아닙니다. 실제 GCP 실행은 source22fc786b5와 동결33/처치10으로 식별합니다.

표준 방법은 [pytest 공식 monkeypatch 문서](https://docs.pytest.org/en/stable/how-to/monkeypatch.html)의 제한된 context 사용법을 따랐습니다. 테스트 환경은 CONTRIBUTING.md의 .venv-test/requirements-test.txt를 사용했습니다.

수정 전 정상 여유 호스트에서는 관련55테스트가 통과했고, 낮은 공간을 주입한 clean test는 의도대로 기존 결함을 재현했습니다. 수정 후 수치와 CI 재검증은 결과 파일에 별도로 남깁니다. 원본 CI 로그·제어 재현·전후 테스트 영수증은 outputs/reports/2026-10-27-baseline-resume-evidence/CI-*에 보존합니다.

수정 후 관련55테스트가78.35초에 통과했고, 동일한 low-disk clean test도 성공(주입된 실제 공간 검사 호출0)했습니다. 운영 low-space 거부 검사는 기존 테스트에서 계속 통과했습니다. 전후 영수증은 ci-fixture-verification.json에 묶었습니다.
