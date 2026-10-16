# warp10 공식 자료 조사 — 2026-10-16

- [설치 버전 Warp 1.15 concurrency](https://nvidia.github.io/warp/v1.15/deep_dive/concurrency.html): pinned CPU 메모리의 비동기 wp.copy, 같은 stream의 실행 순서, event 완료 후 NumPy view 읽기를 적용했다. 매 틱 할당·세계별 반복 전송·카메라별 host wait를 줄이는 표준 방식이다. 문서 원문을 references/에 보존했다.
- [MJWarp upstream io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py): gcp4 설치 get_data_into 원문을 직접 읽었다. 원래 contact/efc 정렬·평가 결과·mj_factorM은 유지하며, 명시된 .numpy() 필드만 batch당 한 번 staged copy한다. 평가 export는 actor/명령 입력과 분리한다. 최신 main 조회도 했으나 설치 API로 간주하지 않았다.
- [warp9 조사](../2026-10-16-warp9/references.md)의 NoSlip·dt·solver·FOV·해상도·기록주기는 그대로다. CPU 영상 합성은 기존 float64 식과 픽셀별 연산 순서를 유지하고 투명층의 소비되는 픽셀만 변환한다.

새 물리 허용오차·성공상수는 없다. 0.3 SIM초·N1/4/16/64는 요청한 고정 작업이다. 실행당 환산 속도는 조정자 결정(사용자 미확인)이고 >3.5 경고/>6.0 차단은 기존 수치다. 비물리 바이트 동등성과 실제 GPU 동일 상태 감사·실제 임무 결과는 구분한다.

## CPU 제어 분리 후보

[Python3.12 multiprocessing](https://docs.python.org/3.12/library/multiprocessing.html)와 [Gymnasium AsyncVectorEnv](https://gymnasium.farama.org/api/vector/async_vector_env/)의 독립 프로세스/메시지 경계를 읽었다. spawn으로 CUDA·네이티브 객체를 상속/전송하지 않고, 각 세계의 기존 교사 generator와 자기 명령 이력을 독립적으로 둔다. 동일 장면/native 초기 qpos/clock 해시가 맞아야 시작한다. 현재 upstream 평가 export가 실제 쓴 필드의 CPU mirror만 복사하며 새로운 제어 측정을 추가하지 않는다. 교사의 기존 InputAudit·RGB 경계는 유지한다.

이 로컬 g2-standard-16 CPU 분리는 조정자 설계(사용자 미확인)다. 우선 이미 할당한16코어를 쓰며 n4 추가 호스트 분리는 이 방법으로도 부족할 때 남긴다. GPU 물리·모델·dt·NoSlip/solver는 부모 소유자에만 둔다. CPU 작업자의 모델 만들기/native reset은 기존 setup이며 이후 물리·렌더 함수는 차단한다. 완료된 N64 고정 작업은 pooloff R2 결과이며 CPU pool은 N16 이하 별도 조건이다.
