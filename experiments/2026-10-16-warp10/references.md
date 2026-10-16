# warp10 공식 자료 조사 — 2026-10-16

- [설치 버전 Warp 1.15 concurrency](https://nvidia.github.io/warp/v1.15/deep_dive/concurrency.html): pinned CPU 메모리의 비동기 wp.copy, 같은 stream의 실행 순서, event 완료 후 NumPy view 읽기를 적용했다. 매 틱 할당·세계별 반복 전송·카메라별 host wait를 줄이는 표준 방식이다. 문서 원문을 references/에 보존했다.
- [MJWarp upstream io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py): gcp4 설치 get_data_into 원문을 직접 읽었다. 원래 contact/efc 정렬·평가 결과·mj_factorM은 유지하며, 명시된 .numpy() 필드만 batch당 한 번 staged copy한다. 평가 export는 actor/명령 입력과 분리한다. 최신 main 조회도 했으나 설치 API로 간주하지 않았다.
- [warp9 조사](../2026-10-16-warp9/references.md)의 NoSlip·dt·solver·FOV·해상도·기록주기는 그대로다. CPU 영상 합성은 기존 float64 식과 픽셀별 연산 순서를 유지하고 투명층의 소비되는 픽셀만 변환한다.

새 물리 허용오차·성공상수는 없다. 0.3 SIM초·N1/4/16/64는 요청한 고정 작업이다. 실행당 환산 속도는 조정자 결정(사용자 미확인)이고 >3.5 경고/>6.0 차단은 기존 수치다. 비물리 바이트 동등성과 실제 GPU 동일 상태 감사·실제 임무 결과는 구분한다.
