"""Session-owned camera reader: existing snapshot server or Pi /dev/video0.

No motor/servo imports, server startup, or termination of other camera owners.
"""
import time
import urllib.error
import urllib.request


class CameraSource:
    URLS = ('http://127.0.0.1:8080/snapshot',
            'http://127.0.0.1:8080/?action=snapshot')

    def __init__(self):
        self.source = None
        self.cap = None
        self.cv2 = None

    @staticmethod
    def _http(url):
        with urllib.request.urlopen(url, timeout=.5) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000 or not data.startswith(b'\xff\xd8'):
            raise ValueError('Snapshot server did not return a bounded JPEG')
        return data

    def read(self):
        if self.cap is None:
            urls = (self.source,) if self.source else self.URLS
            errors = []
            for url in urls:
                try:
                    data = self._http(url)
                    self.source = url
                    return data, time.monotonic()
                except (OSError, urllib.error.URLError) as error:
                    errors.append(str(error))
            try:
                import cv2
            except ImportError as error:
                raise RuntimeError('Snapshot server unavailable and Pi python3 cannot import cv2. '
                                   'Install python3-opencv on the Pi or restore its snapshot server. '
                                   + '; '.join(errors)) from error
            self.cv2 = cv2
            self.cap = cv2.VideoCapture('/dev/video0', cv2.CAP_V4L2)
            if not self.cap.isOpened():
                self.close()
                raise RuntimeError('Snapshot server unavailable; /dev/video0 could not open. '
                                   'Check USB camera, device permissions, and its current owner. '
                                   'No other process was stopped.')
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Flush startup frames once. Keep this handle open for the session.
            for _ in range(3):
                ok, frame = self.cap.read()
                if not ok or frame is None:
                    self.close()
                    raise RuntimeError('/dev/video0 opened but returned no camera frame')
            self.source = '/dev/video0 (V4L2, session owned)'
        ok, frame = self.cap.read()
        received = time.monotonic()
        if not ok or frame is None:
            raise RuntimeError('Fresh /dev/video0 camera read failed')
        if frame.shape[:2] != (480, 640):
            raise RuntimeError(f'Camera returned {frame.shape[:2]}; model requires 480x640')
        ok, encoded = self.cv2.imencode('.jpg', frame)
        if not ok:
            raise RuntimeError('Camera JPEG encoding failed')
        data = encoded.tobytes()
        if not data.startswith(b'\xff\xd8') or len(data) > 2_000_000:
            raise RuntimeError('Invalid camera JPEG')
        return data, received

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


