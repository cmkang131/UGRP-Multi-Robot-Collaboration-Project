# 12차 독립 검증과 증거 경계

| 대상 | 직접 확인 | 결론과 한계 |
|---|---|---|
| 실제 ranked relook | 독립 재실행 JSON 동일,31개 Git source hash, 실제 ranker·controller·guard·endpoint·port; small/large 및 두 counterfactual | source 조건에서 upstream target과 port 발행 setpoint 불일치. 실제 no-fix 원인·물리 위치는 미측정. port tick 위상은 각 fixture의 명시 조건에 한정 |
| worker 초기화 | 별도 평가 담당이 final ENOMEM fixture 전체 결과 재실행,5개 직접 실행 source hash와 추가 caller 대조, 정상/ready-timeout/Popen 실패 | 반환 전 ownership gap과0POST host retry의 연결. fake worker이며 실제 OS/GPU 잔류량·빈도는 미측정 |
| command/model 해석 |8개 Git blob·SHA와 source 범위 독립 대조; smoothstep 산술 | source에 기반한 camera 조건값 해석. 실제 observer/PF 오차 실험 아님 |
| covariance helper |11개 Git source/config hash, 실제 wall3query의 exact 함수 실행과 golden 동일 | world frame·cap·clamp 및 fallback 경계. 새로운 collision/확률 보장 아님 |

Worker golden SHA256 `2015acc52df6c106ca18e9e08115fb0e68d67cf0681faee7e9456e0beab66441`, 초기 full-sequence golden `54001a892edf4110a0ac9fe9890e4a14977dae1850728329842d5333667820d4`, covariance golden `bf0a9f81c5c75c55ba2bffe9b1c2dc5d5334b8f8752799ccdfca1004ba64bf76`을 고정했다. 상세 독립 memo와 source manifest는 Mac의 round12/evidence에 있다.

worker 재현은 read-only Git CLI subprocess를 쓰지만 실제 worker/Popen·selector는 대역이다. 제어 재현의 RobotSpy는 command만 받으며 measured state를 제공하지 않는다. 공개 static map과 승인된 calibration 제품을 읽었으며 raw 이미지/trajectory/heldout outcome을 분석하지 않았다. 과거 검색의 부수적 fixture 출처 한 줄은 분석에서 제외했다.

GitHub에는 Markdown만 추가한다. Mac의 작은 script/result는 기존 결과를 덮어쓰지 않고 임시 출력으로 재현할 수 있다. source에서 읽는 부분, AST 그대로 실행하는 부분, collaborator 대역을 각 fixture에 명시했다. 전체 프로젝트 CI나 실물 동작 검증을 대신하지 않는다. 원래13개 manuscript와 이전1–11차 본문은 수정하지 않았다.

Host-phase 후속은 원본 advance_to/.002와39개 Git hash를 검증했다. rounded clock의 capture3.4s/issued1470, plain float/backend.now의≈3.6s/issued1470을 구별한다. 두 경우 모두 upstream1230/빈 queue의 불일치를 유지하며 clock-only이므로 실측 joint/physics 결과가 아니다. host-phase golden `0738da81b0b7d2eda47817ce3d754882e816e5bf88a7b5728333aad89efa4a0a`, float control golden `53dce90bc218185381ff9ad28dcd095bc5886cb6693d9f5d500378d09bdd2580`을 추가 보존했다.
