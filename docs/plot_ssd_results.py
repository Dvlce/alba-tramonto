"""Render the published measurements; no model inference or network access.

Usage: python docs/plot_ssd_results.py
Requires matplotlib==3.10.8 in a separate reporting environment, not the core.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
DATA = json.loads((ROOT / 'SSD_RUNTIME_RESULTS.json').read_text())
OUTPUT = ROOT / 'ssd-results'
OUTPUT.mkdir(exist_ok=True)
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False,
                     'axes.spines.right': False, 'svg.fonttype': 'none'})
BLUE, GREEN, ORANGE = '#3369b0', '#208163', '#bf5b24'


def row(model, policy):
    return next(item for item in reversed(DATA['results'])
                if item['model'] == model
                and item['options'].get('ssd_policy') == policy
                and item['metrics']['cache'] == 'native-runtime')


def save(fig, name):
    fig.tight_layout()
    for extension in ('png', 'svg'):
        fig.savefig(OUTPUT / (name + '.' + extension), dpi=170,
                    metadata={'Creator': 'ALBA measured-results report'}
                    if extension == 'svg' else None)
    plt.close(fig)


mapped = row('qwen2.5-coder:7b', 'mapped')
draft = row('qwen2.5-coder:7b', 'speculative')
topics = ('python', 'logic', 'english')
rates = lambda item: [next(s['tokens_per_second'] for s in item['metrics']['samples']
                           if s.get('topic') == topic and s.get('cache') == 'warm')
                      for topic in topics]
baseline, verified = rates(mapped), rates(draft)
fig, ax = plt.subplots(figsize=(9, 5))
for offset, values, label, color in ((-.18, baseline, 'Mapped 7B target', BLUE),
                                    (.18, verified, '7B + verified 0.5B draft', GREEN)):
    bars = ax.bar([i + offset for i in range(3)], values, width=.36,
                  label=label, color=color)
    ax.bar_label(bars, fmt='%.2f', padding=3)
ax.set_xticks(range(3), ('Python: +36.9%', 'Arithmetic: +21.1%', 'English: -25.6%'))
ax.set_ylabel('Generated tokens / second (higher is faster)')
ax.set_ylim(0, max(verified + baseline) * 1.3)
ax.set_title('Pi 5 / 8 GB: repeated-prompt 7B decode\nAll six draft outputs match target token IDs; three prompt types only')
ax.legend(loc='upper left')
save(fig, '7b-decode')

checkpoint = next(r for r in DATA['results'] if r['metrics']['cache'] == 'persistent-context')
fig, ax = plt.subplots(figsize=(8, 4.8))
values = [s['wall_ms'] / 1000 for s in checkpoint['metrics']['samples']]
bars = ax.bar(('No checkpoint', 'After restart + restore'), values, color=(BLUE, GREEN))
ax.bar_label(bars, fmt='%.3f s', padding=3)
ax.set_ylim(0, max(values) * 1.25)
ax.set_ylabel('Request seconds (lower is faster)')
ax.set_title('Short checkpoint probe: same output tokens\nExcludes server startup and checkpoint I/O; not full chat')
save(fig, 'checkpoint')

fig, ax = plt.subplots(figsize=(10, 5))
observations = DATA['production_chat_latency']
values = [o['metrics']['first_token_ms'] / 1000 for o in observations]
bars = ax.bar(range(len(values)), values, color=(BLUE, BLUE, ORANGE, ORANGE, GREEN))
ax.bar_label(bars, fmt='%.1f s', padding=3)
ax.set_xticks(range(len(values)), ('Initial\nfirst', 'Initial\nfollowing',
                                  'Stable layout\nfirst', 'Stable layout\nfollowing',
                                  'Checkpoint fix\nrestored'))
ax.set_ylim(0, max(values) * 1.25)
ax.set_ylabel('Seconds to first token (lower is faster)')
ax.set_title('Actual long-history 7B chat: still minutes\nContext changed between stages; not a controlled speed comparison')
save(fig, 'chat-latency')

large = row('qwen2.5-coder:14b', 'mapped')
values = rates(large)
fig, ax = plt.subplots(figsize=(8, 4.8))
bars = ax.bar(('Python: function test FAILED', 'Arithmetic', 'English'), values, color=ORANGE)
ax.bar_label(bars, fmt='%.3f', padding=3)
ax.set_ylim(0, max(values) * 1.3)
ax.set_ylabel('Generated tokens / second (higher is faster)')
ax.set_title('Real 14B Q4 / 8.99 GB mapped above RAM\nShort probes, 32-token limit; about 230 GB disk reads over the run')
save(fig, '14b-decode')
print('Rendered four charts in PNG and SVG:', OUTPUT)
