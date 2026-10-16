# ACTGPU1 — 기존 GCP L4 학습 파이프라인 DEV 시험

2026-10-15 사용자 승인 “ACT 학습 미리 시험”. 실행 소스 `9dc44d905c7c1c54833417c2da86bb1dbc56a869`, PR #504.
**300/300 optimizer step·EXIT 0·저장 모델 재로딩/출력 일치 통과. class dev, 시험용 모델이며 연구 결과·학생 성공이 아니다.**
[수치·원본 위치·해시·환경·실행 argv](actgpu1-summary.json).

- 기존 `ugrp-act-l4-pilot1`(서울 g2-standard-4, L4)만 재사용했다. 시작 전 `budget-stop ACTIVE`, 최신 순비용 메시지 0원, 사전 기능시험 이후 임계값/오류 로그 없음, 8h STOP·시작 스크립트 idle20분을 확인했다. 부팅 후 timer active/enabled, 종료 직전 active. 크레딧 **잔액과 실청구는 미확인**이며 비용 집계 지연은 남는다. 가드 변경·새 VM·다른 VM 접속·자격 증명 전송은 없다.
- 데이터: L4 `/mnt/act-source/act-main-f609979c/dataset`, 기존 원본50(학습45/16,018행, 보류5/1,833행). manifest SHA-256 `da651587d3cbe51f418f63fda55642b53e985a1fe1551db98909517065ba058b`. 200/200 파일 해시 재검증. `act-pilot1/dataset`도 같은 에피소드가 있는 이전 변환본으로 발견했으나 사용하지 않았다. **회복 데이터가 아니며 합성 배치도 만들지 않았다.** sim 원본도 L4 `/mnt/act-source/home/ugrp/ugrp-sim/runs/solo-record-<seed>-6f057f7e`에 보존돼 있다.
- 실행: BCE 완료 손실·명령 이력 dropout .2·batch8·seed20261015, 300step/프로세스840초·외부900초 상한. 실제 trainer94.118초/프로세스102.316초, GPU 오류0. 평균/중앙/p95 **.18396/.17082/.19488초/step**(배치 로딩·전송·학습 포함, 저장/로그 제외). 데이터 초기 로딩(해시 검증 포함)21.440초, 배치 로딩 평균/중앙 .02577/.01888초. 최대 CUDA 할당1.443GiB/예약1.916GiB.
- 체크포인트3개(100/200/300), 각각622,002,224byte, 저장2.410/2.287/2.272초. 최종 모델 로딩1.206초, GPU batch1 chunk 추론 **.01012초**(전처리 제외), 저장 전후 출력 완전 일치. 체크포인트 포함20개 원본 파일 해시, lite174,080byte 및 회수22파일 해시 확인. optimizer 파일은 저장·해시만 확인했으며 **optimizer 상태 재개 step은 시험하지 않았다**. 원본은 `ugrp-act-l4-pilot1:/mnt/act-source/actgpu1-9dc44d90`, 가벼운 회수본은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/actgpu1-ec0bd628/retrieved`다. 가중치는 GCP 영속 디스크에 시험용으로 보존하며 연구용 선택·배포 모델은 없다.
- 입력: 실제 추론 키 `observation.images.own_history [1,3,480,640]`, `observation.state [1,252]`만. 자기RGB4장, 발행명령16×14, skill4/kind9/role8/destination5의 고정 번호표, 자기 명령 기반 clock2다. 정답 위치·측정 관절·접촉·교사/평가 입력0; action/padding은 학습 표적이며 추론에서 제외했다. 기존2에피소드 처음/중간/끝6행의 원본 관측을 strict allowlist로 검증하고 context를 재계산해 텐서와 완전 일치했다. 전체 원장 의미 재감사·폐루프 성능 검증은 아니다.

회복 포함 **총50에피소드(45train+새5holdout)**, 동일 해상도·batch8·총10kstep(새 smoke300 포함)을 가정하면 한 군 **32.60분/$0.493**, step p95 민감도 기준 **34.42분/$0.521**이다. 두 군(p0/p.2)은65.19–68.83분/$0.986–1.041. 계산은 `10k×step시간 + 초기화2회 + 저장23회 + 재로딩/추론2회`이며 회복 데이터 행수·로딩/수렴·실제 학습 성공은 미측정이다. 이전 ACT6의 합성95개 데이터와 총50개 가정을 혼동하지 않는다.
공식 서울 g2-standard-4(L4+4vCPU+16GiB) **$0.907714004/시간**을 당일 HTML의 해당 지역/행에서 확인했다. 디스크·네트워크·세금·크레딧 제외 추정이다. 기존 제안 상한46,800초는 두 군 compute $11.8003에 해당한다. 이번 VM 전체 구간526.736초는 compute 약$0.13281다(실청구 아님).

기본 off인 `--profile-timing`과 명시적 `--run-class dev`를 추가했다(기존 분류 기본 milestone 유지). CUDA를 동기화해 측정하고 저장 비교 때 양쪽 모델을 eval로 맞춘다. `tests/test_grasp_act_pilot.py` **10 passed**, diff check 통과. 최초 `.venv-dev`에 pytest가 없어 기존 `.venv-sim-worker-mac`에서 다시 검증했다. Mac 학습·추론·물리 실행0.

## 회복 기록 뒤 실행할 명령과 미승인 초안

`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-act-train-ready-9dc44d90.json`의 **모든 bool은 false**다. 데이터 경로/해시·관문 영수증은 자리표시다. 새 교사의 **≥38/40**과 성공한 실제 lost→reacquired 장면≥20/40, 같은 교사 SHA/noise/host/camera 및 회복 기록 검토 영수증, 새 데이터의 전체 해시·train-only 통계를 요구한다. ACTGPU1 smoke를 새 데이터 승인으로 재사용하지 않는다. `grasp_act_training_guard`의 clean source/GCP/일치 smoke/정확한 main 승인 검사는 그대로다.

아래는 p.2 군의 **템플릿**이며 실행하지 않았다(p0 명령도 JSON에 있다). 관문/기록 검토와 비용·디스크 재점검 뒤 경로와 `main-approval.json`을 실제 영수증으로 채운다. 실행 cwd는 `/home/ugrp/actgpu1-source-9dc44d90`다.

```sh
/home/ugrp/ugrp-act-env/bin/python -m scripts.train_grasp_act --dataset '{AUDITED_RECOVERY50_DATASET}' --output /mnt/act-source/act-ready-9dc44d90/p02/smoke --stage smoke --steps 300 --max-wall-s 900 --seed 20261015 --done-loss balanced_bce_v1 --done-loss-weight 1 --command-history-dropout 0.2 --run-class dev --profile-timing
/home/ugrp/ugrp-act-env/bin/python -m scripts.train_grasp_act --dataset '{AUDITED_RECOVERY50_DATASET}' --output /mnt/act-source/act-ready-9dc44d90/p02/main --stage main --steps 10000 --max-wall-s 21600 --seed 20261015 --done-loss balanced_bce_v1 --done-loss-weight 1 --command-history-dropout 0.2 --run-class dev --resume /mnt/act-source/act-ready-9dc44d90/p02/smoke/step-000300 --smoke-summary /mnt/act-source/act-ready-9dc44d90/p02/smoke/summary.json --approval /mnt/act-source/act-ready-9dc44d90/p02/main-approval.json
```

남은 문제: 회복50개/새 관문·승인 영수증 미완성. 두 군 체크포인트 예상26.65GiB(예약32GiB), 종료 여유28.82GiB로 **예약32+바닥8GiB 미충족**이라 전체 학습은 차단한다. 디스크 변경/원본 삭제는 하지 않았다. 기존 VM은 **2026-10-15 16:19:20 KST TERMINATED**, 8h STOP 유지; GPU 프로세스0·소스 clean·act9/release18 무변경. ops-log에 시작/종료를 기록한다.

## 참고 자료

- [Google 공식 가속기 VM 가격](https://cloud.google.com/products/compute/pricing/accelerator-optimized): 당일 원문 직접 회수, Seoul(asia-northeast3) g2-standard-4의 첫 hourly/on-demand 열. 원문 SHA-256 `31e8c7183e020837eaa8d96e5ebca56362a842f7f6cefd58afc5a676b8953966`; 추출 offset·발췌는 로컬 `pricing-extraction.json`에 보존. 웹 도구는 본문 크기 제한으로 실패해 직접 회수본에서 확인했다.
- [PyTorch CUDA semantics](https://docs.pytorch.org/docs/main/notes/cuda.html), [benchmark 안내](https://docs.pytorch.org/tutorials/recipes/recipes/benchmark.html): 비동기 CUDA 시간 측정의 동기화·초기 준비 비용 분리 원칙 확인. 이번 값은 CPU 데이터 처리까지 포함한 wall 시간이다.
- 프로젝트 [act4](act4.md)·[act5](act5.md)·[act6](act6.md), `scripts/train_grasp_act.py`, `scripts/grasp_act_training_guard.py`, `harness/grasp_act_data.py`·`grasp_act_contract.py`: 원본/표적 분리·입력 whitelist·총10k/46,800초·32GiB 제안 근거. 과거 학생 성공을 이번 결과로 승계하지 않는다.
