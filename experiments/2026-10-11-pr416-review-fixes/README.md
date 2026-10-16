# PR416 독립 검토 수정
- 공통 가드3파일·S2 pulse 소스와 final-pair/highpose 경로는 main과 바이트/해시 동일.
- S3 전용 재검사만 `fail_closed_without_pose=True`; pulse_odometry도 S3 어댑터로 분리.
- S2 slip 시험3파일은 main 원본 복원; v127 admission 복원, v128/129는 기존 main 봉인 차이로 퇴역.
- main·열린 PR 최대 v192/7.85.0 확인 후 v193/7.86.0 등록; 미실행 v190의 5파일 보존.
- 과거 비교는 선택기700건·합성 단계68건(생성 명령3,190개); 전체 물리 궤적 검증 아님.
- 지정 시험·원본 경로·sha256·push/CI 상태는 `summary.json`; 물리·렌더·모델 실행0.
- 방법: [Python 상속](https://docs.python.org/3/tutorial/classes.html#inheritance)과 [명시적 키워드](https://docs.python.org/3/tutorial/controlflow.html#keyword-arguments)로 기존 구현을 재사용. 제어 알고리즘 변경 없음.
