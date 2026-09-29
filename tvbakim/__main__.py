from __future__ import annotations
import argparse
import signal
import sys
import threading
import webbrowser
from pathlib import Path
from tvbakim import __version__
from tvbakim.adb import Adb
from tvbakim.engine import Engine
from tvbakim.server import App, LocalServer
from tvbakim.store import Store,data_directory


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'): stream.reconfigure(encoding='utf-8',errors='replace')
    if hasattr(signal,'SIGBREAK'):
        def interrupt(signum, frame): raise KeyboardInterrupt
        signal.signal(signal.SIGBREAK,interrupt)
    parser=argparse.ArgumentParser(description='TVCare — yerel Android TV bakım aracı')
    parser.add_argument('--version',action='version',version='TVCare '+__version__)
    parser.add_argument('--demo',action='store_true',help='Sentetik cihaz; gerçek ADB veya TV bağlantısı kullanılmaz')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=0,help='Yerel port; varsayılan otomatik')
    parser.add_argument('--data-dir',type=Path,help='Özel yerel işlem kayıt klasörü')
    parser.add_argument('--adb',type=Path,help='Kurulu Android Platform Tools adb yürütülebilir dosyası')
    args=parser.parse_args()
    if not 0 <= args.port <= 65535: parser.error('Port 0–65535 aralığında olmalı.')
    directory=args.data_dir or data_directory(args.demo)
    # Never mix synthetic transactions with real device history, including explicit directories.
    if args.demo and args.data_dir: directory=directory/'demo'
    store=Store(directory)
    try: store.acquire()
    except RuntimeError as e: parser.exit(1,str(e)+'\n')
    store.recover()
    if args.demo:
        from tvbakim.demo import DemoAdb,DemoDevice
        engine=Engine(DemoAdb(),store,DemoDevice)
    else: engine=Engine(Adb(args.adb),store)
    app=App(engine,args.demo)
    try: server=LocalServer(app,args.port)
    except OSError as e:
        store.close(); parser.exit(1,'Yerel sunucu açılamadı: '+str(e)+'\n')
    url=server.origin+'/#token='+app.token
    print('TVCare '+__version__+(' · DEMO / sentetik cihaz' if args.demo else ''),flush=True)
    print('Yalnızca bu bilgisayardan erişim: '+url,flush=True)
    print('Kapatmak için Ctrl+C. Devam eden işlem varsa bitmesini bekleyin.',flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt: print('\nTVCare kapanıyor; devam eden adımın kaydı tamamlanıyor…',flush=True)
    finally:
        server.server_close(); app.jobs.close(); store.close()

if __name__=='__main__': main()
