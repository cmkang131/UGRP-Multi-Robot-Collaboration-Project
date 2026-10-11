# CI 번들 재등록

- #416: v152 기록·비교 파일은 원본 바이트 보존; v188 / 7.81.0으로 현재 소스를 별도 등록.
- v152의 379개 실행 소스 해시는 원래 SHA `981baa95` / `a6ff738f`에서 모두 일치.
- 현재 변경 6개 소비자를 새 seal에 고정; 기존 PF 선택·제어 옵션 유지, 실행 결과 승계 없음.
- 열린 PR 전체 번호 검사: v185 E2E, v186 연속 운반, v187 OPEN ACK 사용 중.
- 연구 방법: [Git show](https://git-scm.com/docs/git-show), [Git archive](https://git-scm.com/docs/git-archive); 현재 checkout 대신 원래 커밋의 blob/트리 검증.
- 시뮬레이션·모델 호출 0회; 시험과 CI 결과는 `summary.json`.
