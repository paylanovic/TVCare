"""Isolated synthetic TV used for previews and contract tests. Never runs ADB."""
import copy
from .catalog import metadata, TCL_PROFILE


class DemoAdb:
    path='Demo — gerçek ADB kullanılmaz'
    def __init__(self):
        self.settings = {('global','window_animation_scale'):'1.0',('global','transition_animation_scale'):'1.0',('global','animator_duration_scale'):'1.0',('secure','screensaver_components'):'com.android.dreams.basic/.Colors'}
        self.package_states={'com.tcl.bi':'default','com.tcl.guard':'default','com.tcl.browser':'default','com.google.android.youtube.tvmusic':'default','com.google.android.apps.tv.launcherx':'default','com.spocky.projengmenu':'default','com.google.android.youtube.tv':'default','com.android.systemui':'default','com.google.android.katniss':'default'}
        self.home='com.google.android.apps.tv.launcherx/.home.HomeActivity'
    def available(self): return True
    def version(self): return 'TVCare simülasyonu — fiziksel cihaz yok'
    def devices(self): return [{'serial':'demo-tv','state':'device','details':'model:TCL_Demo yalnızca_sentetik'}]
    def discover(self): return []
    def connect(self, endpoint): raise ValueError('Demo modunda gerçek cihaz bağlantısı kapalıdır. Uygulamayı --demo olmadan başlatın.')
    def pair(self,endpoint,code): return self.connect(endpoint)
    def shell(self, serial, args, timeout=20):
        if serial!='demo-tv': raise ValueError('Demo cihazı bulunamadı.')
        if args[:3]==['cmd','package','query-activities']:
            return 'com.google.android.apps.tv.launcherx/.home.HomeActivity\ncom.spocky.projengmenu/.ui.home.MainActivity'
        if args[:3]==['cmd','package','query-services']:
            return 'com.android.dreams.basic/.Colors\ncom.android.dreams.basic/.Dreams'
        if args[:3]==['cmd','role','get-role-holders']: return self.home.split('/')[0]
        if args[:3]==['cmd','package','resolve-activity']: return self.home
        if args[:3]==['cmd','package','set-home-activity']:
            self.home=args[-1]; return 'Success'
        if args[0]=='settings':
            op, namespace, key = args[3:6]
            if op=='put': self.settings[(namespace,key)] = args[6]
            elif op=='delete': self.settings.pop((namespace,key),None)
            return ''
        if args[:3]==['pm','list','packages']:
            return '\n'.join('package:'+p for p in self.package_states if args[-1] in p)
        if args[0]=='pm':
            states={'enable':'enabled','disable-user':'disabled-user','default-state':'default','disable':'disabled','disable-until-used':'disabled-until-used'}
            if args[1] in states:
                self.package_states[args[-1]]=states[args[1]]; return 'Success'
        raise ValueError('Demo bu işlemi simüle etmiyor: '+str(args))
    def install(self,serial,apk): raise ValueError('Demo modunda APK kurulmaz.')


class DemoDevice:
    def __init__(self,adb,serial): self.adb,self.serial=adb,serial
    def inspect(self):
        return {'identity':{'manufacturer':'TCL','model':'TCL Google TV · Örnek cihaz','device':'BeyondTV4','platform':'rtd288o','android':'11','sdk':'30','fingerprint':'TVCare/synthetic/demo','serial_hash':'d'*64,'profile':TCL_PROFILE},'capabilities':{'stable_identity':True,'is_tv':True,'owner_user':True,'current_user':0},'read_errors':[]}
    def read_setting(self,namespace,key):
        return {'present':(namespace,key) in self.adb.settings,'value':self.adb.settings.get((namespace,key))}
    def package_state(self,package): return self.adb.package_states[package]
    def packages(self):
        return [{'id':p,'enabled':s not in ('disabled','disabled-user'),'state':s,**metadata(p,TCL_PROFILE)} for p,s in sorted(self.adb.package_states.items())]
    def health(self):
        return {'uptime_seconds':2478,'memory':{'total_kb':2097152,'available_kb':417916,'free_kb':123744,'swap_total_kb':1048572,'swap_free_kb':899836,'swap_used_kb':148736},'storage':{'total_kb':8388608,'used_kb':3271557,'available_kb':5117051,'used_percent':39},'events':{'scope':'last_500_entries','counts':{'am_anr':0,'am_crash':0,'am_kill':11,'am_proc_start':51,'killinfo':0}},'warnings':[],'cam_suspend':None,'ci_cam_state':None,'cam_wait_evidence':False,'cam_evidence_lines':[],'read_errors':[],'synthetic':True}
