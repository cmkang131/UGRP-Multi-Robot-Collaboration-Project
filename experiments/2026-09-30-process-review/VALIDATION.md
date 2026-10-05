# 측정 산출물 검증

검증 대상은 `2026-09-30-process-review/`의 집계 도구·원자료·파생 표다. 제어기·물리·시뮬레이션·모델 호출을 실행하지 않는다.

```sh
python3 experiments/2026-09-30-process-review/verify.py
python3 scripts/run_ci_tests.py --shard-count 8 --list-shards
```

- 첫 명령: PR 전수·GitHub/git diff 합, 미병합 검열 처리, 독립 시각 계산 예제, CI attempt/job 시각, shard 중복·누락, 저장 데이터의 결정적 재계산, 문서 내부 링크·파일 예산·Python 문법을 검사한다.
- 두 번째 명령: 기존 CI 목록만 출력한다. 328개 파일이 8개 shard에 한 번씩 들어가며 테스트 실행·공용 잠금은 없다.
- 저장된 GitHub 상태는 수집 시각의 기록이다. 이 PR의 CI 결과를 뜻하지 않는다.
- manifest 메타데이터는 로컬 원본에서 읽고 SHA-256과 핵심 필드만 저장했다. private transcript는 본문 없이 합계·분포만 저장했다. 원본 로그·미디어·기존 snapshot을 변경하지 않았다.
- 최종 오프라인 검사 **6/6 통과**. [실행 로그](data/verification.txt). 분석기 두 개가 임시 디렉터리에 재생성한 모든 파생 파일이 저장본과 바이트 동일했다.
- 산출물은 총 5 MiB 미만, 각 파일 1 MiB 미만이다. 저장 원자료의 private transcript 부분은 집계 JSON 하나뿐이며 원문은 포함하지 않았다.
