# egomap48 — 최종 graph 오프라인 성능 (실행 전 등록)

2026-10-08 사용자 지시. 기준21582623, PR405 DRAFT. 물리·렌더·모델 호출0.
egomap47 seed47001의 봉인된 own frontend-ledger/poses로 마지막 graph를 계산한다.
원본 `/Users/changmin/projects/ugrp/outputs/navfn-start-recovery-v1/new-seed`는 수정하지 않는다.
새 raw `/Users/changmin/projects/ugrp/outputs/graph-runtime-v1`; GT는 최종 계산 봉인 후 채점만.

순서: 문서/드라이버 커밋→배타 timing 잠금→기존 최종 graph cProfile1회(30분 상한 제거,
유한한204스캔 입력1회만)→상위 병목과 표준 원문 확인→기본off 옵션 구현·시험→고정 on/off 시간/동일성.
프로파일에는 후보수/정합/field 생성/최적화·LSMR/중복 계산과 노드·엣지·nfev를 기록한다.
이미 Jacobian sparsity+LSMR를 쓰므로 단순히 새 희소 solver를 추가했다고 주장하지 않는다.
결과 동일성 우선: 출력 전체 JSON 직렬화 SHA 비교, 지도·pose·constraint 최대차도 기록.
byte 동일 실패 시 pose≤1e-12·map log-odds≤1e-12/셀집합 완전 동일을 보조 수치 기준으로 보고하고
byte 동일이라 부르지 않는다. 이를 넘으면 가속 미채택. 정합/판정 문턱 변경0.

최종 graph는 egomap46 B와 별도 표: **덮음≥80% AND 영역P≥63.6%** 그대로,
R/RMSE·전체칸·관측영역 칸/벽표본 분모 포함. 새 실행/확증 아님, 동일 녹화 사후 계산.
egomap47 HOST_ERROR를 소급 완료로 바꾸지 않는다. 누락된 마지막 GT1개는 평가 제외를 명시.
360초 예상 wall/SIM은 측정 구간·외삽 가정과 graph/frame 중복 계산 차감을 명시한다.
프레임1.52배를 실제 물리 전체에 무조건 곱하지 않는다. raw 예산512MiB, ENOSPC=HOST_ERROR.
기존 가속도 포함하는 조건은 별도 표기. 새 의존성/venv0. 바뀐 모듈 시험만, 초록 후 커밋/push.
단계 사이 supervisor 확인, 잠금 점유 시 대기, 다른 프로세스/브랜치 수정0. TensorBoard 생략 유지.
