# #299c 독립 검토의 검증 기록

대상 분류기는 `f32d5fd9afc54ca57ed49860843f54d6b5ca174d`, 등록 러너는
`4c6b439f3f7c9a147c901f8b260a1e214d4eb396`이다.
[전체 리뷰](../../REVIEW_299c_astra.md)의 판정은 **BLOCK**이다.

관련 전체 **337 passed, 13 xfailed**. 새 xfail을 해제하면 **13 failed,
14 deselected**이며 전부 실제 AssertionError다. 기존 323개(10,000개 생성 검사 포함)와
새 정상 검사 14개는 통과했다. 검토 대상 소스는 검사 전후 같은 해시다.

- `recorder_audit.json`: 허용된 공개 acceptance 11건만 읽은 필드 감사.
  lag-on 10건은 historical PASS, lag-off sanity 1건은 historical FAIL이며,
  새 confirmatory 스키마에서는 필수 필드가 없어 11건 모두 INVALID다.
  수집기 파일이 #292와 바이트 동일하고 기록된 fingerprint와 일치함을 확인했다.
  입력 36파일의 검사 전후 SHA-256도 보존했다.
- `audit_recorder.py`: 같은 공개 경로만 읽는 재현 도구. 실행기 import/실행,
  원본 수정, coverage/해시 필드 보충을 하지 않는다. 새 출력 파일을 지정한다.
- `related_tests.txt`: 기존 관련 8파일과 새 리뷰 테스트의 pytest 결과.
- `counterexamples_unmasked.txt`: 새 xfail만 해제한 실제 assertion 실패 기록.
- `provenance.json`: 정확한 명령·종료 코드·Python·부하·소스 해시 및 전후 동일성.

새 테스트는 `tests/test_classify_review_299c.py`다. 합성 JSON은 첫 리뷰의 fixture로
구성하며 실제 로봇 성공·진행 중 코호트 결과가 아니다. 7개 false-PASS 반례는
모순된 기록이 처음 저장될 때 해시를 계산한다. 해시 저장 뒤 손상을 숨겼다는 주장은 아니다.
나머지 xfail은 HOST_ERROR 등록 규칙 불일치 2개와 recorder 필드 부재 4개다.

진행 중인 confirmatory raw를 열거나 검색하지 않았다. 물리·SIM step·렌더·모델 호출,
등록/봉인 수정, Drive 작업, TensorBoard 재변환, 병합도 하지 않았다.
새 시험은 최신 main의 #328 오프라인 잠금 선택 규칙에 따라 단일 스레드로 실행하며
다른 작업의 잠금은 그대로 둔다. 이 기록은 원본 raw의 원격 백업을 대신하지 않는다.
