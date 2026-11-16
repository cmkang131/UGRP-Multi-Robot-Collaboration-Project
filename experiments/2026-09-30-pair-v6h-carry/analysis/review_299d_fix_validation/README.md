# PR #299 4차 검토 두 P1 수정 검증

2026-10-01 KST. 검토 head `58dc07e7607e86dd526bc0defe9374489f0ce931`,
4차 검토 `a090317851811360815b3f8be9f8388764a3e2fe`.
먼저 main `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`를 병합한 기준 HEAD는
`f07614a0d2bdda9570b544a46f7090edd19cba8a`다. 수정 소스·테스트는 최종 검사
동안 고정했고, 검사 전후 SHA-256은 `provenance.json`에서 확인한다.
이 기록을 포함하는 커밋이 수정 후보이며 PR 댓글에 전체 SHA를 연결한다.

## 두 항목에 대한 응답

- **299d-R1:** 등록 `pair_chain_probe.chain_legs`가 사용하는 더 늦은 시작/끝
  GT를 같은 tie 순서로 골라 XY 거리를 재계산한다. end/leg error뿐 아니라
  planned length, travel, step error, along error, cross track도 같은 식으로
  대조한다. 필수 원 좌표/요약 누락·비유한 값 또는 1e-9 m 초과 모순은
  `INVALID`, `class=null`이다. 100 mm 과제 기준과 하드 위반 우선순위는 유지한다.
- **299d-R2:** recorded leg마다 양 로봇의 start/end를 필수로 확인한다.
  각 robot timeline·leg 번호에 따른 경계·stage GT 시각이 음수 없이 비감소인지,
  raw/GT/timeline/derived 경계 시각이 연결되는지 검사한다. snapshot은 실제
  trace/종료 창 안에 있어야 한다. 동시각·비동기 관측과 순서 없는 컨테이너는
  허용한다. 실제 cleanup GT와 마지막 trace의 약 0.05초 차이는 0.051초
  관측창 여유로 수용하고, 같은 경계 복사 시각에는 1e-9초만 허용한다.

새 필수 조건은 #292 `4c6b439f`가 실제 쓰는 형식에만 적용한다. 없는 접촉
수집 횟수/주기/receipt를 요구하지 않는다. HOST 미분류·분모 유지·완료 실패
흡수·하드 위반 합집합 등 D1–D5는 그대로다. controller/생산자 recorder/raw는 수정하지 않는다.

## 결과

| 검사 | 결과 |
|---|---|
| 관련 검사 13파일 | 499 passed, 실패/skip/xfail 0 (801.61초) |
| 생성 사례 | 10,000건, seed 202609300299, 사례당 5 불변식 |
| 4차 검토 | 기존 strict-xfail 10개 제거 후 모두 통과; 양성 대조와 일반화 포함 57개 |
| 공개 acceptance | 11/11 기대 판정 일치: lag-on 10 PASS_CLEAN, lag-off 1 FAIL |
| 전체 원본/projection | 판정 객체 동일, 공개 원본 36파일 해시 불변 |
| mutation | 기존 D1–D5 7/7 + 새 두 P1 5/5 검출; 생존 0 |
| 과거 공개 완료 | 16코호트 308/308 판정 일치, cA/cB 각 24/24 |
| 부분 tX1 | 별도 14건: PASS 12, HOST 미분류 2; 기존 판정 유지 |
| 공개 입력 보존 | 고정 자료 17개·fixture 13파일 유지; 공개 대조 입력/소스 697파일 재해시 일치 |
| CI 사전 검사 | frozen fixture 3개 확인, 새 리뷰 검사를 정상 offline 목록에 등록 |
| workflow | `.github/workflows/tests.yml`은 origin/main과 바이트 동일 |

새 mutation 4개는 최종 판정 guard 삭제, start 1개는 어댑터 자체의 필수 start
계약 삭제다. baseline witness 통과 뒤 mutant의 AssertionError만 검출로 센다.
import/runtime 오류는 검출로 세지 않는다.

## 재현·보존

`provenance.json`의 각 command 배열에 정확한 Python·명령·종료 코드·소스 해시가
있다. 호스트 잠금 없이 기존 `.venv-sim-worker-mac`에서 직접 pytest/분석기를
실행했다. 기록된 소요 시간은 성능 비교가 아니다. 원 로그·17개 전체 판정·697개
입력 해시 목록은 `/Users/changmin/projects/ugrp/outputs/v6h-classifier-299d-fix/`에,
작은 최종 요약과 로그는 이 디렉터리에 보존한다. `artifact_index.json`이 둘을 연결한다.

수정 전 `--runxfail -m xfail`은 의도대로 10 failed / 4 deselected였으며,
`baseline_counterexamples.txt`를 보존했다. 개발 검사와 최종 검사 모두 별도 로그다.
추가 보존 감사 첫 시도는 현재 runner와 등록 runner가 같다고 잘못 가정해 중단됐다.
현재 runner는 검토 head부터 원래 다르다. 올바른 비교는 현재 runner의 검토 이후
무변경, 등록/acceptance Git blob 일치, 거리 producer의 세 버전 일치다.
`protected_inputs.json`에 이를 구분했고 source/fixture를 고쳐 통과시키지 않았다.

## 범위와 남은 절차

오프라인 소비자 검증이다. 물리·렌더·모델 실행, blinded 원본 열거/조회, 실제
봉인 변경, Drive 작업, PR 병합은 없다. 새 실험 결과를 만들거나 회수하지 않아
TensorBoard 재변환/재개방을 하지 않았고 기존 snapshot을 보존했다.
로컬 raw의 원격 백업을 주장하지 않는다. 정상 push 뒤 CI 상태와 변경분 독립
재검토는 별도로 확인해야 하며 로컬 검사 통과를 병합 승인으로 표현하지 않는다.
