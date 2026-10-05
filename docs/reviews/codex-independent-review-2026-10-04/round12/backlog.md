# 12차 이후 검토 상태

| 항목 | 상태 | 다음에 결론을 바꿀 증거 |
|---|---|---|
| 실제 ranked relook의 command 완료 불일치 | 현재 source의 조건부 결함; 원본 sequence·guard·port와 독립 대조 | 명시적 abort 취소를 보존하는 수정 뒤 같은 sequence와 host phase 대조 |
| worker 반환 전 초기화 cleanup | 현재 source의 조건부 P2; 독립 재현 완료 | 부분 초기화 모든 생성 경계의 유한한 회수 또는 명시적 cleanup failure |
| view command와 camera 모델 연결 | source 해석 완료, physical/model error 미측정 | 허용 frame·명령 기록에서 capture 당시 사용한 command 계층/시각의 일치 |
| look-around covariance frame·cap | 현재 source 부정 대조; 새 버그 없음 | production source 변경 또는 지원 입력에서의 구체 반례 |
| #371 image SIM/최종 failure 분류 | 8차 확인 항목; a009 영향 경로 유지 | 구현 수정과 오류/정상 control에서 accounting 및 status 일치 |
| 현재 공개 SELF/POSE_UNCERTAIN 원인 | 공개 보고와 source fault tree까지만 확인 | 같은 시행의 허용 기록으로 command·frame·scan·fix·gate 단계 연결 |
| 새 main 및 calibration/registry 변경 | 다음 좁은 delta 검토 대상 | 정확 head/변경 경로와 실제 admission→consumer 연결 |

완료한 음성 대조를 반복하거나 같은 원인을 새 버그로 다시 세지 않는다. 실제 provider 비용/물리/GPU 작업, 신규 실행 조건 변경, raw/heldout 분석 없이 가능한 source·합성 검토를 이어 간다. 다음 유의미한 검증 묶음은 별도 체크포인트에 추가하며 이번 본문은 동결한다.
