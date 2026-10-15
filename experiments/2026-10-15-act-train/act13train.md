# ACT13TRAIN — 회복50 데이터 조립과 L4 두 군 smoke300

class dev. 학생 임무 성공이나 본 학습 승인 아님. 교사 `1fce11554754d4609470e4fe4b172f9a583bc026`, rotation `act8_yaw_gain_v1`. 승인된 train86820–86864 / validation86865–86869를 유지한다. 원본50 및 ACT6 composed95와 섞지 않는다.

실행 전 소스 변경: 전송 SHA와 실행 교사 SHA를 별도 검증하고, 원장 전체의 whitelist·발행 명령 이력·자기 명령 clock·변환 텐서·train-only 통계를 재검증한다. 파일별 해시는 dataset manifest에, manifest 자체 해시는 별도 영수증에 남긴다. 옵션 `--checkpoint-every 5000`은 smoke 최종300, main5000/10000만 저장하며 기존 파일을 삭제하지 않는다. 기본0은 기존 smoke100/main500과 같다. 두 군 합계 체크포인트6개(기존 실측 기준 약3.48GiB), 예약5GiB+바닥8GiB를 요구한다. 새 데이터 실측 용량을 포함해 제출 전 다시 계산한다.

본 학습은 독립 재집계·스모크 검토 뒤 조정자의 SHA 고정 승인만 받는다. 결과와 대기열은 실행 후 추가한다.

## 참고

[PyTorch 공식 저장/로딩 지침](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html): 모델·optimizer state_dict를 포함해 재개 가능하게 저장하고 eval 모드에서 저장 전후 출력을 비교한다. 이번 변경은 저장 빈도만 선택적으로 줄이며 최종 저장과 optimizer/RNG 기록을 유지한다. 기존 프로젝트 `actgpu1.md`, `harness/grasp_act_data.py`, `scripts/grasp_act_training_guard.py`의 형식과 승인 경계를 재사용한다.
