"""Deliberately small support report: no raw log, package inventory or network IDs."""
from . import __version__
from .store import now


def sanitize_report(data, demo=False):
    identity = data.get('identity') or data.get('device') or {}
    result={'app':'TVCare','version':__version__,'generated_at':now(),'evidence':'synthetic_demo' if demo else 'device_readings',
            'device':{key:identity.get(key) for key in ('manufacturer','model','device','platform','android','sdk','profile')},
            'privacy':'IP, seri numarası, cihaz kimlik özeti, ham log ve kurulu uygulama listesi çıkarıldı.'}
    if 'health' in data:
        h=data['health']
        def numeric(value): return value if isinstance(value,(int,float)) and not isinstance(value,bool) else None
        result['health']={k:numeric(h.get(k)) for k in ('uptime_seconds','cam_wait_duration_seconds')}
        result['health']['cam_wait_evidence']=h.get('cam_wait_evidence') is True
        result['health']['memory']={k:numeric((h.get('memory') or {}).get(k)) for k in ('total_kb','available_kb','free_kb','swap_total_kb','swap_free_kb','swap_used_kb')}
        result['health']['storage']={k:numeric((h.get('storage') or {}).get(k)) for k in ('total_kb','used_kb','available_kb','used_percent')}
        result['health']['events']={'scope':'last_500_entries','counts':{k:numeric(((h.get('events') or {}).get('counts') or {}).get(k)) for k in ('am_anr','am_crash','am_kill','am_proc_start','killinfo')}}
        for section in ('memory','storage','events'):
            if not isinstance(h.get(section),dict): result['health'][section]=None
        result['read_error_count']=len(h.get('read_errors',[]))
        result['inspected_at']=data.get('inspected_at')
    if 'actions' in data:
        result['transaction']={'id':data.get('id'),'created_at':data.get('created_at'),'status':data.get('status'),'kind':data.get('kind'),
          'actions':[{'type':a.get('type'),'status':a.get('status'),'verified_at':a.get('verified_at')} for a in data['actions']]}
    return result
