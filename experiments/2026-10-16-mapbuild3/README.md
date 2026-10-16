# mapbuild3 — 깨끗한 시작 재측정 완료, 전체 NOT_READY

[PR #556 DRAFT](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/556), 같은 `codex/mapbuild1` 브랜치. **ownership-ack:** 필수 agent-ownership.md 확인; gcp5 L4 단독·gcp2 CPU 임대, 시작 겹침 검사 새 모듈·지도 코드만 수정했다. 공용 backend·장면 파일·다른 작업자 코드 수정0이다.

**초기 차체–상자 관통15.344881mm를 재현하고, 비관통 시작에서100ms 전진17.040mm를 확인했다.** drivecheck 판정대로 기존0.402mm 붕괴를 MJWarp 단독 구동 결함으로 해석하지 않는다. 새 시작에서 가까운 벽의 부분 지도는 정상적으로 나왔지만, 횡이동 척도·HIGH·미관측 장애물·장거리 관문은 남아 있다. 이전 mapbuild/CPU 결과와 합산하지 않는다.

`sim/spawn_overlap_check.py`의 기본 off `spawn_overlap_check_v1`을 새 후보에서 켠다. t=0 `mj_forward`의 로봇↔비바닥, 화물↔화물, 화물↔벽 관통을 사유·기하/몸체 이름·깊이·최소 contact gap·margin/solimp로 기록하고 거부한다. 바닥은 이름/plane 형식의 명시 집합만 제외하며, 비접촉 간격은 미측정이다. 허용 깊이0은 [MuJoCo signed contact distance의 기하학적 경계](https://mujoco.readthedocs.io/en/stable/computation/#contact)이고 margin/solimp를 초기 관통 허용치로 쓰지 않는다. 기존 장면 파일은 그대로 두고, 모델의 로봇 bounding radius로 만든 유한25개 XY 후보 중 두 자세가 함께 비관통인 첫 시작을 선택한다. 실제로3개 공동 후보를 검사해1개를 선택했다. 새 XY는 두 자세 모두 `(-0.275, -1.2779736397808383)`이다. 화물·r2/r3·카메라/FOV·물리·질감·NoSlip10은 유지했다. [시작 거부 분포](spawn-rejection-table.json), [fixture](fixture.json).

최종 소스에는 fixture/장면 SHA와 두 자세 동일 XY를 확인하는 loader도 넣었다. 물리 수집 소스보다 뒤의 입력 검증 추가이며 이번 물리에 소급 적용했다고 주장하지 않는다. 실제 수집 fixture의 bytes/장면 해시 일치와 동일 XY는 별도로 확인했다([검사](fixture-binding-verification.json)).

|깨끗한 시작,1초 구간(펄스+정지)|실제 FOLDED|기존 명령 예측/실제|실제 HIGH closed|HIGH 예측/실제|
|---|---:|---:|---:|---:|
|전진100ms|17.04048mm|0.75839|17.05024mm|0.75887|
|횡60ms|0.09020mm|76.70628|2.43458mm|2.81980|
|회전100ms|5.15871°|1.04079|5.36175°|0.93391|

[구간별 벡터·LK·명령 비교](command-phase-scale.json). 기존 v122 자세별 명령 모델을 그대로 사용했다. 짧은 횡 펄스의 원인은 미확정이며 76배 보정·새 마찰/구동 상수·정답 맞춤을 하지 않았다. FOLDED 몸체 tilt 중앙0.0252°/p95 0.0962°, 지면 기준 카메라 오차 p95 2.20mm/1.039°다([평가 전용](camera-summary.json)).

|관문|새 결과|판정 범위|
|---|---|---|
|1 실제 명령 주행|MJWarp2세계×4SIM초,세계당16000step·자기82/82프레임 cap_end|전진 회복, 횡이동·넓은 주행 범위 미통과|
|2 LK·HIGH|FOLDED 두 LK 후보 각각39/40,xy ATE p95 5.13mm·yaw0.191°; HIGH0/40 unknown|RGB 열 제외의 추가 이득 없음; 실제 하중/HIGH 자격 없음|
|3 부분 지도(10cm 격자)|FOLDED38/2990셀(1.2709%),잘못된 free0,벽 TP8·FP0,지도 밖0|관측38셀은 맞지만2952셀 unknown; 문/목적지 미관측|
|3 화물 장애물|reset collision box5개가 만든 격자 표본11개 중 예측0/11|물체 인스턴스 성공률 아님, 미관측을 성공으로 세지 않음|
|4 지도 있음/자기 지도 같은 시드·경로/도착|실행0/WITHHELD|warp10 최종 NOT_READY(CPU 접촉 export 오류3회),정상 비교 기준 없음|

[추적 점수](tracking-scores.json), [지도 점수](map-scores.json), [화물 장애물 별도 채점](obstacle-evaluation.json), [순차 누적 funnel](rejection_table.json), [후속 큐](next-queue.json). 희소 ORB는 기존0/40·FAST7 열 제외1/40이며 지도 pose에는 LK를 썼다. 정답·공용 top은 평가 전용이고, 추정 궤적/지도 저장 뒤 별도 채점했다. 새 시작은 시점·동료 가림도 달라져 지도 개선을 tilt 하나나 알고리즘 변경의 단독 효과로 주장하지 않는다. 장시간 frontier·미터 척도·경로/도착·운반·실물·학습·LLM은 검증하지 않았다.

읽기 전용 감사의 [전체 시드 표](audit-final/seed-overlap-table.csv), [분모·미확인/funnel](audit-final/rejection_table.json)은 authored reset과 저장 task tick0을 나눈다. gcp2 C3.12 `mj_forward`만 사용했고 CPU 적분0이다. 원본 XML·qpos·시드·입력 hash와 자산 경로 해석을 보존했다. [원래 호스트 해시 대조](origin-hash-verification.json)는 ACT186파일·warp280파일 전부 일치했다. 최종 검사기는 중첩 화물 몸체도 지원하며, 이번 [원본 XML248개](cargo-hierarchy-verification.json)에는 중첩 화물 collision geom이0이라 기존 감사 분류는 동일하다.

|코호트|settle 전 재구성 겹침/전체|원본 저장 task 시작 겹침/확인|남은 원본 시작|
|---|---:|---:|---:|
|ACT16w 기록|0/40|0/26|14 미회수|
|ACT16w heldout|0/40|미실행/0|40 미확인|
|warp8 beam R2|1/40|미회수/0|40 미확인|
|warp8 beam R1|1/40|0/40|0|
|release A|0/40|미실행/0|40 미확인|
|release B|같은40개 시작 연결,0/40|미실행/0|40 미확인|

seed8318724의 r3 좌/우 집게–동쪽 벽에1.146953mm(2geom쌍/4접점)를 발견해 ops-alert에 즉시 알렸다. R1 저장 시작은 절대tick17=원본setup1.7초임을 대조했고0/40으로 후속 알림을 남겼다. **settle 전 겹침이 R1 task 시작에 남았다는 뜻은 아니다.** R1/R2 결과는 합산하지 않는다. A/B는 plan과 시작 코드 경로가 같은 정책 비교이며 독립80시드가 아니다. 기존 최초 감사도 [audit/](audit/)에 보존했다.

[전체 시간순 검토](playback-review.md): 이전 실패·새 HIGH 자격 실패·새 FOLDED 추적 유지의 개요+r1+r2,전체0–4SIM초2Hz와10Hz 띠18개를 직접 읽었다. 최종 영상2개는41프레임·3배속1.366667초·각8MB 미만([r2 ffprobe/해시](playback-receipts-r2.json)). 첫15프레임 합성은 거부·보존했고, 새 합성의 띠는 직접 검토한 원본과 byte 동일이다. Mac 경로는 `outputs/e2e18-admin/playback/mapbuild3/r2/`, GUI0이다.

[수집 회수](capture-retrieval.json): gcp5→gcp2 원본343파일·7,909,113bytes SHA 불일치0. [압축 복원 검증](archive-verification.json): 큰JSON7개를1,826,645→86,224bytes zstd로 보관하고 해제 SHA와 원본343파일을 재확인했다. [영수증](archive-receipts.json)으로 `archive_json.py --receipt <원격 영수증> --restore` 후 재생한다. Mac은 요약·몽타주·검토 영상만 회수했고 전체 raw를 저장하지 않았다. [소스 SHA](source-receipt.json), [분석 재현 명령](reproduce.json)·[실제 수집 명령](physical-reproduction.json), [모든 시도](attempts.json), [검증](validation.json)을 보존했다. 물리 후보1라운드·정상2세계이며 초기화 HOST_ERROR2회와 감사/합성 오류는 별도다. 모든 정상 유한 물리는 cap_end이며 임무 성공이 아니다.

gcp5는8h상한 없이 시작했고 idle20/budget-stop ACTIVE를 유지했다. 자체 실행·GPU·타 lease0 확인 후 [TERMINATED](operations/gcp5-after-stop.json)로 끝냈다. 중간 gcp2 CPU의 수동 stop/setScheduling으로 전송1회가 끊겼고, 예산 발동 증거가 없음을 확인한 뒤 사용자 지시대로 재시작·전송을 마쳤다. 다른 호스트의 lifecycle은 변경하지 않았다. [최종 gcp2 자체 PID/lease0](operations/close-gcp2-final.json)을 확인했고 타 lease는 보존하여 CPU VM을 정지하지 않았다. 고정4SIM초 수집 loop561.82초는2세계 진단의 지연 기록이며 정식 첫30SIM초 속도 관문 통과나 성능 우위가 아니다. raw의 shared=true는 재사용 기록기의 고정값으로 남았으며 실제 gcp5 할당은 이 작업 단독이었다. 실제 청구 비용은 별도 미측정이다.

비물리24 passed,compile·whitespace·CI8shard 신규 검사1회 등록, 표준 `mapbuild3-clean-start` v0.1.0의 읽기 전용 plan을 확인했다. 관리 CLI를 통한 새 물리 인수·전체 CI·승인·병합은 별도다. 모델 키/에이전트 자격 증명 전송0·모델 호출0·Drive0. 전체 판정은 **NOT_READY / PR DRAFT**다.
