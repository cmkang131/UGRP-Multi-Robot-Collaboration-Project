# simspeed2 — main 기반 v7 공통 가속

기준 main `9b7a8ef81fc6c9b6f263da02b056c927a6ca87ba`. #415의 exact relay 캐시만
이관하며 ego-wall-map 커밋은 포함하지 않는다. 봉인 catalog는 수정하지 않고 `.d` 조각을 쓴다.
사용자 지시로 새 v7 world는 기본 on, 진행 중 고정 소스는 변경하지 않는다. CI 대기·병합은 하지 않는다.

## 구현과 경계

- 공통 `build_world`가 생성 시 환경변수 `UGRP_V7_EXACT_SPEEDUPS`를 한 번 읽는다.
  `off` / `relay-cache-v1`(기본), 명시적 `exact_speedups=`가 우선한다. 알 수 없는 값은 거부한다.
- 불변 v7 DriveParameters 인스턴스별 LRU 256개. dtype/shape/전체 입력 bytes가 키이며
  miss는 원래 command_step을 호출한다. 반환 배열은 copy하여 변경 오염을 막는다.
- 추가 미세 개선: 불변 torque_cap_nm 속성을 직접 보관, relay state가 이미 있으면
  매 스텝 `dict.get` 기본 인수의 불필요한 zeros 배열 할당을 생략한다.
- 로그 버퍼링·접촉 축약·mj_forward 제거는 하지 않는다. 원래 mj_step/forward 호출 순서,
  물리·제어·임계값·카메라·샘플 주기 그대로다.
- `runtime-bundle.json`은 실제 world의 가속 모드·모듈 SHA와 기존 입력 bundle digest를 묶는다.
  자체 result writer를 쓰는 egomap까지 공통 reset에서 기록한다. 공통 writer 경로의 result에도
  runtime_speedups를 넣는다. 봉인 입력 bundle, drive-v7 물리 프로필 bytes는 바꾸지 않는다.
  on/off 출처 2파일의 차이는 의도된 것이며, 궤적·판정·명령·접촉·영상 파일은 직접 bytes 비교한다.
- 다음 코호트 main merge와 기존 source freeze 절차가 필요하다. 지난 코호트 admission을
  완화하거나 실행 성공을 새 SHA로 승계하지 않는다. v3 기반 S3를 v7 물리로 바꾸지 않는다.

## 사전 고정 검증

`suite.json`의 완료된 seed/원본 SHA를 사용한다: S2 v141 seed1065, S3 v142 seed14201,
egomap49 seed49001. 각각 30 SIM초 고정 발행 명령, ABBA(off/on/on/off), 조건별 n=2.
각 source SHA를 Git에서 별도 export하고 4개 공통 모듈만 overlay한다. 다른 worktree 수정0.
S2 backend 구성은 해당 원본 run_s2_landmarks_dev의 동일 class/scene 변환을 사용한다.
원본 scene.xml은 Git export에 따른 asset 절대 경로만 SHA로 치환하고 asset bytes와 나머지 XML 동일을 확인한다. on/off scene.xml은 직접 bytes 비교한다. 연속 프레임/샘플수/파일존재/영상 SHA를 먼저 확인한다.
매 물리 스텝 mjSTATE_INTEGRATION과 relay state 누적 해시, 최종 상태, 산출물 직접 bytes를 비교한다.
기존 v98-exact-v6는 원본 bundle에 있는 S2/S3에서 양쪽 동일하게 유지한다.
전체 온라인 제어기·임무 성공 검증이 아니며, 컨트롤러/모델 호출0이다.
각 실행 시작/끝 loadavg(1/5/15분), wall/SIM, nice=0, source/input/export hashes를 기록한다.
순서 S3 smoke → egomap54 → 본 검증, agent_lock 한 개, 부모/자식 확인, timeout 유한.

## 표준 방법·참고 자료

- [Python functools.lru_cache](https://docs.python.org/3/library/functools.html#functools.lru_cache):
  반복 순수 계산을 유한 캐시로 재사용한다. mutable 반환값은 복사해 alias를 차단한다.
- [MuJoCo simulation loop](https://mujoco.readthedocs.io/en/stable/programming/simulation.html#simulation-loop):
  mj_step은 forward dynamics 뒤 적분하며 파생 상태는 한 step 뒤처질 수 있다.
  카메라 갱신의 별도 forward를 증거 없이 제거하지 않는다.
- 선행 #415 고정 입력 12초 n=2 결과 1.253→1.058은 별도 조건이며 여기 측정과 합산하지 않는다.

최종 결과는 [30초 ABBA·프로파일 표](results/results.md), [기계 판독 요약](results/summary.json),
[실행·환경·재개 감사](results/run-audit.json)에 보존했다. 실물·새 연구 성과 아님. raw는 primary outputs에 보존한다.

## 보존한 진단·보완

- `97b408b2`의 v1: S2 ABBA 완료(625파일 차이0); S3 off 30초 물리·601프레임 완료 뒤
  원본 v142와 동일한 `ContractViolation: invalid item identity, kind, height or speed`로
  사후 referee가 실패하여 드라이버 종료. raw `outputs/simspeed-core-20261009-v1`,
  관리 기록 `outputs/simspeed-core-20261009-v1-managed/manifest.json` 보존. S3 시간 결과는
  실패 당시 미게시되어 통계에 포함하지 않는다. S2 수치도 최종 후보 전체 비교와 합산하지 않는다.
- benchmark는 이 특정 기존 referee 예외를 `EVALUATOR_ERROR` 판정으로 저장하여 양쪽
  오류 바이트까지 비교한다. 예상 밖 예외는 여전히 실패한다. 판정 규칙 수정0, 성공으로 바꾸지 않는다.
- 공통 캐시는 사용자 정의 DriveParameters 하위 클래스에 대해 원래 객체/계산으로
  fallback한다. 실제 enabled=false와 이유를 기록하여 기존 확장 동작을 보존한다.

## 최종 검증과 재개 기록

- 실행 소스 `725f45b155fda3f7dc93beba782b848ca3b4a6dd`, 각 조건 n=2.
  S2 1.083963→0.887058(−18.17%), S3 1.871652→1.674306(−10.54%),
  egomap 1.199962→0.997754(−16.85%) wall/SIM. 시작/끝 1·5·15분 부하와 개별 반복을 표에 함께 기록했다.
- 매 반복 120,000스텝 상태 체인·최종 상태 동일, 경로별 625/1,825/172개 행동 파일 직접 bytes 차이0.
  가속 모드 출처 2파일만 의도적으로 다르며 실제 mode/enabled/module SHA/입력 bundle 연결을 검증했다.
- wall은 동기 명령·물리·렌더·eval_sample 루프이며 양쪽 동일한 매 스텝 상태 해시 비용을 포함한다.
  생성/reset 및 루프 뒤 최종 referee·보고 직렬화는 제외한다. n=2의 로컬 개발 측정으로 전체 온라인 임무 시간의 보장은 아니다.
- v2는 감독 세션 종료로 17:07–17:08 대기 중단, 물리 실행0이다. 실제 원본 manifest는
  `running`/exit_code=null 상태로 남아 있었으며 그 bytes/해시를 보존했다.
  [host-interruption.json](results/host-interruption.json)에 “감독 세션 종료로 대기 중단” 사유를 별도 기록했다.
  v1의 process_failed 기록도 유지했다. v3는 소스·설정·명령이 새 출력 경로 외 동일하다.
  heading 잠금 종료 후 획득, v3 process_completed/exit0 및 자신의 잠금 정상 release를 확인했다.
- 로컬 변경 시험 14개 통과, 기존 v7 회귀 4개 통과. 완료 후 runtime 소스는 고정 SHA와 동일하며
  보고 자료만 추가한다. CI 완료 대기·병합 없음. 새 코호트의 활성 경로는 루트 README 안내를 따른다.
- [TensorBoard 검증](results/tensorboard.json): primary `outputs/tensorboard/1009-simspeed-core-725f45b1`,
  16개 뷰(ABBA12+프로파일2+진단2), 원본·이벤트·live scalar 132개 일치(허용오차1e-6), 새 영상0.
  기존 공유 서버 logdir/PID 확인 후 그대로 사용했다. Time Series 12실행 선택·6카드 고정,
  HParams 6열(case/outcome/policy/wall/commands/model_calls) 재적용을 실제 화면에서 확인했다.
  공유 legacy HParams는 runFilter를 적용하지 않아 수치 비교는 필터된 Time Series로 확인했다.
  모델 호출0, 응답시간은 측정하지 않았다. screenshot은 primary outputs에 해시와 함께 보존했다.

후처리는 [finalize_results.py](code/finalize_results.py), 이벤트 검증은
[verify_tensorboard.py](code/verify_tensorboard.py)에 정확한 당시 명령을 보존했다.
이 스크립트들은 기존 출력 덮어쓰기를 거부하는 1회 기록 도구다. 재생 시 새 뷰 경로/키를 먼저 지정한다.
