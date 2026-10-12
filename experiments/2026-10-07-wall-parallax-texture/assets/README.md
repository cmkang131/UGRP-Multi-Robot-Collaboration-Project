# 실물 부착용 배치도

단위: CSV는 mm, JSON은 m. `origin_world_m`는 해당 면의 **바닥 왼쪽 모서리**, u는 그 면을 바라볼 때 오른쪽, v는 위(+z)입니다. SVG는 100% 크기로 인쇄하며 각 면을 한 번만 붙입니다. 바탕/검은 색은 실물 미확인 가정입니다.

세로 테이프는 표의 centre_u_mm 중심에서 width_mm 폭으로 바닥부터 height_mm까지 부착합니다. 조각은 layout.json vertices_m 또는 SVG 윤곽대로 자릅니다. 50 mm 끝면은 중앙 테이프 1개뿐이라 mm 래스터 폭이 다른 면과 우연히 같을 수 있습니다. 넓은 12면의 배치는 모두 다릅니다.

[전체 테이프 위치표](tape-positions-mm.csv) · [조각 꼭짓점/좌표 원점](layout.json)

|벽/면|폭×높이 mm|테이프/조각|1:1 배치도|
|---|---:|---:|---|
|zone_wall_divider_1 / px|1925×400|8/22|[px](zone_wall_divider_1_px.svg)|
|zone_wall_divider_1 / nx|1925×400|8/19|[nx](zone_wall_divider_1_nx.svg)|
|zone_wall_divider_1 / py|50×400|1/0|[py](zone_wall_divider_1_py.svg)|
|zone_wall_divider_1 / ny|50×400|1/0|[ny](zone_wall_divider_1_ny.svg)|
|zone_wall_divider_2 / px|1150×400|5/13|[px](zone_wall_divider_2_px.svg)|
|zone_wall_divider_2 / nx|1150×400|4/8|[nx](zone_wall_divider_2_nx.svg)|
|zone_wall_divider_2 / py|50×400|1/0|[py](zone_wall_divider_2_py.svg)|
|zone_wall_divider_2 / ny|50×400|1/0|[ny](zone_wall_divider_2_ny.svg)|
|zone_wall_east / px|4600×400|18/54|[px](zone_wall_east_px.svg)|
|zone_wall_east / nx|4600×400|18/53|[nx](zone_wall_east_nx.svg)|
|zone_wall_east / py|50×400|1/0|[py](zone_wall_east_py.svg)|
|zone_wall_east / ny|50×400|1/0|[ny](zone_wall_east_ny.svg)|
|zone_wall_north / px|50×400|1/0|[px](zone_wall_north_px.svg)|
|zone_wall_north / nx|50×400|1/0|[nx](zone_wall_north_nx.svg)|
|zone_wall_north / py|6500×400|26/73|[py](zone_wall_north_py.svg)|
|zone_wall_north / ny|6500×400|27/77|[ny](zone_wall_north_ny.svg)|
|zone_wall_south / px|50×400|1/0|[px](zone_wall_south_px.svg)|
|zone_wall_south / nx|50×400|1/0|[nx](zone_wall_south_nx.svg)|
|zone_wall_south / py|6500×400|26/72|[py](zone_wall_south_py.svg)|
|zone_wall_south / ny|6500×400|26/75|[ny](zone_wall_south_ny.svg)|
|zone_wall_west / px|4600×400|18/51|[px](zone_wall_west_px.svg)|
|zone_wall_west / nx|4600×400|19/53|[nx](zone_wall_west_nx.svg)|
|zone_wall_west / py|50×400|1/0|[py](zone_wall_west_py.svg)|
|zone_wall_west / ny|50×400|1/0|[ny](zone_wall_west_ny.svg)|
