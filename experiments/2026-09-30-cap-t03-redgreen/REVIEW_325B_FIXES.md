# PR #325 두 P2 수정 — 2026-10-01

**DRAFT 유지 / 병합하지 않음 / 오프라인 코드 검증만.** 독립 검토
`6f87c959`의 `REVIEW_325B.md`와 반례를 기준으로 후보 `9db1bbb6`의 두 지적을
한 묶음으로 수정했다. 시작 시 `git fetch origin && git merge origin/main`은
Already up to date였으며 비교 main은 `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`다.
최종 실행 소스·명령·raw·해시는 `review_325b_fixes_verification.json`에 기록한다.

## 수정

- **R325B-1 / P2:** 빈 target, 잘못된 길이/값, 비유한 값/overflow/원점 좌표,
  현재 자기 영상·PWM·목표 색 근거 소실 때 정렬 표를 초기화한다. 이전 normal과
  `last_ready`도 폐기하며, 표의 일치도가 부족해진 뒤 이전 ready를 남기지 않는다.
  차체 이동에 따른 기존 window reset도 같은 초기화를 사용한다. 직접 box 호출에서
  영상 스키마·해시 검사가 거절되면 이전 target/정렬 근거를 무효화하고 예외를 유지한다.
  재획득 후에는 새 일치 표 세 개가 필요하다. 시간 기준을 새로 정한 것은 아니며,
  기존 최대 여섯 표의 창과 현재 관측 거절을 기준으로 한다.
- **R325B-2 / P2:** `WristColorBoxDelivery`의 기본값을 `mode='m1'`으로 고정했다.
  `mode='diagnostic'`를 직접 지정해야 진단 모드가 된다. 색 executor는 factory의
  profile/kind 외에 반환 skill의 mode도 자신의 mode와 같은지 검사하여 다른 모드를
  반환하는 factory를 스킬 실행 전에 거절한다. custom factory의 호출 형식은 유지한다.
  진단 executor를 쓰려면 executor와 factory 양쪽에서 진단 모드를 명시해야 한다.
- `tests/test_review_325b.py`는 검토 커밋에서 가져와 12개 매개변수 반례의 xfail을
  모두 제거했다. 기본 실행 대상은 현재 checkout이며 후보 미지정에 따른 skip이 없다.
  봉인 assertion과 기존 18개 행동 검사를 유지하고 경계 검사 40개를 추가했다.
  `scripts/run_ci_tests.py`의 일반 CI 목록에도 이 파일을 등록했다.

## 검증과 보존

- 수정 전 원문 반례: **13 passed, 12 failed**. 모두 assertion failure이며
  9개는 실제 색 소실 연쇄, 3개는 기본 factory의 모드 경계 실패였다.
- 수정 후 반례·경계 검사: **65 passed**, xfail/skip/error 없음. 원래 12개 반례와
  연속 정상 영상 양성 대조, 빈 값·NaN·inf·overflow, ready 결과 만료, 영상 누락/해시
  거절, 기본 M1의 동작/placement GT 거절, 명시적 진단 허용, factory mode 불일치를 포함한다.
- 관련 39파일 회귀 **1,235 passed + 291 subtests passed, 7 deselected**.
  필수 등록 소스 22개·소스 고정 34개·새 검토 65개를 포함한다. 실패·오류·skip은 0이며
  실행 전후 소스 해시가 같다. world/물리 3개와 MuJoCo geometry/projection 4개는
  이름으로 제외했다. 전체 저장소 또는 물리 회귀 통과를 뜻하지 않는다.
- frozen fixture 3개, v63 정적 manifest/source, 기존 registry 불변성,
  CI shard coverage 341파일과 새 검토 파일 1회 포함, `git diff --check`를 확인했다.
- 변이 **18/18 assertion 검출**, collection/setup error 0, 원본 소스 변경 0.
  기존 색 논리 10개에 이번 초기화·만료·기본 모드·factory 거절의 변이 8개를 추가했다.
  변이는 subprocess 메모리에만 적용하고 임시 plugin 디렉터리는 자동 정리했다.
- v6e 소스 85개·scene 소스 12개와 등록 JSON을 origin/main 바이트와 대조했다.
  두 집합은 중복된다. 지정한 `tests/test_zone_pair_registered_source.py`,
  `tests/test_zone_study_source_pinning.py`와 `.github/workflows` 전체도 바이트 동일하다.
  #332의 두 Ubuntu simulation job 15분 제한을 유지했다. 봉인/기대 hash/기존 기록을
  고쳐 검사를 통과시키지 않았다.

## 범위와 인계

호스트 잠금 없이 MuJoCo/Torch import와 네트워크를 막은 기존 guard로 검사했다.
로컬 물리/SIM/렌더/실제 모델 호출은 **0회**다. 사용자 요청에 따라 물리 인수 재생은
실행하지 않았다. 새 실험·학습·평가 코호트가 없어 TensorBoard 변환·viewer는 만들지 않았다.
실제 red/green 배송, host/runner·새 bundle 통합, v3 카메라/FK/IK/provider 검증과
독립 재검토는 별도다. 일반 CI는 push로 실행하며 CI 최종 상태는 PR에서 확인한다.

원본은 `/Users/changmin/projects/ugrp/outputs/cap-t03-redgreen/`에 로컬 보관한다.
Git에는 이 기록·검증 요약·테스트를 보존하며 raw 전체의 원격 백업으로 표현하지 않는다.
이번 작업은 `/private/tmp`에 후보 추출 디렉터리를 만들지 않았다. Drive 작업 없음.
