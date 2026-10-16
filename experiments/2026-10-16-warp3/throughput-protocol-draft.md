# 4단계 warm 측정 프로토콜

40/40 교사 관문과 RECORD_API_READY 뒤에만 구현·실행했다. 진입점은 `scripts/warp_act_warm.py`, CPU `warp_act_c16_warm.py`, L4 `warp_act_gpu_warm.py`. 모두 기본 off다.

같은 f0db 교사·선택 장면·seed8317104/s1_normal_mixed_v4에서 정상 교사 행동을 실행한다. SIM0..3의 초기화/JIT/최초 RGB/동역학 예열을 제외하고 **SIM3..6의30제어 간격**을 잰다. 3SIM는 기존 Score lift_hold_s=3을 유한 측정 예산으로 빌린 값이며 성공·수용 상수가 아니다. 같은 native640×480/10Hz/JPEG를 포함하고 학습용 저장은 끈다. C는3.12.0, Warp는 설치된3.16 계열이며 호스트·backend 결과를 각각 표시한다.

이 값은 **짧은 접근 구간의 warm 실행률**이다. 전체 교사/ACT 임무·학습·접촉 hold의 정상상태 성능으로 확대하지 않는다. 첫10/마지막10간격 중앙값과 p90·구간별 소요를 함께 보존하여 phase별 비용 변화를 드러낸다. 교사 Python 상태기계와 평가 기록도 전체 wall에 포함한다. world는 같은 case 복제 부하이며 독립 교사 n/N=0이다.

C16은16프로세스 모두 warm READY 뒤 동시에 GO, 가장 이른 시작~가장 늦은 종료의48SIM/VM wall로 계산한다. 모두 DONE 뒤에만 FINALIZE하므로 빠른 worker의 압축/마감이 느린 worker 측정에 섞이지 않는다. L4 N64→N256은 같은 boot에서 순서대로, GPU context 없이 다른 작업 종료를 기다린다. 예열·측정 중 외부 CUDA PID와 같은 사용자의 Python/MuJoCo/ffmpeg 작업을 샘플링하며 섞인 시도는 제외한다. timed 로그에 신규 compile이 있어도 제외한다. 다른 작업을 중지하지 않는다.

CPU C16 r1은 외부 Python PID23613이1회 보여 제외했다. r2는 외부 부하 관찰0,48SIM/5.866921376s=**8.181462972 SIM/s**, 자원 상한 cap_end16/HOST_ERROR0이다. 16worker의 원본1360파일 해시 불일치0·visible/held 입력 감사0을 독립 확인했다([감사](warm-c16-r2-independent-audit.json)). 첫10/마지막10간격의 속도 차이가 있어 임무 전체의 안정된 지연이라고 주장하지 않는다.

L4는 현재 외부 beamact3/act16w 작업 종료 대기다. 별도 gcp2b는 GPUS_ALL_REGIONS limit1 때문에 생성이 거절됐고 추가 instance/disk는 남지 않았다. 유한 대기열은 현 boot8h 상한보다2분 앞선13:59:09Z까지이며 budget-stop/idle20분을 유지한다. 공유 부하가 없고 원본 SHA 검증이 끝난 경우만 최종 표에 수록한다.

SIM초/$는 inherited 단가 가정(CPU $3.1454/h, L4 $1.096/h)에 따른 한 VM 값이다. 실시간 가격·실제 청구/크레딧 소진액은 검증하지 않았다. 종전 cold/shared warp1 값과 합산하지 않는다.
