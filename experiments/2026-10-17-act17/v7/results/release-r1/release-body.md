v7 native 접촉(`warp_native_contact_v1`, noslip0)의 실험용 단독 BOX ACT 비교 모델 M/F/S를 보존합니다. 각 모델은 별도 v7 교사240회 중 TRAIN200회에서 10000 update 학습했으며, 자기 RGB·자기 발행 명령·고정 작업 토큰만 입력받습니다.

실제 학습 소스: `e1b7de0f789305e12a3612e7cbf392b8e4ac21ee`. 패키징 소스: `de6170d93433fe340806a0881a45f23b19e6af4e`. 모든 모델은 가중치·설정·정규화·adapter·추론 코드·고정 ACT runtime·라이선스·출처·데이터 manifest를 포함합니다. raw 시연 전체와 optimizer state는 포함하지 않습니다.

VAL8×3 실제 native 평가는 진행 중입니다. 이 Release는 실패 비교 모델을 포함한 보존이며 성공 모델/기본 제어기라는 뜻이 아닙니다. 공개 재다운로드·전체 SHA·bundled CPU 로딩 검증은 별도 기록합니다. 기존 고정 ACT 환경의 Python으로 `python inference/load_model.py`를 실행합니다.
