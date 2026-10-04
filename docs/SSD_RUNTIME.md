# ALBA SSD Runtime

The runtime executes the selected GGUF itself on the Raspberry. It does not
substitute a smaller model, prune layers, retrain weights, change quantization or
quantize the KV cache. An optional small draft proposes tokens; llama.cpp checks
them against the selected target. Speculation can be slower on CPU and is never
automatically selected.

This is a CPU llama.cpp integration with a GGUF memory planner and reproducible
experiments. It is **not** a universal port of Colibri's per-layer expert LRU,
learned pins, prefetch and custom kernels. Linux mmap supplies demand paging;
supported MoE kernels select their actual routed experts. The planner labels
recognized expert tensors but does not invent a measured expert hit rate.

## Model identity and preservation

`prepare_ssd` checks the installed Ollama manifest, complete SHA-256 and byte
length. It creates a read-only hard link on the same SSD when possible, or a
verified copy. The Ollama model, training adapters, encrypted backups, SQLite
conversation history, diary and embeddings remain intact. Placement changes
where bytes are read, not what weights the model has. Importing Q4 retains that
existing Q4, not the original training model's BF16 precision.

No-context-shift prevents silently dropping tokens inside the native server.
Notte still builds a bounded prompt from recent history and retrieved memory:
the complete archive is preserved, but a short context is not equivalent to
feeding every past conversation to the model. Numerical changes between CPU
kernels or batched verification can affect near-tie logits. The benchmark checks
token IDs and generated text against the same target's baseline; a few matching
prompts are evidence for those prompts, not a universal intelligence guarantee.

## Components

* `core/gguf_plan.py`: bounded GGUF metadata/tensor reader; dense/MoE placement,
  active-weight and f16 KV estimates, available RAM minus system reserve.
* `core/prepare_ssd.py`: administrative model registration and independent ARM
  native build. Uses the converter source pinned to
  `dd266785c2595775001c1c714bd9d92b3ef34cde`, without overwriting its training build.
* `core/ssd_runtime.py`: loopback-only authenticated llama-server, three policies,
  process-group cleanup, RAM/thermal watchdog, SSE chat and measured experiments.
* `core/ssd_cli.py`: ephemeral authenticated local admin client. Sessions are
  removed on exit; secrets are never printed. Benchmark waits for an idle model.
* `data/core-inference/models.json`: model name, immutable GGUF digest and size.
  `models/` holds links/copies; `build/` holds native binaries; private
  `server.log` records the latest server. `server.key` exists only during a run.
  Private `kv-cache/` holds at most 512 MiB of derived f16 context checkpoints.

The native runtime uses one slot, four Cortex-A76 CPU threads, batch/ubatch 128,
polling disabled, mmap and f16 K/V. `native` enables CPU weight repacking only when
two copies of the weights are estimated to fit during setup; `mapped` disables repacking so a large file does
not also become a complete anonymous-RAM copy. `speculative` adds a genuine Qwen
Coder 0.5B draft, four draft tokens and two draft threads. Unsupported model/draft
tokenizers fail visibly. There are no shell commands supplied by the model/API.

## Setup on the Pi

Use the existing training/conversion setup to obtain the pinned source first.
As the service account, from the project directory:

```sh
cd /home/dvlce/supporto-ai
sudo -u alba .venv/bin/python -m core.prepare_ssd \
  --root data/core-inference --source data/core-training/llama.cpp
```

For the protected Ollama store on this installation, model registration requires
root read access. Keep linked blob ownership unchanged; chown only the new
directory/catalog, never recursively chown or chmod the linked model files:

```sh
sudo .venv/bin/python -m core.prepare_ssd --root data/core-inference \
  --model qwen2.5-coder:7b
sudo .venv/bin/python -m core.prepare_ssd --root data/core-inference \
  --model qwen2.5-coder:0.5b
sudo chown alba:alba data/core-inference/models data/core-inference/models.json
```

Download additional chosen models with Ollama on the Pi, then register them
identically. The tool never downloads a different model as an implicit fallback.
Root/private directory permissions and the existing service sandbox remain.

## Plan, benchmark and native Android chat

```sh
sudo -u alba .venv/bin/python -m core.ssd_cli plan --model qwen2.5-coder:7b
sudo -u alba .venv/bin/python -m core.ssd_cli bench --model qwen2.5-coder:7b
sudo -u alba .venv/bin/python -m core.ssd_cli enable \
  --model qwen2.5-coder:7b --policy auto
```

`enable` selects Notte's advanced profile and that exact target. Subsequent chat
in the existing native Android app or portal streams from the local CPU server.
Each request unloads other Ollama weights, starts the native server, restores a
compatible context checkpoint, then releases it on completion, cancellation or
failure. Checkpoints are keyed by target SHA, llama.cpp revision, policy and
context size; the server reuses only the exact matching prompt prefix. Dynamic
state is appended as labelled data to the current message instead of changing
the beginning of the system prompt. All selected state/history content is kept;
up to 128 recent messages are considered within the same bounded context budget.
A corrupt
cache is discarded and the original model computes the context again. Completed
chat saves atomically with 0600 permissions. These caches are reconstructable,
not substitutes for the persistent conversation archive. This avoids a second persistent model
competing with autonomous study/daily training; each chat includes a load cost.
Fast/quality chat, Alba and autonomous learning retain their existing Ollama path.
The selected model and runtime policy appear in activity/latency logs; benchmark
rows appear in the existing System section on Android and the portal.

```sh
sudo -u alba .venv/bin/python -m core.ssd_cli disable
```

`disable` restores Ollama inference without deleting models, data or benchmarks.
The advanced model selection remains explicit; choose the fast profile in app
settings when desired. The SSD runtime is opt-in until hardware measurements
justify enabling it. CLI commands require the project directory and access to
its private admin/session storage, not a publicly supplied password.

Admin API: `GET /api/notte/ssd-plan?model=…&context=1024`,
`POST /api/notte/action` with `{"action":"ssd_benchmark","text":"model:tag"}`,
or `{"action":"config","config":{"ssd_enabled":true,"ssd_policy":"auto"}}`.
The existing session, admin, CSRF, origin and body limits apply.
`GET /api/notte/status` adds `ssd_runtime`; exported statistics include it.
Benchmarks share Alba's inference lock and yield to foreground Notte chat.

## Measurement and resource limits

For resident targets, compare native repacking, mmap without repacking and draft
verification, using mapped as the token reference. Repacking is skipped when its
transient duplicate would exceed the budget. For disk-bound targets, run only the
mapped policy. Three fixed
public prompts cover code, Italian arithmetic and an English hardware question;
repeat each to expose prompt-cache reuse. All use temperature 0, seed 42, at most
96 output tokens and the target GGUF's own template. Oversized dense models use
three shorter public probes and a 32-token limit; their results are not the same
task as the resident-model speed comparison. A cold prompt means a new
prompt, not a globally evicted SSD cache. No global drop_caches or swap changes.

Results retain target SHA, architecture, byte size, quantization provenance, load
time, native llama.cpp timings, wall time, tokens/text, code test results and
policy comparisons. Code is executed in the existing offline bubblewrap sandbox
against independent order-preservation cases. Report failures and slow policies.
This tiny suite measures a runtime and catches particular mistakes; it does not
rank general model intelligence. Ollama's older matrix uses different sampling
defaults, so it is not a token-exact baseline for the native server.

The watchdog samples every 200 ms: child RSS/anonymous/swap, bytes read from disk,
available system RAM and temperature. It stops below 512 MiB available or at
80 °C, or when the runtime itself exceeds 512 MiB of swap. Startup requires 1 GiB
available, has a 120-second deadline; each benchmark
request has 240 seconds; chat has 480 seconds. Stop kills the whole process group
and removes the ephemeral key. The service's systemd restrictions also apply.
These guardrails can reject a large model; rejection preserves the conversation
and explicitly reports failure, without claiming that a smaller model answered.

## Physical limits

A dense model accesses almost all layer weights per generated token. If its
working set exceeds usable RAM, paging repeatedly reads the deficit from SSD;
mapping a 12 GB file is possible, but does not make SSD bandwidth equal to RAM.
For MoE, fewer expert weights are active at each layer, making selective
placement a useful candidate, still constrained by dense weights, KV and I/O.
Neither model file size nor total parameter count alone predicts speed.

For the existing 8 GB Pi, benchmark a real 14B Q4 (~9 GB) rather than promise
fluid performance for dense oversized weights. A Pi with 16 GB can hold more
weights but still has the same CPU limitations. Distillation, extra quantization,
pruning or cloud inference are separate choices with different semantics; this
runtime does not apply them implicitly.

Primary references: [Colibri](https://github.com/JustVugg/colibri),
[pinned llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/dd266785c2595775001c1c714bd9d92b3ef34cde/tools/server/README.md),
[Qwen Coder 14B model](https://ollama.com/library/qwen2.5-coder:14b).
