**봉인 — 독립 검토 필요.** b-v6h1의 실행 소스와 분석 소스를 따로 고정했습니다. 코호트는 결과를 보지 않은 채 이미 기록됐으며, 이번 봉인은 **기록 후 블라인드 분석 봉인**입니다. 실행 전에 봉인한 등록으로 소급하지 않습니다. 이 PR을 병합하지 않습니다.

- EXECUTION: `4c6b439f3f7c9a147c901f8b260a1e214d4eb396`의 274파일(EXTRA 6개 포함), Git blob SHA + SHA-256. `git show`로 재계산하며 재실행은 이 source checkout이 필요합니다.
- ANALYSIS: #299 최종 classifier/recorder·blinded-manifest adapter/정의와 분석 gate·의존성을 봉인 커밋에 별도로 고정합니다. 최종 분류기 바이트는 `1f0e4eb5`와 같습니다.
- `CURRENT_REVISION=v6h`, v83 / workflow 2.16.0 유지. JSON은 state=sealed이며 새 실행 권한은 없습니다.
- seed 941의 60곳에서 48/60 관측 기준, seed 943의 첫 12곳 민감도 분리, 전체 안전·B 판정 유지. HOST_ERROR/ENOSPC/주 시드 누락/INVALID는 UNCLASSIFIED이고 분모를 줄이지 않습니다.

72개 builder cases는 registration_run_id만 제외하면 커밋된 plan의 literal 배열과 바이트 단위로 같습니다(양쪽 SHA-256 `f476c3d3…`). 원래 chain_stop_leg의 키 순서 차이만 metadata builder에서 맞췄고 제어기·case 값은 바꾸지 않았습니다.

실행은 봉인 전 source 4c6b439f의 동일 worker를 얇은 driver가 unsealed_stage_probe 경로로 호출했다고 커밋 metadata에 기록돼 있습니다. RUN_MANIFEST SHA-256 `99723de3…`, plan `d627f9cd…`, cases.jsonl `8e7837cb…`, driver `7a35229e…`의 전체 값과 검증 범위를 prereg/두 문서에 공개했습니다. 뒤 두 해시는 metadata 진술이며 raw에서 독립 재계산하지 않았습니다. 블라인드 raw의 목록·내용과 outcome은 열지 않았습니다. ICH E9(R1)/CONSORT의 분석계획 고정·변경 공개 원칙을 참고하되 실행 전 등록으로 소급하는 근거로 사용하지 않습니다.

main은 `f5cd3a2b`를 병합했습니다. 명시된 4파일 외에 이후 main의 vision_loc_protocol.py(응답 seq 검증)와 workflow_manager.py(실행 전 admission)가 추가됐음을 공개합니다. 재개 결정 A(1)/B에 따라 main 바이트를 반영했고, 원본 execution pin은 계속 4c6b439f를 검증합니다. 제어기·등록 metadata·분석 작업 트리의 차이는 notes의 파일별 해시로 구분합니다.

검증의 최종 수치와 봉인 SHA는 검증 완료 뒤 아래에 기재합니다. 물리·렌더·모델 호출·개봉은 하지 않았습니다. 새 실험 결과가 없어 TensorBoard 재변환은 없고 raw 로컬 보관은 원격 백업이 아닙니다. `.github/workflows`의 main 대비 변경은 없습니다.

Refs #216, #285, #292, #299.
