# ACT MJWarp 기록·학생 평가 API 인수

**RECORD_API_READY** (2026-10-16 05:42UTC). 실행 검증 source `0362037280c6cbc4677f70366db43b9892b23690`, 교사·물리 source `f0db6b1abb842ea65b71c433738210254f300a7c`. [준비 완료 영수증](RECORD_API_READY.json)의 원본 SHA와 [166파일 매니페스트](api-raw-manifest.json)를 보존한다. 모델·물리 모듈은 Linux gcp2 owner 프로세스에만 로드하고 Torch client에는 검증한 자기 RGB/발행 명령/작업 번호표만 넘긴다.

| API | 실제 지원·검증 범위 |
|---|---|
| `Client.reset(plans, indices)` | 첫 호출은 전체, 이후 선택 world의 새 free-body 시작. 초기화한 world의 모델·seed·scenario·종류·담당 물건·역할은 고정한다. 바뀌면 실패하며 새 owner와 정확한 C312 export가 필요하다. 검증은 모든 계획을 먼저 확인한 뒤 적용한다. |
| `Client.step(actions)` | world별 `{command, done}`, 원래 0.1 SIM초. actor는 자기 RGB만 받는다. 종료는 발행 done/SIM cap이며 평가 정답으로 바꾸지 않는다. |
| `Client.read_actor(i)` | 부작용 없는 복사본. 원래640×480/10Hz/K,D/FOV/마운트의 JPEG 이력, 발행 명령, 정해진 작업 토큰만. 모델 내부224 resize와 별개다. |
| `Client.instruct(i, skill)` | 명시적인 grasp/release 지시. 다른 world의 이력은 바꾸지 않는다. |
| `Client.read_training(i)` | 명시적 training 인스턴스의 reward/critic lane만. 평가 client에서는 거부하고 actor canary를 차단한다. `target_xy=None`; instance-mask centroid 미지원이며 요구하면 실패한다. |
| `Client.on_reset(indices)` | 선택 world의 policy chunk/RNG를 consumer가 초기화하는 callback. 실제 ACT15 chunk0 초기화/다른 world chunk 보존을 확인했다. |
| `Client.close(reason)` | 닫히지 않은 prefix도 cap/interrupted/HOST_ERROR로 마감하고 원본을 남긴다. |

[RPC 실제 검증](api-reset-pause-r8.json): world0과 world1의 서로 다른 새 시작 reset, 미선택 world의 persistent/port/history 즉시 byte 일치, 부적합 reset 원자적 거부, terminal world의 상태·명령·history clock 보존을 확인했다. 종료 world는 매0.1SIM 경계에서 integration/sleep/solver/relay 상태를 복원한다. 내부 GPU 계산 자체를 건너뛰는 구현은 아니다.

**다음 궤적의 bitwise 일치는 미검증이다.** 독립된 동일 baseline끼리도 첫 물리 step 뒤 qpos/qvel이 달라졌고, 전체 workspace 복제와 별도 프로세스에서도 재현됐다. 즉시 reset 경계와 terminal freeze 증거를 다음 동역학의 수치 결정성으로 확대하지 않는다. qpos 성분은 혼합 단위이며 오차를 mm로 바꾸지 않았고 새 물리 허용 오차도 만들지 않았다. 실패한 API probe r1–r4의 HOST_ERROR 원본을 보존한다.

기록 진입점은 `scripts/run_warp_act_record.py`. 승인된 f0db 교사를 수정하지 않고 `capture`가 돌려준 **동일 JPEG**와 호출 직전 스킬·phase·발행 명령을 저장한다. 종료 뒤 원래 SoloRecorder와 command trace로 관측/표적을 짝짓는다. gate controller SHA와 adapter SHA를 구분한다. [실제 기록 pilot](record-api-audit-r1.json)은 fresh train seed88960, 3SIM cap에서 JPEG30/30 바이트 일치·표적30/30·unpaired0을 확인했다. cap_end이며 데이터셋 승인·성공 시연이 아니다. bulk는 별도 승인 및 검토한 pilot2개를 요구한다. 후속 직렬화 수정은 previous의 deep copy와 후처리 실패 HOST_ERROR 기록만이며 f0db 행동 코드는 그대로다.

학생 진입점은 `scripts/run_warp_act_student.py` (`warp_act_student_smoke.py`). ACT15 가중치 SHA `d90a2b545709df6cd1a5972874db2e20c264007f9a798888f1bdccac22882ed1`로 실제 자기 RGB actor step2회×2world와 선택 chunk reset을 확인했다([영수증](student-api-smoke-r2.json)). `--full-evaluation`은 원래 SoloSequence의 grasp→release와900tick/90SIM를 실행하고 모든 행동이 끝난 뒤 원래 SoloScore로 평가한다. 이 full mode의 학생 임무 성공률, ACT 학습, 기록 본실행은 아직 측정하지 않았다. 학습 자료 승인과 이 API 인수는 별도다.

학습 전용 critic 실측 추가: [training-lane-r1](training-lane-r1.json), 별도 source dfa8457b0/API source2b99e00d8. 한 실제 물리 step 전후 critic512개·정답4필드를 분리 반환했고 critic 읽기가 actor 관측을 바꾸지 않았다. 원본13파일 SHA 불일치0, RL update0이다.

발행 명령 원장 추가(source7303986fd): 평가 owner는 물리 step 전에 `issued-commands.jsonl`에 world/generation/sample/시간/스킬·입력 RGB의 경로와 SHA·발행 action을 기록한다. 정답은 이 원장에 넣지 않는다. [실제 R3 검증](student-api-smoke-r3-audit.json)에서 명령4/4가 actor 출력과 일치하고 RGB 참조16개를 확인했다. 학습 hot path에서는 이 평가용 원장을 끈다. 중단된 student prefix도 summary에 보존한다.
