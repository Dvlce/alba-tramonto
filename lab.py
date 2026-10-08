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
       'ammeter':2,'voltmeter':2,'scope':4,'probe':1,'fuse':2,'and':5,'or':5,'not':4,'junction':1,'nand':5,'nor':5,'xor':5,'xnor':5,'summer':4,'summer3':4}
# Fixed manufacturer model, TI SLOJ069: https://www.ti.com/lit/zip/sloj069
TL081_MODEL = '''* TL081 OPERATIONAL AMPLIFIER "MACROMODEL" SUBCIRCUIT
* CREATED USING PARTS RELEASE 4.01 ON 06/16/89 AT 13:08
* (REV N/A)      SUPPLY VOLTAGE: +/-15V
* CONNECTIONS:   NON-INVERTING INPUT
*                | INVERTING INPUT
*                | | POSITIVE POWER SUPPLY
*                | | | NEGATIVE POWER SUPPLY
*                | | | | OUTPUT
*                | | | | |
.SUBCKT TL081    1 2 3 4 5
*
  C1   11 12 3.498E-12
  C2    6  7 15.00E-12
  DC    5 53 DX
  DE   54  5 DX
  DLP  90 91 DX
  DLN  92 90 DX
  DP    4  3 DX
  EGND 99  0 POLY(2) (3,0) (4,0) 0 .5 .5
  FB    7 99 POLY(5) VB VC VE VLP VLN 0 4.715E6 -5E6 5E6 5E6 -5E6
  GA    6  0 11 12 282.8E-6
  GCM   0  6 10 99 8.942E-9
  ISS   3 10 DC 195.0E-6
  HLIM 90  0 VLIM 1K
  J1   11  2 10 JX
  J2   12  1 10 JX
  R2    6  9 100.0E3
  RD1   4 11 3.536E3
  RD2   4 12 3.536E3
  RO1   8  5 150
  RO2   7 99 150
  RP    3  4 2.143E3
  RSS  10 99 1.026E6
  VB    9  0 DC 0
  VC    3 53 DC 2.200
  VE   54  4 DC 2.200
  VLIM  7  8 DC 0
  VLP  91  0 DC 25
  VLN   0 92 DC 25
.MODEL DX D(IS=800.0E-18)
.MODEL JX PJF(IS=15.00E-12 BETA=270.1E-6 VTO=-1)
.ENDS
'''

# Bounded conversion into editable components. Imported SPICE is parsed as data,
# never passed to ngspice; model/control/include statements cannot execute.
IMPORT_MAX_FILE = 8 * 1024 * 1024
IMPORT_MAX_XML = 12 * 1024 * 1024

# Altered Python implementation of Mark Adler's blast.c (PKWare DCL decoder).
# Copyright (C) 2003, 2012, 2013 Mark Adler. https://github.com/madler/zlib/contrib/blast
# This software is provided 'as-is', without any express or implied
# warranty. In no event will the author be held liable for any damages
# arising from the use of this software.
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
# 1. The origin of this software must not be misrepresented; you must not
#    claim that you wrote the original software. If you use this software
#    in a product, an acknowledgment in the product documentation would be
#    appreciated but is not required.
# 2. Altered source versions must be plainly marked as such, and must not be
#    misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source distribution.
# Mark Adler madler@alumni.caltech.edu

def _dcl_table(compact):
    lengths=[b & 15 for b in compact for _ in range((b >> 4)+1)]
    return [lengths.count(i) for i in range(14)],sorted(range(len(lengths)),key=lambda i:(lengths[i],i))
_DCL_LIT=_dcl_table([11,124,8,7,28,7,188,13,76,4,10,8,12,10,12,10,8,23,8,9,7,6,7,8,7,6,55,8,23,24,12,11,7,9,11,12,6,7,22,5,7,24,6,11,9,6,7,22,7,11,38,7,9,8,25,11,8,11,9,12,8,12,5,38,5,38,5,11,7,5,6,21,6,10,53,8,7,24,10,27,44,253,253,253,252,252,252,13,12,45,12,45,12,61,12,45,44,173])
_DCL_LEN=_dcl_table([2,35,36,53,38,23]);_DCL_DIST=_dcl_table([2,20,53,230,247,151,248])

def _dcl_explode(data,expected,deadline):
    pos=buf=available=0
    def bits(n):
        nonlocal pos,buf,available
        while available<n:
            if pos>=len(data): raise ValueError('File Multisim troncato.')
            buf|=data[pos]<<available;pos+=1;available+=8
        v=buf&((1<<n)-1);buf>>=n;available-=n;return v
    def code(table):
        counts,symbols=table;v=first=index=0
        for length in range(1,14):
            v|=bits(1)^1;count=counts[length]
            if v<first+count:return symbols[index+v-first]
            index+=count;first=(first+count)<<1;v<<=1
        raise ValueError('Compressione Multisim non valida.')
    literal,dictionary=bits(8),bits(8)
    if literal not in (0,1) or dictionary not in (4,5,6):raise ValueError('Compressione Multisim non riconosciuta.')
    out=bytearray();base=[3,2,4,5,6,7,8,9,10,12,16,24,40,72,136,264];extra=[0]*8+[1,2,3,4,5,6,7,8];operations=0
    while True:
        operations+=1
        if operations%1024==0 and time.monotonic()>deadline:raise ValueError('File troppo complesso da convertire: esporta una netlist .cir.')
        if bits(1):
            c=code(_DCL_LEN);length=base[c]+bits(extra[c])
            if length==519:break
            n=2 if length==2 else dictionary;distance=(code(_DCL_DIST)<<n)+bits(n)+1
            if distance>len(out) or len(out)+length>expected:raise ValueError('Blocco Multisim danneggiato.')
            # Repeated chunks preserve overlapping copies without a byte-wise loop.
            pattern=bytes(out[-distance:]);out.extend((pattern*((length+distance-1)//distance))[:length])
        else:
            if len(out)>=expected:raise ValueError('Dimensione Multisim non valida.')
            out.append(code(_DCL_LIT) if literal else bits(8))
    if len(out)!=expected:raise ValueError('Dimensione Multisim non corrispondente.')
    return bytes(out)

def _multisim_xml(data):
    import struct
    for magic in (b'MSMCompressedElectronicsWorkbenchXML',b'CompressedElectronicsWorkbenchXML'):
        if data.startswith(magic):
            p=len(magic)
            if len(data)<p+8:raise ValueError('File Multisim troncato.')
            total,reserved=struct.unpack_from('<II',data,p);p+=8
            if reserved or not 0<total<=IMPORT_MAX_XML:raise ValueError('Progetto Multisim troppo grande o non valido (massimo 12 MB decompressi).')
            out=bytearray();deadline=time.monotonic()+6;blocks=0
            while p<len(data):
                if p+8>len(data):raise ValueError('File Multisim troncato.')
                size,compressed=struct.unpack_from('<II',data,p);p+=8;blocks+=1
                if blocks>16 or not 0<size<=900000 or not 0<compressed<=IMPORT_MAX_FILE or p+compressed>len(data) or len(out)+size>total:raise ValueError('Blocco Multisim non valido.')
                out.extend(_dcl_explode(memoryview(data)[p:p+compressed],size,deadline));p+=compressed
            if len(out)!=total:raise ValueError('File Multisim incompleto.')
            return bytes(out)
    if data.lstrip().startswith(b'<?xml') or data.lstrip().startswith(b'<MSMElectronicsWorkbench'):return data
    raise ValueError('Formato Multisim non riconosciuto. Apri il file in Multisim e usa Transfer → Export netlist (.cir).')

def _ms_text(value):
    value=value or ''
    if value.startswith('&ASC'):return value[4:]
    if value.startswith('&UNI'):return re.sub(r'_uc1([0-9a-fA-F]{4})',lambda m:chr(int(m[1],16)),value[4:])
    return value

def _spice_number(value):
    # SPICE M means milli, unlike SI M: do not confuse m and meg during import.
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(meg|[tgkmunpf]?)(?:ohms?|[vahf]|hz)?',value.strip(),re.I)
    if not match:raise ValueError('Valore SPICE non convertibile: '+value[:40])
    factors={'':1,'t':1e12,'g':1e9,'meg':1e6,'k':1e3,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15}
    return numeric(float(match[1])*factors[match[2].lower()],-1e12,1e12)

def _import_display(number,unit):
    if number==0:return '0 '+unit
    for suffix,factor in [('G',1e9),('M',1e6),('k',1e3),('',1),('m',1e-3),('µ',1e-6),('n',1e-9),('p',1e-12)]:
        if abs(number)>=factor or suffix=='p':return format(number/factor,'.10g')+' '+suffix+unit
    return '0 '+unit

def _import_part(ident,kind,value='',params=None,x=None,y=None,rotation=0):
    return {'id':ident,'type':kind,'label':ident,'value':value,'rotation':rotation,'x':x,'y':y,**({'params':validate_params(params)} if params is not None else {})}

def _import_connect(parts,nets):
    """One star per electrical net; same-label grounds are electrically unified."""
    wires=[];count=0;used={p['id'] for p in parts}
    def fresh(prefix):
        candidate=prefix;index=0
        while candidate in used:index+=1;candidate=prefix+'_'+str(index)
        used.add(candidate);return candidate
    for node,endpoints in nets.items():
        endpoints=list(dict.fromkeys(endpoints))
        if node=='0' and not any(next(p for p in parts if p['id']==ident)['type']=='ground' for ident,_ in endpoints):
            ground=_import_part(fresh('GND_import'),'ground',x=100,y=max((p['y'] or 100 for p in parts),default=400)+100);parts.append(ground);endpoints.append((ground['id'],0))
        if len(endpoints)<2:continue
        # A dedicated junction gives each branch a visible, movable node.
        if len(endpoints)>2:
            related=[next(p for p in parts if p['id']==ident) for ident,_ in endpoints]
            j=_import_part(fresh('J_import_'+str(count)),'junction',x=sum(p['x'] for p in related)/len(related),y=max(p['y'] for p in related)+80);j['label']='';parts.append(j);anchor=(j['id'],0)
        else:anchor=endpoints.pop(0)
        for end in endpoints:
            count+=1;wires.append({'id':'import_wire_'+str(count),'from':{'component':anchor[0],'port':anchor[1]},'to':{'component':end[0],'port':end[1]},'color':'#161b23'})
    if len(parts)>100 or len(wires)>200:raise ValueError('Schema oltre i limiti: massimo 100 oggetti e 200 collegamenti. Importa un circuito più piccolo.')
    return {'components':parts,'wires':wires}

def _import_native(data):
    import xml.etree.ElementTree as ET
    xml=_multisim_xml(data)
    if len(xml)>IMPORT_MAX_XML or b'<!DOCTYPE' in xml.replace(b'\0',b'').upper() or b'<!ENTITY' in xml.replace(b'\0',b'').upper():raise ValueError('XML Multisim non valido.')
    try:root=ET.fromstring(xml)
    except ET.ParseError as exc:raise ValueError('XML Multisim danneggiato.') from exc
    if root.tag not in ('MSMElectronicsWorkbench','ElectronicsWorkbench'):raise ValueError('Questo XML non è un progetto Multisim.')
    if len(root.findall('.//CiCircuit'))!=1:raise ValueError('Importazione di progetti gerarchici/multi-circuito non disponibile: esporta una singola netlist .cir.')
    objects={item.get('CiID'):child for item in root.iter('Item') if item.get('CiID') for child in item if child.tag in ('CiComponent','CiPort','CiNode')}
    components=[(ident,el) for ident,el in objects.items() if el.tag=='CiComponent']
    if not 0<len(components)<=80:raise ValueError('Progetto vuoto o troppo grande: massimo 80 componenti originali.')
    symbols={s.get('CiComponent'):s for s in root.iter('CIITSymbolComp')}
    parts=[];nets={};unsupported=[];warnings=['I tracciati dei cavi sono ridisegnati automaticamente; le connessioni elettriche vengono conservate.'];used=set()
    def scalar(comp,index):
        params=comp.find('./Attributes/Item/CiaParamList')
        if params is None:raise ValueError('Parametri mancanti.')
        vals=params.findall('./parameters/Item') or params.findall('./doubles/Item')
        if index>=len(vals):raise ValueError('Parametro mancante.')
        return _spice_number(_ms_text(vals[index].get('Value')))
    def transform(el,x,y):
        a=el.attrib
        return (float(a.get('Transformer-M00',1))*x+float(a.get('Transformer-M10',0))*y+float(a.get('Transformer-M20',0)),float(a.get('Transformer-M01',0))*x+float(a.get('Transformer-M11',1))*y+float(a.get('Transformer-M21',0)))
    for ident,comp in components:
        name=_ms_text(comp.get('LocalName'));name=(re.sub(r'[^A-Za-z0-9_-]','_',name) or 'part')[:35];name='GND_'+str(len(parts)) if name=='0' else name
        if name in used:raise ValueError('Etichette duplicate nel progetto.')
        used.add(name);coll=comp.findall('./Attributes/Item/CiaCollString/strings');metadata=[_ms_text(v.get('Value')).upper() for values in coll[:2] for v in values];family=metadata[:4];sym=symbols.get(ident);port_ids=[e.get('CiID') for e in comp.findall('./Ports/Item')];kind=None;params=None;value='';mapping=list(range(len(port_ids)))
        try:
            if 'GROUND' in family:kind='ground'
            elif any(v in family for v in ('RESISTOR','CAPACITOR','INDUCTOR')):
                kind=next(k.lower() for k in ('RESISTOR','CAPACITOR','INDUCTOR') if k in family);number=scalar(comp,1);numeric(number,1e-12,1e12);value=_import_display(number,{'resistor':'Ω','capacitor':'F','inductor':'H'}[kind])
                # Non-zero initial conditions and temperature models need an explicit warning.
                if scalar(comp,4):warnings.append(name+': condizioni iniziali/temperatura non riprodotte dal modello didattico.')
            elif 'AC_VOLTAGE' in family:
                kind='ac';params={'amplitude':scalar(comp,1),'offset':scalar(comp,3),'frequency':scalar(comp,5),'phase':scalar(comp,11),'wave':'sine'}
                if scalar(comp,7) or scalar(comp,9):raise ValueError('Ritardo/smorzamento della sinusoide non supportati.')
                value=format(params['frequency'],'.12g')+' Hz'
            elif any(v in family for v in ('DC_POWER','DC_VOLTAGE','DC_CURRENT')):
                kind='current' if 'DC_CURRENT' in family else 'voltage';value=_import_display(scalar(comp,1),'A' if kind=='current' else 'V')
            elif 'SCOPE' in metadata:
                kind='scope';params={'portsBottom':True};pinmap={'1':0,'4':1,'2':2,'5':3};mapping=[]
                for pid in port_ids:
                    port=objects.get(pid);pin=_ms_text(port.get('LocalName')) if port is not None else '';mapping.append(pinmap.get(pin))
                if sorted(i for i in mapping if i is not None)!=[0,1,2,3] or len(port_ids)!=6:raise ValueError('Piedinatura oscilloscopio non riconosciuta.')
                for pid,target in zip(port_ids,mapping):
                    if target is None and any(e.get('CiID') for e in objects[pid].findall('./Nodes/Item')):raise ValueError('Trigger esterno collegato, non convertibile.')
                warnings.append(name+': impostazioni di acquisizione da regolare in Tramonto; dati della vecchia simulazione non importati.')
            elif any('VOLTMETER'==v for v in family):kind='voltmeter';warnings.append(name+': voltmetro convertito in misura ideale (impedenza infinita).')
            elif any('AMMETER'==v for v in family):kind='ammeter';warnings.append(name+': amperometro convertito in misura ideale.')
            elif any('TL081' in v for v in metadata):
                kind='opamp';params={'model':'tl081','plusTop':True};value='TL081';pins={p.get('PortID'):_ms_text(p.get('PinNumber')) for p in sym.findall('.//CIITPinSymbolComp')} if sym is not None else {};pinmap={'2':0,'3':1,'6':2,'7':3,'4':4};mapping=[pinmap.get(pins.get(pid)) for pid in port_ids]
                if sorted(i for i in mapping if i is not None)!=[0,1,2,3,4]:raise ValueError('Piedinatura TL081 non riconosciuta.')
                warnings.append(name+': macromodello TL081 Texas Instruments di Tramonto.')
            elif 'DIODE' in family:kind='diode';warnings.append(name+': modello diodo generico Tramonto; parametri originali non riprodotti.')
            elif 'SPST' in family or 'SPST_SWITCH' in family:
                kind='switch';state=scalar(comp,1)
                if state not in (0,1):raise ValueError('Stato interruttore non riconosciuto.')
                params={'closed':bool(state),'key':''};value='chiuso' if params['closed'] else 'aperto';warnings.append(name+': SPST ideale, stato importato '+value+'; verifica lo stato prima della simulazione.')
            if kind is None:raise ValueError('Tipo componente non disponibile.')
            if kind!='scope' and len([p for p in mapping if p is not None])!=PORTS[kind]:raise ValueError('Piedinatura non disponibile.')
            params=validate_params(params) if params is not None else None
            # Read native geometry, including rotated symbol/pin matrices.
            center=(len(parts)%5*160,len(parts)//5*160);rotation=0
            if sym is not None:
                bounds=sym.find('.//CIITSymbolBorderRect')
                if bounds is not None:
                    x=(float(bounds.get('pt0X'))+float(bounds.get('pt1X')))/2;y=(float(bounds.get('pt0Y'))+float(bounds.get('pt1Y')))/2;center=transform(sym,*transform(bounds,x,y))
                if PORTS[kind]==2:
                    locations={}
                    for pin in sym.findall('.//CIITPinSymbolComp'):
                        connector=pin.find('.//CIITPinConnectorComp')
                        if connector is not None:locations[pin.get('PortID')]=transform(sym,*transform(pin,*transform(connector,float(connector.get('ptCenterX')),float(connector.get('ptCenterY')))))
                    if all(pid in locations for pid in port_ids):
                        a,b=[locations[pid] for pid in port_ids];rotation=(round(math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))/90)*90)%360
            part=_import_part(name,kind,value,params,*center,rotation);parts.append(part)
            for pid,target in zip(port_ids,mapping):
                port=objects.get(pid)
                if port is None or port.tag!='CiPort':raise ValueError('Terminale mancante.')
                if target is None:
                    if any(e.get('CiID') for e in port.findall('./Nodes/Item')):raise ValueError('Terminale aggiuntivo collegato non convertibile.')
                    continue
                ns=[e.get('CiID') for e in port.findall('./Nodes/Item') if e.get('CiID')]
                if len(ns)>1:raise ValueError('Terminale su più reti non supportato.')
                if ns:
                    node=objects.get(ns[0])
                    if node is None or node.tag!='CiNode':raise ValueError('Nodo mancante.')
                    node_name='0' if node is not None and _ms_text(node.get('LocalName'))=='0' else ns[0];nets.setdefault(node_name,[]).append((name,target))
        except (ValueError,TypeError,KeyError):unsupported.append(name+' ('+(family[1] if len(family)>1 else 'tipo/piedinatura non disponibile')+')')
    if unsupported:raise ValueError('Conversione interrotta; lo schema attuale è intatto. Componenti non convertibili: '+', '.join(unsupported[:12])+'. Esporta una netlist .cir oppure usa componenti supportati.')
    minx=min(p['x'] for p in parts);miny=min(p['y'] for p in parts)
    for p in parts:p['x']=round((p['x']-minx)*1.5+140,2);p['y']=round((p['y']-miny)*1.5+140,2)
    title=_ms_text(root.find('Project').get('Name')) if root.find('Project') is not None else 'Multisim'
    return _import_connect(parts,nets),title,warnings


def _import_spice(data):
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:raise ValueError('Netlist non testuale: usa .ms14 oppure esporta .cir.')
    lines=[]
    for original in text.splitlines():
        line=original.split(';')[0].strip()
        if not line or line.startswith('*'):continue
        if line.startswith('+'):
            if not lines:raise ValueError('Continuazione SPICE senza riga iniziale.')
            lines[-1]+=' '+line[1:].strip()
        else:lines.append(line)
    if len(lines)>10000 or any(len(line)>2000 for line in lines):raise ValueError('Netlist troppo complessa: massimo 10000 righe di 2000 caratteri.')
    if any(line.split()[0].lower() in ('.control','.include','.lib','.exec','.shell') for line in lines):raise ValueError('La netlist contiene comandi esterni/non convertibili.')
    parts=[];nets={};warnings=['Posizioni e tracciati ricostruiti automaticamente dalla netlist.'];unsupported=[];used=set();title='Netlist Multisim';in_model=False
    def pin(node,ident,index):
        if not re.fullmatch(r'[A-Za-z0-9_.$+-]{1,64}',node):raise ValueError('Nome nodo non valido.')
        nets.setdefault(node.lower(),[]).append((ident,index))
    for n,line in enumerate(lines):
        tokens=line.split();name=tokens[0];head=name.lower()
        if head.startswith('.'):
            if head in ('.control','.include','.lib','.exec','.shell'):raise ValueError('La netlist contiene comandi esterni/non convertibili: '+name)
            if head=='.subckt':in_model=True;warnings.append('Macromodelli originali non eseguiti; sono disponibili solo i modelli Tramonto indicati.');continue
            if head=='.ends':in_model=False;continue
            if head=='.end':break
            if head in ('.model','.tran','.ac','.dc','.op','.options','.param','.print','.plot','.save','.global'):
                if head=='.param':unsupported.append('parametri simbolici .param')
                continue
            unsupported.append(name);continue
        if in_model:continue
        # The optional first line is the SPICE title, never an unknown device.
        if n==0 and not re.fullmatch(r'[A-Za-z]+[0-9]+',name) and (len(tokens)<4 or len(name)>40 or name[0].upper() not in 'RCLVIDQMXSEFGHB'):
            title=line[:80];continue
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}',name) or name.lower() in used:raise ValueError('Etichetta componente non valida o duplicata: '+name[:40])
        used.add(name.lower());prefix=name[0].upper();kind=None;params=None;value='';nodes=[]
        try:
            if prefix in 'RCL' and len(tokens)>=4:
                kind={'R':'resistor','C':'capacitor','L':'inductor'}[prefix];v=_spice_number(tokens[3]);numeric(v,1e-12,1e12);value=_import_display(v,{'resistor':'Ω','capacitor':'F','inductor':'H'}[kind]);nodes=tokens[1:3]
                if len(tokens)>4:warnings.append(name+': valore nominale importato; modello termico/condizioni iniziali aggiuntive non riprodotti.')
            elif prefix in 'VI' and len(tokens)>=4:
                nodes=tokens[1:3];source=' '.join(tokens[3:]);sin=re.search(r'SIN\s*\(([^)]+)\)',source,re.I)
                if sin and prefix=='V':
                    values=[_spice_number(v) for v in sin[1].replace(',',' ').split()]
                    if not 3<=len(values)<=6 or len(values)>3 and values[3] or len(values)>4 and values[4]:raise ValueError('Sinusoide con ritardo/smorzamento non convertibile.')
                    kind='ac';params={'offset':values[0],'amplitude':values[1],'frequency':values[2],'phase':values[5] if len(values)>5 else 0,'wave':'sine'};value=format(values[2],'.12g')+' Hz'
                    remainder=source[:sin.start()]+source[sin.end():]
                    if remainder.strip():warnings.append(name+': importata la sinusoide transitoria; impostazioni AC/DC separate non riprodotte.')
                else:
                    dc=re.fullmatch(r'(?:DC\s+)?(\S+)',source,re.I)
                    if not dc:raise ValueError('Sorgente non convertibile.')
                    kind='voltage' if prefix=='V' else 'current';value=_import_display(_spice_number(dc[1]),'V' if kind=='voltage' else 'A')
            elif prefix=='D' and len(tokens)==4:kind='diode';nodes=tokens[1:3];warnings.append(name+': diodo '+tokens[3]+' sostituito dal modello generico Tramonto.')
            elif prefix=='X' and len(tokens)==7 and tokens[-1].upper().startswith('TL081'):
                kind='opamp';nodes=[tokens[i] for i in (2,1,5,3,4)];value='TL081';params={'model':'tl081','plusTop':True};warnings.append(name+': usato il macromodello TL081 Texas Instruments di Tramonto.')
            elif prefix=='Q' and len(tokens)==5 and tokens[-1].upper() in ('NPN','PNP'):
                kind=tokens[-1].lower();nodes=[tokens[i] for i in (2,1,3)];warnings.append(name+': transistor con modello generico Tramonto.')
            if kind is None:raise ValueError('Componente non convertibile.')
            if len(parts)>=80:raise ValueError('Troppi componenti.')
            p=_import_part(name,kind,value,params,140+(len(parts)%5)*190,160+(len(parts)//5)*180);parts.append(p)
            for index,node in enumerate(nodes):pin(node,name,index)
        except (ValueError,KeyError,IndexError):unsupported.append(name)
    if unsupported:raise ValueError('Conversione interrotta; schema attuale intatto. Elementi non convertibili: '+', '.join(unsupported[:15])+'. Supportati R, C, L, sorgenti DC/SIN, diodi, transistor NPN/PNP e TL081.')
    if not parts:raise ValueError('Nessun componente convertibile nel file.')
    return _import_connect(parts,nets),title,warnings


def import_circuit(data,filename):
    if not isinstance(data,bytes) or not 0<len(data)<=IMPORT_MAX_FILE:raise ValueError('File vuoto o superiore a 8 MB.')
    if not isinstance(filename,str) or len(filename)>180:raise ValueError('Nome file non valido.')
    native=data.startswith((b'MSMCompressedElectronicsWorkbenchXML',b'CompressedElectronicsWorkbenchXML')) or Path(filename).suffix.lower()=='.xml' or re.fullmatch(r'\.ms\d+',Path(filename).suffix.lower())
    circuit,title,warnings=_import_native(data) if native else _import_spice(data)
    from tramonto import content_data
    clean=content_data({'circuit':circuit})['circuit']
    return {'circuit':clean,'title':title[:80],'format':'Multisim nativo' if native else 'Netlist SPICE','warnings':list(dict.fromkeys(warnings)),'components':len(clean['components']),'wires':len(clean['wires'])}


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
    if not isinstance(value,dict) or set(value)-{'frequency','amplitude','offset','duty','wave','ratio','closed','gainA','gainB','gainC','gainOut','phase','model','plusTop','portsBottom','key'}: raise ValueError('Parametri componente non validi.')
    result={}
    for name,low,high in (('frequency',.001,1e9),('amplitude',0,1e6),('offset',-1e6,1e6),('duty',.01,.99),('ratio',.01,.99),('gainA',-1000,1000),('gainB',-1000,1000),('gainC',-1000,1000),('gainOut',-1000,1000),('phase',-360,360)):
        if name in value: result[name]=numeric(value[name],low,high)
    if 'wave' in value:
        if value['wave'] not in ('sine','square','triangle'): raise ValueError('Forma d’onda non valida.')
        result['wave']=value['wave']
    if 'closed' in value:
        if type(value['closed']) is not bool: raise ValueError('Stato interruttore non valido.')
        result['closed']=value['closed']
    if 'portsBottom' in value:
        if type(value['portsBottom']) is not bool: raise ValueError('Orientamento porte non valido.')
        result['portsBottom']=value['portsBottom']
    if 'plusTop' in value:
        if type(value['plusTop']) is not bool: raise ValueError('Orientamento ingressi non valido.')
        result['plusTop']=value['plusTop']
    if 'model' in value:
        if value['model'] not in ('generic','tl081'): raise ValueError('Modello operazionale non valido.')
        result['model']=value['model']
    if 'key' in value:
        if not isinstance(value['key'],str) or not re.fullmatch('[A-Z]?',value['key']): raise ValueError('Tasto interruttore non valido.')
        result['key']=value['key']
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
        result.update(stop=numeric(value.get('stop',.01),1e-9,100),samples=int(numeric(value.get('samples',600),20,10000)))
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
    connected={(wire[end]['component'],wire[end]['port']) for wire in circuit['wires'] for end in ('from','to')}
    roots={find(zero):'0'}; counts={}; rows=['Tramonto: generated circuit']; labels={}; probes=[]; first_dc=None
    def node(part,index):
        root=find((part['id'],index))
        if root not in roots: roots[root]='n'+str(len(roots)); labels[roots[root]]=part['label']+' · terminale '+str(index+1)
        return roots[root]
    def name(prefix): counts[prefix]=counts.get(prefix,0)+1; return prefix+str(counts[prefix])
    def fmt(number): return format(number,'.12g')
    def add_probe(expr,name,unit,**metadata): probes.append((expr,name,unit,metadata))
    for p in parts:
        kind=p['type']
        if kind=='scope':
            for channel,positive,negative in (('A',0,1),('B',2,3)):
                if all((p['id'],port) in connected for port in (positive,negative)):
                    add_probe(f'v({node(p,positive)},{node(p,negative)})',p['label']+' · '+channel,'V',scope_id=p['id'],channel=channel)
            continue
        if kind in ('probe','voltmeter') and not all((p['id'],port) in connected for port in range(PORTS[kind])): continue
        pins=[node(p,i) for i in range(PORTS[kind])]; params=validate_params(p.get('params',{})); value=p.get('value','')
        if kind in ('ground','junction'): continue
        a,b=pins[:2] if len(pins)>1 else (pins[0],'0')
        if kind in ('resistor','capacitor','inductor','fuse'):
            default={'resistor':1000,'capacitor':1e-6,'inductor':.001,'fuse':.01}[kind]; val=component_value(value,default,True)
            rows.append(f'{name({"resistor":"R","capacitor":"C","inductor":"L","fuse":"R"}[kind])} {a} {b} {fmt(val)}')
        elif kind in ('voltage','battery','current','ammeter'):
            prefix='I' if kind=='current' else 'V'; val=0 if kind=='ammeter' else component_value(value,5 if prefix=='V' else .001)
            ident=name(prefix); rows.append(f'{ident} {a} {b} DC {fmt(val)}')
            if kind in ('voltage','battery') and first_dc is None: first_dc=ident
            if kind=='ammeter': add_probe(f'i({ident})',p['label']+' · corrente','A')
        elif kind in ('ac','function'):
            frequency=params['frequency'] if 'frequency' in params else numeric(component_value(value,1000,True),.001,1e9); amplitude=params.get('amplitude',1); offset=params.get('offset',0); period=1/frequency; wave=params.get('wave','sine')
            source=f'SIN({fmt(offset)} {fmt(amplitude)} {fmt(frequency)}'+(f' 0 0 {fmt(params["phase"])}' if 'phase' in params else '')+')'
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
        elif kind=='summer':
            ina,inb,out,reference=pins
            rows.append(f'{name("B")} {out} {reference} V={fmt(params.get("gainA",1))}*v({ina},{reference})+{fmt(params.get("gainB",1))}*v({inb},{reference})')
        elif kind=='summer3':
            ina,inb,inc,out=pins
            rows.append(f'{name("B")} {out} 0 V={fmt(params.get("gainOut",1))}*({fmt(params.get("gainA",1))}*v({ina})+{fmt(params.get("gainB",1))}*v({inb})+{fmt(params.get("gainC",1))}*v({inc}))+{fmt(params.get("offset",0))}')
        elif kind=='opamp':
            minus,plus,out,vplus,vminus=pins
            if params.get('model')=='tl081': rows.append(f'{name("X")} {plus} {minus} {vplus} {vminus} {out} TL081')
            else: rows.append(f'{name("B")} {out} 0 V=min(v({vplus}),max(v({vminus}),1e5*(v({plus})-v({minus}))))')
        elif kind in ('and','or','not','nand','nor','xor','xnor'):
            if kind=='not': inp,out,high,low=pins; expr=f'1-u(v({inp})-(v({high})+v({low}))/2)'
            else:
                inp1,inp2,out,high,low=pins; terms=[f'u(v({pin})-(v({high})+v({low}))/2)' for pin in (inp1,inp2)]; expr=('*'.join(terms) if kind in ('and','nand') else f'abs({terms[0]}-{terms[1]})' if kind in ('xor','xnor') else f'min(1,{terms[0]}+{terms[1]})')
                if kind in ('nand','nor','xnor'): expr=f'1-({expr})'
            rows.append(f'{name("B")} {out} {low} V=(v({high})-v({low}))*({expr})')
        elif kind in ('probe','voltmeter'): add_probe(f'v({a},{b})',p['label'],'V')
    if not any(p['type'] in ('voltage','battery','current','ac','function') for p in parts): raise ValueError('Serve almeno un generatore collegato.')
    if any(p['type']=='opamp' and p.get('params',{}).get('model')=='tl081' for p in parts): rows.extend(TL081_MODEL.splitlines())
    rows += ['.model DIODE D(Is=2.52n N=1.75 Rs=.568 Cjo=4p Tt=20n)', '.model LED D(Is=1e-20 N=2 Rs=10)', '.model ZENER D(Is=1n N=1 Rs=1 Bv=5.1 Ibv=1m)',
             '.model NPN NPN(Is=1e-14 Bf=100 Vaf=100)', '.model PNP PNP(Is=1e-14 Bf=100 Vaf=100)', '.model NMOS NMOS(Level=1 Vto=1 Kp=100u)', '.model PMOS PMOS(Level=1 Vto=-1 Kp=100u)', '.options numdgt=12', '.control','set noaskquit','set wr_singlescale','set wr_vecnames','set numdgt=12']
    analysis=options['analysis']
    if analysis=='tran': rows.append('tran '+fmt(options['stop']/options['samples'])+' '+fmt(options['stop'])+' 0 '+fmt(options['stop']/options['samples']))
    elif analysis=='ac': rows.append(f'ac dec {options["points"]} {fmt(options["start"])} {fmt(options["end"])}')
    elif analysis=='dc':
        if not first_dc: raise ValueError('La scansione DC richiede un generatore DC o una batteria.')
        rows.append(f'dc {first_dc} {fmt(options["dc_start"])} {fmt(options["dc_end"]+abs(options["dc_end"]-options["dc_start"])/(options["samples"]-1)*1e-7)} {fmt((options["dc_end"]-options["dc_start"])/(options["samples"]-1))}')
    else: rows.append('op')
    traces=probes[:8] or [(f'v({node})',description,'V',{}) for node,description in list(labels.items())[:6]]
    if not traces: raise ValueError('Nessun nodo da misurare; controlla i collegamenti alla massa.')
    def control_voltage(expr):
        # Ground has no voltage vector in ngspice's control language.
        match=re.fullmatch(r'v\((n\d+|0),(n\d+|0)\)',expr)
        if not match: return expr
        a,b=match.groups()
        if a==b:
            reference=a if a!='0' else next(iter(labels),None)
            if reference is None: raise ValueError('Nessun nodo da misurare; controlla i collegamenti alla massa.')
            return f'(v({reference})*0)'
        if b=='0': return f'v({a})'
        if a=='0': return f'(-v({b}))'
        return expr
    expressions=[f'mag({control_voltage(expr)})' if analysis=='ac' else control_voltage(expr) for expr,_,_,_ in traces]
    rows += ['wrdata result.dat '+' '.join(expressions),'quit','.endc','.end']
    return {'netlist':'\n'.join(rows)+'\n','traces':[{'name':description,'unit':unit,**metadata} for _,description,unit,metadata in traces],'options':options,'nodes':labels}

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
    import_slots=asyncio.Semaphore(1)
    async def import_file(request):
        admin(request)
        if request.content_length is not None and request.content_length>IMPORT_MAX_FILE:return web.json_response({'error':'File superiore a 8 MB.'},status=413)
        data=await request.read()
        from urllib.parse import unquote
        filename=unquote(request.headers.get('X-Circuit-Name','schema.cir'))
        async with import_slots:
            try:result=await asyncio.to_thread(import_circuit,data,filename)
            except ValueError as exc:return web.json_response({'error':str(exc)},status=422)
        return web.json_response(result)
    async def capabilities(request):
        admin(request); return web.json_response({'spice_available':spice.available,'analyses':['op','tran','ac','dc'],'components':list(PORTS),'network':'didactic_ipv4','timeout_seconds':12})
    async def cleanup(_):
        tasks=[entry['task'] for entry in jobs.values() if not entry['task'].done()]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
    app.add_routes([web.get('/api/tramonto/labs',capabilities),web.post('/api/tramonto/circuit/import',import_file),web.post('/api/tramonto/netlist',start),web.post('/api/tramonto/simulations',start),
                    web.get('/api/tramonto/simulations/{id}',job),web.post('/api/tramonto/simulations/{id}/cancel',job)])
    app.on_cleanup.append(cleanup)
