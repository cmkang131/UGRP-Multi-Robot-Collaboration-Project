"""One outstanding request per robot to a localhost Mac relay; no credentials."""
import base64,json
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
from urllib.error import HTTPError

class Client:
    def __init__(self,url):
        if url not in ('http://127.0.0.1:18093/end',):raise ValueError('LOCAL_END_RELAY_REQUIRED')
        self.url=url;self.pool=ThreadPoolExecutor(max_workers=1);self.future=None;self.calls=0
    def start(self,context,frame):
        if self.future is not None:raise ValueError('END_REQUEST_PENDING')
        body=json.dumps(dict(context=context,image=base64.b64encode(frame.jpeg).decode(),image_sha256=frame.sha256)).encode()
        def call():
            try:
                with urlopen(Request(self.url,data=body,headers={'Content-Type':'application/json'}),timeout=30) as r:return json.load(r)
            except HTTPError as e:
                try:return json.loads(e.read(4096))
                except Exception:return dict(error='END_HTTP_ERROR')
            except Exception as e:return dict(error='END_TRANSPORT_ERROR',error_type=type(e).__name__)
        self.calls+=1;self.future=self.pool.submit(call)
    def poll(self):
        if self.future is None or not self.future.done():return None
        value=self.future.result();self.future=None;return value
    def close(self):self.pool.shutdown(wait=True,cancel_futures=True)
