"""Allowlisted plans and write-ahead, device-bound, conflict-aware transactions."""
from __future__ import annotations
import copy
import hashlib
import re
import sys
import threading
import time
import uuid
from pathlib import Path
from .device import Device
from .store import now

ANIMATIONS = {'window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'}
GUARD = 'com.kilitkoruyucu.tv'
GUARD_DIR = '/data/local/tmp/'
PROFILE = 'tcl_beyondtv4_rtd288o_a11'
COMPONENT = re.compile(r'^[A-Za-z][A-Za-z0-9_.]*\/[A-Za-z0-9_.$]+$')


def resources():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'resources'


class PlanError(ValueError): pass


class Engine:
    def __init__(self, adb, store, device_factory=Device, clock=time.time):
        self.adb, self.store, self.device_factory, self.clock = adb, store, device_factory, clock
        self.plans = {}
        self.lock = threading.RLock()
        self.last_inspection = None

    def device(self, serial):
        if not isinstance(serial, str) or not serial or len(serial) > 200:
            raise PlanError('Önce bir TV seçin.')
        matches = [d for d in self.adb.devices() if d['serial'] == serial]
        if not matches or matches[0]['state'] != 'device':
            raise PlanError('Seçilen TV bağlı veya yetkilendirilmiş değil. Bağlantıyı kontrol edin.')
        return self.device_factory(self.adb, serial)

    def identity(self, device, writable=True):
        info = device.inspect()
        if writable:
            if not info['capabilities'].get('is_tv', False):
                raise PlanError('Bakım işlemleri yalnızca Android TV / Google TV cihazlarına uygulanabilir.')
            if not info['capabilities'].get('owner_user', False):
                raise PlanError('Bakım yalnızca TV’nin ana kullanıcı profili (kullanıcı 0) açıkken yapılabilir.')
            if not info['capabilities'].get('stable_identity', False):
                raise PlanError('TV için kalıcı cihaz kimliği okunamadı. Yanlış cihaza işlem yapmamak için yalnızca tanı kullanılabilir.')
        return info

    @staticmethod
    def same_device(expected, actual):
        if (not expected.get('serial_hash') or expected.get('serial_hash') != actual.get('serial_hash')
                or expected.get('fingerprint') != actual.get('fingerprint')):
            raise PlanError('Cihaz veya sistem sürümü planla uyuşmuyor. TV’yi yeniden tarayın.')

    def _components(self, device, action, prefix):
        try:
            output = self.adb.shell(device.serial, ['cmd','package','query-activities','--brief','--user','0','-a',action] + prefix)
            return sorted(set(line.strip() for line in output.splitlines() if COMPONENT.fullmatch(line.strip())))
        except Exception:
            return []

    def launcher_state(self, device):
        # HOME role is authoritative; an implicitly resolved fallback is not a saved preference.
        holder = self.adb.shell(device.serial, ['cmd','role','get-role-holders','--user','0','android.app.role.HOME']).strip()
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+', holder):
            raise PlanError('Kaydedilmiş tek bir ana ekran tercihi okunamadı; güvenli geri alma için ana ekran değişimi kapalı.')
        out = self.adb.shell(device.serial, ['cmd','package','resolve-activity','--brief','--user','0','-a','android.intent.action.MAIN','-c','android.intent.category.HOME','-p',holder]).strip()
        matches = [x.strip() for x in out.splitlines() if COMPONENT.fullmatch(x.strip())]
        if len(matches) != 1 or matches[0].split('/')[0] != holder:
            raise PlanError('Geçerli ana ekran bileşeni kesin okunamadı.')
        return matches[0]

    def inspect(self, serial):
        d = self.device(serial)
        result = self.identity(d, writable=False)
        result['health'] = d.health()
        result['packages'] = d.packages()
        result['settings'] = {}
        for key in sorted(ANIMATIONS):
            try: result['settings'][key] = d.read_setting('global',key)
            except Exception as e: result['settings'][key] = {'present':None,'value':None,'error':str(e)}
        launchers = self._components(d,'android.intent.action.MAIN',['-c','android.intent.category.HOME'])
        try: current = self.launcher_state(d)
        except Exception: current = None
        result['launchers'] = [{'component':c,'label':c.split('/')[0],'current':c==current} for c in launchers] if current else []
        # Query services specifically: dreams are not activities.
        try:
            out = self.adb.shell(serial,['cmd','package','query-services','--brief','--user','0','-a','android.service.dreams.DreamService'])
            dreams = sorted(set(x.strip() for x in out.splitlines() if COMPONENT.fullmatch(x.strip())))
            old = d.read_setting('secure','screensaver_components')
            result['screensavers'] = [{'component':c,'label':c.split('/')[0],'current':c==old['value']} for c in dreams]
        except Exception:
            result['screensavers'] = []
        result['inspected_at'] = now()
        result['serial'] = serial
        self.last_inspection = copy.deepcopy(result)
        return result

    def _read(self, d, action):
        kind = action['type']
        if kind == 'setting': return d.read_setting(action['namespace'],action['key'])
        if kind == 'package': return d.package_state(action['package'])
        if kind == 'launcher': return self.launcher_state(d)
        if kind == 'guard_apk':
            output = self.adb.shell(d.serial,['pm','list','packages','--user','0',GUARD])
            return 'installed' if 'package:'+GUARD in output.splitlines() else 'absent'
        if kind == 'guard_appop':
            output = self.adb.shell(d.serial,['appops','get',GUARD,'APP_AUTO_START'])
            match = re.search(r'APP_AUTO_START:\s*(allow|ignore|deny|default|foreground)',output)
            if match: return match.group(1)
            if 'No operations' in output: return 'default'
            raise PlanError('Otomatik başlama izni okunamadı.')
        if kind == 'guard_active':
            out = self.adb.shell(d.serial,['sh','-c','if [ ! -f /data/local/tmp/kilit-koruyucu.sh ]; then echo STOPPED; elif head -n 2 /data/local/tmp/kilit-koruyucu.sh | grep -Fq "# TVCare Guard 1.1."; then sh /data/local/tmp/kilit-koruyucu.sh --status; else echo UNKNOWN_LEGACY; fi'])
            if out.strip().startswith('RUNNING:'): return 'running'
            if out.strip().startswith('STOPPING:'): return 'stopping'
            if 'LEGACY' in out: return 'unknown'
            if 'DISABLED' in out or 'STOPPED' in out: return 'stopped'
            raise PlanError('Bekçi durumu doğrulanamadı.')
        raise PlanError('Desteklenmeyen işlem.')

    def _write(self, d, action, value):
        kind, s = action['type'], d.serial
        if kind == 'setting':
            if value['present']: self.adb.shell(s,['settings','--user','0','put',action['namespace'],action['key'],value['value']])
            else: self.adb.shell(s,['settings','--user','0','delete',action['namespace'],action['key']])
        elif kind == 'package':
            commands = {'default':'default-state','enabled':'enable','disabled':'disable',
                        'disabled-user':'disable-user','disabled-until-used':'disable-until-used'}
            self.adb.shell(s,['pm',commands[value],'--user','0',action['package']])
        elif kind == 'launcher':
            self.adb.shell(s,['cmd','package','set-home-activity','--user','0',value])
            resolved=self.adb.shell(s,['cmd','package','resolve-activity','--brief','--user','0','-a','android.intent.action.MAIN','-c','android.intent.category.HOME']).strip()
            if value not in resolved.splitlines():
                raise PlanError('Üretici ana ekran önceliği tercihin uygulanmasını engelledi. Geçmişten eski tercihi geri alabilirsiniz.')
        elif kind == 'guard_apk':
            if value == 'installed':
                apk = resources()/'guard/kilit-koruyucu.apk'
                if not apk.is_file() or hashlib.sha256(apk.read_bytes()).hexdigest() != action['apk_sha256']:
                    raise PlanError('Koruyucu APK dosyası plan oluşturulduktan sonra değişmiş.')
                self.adb.install(s,str(apk))
            else:
                self.adb.shell(s,['pm','uninstall','--user','0',GUARD],timeout=60)
        elif kind == 'guard_appop':
            self.adb.shell(s,['appops','set',GUARD,'APP_AUTO_START',value])
        elif kind == 'guard_active':
            if value == 'running':
                self.adb.shell(s,['am','start','-n',GUARD+'/.MainActivity'])
                self.adb.shell(s,['am','start-foreground-service','-a','com.kilitkoruyucu.tv.START','-n',GUARD+'/.GuardService'])
                # TV screen may ask for the companion's distinct localhost RSA key.
                deadline = time.monotonic()+185
                while time.monotonic() < deadline:
                    try:
                        if self._read(d,action) == 'running': return
                    except Exception: pass
                    time.sleep(2)
                raise PlanError('Bekçi başlamadı. TV’deki ADB izin penceresini onaylayın; kısmi işlemi geçmişten geri alabilirsiniz.')
            else:
                if self._read(d,action)=='unknown':
                    raise PlanError('Eski veya tanınmayan bekçi betiği çalıştırılmayacak. Otomatik durdurma desteklenmiyor.')
                self.adb.shell(s,['am','force-stop',GUARD])
                self.adb.shell(s,['sh','-c','touch /data/local/tmp/kilit-koruyucu.disabled; if [ -f /data/local/tmp/kilit-koruyucu.sh ]; then sh /data/local/tmp/kilit-koruyucu.sh --stop; fi'])
                for _ in range(10):
                    if self._read(d,action)=='stopped': return
                    time.sleep(1)
                raise PlanError('Bekçi durdurulamadı.')
        else: raise PlanError('Desteklenmeyen işlem.')

    def _new_plan(self, serial, identity, actions, kind='apply', source=None, warnings=None):
        if not actions: raise PlanError('Seçimler zaten uygulanmış; değiştirilecek bir ayar yok.')
        plan = {'id':uuid.uuid4().hex,'created_at':now(),'expires_at':self.clock()+900,
                'serial':serial,'device':identity,'actions':actions,'kind':kind,
                'source':source,'warnings':warnings or [],'used':False}
        self.plans[plan['id']] = plan
        # Expired plans never survive restart and do not grow indefinitely.
        for key in list(self.plans):
            if self.plans[key]['expires_at'] < self.clock(): del self.plans[key]
        return copy.deepcopy(plan)

    def plan(self, serial, requests):
        with self.lock:
            if not isinstance(requests,list) or not 1 <= len(requests) <= 40:
                raise PlanError('1–40 bakım seçeneği seçin.')
            d = self.device(serial)
            info = self.identity(d)
            packages = {p['id']:p for p in d.packages()}
            actions, seen, warnings = [], set(), []
            for request in requests:
                if not isinstance(request,dict): raise PlanError('Geçersiz işlem.')
                kind = request.get('type')
                if kind == 'setting':
                    namespace, key, value = request.get('namespace'),request.get('key'),request.get('value')
                    if namespace == 'global' and key in ANIMATIONS and value in ('0','0.5','1.0'):
                        label = {'window_animation_scale':'Pencere animasyonu','transition_animation_scale':'Geçiş animasyonu','animator_duration_scale':'Animasyon süresi'}[key]
                    elif namespace == 'secure' and key == 'screensaver_components' and isinstance(value,str) and COMPONENT.fullmatch(value):
                        inspect = self.inspect(serial)
                        if value not in [v['component'] for v in inspect['screensavers']]:
                            raise PlanError('Ekran koruyucu cihazda bulunamadı.')
                        label = 'Ekran koruyucu'
                    else: raise PlanError('İzin verilmeyen ayar veya değer.')
                    action = {'type':kind,'namespace':namespace,'key':key,'label':label,
                              'after':{'present':True,'value':value}}
                    identity = (kind,namespace,key)
                elif kind == 'package':
                    package, value = request.get('package'),request.get('value')
                    meta = packages.get(package,{})
                    if not meta.get('eligible') or value not in ('disabled-user','enabled'):
                        raise PlanError('Bu pakete müdahale desteklenmiyor: '+str(package))
                    action = {'type':kind,'package':package,'label':meta.get('label',package),'after':value}
                    identity = (kind,package)
                    if meta.get('description'): warnings.append(meta['label']+': '+meta['description'])
                elif kind == 'launcher':
                    component = request.get('component')
                    if not isinstance(component,str) or not COMPONENT.fullmatch(component): raise PlanError('Geçersiz ana ekran.')
                    choices = self._components(d,'android.intent.action.MAIN',['-c','android.intent.category.HOME'])
                    if component not in choices: raise PlanError('Ana ekran cihazda kurulu veya etkin değil.')
                    action = {'type':kind,'label':'Varsayılan ana ekran','after':component}
                    identity = (kind,)
                    warnings.append('Bazı üreticiler ana ekran tercihini öncelik kurallarıyla geçersiz kılar. Tercih doğrulanamazsa işlem başarısız bildirilir; sistem launcher’ı otomatik kapatılmaz.')
                else: raise PlanError('İzin verilmeyen işlem türü.')
                if identity in seen: raise PlanError('Aynı ayar bir planda iki kez değiştirilemez.')
                seen.add(identity)
                action['before'] = self._read(d,action)
                if action['before'] != action['after']: actions.append(action)
            # Do not disable the chosen/current home even if a future catalogue includes it.
            try: home_package = self.launcher_state(d).split('/')[0]
            except Exception: home_package = None
            for a in actions:
                if a['type']=='package' and a['after']=='disabled-user' and a['package']==home_package:
                    raise PlanError('Kullanılan ana ekran kapatılamaz.')
            return self._new_plan(serial,info['identity'],actions,warnings=warnings)

    def apply(self, plan_id, confirmed=False, log=lambda message:None):
        with self.lock:
            if confirmed is not True: raise PlanError('İşlem planını inceleyip onaylayın.')
            plan = self.plans.get(plan_id)
            if not plan or plan['used'] or plan['expires_at'] < self.clock():
                raise PlanError('Planın süresi dolmuş veya kullanılmış. Yeni plan oluşturun.')
            d = self.device(plan['serial'])
            self.same_device(plan['device'], self.identity(d)['identity'])
            # Validate *all* before states before the first write (dependent guard steps excluded).
            for action in plan['actions']:
                if not action.get('dependent') and self._read(d,action) != action['before']:
                    raise PlanError('TV’deki durum değişmiş: '+action['label']+'. Planı yeniden oluşturun.')
            plan['used'] = True
            record = {k:copy.deepcopy(v) for k,v in plan.items() if k not in ('used','expires_at','serial')}
            record.update(id=uuid.uuid4().hex, plan_id=plan_id, status='running',created_at=now())
            for a in record['actions']: a['status']='pending'
            self.store.save(record)
            for action in record['actions']:
                try:
                    # Re-read at the last possible moment to detect external changes between steps.
                    if not action.get('dependent') and self._read(d,action) != action['before']:
                        raise PlanError('İşlem sırasında değer değişti: '+action['label'])
                    if action.get('dependent'):
                        # New APK defaults can be OEM-specific: capture the real baseline only after install.
                        action['before']=self._read(d,action)
                        action['baseline_captured']=True
                    action['status']='running'; self.store.save(record)
                    log(action['label']+' uygulanıyor…')
                    self._write(d,action,action['after'])
                    actual = self._read(d,action)
                    if actual != action['after']:
                        raise PlanError('Yazılan değer TV’den doğrulanamadı: '+action['label'])
                    action['status']='verified'; action['verified_at']=now(); self.store.save(record)
                except Exception as e:
                    action['status']='failed'; action['error']=str(e)
                    record['status']='partial'; record['error']=str(e)
                    self.store.save(record)
                    log('İşlem durdu. Tamamlanan adımlar saklandı; geçmişten geri alma planı oluşturabilirsiniz.')
                    return record
            record['status']='succeeded'; record['completed_at']=now(); self.store.save(record)
            if record.get('source'):
                original=self.store.get(record['source'])
                original['rolled_back_by']=record['id']; self.store.save(original)
            return record

    def rollback_plan(self, transaction_id, serial):
        with self.lock:
            original = self.store.get(transaction_id)
            if original.get('rolled_back_by'): raise PlanError('Bu işlem zaten geri alınmış.')
            if original.get('kind')=='rollback': raise PlanError('Geri alma kaydı tekrar geri alınamaz; yeni bakım planı oluşturun.')
            d = self.device(serial)
            info = self.identity(d)
            self.same_device(original['device'],info['identity'])
            actions=[]
            managed_guard = any(a['type']=='guard_apk' and a.get('status')!='pending' for a in original['actions'])
            if managed_guard and self._read(d,{'type':'guard_apk'})=='installed':
                # Even a STOPPED watcher may have a companion retrying in the background.
                # Stop that service before restoring permissions/settings or removing the APK.
                actions.append({'type':'guard_active','label':'Koruyucuyu ve yeniden denemelerini durdur',
                                'before':self._read(d,{'type':'guard_active'}),'after':'stopped'})
            for a in reversed(original['actions']):
                if a.get('status')=='pending' or (managed_guard and a['type']=='guard_active'): continue
                if a.get('dependent') and not a.get('baseline_captured'): continue
                action = copy.deepcopy(a)
                current = self._read(d,action)
                if current == a['before']: continue
                if current != a['after']:
                    raise PlanError('Geri alma çakışması: '+a['label']+' sonradan değişmiş. Otomatik üzerine yazılmayacak.')
                action.update(before=current,after=a['before'],label='Geri al: '+a['label'])
                action.pop('status',None); action.pop('error',None); action.pop('dependent',None)
                actions.append(action)
            return self._new_plan(serial,info['identity'],actions,kind='rollback',source=transaction_id,
                                  warnings=['Bu işlem yalnızca listelenen değerleri eski durumuna getirir.'])

    def guard_plan(self, serial, operation):
        with self.lock:
            d=self.device(serial)
            info=self.identity(d, writable=operation!='status')
            if info['identity'].get('profile') != PROFILE:
                raise PlanError('Bu koruyucu yalnızca tanınan TCL BeyondTV4 / RTD288O / Android 11 profili için kullanılabilir.')
            installed=self._read(d,{'type':'guard_apk'})=='installed'
            if operation=='status':
                state='not_installed'
                if installed:
                    try: state=self._read(d,{'type':'guard_active'})
                    except Exception: state='unknown'
                return {'installed':installed,'state':state,'checked_at':now()}
            if operation=='remove':
                for r in self.store.history():
                    if r.get('device',{}).get('serial_hash')==info['identity']['serial_hash'] and not r.get('rolled_back_by') and r.get('kind')!='rollback' and any(a['type']=='guard_apk' for a in r.get('actions',[])):
                        return self.rollback_plan(r['id'],serial)
                raise PlanError('TVCare kurulum yedeği bulunamadı. Önceden kurulu koruyucu otomatik kaldırılmayacak.')
            if operation!='install': raise PlanError('Geçersiz koruyucu işlemi.')
            if installed: raise PlanError('Koruyucu zaten kurulu. Mevcut APK’yı yedeksiz değiştirmek yerine durum kontrolünü kullanın.')
            if self._read(d,{'type':'guard_active'})!='stopped':
                raise PlanError('Önceden kalmış çalışan koruyucu bulundu; yeni kurulum otomatik yapılmayacak.')
            health=d.health()
            if not health.get('cam_wait_evidence'):
                raise PlanError('Mevcut loglarda ilgili CAM bekleme hatası doğrulanamadı; koruyucu kurulumu açılmadı.')
            apk=resources()/'guard/kilit-koruyucu.apk'
            if not apk.is_file(): raise PlanError('Bu dağıtımda koruyucu APK dosyası bulunmuyor.')
            old=d.read_setting('global','adb_allowed_connection_time')
            actions=[{'type':'guard_apk','label':'Kilit Koruyucu 1.1 kurulumu','before':'absent','after':'installed','apk_sha256':hashlib.sha256(apk.read_bytes()).hexdigest()},
                     {'type':'guard_appop','label':'Koruyucunun TV açılışında başlaması','before':'TV’den kurulum sonrası okunacak','after':'allow','dependent':True}]
            if old!={'present':True,'value':'0'}:
                actions.append({'type':'setting','namespace':'global','key':'adb_allowed_connection_time','label':'ADB anahtar süresini kaldır','before':old,'after':{'present':True,'value':'0'}})
            actions.append({'type':'guard_active','label':'Bekçiyi başlat ve canlı durumunu doğrula','before':'stopped','after':'running','dependent':True})
            return self._new_plan(serial,info['identity'],actions,warnings=[
                'TV’de koruyucunun ayrı ADB anahtarı için izin penceresi çıkacak; her zaman izin ver seçeneğini onaylayın.',
                'Kapanışta doğrulanan CAM beklemesi 5 saniyeyi aşarsa TV tamamen kapatılır. Sonraki açılış soğuk açılıştır.',
                'USB hata ayıklama açık kalmalı. ADB anahtarlarının süre sınırı bu cihazdaki tüm onaylı anahtarlar için kaldırılır.',
                'Önceki sürümün bu TV’deki kayıtlarında açılıştan sonra yaklaşık 100 saniyelik korumasız süre vardır; yeni sürümün canlı açılış testi ayrıca gerekir.'])
