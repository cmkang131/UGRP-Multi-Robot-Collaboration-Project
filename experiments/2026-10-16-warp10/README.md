# warp10 — 호스트 readback·렌더·제어 처리량 후보

PR #550 DRAFT, claude/warp5, warp9 후속. **NOT_READY — CPU 접촉 export 동일 결함 3회 후 신규 배치 중단, gcp4 TERMINATED.**

## 결정의 출처

이번 속도 기준·새 결함 묶음·토글 설계·머신 변경은 **조정자 결정/해석, 사용자 미확인**으로 기록한다. 사용자 직접 결정은 “GCP에서 비싼 거나 좋은 거 써서 시뮬레이션 더 빠르게”이며 이번 요청이 gcp4 변경·측정을 지시했다. 실행당 환산=배치 wall/(SIM초×세계 수)에 기존 >6.0 차단을 적용하고 배치 값도 병기한다. 3.5 경고·6.0 차단은 기존 기준의 승계이며 새로운 물리 수용 상수가 아니다.

## 범위

- gcp4 `ugrp-sim-d-1016/ugrp-act-l4-gcp4`, 정지 상태 g2-standard-8 → g2-standard-16(L4 1, 64GB). 이전 머신 결과와 합산하지 않는다. 같은 새 머신에서 N1·4·16·64 ×0.3 SIM초 수정 전/후를 측정한다.
- NoSlip·dt·solver 불변, warp9 scratch/fullgraph off. 호스트 readback/렌더/명령 처리만 기본 off 토글. 정답은 평가 export에 한정하며 제어 입력을 늘리지 않는다.
- 유휴20분·budget-stop 유지, 실행 상한 없음. gcp2 L4와 gcp3는 변경하지 않는다. 모델 키·에이전트 자격증명은 VM에 보내지 않는다.
- Mac 물리·렌더·GUI 0. 요약·몽타주·선택 실패 프레임만 회수, 원본·분석은 GCP.

[수정 전 사유 분포와 관문표](pre-fix-rejection-table.json)를 먼저 만들었다. 타이밍 구간은 중첩되므로 단순 합산하지 않는다. 이전 처리량/상태 불일치로 임무 실패 원인을 새로 주장하지 않는다.

## 최종 결과와 남은 문제

같은 g2-standard-16에서 N1/4/16/64×0.3SIM 전후 계측을 완료했다. 아래는 setup을 뺀 계측 wall이며 첫30 관문 값이 아니다.

|N|수정 전 wall초|수정 후 wall초|실행당 환산 전→후|wall 감소|
|---:|---:|---:|---:|---:|
|1|7.4663|7.0459|24.8876→23.4863|5.6%|
|4|10.5700|9.5545|8.8083→7.9621|9.6%|
|16|24.8193|18.8458|5.1707→3.9262|24.1%|
|64|86.2115|49.4642|4.4902→2.5763|42.6%|

[짧은 요약 JSON](summary.json), [모든14구성 계측·오류](final-record/timing-table.md), [구성 funnel](final-record/rejection-table.json), [세계·프레임·이벤트 funnel](gate-funnel.json). N64는 약60.4GiB sampled VmHWM으로 메모리 여유가 작았으며 장시간 임무 자격이 아니다. 이전 g2-standard-8과 합산하지 않는다.

- 혼합N16 직렬 진단은10.1SIM에 감독 중단했다. 이어 CPU spawn 세 시도는11.5/11.6/11.5SIM 접촉 export 오류로 HOST_ERROR다. 세 번째의 마지막 완료 tick은11.4이며 다음11.5 export에서 차단됐다. **첫30은 모두 미완료이므로 정식 속도 PASS/FAIL을 내지 않는다.** 부분 평균5.6–5.7을 관문 통과로 쓰지 않는다.
- 세 번째 원본 덤프에서 활성 GPU staging geom ID는 범위 위반0, CPU 출력은20행 모두 다르고2개 값이 모델 범위 밖이었다([오프라인 재현·해시](staging-cpu-forensics.json)). CPU export 경로(원래 함수·어댑터·native 바인딩)의 정확한 첫 덮어쓰기 지점은 미확정이다. 수신기/부모 arena reset 모두 해결하지 못했다. 새 물리 배치는 멈췄고 모든 후보는 기본off·미채택이다. 초기 동일 상태 export byte parity는 이후 접촉의 의미적 정확성을 보장하지 않는다. 이 시도의 접촉 기반 채점은 자격 미달이다.
- 운반·place·완주, held 이동 입력 감사, live CoreWeave fp4/Mac 중계·ACT 학생은 미검증/미연결이며 모델 호출0이다. 로컬16코어 spawn을 먼저 시험했고 추가 n4 제어 분리는 미구현이다. 이 정확성 결함이 해소되기 전에는 더 진행하지 않았다. 기존 수작업 근거리 코드를 학생으로 보고하지 않는다.
- Mac 비물리26 passed, CI 보고 결과 없음. 별도 GPU 실행의 최종 qpos/qvel/warmstart는 비트 불일치여서 결정성·물리 동등성을 주장하지 않는다.
- 원본19,084파일을 gcp2에서 SHA 불일치0으로 검증했다. Mac에는 요약·몽타주·선택 실패 띠만 회수했다. gcp4는 임대/관련 실행/GPU 프로세스0 확인 뒤 TERMINATED([정지 전 검사](final-stop-check.json), [최종 상태](gcp4-final.json)). 유휴20분·budget-stop·원본 디스크는 보존했다. gcp2의 다른 임대는 그대로 두었고 그 VM·다른 L4·gcp3를 정지/변경하지 않았다.

이하 항목은 실행 당시의 중간 기록이다. 위 최종 판정이 우선한다.

## 중간 검증 — 완료 수치만

- g2-standard-16 수정 전 N1/4/16/64 모두 0.3 SIM초 완료: wall 7.4663/10.5700/24.8193/86.2115초. 실행당 환산 24.8876/8.8083/5.1707/4.4902. setup은 제외했다. N64 VmHWM 기록 최고 47,941,464 KiB(약45.7GiB), 이전32GB 머신 결과와 합산하지 않는다.
- R1 `5333afaad339446a63697409ad1f86482a4e320b`: N1 초기 동일 상태 감사에서 HOST_ERROR. RGB는 정확 일치했으며, 차이는 ordinary integrator가 내보내지 않는 EFM 작업공간11개였다. `MjData.__copy__`의 미사용 작업공간까지 비교한 감사 결함이다. [원본 차이·사유 분포](r1-failure.json).
- R2 `55e6a64c5e87901aab911529b5064e661dac33f9`: 실행된 upstream 대입/C 출력의 manifest만 비교한다. 허용 오차나 이름별 예외 목록을 새로 넣지 않았다. N1은116 배열이 정확 일치했고 N4/N16도 고정 작업을 완료했다. N16 wall18.8458초(24.1% 감소), 배치62.8194·실행당3.9262. 초기 동일 GPU 상태의 RGB/평가 export 감사이며 별도 실행 최종 상태의 결정성을 주장하지 않는다.
- N16 카메라 완료 대기90→3회(틱당1회), 평가 D2H189.09→13.47MB. 전체 렌더 이미지 D2H는7.741→7.225GB로 남아 있다. pinned copy의 submit 시간과 완료 wait를 합쳐 해석해야 하며 0.003초 submit을 실제 전송 완료 시간으로 쓰지 않는다. 렌더 알파 합성은 CPU float64로 유지한다.
- 명령 배열은 로봇/세계 축만 묶고 physics tick 누적 순서는 유지한다. Mac 순수 NumPy N64×3로봇400틱 ABBA에서 0.054–0.055→0.023–0.024초, 전체 tape SHA 일치. 이는 원격 물리/E2E 가속 배율이 아니다.
- 첫30은 별도의 무계측 N16 교사 운반 진단으로 준비했다(6초기 상태+명시적 반복10, 미채택 reloc21 progress 모두off). CoreWeave live E2E/ACT는 [정적 연결 점검](e2e-preflight.json)의 미완료 조건으로 남는다. 이 교사 진단을 LLM/ACT E2E로 대체 보고하지 않는다.
- 이전 warp9 R2/R3 자기 영상 띠를 파일로 직접 다시 봤다: 1.7–1.9SIM초 세 장에서 바닥/벽 시야가 거의 그대로이며 운반 구간이 아니다. 성공 비교·전체10초 tail은 없으므로 이동 실패 원인을 이 영상으로 주장하지 않았다.

## CPU 제어 분리 후속 — 당시 기록

R2 N64도 wall49.4642초(86.2115초 대비42.6% 감소), 실행당2.5763으로 완료했다. [전후 전체 표](fixed-record/timing-table.md)·[상태 비교 한계](state-comparison.json). 초기 qpos/clock과 실제 물리 설정은 모두 같고 issued ctrl도 정확 일치했으나 별도 실행의 qpos/qvel/warmstart는 비트 불일치다. 같은 GPU 상태의 export/RGB 정확 일치를 물리 궤적 결정성으로 확대하지 않는다. R2 N64의 sampled VmHWM은63,314,988KiB(약60.4GiB)로64GB 호스트에서 여유가 적어, 장시간 N64 임무를 검증했다고 주장하지 않는다.

혼합6초기 상태+반복10의 직렬 첫30 진단은10.1SIM초에서 의도적으로 멈췄다. 부분 관측 중앙값약7.84, wall1183.66초이며 첫30 관문은 **미완료**다. 원본 HOST_ERROR/KeyboardInterrupt/GeneratorExit는 그대로 남기고 감독 중단 근거를 별도 보존한다. 이 값으로 첫30 PASS/FAIL을 만들지 않는다.

새 기본off `warp10_control_pool_v1`은 g2-standard-16의 기존16코어를 먼저 쓰는 조정자 설계(사용자 미확인)다. 각 CPU 프로세스가 같은 교사 코드를 실행하고 부모만 GPU 물리·렌더·평가 export를 소유한다. 기존 export가 쓴 CPU 평가 mirror·자기 명령 상태·기존 JPEG만 복사하고 새로운 행동 측정은 넣지 않는다. 입력 Audit는 원래 교사 그대로이며 학생/E2E가 아니다. CPU 작업자의 native reset 뒤 물리/렌더를 차단하고, 초기 모델/qpos/clock·첫 snapshot·첫 issued command를 대조한다. worker당OpenCV1스레드는 할당한 CPU1개에 맞춘 자원 설정이다. n4의 추가 호스트 분리는 이 로컬 분리로도 부족할 때의 미완료 경로다.


## CPU mirror 오류와 재검증

로컬 spawn 첫 시도(`5894d2d8d`)는11.5SIM초에서 worker7의 평가 접촉 geom 인덱스가1072693248로 깨져 HOST_ERROR였다. [원본 오류·분포](pool-failure.json). 초기 검증만 했던 mirror를 매 틱 바이트 검사로 강화했다. 수신기 MjData 객체는 유지하고 `mj_resetData` 뒤 native contact/constraint/island 영역을 다시 할당하여 기존 arena 포인터 재사용을 피한다. GPU 상태·물리·NoSlip 설정에는 적용되지 않는다. 단순히 잘못된 contact를 버리거나 허용 오차를 늘리지 않는다. 이는 **원인 확정이 아닌 격리 수정**이다: 동적 할당의 작은 비물리24회 검사에서는 [이전본](native-mirror-before.json)과 [수정본](native-mirror-check.json)이 모두 통과했다. 실제 운전으로 확인해야 한다.

`14aec45a14294703827625107014841b3f32feb4`로 같은 혼합N16 첫30을 재실행 중이다. 매 틱 mirror를 검사하며, 완료 전에는 첫30·임무 관문을 통과로 기록하지 않는다. Mac 비물리25 passed. 실패 원본4,090파일을 gcp2에 전달해 SHA 불일치0을 확인했고, 자기 영상2Hz 전체와 마지막10초10Hz 띠를 직접 읽었다([타임라인·검토 범위](playback-review-pool-r1.json)). worker7의 빨간 상자는 절대SIM10.6에 화면 밖으로 나가며 이후13.2까지 바닥뿐이다. 메모리 오류를 이 영상의 물리적 결과로 추정하지 않는다. 같은 조건의 완주 성공 영상은 없다.


수신기 초기화만 넣은 두 번째 시도(`14aec45a1`)도11.6SIM초 worker1에서 같은 인덱스로 HOST_ERROR였다. 매 틱 mirror exact였으므로 수신 복사만의 오류라는 가설은 지지되지 않았다([두 번째 오류](pool-r2-failure.json)). [부모 수정 전 사유 분포](pre-parent-fix-rejection-table.json)를 남긴 뒤, 기본off `warp10_eval_arena_reset_v1`으로 **부모의 평가 CPU arena도 export 직전에 초기화**하는 세 번째/마지막 동일 결함 시도를 준비했다. GPU 적분 상태는 그대로다. 실제 model.ngeom 범위를 벗어난 contact는 dispatch 전에 중단하고 원래 GPU staging 입력+CPU contact 출력 NPZ를 GCP에 보존한다. 잘못된 접촉을 제거해 계속 돌리지 않는다. 이 수정도 원인 확정이 아닌 arena 재사용 격리다. 원래 장면의 native forward 후 소규모 할당 검사(적분0/GPU0)는 전후 모두 통과하여 단독 재현에는 실패했다([검사](parent-arena-native-check.json)); 초기 자산 상대 경로 로딩 실패2회는 시뮬레이션 시도가 아니다. 같은 오류가 세 번째 반복되면 추가 실행 없이 보고한다.


## 세 번째 종료와 오프라인 국소화

최종 실행 소스는 `41584d3a114b820fd7b3939e558bc7e969f990a6`이다. 부모 contact 범위 검사가 작업자 dispatch 전에 중단했고, 전 세계 작업자의 성공 응답115틱×16=1,840회는 mirror exact였다. [세 번째 trace·입력감사](pool-r3-prefix-summary.json). 기록된 네 motion prefix를 합쳐 세계 시도64개, trace/RGB SHA/명령7,200개씩이다. close 단계 노출18세계 시도, lift 이후0이며 독립 완주 시행 수는0이다. 입력 Audit의0은 실행된 경로만의 값이다.

[세 번째 개요+r1+r2 4배속](figures/pool-r3-red-approach-4x.mp4)(18,685bytes, SHA256 `c8ec79b14ee37ee882435f467d46c9cef1be0e7321fd07978ac73a3ffb72f3fe`), [2Hz 전체/마지막10초10Hz 직접 검토](playback-review-pool-r3.json). 자기 영상에서 빨간 상자는 절대SIM10.6–10.7에 화면 밖으로 나갔고 이후13.1까지 바닥이 보인다. 완료 성공 비교 영상은 없으며, 영상으로 메모리 원인을 단정하지 않는다. 원래 GPU staging과 CPU 출력 NPZ는 gcp2 원본 경로에만 보존했다. 후속은 이 덤프를 동일 MuJoCo3.16 ABI의 export에 넣어 첫 잘못된 쓰기/뷰를 분리하는 CPU 재현이며, 이번 라운드에서 네 번째 배치는 내지 않았다.
