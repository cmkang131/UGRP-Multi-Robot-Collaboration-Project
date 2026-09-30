# 블라인드 실행의 메타데이터 전용 fixture

`origin/claude/v6h1-confirm-run`의 커밋
`e78ef70fb5004fed1dfef1866aaf99bbf0bdda41`에서 아래 두 blob만 바이트 그대로 복사했다.
원 경로는 `experiments/2026-10-01-v6h1-confirm-blinded/`다.

| 파일 | SHA-256 |
|---|---|
| RUN_MANIFEST.json | `99723de36d20a55f348ea5b25ca203cf1db910dd9a620d3a8c4a17f27407f210` |
| plan.json | `d627f9cda827d07bab5b86c04f9e45ffceb474e97a8dda566c4956372d5fb026` |

결과·trace·명령 본문은 포함하지 않는다. 메타데이터 안의 raw 경로는 문자열로만
보존하며 테스트는 따라가지 않는다. 모든 per-case 기록·명령 본문은 테스트가
임시 디렉터리에 새로 만드는 합성 자료다. 테스트용 manifest 사본에서는 그 합성
commands/cases 파일의 해시만 교체하고, 원 fixture와 계획은 수정하지 않는다.
72개 합성 PASS는 실제 확증 결과가 아니다.

커밋된 schema는 `v6h1-confirm-blinded.manifest.v1`이다. 로컬 raw manifest의
`run.v1` 형식은 조회하지 않았으며 이 fixture로 그 형식까지 검증했다고 주장하지 않는다.
