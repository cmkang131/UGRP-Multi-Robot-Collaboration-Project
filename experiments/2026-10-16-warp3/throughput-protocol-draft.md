# 4단계 warm 측정 검토안 (미구현·미실행)

40시드 교사 관문과3단계 API 검증 뒤에만 확정·구현한다. 현재 관문의 공유 부하/SIGSTOP 시간은 intrinsic 처리량에서 제외한다.

- 우선 구동+물리+640×480/10Hz RGB/JPEG 경로를 동일 상자 시나리오의 안정된 접촉 구간에서 비교한다. teacher FSM/ACT 추론/학습 시간은 별도다. 비교 C16은 gcp2 CPU VM, MJWarp N64/256은 외부 GPU 작업이 없는 L4 구간 또는 승인된 gcp2b다.
- 초기화/JIT/capture/최초 RGB와 별도 동역학 warmup을 시간에서 뺀다. 후보 측정 창3SIM초=기존 Score의 lift_hold_s3초×10Hz=30개 제어 간격이다. 성공 수용 기준이 아니라 실행 예산을 제한하는 측정 창이며, 실제 적용 전 구간 안정성/컴파일 로그/분산을 확인한다. 짧은 창의 결과를 전체 교사/ACT 임무 처리량으로 확대하지 않는다.
- 초기0.1SIM prefix 반복만으로 warm이라고 하지 않는다. 검토할 방법은 각 backend에서 정상 teacher로 들기/hold에 도달한 뒤 고정 발행 PWM/바퀴0 명령을 유지하는 접촉 부하를 비교하는 것이다. 전체40SIM을 N256으로 여러 번 돌리는 대신 N1 정상 실행의 full integration/sleep/warmstart/relay/port 상태를 정확히 복제할 수 있는지도3단계 reset 검증 뒤 판단한다. 현재 states.npz에는 qpos/qvel만 있어 그 파일만으로 완전한 접촉/sleep snapshot이라고 주장할 수 없다.
- C와 Warp의 같은 초기 시나리오·알고리즘/명령 조건, 접촉 수·solver iteration·payload 상태·RGB/JPEG 바이트 수를 함께 기록한다. C RGB 동등성이나 물리 동등성을 새 관문으로 넣지 않는다. 복제 world는 처리량 부하일 뿐 독립 교사 n/N에 더하지 않는다.
- 외부 leases/실행 PID와 측정 구간 실제 부하를 확인한다. GPU 예열과 actor/model 프로세스가 측정 시간에 섞이지 않게 하고, 단독 측정 전 실제 계측 경로를 확정한다. 다른 작업은 중단하지 않는다.
- SIM초/$는 한 VM 측정 시간과 명시한 hourly 단가 가정으로 계산한다. 겹친 그룹 시간을 합산하지 않으며 실제 결제·크레딧 사용액과 구분한다. 새 VM은8h/idle20분/budget-stop을 유지하고 임대/프로세스 확인 뒤 정지한다.
