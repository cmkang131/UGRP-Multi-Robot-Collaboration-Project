# b-v6h1 분석 봉인 v2

리뷰 `77b6b94c`의 P1 대응이다. 원시 자료와 실제 inventory는 개봉하지 않았다.

- **지적 → 수정:** 분석 시작 전 result/trace 변조가 통과하던 경로에 acquisition inventory의 SHA-256/schema/raw 경로/파일 수/총 바이트 검사를 추가했다. `EvidenceReader`를 통해 모든 소비 입력을 목록·해시와 대조하고 기존 분석 도중 변경 검사도 유지한다. 누락·미등록·불일치는 `INVALID / NOT_ANALYSED`와 이유만 남기며 gate verdict·부분 classifier 보고서를 저장하지 않는다.
- **봉인:** 새 `prereg_v6h.json`의 EXECUTION 274개는 기존 `4c6b439f` pin 집합과 동일하다. ANALYSIS 293개는 이 파일을 처음 추가한 커밋의 Git blob/SHA-256으로 검증한다. 기존 루트 `prereg_v6h.json`과 `analysis/seal/` 바이트는 보존했다.
- **기록 시점:** inventory는 기록 후 개봉 전에 조정자가 만들었다. count/bytes 일치와 mtime ≤ driver end +0.11초는 보조 근거이지 기록 당시 바이트의 증명이 아니다. generator의 late counter는 +1.0초 기준이다. 상세한 진술·한계는 `disclosure.json`과 새 봉인의 notes에 있다.
- **안전한 출처:** `ACQUISITION_INVENTORY.json`은 목록 본문이 아닌 커밋된 pointer다. pointer·driver·build_plan·generator는 `0b77ae4b`와 바이트 동일하다. 이 폴더의 원본 generator/driver는 출처 보존용이며 import/실행하지 않는다.
- **검증:** `validation.json`에 오프라인 회귀와 변경 전후 검증, `mutation_results.json`에 inventory admission 제거 시 두 리뷰 반례의 실제 AssertionError를 기록한다. `tests/test_review_seal_v6h1.py`는 `77b6b94c`에서 가져왔고 기존 6개 역사 감사는 그대로, 2개 strict xfail은 실제 v2 진입점과 generator 형식의 합성 inventory를 쓰는 필수 검사로 전환했다. 정상 자료의 PASS/FAIL 도달을 먼저 확인하므로 준비 오류를 성공으로 보지 않는다.
- **미완료:** 독립 재검토와 개봉 승인은 남았다. 개봉 명령은 상위 `REGISTRATION_PLAN.md`에만 적었으며 실행하지 않았다. 물리·렌더·모델 호출·TensorBoard 결과 변환·PR 병합은 하지 않았다.

재현(원시 자료 접근 없음):

```sh
python -m experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h --verify-seal --seal-revision v2 --seal-commit "$V6H_SEAL_V2_COMMIT"
python -m pytest -q -p tests.pose_provider_no_physics -p tests.v6h_seal_offline_guard tests/test_review_seal_v6h1.py tests/test_v6h_acquisition_reader.py
python experiments/2026-09-30-pair-v6h-carry/analysis/seal_v2/mutation_check.py --output /absolute/new/synthetic-validation-mutation
```

mutation은 모듈을 메모리에서만 바꾸고 테스트 2개의 exit=1, 실패 이유, 소스 파일 불변을 확인한다. 임시 추출 디렉터리는 만들지 않는다. 리뷰 검사 자체의 임시 clone은 context manager 종료 시 삭제된다.
