"""Offline bar charts from explicitly published Pi probes, never model inference."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
data=json.loads((root/'ADAPTIVE_RESULTS.json').read_text())
for topic in ('coding','long_wait'):
 rows=[r for r in data['results'] if r['topic']==topic]
 fig,axes=plt.subplots(2,2,figsize=(14,9))
 metrics=[('first_token_ms','First token / seconds · lower is faster',1000),('wall_ms','Total request / seconds · lower is faster',1000),('tokens_per_second','Decode / tokens per second · higher is faster',1),('output_tokens','Actual output / tokens · shorter must still satisfy the task',1)]
 for ax,(key,title,scale) in zip(axes.flat,metrics):
  for i,row in enumerate(rows):
   for j,backend in enumerate(('normal','optimized')):
    sample=next((s for s in row['samples'] if s['backend']==backend),{})
    value=sample.get(key)
    x=i+(-.19 if j==0 else .19)
    if sample.get('status')=='ok' and isinstance(value,(int,float)):
     bar=ax.bar(x,value/scale,width=.36,color='#788275' if j==0 else '#456b43',label=('Standard' if j==0 else 'Selected optimization') if i==0 else None)
     ax.bar_label(bar,fmt='%.2f',padding=3,fontsize=8)
    else:ax.annotate('FAILED / N/A',(x,0),rotation=90,ha='center',va='bottom',fontsize=7,color='#a04439')
  ax.set_xticks(range(len(rows)),[r['technology'] for r in rows],rotation=25,ha='right');ax.set_title(title,fontsize=11);ax.set_ylim(bottom=0);ax.margins(y=.2);ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15);ax.legend(fontsize=8)
 fig.suptitle('Notte · real same-model '+data['model']+' · '+('coding' if topic=='coding' else 'long input / waiting time')+' · Pi 5 / 8 GB',fontsize=15)
 fig.text(.5,.015,'One repetition per condition; standard first; startup included; OS cache not evicted. Warm/CPU2 reuse residency; Flux changes budgets; KV8 changes KV precision.',ha='center',fontsize=9)
 fig.tight_layout(rect=(0,.05,1,.95))
 for extension in ('png','svg'):fig.savefig(root/'ssd-results'/('adaptive-'+('coding' if topic=='coding' else 'long-wait')+'.'+extension),dpi=170)
 svg=root/'ssd-results'/('adaptive-'+('coding' if topic=='coding' else 'long-wait')+'.svg')
 svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
 plt.close(fig)
print('Rendered real-policy coding and long-wait histograms, with failures visible.')
