"""Offline report rendering from a recorded public probe; no inference."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parent
data=json.loads((root/'TEST_LAB_RESULTS.json').read_text())
fig,axes=plt.subplots(1,3,figsize=(12,4.8))
for ax,key,unit,title in zip(axes,('first_token_ms','wall_ms','tokens_per_second'),
                            ('seconds','seconds','tokens/s'),
                            ('First token\nlower is faster','Total request\nlower is faster','Decode rate\nhigher is faster')):
    values=[s[key]/1000 if key.endswith('_ms') else s[key] for s in data['samples']]
    bars=ax.bar(('Normal\nOllama','Optimized\nSSD'),values,color=('#788275','#456b43'))
    ax.bar_label(bars,fmt='%.2f',padding=4);ax.set_ylim(0,max(values)*1.22)
    ax.set_title(title);ax.set_ylabel(unit);ax.spines[['top','right']].set_visible(False)
fig.suptitle('Real Pi 5 / 8 GB: same Qwen Coder 7B, both answer 42',fontsize=15)
fig.text(.5,.02,'One arithmetic probe; normal first; startup included; OS cache not evicted. Lower latency, slower decode.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.05,1,.92))
for extension in ('png','svg'):fig.savefig(root/'ssd-results'/('test-lab-comparison.'+extension),dpi=170)
plt.close(fig)
print('Rendered real Test Lab comparison in PNG and SVG.')
