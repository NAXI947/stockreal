"""Phase-0 readiness diagnostics; does not start jobs or approve calendars."""
import csv
import hashlib
import io
from datetime import date,datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from stockreal.stage0 import load

def calendar_status(path,reviewed_sha256,today):
    if not path.exists():return 'CALENDAR_MISSING'
    raw=path.read_bytes()
    if not reviewed_sha256 or hashlib.sha256(raw).hexdigest()!=reviewed_sha256:
        return 'CALENDAR_UNREVIEWED'
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if reader.fieldnames!=['date','is_open']:return 'CALENDAR_INVALID'
        days={}
        for row in reader:
            d=date.fromisoformat(row['date'])
            if row['date']!=d.isoformat() or d in days or row['is_open'] not in ('0','1') or None in row:
                return 'CALENDAR_INVALID'
            days[d]=row['is_open']=='1'
        if not days:return 'CALENDAR_INVALID'
        if max(days)<date(today.year,1,1):return 'CALENDAR_EXPIRED'
        d=date(today.year,1,1)
        while d<date(today.year+2,1,1):
            if d not in days:return 'CALENDAR_INCOMPLETE'
            d+=timedelta(days=1)
        return 'OPEN_DAY' if days[today] else 'CLOSED_DAY'
    except (ValueError,TypeError,KeyError,UnicodeError):
        return 'CALENDAR_INVALID'

def status(root,now=None):
    now=now or datetime.now(ZoneInfo('Asia/Shanghai'))
    today=now.astimezone(ZoneInfo('Asia/Shanghai')).date()
    policy=load(root/'config/runtime-policy.json')
    cal=calendar_status(root/'config/trade_calendar.csv',policy['calendar_reviewed_sha256'],today)
    # Phase-0 is diagnostic only; no caller can promote this to a running scheduler.
    return {'config_version':'R3.5','automatic_collection_enabled':False,'directional_signals_enabled':False,
            'calendar_status':cal,'blockers':['AUTO_COLLECTION_DISABLED_BY_OWNER','FIELD_CONTRACTS_UNVERIFIED'],
            'disabled_phase1_features':policy['disabled_phase1_features']}

if __name__=='__main__':
    import json
    print(json.dumps(status(Path('/workspace')),ensure_ascii=False))
