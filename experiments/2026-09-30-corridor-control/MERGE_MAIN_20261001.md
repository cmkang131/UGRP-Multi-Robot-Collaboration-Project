# T10b — 최종 T10a main 통합 (2026-10-01)

검토된 #331 `25beb0694027b2d6d8db646a043de51fabc479dc`에 #310 병합 main
`f5cd3a2b7754236a7b416cca1e1f9fe76fe8dd14`를 `git merge --no-commit origin/main`으로
반영했다. GitHub의 충돌 표시는 있었지만 로컬 Git 병합에는 텍스트 충돌이 없었다.
아래 검사 통과 뒤 병합 커밋을 만들고 정상 push한다. **PR 자체는 병합하지 않는다.**

## API와 소스 보존

- 추가 API 수정 없음. 최종 T10a는 `UnsupportedCorridor`와 `require_door_runtime`을
  작은 `zone_corridor_admission`으로 옮기되 기존 계약 모듈에서도 그대로 노출한다.
  기존 T10b 호출부를 유지할 수 있다.
- T10a 계약·admission·관리 진입점·계약 테스트는 main과 바이트가 같다.
- T10b 제어·계획 모듈 두 개와 제어 테스트는 독립 검토된 `25beb069`와 바이트가 같다.
  제어 동작·지도·등록 번들·기존 실험 기록은 바꾸지 않았다.
- `.github/workflows`와 지정한 두 source-pinning 테스트는 main과 바이트가 같다.
  v6e 봉인 소스 85개는 검사 전후 등록 SHA-256과 일치한다.

## 오프라인 검증

기존 Python 3.12 환경과 `validate_offline.py`를 사용했다. 공용 잠금 없이 실행했으며
물리·모델 import와 네트워크를 차단했다. **295 passed**, 실패·오류·skip 0개다.

| 검사 | 통과 |
|---|---:|
| corridor control / contract | 78 / 55 |
| zone_pair_registered_source / zone_study_source_pinning | 22 / 34 |
| zone_pair_status / pair_passage_plan | 16 / 44 |
| zone_hard_routes / execution_dependency_contract | 11 / 35 |

제어·양보·heartbeat·대기 상한·전체 출구·정적 경로 거절 제거 변이 **6/6**을
행동 assertion 실패로 검출했다. setup/teardown 오류는 없고 원본 코드도 불변이다.
이 변이 실행의 통과 사례는 정상 검사 295개에 합산하지 않는다.

검토 브랜치 `e24cb9ce3c10236efe03a1b66c9ec7671ece71b9`의
`tests/test_review_e2e_batch_i.py`에는 #330·#335 반례 두 개만 있으며 #331 항목이 없다.
정확한 테스트 이름 선택에서는 **2 deselected, exit 5**다. 이를 통과로 세지 않고
검토 문서가 #331용으로 지정한 corridor 두 파일과 source-pinning 두 파일을 위에서 실행했다.
최초 넓은 `-k` 선택은 상위 디렉터리 이름까지 일치하여 무관한 두 반례를 잘못 골랐고,
검토 파일 복사 위치 때문에 archive 준비 오류 2개가 났다. 원문은 보존했으며
#331 제품 실패나 반례 검출로 세지 않는다. 임시 추출 폴더는 자동 삭제됐고 잔여 0개다.

명령·Python·소스/검사 파일 해시·JUnit·로그·변이 receipt는
primary `outputs/2026-10-01-t10b-main-integration/`에 로컬 보존한다.
[검증 요약과 원본 해시](validation/main-t10a-integration.json)를 함께 커밋한다.
raw 로컬 보관은 원격 백업이 아니다.

물리·렌더·실모델 실행은 0회다. 새 실험/평가 코호트가 없어 TensorBoard snapshot은
추가하지 않았다. 실제 RGB observer·actuator·실행 번들·물리 인수는 기존대로 남아 있다.
이 기록의 로컬 통과와 push 뒤 정상 GitHub CI 결과는 구분한다.
