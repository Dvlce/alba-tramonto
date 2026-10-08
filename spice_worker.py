"""Standard-library-only worker, invoked inside an empty filesystem/network namespace."""
import json
import math
import resource
import subprocess
from pathlib import Path

def main():
    resource.setrlimit(resource.RLIMIT_CPU,(6,6)); resource.setrlimit(resource.RLIMIT_AS,(384*1024*1024,384*1024*1024))
    resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024*1024,4*1024*1024)); resource.setrlimit(resource.RLIMIT_NOFILE,(32,32)); resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    with open('ngspice.log','wb') as log:
        result=subprocess.run(['/usr/bin/ngspice','-n','-b','circuit.cir'],stdout=log,stderr=log,timeout=9)
    path=Path('result.dat')
    if not path.exists() or path.stat().st_size>4*1024*1024: raise ValueError('Nessun risultato: circuito non convergente o terminali scollegati. Controlla anche la massa.')
    metadata=json.loads(Path('metadata.json').read_text()); values=[]
    with path.open() as source:
        next(source,None)
        for line in source:
            if len(values)>=100000: raise ValueError('Troppi campioni: riduci frequenza e durata.')
            row=[float(value) for value in line.split()]
            if len(row)!=len(metadata)+1 or any(not math.isfinite(v) for v in row): raise ValueError('Risultati non finiti; controlla i valori e i collegamenti.')
            values.append(row)
    if not values: raise ValueError('Nessun campione ottenuto.')
    return {'x':[row[0] for row in values],'series':[{**description,'values':[row[i+1] for row in values]} for i,description in enumerate(metadata)],'total_samples':len(values),'display_samples':len(values),'downsampled':False}

if __name__=='__main__':
    try: response=main()
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        response={'error':str(exc) if isinstance(exc,ValueError) else 'Simulazione interrotta dai limiti di sicurezza o dal simulatore.'}
    Path('response.json').write_text(json.dumps(response,allow_nan=False))
