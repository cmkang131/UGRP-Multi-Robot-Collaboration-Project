# beamact2 — 학습·학생20 평가 완료, NOT_READY

고정 최종10000step을 학습하고 보류20시드의 학생 폐루프 평가·원본 재계수·실패 영상 검토·Release 배포를 완료했다. 학생 성공은 **0/20**, 맡은 끝 안정 들기도0/20이다. 모델은 기본 off 비교 자료로 보존하며 채택하지 않는다. [요약](summary.json), [원본 재계수](student-summary.json), [거부·퍼널 표](rejection_table.json).

## 검증 결과

| 항목 | 결과 |
|---|---|
| smoke |300step, 저장/재로딩 chunk `torch.equal` |
| main | 총10000step, 최종 저장/재로딩 통과; 검증/보류로 선택 안 함 |
| GPU | 기존 L4·warp3 공유, 감독8250.397초(2.292h), main7109.814초; 속도 판정에 사용 안 함 |
| 학생 |20/20 실행 완료, 성공0/20; cap_end16·학생 실패4·HOST_ERROR0 |
| 단계 미통과 | 접근12·명목 정렬7·파지1 |
| 순서 퍼널 | 접근8 → 명목 정렬1 → READY1 → 파지0 →3초 들기0 |
| 독립 평가 | 맡은 끝 안정 들기0; 빔 어디든 기준 안정 들기3(별도 수치) |
| 입력/재생 |21,684 요청·86,736 RGB참조; 교사/정답 보정/top입력0, invisible_measurements·held_world_reads0;20회 명령/프로토콜 재생 불일치0 |
| 원본 무결성 |32,612파일·538,611,844B 전체SHA와 모든 RGB참조 확인; 이후 무손실 압축 해제SHA 확인 |
| 비물리 | Mac에서40pass; CPU 실행 소스에서 기존30pass; CI는 별도 확인 |

첫16회 중14회가30SIM초를 채웠고2회는 정상 학생 종료18.9/19.7초였다. 실제30초 표본 중앙 wall/SIM5.703은 경고(>3.5), 차단(>6)은 아니어서 나머지4회를 계속했다. [측정](first30.json).

## 오프라인 검증

각 셀은 ACT / persistence이며 모두 같은 validation19시드에서 계산했다. wheel은 정규화 명령 단위, pulse는ms, PWM은servo 단위다.

| 범위 | 단계 | N | wheel MAE | pulse MAE(ms) | PWM MAE |
|---|---|---:|---:|---:|---:|
| all_h0 | all | 6908 | 0.054589 / 0.023129 | 7.3179 / 2.9610 | 23.1315 / 8.3018 |
| all_h0 | align | 1142 | 0.074942 / 0.045359 | 4.8963 / 2.0958 | 10.8960 / 4.0497 |
| all_h0 | approach | 2968 | 0.069711 / 0.034729 | 11.3735 / 5.7525 | 15.5153 / 2.4551 |
| all_h0 | complete | 38 | 0.000000 / 0.000000 | 0.0000 / 0.0000 | 32.3579 / 0.0000 |
| all_h0 | pick | 2166 | 0.000000 / 0.000000 | 0.0000 / 0.0000 | 32.7310 / 15.1891 |
| all_h0 | ready | 38 | 0.002039 / 0.000000 | 0.1789 / 0.0000 | 13.9737 / 0.0000 |
| all_h0 | search | 556 | 0.152044 / 0.008813 | 20.1389 / 1.7769 | 51.5176 / 22.5493 |
| refresh_h0 | all | 913 | 0.053548 / 0.022809 | 7.1346 / 3.3832 | 23.6269 / 8.9093 |
| refresh_h0 | align | 145 | 0.072923 / 0.036810 | 4.6269 / 1.6786 | 11.4055 / 4.5476 |
| refresh_h0 | approach | 385 | 0.071624 / 0.032955 | 11.4982 / 5.5519 | 15.4016 / 2.9148 |
| refresh_h0 | pick | 304 | 0.000000 / 0.000000 | 0.0000 / 0.0000 | 33.7184 / 15.4099 |
| refresh_h0 | ready | 6 | 0.000000 / 0.000000 | 0.0000 / 0.0000 | 13.7000 / 0.0000 |
| refresh_h0 | search | 73 | 0.147133 / 0.038356 | 19.4002 / 9.6980 | 50.0740 / 22.8493 |

전체 wheel오차는136.02%, 재추론 격자는134.76% 증가했다. pick의 wheel0은 기존 TRAIN-mean 마스크/정지 단계 범위이며 전체 행동 성공을 뜻하지 않는다. 원 요약은 [offline-summary.json.zst](offline-summary.json.zst), 압축 해제SHA는 [회수 기록](offline-retrieval.json)에 있다.

## 증거·배포

실패2회와 별도 교사 성공1회의 전체2Hz·마지막10초10Hz를 검토했다. [시간순 검토](playback-review.md), [실패12장](failure-frames/frames.json). 학생 성공 영상은 없다. 근접 장면만으로 파지를 주장하지 않고 배정된 끝 접촉과 빔 어디든 접촉을 분리했다.

[Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261016-beamact2-v1):191,867,389B ZIP, SHA `1dc60f6bad63009c8aecfaa60688b9982dcc65e027932d571e7cd71418f2c56d`. 공개 재다운로드·전체10파일SHA·새 clone의 실제 CPU 로딩 통과([검증](release-verification.json)). 원본 학습 데이터/영상 전체 백업이나 새 물리 재실행을 뜻하지 않는다. 과거 asset을 덮어쓰지 않았다.

작업 종료 점검: beamact2 실행 자식과 임대0. CPU의 다른 임대 `reloc20.json`, L4의 다른 임대 `warp3.json` 및 다른 실행이 남아 VM을 정지하지 않았다. [정리 검증](cleanup-verification.json).

## 소스·재현 범위

학습·오프라인 소스 `ee1e2275bc5cb4a15278220214ebf1861d131fe7`, 학생 실행·재계수 소스 `24222c51e86c938799e7619290734db8e530a3f4`, 고정 dependency `26f84d0f0ada1c33473c83cca2d3415ce51bd247`. 모델 SHA `f7b2e195833555fa7b66e413200c40caad584677245b4346a98d5bd91336a2ac`. GPU3회/CPU20회 managed 원장 모두 exit0·실행 소스/입력 변경false. [GPU](gpu-managed-verification.json), [CPU 및 원본](integrity.json). metadata의 현행 workflow1.0.1은 이후 requires설명 수정이며 실제 이번 학습1.0.0·학생0.1.0을 바꾸지 않는다.

gcp2 원본은 `/home/ugrp/ugrp-sim/ops-reviews/beamact2/heldout20-v1`, 모델은 `model-v1`, GPU 원본은 같은 ops 경로의 `train/main`, `offline-v1`이다. 영상은 gcp2 `ops-reviews/beamact2/playback/seed-<seed>`와 Mac 기본 checkout `outputs/e2e18-admin/playback/beamact2-<seed>/`에 있다. >64KiB JSON은 `.zst`로 옮겼으며 [CPU 압축](cpu-compression.json)·[GPU 압축](gpu-compression.jsonl)·[요약 복사 압축](cpu-summary-compression.jsonl)에 원래/압축 해시를 보존했다.

재계수는 gcp2 실행 소스에서 `PYTHONPATH=. /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python -m scripts.analyze_beamact2 --root /home/ugrp/ugrp-sim/ops-reviews/beamact2/heldout20-v1`이다. 제출/학습 명령은 [GPU 감독](train_shared.py), [학생 유한 큐](run_eval.py)와 원본 managed 원장에 있다. 이 명령은 새 물리 실험을 다시 제출하는 승인이 아니다.

평가는 원래 cold start.5–2m를 유지했다(TRAIN local선정≤.8m). 교사 burn-in·유리한 시작 변경·수제 근거리 경로를 넣지 않았다. 보류 plan의 disturbance burst는 이 학생 평가에 주입하지 않았다. 명목 정렬 퍼널은 대체 교사 자세를 모두 대표하지 않으므로 최종 성공과 독립 들기를 별도로 보고한다. LLM E2E·운반·놓기·실물 검증은 이 범위에 없다.

남은 연구 문제는 학생의 접근·역할 배정·단계 신호 학습 품질이다. 보류20으로 체크포인트를 재선택하거나 같은 보류를 튜닝 관문으로 돌리지 않았다. PR #540은 DRAFT로 유지한다.

# 실행 설계와 사전 등록

beamact1 PR #540·같은 브랜치를 이어간다. TRAIN166/60,023행·validation19/6,908행·reserved20 분할과 정규화, batch8/chunk8/10Hz, seed20261015, balanced_bce_v1, wheel_pulse_train_mean, 최종10000step 고정 선택을 유지한다. validation/보류20으로 모델을 선택하지 않는다.

사용자 지시로 기존 gcp2 L4를 warp3와 공유한다. 2026-10-16 07:33 KST GPU 사용5817/23034MiB·util100%, 기존 ACT 예약 메모리2057306112바이트(동일 구조 actgpu1 기록)였다. 기존 /home/ugrp/ugrp-rl1b-act-env는 pinned LeRobot89236ea0·torch2.11.0+cu128과 일치했다. GPU 시간은 shared-load이며 속도 판정 자료가 아니다. warp3의 프로세스·VM·유휴/8h/budget-stop은 변경하지 않는다. 데이터20GiB·체크포인트/분석4GiB 예약, L4 제출 전38GiB 여유라8GiB 바닥을 보존한다. Mac에는 요약·실패 프레임/영상만 회수한다.

학생 실행기는 교사 객체를 만들지 않는다. 자기 RGB4장·실제 발행16명령·고정 스킬/물건/색 끝 토큰·자기 명령 시계만 격리 CPU worker에 전달한다. 정답은 evaluator의 결과 원장에만 쓴다. held_object_hidden_v1은 학생에게 화물 좌표 경로 자체가 없어 상시 충족하며 invisible_measurements/held_world_reads=0을 입력 allowlist로 검사한다. 근거리 명령은 ACT만 낸다. 통신은 pinned dependency26f84d0f의 GraspStartSync READY/GO/ACK를 그대로 쓴다.

ACT14차원에 READY head가 없어 자기 집게 닫기 proposal을 READY로 해석한다. OPEN2000/CLOSED1500의 방향에 따라 직전 발행보다 PWM이 감소하면1PWM이라도 READY다. 새 물리 수용 상수는 없다. 초기 구현의1750 최근접 분류는 평가 전 검토에서 제거했다(그 경계까지 부분 닫기를 먼저 발행할 수 있기 때문). GO/ACK와 원래0..1.5SIM초 지연을 통과할 때까지 ACT proposal을 보관하고 이전 PWM·정지 wheel을 발행한다. 허용 뒤 정확히 그 proposal을 발행한다. 대기 때 모델 추론/교사 동작/인식 보정은 없다. 완료는 학생 done과 기존3.1SIM초 관찰 창, 또는60SIM초cap뿐이다. 평가 정답으로 실행을 끝내지 않는다.

보류20은 기존 beampair8 heldout-plan을 그대로 쓴다. 원래 시작 분포(.5..2m)와 학습 local 선정(.8m 이내)의 범위 차이는 남기며 정답으로 시작 위치를 바꾸지 않는다. 평가 퍼널 접근(.8m)·명목 정렬(.203m station, .03m/.06rad)·READY·양 집게 접촉(.5N)·3초 들기(.012m/10도)는 기존 교사/평가기 수치를 재사용한다. 명목 정렬은 teacher의 대체/표본 자세 전체를 대표하지 않으므로 원시 geometry·단계별 독립 통과도 함께 남긴다. 최종 성공은 양 학생 완료+안정 공동들기3초+cap아님+감사0이며 교사와 합산하지 않는다.

실패 전10SIM초10Hz 자기 카메라 ring은 기록 전용으로 켠다. 전체2Hz overview/r1/r2를 보존하고 gcp2에서 영상·프레임 띠를 만든다. Mac GUI는 열지 않는다. 이 문단은 평가 전 등록한 기록 범위다. 실제 완료 결과는 위 표를 따른다.

완료/done 또는 cap 때문에 안정 공동들기를 숨기지 않도록, strict 학생 성공 n/20과 별도로 정답 평가의 안정 공동들기3초 독립 통과 수도 보고한다. 이 값은 명목 정렬 퍼널이나 학생 done에 의존하지 않는다. 학생 입력·종료·모델 선택에는 쓰지 않는다.

보류 평가 시작 전 추가한 배정 검사는 접촉점을 두 기존 색 끝의 최근접 구역으로 분류한다(같은 거리면 모호함). 각 학생은 맡은 끝 구역의 양 집게 접촉으로3초를 유지해야 strict 성공이다. 새 거리/힘 허용 상수는 넣지 않고 기존.5N/.012m/10도/3초를 유지한다. 빔 어디든 잡은 기존 접촉 기준의 들기 수는 별도로 남겨 교사 기록과 의미를 구분한다. 접촉점·힘은 평가에만 쓰며 READY/행동/종료/모델 선택에 쓰지 않는다.

참고: [ACT 공식 코드](https://github.com/tonyzhaozh/act)의 chunk 예측/closed-loop 실행·batch8/lr1e-5 구조와 기존 프로젝트 adapter를 재사용했다(2026-10-16 확인). [원 논문](https://arxiv.org/abs/2304.13705)은 이번 웹 재조회 실패이며 기존 beamact1의 참고자료다. READY proposal 연결은 프로젝트의 출력 제약에 필요한 설계이며 ACT 논문이 보증하는 성능이 아니다.

## 검증된 smoke300

소스 `ee1e2275bc5cb4a15278220214ebf1861d131fe7`, 기존 L4에서 실제 optimizer300step 완료. 저장/재로딩 후 TRAIN probe chunk의 `torch.equal`을 확인했다. wall303.400초, 최대 할당1,549,413,888B·예약2,057,306,112B이며 warp3 공유 부하이므로 속도 수용 판정에 쓰지 않는다. [원본 요약](smoke-summary.json). 학생 물리 성공을 뜻하지 않는다. main은 이 smoke의 정확한 source/data/mask/summary 해시에 묶어 총10000step까지 optimizer/RNG를 복원한다.
