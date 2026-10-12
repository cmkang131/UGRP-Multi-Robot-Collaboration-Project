# #425 후속 v193 퇴역

- v193 등록은 `cadf4da8`, #416 병합은 `eebb2490`; 원래 봉인 런타임 소스 433개의 해시와 보존 대상 6파일의 바이트가 두 SHA에서 동일하다.
- #425 main `4d0b8304`에서는 계약·실행기·LLM driver·S3 host 4파일이 변경됐다. 기존 v193 ID가 v195 번들을 생성하므로 현재 workflow 등록을 제거하고 대체를 `zone-s3-recovery-v195` / 7.88.0으로 기록했다.
- `retired-bundle/v193/`에 원래 계약·실행기·workflow·등록·봉인·퇴역 원장 6파일을 보존했다. #425 요약의 앞선 보존 범위를 기록 3파일로 명시했다.
- 지정 시험 2파일 39/39 통과. 시뮬레이션·렌더·모델 호출 0회. 시험 원본 위치·sha256·검증 범위는 [summary.json](summary.json)에 기록했다.

## 참고 자료

[Git show 공식 문서](https://git-scm.com/docs/git-show)의 blob 원문 조회를 사용해 원래 커밋의 바이트와 sha256을 대조했다. [프로젝트 실행 버전 관리](../../docs/execution_versioning.md)의 원본 봉인 보존 규칙과 [v189·v191 퇴역 목록](../2026-10-11-ci-bundle-reregistration/retired-bundles.json)의 기존 구조를 그대로 재사용한다. 제어 알고리즘 변경이나 새 실행 결과의 승계는 없다.

Refs #425.
