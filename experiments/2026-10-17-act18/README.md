# act18: 근거리 ACT TRAIN 적합도부터 검증

상태: **NOT_READY (2026-10-18 03:33 KST)**. R8·R100 모두 100k fp32 학습을 끝냈지만 TRAIN4 관문이 **각 0/4**로, VAL8·FINAL40은 제출하지 않았다. 물리 임무 성공은 0/4이며 기본 제어기가 아니다. 두 모델은 NOT_READY 라벨의 재현·비교용으로 공개 Release에 보존했고, 배포 검증(익명 재다운로드·전체 SHA·CPU 로딩)만 완료했다.

## 최종 결과 (2026-10-17 09:25Z 학습 시작 → 10/18 03:33 KST 종료)

학습은 gcp2 L4 `ugrp-act-l4-gcp2`(g2-standard-8, project `ugrp-sim-b-1014`, account `changmin5781@gmail.com`)에서 소스 `52e486316c25be122dc1e872b10ef8cd1e8b98e8`로 실행했다. 두 후보 모두 100,000/100,000 updates, seed20261017, batch8, AdamW1e-5, **fp32**(당시 소스에 autocast/precision 코드 없음), readback_verified=true다.

|후보|chunk|steps|wall|체크포인트 sha256(step100000)|TRAIN4|VAL8|FINAL40|
|---|---:|---:|---:|---|---|---|---|
|R8|8|100,000|30,812s|`e1ec659216e289e1e5e9bb48ac597763ad8d1a088c3c85eb3205336307bb8d5a`|0/4|미제출|미제출|
|R100|100|100,000|30,779s|`44b11c3c147fb633fffa9e9cb6a0a48c5801f0b8fd2bdd9e33ea14a16804a544`|0/4|미제출|미제출|

TRAIN4(원 프로토콜 첫 4시드, 네 종류 각1개) 4세계는 모두 `cap_end`(90 SIM초 상한)로 끝났다. `requested 4 → grasp_done 0(4 전부 cap_end) → stable_lift 0 → stable_release 0 → task_success 0` funnel이며, R8은 88601·88603에서 물리 lift만 2/4, R100은 물리 lift도 0/4다. stage 자체 recount와 별도 실행한 독립 원본 재계수(같은 `act18_recount.py`, actor-actions/actor-inputs/owner evaluation-only/scene.xml에서 재계산)가 **둘 다 0/4로 일치**했다.

마지막 10 SIM초 10Hz 링을 1Hz로 샘플링한 4행 몽타주(각 후보 4시드): Mac 사본 `outputs/e2e18-admin/playback/act18-R8-TRAIN4/failure-montage-1hz.png` sha256 `a4466db727d50ef2f36a2fb4972c45d1a88093b574291d714f9c56fa80b05d9b`(VM `/home/ugrp/ugrp-sim/runs/act18/montages/R8-TRAIN4-1hz.png`), `outputs/e2e18-admin/playback/act18-R100-TRAIN4/failure-montage-1hz.png` sha256 `6a6013eceea0c16fe87fee615b1bc4840219a4fc15a51a88ed520c3c7e88213c`(VM `.../montages/R100-TRAIN4-1hz.png`). `outputs/`는 git 제외 경로라 실험 디렉터리에는 JSON·문서만 둔다(baseline-F 몽타주와 같은 규약). 몽타주에서 마지막 구간은 대부분 파란 바닥/상자 하단 띠이며, Lead 시각 분석(독립 재검증 아님)으로는 R8 4/4가 t≈9.7–12.4s에 base·arm이 전체 정지(마지막 100틱 관절 range ≤0.005rad, 속도 0, 손가락힘 0)하고 목표상자와 정확히 0.20m 지점에 머문다.

개루프 TRAIN 적합도(물리0, 1,430행)는 정지/진동 설명만으로 부족함을 보인다. R8 wheel 오차 median 0.00146·p90 0.00754, servo PWM p90 16.29, 교사 이동 2,482틱 중 projected-stop 123·raw 반대부호 44였다. R100은 wheel median 0.00225·p90 0.02017, servo p90 29.56, projected-stop 124·raw 반대부호 49다. 즉 교사 상태에서의 예측 오차는 작은 편인데(act17 10k 대비 크게 개선) 폐루프에서는 조기 정지한다. 이는 "개루프 fit 문제"와 "폐루프 누적/정지"를 분리해야 한다는 기존 act17 진단과 같은 방향이며, 이번에도 기본 제어기로 채택하지 않는다.

게이트 규칙은 코드로 강제됐다. `act18_evaluate.allowed_seeds`가 VAL8에 TRAIN4 raw-recount 4/4 영수증을, FINAL40에 VAL8 8/8·frozen selection을 요구하고 `act18_finish.prepare_final`도 같은 조건을 재확인한다. 이번에는 TRAIN4가 0/4였으므로 finish-r3 summary에 `VAL: NOT_SUBMITTED_TRAIN_FIT_FAILED`, `FINAL40_submitted=false`, `winner=null`이 기록됐다.

패키징은 두 후보 모두 수행했다(`finish-r3/packages/{R8,R100}/registry-entry.pending.json`, sha256 `17b1649c0e03152cf866ca22de3696e65a1d5d391cd9ea20ddb3ccfa23b8c261`/`b3f4aec754a2652f6a76d8a5c94239dd9c61ea7f5605a0497bb77d5756c5ea92`). 공개 Release: <https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261017-act18-v7-r1> (Pre-release, **TRAIN4 0/4 NOT_READY, 재현용·사용 금지**). 공개 검증은 `results/release-r1/public-verification.json`(sha256 `fc74c8967ea43f9341b13a8c6bff36e0ea934d6822b60d24020f94be35ed9f7a`)에 있다: 새 checkout `e91d41809`에서 익명 재다운로드로 ZIP SHA·크기 일치, 내부 24/24파일 SHA(207,592,611 / 207,969,467 bytes) 일치, bundled CPU 로더 `ready=true, chunk=8/100`. 이는 배포·로딩 검증이며 물리 성공이 아니다. registry는 `configs/model_artifacts.json`에 append했다(과거 자산 덮어쓰기 없음).

### 실패 진단과 post-close 가중 fine-tune 프로브 (10/18, gcp2)

TRAIN4 원본으로 정지 시점·자세를 재계수했다(`results/faildiag-r3.json` sha256 `4dff82ef…`, 도구 `scripts/act18_faildiag.py`). 정의: base 마지막 이동=바퀴명령>0.01, arm/finger=서보 PWM 변화≥3/≥10 마지막 tick, 물리 정지=평가-only speed>0.005 마지막 tick, 이동거리=∫speed dt.
- R8 4/4: base 마지막 이동 9.9/10.5/11.3/13.8s(교사 align 시작 8.0/9.0/10.1/12.3s 직후), 그리퍼 close 10.5–14.4s, 물리 이동 0.023–0.125m, 손가락힘 3.7–5.2N, 물리 lift 2/4·done 0/4, 물리 정지 14.5/15.3/19.2/79.1s.
- R100: base 마지막 이동 21.6–24.7s(88603은 91.6s까지 바퀴명령 지속이나 물리 이동 0), 88601은 물리 이동·손가락힘 0, 88600/88602 손가락힘 3.0N이나 lift 0/4.
- 공통: align 1Hz 몽타주에서 목표상자가 t≈10–15s에 화면 하단으로 이탈하고 이후 파란 바닥/벽만 보인다. done 0/8, cap_end 8/8. 교사는 같은 시점부터 close→lift→hold를 5–8s 더 수행한다(데모에 post-visibility 예시 있음). 진동 증거는 없고 조기 정지가 지배적이다(Mac 몽타주 `outputs/e2e18-admin/playback/act18-faildiag/`, sha256은 summary.json).

이 진단에 따라 **default-off post-close 가중 fine-tune 프로브 `act18-tune`**을 1회 실행했다(사용자/Lead 승인 조건). R8 step-100000에서 초기화(sha256 `e1ec6592…`, SHA256·adapter chunk8·protocol/dataset sha 검증), 같은 v7 TRAIN200, 2,000 step bf16 autocast(가중치·옵티마이저 fp32), seed20261017. 가중 표는 `grasp:lift/lift_settle/lookback_pose/lookback/lookback_settle/verify_lift/hold ×4`, `grasp:hover/descent/close ×2`, 그 외 ×1이며 episode 균등 샘플링을 유지한 채 에피소드 내 행을 가중했고, completion prior는 가중 측도로 재계산했다(추가 상수 없음). 마지막 short step만 저장하고 `packaging_eligible=false`라 패키징·배포·R8/R100 합산 대상이 아니다.

결과(`runs=tune-r2`, 학습 wall 269.8s, readback_verified=true): **물리 lift는 4/4로 R8의 2/4보다 늘었지만 grasp_done/done 신호는 여전히 0/4**이고 TRAIN4 0/4(NOT_READY, wall 856.6s, 원본 재계수 일치 `recount-r1/act18-tune-TRAIN4.json` sha256 `59f3b6ae…`). base 마지막 이동 10.1–15.1s, 이동거리 0.114–0.121m, 손가락힘 5.21–5.23N, done 0/4·cap_end 4/4로 정지·done 미선언 패턴은 유지됐다. 개루프 fit(1,430행)은 wheel median 0.00109·p90 0.00750, servo PWM p90 18.84, projected-stop 111이었다. VAL8·FINAL40은 규칙대로 제출하지 않았다.

실패 원인 1건과 수정: 첫 평가 시도(`tune-r1`)는 evaluator guard가 완전 등록된 100k 참조 모델만 허용해 `ValueError('complete registered100k reference model required')`로 세계 실행 전 HOST_ERROR(wall 2s)였다. 커밋 `c7e652e80`에서 등록된 short probe만 허용하는 `registered_tune_probe()`(후보·probe kind·init sha·chunk·protocol sha·training_complete·step=steps_override·packaging_eligible=false 검증)와 패키징 측 명시 거부를 추가했고, 거부/허용 테스트를 포함해 `tests/test_act18_tune.py` 9 passed다. tune-r1 실패 원본은 보존하고 tune-r2(수정 후)를 결과로 쓴다.

기억 입력 후보(프레임 이력·마지막 목표 상대위치)는 코드 없이 설계만 `MEMORY_INPUT_DESIGN.md`에 남겼다. 다음 라운드 승인 전이며 어떤 결과도 주장하지 않는다.

### B1 done-only 프로브 (act18-doneb1, 10/18)

사전등록 `B1_PREREG.json`(커밋 `a142046ac`). R100 step-100000에서 5,000 step bf16 fine-tune, 변경은 done 감독만(배치 50%에서 양성 1+uniform 7, 행동손실·balanced BCE 공식 불변), chunk100·batch8·lr1e-5 유지. 학습 wall 661.6s, 양성 배치 2,559/5,000, done_bce_loss 0.025. **TRAIN4 0/4**(wall 734.4s, 독립 recount 일치, 4세계 cap_end·물리 lift 0/4).

핵심 발견(원본 `results/b1-r1/`, VM `runs/act18/b1-r1/`): done 감독은 **일부 학습됐다** — 청크 미래 스텝(h≈99) 확률은 평균 0.454–0.574, 최대 **0.999**(전체 step-prediction 중 9,356개 ≥ .65). 그러나 실행이 읽는 **현재 스텝 h=0 확률은 평균 1e-4–2e-4, 최대 0.0034**이고 temporal ensemble 후 실행 결정도 max 0.21이라 문턱 .65·.5·.3·.2는 0틱, .1에서만 t≈50–84s에 발화(lift/grip 정렬 없음). tune/R8의 전체 max가 0.0008이었던 것과 달리 done 신호 자체는 학습됐으나 **미래 horizon에 치우친 라벨/실행 불일치**가 지배적이다. 즉 문턱·pos_weight 상향만으로는 해결 불가(h=0이 ~1e-4). B1 실패 원인표: (1) horizon 계약 불일치(주원인), (2) 물리 lift 0/4로 행동 축도 여전히 미달(R100과 동일). 후속 B3a(현재스텝 라벨만, `B3_PREREG.json`)와 (b) 터미널 예측 실행의 오프라인 분석으로 분리 검증한다.

### B2 표준 정렬 프로브 결과 (act18-std, 10/18)

사전등록 `B2_PREREG.json`. 20,000 step bf16 from scratch(wall 2,565.7s), chunk20(2.0s @10Hz), base 명령 5샘플 이동평균, best-val 선택(VAL8 시드 제외 32검증·256행), done 양성배치 10,075/20,000. val 손실 0.4907→**0.1392(step20000 최선)**. **TRAIN4 0/4**(wall 804.5s, 독립 recount 일치, cap_end 4/4, 물리 lift 1/4(88602)). done 확률 max raw 0.0014/ensemble 0.0013으로 문턱 미발화.

행동 프로파일(원본): base 마지막 이동 9.5–18.9s, 그리퍼 close 10.1–19.5s, 이동거리 0.011–0.128m, 손가락힘 0–5.28N — **R8/tune/B1과 같은 조기 정지 패턴**이다. 원인표: chunk 시간스케일·base 이동평균·best-val은 병리를 바꾸지 못했고, 잔여 축은 (1) 행동 형식(wheel 펄스/dt/PWM+디코드 클램프; `ACTION_FORMAT_DESIGN.md`), (2) from-scratch 20k에서는 done이 학습되지 않음(B1의 5k fine-tune은 100k 기반에서 미래 horizon done을 학습), (3) 단일 200시연 규모(co-training 미검증). gcp2는 B3로 이어서 진행.

### B2/B3 사전등록 (10/18)

- B2(`B2_PREREG.json`, 커밋 `8bafca6c7`): `act18-std`, 20k bf16 from scratch, **chunk20(2.0s @10Hz=ALOHA 100@50Hz 시간수평)**, base 명령 5샘플 이동평균(act-plus-plus `preprocess_base_action`), **best-val 선택**(VAL8 시드 제외 32검증에피소드·고정 256행), ACT 표준 aug 없음·현재프레임 1장 유지, done 양성배치 유지. TRAIN4 4/4 판정.
- B3(`B3_PREREG.json`): `act18-b3`, B2 체크포인트에서 5k bf16, **현재 스텝(h=0) 완료표적만 남김**(미래 horizon 제거). TRAIN4 4/4 판정. 평가 계약 변경은 하지 않으며 (b) 터미널 예측 실행은 오프라인 분석·메모만.

### B3 done horizon 프로브 결과 (act18-b3, 10/18)

사전등록 `B3_PREREG.json`. B2 체크포인트에서 5,000 step bf16, **완료표적을 현재 스텝(h=0)에만** 남긴 5k fine-tune. TRAIN4 **0/4**(B3a wall 872.5s, B3b 재시도 826.5s, 둘 다 독립 recount 일치).

- B3a: done_bce 0.949·pre-clip grad norm 752로 최적화 불안정, done 확률 max 0.0009로 문턱 미발화, 88600/88603은 행동까지 붕괴(이동 0).
- B3b(lr 2e-6 재시도): 안정화(done_bce 0.023, grad 53)했지만 done 확률 max raw 0.0018/ensemble 0.0007 — **여전히 문턱 미발화**, 물리 lift 2/4.
- 해석: 현재 스텝 완료시점은 단일 RGB+4틱 명령 이력으로 식별 불가(hold 마지막 행이 직전 행들과 관측상 거의 동일). horizon 라벨 조작만으로는 done을 실행 신호로 만들 수 없다. (b) 터미널 예측 실행은 B1 로그 오프라인 분석에서 t=9.2/20.1/21.5/41.7s 발화로 교사 close/hold와 3.5–19s 어긋나 신뢰 불가. (c) done 전용 history/시퀀스 입력 설계는 `DONE_HISTORY_DESIGN.md`.
- 다음 후보(승인 카드): offline done classifier(시퀀스/명령이력 입력, 물리 없이 AUC·발화 오차 먼저) — 평가 계약 변경 없음. 행동 형식 표준화는 `ACTION_FORMAT_DESIGN.md`, co-training은 `PHASE_C_PLAN.md`(B2 미통과로 보류).

### B4 hybrid done 모듈 결과 (act18-doneh, 10/18)

사전등록 `B4_PREREG.json`. **투명성: ACT가 done을 학습한 것이 아니라**, B2 체크포인트(행동 가중치 불변)에 **자기 발행 명령 이력 기반 GRU done 모듈**(오프라인 학습 AUC 0.9967, history16, 문턱 .65·persistence 1)을 결합한 hybrid다. 외부 issued_done 형식·성공 정의는 변경하지 않았다.

- 결과: **TRAIN4 0/4**(wall 399.8s, 독립 recount 일치)이지만 **4/4 모두 issued_done=True·cap_end=False** — 이전 후보들이 done을 못 내 90초 cap_end로 끝난 것과 달리 종료 신호가 작동했다.
- 발화: grasp done 31.3–31.7s(교사 26.5–31.3s, +0.3~+4.9s 늦음), release done 34.8–35.3s(교사 35.2–40.1s, −0.4~−4.8s 이름). 발화 p 분포 median 0.001·p90 0.457·max 0.991(발화 시 버스트).
- 실패 원인: **물리 lift 0/4, reason=lift_not_stable** — done 모듈은 명령 패턴 기반이라 물리 lift 없이도 발화했고(발화≠성공), 외부 성공 판정은 물리 Score+issued_done 둘 다 요구해 0/4. 즉 **done 축은 해소됐고 남은 원인은 전적으로 행동/물리 축**이다.
- 원본: `runs/act18/doneh-r1/`(head sha 82b797b9…, gate summary 39ea94e0…/raw-recount 4385b8a3…, head logs 39cf463d…/88fd8cf6…, done logs 9b48c548…/5425cec7…), Mac `results/doneh-r1/`. 다음: 교사 명령 vs 모델 예측 분포·디코드 클램프 offline 분해(행동축).

### 행동축 offline 분해 (10/18, GPU 없음)

B2 체크포인트(act18-std step-20000)를 TRAIN 발췌 1,200행에 CPU로 돌려 교사 명령·모델 예측·동결 디코더 클램프를 비교했다(`results/actionaxis-r1/action-axis.json`, sha256 `c9504188…`).
- 교사 원본 명령(TRAIN 290,288 wheel 값): 정지 55.8%, 비영 wheel은 **전부 0.35**, `deadzone(.155)/min(.31)/max(.40)`에 걸리는 값 **0.0%**. duration 비영 값 0.043–0.10s. 즉 교사 라벨은 클램프와 무관하다.
- 모델 open-loop 예측: wheel MAE 중앙 0.0114, duration MAE 0.0091, gripper close 비율 0.603(교사 0.603) — **예측은 교사를 잘 따르며 행동 형식/클램프가 lift 실패의 주원인이 아님**을 지지. 다만 teacher-moving 행의 7.2%가 디코드에서 정지로 바뀐다.
- 실제 실행(B4 actor-actions): wheel 0.31(교사 0.35), pulse 0.028s(교사 0.043–0.10s)로 **더 약하게** 실행되고 all-zero 35.4%. 잔여 lift 실패(0–2/4)는 closed-loop 상태 분포/조기 정지·데이터 규모 축으로 좁혀진다.
- 다음 카드 후보: (1) closed-loop 상태 분포 진단(자기 관측에서 정지가 시작되는 조건), (2) co-training(Phase C, 100k) — 단 B2 TRAIN4 미통과 상태라 Lead/사용자 승인 필요. 평가계약 후보 메모는 사용자 결정 대기.

### closed-loop 상태분포 진단 (10/18, GPU 없음)

B4 실행(raw `doneh-r1/DONEH-TRAIN4`)의 **발행 명령 이력**과 교사(TRAIN200) 명령을 skill/elapsed 구간에서 비교(`results/closedloop-r1/`, 계약 변경 없음).
- grasp 0–10s: 모델·교사 모두 base 이동 0.71–1.0로 유사.
- grasp **10–15s에서 분기**: 교사는 base 이동 0.91→0.26·gripper closed 0.05→0.63→0.98로 접근을 끝내고 hold/lift로 전환. 모델은 base 이동 **0.73–0.75를 20–30s까지 유지**하고 gripper closed는 **0.24–0.25**에 머묾. wheel 크기도 0.35→0.25→0.16으로 약화(디코드 클램프 0.31 하한과 혼재).
- release 0–2s: 교사는 즉시 물러나기(이동 1.0, 5–10s 0.53). 모델은 이동 0.05·wheel 0.08로 **사실상 정지** — release 동작이 누락.
- halt onset(grasp 마지막 이동): 모델 29.5/32.7/43.7s, 1세계 9.6s(교사 31.7s). 
- 주의: 같은 B2 체크포인트의 별도 실행(B2 run3)이 t≈2.2s에서 이미 분기했다 — closed-loop GPU 비결정성. 따라서 B2 raw와 B4 raw의 직접 비교가 아니라 **B4 단일 실행 내 교사 대비**로 해석한다. 실패 시작점은 open-loop 예측이 아니라 **grasp hold 전환과 release 물러나기 단계**다.
- 평가계약(물리 성공 정의) 후보는 `EVAL_CONTRACT_CANDIDATES.md`(사용자 결정용, 실행 금지).

### 조건 이탈·미검증 범위
- **R100 gcp5 미이동(deviation):** bf16 프로브(2,000 step, 1.10배)는 수용했지만, R8이 gcp2에서 fp32로 학습 중이라 정밀도가 섞이고(합산 금지), `act18_train.py`가 옵티마이저/RNG 재개를 지원하지 않아 42,400/100,000(≈13,484s)을 폐기해야 하며, gcp5 예산 1,000KRW 정지 위험이 있어 gcp2 matched fp32 pair를 끝까지 유지했다. 근거는 `bf16-probe-decision.json`.
- 이 학습은 **fp32**다. bf16 기본 전환 커밋(c7900c0ac)은 이 학습 시작 뒤다. 100k bf16 학습은 아직 없다(runtime 증거는 2,000 step 프로브뿐). bf16 결과와 합산하지 않는다.
- 미검증: VAL8·FINAL40·일반화 성공률(미실행), 100k bf16, R100 gcp5 이전·재개, raw 시연 전체의 원격 백업(Release 범위 아님), 다른 호스트/정밀도/조건과의 합산.
- 실행 실패 원본 보존: `finish-r1`(학습 전 정지, `8d95cb6a…`), `finish-r2` HOST_ERROR(`bd58ebb5…`, training owner disappeared), `baseline-F-TRAIN4-r1` HOST_ERROR(원 recount가 eval-owner에 없는 input_audit 키를 요구한 결함, wall 1,646.5s; 수정 8d21fbe1a 뒤 raw recount 0/4, sha256 `95a95ac2…`)를 그대로 남겼다.
- 기계 판독용 전체 실행·경로·SHA는 `summary.json`에 있다.

`SURVEY.md`는 공개 구현 비교, `DIAGNOSIS.md`와 `rejection_table.json`은 변경 전 실패 분포다. `diagnosis-summary.json`은 gcp2 원본에서 만든 축약 요약이며 전체 히스토그램·프레임 예측은 VM에 있다. 회수 SHA-256은 각각 `b36b39aa2b952c4c7e3e0048e272b9d75295f44256ffa7da9d5893190f7ea217`, `370de0a0c3ec6a2f31b3f25d4921413dbc00fbe1b8ec91faa98d12a02ad55307`이다. 첫 진단 시도는 물리 전용 환경에 torch가 없어 실행 전 실패했고, 기존 ACT 환경으로 재시도했다(새 환경·새 물리0).

새 비교는 `protocol.json`에 고정한다. R8과 R100은 같은 v7 TRAIN200 시연, batch8, seed20261017, AdamW1e-5, 100k updates를 사용한다. 차이는 예측 chunk8/100이다. 기존 완료 BCE는 동일하게 유지하는 과제 어댑터이며 원 논문의 추가 상태·카메라를 가져오지 않는다. 원본 LeRobot을 직접 호출하고 별도 ACT 재구현은 하지 않는다. 체크포인트10k/50k는 TRAIN 진단에만 쓰고 최종100k를 비교한다. 추론은 두 후보 모두 공개 ACT temporal ensemble0.01·매틱 재예측이다. 이는 기존 act17의 실행8틱과 다른 조건임을 명시한다.

모델 완성 뒤 첫 TRAIN4(원 프로토콜 첫4개, 네 종류 각1개)의 개루프·폐루프를 먼저 확인한다. 4개는 종류별1개의 유한 적합도 점검이라는 설계 선택이며 모집단 성공률이 아니다. 이 네 시작의4/4가 확인된 후보만 같은 VAL8로 가고, VAL8의8/8이 원본으로 재계수된 후보만 FINAL40에 진입한다. TRAIN/VAL/FINAL을 합산하지 않는다. 현재 새 시연 녹화는 필요하지 않다: 기존 h0부터 긴 chunk를 재구성하고 기존8개 미래 표적과 전수 일치를 검사한다.

Mac에서는 소스 편집·짧은 비물리 시험·요약/기존 프레임 띠 파일 열람만 한다. 실행과 실패 분석은 gcp2 L4 영속 디스크, 모든 gcloud는 계정/프로젝트 명시, gcp1·CPU VM 시작0이다. 모델 키·정답 학생 입력·정적 지도·weld·noslip은0이다. 예산2,000KRW 정지와 유휴20분을 유지한다. 새 이미지/텐서 복제0, 예상 신규 디스크는 소스 사본≤2GB+2후보×3체크포인트×0.21GB+평가/대표 영상≤2GB이며 기존 여유26.76GiB에서 바닥8GiB를 남긴다. 중간/최종 모델과 실패 원본을 보존하고, 결과에 쓰는 모델은 Release 업로드·익명 재다운로드·전체 SHA·로딩까지 검증한다.

훈련 진입점은 `scripts/act18_queue.py --enabled`, 개별 훈련은 `scripts/act18_train.py --enabled`다. 모든 새 대기열은 현재 main에서 가져온 `check_current_stack.py`와 `configs/current_stack.json`으로 점검하고 절대 `rejection_table` 경로를 연결한다. 실행 소스는 커밋 후 고정한다. 임대 `leases/act18*.json`과 자기 프로세스를 정리하고, 타 작업이 없을 때만 L4 정지·TERMINATED를 확인한다.

## bf16 짝 비교 (10/17, gcp5 단독)

AGENTS 10/17 bf16 규칙에 따라 gcp5 L4 한 대에서 R100 조리법(chunk100·batch8·seed20261017)을 2,000단계씩 fp32→bf16 순차로 돌렸다. bf16은 forward/loss만 `torch.autocast('cuda', dtype=torch.bfloat16)`이고 가중치·옵티마이저·grad clip은 fp32다. 단계 중앙값 0.1675→0.1523초(1.10배), 최고 GPU 메모리 2,230→2,186MB, last200 손실 평균 1.654→1.596, VAL8 손실 0.7358→0.6448(2,834행), NaN/inf 0/2000·0/2000이었다. 단일 시드·2,000단계 방향 점검이며 품질 결과가 아니다.

판정: 수용. 다만 R100을 gcp5로 옮기지 않는다. R8이 gcp2에서 fp32로 이미 학습 중이라 bf16 R100과 짝지으면 chunk 차이 외에 정밀도가 섞이고(AGENTS: bf16·fp32 결과 합산 금지), act18_train.py는 옵티마이저/RNG 재개를 지원하지 않아 42,400/100,000에서 옮기면 13,484초를 버리고 0부터 다시 해야 하며, 그래도 gcp2 잔여(약 5.1시간)보다 0.9시간 이르는 데 그친다. bf16은 다음 새 학습부터 쓴다. 원본·해시·근거는 `bf16-probe.json`, `bf16-probe-decision.json`, `bf16-probe-progress-*.jsonl`에 있다.

### 프로브 재계수 검증 범위 (10/17, haiku-verifier 독립)

원격 원본 JSONL은 50스텝마다 1점만 남겨 팔당 41점(2,000스텝의 2.05%)이다. 그 표본으로 다시 계산한 단계 중앙값은 fp32 0.1682초, bf16 0.1524초(1.104배)로 보고값(0.1675/0.1523, 1.0997배)과 방향·크기가 일치했고, 메모리 2,230→2,186MB(십진), VAL8 손실 0.7358→0.6448(2,834행 보고값), 비유한 손실 0건도 확인됐다. 다만 보고된 중앙값은 첫 200스텝을 제외한 1,800점에서 계산한 값이고, "0/2000 NaN"과 2,834행은 원격 실행 보고값이라 로컬 JSONL 41점만으로는 재현되지 않는다. 로컬 파일 해시는 decision에 기록한 원격 해시와 일치한다(b4801ee9…, 11f8e04e…, 8dda6137…). 이 검증은 표본 2.05%에 대한 방향·크기 확인이며 100k 학습 품질이나 전체 스텝 집계의 독립 재계산이 아니다.

새 ACT 학습 기본은 bf16이다(사용자 10/17 결정, 위 프로브 확인). `act18_queue.py`/`act18_train.py`가 `--precision bf16_autocast_v1`을 기본으로 쓰고 queue.json·훈련 config에 `training_precision` 영수증을 남긴다. fp32는 재생·정밀도 짝 비교에만 명시적으로 쓰며 bf16 결과와 합산하지 않는다. 이 기본값 변경 뒤의 새 학습은 아직 실행 전이라 런타임 증거는 프로브(2,000스텝)뿐이다.

## 정리 (2026-10-18 04:20 KST)

gcp2는 임대 파일 제거 → act18 프로세스 0·GPU 0%/0MiB 확인 → `gcloud compute instances stop` → `describe` status **TERMINATED**(2026-10-17T19:20:47Z) 확인 후 원본·체크포인트·검증 기록을 디스크에 보존했다(`results/cleanup-r1.json`). VM scratch `/tmp/act18_*.py`와 로컬 `/private/tmp/act18-dsh`를 제거했고, worktree의 비-act18 미추적 파일은 경로·크기·sha256을 cleanup 기록에 남긴 뒤 삭제했다. Mac에는 가중치를 쓰지 않았고 VM 자격 증명을 복사하지 않았다.
