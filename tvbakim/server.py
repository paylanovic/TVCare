"""Loopback-only UI host. Not a remote management server."""
from __future__ import annotations
import hmac
import json
import mimetypes
import re
import secrets
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from . import __version__
from .report import sanitize_report
from .store import now


class Jobs:
    def __init__(self):
        self.executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='tvcare-worker')
        self.records={}
        self.lock=threading.RLock()
    def submit(self,kind,fn):
        with self.lock:
            if any(j['status'] in ('queued','running') for j in self.records.values()):
                raise ValueError('Bir işlem sürüyor. Bitmesini bekleyin.')
            job={'id':uuid.uuid4().hex,'kind':kind,'status':'queued','created_at':now(),'result':None,'error':None,'logs':[]}
            self.records[job['id']]=job
            if len(self.records)>100:
                del self.records[next(iter(self.records))]
        def log(message):
            with self.lock: job['logs'].append(str(message)[:1000])
        def run():
            with self.lock: job['status']='running'
            try:
                result=fn(log)
                with self.lock:
                    job['result']=result; job['status']='succeeded'
            except Exception as e:
                with self.lock: job['status']='failed'; job['error']=str(e)[:1500]
        self.executor.submit(run)
        return self.get(job['id'])
    def get(self,key):
        with self.lock:
            if key not in self.records: raise KeyError('İşlem bulunamadı.')
            return json.loads(json.dumps(self.records[key]))
    def list(self):
        with self.lock: return [self.get(key) for key in self.records]
    def close(self): self.executor.shutdown(wait=True)


class App:
    def __init__(self,engine,demo=False):
        self.engine=engine; self.demo=demo; self.jobs=Jobs()
        self.token=secrets.token_urlsafe(32)
    def status(self):
        adb=self.engine.adb
        error=None
        try: devices=adb.devices() if adb.available() else []
        except Exception as e: devices=[]; error=str(e)
        return {'app':'TVCare','version':__version__,'demo':self.demo,'adb':{'available':adb.available(),'path':adb.path,'error':error},'devices':devices,'jobs':self.jobs.list(),'history':self.engine.store.history()}
    def dispatch(self,path,body):
        if not isinstance(body,dict): raise ValueError('JSON nesnesi gerekli.')
        e=self.engine
        if path=='/api/connect': fn=lambda log: {'message':e.adb.connect(body.get('endpoint')),'devices':e.adb.devices()}
        elif path=='/api/pair': fn=lambda log: {'message':e.adb.pair(body.get('endpoint'),body.get('code')),'devices':e.adb.devices()}
        elif path=='/api/inspect': fn=lambda log:e.inspect(body.get('serial'))
        elif path=='/api/plan': fn=lambda log:e.plan(body.get('serial'),body.get('actions'))
        elif path=='/api/apply': fn=lambda log:e.apply(body.get('plan_id'),body.get('confirmed'),log)
        elif path=='/api/rollback-plan': fn=lambda log:e.rollback_plan(body.get('transaction_id'),body.get('serial'))
        elif path=='/api/guard/plan': fn=lambda log:e.guard_plan(body.get('serial'),body.get('operation'))
        else: raise KeyError('İşlem bulunamadı.')
        return {'job':self.jobs.submit(path.rsplit('/',1)[-1],fn)}


class LocalServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,app,port=0):
        self.app=app
        super().__init__(('127.0.0.1',port),Handler)
        self.origin=f'http://127.0.0.1:{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    server_version='TVCare'
    sys_version=''
    protocol_version='HTTP/1.1'
    def setup(self):
        super().setup(); self.connection.settimeout(15)
    def log_message(self,*args): pass  # never log token, pairing code or device endpoints
    def _reply(self,status,payload,content_type='application/json; charset=utf-8',download=None):
        raw=payload if isinstance(payload,bytes) else json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        if download: self.send_header('Content-Disposition',f'attachment; filename="{download}"')
        self.end_headers(); self.wfile.write(raw)
    def _trusted(self,auth=True):
        expected=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host')!=expected:
            self._reply(403,{'error':'Geçersiz yerel sunucu adresi.'}); return False
        if self.headers.get('Origin') not in (None,self.server.origin):
            self._reply(403,{'error':'Bu kaynak TVCare oturumuna erişemez.'}); return False
        if self.headers.get('Sec-Fetch-Site')=='cross-site':
            self._reply(403,{'error':'Siteler arası erişim engellendi.'}); return False
        if auth and not hmac.compare_digest(self.headers.get('Authorization','').encode('utf-8'),('Bearer '+self.server.app.token).encode('utf-8')):
            self._reply(401,{'error':'Oturum anahtarı eksik veya geçersiz. TVCare’nin açtığı bağlantıyı kullanın.'}); return False
        return True
    def do_GET(self):
        path=urlsplit(self.path).path
        if not self._trusted(auth=path.startswith('/api/')): return
        try:
            app=self.server.app
            if path=='/api/status': return self._reply(200,app.status())
            if path=='/api/discover':
                return self._reply(200,{'devices':app.engine.adb.devices(),'services':app.engine.adb.discover()})
            if path=='/api/history': return self._reply(200,{'history':app.engine.store.history()})
            if re.fullmatch(r'/api/jobs/[a-f0-9]{32}',path): return self._reply(200,app.jobs.get(path.split('/')[-1]))
            if path=='/api/report' or re.fullmatch(r'/api/report/[a-f0-9]{32}',path):
                data=app.engine.last_inspection if path=='/api/report' else app.engine.store.get(path.split('/')[-1])
                if not data: raise ValueError('Önce TV’yi kontrol edin.')
                return self._reply(200,sanitize_report(data,app.demo),download='TVCare-rapor.json')
            files={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path not in files: return self._reply(404,{'error':'Sayfa bulunamadı.'})
            file=Path(__file__).parent/'static'/files[path]
            return self._reply(200,file.read_bytes(),(mimetypes.guess_type(file.name)[0] or 'text/plain')+'; charset=utf-8')
        except (KeyError,FileNotFoundError): self._reply(404,{'error':'Kayıt bulunamadı.'})
        except (ValueError,RuntimeError) as e: self._reply(400,{'error':str(e)[:1500]})
        except Exception: self._reply(500,{'error':'Beklenmeyen yerel hata; işlem uygulanmadı veya geçmişten kontrol edilmeli.'})
    def do_POST(self):
        if not self._trusted(): self.close_connection=True; return
        try:
            if self.headers.get('Transfer-Encoding'): raise ValueError('Parçalı istek desteklenmiyor.')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('JSON içerik türü gerekli.')
            length=int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 32768: raise ValueError('İstek boyutu geçersiz (en fazla 32 KB).')
            raw=self.rfile.read(length)
            if len(raw)!=length: raise ValueError('İstek tamamlanmadı.')
            body=json.loads(raw)
            self._reply(202,self.server.app.dispatch(urlsplit(self.path).path,body))
        except KeyError: self._reply(404,{'error':'İşlem bulunamadı.'})
        except (ValueError,UnicodeDecodeError) as e:
            self.close_connection=True
            self._reply(400,{'error':str(e)[:1500]})
        except Exception:
            self.close_connection=True
            self._reply(500,{'error':'İstek işlenemedi. Geçmişi kontrol edin.'})
