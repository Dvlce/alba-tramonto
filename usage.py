"""Monthly accounting from backend-reported token counts, never estimated text lengths."""
import calendar
import re
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROME=ZoneInfo('Europe/Rome')


def monthly_usage(store,uid,month,all_users=False,now=None):
    if not isinstance(month,str) or not re.fullmatch(r'\d{4}-\d{2}',month):
        raise ValueError('Mese non valido.')
    year,number=map(int,month.split('-'))
    if not 2000<=year<=2100 or not 1<=number<=12:
        raise ValueError('Mese non valido.')
    start=datetime(year,number,1,tzinfo=ROME)
    end=datetime(year+(number==12),1 if number==12 else number+1,1,tzinfo=ROME)
    now=now or datetime.now(ROME)
    since=float(store.setting('token_tracking_since',str(time.time())))
    days={}
    for day in range(1,calendar.monthrange(year,number)[1]+1):
        date=start.replace(day=day)
        available=(date+timedelta(days=1)).timestamp()>since and date.date()<=now.date()
        days[date.strftime('%Y-%m-%d')]={'date':date.strftime('%Y-%m-%d'),
            'input_tokens':0,'output_tokens':0,'total_tokens':0,'requests':0,'unreported':0,
            'available':available,'partial':available and date.timestamp()<since,
            'future':date.date()>now.date()}
    condition='' if all_users else ' AND user_id=?'
    args=(start.timestamp(),end.timestamp(),*(() if all_users else (uid,)))
    cursor=store.db.execute('SELECT timestamp,input_tokens,output_tokens FROM token_usage WHERE timestamp>=? AND timestamp<?'+condition,args)
    for row in cursor:
        key=datetime.fromtimestamp(row['timestamp'],ROME).strftime('%Y-%m-%d')
        day=days[key]
        day['requests']+=1
        day['input_tokens']+=row['input_tokens'] or 0
        day['output_tokens']+=row['output_tokens'] or 0
        day['unreported']+=int(row['input_tokens'] is None or row['output_tokens'] is None)
        day['total_tokens']=day['input_tokens']+day['output_tokens']
    items=list(days.values())
    totals={field:sum(d[field] for d in items) for field in ('input_tokens','output_tokens','total_tokens','requests','unreported')}
    totals['active_days']=sum(d['requests']>0 for d in items)
    return {'month':month,'timezone':'Europe/Rome','today':now.strftime('%Y-%m-%d'),
            'tracking_since':datetime.fromtimestamp(since,ROME).isoformat(),
            'scope':'bot' if all_users else 'self','days':items,'totals':totals}
