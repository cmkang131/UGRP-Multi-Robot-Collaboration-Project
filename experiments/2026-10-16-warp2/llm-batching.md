# LLM E2E의 세계별 대기 설계

이번에는 설계만 한다. 아래 방식은 공식 reset 기능을 참고한 **UGRP 제안**이며 구현/성능/정지 보존을 검증하지 않았다. 현재 E2E는 pending 응답을 poll한 뒤 SIM을 진행하므로 `pause_on_llm_v1`을 넣으면 새 스케줄 프로필이며 이전 결과와 합산하지 않는다. 모든 로봇이 같은 세계의 물리를 공유하므로 한 로봇의 판단을 기다리며 정지시킬 때 **그 세계 전체**가 멈춘다. 한 세계의 r1만 얼리고 r2는 물리를 진행하는 방식은 사용하지 않는다.

## 공식 코드에서 확인한 것

|시스템/고정 소스|reset/선택 방식|pause에 대한 확인 한계|
|---|---|---|
|MJWarp io.py@57b4692f:2656,forward.py:2224|reset_data(m,d,reset)의 세계별 bool/integer mask. step(m,d)는 forward와 integrator를 호출|확인한 step에는 active mask 인자가 없다. reset mask를 step mask로 사용할 수 없음. 이 조사 버전이 warp1 설치 버전과 같다는 뜻도 아님|
|mujoco_playground wrapper.py@d59156e0:198–246|env.step을 수행한 뒤 done mask로 data/obs/info tree를 reset state와 선택|autoreset 예제이며 대기 세계가 계산되지 않는다는 보증이 아님. freeze 시에는 data뿐 아니라 clocks/RNG/info도 선택해야 함|
|Brax training.py@6d039374:130–165|done에 따라 first_pipeline_state/first_obs 선택|pipeline과 obs 선택을 응용할 수 있지만 Python side effect·외부 요청·메트릭·CPU 상태는 별도 보존 필요|
|Isaac Lab direct_rl_env.py@86042738:662–703|reset_buf→env_ids→scene.reset/env event; articulation 선택 쓰기 API|env_ids reset과 root/joint state 쓰기가 전체 sim.step의 독립 pause는 아님. PhysX나 Isaac 도입은 이번 범위 밖|

링크·해시는 README 참고 자료와 official-sources.json에 있다. 공식 소스 원문을 직접 읽었고 선택 reset의 존재와 pause의 검증을 구분했다.

## 세 가지 선택

|방식|실행 의미|이득/비용·검증 요구|추천|
|---|---|---|---|
|세계별 저장·복원|pending 세계의 authoritative state를 GPU에 저장→배치 step→pending lane을 복원. CPU view/port/교사/통신/clock/RNG도 그대로 둠|기존 step과 고정 CUDA graph 재사용 가능. pending lane 계산량은 낭비. contact/constraint pool이 세계 공유 배열이므로 qpos/qvel만 되돌리는 것으로는 불충분. 파생 배열 재계산/solver warm state 일관성 검증 필요|공통 백엔드가 완전 상태 API를 제공하면 첫 정확성 프로토타입. warp2가 별도 복사 커널을 구현하지 않음|
|세계별 active mask|physics/constraint/contact/통합/시각·센서 업데이트의 모든 관련 kernel이 active-world 선택을 지킴|낭비 감소 가능. 공식 step API에 없는 기능을 일부 integrator에만 넣으면 stale state·공유 capacity 오염 위험. backend 공통 변경과 전체 단계 검증 필요|warp1 후속 공통 기능으로 제안. 이번 B의 선행 조건으로 요구하지 않음|
|비동기 활성 cohort|LLM을 기다리는 lane을 활성 cohort에서 빼고, 응답 준비된 세계만 다음 공통 batch에 넣음. 고정 topology/model·capacity별 버킷 사용|대기 lane의 물리 계산을 생략. 상태 gather/scatter와 graph size 버킷/재컴파일 비용 발생. 영속 world_id와 batch slot을 분리해야 함|장기 throughput 1순위. 처음에는 고정 slot+검증된 저장/복원으로 정확성을 확인한 뒤 이동|

`ctrl=0`은 자유 낙하·미끄러짐이 계속되므로 정지가 아니다. `qvel=0`은 속도 상태를 파괴한다. `timestep=0`은 일부 actuator 연산의 dt 나눗셈 등과 맞지 않아 안전한 pause API로 간주하지 않는다(MJWarp forward.py:1636). sleeping은 접촉/명령으로 깨어나며 clock/외부 큐 정지를 보장하지 않는다. 전 세계 barrier는 단순하지만 느린 모델 응답 하나가 전 배치를 막으므로 fallback 검증용으로만 둔다.

## 상태·시각·요청 계약

영속 키는 `(run_id,world_id,robot_id,episode_epoch,call_id)`다. batch_slot은 재배치될 수 있다. topology와 물리 profile·카메라·장면 hash가 다른 세계는 같은 모델이라고 가정하지 않고 버킷을 나눈다. pending 세계의 `sim_t`와 명령 만료·서보 큐·자기 odom·관측 frame_id·메시지 delivery SIM deadline·교사/판단 상태·RNG는 진행하지 않는다. 모델 HTTP timeout/비용·호스트 상한은 wall 시계로 계속 진행한다. 계획/탐색 예산은 계산량/SIM 기준을 유지한다.

요청 snapshot은 발행 당시 자기RGB·허용 이력만 담고 hash를 고정한다. Mac 중계에 비동기로 제출한다. 준비된 다른 세계의 응답이 먼저 와도 대상 world_id/epoch/call_id를 검증하기 전에는 명령·통신을 적용하지 않는다. 늦은/중복/다른 epoch/비정상 finish 응답은 ledger에 비용과 사유만 남긴다. retry/rate limit/최대 요청 수는 기존 공급자 계약을 지키고, N배 GPU 세계 수를 N배 동시 모델 호출 허용으로 해석하지 않는다.

pending→ready 전환은 해당 세계의 정지 SIM 시각에서만 일어난다. 기존 `host.step_to(now)` 이벤트 순서와 안정된 world_id 순서를 정하고 재생에 남긴다. 네 통신 조건 사이의 구조화된 옆길·파지 정답·평가 성공을 scheduler metadata로 LLM에 흘리지 않는다. 완료한 세계를 재사용할 때 물리 상태뿐 아니라 frame/guard/port/통신 ledger/RNG/cache를 epoch별 reset한다.

## 구현 전 필요한 반례와 측정

1. 동일 초기 상태에서 A는 대기, B는 정상 진행: A의 integration/명령·RNG·시각·이력 hash가 매 tick 그대로인지, B는 N1 실행과 같은 결과인지 확인한다. 정지 전 속도가 0이 아닌 사례와 들고 있는 사례를 포함한다.
2. A만 reset: B의 물리·contact force·카메라·guard·메시지·frame_id가 변하지 않아야 한다. 공유 contact/constraint capacity overflow도 기록한다.
3. 응답 역순/중복/timeout/비정상 종료/epoch 교체: 잘못된 세계로 action/message가 가는 횟수0, 비용 원장은 보존. 모델을 쓰지 않는 고정 응답 fixture로 먼저 검사한다.
4. pause 전후의 전체 상태 복원이 scalar 이어달리기와 일치하는지 검사한다. qpos만 맞고 warmstart/act/ctrl/mocap/applied force/port가 다른 상태는 통과가 아니다. 허용 오차를 임의로 새로 만들지 않고 공통 백엔드의 표현별 계약과 기존 성공식으로 보고한다.
5. 실제 모델 사용은 별도 승인 범위와 endpoint alert 확인·동시 부하 점검 뒤 진행한다. active fraction, physics 낭비율, gather/scatter, host sync, RGB, LLM 대기/429, first-response, end-to-end SIM초/초·SIM초/$를 분리한다. 계산하지 않은 pending SIM초는 처리량 분자에 넣지 않는다.
