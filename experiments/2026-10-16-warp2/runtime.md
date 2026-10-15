# gcp2 유한 실행 기록

**R3 진행 중, NOT_READY / HOLD_SCENE.** 아래는 서로 다른 모집단이며 합산하지 않는다. 후보는 기본 off이고 학습·LLM 호출·새 관문 제출은 0이다.

|모집단|검증 결과|배치 wall초|합계 SIM초|SIM초/wall초|추정 SIM초/$|
|---|---|---:|---:|---:|---:|
|C, n4, 여섯 시드 반복 N16|16/16 성공, 고유 시드6, 기존 명령 byte16/16 동일|200.053|671.7|3.358|3842.88|
|C, n4, seed8318631 반복 N16|16/16 성공, 고유 시드1, 기존 명령 byte16/16 동일|105.050|446.4|4.249|4863.56|
|C, n4, 같은 시드 1SIM초 prefix N16|cap_end16, 원본 명령 prefix16/16 동일|10.049|16|1.592|1822.38|
|MJWarp R1 N1 seed8318726|감독 중단/HOST_ERROR1, 물리 실패 판정 아님|미완료|비교 제외|미완료|미완료|
|MJWarp R2 N1 seed8318631|1/1 성공, input audit invisible0·held_world_reads0|약2770|27.7|약0.010|약32.84|
|MJWarp 여섯 정확한 모델 묶음 초기화 N16|초기화 통과, 교사 rollout0|성공 trial 아님|성공 trial 아님|해당 없음|해당 없음|
|MJWarp R3 N16/64/256 1SIM초 prefix + 혼합6 N16|진행 중|미완료|미완료|미완료|미완료|

C3.12와 MJWarp(C3.16·Warp1.15)는 host·backend·source SHA가 다르다. 반복 시드를 독립 관문 성공 횟수로 해석하지 않는다. C의 합계 wall은 16 프로세스 coordinator의 초기화/기록 포함 실측이다. GPU 완료 job의 시간은 coordinator 시작부터 종료까지로 정리하고, R2처럼 완료 직후 coordinator가 취소된 경우 최종 summary가 저장된 시각까지의 시간을 명시한다.

가격은 L4 $1.096/h, n4 $3.1454/h의 **기존 미검증 지역 추정값**이며 청구 내역이 아니다. 공유 VM의 다른 작업·캐시·GPU 메모리도 admission/resource 원장에 있다. 단독 GPU 성능이나 증분 비용을 측정했다고 주장하지 않는다. 1 SIM초 prefix는 물리4000 step·control10 tick이며 초기화가 지배할 수 있다. 장기 정상 상태/전체 집기 효율은 별도 전체 교사 결과로 판단한다.

초기 생성자는 C에서 1.3 SIM초를 진행한다. GPU warmup은 저장한 초기 통합 상태로 복원한 뒤 rollout을 시작한다. 초기화 전용 export의 rollout0은 생성자 물리0을 의미하지 않는다. R3는 C3.12의 actuator/geometry 자산 여섯 벌을 각 정확한 XML에 적용하며, 크기·질량·`dof_length`를 강제로 일치시키지 않는다.

기록: [CPU 혼합](runtime/cpu-mixed6-analysis.json), [CPU 동일 시드](runtime/cpu-seed8318631-analysis.json), [CPU prefix](runtime/cpu-prefix1-analysis.json), [GPU N1](runtime/gpu-r2-n1-summary.json). 원본은 각 파일의 gcp2 절대 경로에 보존한다. 가져온 것은 분석 JSON·몽타주·8MB 이하 검토 영상이며 원시 상태/학습 RGB 전체를 Mac에 가져오지 않았다.
