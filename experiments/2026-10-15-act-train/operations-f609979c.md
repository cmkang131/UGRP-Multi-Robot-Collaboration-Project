# f609979c 운영 결과 — 2026-10-15

실행 소스는 `f609979cd4e0b7174f999986408401817a5c991a`이며 PR #504의 승인된 RGB 학습 1회다. 이 문서 이후 기록 커밋을 실행 소스로 소급하지 않는다.

- 변환 결과 재사용: 전체 원본/산출물 해시 일치(기록된 RUN_META 100개 예외), 50 ep·17,851행·train45/보류5·grasp/release done 각50/50·입력0/0.
- 새 smoke300 → 총10,000step 완료. 최종 loss0.104448, 가중치 재로딩·main122파일/smoke20파일 해시 재검증. [손실 JSON](loss-curve-f609979c.json).
- 보류5 unique timestep done 검출 grasp0/5·release0/5, 예측양성0·precision null. 바퀴 MAE grasp0.03362/release0.03473, PWM MAE21.84/21.83. 중복 all-horizons 지표와 구분한다. 물리 성공 추정이 아니다.
- 학생 폐루프는 cyan91100 물리0/1, HOST_ERROR0. 90SIM초·wall277.16초, ACT113회·중앙0.323/p950.375초, 입력0/0(113요청·전체900행 재감사), weld off·교사 보정 없음. 안정들기0초·done0, release 미진입.
- 자기 카메라 고유10장(0–89.9초, 총12회 열람): 처음 중앙의 상자가 오른쪽 끝으로 이탈, 53.9/71.9/89.9초에도 거의 같은 바닥·상자 가장자리 화면. 접근/정렬 실패가 확인돼 같은 모델의 잔여9개는 미제출·중단했다. 성공 사례가 없어 성공 영상 표본은 없다. 모델 학습상의 근본 원인은 미확정이다.
- 원본은 gcp1 `~/ugrp-sim/runs/act-student-main-91100-f609979c`에 milestone으로 보존했다. 전체 SHA256SUMS 검증 통과. 학습 원본/체크포인트는 L4 보존 디스크에 남아 있다. [종합 JSON](operations-f609979c-summary.json), [직접 본 프레임·입력 감사](operations-f609979c-frame-review.json).

공식 서울 on-demand 단가를 재조회했다: [g2-standard-4](https://cloud.google.com/products/compute/pricing/accelerator-optimized) $0.907714004/h, [n4-highcpu-64](https://cloud.google.com/products/compute/pricing/general-purpose) $3.145365504/h. 시간과 추정액은 종합 JSON을 따른다. 크레딧 잔액·실청구·디스크/네트워크/세금은 미확인이다.

모델 [Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261015-grasp-act-f609979c)에 두 모델을 올리고 ZIP·내부18파일 재다운로드 해시·gcp1 CPU 로딩2/2를 확인했다. [배포 검증](operations-model-release-verification.json). 학습 VM은 TERMINATED. gcp1은 다른 작업의 tar/SSH 프로세스(PID48802/48800)가 있어 멈추지 않고 기존 유휴20분 가드에 맡겼다(8h STOP 유지). L4 사용45.52분·gcp1 ACT 작업구간42.07분(공유 호스트), 두 구간 compute 추정$2.8939이며 실청구는 미확인이다. 실행하지 않은9개를 실패 분모에 넣지 않으며, 교사 성공이나 오프라인 오차를 학생 성공으로 합산하지 않는다.
