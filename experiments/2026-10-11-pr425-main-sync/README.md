# PR425 main eebb2490 동기화

- #416 병합 main `eebb2490`을 현재 worktree에 반영; S3 전용 가드·공통 기본 off 유지.
- main v193 / 7.86.0 등록 3파일과 기존 퇴역 14파일·3항목은 원본 보존.
- PR433의 v194 / 7.87.0 확인 후 S4 소비자 구성을 **v195 / 7.88.0**으로 새로 등록(소스 434개).
- 미병합·미실행 v191은 `00418638` 원본 6파일·432개 소스 해시로 퇴역 보존.
- 지정한 오프라인 시험 3파일 **46/46 통과**(179.47초); main/병합 SHA·원본 해시는 `summary.json`.
- 시뮬레이션·모델 호출 0회; 과거 명령 동등성 비교는 재실행하지 않았고 `summary-v191.json`에 보존.
- 방법: [Git merge](https://git-scm.com/docs/git-merge), [Git show](https://git-scm.com/docs/git-show), [Git grep](https://git-scm.com/docs/git-grep).

## 이전 v191 라운드 기록

# #425에 #416 main 반영

- #416 `6af2afa4` 병합; S4 고유 소비자 432개를 v191 / 7.84.0에 봉인.
- 공통 기본 off 유지, S3/S4 실행 구성은 `min_command_contract=on_v1`.
- 병합 전 `69147ab2`와 700개 호출·68단계 비교: 차이0, 명령3,190개 바이트 동일.
- v189/v190 원본 등록 바이트 보존; 각각 432/432·431/431 소스 해시 일치.
- 관련 3파일 44/44 통과; 시험·원본·SHA256는 `summary.json`, 최종 CI 영수증은 `outputs/pr425-main-sync/contract-on-v1/ci-summary.json`.
- 합성 오프라인 검증이며 물리·모델 실행0; PR 병합 없음.
- 방법: [Python 명시적 키워드](https://docs.python.org/3/tutorial/controlflow.html#keyword-arguments), [Git show](https://git-scm.com/docs/git-show), [Git diff](https://git-scm.com/docs/git-diff).
