# act16w4 인수 기록

`nativecontact-ack`, `resume-ack`. 원격 원본을 먼저 읽었고 기존 실행은 중복 제출하지 않았다.
소유 VM은 gcp2 L4 `ugrp-act-l4-gcp2`이며 CPU VM은 시작하지 않는다.
상한 없음, idle20·budget-stop 유지. Mac에는 요약·몽타주·실패 프레임만 회수한다.

noslip10 VAL5 원본 채점·행동 원장의 재계수는 **A0/5, B0/5**다.
두 팔 모두 발행 완료5/5 → 안정 들기0/5 → 안정 내려놓기0/5 → 임무0/5이며
같은 종류 아무 물체 성공도0/5, cap_end0이다. 종류별 cyan0/1, red0/2,
green0/1, yellow0/1이다. [재계수](noslip-baseline-recount.json)는 저장된 요약의
physical·lift·release·drop·안정 지속시간 값과 전부 일치했다.
단 chunk별 done 시각은 과거 원장에 없어 실패 메시지 문구 자체는 독립 재구성하지 않았다.
noslip10 데이터·모델·Release는 비교용으로 보존하고 native 결과에 합산하지 않는다.

native r1은 모델 그룹 검사에서 `from_xml_path`의 텍스처 상대경로 해석 때문에
HOST_ERROR로 종료됐다. 교사 rollout0이며 물리 실패로 세지 않는다.
XML을 바꾸지 않고 원래 world factory와 같은 Q 작업 디렉터리에서
`from_xml_string`으로 읽게 수정했다. L4의 비물리 로딩 nq243/ngeom1387/noslip0,
step0 확인 후, 같은 사전 고정40개87220–87259를 r2로 제출했다.
소스 e40ff44ce, dispatcher52916. [실행 인수](native-r2-launch.json),
[준비 거부 표](rejection_table.json). 40/40 PASS(종류별10/10), invisible/held0/0이다.
원시 평가 시퀀스로 Score40개를 독립 재계산했고8254개 원본 파일 SHA가 일치했다
([독립 관문](native-gate-independent.json), [실행 요약](native-gate-summary.json),
[실제 관문표](native-gate-rejection_table.json)). 기준값·score 모듈·원본은 바꾸지 않았다.
대표성공87244의 전체0–41SIM초2Hz·마지막31.1–41.0초10Hz를 직접 검토했다
([타임라인](native-teacher-playback-review.json)). 학생 성공으로 세지 않는다.

이후 별도 시드87420–87459의40개 기록을 시작했다. 소스c27a9d537, dispatcher64948,
32TRAIN/8VAL을 사전 고정했다. [기록 제출](native-record-launch.json),
[메모리·디스크·속도 수신](native-record-preflight.json). 첫30의 세계별 지연 중앙값34.292 wall/SIM은
속도 관문FAIL이며 물리 성공과 별개다.40세계가7호환 모델 그룹을 한L4에서 공유한 실제 부하이며,
사용자가 요구한 MJWarp·카메라·접촉을 유지하고 기록을 계속하는 사유를
`--speed-gate-override`에 남겼다. 속도 통과·성능 개선으로 보고하지 않는다.
기록40/40(종류별10/10), 원시Score40 재계산과8315개 원본 SHA 확인을 마쳤다.
전체18046 JPEG/이력/표적 쌍이 정합했고, 변환된14886행 중 TRAIN11860행/32회와
VAL3026행/8회로 나뉜다. [확정 데이터](native-dataset-receipt.json),
[전체 감사](native-dataset-audit.json), [기록 관문](native-fresh-recording-gate.json).
A/B300스텝과 저장/재로딩 예측 일치 검사를 통과하고10000 본 학습으로 이어졌다.
[후속 실행기](native-experiment-launch.json)는 기존 A/B를 재제출하지 않고,
검증→실제 영상 검토→h4→검토→h5→검토→선택 봉인→최종40 순서로 진행한다.
학습 실행 소스는c27a9d537로 고정하고 조정 코드37a8c8336과 구분한다.

종료된 자체 소스 사본8개만 sparse checkout으로 줄여 순여유10640805888바이트를
확보했다. HEAD와 Git clean을 각각 확인했고, 원본·체크포인트·Git 객체는 보존했다
([복원 명령/공간 기록](native-source-storage.json)).

교사 라이브러리6f057f7e → MJWarp controller f0db6b1a → 기록API0362037의
출처 관계를 유지한다. warpfit df5a1f86a의 프로필 파일 SHA256
`a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`는 byte 그대로다.
공용 backend·장면 수정0. 후속 native learning dispatcher는 명시적 단계별 호출만 하며
실패 후 자동 재시도나 최종평가를 시작하지 않는다. h1/h2/h3은 계속 기본off·미구현이다.
h4 C와 h5 D1은 각각10000스텝 새 초기화로 비교한다.

검증: 수정 접촉/분모/입력경계 관련 비물리5pass; 기존 ACT16 관련36pass1torchskip.
이는 CUDA 학습·native 관문 성공을 뜻하지 않는다. 최종91620–91659는 미개봉이다.

참고 자료와 사전 계획은 [resume3](../resume3/README.md), [protocol](../resume3/protocol.json),
[warpfit PR562](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/562),
[act16a PR528](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/528).
Refs #523, PR #539 DRAFT.
