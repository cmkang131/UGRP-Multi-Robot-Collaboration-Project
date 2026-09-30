# 분류기 v2 봉인 입력 계약 (초안)

이 문서는 평가 입력 계약이다. 실행·봉인 승인이 아니며 실제 봉인 파일을 만들지 않았다. 제어기/러너를 바꾸지 않았다. 기존 러너에는 아래 전체 범위 메타데이터가 없으므로 과거 raw를 확증 입력으로 승격할 수 없다. 후속 실행 기록 어댑터가 이를 기록하고 독립 검토에서 확인해야 한다.

`classify_placements.py --sealed-manifest <파일> --sealed-manifest-sha256 <독립적으로 고정한 해시>`로 기존 조정자 소유 봉인 파일을 읽는다. 옵션을 생략하면 `historical_endpoints`이며 어떤 60개 입력도 확증 PASS를 내지 않는다. 파일 해시를 보고 그 자리에서 선택하는 것은 사전 고정의 대체가 아니다.

봉인 JSON의 필수 구조:

- `schema="ugrp.v6h_confirmatory.v1"`, `state="sealed"`, `primary_seed=941`, `secondary_seed=943`.
- `evaluation_protocol`: `classify_placements.EVALUATION_PROTOCOL`과 정확히 같은 정의(teacher 포함, 종료 정리까지, trace 공백 .051 s, PF 나이 .30 s, 주 σ 시드 941, 최종 목적지 내려놓기 제외, L0 handover/재파지 및 L1 첫 wait_lower). 이 정의도 manifest의 독립 고정 해시에 묶인다.
- `execution_identity`: `source_sha`(40자리), `policy_id`, `bundle_id`, `source_files_sha256`(실행 파일 전체의 경로→SHA-256). 정책·번들·지도·센서·물리·환경 구성도 실행 계획/파일 해시로 고정한다. runtime manifest의 실제 `source.execution_tree.files` 목록이 이 전체 목록과 같아야 한다. 이름만 맞는 `execution_identity` 선언으로 대체하지 않는다.
- `placements_file`, `placements_sha256`: C01…C60 순서의 JSON 목록. 각 항목 `name,x,y,yaw_deg,prior,sheet="coarse"`. 기존 DRAFT 파일을 이번 수정에서 다시 추첨하지 않았다.
- `plan_file`, `plan_sha256`: JSON `{execution_identity, cases}`. `cases`는 정확한 72개 원본 계획이며 각 case에 `case_id,cell,seed,stage,beam_xyyaw,prior,prior_id,coarse_order_sheet,policy_id,bundle_id,source_sha,chain_stop_leg=1`와 실행에 쓰는 전체 설정을 둔다. 빔 좌표는 배치 x/y 및 yaw 라디안과 같아야 한다. `prior_id`는 배치의 prior 이름과 같고 `prior`는 r1/r2 실제 사전분포다.
- `cases`: C01…C60×941 + C01…C12×943에 정확히 대응하는 72개 항목. 각 항목은 `placement,seed,placement_sha256,prior_sha256,attempts`다. 내용 해시는 `json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)`의 UTF-8 SHA-256이고 파일 해시와 구별한다.
- `attempts`: 원본 1개 + 미리 정한 HOST_ERROR 재시도 최대 1개. 각 항목 `case_id,case_sha256,replaces`이며 원본은 `replaces=null`, 재시도는 원본 case id다. `case_sha256`은 실제 `case.json` 바이트 해시다. 재시도 case는 id 외 전체 설정이 원본과 같아야 한다. **선택 시도를 봉인에 사후 기록하지 않는다**(`selected_attempt` 거부). 실제 결과에서 원본 HOST_ERROR일 때만 재시도를 선택하고, 미실행 허용 재시도는 누락으로 세지 않는다. 재시도 없는 HOST_ERROR/재시도 HOST_ERROR는 미분류로 남는다. controller 실패는 재시도하지 않는다. 실제 원본 72건은 모두 필요하며 중복/미등록 추가 케이스를 거부한다.

runtime `manifest.json`은 `state=completed`, `source_changed=false`, 고정 실행 SHA와 위 identity/실제 파일 목록이 같아야 한다. 각 `result.json`의 `execution_identity`와 `row`도 위 identity/`cases.jsonl` 행과 일치해야 한다. 원본/재시도 `case.json`의 해시와 전체 설정을 계획과 대조한다. 결과/trace/입력 파일 해시는 계산 후 다시 읽어 안정성을 확인한다.

일반 케이스 증거:

- leg `recorded`는 bool. 도달한 leg의 start/end/lift/tilt/end_error/leg_error는 유한·유효 범위, 집게는 정확히 r1/r2 각 2개 bool. L0 끝 < L1 시작 < L1 끝. 미도달 leg는 도달 증거로 취급하지 않는다.
- trace는 엄격 증가, 최대 간격 0.051 SIM s. 전체 수집 시작(teacher 준비 포함)→실제 종료 정리까지 덮는다. 모든 행의 t/tilt/lift와 집게를 검사한다. `result.evaluation_coverage={start_sim_s,end_sim_s,trace_count}` 필수. 마지막 시각은 end에서 0.051 s 이내이며 end는 `termination.sim_s`와 같다. 행 수가 실제 trace와 일치해야 한다.
- `result.wall_contact.coverage={start_sim_s,end_sim_s,sample_period_s,max_gap_s,sample_count}` 필수. 같은 전체 창을 덮고 주기는 양수 ≤0.051 s, 최대 공백 ≤주기, 표본 수 ≥floor(창 길이/주기). 접촉 에피소드가 없어도 이 추적 범위 증거가 필요하다. 기존 `wall_contact.steps`는 **접촉한 step 수**이므로 전체 추적 표본 수로 쓰지 않는다.
- L0 끝→L1 시작 사이 동시 바닥 놓기(lift≤5 mm, tilt≤3°)·네 집게 개방 표본, L1 시작 전 ≤0.051 s의 들림≥3 cm·네 집게 접촉 표본, restaging_between_legs=false를 검사한다. 최종 목적지 `chain.setdown.reached=false`는 별도 범위라 이 증거의 대체가 아니다.
- 완료 L1은 stage stop=L1 끝(허용오차 1e-6 s), 두 로봇 first wait_lower 종료, `termination.outcome=STUDY_LAYER_DONE`. 정리 중 추가 trace도 하드 검사에 포함한다. 실제 controller/guard/timeout 실패는 좋은 끝점 수치가 있어도 PASS를 막고 null 실패 항목은 실패가 아니다.

주 기준 B는 941의 r1/r2×L0/L1, 최대 PF 나이 0.30 s, 같은 행의 정답, yaw wrap, 양의 정부호 공분산으로 계산한다. 누락 후 도달과 미도달을 구분한다. 로봇 표본 포함률≥90%·평균 z²≤1.3의 6개 AND이며 보조 943은 별도다. 72건 전부 안전 거부를 적용한다. `criterion`(A+안전), `sigma_criterion_B`, `full_verdict`를 별개로 출력한다. 양성 시험은 합성 기록이고 실제 완주/접촉 추적 성능/새 봉인 호환 실행 검증은 아니다.
