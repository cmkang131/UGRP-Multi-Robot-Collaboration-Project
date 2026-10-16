# ACT16a — ACT15 학생 실패 분석 (학습 없음)

ACT15 실패의 가장 큰 범주는 기능 정렬22/40이며, 새 추론 시점에도 필요한 교정의79.4%가 이전 부호를 유지했다. history_causal_split_v1을 첫 A/B로 둘 근거가 있다. copycat의 인과 확정과 학습 효과는 미측정이다.

|기존 ACT15 코호트|N|접근|정렬|집기|안정 들기|완료|cap_end|
|---|---:|---:|---:|---:|---:|---:|---:|
|같은20|20|13|2|2|0|0|8|
|새20|20|12|1|0|0|0|7|

첫 거부 분포는 정렬22, 접근15, 집기1, 들기 확인2다. cap_end15는 종료 방식이며 이40회 거부 범주와 별도 축이다. 원래 교사40/40은 기존 GCP1 기록이고 이번 교사 재관문이 아니다.

## 측정 결과

GCP2에서도 같은20 **0/20**, 새20 **0/20**이며 관문 수는 원래 ACT15와 같다. 완료/최초 실패 관문/cap_end의 실행별 요약40/40과 저장 영상 지문240/240이 일치했다. 이는 회수된6시점/실행의 재현 확인이며 원래 전체 raw의 바이트 동일성을 뜻하지 않는다.

유효 교사 표적은12,776행이다. 첫 행동 재추론 시점1,573행을 별도로 보았다. wheel MAE는 발행 명령[-1,1] 단위, pulse는ms, PWM은발행 펄스 값 단위다.

|구간|ACT wheel MAE|persistence wheel MAE|감소율|ACT pulse MAE|persistence pulse MAE|
|---|---:|---:|---:|---:|---:|
|전체 실제 발행|0.180003|0.180843|0.46%|24.078|24.089|
|새 추론 첫 행동|0.175615|0.180979|2.96%|23.985|24.362|
|새 추론·정렬|0.186771|0.194121|3.79%|23.132|23.821|

전체 이전 휠 부호 일치는97.14%지만 새 추론에서는85.66%다. 교정이 필요한 바퀴에서 이전 부호를 유지한 비율은 전체95.98%(22,250개 중), 새 추론79.42%(2,716개 중), 새 추론·정렬83.09%(905개 중)다. 새 추론에서도 전문가의 필요한 반전을 대부분 실행하지 못하는 정황이다. **청크 내부 지속만으로 설명되지 않지만, 이력이 인과 원인이라는 확증은 아니다.** PWM 오차는 persistence보다 나쁘다(새 추론48.18 대38.29).

교정 필요 직접 반전153건 중29건만 다음 교사 부호 변화 전에 응답했고124건은 검열(censored)이다. 교사 반전이 기존 청크 길이0.8초 이상 유지된113건에서도 응답27·미응답86이다. 응답한27건의 ACT 지연 중앙0.8초(최대2.8), 같은 경로 persistence는0.9초다. 이0.1초 차이는 같은 ACT 경로의 한 틱 지연 기준선 구조를 포함하므로 독립 정책의 우열로 해석하지 않는다.

마스킹은실제 재추론3,139회에서 비교했다. 원래 입력의 재계산 청크는 저장 청크와 최대 오차0이다. 과거 wheel/pulse만 TRAIN 평균으로 바꾸면 첫 행동이 평균 wheel0.01653·pulse2.955ms·PWM31.36만큼 바뀌고, 휠 부호4.39%가 달라졌다. done 문턱 교차는2/3,139다. 유효1,573개 표적에서 wheel 오차는0.175615→0.172974지만 PWM은48.18→55.09로 커진다. **추론 마스킹을 바로 배포할 근거는 없다.**

done 요청은26회 모두 안정 들기 전이었다. 그중1회는 settle을 못 마쳐cap_end이기도 하며, 종료 분류student_done25와cap_end15는 별도로 센다. “성공보다 몇 초 이른가”만으로 done을 평가하지 않는다.

결론은 **가장 큰 실패 범주=정렬 미통과22/40**, 행동 증상=접근·정렬의 교정 필요 상황에서 이전 명령 유지다. ACT16은 history_causal_split_v1의 동일 조건 A/B를 먼저 할 근거가 가장 강하다. RGB와 회복 표집 간 우열은 미측정이어서 research-act의2→3순위를 잠정 유지한다. 원래 DAgger 비율은행 기준26.96%이고, 연속 학생 상태의 교사 질의 라벨은 실제 교사 미래 궤적이 아니라는 표적 한계도 남는다.

[전체 지표](metrics.json) · [보고용 비율/반전 층화](compact-metrics.json) · [원래/재현을 분리한 관문표](rejection_table.json) · [40회 원본 위치와 판정](runs.json).

## 자료와 재현 경계

첫 GCP 프로젝트는 접속·시작·복사하지 않았다. ACT15 모델은 기존 GitHub Release에서 GCP2로 직접 내려받아 ZIP 및 내부10파일 SHA와 CPU 로딩을 확인했다. 원래 학습 데이터와 평가 raw는 GCP1 디스크에 남아 있어 사용할 수 없다. 필수 데이터 파일282개는 변환기 구조로 이름을 재구성했으며 원본 manifest를 회수한 완전 목록으로 표현하지 않는다.

정규화 TRAIN 평균은 Release의 actor/adapter.json에 보존된 값이다. 원래 TRAIN 행에서 평균을 다시 계산하지 못했다. 학생 자료는 GCP2 CPU에서 원래 계획·같은 시드·같은 체크포인트로 재생성했으며 GCP1 코호트와 합산하지 않는다. 원래 전체 명령·평가 바이트가 없어 완전한 궤적 동일성은 확정하지 않는다.

## 측정 정의

- persistence는 **각 학생 입력의 마지막 발행 명령을 다음 명령으로 유지**하는 예측 기준선이다. 독립 폐루프 persistence 성공률 시험이 아니다.
- ACT와 persistence를 동일한 학생 방문상태의 유효한 visible-only 교사 라벨에 비교한다. 교사 첫 hover 이후 무효 라벨은 제외하고 교사 행동 실행은0이다.
- 실제 발행 행동 전체와 새로8행 청크를 추론한 첫 행동만을 따로 집계한다. 8스텝 실행 자체가 높은 이전 행동 일치율을 만드는 혼동을 줄인다.
- 직접적인 +/− 휠 부호 반전에서 다음 교사 부호 변화/라벨 종료 전의 반응을 잰다. 미응답은 censor로 보존한다. 평균 지연만으로 미응답을 숨기지 않는다. 정지↔이동은 직접 반전과 구분한다.
- 이력 마스킹은 정규화된16개 wheel/pulse 이력 슬롯만0(TRAIN 평균)으로 바꾼다. 모든 PWM·이력 나이·지시·두 경과 시간은 동일하다. 추론 때만 바꾸므로 입력 분포 밖 민감도이며 인과 분리·성능 개선 증거가 아니다.
- 기존 관문·허용 오차·done 문턱은 변경하지 않았다. 접촉 이름·최소 틈은 평가 관측이며 그 물체가 충돌 실패를 일으켰다는 판정으로 바꾸지 않는다.

## 영상 검토

실패91427·91439와 교사 성공91434의 개요+r1 영상을3배속으로 만들고 전체2Hz, 실패 done 직전10초를10Hz로 직접 확인했다. 단독 작업이라 r2는 해당 없음으로 표시했다. 총32쪽 띠를 파일로 읽었고 Mac 화면 앱은 열지 않았다. 원본은 GCP2에, 파생 영상·띠는 Mac outputs/e2e18-admin/playback/act16a-*/에 있다.

- 91427:2.3–2.8초 사이 대상이 오른쪽 경계에서 사라지고 회복을 못 한다. 접근 관문 미통과,53.2초 done. “너무 이른”은 절대 시간보다 **완료 전인데 done을 냄**을 뜻한다.
- 91439:9.1초 접근 통과,12.7–12.8초 아래 경계 이탈,19.7초 재등장,22.1초 done. 집기/안정 들기는 없다.
- 교사91434:11.8–12.3초 대상이 아래로 가려진 뒤 얇은 초록 띠만 보이는 상태에서도 들기 성공.24.7초 hold,27.7초 release 전환,42.3초 전체 명령 완료다. 학생 grasp done과 같은 완료 시점으로 비교하지 않는다.

[시간순 관찰과 검토 범위](playback-review.json), [접근 실패 영상](videos/act16a-fail-91427-3x.mp4), [정렬 실패 영상](videos/act16a-fail-91439-3x.mp4), [교사 성공 영상](videos/act16a-teacher-91434-3x.mp4).

화면 이탈 자체는 성공/실패를 가르지 못한다. 조밀한 띠는 이탈→재등장→done 순서를 확인했지만 두 사례의 마지막 구간에서 빠른 회복 진동은 보이지 않았다. 부호 반전과 실제 차체 진동을 동일시하지 않는다. 예전 playback1의 ACT14 실패 done28.4/34.6 및 성공50.0은 이번 ACT15의 시각과 합산하지 않는다.

## 후속 계획과 미해결 사항

[ACT16 학습 계획 JSON](act16-training-plan.json)은 미승인·미실행이다. 우선 history_causal_split_v1의 동일 데이터 A/B, 다음 RGB 현재 해상도 보존과 작은 shift를 각각, 마지막 회복 표집을 비교한다.2/3순위 간 우열은 아직 측정하지 않았다. 기존20개·ACT15 새20개를 튜닝에 쓰지 않고 새 시작 상태91620–91659를 정적으로 만들고 기존120개 시작 계획과 중복이 없음을 확인했다. 이40개는 실행하지 않았다. [시작 상태](eval-plans.json)·[정적 표집 관문](setup-funnel.json).

훈련 명령은 미래 인터페이스 계획이며 관련 토글·GCP2 GPU admission은 이 PR에서 구현하지 않았다. 원본 데이터가 금지된 디스크에만 있어 새 GCP2 교사 관문·데이터 재생성 및 유효 미래 청크/첫 행동만 감독하는 표적 감사가 선행돼야 한다. A/B는 그 새 단일 manifest를 공유하고 ACT15와 직접 동일 데이터 비교라고 주장하지 않는다. 첫 A/B L4 VM 시간은 ACT15의 측정 창을 근거로 약1.58시간 추정이며 GCP2 GPU 실측값이 아니다. L4는 simalt4 소유로 이번 작업에서 사용하지 않았다.

실행 도중 다른 Mac CLI의 정지 명령으로 CPU VM이 끊겼다. 완료26회는 보존했고 추론만 끊긴3회와 물리 실행이 끊긴11회를 구분해 복구했다. 원래 부분 산출물은 덮어쓰지 않았다. [정지 근거](host-interruption.json). 학습·optimizer step0, 제어기 채택·병합 없음.

## 검증과 재현

Mac 비물리 단위검사7통과/1skip(torch 미설치), GCP2 동일 마스킹/호스트/반전 검사3통과. GCP2 raw25,806행·자기 RGB25,806개 SHA, 자기 발행 이력·clock을 모두 검증했고 입력/교사 입력 감사 위반0, 교사 행동 실행0이다. 보고 집계는 raw 관문을 다시 계산했다. [검증](raw-verification.json), [Release 검증](release-verification.json), [누락 목록](missing-data.json), [재현 지문](reproduction-fingerprints.json).

롤아웃 소스b4db8ba2, 고정 장면/교사6f057f7e, CPU actor torch2.11.0+cpu·고정 LeRobot89236ea0. 호스트는ugrp-sim-b-1014/ugrp-sim-gcp2/n4-highcpu-64다. 고정 교사 runner의 역사적gcp1 enum은 진짜GCP2 CPU metadata를 확인한 identity adapter로만 연결했고 GCP1에 접속하지 않았다. 정책·물리·카메라·상수는 바꾸지 않았다.

GCP2의원본은/home/ugrp/ugrp-sim/runs/act16a-gcp2-<seed>-b4db8ba2[-retry1]/raw, 정합 배치는/home/ugrp/ugrp-sim/act16a/recovery1, 분석/전체 원본 해시 목록은/home/ugrp/ugrp-sim/act16a/final-analysis-v2다. 원본 독립 전체 백업은 미완료다. 실행 argv는정합 배치와runs.json의거부표에 남겼다. 기존 출력에 덮어쓰지 말고새 --output을 쓴다.

```sh
# GCP2 CPU에서만; 학습/새 rollout 없음
cd /home/ugrp/ugrp-sim/src/0633dff7
PYTHONPATH=. /home/ugrp/ugrp-act-cpu-env/bin/python /home/ugrp/ugrp-sim/act16a/report_grasp_act_act16a_v2.py \
  --batch /home/ugrp/ugrp-sim/act16a/recovery1 --output NEW_REPORT_DIR
PYTHONPATH=. /home/ugrp/ugrp-act-cpu-env/bin/python /home/ugrp/ugrp-sim/act16a/compact_metrics.py --report NEW_REPORT_DIR
PYTHONPATH=. /home/ugrp/ugrp-act-cpu-env/bin/python /home/ugrp/ugrp-sim/act16a/verify_records.py --report NEW_REPORT_DIR
```

ACT16a 소유 프로세스·임대는0이다. GCP2 CPU는beampair5·scenetex3의 임대가 있어 유지했다. L4의 최종 조회는TERMINATED이며 사용/시작/정지는 이 작업에서 하지 않았다.
