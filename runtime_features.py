"""Small local resource sampler, monthly quotas and private break reminders."""
import asyncio
import shutil
import time
from pathlib import Path
from datetime import datetime
from usage import ROME

BREAKS=(
    'Ci concediamo una piccola pausa? Sono passati circa venti minuti. Un bicchiere d’acqua o qualcosa di caldo, uno sguardo fuori dalla finestra e qualche respiro tranquillo. Puoi tornare quando vuoi.',
    'Un momento per te: posa lo schermo, rilassa le spalle e prenditi qualcosa da bere. Non c’è fretta di risolvere tutto adesso. Quando vuoi, continuiamo.',
    'Piccola pausa? Dopo un po’ di conversazione può aiutare alzarsi, guardare lontano e respirare con calma. Alba può aspettare.',
)


def quota(store,uid,now=None):
    now=now or datetime.now(ROME)
    start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    end=start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1)
    rows=store.rows('SELECT token_limit FROM user_limits WHERE user_id=?',(uid,))
    limit=rows[0]['token_limit'] if rows else 0
    usage=store.rows('SELECT coalesce(sum(coalesce(input_tokens,0)+coalesce(output_tokens,0)),0) AS used, '
        'coalesce(sum(input_tokens IS NULL OR output_tokens IS NULL),0) AS unreported '
        'FROM token_usage WHERE user_id=? AND timestamp>=? AND timestamp<?',(uid,start.timestamp(),end.timestamp()))[0]
    return dict(month=start.strftime('%Y-%m'),limit=limit,used=usage['used'],unreported=usage['unreported'],
                remaining=max(0,limit-usage['used']) if limit else None,
                exhausted=bool(limit and usage['used']>=limit))


def touch_activity(store,uid,now=None):
    now=time.time() if now is None else now
    rows=store.rows('SELECT * FROM user_activity WHERE user_id=?',(uid,))
    if not rows or now-rows[0]['last_seen']>300:
        store.execute('INSERT OR REPLACE INTO user_activity VALUES(?,?,?,?,?)',(uid,now,now,0,''))
    else:
        store.execute('UPDATE user_activity SET last_seen=? WHERE user_id=?',(now,uid))
    return break_status(store,uid,now)


def break_status(store,uid,now=None):
    now=time.time() if now is None else now
    rows=store.rows('SELECT * FROM user_activity WHERE user_id=?',(uid,))
    if not rows or now-rows[0]['last_seen']>300: return None
    row=rows[0]; interval=int(store.setting('break_minutes','20'))*60
    if now-row['started']>=interval and (not row['notice_at'] or now-row['notice_at']>=interval):
        text=BREAKS[int(now//interval)%len(BREAKS)]
        if interval!=1200: text=text.replace('Sono passati circa venti minuti. ','')
        store.execute('UPDATE user_activity SET notice_at=?,notice=? WHERE user_id=?',(now,text,uid))
        row['notice_at'],row['notice']=now,text
    return {'id':row['notice_at'],'message':row['notice']} if row['notice_at'] else None


class Performance:
    def __init__(self,root,proc='/proc'):
        self.root,self.proc=Path(root),Path(proc)
        self.previous=None; self.snapshot={}; self.sample()

    def sample(self):
        cpu=None; ram={'total':None,'used':None,'percent':None}
        try:
            values=[int(x) for x in (self.proc/'stat').read_text().splitlines()[0].split()[1:9]]
            total=sum(values); idle=values[3]+(values[4] if len(values)>4 else 0)
            if self.previous:
                delta=total-self.previous[0]
                if delta>0: cpu=round(max(0,min(100,100*(1-(idle-self.previous[1])/delta))),1)
            self.previous=(total,idle)
            fields={line.split(':',1)[0]:int(line.split()[1])*1024 for line in (self.proc/'meminfo').read_text().splitlines() if ':' in line}
            total=fields['MemTotal']; used=total-fields['MemAvailable']
            ram=dict(total=total,used=used,percent=round(100*used/total,1))
        except (OSError,ValueError,KeyError,IndexError): pass
        disk=shutil.disk_usage(self.root)
        self.snapshot={'timestamp':time.time(),'cpu_percent':cpu,'ram':ram,
                       'disk':dict(total=disk.total,used=disk.used,free=disk.free,percent=round(100*disk.used/disk.total,1))}
        return self.snapshot

    async def run(self):
        while True:
            self.sample()
            await asyncio.sleep(2)


class Capacity:
    """One short presence lease per Telegram identity, shared across transports."""
    def __init__(self,limit=5,ttl=90):
        self.limit,self.ttl=limit,ttl; self.leases={}; self.waiting={}

    def clean(self,now,active=()):
        for uid,until in list(self.leases.items()):
            if until<=now and uid not in active: self.leases.pop(uid,None)
        for uid,stamp in list(self.waiting.items()):
            if now-stamp>self.ttl: self.waiting.pop(uid,None)

    def enter(self,uid,now=None,active=()):
        now=time.monotonic() if now is None else now; self.clean(now,active)
        if uid in self.leases:
            self.leases[uid]=now+self.ttl
        else:
            self.waiting.setdefault(uid,now)
            if len(self.leases)<self.limit and next(iter(self.waiting),uid)==uid:
                self.waiting.pop(uid,None); self.leases[uid]=now+self.ttl
            elif uid in self.waiting:
                self.waiting[uid]=now
        return self.status(uid,now,active)

    def status(self,uid,now=None,active=()):
        now=time.monotonic() if now is None else now; self.clean(now,active)
        return {'admitted':uid in self.leases,'online':len(self.leases),'max_online':self.limit,
                'position':list(self.waiting).index(uid)+1 if uid in self.waiting else None}

    def leave(self,uid):
        self.leases.pop(uid,None); self.waiting.pop(uid,None)
