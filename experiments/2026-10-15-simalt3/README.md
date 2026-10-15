# simalt3 — gcp2 L4 MJWarp 재개

상태: 비용 정지 장치 시험 `gcp2setup: PASS` 대기. VM 생성·시작·물리 실행 0. gcp1/첫 프로젝트는 사용하지 않는다.

[plan.json](plan.json)에 사용자 승인 범위와 3시간 L4 상한, N=1→16→64→128(256 선택), 물리/배치 RGB 분리, 동등성 + SIM초/$ 2배 채택 제안을 고정했다. [rejection_table.json](rejection_table.json)은 실행 전 거부 분포와 순차 관문을 연결한다. 결과는 실행 뒤 갱신한다.

simalt2 인계 범위는 `d93837eb..17b19ae7`의 12개 커밋이다. [inherited-audits.json](inherited-audits.json)에 기존 미추적 감사 3파일의 절대 경로·크기·전체 SHA256·주요 결과를 보존했다. intact 및 unused_efm_v1은 입력 변환만 통과했고, perturbed는 `efm_c` 변환 실패다. 완료된 물리 step은 이 자료에서 입증되지 않는다. 큰 원본 감사 파일은 로컬에 그대로 유지한다.

준비 변경: 기본 OFF인 `--gcp2-v1`로 gcp2 프로젝트·인스턴스·머신·서울 존을 metadata에서 확인한다(자격 증명 endpoint 사용 없음). 기존 simalt2 진단에만 적용하며 교사·평가의 운영 backend 이식은 하지 않는다. 고정 MJWarp의 자동 solver tolerance 보정(1e-8→1e-6)을 원래 장면 값으로 되돌리고 전후를 기록한다. 마찰·접촉·dt·noslip10·질량은 바꾸지 않는다. GPU 물리 실행 시간과 CPU 평가 전송/접촉 집계 시간을 분리한다.

Mac 비물리 검사: `tests/test_simalt_host.py tests/test_simalt_numeric_audit.py tests/test_simalt_pilot.py` 12 passed. Mac 물리·렌더·화면 앱 실행 0. gcp1 사용 금지에 따라 원격 분석·영상 생성도 gcp2에서 수행한다.

참고: [고정 upstream io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py#L433), [derivative.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/derivative.py#L2961), [공식 배치·그래프·overflow 설명](https://mujoco.readthedocs.io/en/latest/mjwarp/). 원문을 직접 내려받아 simalt1 io.py SHA256과 일치함을 확인했다. 조건부 EFM 비활성과 CUDA graph 권장을 재확인했으며, solver 반복/접촉 옵션을 줄이는 가속 제안은 적용하지 않는다.
