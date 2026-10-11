# #425에 #416 main 반영

- #416 `6af2afa4` 병합; S4 고유 소비자 432개를 v191 / 7.84.0에 봉인.
- 공통 기본 off 유지, S3/S4 실행 구성은 `min_command_contract=on_v1`.
- 병합 전 `69147ab2`와 700개 호출·68단계 비교: 차이0, 명령3,190개 바이트 동일.
- v189/v190 원본 등록 바이트 보존; 각각 432/432·431/431 소스 해시 일치.
- 관련 3파일 44/44 통과; 시험·원본·SHA256는 `summary.json`, 최종 CI 영수증은 `outputs/pr425-main-sync/contract-on-v1/ci-summary.json`.
- 합성 오프라인 검증이며 물리·모델 실행0; PR 병합 없음.
- 방법: [Python 명시적 키워드](https://docs.python.org/3/tutorial/controlflow.html#keyword-arguments), [Git show](https://git-scm.com/docs/git-show), [Git diff](https://git-scm.com/docs/git-diff).
