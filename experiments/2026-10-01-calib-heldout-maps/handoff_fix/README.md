# PR #352 재검토 R3 문서 수정 (2026-10-02)

대상 `fa2119ca6926a66a317a455701cbc389d7d3fb58`, 독립 재검토
[`3a6070b3`의 R3 / P2](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/3a6070b3/experiments/2026-10-01-calib-heldout-maps/REVIEW_352b.md)에 대한 수정이다.

`PHYSICS_HANDOFF.md`의 잘못된 v88 직접 계획 안내를
`scripts.run_final_pair_heldout`으로 고치고, 두 지도 각각에 필요한 source SHA·seed·output을
모두 포함한 계획 명령을 추가했다. 실제 수집의 잠금 획득·세션·`sim_cli workflow run`
명령은 기존 바이트를 유지한다. 직접 계획은 `--execute` 없이 출력 생성도 하지 않는다.

리뷰어 `tests/test_review_352b.py`의 문서 반례 두 개와 workflow→가짜 backend 저장 검사
한 개를 이미 CI에 등록된 `tests/test_review_352.py`에 이식했다. strict xfail은 제거했다.
원래 리터럴 판정·저장 결과·해시 검사를 유지하며, 새 완전한 직접 계획 명령도 문서에서
추출해 구문·parser·v90 계획을 확인한다. 기존 shell 검사도 실제 v90 parser를 사용한다.

## 이번 검증

- 수정 전: R3 반례 **2 failed**를 실제로 재현했다([before.log](before.log)).
- 수정 후 리뷰 회귀: **25 passed**([review.log](review.log), [JUnit](review.xml)).
- held-out·v88·clearance 관련 회귀, CI 분할, 읽기 전용 workflow 계획: **182 passed**
  ([related.log](related.log), [JUnit](related.xml)).
- 최종 중복 없는 합계: **207 passed, 0 failed, 0 skipped, 0 xfail**. 전체 suite는 실행하지 않았다.
- frozen fixture 3개 존재, 코드·문서 `git diff --check` 통과(원본 pytest 실패 로그의 줄 끝 공백은 보존).

기존 audit hook으로 pytest의 공용 outputs 접근을 차단했다. 물리·렌더·모델 호출,
실제 잠금·세션·수집 실행은 없다. fake host의 source·disk·lock 판정은 대체했으므로
실제 호스트의 수집 가능성이나 완료 증거가 아니다. 명령과 해시는 [verification.json](verification.json)에 있다.

[보존 검사](verify_preservation.py)와 [결과](preservation.json): v88 세 profile의 plan/bundle
전체 바이트 및 각 소스 239개, v90 두 bundle의 전체 바이트와 소스 247/248개가 기존 기준과
동일하다. `zone-final-pair-v90` / workflow **3.2.0**은 그대로다. 기존 v88 이후 인계문,
두 수집 shell 명령, `.github/workflows`도 바뀌지 않았다. 테스트 파일은 8개 CI shard 중
정확히 한 번 포함되고 시간 자료 coverage는 기존 **371/409**를 유지한다.

이번 작업은 `/private/tmp` extraction을 만들지 않았으며 작업 관련 추출 디렉터리도
남아 있지 않음을 확인했다. 새 물리·학습·평가 코호트가 없어 TensorBoard/Drive 작업은 없다.

CI shard 3 시간 제한은 별도 PR #354 범위다. 이번 로컬 통과는 GitHub 필수 CI 통과가 아니다.
PR #352는 draft로 유지하며 병합하지 않는다. 물리 수집·criterion B·학생/실물 성공은
이번 검증 범위 밖이다.
