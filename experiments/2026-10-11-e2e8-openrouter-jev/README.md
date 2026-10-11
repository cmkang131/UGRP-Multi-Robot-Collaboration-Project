# E2E 8차 OpenRouter / Jev DEV
- SHA `7743f530`: seed61001·61002, A=Gemma, B=Gemma 대화+Jev 선택(v192).
- 총8시도: 보정 입력 누락 HOST_ERROR4 + 실제 시뮬레이션4; 추가 seed 없음.
- 실제4회: LLM4/4 · 자기 지도 경로0/4 · 시작→끝 운반0/4.
- 180–184초 초기 점검에서 회전만 반복하여 개별 종료; 최종 result.json 누락1회는 HOST_ERROR.
- Gemma A/B: 6/6호출, 9547/10320토큰, 중앙2.902/4.036초, 총$0.00194360.
- Jev6호출·6542토큰·중앙0.246초·비용 미제공; Gemma shadow 불일치0/6(모두 continue).
- 자기 위치 점프768간격: >5cm57 · >20cm17 · 최대0.709726m; 실제 이동 성공 아님.
- 원본8회 ARM1235/1235해시 확인·Mac 경량회수; 상세·경로·출처는 summary.json.
- 다음: frontier 전환·자기 pose 연속성·종료 flush; PR433 DRAFT, 연구/E2E 성공 주장 없음.
