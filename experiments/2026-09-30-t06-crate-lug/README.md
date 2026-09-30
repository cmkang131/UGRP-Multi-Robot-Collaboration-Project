# T06 — heavy_crate west/east lug 판단 skill

범위는 T06이다. 함께 전달된 T10b 복도 제어는 이 변경에 포함하지 않는다.
로컬 물리·SIM·렌더·새 모델 호출은 0회이며, **실제 crate API/물리 지원은 아직 차단**이다.
GitHub 정상 CI는 별도로 실행하고 취소하거나 건너뛰지 않는다. Draft PR로 인계하며 병합하지 않는다.

## 변경

- `harness/zone_crate_skill.py`: 900 g heavy_crate의 west/east lug 전용 판단기.
  몸체는 100 mm 폭이고 lug grip 폭은 40 mm이므로 body를 파지점으로 사용하지 않는다.
  crate 좌표계 파지점은 west `(-.10,0,.024)`, east `(.10,0,.024)` m이다.
  실제 `sim/zone_cargo.py` 정적 카탈로그와 테스트로 대조한다. beam의 길이·색·end 역할·
  M2 자세/팔 보정을 crate로 복사하지 않았다.
- 자기 RGB 인터페이스 → 접근/close → 양쪽 파지 확인 → 공통 시각 lift → 양쪽 holding →
  운반 → 각자 목적지 확인 → lower → 지지 확인 → open/해제 확인 순서다.
  입력은 해당 로봇의 JPEG, 자기 발행 명령, 공개 주문/정적 지도, 전달된 고정 enum뿐이다.
  `CrateEvidence`는 own-RGB 판독기 seam이며 현재 테스트에서는 fixture bytes를 읽는 fake다.
  실제 영상 인식, IK/servo/navigation 어댑터나 주행 경로를 구현했다고 주장하지 않는다.
- 기존 `zone_pair_status_v5` 채널의 공통 GO·heartbeat·영상 TTL을 재사용한다.
  새 enum 필드는 없다. crate skill에서 `carry_ready_1`을 운반 중 holding 증거 갱신에
  예약하고 `lower_ready_0`은 holding+목적지 확인을 뜻한다. 심판/좌표/자유 문장을 싣지 않는다.
  이 의미 계약은 새 crate profile에서만 사용하며 기존 beam wire/제어/기록을 바꾸지 않는다.
- 양쪽 준비 누락·미파지·holding 소실·heartbeat 단절·잘못된/오래된 영상·GO 누락·timeout은
  hold/abort로 끝난다. 명령 발행 전 촬영한 긍정 영상으로 다음 단계를 승인하지 않는다.
  완료는 `sequence_complete_unconfirmed`이고 배송 심판 결과와 분리된다.
- `harness/zone_crate_dispatch.py`의 opt-in `executor_plan`/`PairTeam.start`에 명시적
  kind dispatch만 두었다. **봉인된 원본 두 파일과 현재 runner는 바이트 그대로**다.
  새 facade의 claim은 crate의 r1/west·r2/east를 받아 API 요청을 만들지만, native 진입점은
  `CRATE_PHYSICAL_ADAPTER_UNAVAILABLE`을 반환한다. fake controller 주입도 이 관문을
  해제하지 않는다. 원래 study 진입점은 여전히 `UNSUPPORTED_TEAM_ORDER`로 crate를 거절한다.
  long_beam은 원본 함수/클래스로 위임하고 전용 거절/역할/실행 경로는 그대로다.
- 현재 역할은 고정 r1=west/r2=east다. T07 #323의 r3·역할 교환·예약/취소 구현은 복제하지 않았다.
  T07과는 위 두 API의 의미가 겹치며 최종 diff의 공용 파일 hunk는 없다. 조정자가 향후
  새 adapter에서 facade를 선택할 때 crate 분기를 beam role 해석보다 먼저 유지하고
  두 PR의 API·source-pinning 회귀를 다시 확인해야 한다.

## 선행 SHA와 검증 경계

시작 시 `git fetch origin`, 열린 PR 목록, 현재 worktree/branch·primary 지침을 확인했다.
시작 base/main은 `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e`였다.
primary main의 소스나 다른 feature worktree를 변경하지 않았다.
검사 중 선행 PR들이 병합되어 작업 브랜치를 main
`394f9cda5d67a9d1b94ad1688f39f5616fc00e7b`로 fast-forward했다. 검사한 소스/테스트
15개 파일의 해시는 전부 동일하다. 구현 커밋은
`3d79591e8b676ee2516874131bebb4ee47fa771d`이며 뒤 커밋은 이 검증/인계 문서뿐이다.

| 선행 | 확인한 상태/SHA | 이번에 사용하는 범위 |
|---|---|---|
| P09 #302 | MERGED `09081b3c46f0d51e02ef625e4be8c7d6f6e67963` | REQUIREMENTS/TASKS의 T06 요구·정적 거리. 정적 감사 124건은 이 후보의 물리 증거가 아님 |
| #255 최종 지도/시나리오 v2 | MERGED `1ed1f1e4bd51d1ec4907a6abe564c0635b45e7f1` | 원본 s2의 설정/요구 출처. 학생 실행 가능성은 승계하지 않음 |
| #300 CI 소유 | MERGED `e6cc2a8850f35dd8e29cb20a7615c7e0901f795f` | workflow/CI 설정 무변경. 기존 `test_zone_own_executor*.py` glob으로 새 테스트 수집 |
| #328 offline 잠금 | MERGED `6a57435e6e24f7f7a3f082d9458d3d9f4ebc010e` | offline pytest는 공용 host lock 없이 실행. 물리 잠금에 관여하지 않음 |
| T07 #323 | 시작 시 OPEN → 최종 MERGED `394f9cda5d67a9d1b94ad1688f39f5616fc00e7b` | 별도 opt-in 역할 routing/offline 검사. 두 API의 의미가 겹침; crate 대칭 파트너 지원으로 승계하지 않음 |
| P01 #305 | 시작 시 OPEN → 최종 MERGED `6c754f2d2ab4bc3c3b499b1ba3047797b017ee13` | 최종 환경 registry/Scene provider. T06 실제 장면 합성과 어댑터는 여전히 별도 확인 필요 |
| P02 #307 | MERGED `d7ee112e22018055ec08e1098c3f33a7a06cb420` | opt-in cyan+beam 혼합 경로. crate로 확장하지 않음 |
| CI #332 | MERGED `26545c2499f94c3f99a5d650f7cc8ea992f24196` | 정상 Ubuntu CI 시간 제한 변경을 base에서 가져옴; 이 PR의 CI diff는 0 |

[T07 범위 공유 댓글](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/323#issuecomment-5913458607).
[봉인 제약과 opt-in 전환 공유](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/323#issuecomment-5913804629).

## 재현과 검증 기록

기존 Mac Python 환경을 재사용한다. 아래 output은 매번 **새 경로**로 지정한다.
CI 설정, 가상환경, 시뮬레이션 세션, 잠금을 생성/수정하지 않는다.

```sh
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-t06-crate-lug/offline_checks.py \
  --output /Users/changmin/projects/ugrp/outputs/t06-crate-lug/offline-NEW

/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-09-30-t06-crate-lug/mutation_check.py \
  --output /Users/changmin/projects/ugrp/outputs/t06-crate-lug/mutations-NEW
```

최종 건수·JUnit/log 해시·검사 대상 소스 해시는 [verification.json](verification.json)에 둔다.
최종 **336 passed / 0 failed / 0 skipped**: logic 170, integration 110, pinning 56.
새 T06 테스트는 54개다. 최종 mutant **7/7 검출**, 원본 파일 해시 불변을 확인했다.
v6e 고정 소스 **85개**와 원본 시나리오 **12개**의 바이트도 그대로다.
`offline_checks.py`는 MuJoCo/모델 SDK import와 network connect를 막고 관련 11개 파일을
실행한다(최종 재검사는 logic/integration/pinning 세 독립 pytest 프로세스).
필수 `test_zone_pair_registered_source.py`, `test_zone_study_source_pinning.py`와
기존 M2 frozen source hash 검사, beam·own-input·통신 조건 회귀를 포함한다.
`mutation_check.py`는 자식 Python 메모리에서만 원본을 변형하여 실제 pytest assertion이
실패하는지 검사한다. collection error는 mutant 검출 성공으로 세지 않는다.

7개 mutant: 상대 준비 무시, grasp gate 제거, holding gate 제거, 운반 중 holding 상실 무시,
heartbeat 단절 무시, body를 파지점으로 변경, fake 통과의 physical support 승격.
원본 파일 해시 불변을 함께 확인한다. 테스트가 구현을 제거해도 녹색으로 남는지를 검사하는
증거이며 실제 물리 실패 주입이나 인식 정확도 평가가 아니다.

초기 대화형 확인은 새 테스트 48 passed였다. 카탈로그 대조 등 세 검사를 추가한 다음
51건 중 1건이 `Grasp.part`라는 잘못된 테스트 속성명으로 실패했다(실제 필드는 `geom`).
테스트를 수정했고 최종 검사에 포함했다. 이 실패 이력을 없애거나 물리 실패로 바꾸지 않는다.

첫 전체 검사 `offline-01`은 **328 passed / 5 failed / 0 skipped**였다. 두 공용 파일에
넣었던 dispatch 9줄이 현재 v6e DRAFT의 source pin을 바꾸어 registered-source 검사
5건이 실패했다. main 원본의 두 SHA-256이 등록 값과 같음을 대조했고, 좁은 재현도
동일 지점에서 16 passed / 1 failed였다. 등록/기대 해시/기존 테스트를 바꾸지 않고
**원본을 복구한 뒤 새 opt-in 모듈로 옮겼다**. 이 첫 실패의 JUnit/log/당시 소스 해시는
원본 경로에 보존한다. 최종 검사에서 원본 두 파일의 pin 일치와 기존 crate 거절,
facade의 crate 거절·실제 beam 위임을 모두 별도로 검사한다.

## 보존과 남은 일

원본 s1–s6/지도/실험·성공 번들, 봉인 등록 파일, frozen M2 소스, `.github/workflows`와
CI 설정은 변경하지 않았다. 신규 실행 번들/workflow ID도 아직 없다. 새 crate 모듈은
새 opt-in 진입점의 정적 source closure에 포함되며 기존 등록 실행에 자동 연결되지 않는다.
향후 새 adapter/runner에서 선택할 때 새 실행 등록으로 별도로 pin해야 한다.

raw는 primary `outputs/t06-crate-lug/`에 로컬 보관하고 핵심 요약/해시는 이 디렉터리에
커밋한다. raw 로컬 보관을 원격 백업으로 표현하지 않는다. UGRP 예외에 따라 Drive 작업은 없다.
이번 것은 fake/offline 소프트웨어 회귀이며 새 물리·학습·모델 평가 결과가 없어
TensorBoard 성공 지표나 물리 snapshot을 만들지 않았다. 실제 두 셀을 수행한 뒤에는
실패도 포함하여 원본 해시·새 snapshot·영상/화면을 확인해야 한다.

[PHYSICS_HANDOFF.md](PHYSICS_HANDOFF.md)에 최종 v3/walls_v3/tag0/weld OFF/noslip의
정상1+동쪽 파지실패1, 총 **1,800 SIM초**와 차단점·판정·보존 절차를 적었다.
하중/관절/마찰 및 실제 양측 holding 인식은 미측정이다. 물건/정책을 바꾸어 통과시키지 않는다.
구현의 독립 검토와 native 어댑터/물리 인수는 조정자에게 남아 있다.
