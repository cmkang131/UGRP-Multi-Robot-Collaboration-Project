"""Instance-local camera extension; preserve the VIS3 hash-pinned module.

Keep all original ColumnModel geometry/methods. Only supply explicit optical
extrinsics to its constructor through ordinary dependency injection.
"""
from dataclasses import dataclass
from types import SimpleNamespace
import numpy as np
from harness.active_camera import bind


def adapter(module):
    @dataclass
    class ColumnModel(module.ColumnModel):
        camera_transform: tuple | None = None

        def __post_init__(self):
            if self.camera_transform is None:return super().__post_init__()
            origin,rotation=(np.asarray(v,float) for v in self.camera_transform)
            initialize=bind(module.ColumnModel.__post_init__,camera_in_base=lambda servo:(origin,rotation),
                            bias_rotation=lambda angle:np.eye(3))
            initialize(self)
    return SimpleNamespace(**{**vars(module),'ColumnModel':ColumnModel})
