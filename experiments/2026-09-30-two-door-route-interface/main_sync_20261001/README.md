# PR #314 최신 main 충돌 해소

2026-10-01 KST. 검토·수정 완료 HEAD `386afaee24a790f2ac33cb84d5bd0943cd299c02`에
main `f3fbbf9a08c0ba96b22858b573ab5d4da52e9011`을 merge했다.
T10a #310, T10b #331, T04 #335, T06 #336 및 CI apt cache #340이 포함된 기준이다.

충돌은 `experiments/2026-09-30-p08-stall-contract/README.md`의 CI 안내 문단 한 곳이었다.
main 원문으로 해결했다. **API 조정은 없다.** T09a 구현·검토된 기하 테스트와
`static_keepouts`, `zone_team_footprint`, `zone_team_footprint_v3`는 기존 HEAD와
바이트가 같다. main 코드·설정 위에 기존 T09a 소스와 테스트 두 파일만 추가된 상태다.
`.github/workflows` 전체와 지정 소스 고정 테스트 두 파일은 main과 바이트가 같다.

## 오프라인 검증

기존 Python 3.12 환경과 `../review_f314_1/verify.py`를 재사용했다.
이 검증기는 물리·렌더·모델 라이브러리 import 및 네트워크 접속을 차단한다.
host lock 없이 **364 passed, 280 subtests passed**, 실패·오류·skip 0을 확인했다.

| 검사 | 통과 |
|---|---:|
| T09a 두 문 경로 | 76 |
| 기존 passage / team jobs | 44 / 41 |
| keepout / 지도 고정·catalog·좁은 문 차단 시 넓은 문 경로 | 1 / 3 |
| `test_zone_pair_registered_source.py` | 22 |
| `test_zone_study_source_pinning.py` | 34 |
| CI 정책 | 10 |
| T10a 복도 계약 / T10b 복도 제어 | 55 / 78 |

v6e 봉인 소스 85/85 SHA-256 일치, 보호 파일 88개의 실행 전후 불변을 확인했다.
필수 frozen fixture 3개도 확인했다. main 대비 diff 공백 검사는 통과했다.
병합으로 들어온 main의 과거 실패 로그에 있는 후행 공백은 원본 그대로 보존했다.
T09a 코드·테스트를 바꾸지 않았으므로 기존 역할 제거 변이 검사는 반복하지 않았다.

명령·검사별 개수·소스 및 raw 해시는 [verification.json](verification.json)에 있다.
원본 로그/JUnit/검증 manifest는
`/Users/changmin/projects/ugrp/outputs/2026-10-01-t09a-main-sync-01/`에 로컬 보관한다.
검사 뒤 최신 fetch에서도 main SHA가 같음을 확인했다.

물리·렌더·모델 실행은 없으며 실제 문 통과나 E2E 인수 결과가 아니다.
새 실험 코호트가 없어 TensorBoard 변환은 하지 않았다. Drive 작업 및
`/private/tmp` 추출 디렉터리 생성도 없다. 정상 CI를 실행하는 일반 push 후
최종 SHA와 원격 상태는 PR 댓글에 남기며, PR은 draft 유지·병합하지 않는다.
