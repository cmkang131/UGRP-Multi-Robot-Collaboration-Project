# 번호표만 바꾸는 오프라인 검사

동일 own RGB·자기 발행 이력·시계에서 role(청록/파랑) 번호표만 교환했다. 가중치는 고정 final20000이며 이 검사로 checkpoint를 고르지 않았다.

| 저장 입력 | 지표 | A | B |
|---|---|---:|---:|
| baseline cold-start40 | first_wheel_classes_changed | 3/40 | 2/40 |
| baseline cold-start40 | chunk_wheel_classes_changed | 6/40 | 4/40 |
| baseline cold-start40 | first_translation_reversed | 1/40 | 0/40 |
| baseline cold-start40 | chunk_translation_reversed | 1/40 | 0/40 |
| validation initial | wheel_class_changed | 0/38 | 0/38 |
| validation initial | translation_reversed | 0/38 | 0/38 |
| validation initial | nonzero_heading_changed | 0/38 | 0/38 |
| validation initial | translation_starts_or_stops | 0/38 | 0/38 |
| validation first_approach | wheel_class_changed | 1/29 | 0/29 |
| validation first_approach | translation_reversed | 0/29 | 0/29 |
| validation first_approach | nonzero_heading_changed | 0/29 | 0/29 |
| validation first_approach | translation_starts_or_stops | 1/29 | 0/29 |

cold-start는40개의 실제 첫 제어 입력(20seed×2robot), pulse 길이를 곱한 발행명령 dose다. validation initial38/first-approach29는 기록된 별도 문맥에서 h0 wheel 축합의 정수 단위0.35/4를 사용했다. 서로 다른 문맥/단위를 합산하지 않는다.

번호표에 대한 첫 접근 방향 민감도는 낮다. 출력 변화가 적다는 사실만으로 role을 완전히 무시한다고 단정하거나 실제 다른 끝 선택을 보장하지 않는다. A8329001 영상에서는 두 로봇이 배정된 끝에 접근했다. 직접 본 폐루프 영상과 별도로 해석한다.

검사 source67dd59df0(cold-start)/6f4fe4b3c(정확한 validation 축합), 원본·해시는 각 A/B-role-probe-coldstart.json 및 A/B-validation-role-direction.json에 있다. 새 물리 실행0.
