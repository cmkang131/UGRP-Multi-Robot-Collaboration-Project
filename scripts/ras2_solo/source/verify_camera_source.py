"""No-hardware checks for snapshot fallback and owned camera cleanup."""
import contextlib
import io
import json
from types import SimpleNamespace
import sys
import urllib.error
from unittest.mock import Mock, patch

import cv2
import numpy as np
import camera_source
import pi_bridge
import run


class Capture:
    def __init__(self, opened=True, shape=(480,640,3)):
        self.opened, self.shape = opened, shape
        self.reads, self.releases = 0, 0
    def isOpened(self):
        return self.opened
    def set(self, *args):
        return True
    def read(self):
        self.reads += 1
        return True, np.zeros(self.shape, dtype=np.uint8)
    def release(self):
        self.releases += 1


def main():
    jpeg = cv2.imencode('.jpg', np.zeros((480,640,3), np.uint8))[1].tobytes()
    with patch.object(camera_source.CameraSource, '_http', return_value=jpeg), \
         patch.object(cv2, 'VideoCapture') as opening:
        source = camera_source.CameraSource()
        image, _ = source.read()
        assert image == jpeg and not opening.called
        source.close()
    capture = Capture()
    with patch.object(camera_source.CameraSource, '_http', side_effect=urllib.error.URLError('refused')) as http, \
         patch.object(cv2, 'VideoCapture', return_value=capture) as opening:
        source = camera_source.CameraSource()
        try:
            for _ in range(2):
                image, _ = source.read()
                assert cv2.imdecode(np.frombuffer(image,np.uint8),cv2.IMREAD_COLOR).shape == (480,640,3)
            assert http.call_count == 2 and opening.call_count == 1 and capture.reads == 5
            assert source.source.startswith('/dev/video0')
        finally:
            source.close()
        assert capture.releases == 1
    capture = Capture(opened=False)
    with patch.object(camera_source.CameraSource, '_http', side_effect=urllib.error.URLError('refused')), \
         patch.object(cv2, 'VideoCapture', return_value=capture):
        try:
            camera_source.CameraSource().read()
        except RuntimeError as error:
            assert '/dev/video0 could not open' in str(error)
        else:
            raise AssertionError('Missing camera accepted')
        assert capture.releases == 1
    with patch.object(camera_source.CameraSource, '_http', side_effect=urllib.error.URLError('refused')), \
         patch.dict(sys.modules, {'cv2': None}):
        try:
            camera_source.CameraSource().read()
        except RuntimeError as error:
            assert 'python3 cannot import cv2' in str(error)
        else:
            raise AssertionError('Missing cv2 accepted')
    control = SimpleNamespace(probe_hardware=lambda: {'ok': True}, load_pose_state=lambda: {})
    camera = Mock()
    camera.read.side_effect = RuntimeError('injected camera failure')
    spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module: None))
    fake_input = io.StringIO('{"op":"observe"}\n')
    with patch.object(pi_bridge, 'CameraSource', return_value=camera), \
         patch.object(pi_bridge.socket, 'gethostname', return_value='ras2'), \
         patch.object(pi_bridge.importlib.util, 'spec_from_file_location', return_value=spec), \
         patch.object(pi_bridge.importlib.util, 'module_from_spec', return_value=control), \
         patch.object(pi_bridge.signal, 'signal'), \
         patch.object(pi_bridge.signal, 'SIGHUP', 1, create=True), \
         patch.object(pi_bridge.select, 'select', return_value=([fake_input],[],[])), \
         patch.object(sys, 'stdin', fake_input), \
         patch.object(sys, 'argv', ['pi_bridge.py','--control','unused.py']), \
         contextlib.redirect_stdout(io.StringIO()):
        try:
            pi_bridge.main()
        except RuntimeError as error:
            assert str(error) == 'injected camera failure'
        else:
            raise AssertionError('Expected camera failure')
    camera.close.assert_called_once()
    result = {'existing_http_camera':'passed', 'http_refused_v4l2_fallback':'passed',
              'fresh_reads_and_single_handle':'passed', 'owned_camera_release':'passed',
              'missing_device_and_cv2_errors':'passed', 'bridge_cleanup_after_camera_error':'passed',
              'physical_camera_access':'not performed', 'physical_commands_sent':0}
    (run.ROOT/'camera-source-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
