"""Bounded, declarative lab data and isolated ngspice jobs. No user netlists or shell commands."""
import asyncio
import ipaddress
import json
import math
import os
import re
import secrets
import shutil
import signal
import tempfile
import time
from pathlib import Path
from aiohttp import web

PORTS={'resistor':2,'capacitor':2,'inductor':2,'diode':2,'voltage':2,'ac':2,'ground':1,'switch':2,'npn':3,'opamp':5,
       'battery':2,'current':2,'function':2,'pot':3,'led':2,'zener':2,'pnp':3,'nmos':3,'pmos':3,'transformer':4,
       'ammeter':2,'voltmeter':2,'scope':2,'probe':1,'fuse':2,'and':5,'or':5,'not':4}
NODE_TYPES={'router','switch','pc','server','laptop','accesspoint','firewall','cloud','printer'}

def numeric(value,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high: raise ValueError('Parametro numerico fuori intervallo.')
    return value
def label(value,size=80):
    if not isinstance(value,str) or len(value)>size: raise ValueError('Testo non valido.')
    return value
def key(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value): raise ValueError('Identificatore non valido.')
    return value
def validate_params(value):
    if not isinstance(value,dict) or set(value)-{'frequency','amplitude','offset','duty','wave','ratio','closed'}: raise ValueError('Parametri componente non validi.')
    result={}
    for name,low,high in (('frequency',.001,1e9),('amplitude',0,1e6),('offset',-1e6,1e6),('duty',.01,.99),('ratio',.01,.99)):
        if name in value: result[name]=numeric(value[name],low,high)
    if 'wave' in value:
        if value['wave'] not in ('sine','square','triangle'): raise ValueError('Forma d’onda non valida.')
        result['wave']=value['wave']
    if 'closed' in value:
        if type(value['closed']) is not bool: raise ValueError('Stato interruttore non valido.')
        result['closed']=value['closed']
    return result
def validate_network(value):
    if not isinstance(value,dict) or not isinstance(value.get('nodes'),list) or not isinstance(value.get('links'),list) or len(value['nodes'])>80 or len(value['links'])>160: raise ValueError('Topologia non valida.')
    nodes=[]; ids=set()
    def interface(value):
        value=label(value,50).strip()
        if value:
            try: ipaddress.IPv4Interface(value)
            except ValueError: raise ValueError('Indirizzo IPv4/prefisso non valido.')
        return value
    for item in value['nodes']:
        if not isinstance(item,dict) or not isinstance(item.get('type'),str) or item['type'] not in NODE_TYPES: raise ValueError('Dispositivo di rete non valido.')
        ident=key(item.get('id'))
        if ident in ids: raise ValueError('Dispositivo duplicato.')
        ids.add(ident); gateway=label(item.get('gateway',''),50).strip()
        if gateway:
            try: ipaddress.IPv4Address(gateway)
            except ValueError: raise ValueError('Gateway non valido.')
        interfaces=item.get('interfaces',[])
        if not isinstance(interfaces,list) or len(interfaces)>8: raise ValueError('Massimo otto interfacce.')
        enabled=item.get('enabled',True)
        if type(enabled) is not bool or type(item.get('vlan',1)) is not int: raise ValueError('Stato/VLAN non valido.')
        nodes.append({'id':ident,'type':item['type'],'name':label(item.get('name','Dispositivo'),60),'x':numeric(item.get('x'),40,960),'y':numeric(item.get('y'),40,600),
                      'ip':interface(item.get('ip','')),'gateway':gateway,'vlan':numeric(item.get('vlan',1),1,4094),'enabled':enabled,'interfaces':[interface(ip) for ip in interfaces]})
    links=[]; seen=set()
    for item in value['links']:
        if not isinstance(item,dict) or not isinstance(item.get('from'),str) or not isinstance(item.get('to'),str) or item.get('from') not in ids or item.get('to') not in ids or item['from']==item['to']: raise ValueError('Collegamento di rete non valido.')
        ident=key(item.get('id'))
        if ident in seen: raise ValueError('Collegamento duplicato.')
        seen.add(ident); kind=item.get('kind','ethernet'); enabled=item.get('enabled',True)
        if kind not in ('ethernet','fiber','serial','wifi') or type(enabled) is not bool: raise ValueError('Tipo di collegamento non valido.')
        links.append({'id':ident,'from':item['from'],'to':item['to'],'kind':kind,'enabled':enabled})
    return {'nodes':nodes,'links':links}

def component_value(value,default,positive=False):
    """Accept common SI suffixes and units; never emit the original text in a netlist."""
    value=str(value).strip().replace('Ω','ohm').replace('µ','u').replace('μ','u').replace(',','.')
    if not value: return default
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[pnuUmMkKgGtT]?)\s*(?:ohms?|[vVaAfFhH]|Hz)?',value)
    if not match: raise ValueError('Valore non numerico: usa per esempio 1 kΩ, 10 µF, 5 V, 1 kHz.')
    suffix=match[2]; factors={'':1,'p':1e-12,'n':1e-9,'u':1e-6,'U':1e-6,'m':1e-3,'k':1e3,'K':1e3,'M':1e6,'meg':1e6,'g':1e9,'G':1e9,'t':1e12,'T':1e12}
    number=float(match[1])*factors[suffix]
    return numeric(number,1e-12 if positive else -1e9,1e12)

def simulation_settings(value):
    if not isinstance(value,dict) or set(value)-{'analysis','stop','samples','start','end','points','dc_start','dc_end'}: raise ValueError('Opzioni simulazione non valide.')
    analysis=value.get('analysis','tran')
    if analysis not in ('op','tran','ac','dc'): raise ValueError('Analisi non valida.')
    result={'analysis':analysis}
    if analysis=='tran':
        result.update(stop=numeric(value.get('stop',.01),1e-9,100),samples=int(numeric(value.get('samples',600),20,2000)))
    elif analysis=='ac':
        result.update(start=numeric(value.get('start',10),.001,1e9),end=numeric(value.get('end',100000),.001,1e9),points=int(numeric(value.get('points',40),5,100)))
        if result['start']>=result['end'] or math.log10(result['end']/result['start'])*result['points']>2000: raise ValueError('Intervallo AC troppo grande.')
    elif analysis=='dc':
        result.update(dc_start=numeric(value.get('dc_start',0),-1000,1000),dc_end=numeric(value.get('dc_end',10),-1000,1000),samples=int(numeric(value.get('samples',100),10,500)))
        if result['dc_start']>=result['dc_end']: raise ValueError('Intervallo DC non valido.')
    return result

def build_netlist(circuit,options):
    """Union terminal connections, then generate only fixed SPICE statements and finite numbers."""
    options=simulation_settings(options); parts=circuit['components']
    if not parts: raise ValueError('Aggiungi componenti e collegamenti prima di simulare.')
    parent={}; zero='__ground__'; parent[zero]=zero
    for part in parts:
        if part['type'] not in PORTS: raise ValueError('Componente non supportato.')
        for port in range(PORTS[part['type']]): parent[(part['id'],port)]=(part['id'],port)
    def find(value):
        while parent[value]!=value: parent[value]=parent[parent[value]]; value=parent[value]
        return value
    def union(a,b): parent[find(a)]=find(b)
    grounds=[p for p in parts if p['type']=='ground']
    if not grounds: raise ValueError('Inserisci la massa e collegala al circuito.')
    for p in grounds: union((p['id'],0),zero)
    for wire in circuit['wires']: union((wire['from']['component'],wire['from']['port']),(wire['to']['component'],wire['to']['port']))
    roots={find(zero):'0'}; counts={}; rows=['Tramonto: generated circuit']; labels={}; probes=[]; first_dc=None
    def node(part,index):
        root=find((part['id'],index))
        if root not in roots: roots[root]='n'+str(len(roots)); labels[roots[root]]=part['label']+' · terminale '+str(index+1)
        return roots[root]
    def name(prefix): counts[prefix]=counts.get(prefix,0)+1; return prefix+str(counts[prefix])
    def fmt(number): return format(number,'.12g')
    for p in parts:
        kind=p['type']; pins=[node(p,i) for i in range(PORTS[kind])]; params=validate_params(p.get('params',{})); value=p.get('value','')
        if kind=='ground': continue
        a,b=pins[:2] if len(pins)>1 else (pins[0],'0')
        if kind in ('resistor','capacitor','inductor','fuse'):
            default={'resistor':1000,'capacitor':1e-6,'inductor':.001,'fuse':.01}[kind]; val=component_value(value,default,True)
            rows.append(f'{name({"resistor":"R","capacitor":"C","inductor":"L","fuse":"R"}[kind])} {a} {b} {fmt(val)}')
        elif kind in ('voltage','battery','current','ammeter'):
            prefix='I' if kind=='current' else 'V'; val=0 if kind=='ammeter' else component_value(value,5 if prefix=='V' else .001)
            ident=name(prefix); rows.append(f'{ident} {a} {b} DC {fmt(val)}')
            if kind in ('voltage','battery') and first_dc is None: first_dc=ident
            if kind=='ammeter': probes.append((f'i({ident})',p['label']+' · corrente','A'))
        elif kind in ('ac','function'):
            frequency=params['frequency'] if 'frequency' in params else numeric(component_value(value,1000,True),.001,1e9); amplitude=params.get('amplitude',1); offset=params.get('offset',0); period=1/frequency; wave=params.get('wave','sine')
            source=f'SIN({fmt(offset)} {fmt(amplitude)} {fmt(frequency)})'
            if wave=='square': source=f'PULSE({fmt(offset-amplitude)} {fmt(offset+amplitude)} 0 {fmt(period*.001)} {fmt(period*.001)} {fmt(period*params.get("duty",.5))} {fmt(period)})'
            if wave=='triangle': source=f'PULSE({fmt(offset-amplitude)} {fmt(offset+amplitude)} 0 {fmt(period*.499)} {fmt(period*.499)} {fmt(period*.001)} {fmt(period)})'
            rows.append(f'{name("V")} {a} {b} DC {fmt(offset)} AC {fmt(amplitude)} {source}')
        elif kind in ('diode','led','zener'):
            rows.append(f'{name("D")} {a} {b} {kind.upper()}')
        elif kind in ('npn','pnp'):
            base,collector,emitter=pins; rows.append(f'{name("Q")} {collector} {base} {emitter} {kind.upper()}')
        elif kind in ('nmos','pmos'):
            gate,drain,source=pins; rows.append(f'{name("M")} {drain} {gate} {source} {source} {kind.upper()} W=10u L=1u')
        elif kind=='pot':
            total=component_value(value,10000,True); ratio=params.get('ratio',.5)
            rows.extend([f'{name("R")} {pins[0]} {pins[1]} {fmt(total*ratio)}',f'{name("R")} {pins[1]} {pins[2]} {fmt(total*(1-ratio))}'])
        elif kind=='switch': rows.append(f'{name("R")} {a} {b} {".001" if params.get("closed",value.lower() in ("chiuso","closed","on")) else "1e12"}')
        elif kind=='transformer':
            l1,l2=name('L'),name('L'); inductance=component_value(value,.01,True)
            rows.extend([f'{l1} {pins[0]} {pins[1]} {fmt(inductance)}',f'{l2} {pins[2]} {pins[3]} {fmt(inductance)}',f'{name("K")} {l1} {l2} .99'])
        elif kind=='opamp':
            minus,plus,out,vplus,vminus=pins
            rows.append(f'{name("B")} {out} 0 V=min(v({vplus}),max(v({vminus}),1e5*(v({plus})-v({minus}))))')
        elif kind in ('and','or','not'):
            if kind=='not': inp,out,high,low=pins; expr=f'1-u(v({inp})-(v({high})+v({low}))/2)'
            else:
                inp1,inp2,out,high,low=pins; terms=[f'u(v({pin})-(v({high})+v({low}))/2)' for pin in (inp1,inp2)]; expr=('*'.join(terms) if kind=='and' else f'min(1,{terms[0]}+{terms[1]})')
            rows.append(f'{name("B")} {out} {low} V=(v({high})-v({low}))*({expr})')
        elif kind in ('probe','voltmeter','scope'): probes.append((f'v({a},{b})',p['label'],'V'))
    if not any(p['type'] in ('voltage','battery','current','ac','function') for p in parts): raise ValueError('Serve almeno un generatore collegato.')
    rows += ['.model DIODE D(Is=2.52n N=1.75 Rs=.568 Cjo=4p Tt=20n)', '.model LED D(Is=1e-20 N=2 Rs=10)', '.model ZENER D(Is=1n N=1 Rs=1 Bv=5.1 Ibv=1m)',
             '.model NPN NPN(Is=1e-14 Bf=100 Vaf=100)', '.model PNP PNP(Is=1e-14 Bf=100 Vaf=100)', '.model NMOS NMOS(Level=1 Vto=1 Kp=100u)', '.model PMOS PMOS(Level=1 Vto=-1 Kp=100u)', '.options numdgt=12', '.control','set noaskquit','set wr_singlescale','set wr_vecnames','set numdgt=12']
    analysis=options['analysis']
    if analysis=='tran': rows.append('tran '+fmt(options['stop']/options['samples'])+' '+fmt(options['stop'])+' 0 '+fmt(options['stop']/options['samples']))
    elif analysis=='ac': rows.append(f'ac dec {options["points"]} {fmt(options["start"])} {fmt(options["end"])}')
    elif analysis=='dc':
        if not first_dc: raise ValueError('La scansione DC richiede un generatore DC o una batteria.')
        rows.append(f'dc {first_dc} {fmt(options["dc_start"])} {fmt(options["dc_end"]+abs(options["dc_end"]-options["dc_start"])/(options["samples"]-1)*1e-7)} {fmt((options["dc_end"]-options["dc_start"])/(options["samples"]-1))}')
    else: rows.append('op')
    traces=probes[:6] or [(f'v({node})',description,'V') for node,description in list(labels.items())[:6]]
    if not traces: raise ValueError('Nessun nodo da misurare; controlla i collegamenti alla massa.')
    expressions=[f'mag({expr})' if analysis=='ac' else expr for expr,_,_ in traces]
    rows += ['wrdata result.dat '+' '.join(expressions),'quit','.endc','.end']
    return {'netlist':'\n'.join(rows)+'\n','traces':[{'name':description,'unit':unit} for _,description,unit in traces],'options':options,'nodes':labels}

class Spice:
    def __init__(self,root): self.root=Path(root); self.lock=asyncio.Lock()
    @property
    def available(self): return bool(shutil.which('bwrap') and shutil.which('ngspice') and (self.root/'spice_worker.py').is_file())
    async def run(self,prepared):
        if not self.available: raise ValueError('ngspice o il sandbox non sono disponibili sul server.')
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix='tramonto-spice-') as folder:
                work=Path(folder); (work/'circuit.cir').write_text(prepared['netlist']); (work/'metadata.json').write_text(json.dumps(prepared['traces']))
                args=['bwrap','--unshare-all','--die-with-parent','--new-session','--ro-bind','/usr','/usr','--symlink','usr/lib','/lib','--symlink','usr/bin','/bin',
                      '--dir','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/etc','--bind',str(work),'/work','--ro-bind',str(self.root/'spice_worker.py'),'/worker.py','--chdir','/work','/usr/bin/python3','/worker.py']
                if Path('/lib64').exists(): args[args.index('--dev'):args.index('--dev')]=['--symlink','usr/lib64','/lib64']
                process=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,
                    env={'PATH':'/usr/bin:/bin','HOME':'/tmp','LC_ALL':'C','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1'},start_new_session=True)
                try: await asyncio.wait_for(process.wait(),12)
                except (asyncio.TimeoutError,asyncio.CancelledError):
                    try: os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    await process.wait(); raise
                result=work/'response.json'
                if process.returncode!=0 or not result.is_file() or result.stat().st_size>2000000: raise ValueError('La simulazione non è riuscita: controlla massa, collegamenti e valori.')
                data=json.loads(result.read_text())
                if 'error' in data: raise ValueError(data['error'])
                return {**data,'engine':'ngspice','analysis':prepared['options']['analysis'],'netlist':prepared['netlist'],'nodes':prepared['nodes']}

def setup_labs(app,service,admin,owned,body):
    spice=Spice(service.settings.root); jobs={}
    service.spice_jobs=jobs
    async def start(request):
        uid=admin(request); value=await body(request); record=owned('notes',value.get('note_id'),uid); prepared=build_netlist(json.loads(record['content'])['circuit'],value.get('options',{}))
        if request.path.endswith('/netlist'): return web.json_response(prepared)
        if not spice.available: return web.json_response({'error':'Il simulatore ngspice isolato non è disponibile.'},status=503)
        if any(not entry['task'].done() for entry in jobs.values()): return web.json_response({'error':'Una simulazione è già in corso. Attendi o interrompila.'},status=429)
        for ident in list(jobs):
            if jobs[ident]['task'].done() and (len(jobs)>=20 or time.monotonic()-jobs[ident]['started']>900):
                task=jobs.pop(ident)['task']
                if not task.cancelled(): task.exception()
        ident=secrets.token_urlsafe(18); identity=request['identity']; entry={'uid':uid,'note':record['id'],'digest':identity['digest'],'started':time.monotonic()}
        async def simulate():
            try: return await spice.run(prepared)
            except asyncio.TimeoutError: return {'error':'Simulazione fermata dopo 12 secondi: riduci complessità o intervallo.'}
            except ValueError as exc: return {'error':str(exc)}
            except (OSError,RuntimeError): return {'error':'Il simulatore non è disponibile. Controlla la configurazione del sandbox.'}
        entry['task']=asyncio.create_task(simulate()); jobs[ident]=entry; service.store.audit(uid,'spice_start',uid)
        return web.json_response({'job_id':ident},status=202)
    async def job(request):
        uid=admin(request); entry=jobs.get(request.match_info['id'])
        if not entry or entry['uid']!=uid: raise PermissionError()
        owned('notes',entry['note'],uid); task=entry['task']
        if request.method=='POST':
            task.cancel(); await asyncio.gather(task,return_exceptions=True); service.store.audit(uid,'spice_cancel',uid)
        if task.cancelled(): return web.json_response({'done':True,'cancelled':True})
        if not task.done(): return web.json_response({'done':False,'elapsed':round(time.monotonic()-entry['started'],1)})
        return web.json_response({'done':True,'result':task.result()})
    async def capabilities(request):
        admin(request); return web.json_response({'spice_available':spice.available,'analyses':['op','tran','ac','dc'],'components':list(PORTS),'network':'didactic_ipv4','timeout_seconds':12})
    async def cleanup(_):
        tasks=[entry['task'] for entry in jobs.values() if not entry['task'].done()]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    app.add_routes([web.get('/api/tramonto/labs',capabilities),web.post('/api/tramonto/netlist',start),web.post('/api/tramonto/simulations',start),
                    web.get('/api/tramonto/simulations/{id}',job),web.post('/api/tramonto/simulations/{id}/cancel',job)])
    app.on_cleanup.append(cleanup)
