# T13 실물 자료를 시뮬에 되먹이기

## 목적
실측 자료의 출처·단위·fit/holdout을 보존해 새 시뮬 프로필 후보를 만든다. 실물 보정 채택은 **확인 안 됨**.

## 준비물
기존 [보정 자산과 fitter 흐름](../../../calibration/masterpi/README.md), [실측 템플릿](../../../configs/real_measurements_template.json), 로봇별 실측 원자료·해시. 합성/모의 자료는 도구 시험에만 쓰고 실측 출처로 표시하지 않는다.

2026-11-13 정적 자산 감사에서 기존 JSONL 계획행 224/224개의 `measurement_source`가 `null`이었다(chassis 108, servo 60, hand-eye 24, task 32; 제외 0). 정적 측정 5항목도 `null`이므로 완료된 실측 자료로 세지 않는다. 다만 카메라 내부값은 코드에 과거 실측으로 기재되어 있어 저장소 전체를 '실측 전무'라고 단정하지 않는다.

## 병렬 준비와 물리 통합
스키마·단위 검증·변수 대응표·모의 parser 시험은 처음부터 독립 준비한다. 값 채택은 해당 항목의 실측 결과만 필요하다(T01 색, T02 카메라, T03 구동, T04 서보, T05 시선, T06 지연). 모든 카드 종료를 기다리는 통합 마지막 단계가 아니다.

## 실행절차
1. 측정 항목→단위→현재 코드/설정 변수→후보 변수 대응표를 만들고 현재 `validated` 상태를 실제 파일에서 확인한다. 기존 파일을 덮어쓰지 않는다.
2. 로봇·환경·하중별 원본을 해시로 고정하고 fit/holdout을 적합 전에 나눈다. 검증 자료를 재조정에 쓰면 더 이상 holdout이라고 부르지 않는다.
3. 기존 fitter가 현재 모델에도 적용 가능한지 확인하고 쓰기 옵션 없이 적합한다. 구형 [물리 보정 문서](../../masterpi_physics_calibration.md)의 퇴역 명령은 그대로 실행하지 않는다.
4. 별도 기본 off 프로필로 실측 후보를 만들고 원본/후보의 같은 입력·장면 비교를 실행한다. 카메라·물리·명령 버전과 백엔드를 기록한다.
5. 독립 실측 holdout 잔차와 시뮬 동작을 함께 확인한다. 관련 단위 시험만 통과했다고 `validated=true`를 수동 변경하지 않는다.
6. 새 수용 상수는 사양·원본 분포·문헌·담당자 합의 기록을 붙이고 통과 후에만 채택을 제안한다.

## 수치 통과기준
**초안 제안·실물 미검증·담당자 합의 필요:** 채택 후보 항목의 원자료/해시/단위/실측 출처 연결률 100%, fit–holdout 시행 중복 0개, 근거 없는 수용 상수 0개. 각 후보 항목에 독립 holdout 3회 이상과 잔차 분포를 제출한다. 정확도 수용치는 항목별 실측 근거로 사전 합의해야 하며, 그 전에는 자료 준비만 통과하고 모델 채택은 `blocked`다.

## 기준의 근거
연결률·중복 0은 출처와 검증 독립성을 감사하기 위한 요건이다. holdout 3회는 초기 오차 확인용 초안이며 기존 validator의 더 큰 표본 요구를 대체하거나 약화하지 않는다. 옛 V2의 cm/각도 허용치를 최신 hybrid에 자동 승계하지 않는다.

## 시뮬 기준
전진 0.10 s 약 11–12 mm, 회전 약 0.09 rad(0.06–0.095 rad), 10 Hz·펄스 0–0.15 s, RGB 640×480/320×240. 이것들은 비교 출발점이며 실물값을 시뮬에 강제로 맞추는 목표가 아니다. 최신 hybrid main 미포함 상태에서 코드 이관과 SysID 변경을 섞지 않는다.

## PR 결과 상대경로와 형식
`experiments/sim2real-<YYYYMMDD>-T13-<run>/`: [공통 template](../04_tasks.md#result-template), `parameter_mapping.csv`, `fit_report.json`, `comparison.csv`. 대응 CSV: `measurement_key,unit,source_path,source_sha256,current_variable,candidate_variable,profile,criterion_evidence`. 비교 CSV: `trial_id,split,robot_id,parameter,real_value,baseline_value,candidate_value,residual,reason`. 후속 코드 PR의 실제 변경 경로와 rollback 방법을 README에 적는다.

## 막힐 때
[보정 자산](../../../calibration/masterpi/README.md), [실측 프로토콜](../../sim2real_measurement_protocol.md), [실행 버전 관리](../../execution_versioning.md), [보정 시험](../../../tests/test_masterpi_digital_twin_calibration.py). 원본이 없으면 `unavailable`로 남기며 합성값으로 채우지 않는다.
