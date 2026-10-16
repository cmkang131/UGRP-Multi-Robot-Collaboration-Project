# warp5 source and method references

- [MJWarp API](https://mujoco.readthedocs.io/en/latest/mjwarp/api.html): create_render_context fixed nworld, explicit camera selection, textures/shadows and subpixel samples. Installed pinned source is authoritative and is archived in runtime metadata. MJWarp ray tracing differs from native OpenGL; RGB byte equality is not assumed.
- [MJWarp rendering source](https://github.com/google-deepmind/mujoco_warp/blob/main/mujoco_warp/_src/render_util.py): source inspected on gcp2 for samples_per_pixel and get_segmentation. Segmentation is evaluation only.
- Existing scene-tex5 88 fixtures, PIL82 codec, own camera optics, relocation colour calibration and detector constants are reused. Static no-motion/one-pixel-yaw LK distributions are measurements, not a loaded VO gate or new stall threshold.
- Shared backend source e97464a32c7c90b68b0c3a4d19ce630f9ad7abee and reloc20 source 2f4f469ef8e3c3bedeaebb0aff698332b426fbaf are separate provenance. CPU results are never pooled with MJWarp.
