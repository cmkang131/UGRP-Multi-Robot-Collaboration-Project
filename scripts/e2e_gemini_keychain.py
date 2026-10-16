"""Finite installed Gemini proxy with OAuth persistence only in macOS Keychain.

The audited installed proxy/model implementation is unchanged. The credential
loader/refresher is replaced before serving; credentials never enter argv/logs.
"""
import argparse
import ctypes
import getpass
import hashlib
import json
from pathlib import Path
import runpy
import signal
import threading
import time
import urllib.parse
import urllib.request

SERVICE=b'ugrp-gemini-subscription-oauth'


class Keychain:
    def __init__(self):
        self.api=ctypes.CDLL('/System/Library/Frameworks/Security.framework/Security')
        self.account=getpass.getuser().encode()
        self.api.SecKeychainFindGenericPassword.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_char_p,
            ctypes.c_uint32,ctypes.c_char_p,ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p)]
        self.api.SecKeychainAddGenericPassword.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_char_p,
            ctypes.c_uint32,ctypes.c_char_p,ctypes.c_uint32,ctypes.c_char_p,ctypes.POINTER(ctypes.c_void_p)]
        self.api.SecKeychainItemModifyAttributesAndData.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_char_p]
        self.api.SecKeychainItemFreeContent.argtypes=[ctypes.c_void_p,ctypes.c_void_p]

    def find(self):
        size=ctypes.c_uint32();data=ctypes.c_void_p();item=ctypes.c_void_p()
        status=self.api.SecKeychainFindGenericPassword(None,len(SERVICE),SERVICE,len(self.account),self.account,
            ctypes.byref(size),ctypes.byref(data),ctypes.byref(item))
        if status==-25300:return None,None
        if status:raise RuntimeError('Keychain lookup status '+str(status))
        try:return json.loads(ctypes.string_at(data,size.value)),item
        finally:self.api.SecKeychainItemFreeContent(None,data)

    def save(self,value):
        raw=json.dumps(value).encode();_,item=self.find()
        status=self.api.SecKeychainItemModifyAttributesAndData(item,None,len(raw),raw) if item else self.api.SecKeychainAddGenericPassword(
            None,len(SERVICE),SERVICE,len(self.account),self.account,len(raw),raw,None)
        if status:raise RuntimeError('Keychain save status '+str(status))


def refresh(namespace,store):
    creds,_=store.find()
    if not creds:raise RuntimeError('Gemini OAuth Keychain entry required')
    if creds.get('access_token') and time.time()*1000<(creds.get('expiry_date') or 0)-300000:
        return creds['access_token']
    body=urllib.parse.urlencode(dict(client_id=namespace['CLIENT_ID'],client_secret=namespace['CLIENT_SECRET'],
        refresh_token=creds['refresh_token'],grant_type='refresh_token')).encode()
    request=urllib.request.Request('https://oauth2.googleapis.com/token',data=body,method='POST',
        headers={'Content-Type':'application/x-www-form-urlencoded'})
    with urllib.request.urlopen(request,timeout=30) as response:tokens=json.load(response)
    creds.update(access_token=tokens['access_token'],expiry_date=int((time.time()+tokens.get('expires_in',3600))*1000))
    store.save(creds)
    return creds['access_token']


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=14400)
    p.add_argument('--port',type=int,choices=(8391,8395),default=8391)
    p.add_argument('--import-existing',action='store_true')
    a=p.parse_args()
    if not 0<a.seconds<=14400:raise ValueError('finite proxy lifetime required')
    from harness.zone_pilot_budget import PROXY_SHA256
    if hashlib.sha256(a.source.read_bytes()).hexdigest()!=PROXY_SHA256:raise ValueError('INSTALLED_PROXY_HASH_MISMATCH')
    store=Keychain();existing,_=store.find()
    if existing is None and a.import_existing:
        # One-way import of the user's already authenticated local cache. Keep
        # the pre-existing file untouched; this process only writes Keychain.
        value=json.loads((Path.home()/'.gemini/antigravity_creds.json').read_text())
        if not value.get('refresh_token'):raise ValueError('LOCAL_OAUTH_REFRESH_TOKEN_MISSING')
        store.save(value);del value
    elif existing is None:raise ValueError('OAUTH_KEYCHAIN_ENTRY_MISSING')
    loaded=runpy.run_path(str(a.source),run_name='ugrp_installed_proxy')
    ns=loaded['refresh_token'].__globals__
    ns['load_creds']=lambda:store.find()[0]
    ns['refresh_token']=lambda:refresh(ns,store)
    ns['PORT']=a.port
    a.output.mkdir(parents=True,exist_ok=False)
    ns['LOG_PATH']=a.output/'proxy.log'
    server=ns['ThreadingHTTPServer'](('127.0.0.1',ns['PORT']),ns['Handler'])
    server.daemon_threads=True
    timer=threading.Timer(a.seconds,server.shutdown);timer.daemon=True;timer.start()
    def stop(*_):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop)
    print(json.dumps(dict(status='READY',credential_store='macOS Keychain',port=ns['PORT'],
        source_sha256=PROXY_SHA256,wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())),flush=True)
    try:server.serve_forever()
    finally:timer.cancel();server.server_close()


if __name__=='__main__':main()
