# PR #299 — 별도 블라인드 드라이버 manifest 어댑터

기준 후보 `d434fba95364bcf4a994ccf01943301c23989a7e`에서 추가한 D1 입력 어댑터다.
표준 러너와 per-case 판정 함수는 유지하고, 커밋된 별도 run manifest/plan의
source·driver·plan·명령 해시와 72개 case 설정을 연결한다.
새 옵션·필드 대응·미봉인 입장 상태는 [CLASSIFY_NOTES](../CLASSIFY_NOTES.md)를 따른다.

## 자료 경계

- `e78ef70fb5004fed1dfef1866aaf99bbf0bdda41`의 메타데이터 두 파일만 fixture로 복사했다.
  파일 바이트와 원 Git blob이 같고, 실제 schema `manifest.v1`/`plan.v1`을 확인했다.
- 새 per-case 기록과 commands 본문은 모두 임시 디렉터리에서 합성했다.
  72개 합성 성공은 실제 실행 결과가 아니다.
- 블라인드 raw 경로는 열거·조회하지 않았다. manifest에 기록된 절대 경로를 따라가지 않는다.
- 실제 source `4c6b439f…`의 worker 형식은 공개 golden 계약과 같다.
  driver 본문이나 블라인드 실행 내용을 새로 감사했다는 뜻은 아니다.
- 미봉인 `unsealed_stage_probe`를 그대로 표시한다. 판정기 봉인과 실행 사전 등록은
  별개이며, 해당 입력만으로 A/B 확증 입장 자격을 만들지 않는다.

## 검증

| 검사 | 확인한 결과 |
|---|---|
| 전체 관련 오프라인 14파일 | **544 passed**, 실패/skip/xfail 0; 10,000 생성 사례 포함 |
| 새 입력·기존 recorder·4차 리뷰 묶음 | 135 passed, 실패/skip/xfail 0 |
| 공개 acceptance | 11/11, lag-on 10 PASS_CLEAN + lag-off 1 FAIL |
| acceptance 전체 출력 | 이전 후보의 검증 JSON과 동일; 전체 raw/projection 판정 동일 |
| 공개 원본 | 36개 입력 해시 불변 |
| 공개 완료 코호트 | 16코호트 308/308 판정 동일, cA/cB 각 24/24 |
| 부분 tX1 | 별도 12 PASS + 2 HOST 미분류 유지 |
| 과거 대조 입력 재검사 | 697개 입력·소스 해시 동일, 사례/코호트 판정 변화 0 |
| 보존 | workflow·worker·거리 계산·배치·공개 fixture 17파일은 기준 후보와 동일; 메타데이터 2파일은 원 커밋과 동일 |

새 검사는 source/driver/plan/commands의 누락·변조, metadata 목록·경로·시드 모순,
정확한 plan/case 연결, 72슬롯/60곳 분모 유지, CLI 경로, HOST 미분류와 하드 위반
우선순위를 검사한다. 기존 start·거리·시각·handover·PF·coverage·receipt 검사를
새 어댑터에서도 유지한다. 새 테스트 파일은 `scripts/run_ci_tests.py`의 일반
오프라인 목록에 추가했으며 `.github/workflows`는 수정하지 않았다.

초기 새 테스트는 43 passed / 2 failed였다. handover 실패를 INVALID로 기대한
오류와 끝점 선택 뒤의 PF 샘플을 손상시킨 오류를 고쳤다. 구현 판정 규칙은 바꾸지
않았고, 이후 묶음 검사에서 모두 통과했다. 자세한 개발 기록은
`development_notes.json`에 남겼다.

## 재현과 보존

정확한 명령·종료 코드·검사 소스 해시는 `provenance.json`, 전체 관련 테스트는
`related_tests.txt`를 따른다. 호스트 잠금 없이 기존 Mac 환경에서 직접 오프라인
pytest/분석기를 실행했다. 실행 시간은 성능 비교 자료가 아니다.

전체 17코호트 재분류 JSON과 697개 입력 해시 목록은
`/Users/changmin/projects/ugrp/outputs/v6h-classifier-run-manifest-20261001/`에 보존한다.
이 디렉터리에는 작은 로그·집계·해시만 복사했으며 `artifact_index.json`으로 연결한다.
로컬 raw의 원격 백업을 주장하지 않는다.

물리·렌더·모델 실행, 실제 분류기/등록 봉인, 블라인드 결과 판정, Drive 작업,
PR 병합은 하지 않았다. 새 실험 결과가 없어 기존 TensorBoard snapshot은 보존하고
재변환·재개방하지 않았다. 커밋 이후 정상 PR CI와 독립 검토는 로컬 검사와 별도다.
