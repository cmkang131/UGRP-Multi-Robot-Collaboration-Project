# 실제 색 띠 인식 재생 — v430/v431, 기본 off
ARM 원본 청록30·파랑30·음성30장(재인코딩 없음), 원본 경로·SHA는 labels.json.
라벨/상자는 Codex 직접 시각 검토 초안이며 사람 확인 전이다(label-review-0…4.jpg).
기존 파지용 검출 청록14/30·파랑7/30 → v431 19/30·13/30, 오검출0/30.
새 띠 존재 검출은30/30·30/30, 오검출0/30; 파지 위치 채택과 다른 지표다.
12cm 몸체 지지 조건·청록 H 상한·원거리 축 corridor 탈락을 분리했다(diagnosis.md).
90장에 맞춘 DEV 회귀이며 독립 holdout/실물/단계 성공 증거가 아니다.
관련3파일18시험 통과, VM 시작0·새 단계0/12; 사람 라벨 확인이 남았다.
재생: python -m scripts.evaluate_e2e_color_detector --output outputs/color-replay.json.zst
