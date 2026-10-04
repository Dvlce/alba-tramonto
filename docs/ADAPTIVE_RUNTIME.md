# Notte 1.5: token, context and runtime evolution

All inference and resource measurements run on the Raspberry Pi 5, not the Mac.
This is a set of measurable CPU/SSD policies, not a new foundation-model
architecture. Weight identity is recorded; replacing a 7B with a 0.5B is not a
speed optimization of the same model.

## Policies and evidence sources

| Public name | Policy | What changes | Main limitation |
| --- | --- | --- | --- |
| Standard | normal | Installed Ollama model, requested context/output, 4 CPU threads | Cold loading and prompt processing |
| Notte SSD | mapped | Same GGUF, mmap, no full repack copy, f16 KV, native ARM kernels | Dense weights still need every layer |
| Notte ARM | native | Native repacking when the conservative transient memory forecast fits | Needs a second weight copy while packing; refused if RAM cannot fit it |
| Notte KV8 | compact | Same weights, mmap/no repack, q8_0 K/V instead of f16 | KV precision changes; quality must be checked, not called lossless |
| Notte Draft | speculative | Small draft proposes tokens verified by the chosen target | Added memory and draft overhead; acceptance depends on task |
| Notte Warm | warm | Same Ollama weights/prompt/context; retains the standard model for the next request | Second request has a warm cache; not a balanced cold comparison |
| Notte CPU2 | cpu2 | Same Ollama target with two decode threads | May trade prompt speed for memory-bandwidth efficiency; measure both |
| Notte Flux | adaptive | Compact stable system prefix, task-aware output reserve and bounded context | Prompt instructions/budgets differ; equal text or general speed is not guaranteed |

[Ollama's FAQ](https://docs.ollama.com/faq) documents model residency, preloading,
context-driven memory, parallelism and KV precision. Keeping a resident model
reduces reload work; a changing context allocation can still require reloading.
We retain one active inference model and a stable 2048-token chat allocation for
short turns. No extra concurrent model copies are introduced.

[The chat API](https://docs.ollama.com/api/chat) reports load, prefill, decode and
token counts separately. We store those declared counts rather than calling our
planning estimate an exact tokenizer result. The first token and full elapsed
request are wall-clock measurements, including setup and loading.

[llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
provides native thread/batch controls, mmap/repack, Flash Attention, KV types,
prompt caching and speculation. We use the existing pinned ARM binary, one slot,
128-token microbatches and thermal/memory guards. Unsupported policies fail
visibly. Compact's RAM admission remains conservatively based on f16 KV.

[Prompt Cache](https://arxiv.org/abs/2311.04934) explains attention-state reuse
for overlapping prefixes. Our static personality stays first; changing emotion,
selected memories and response-length instructions move after stable history.
This improves cache eligibility; it is not a claim that every prefix is reused.
Private persistent SSD checkpoints remain scoped to a model hash/backend version.

[Colibri](https://github.com/JustVugg/colibri) streams routed MoE experts.
[LLM in a flash](https://arxiv.org/abs/2312.11514) studies sparsity-aware flash
loading and transfer layouts. Neither establishes that arbitrary dense Qwen
weights can be skipped without changing computation. Sparse activation,
model-specific MTP, distributed inference and accelerators require other model
architectures, compatible kernels or extra hardware; they are not enabled by a
web setting or claimed as implemented here.

## Response budgeting

`core/generation_policy.py` classifies each request before generation:

| Request | Output ceiling |
| --- | ---: |
| Greeting/simple arithmetic | 48 tokens |
| Explicit short answer | 96 tokens |
| Ordinary conversation | 224 tokens |
| Code | 640 tokens |
| Detailed explanation | 768 tokens |
| Explicit complete/detailed code | 1024 tokens |

These are ceilings, not required output lengths. Instructions favor direct
answers; code keeps enough reserve for a complete solution. Streaming ends at
the model's natural stop. If it reaches its configured ceiling, the activity
record exposes `output_limit_reached`; we do not claim the output is complete.

A conservative UTF-8-byte planning estimate reserves output and message overhead.
Older whole turns and low-ranked retrieved excerpts can be omitted from this
request window, while original events remain in SQLite/RAG. Current input and
instructions are never silently shortened: overlong input is rejected with a
request to split it. Chat grows up to 4096 tokens when needed, with a lower
ceiling under memory pressure. This is local working context, not deletion of
long-term memory or a promise of a model's advertised 32K performance on the Pi.

Chat uses lexical retrieval to avoid loading an embedding model between turns.
Background consolidation still computes embeddings. Background study/reflection
and daily training wait for a two-minute foreground grace period after a chat.
The operator can still start explicit tests/study actions. Language follows the
message or selected IT/EN setting.

## Model lifecycle

`python -m core.model_family --root /home/dvlce/supporto-ai` creates and verifies
same-GGUF aliases: `notte:latest` from Qwen2.5 1.5B and `notte-coding:latest` from
Qwen2.5-Coder 7B. Naming is branding, not a claim of newly trained foundation
weights. Personal diary/RAG is shared. The actual daily CPU LoRA remains on its
explicit 0.5B training base; it cannot be applied to a 1.5B or 7B architecture.
Its current and previous verified adapters remain inspectable as experimental
personal checkpoints, with their true base and tests in the training section.

After encrypted backup, stop Alba and add `--clean` to remove unrelated installed
chat tags and discarded generated versions. Aliases retain their shared blobs;
embedding and the internal speculation GGUF are technical dependencies. Training
keeps the active checkpoint plus one verified rollback; rejected candidates do
not displace that rollback. Old weights/adapters are removed only after successful
Ollama removal. Provenance, source hashes, reports and logs remain. Cleanup never
runs arbitrary model names supplied by a web prompt. Restart Alba after updating
its model configuration. No private keys, accounts, diaries or chat memory are
removed.

## Online comparison and reports

Open `/optimization#test` and activate the administrator test. One submit runs
standard first, then the chosen policy, with the same model and original prompt.
The page streams each result in order and draws first-token, total-wait, decode
and output-token bar charts. JSON and standalone HTML/SVG reports are private.
The equivalent Notte/native Android Lab remains available. The public news and
benchmarks read only explicitly published repository probes.

Read [the reporting protocol](TESTING_REPORTS.md) and the campaign's results
before choosing a policy. Record cache/order, ceiling hits, errors and executed
code checks. A shorter answer must still satisfy the task; a faster number alone
is not proof of better intelligence. Large models beyond RAM retain the limits
from [the original SSD results](SSD_RUNTIME_RESULTS.md).
