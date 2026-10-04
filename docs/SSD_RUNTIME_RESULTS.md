# SSD runtime: measured Raspberry Pi results

Measured on 4 October 2026 on the actual Raspberry Pi 5, 8 GB RAM, NVMe,
CPU-only llama.cpp revision `dd266785c2595775001c1c714bd9d92b3ef34cde`.
Compilation and all model execution happened on the Pi. No LLM ran on the Mac.
See [setup and implementation](SSD_RUNTIME.md) and the
[public measurements, outputs and token IDs](SSD_RUNTIME_RESULTS.json).

## Outcome

The tool executes the selected model's existing Q4_K_M GGUF unchanged, with f16
KV, explicit CPU/mmap settings and no smaller-model fallback. It includes memory
planning, bounded context checkpoints, verified speculative decoding and a
resource watchdog. It remains **experimental and disabled by default**: these
measurements do not establish a fluid large-model chat on an 8 GB Pi.

## Controlled 7B comparison

Qwen2.5-Coder 7B occupies 4,683,074,048 bytes. Rows 68–69 compare the same
target, template, temperature 0, seed 42 and 1,024-token context. Each of three
public prompts runs once with a new prompt and once repeated. A new prompt does
not mean the operating system's SSD cache was cleared. The speculative policy
uses Qwen2.5-Coder 0.5B as a draft, with every proposal verified by the 7B target.

| Repeated prompt | Mapped target, token/s | Verified draft, token/s | Change |
| --- | ---: | ---: | ---: |
| Python order-preserving `unique` | 2.552 | 3.493 | +36.9% |
| Italian arithmetic | 2.522 | 3.053 | +21.1% |
| English SSD/RAM explanation | 2.521 | 1.875 | −25.6% |

All six speculative outputs matched the mapped target's token IDs and text.
Both code outputs passed three independent functional cases in the offline
sandbox. This is a small runtime comparison, not a general intelligence test or
a guarantee of identical output for every prompt. Mean repeated-prompt decode
rates were 2.53 and 2.81 token/s. Peak RSS was 4.82 and 5.28 GB; neither final
policy swapped. Load times were 8.501 and 2.637 seconds with different file-cache
conditions and should not be treated as a controlled load-speed improvement.

Rows 65–67 retain earlier exploratory runs with CPU repacking, which produced
different token sequences and up to 1.89 GB of process swap. The final admission
rule rejects repacking unless its transient duplicate fits; final speculation
also disables repacking. Those earlier rows are retained rather than presented
as successful final-policy results.

## Persistent context checkpoint

Row 70 performs the same short public arithmetic completion, saves an f16
checkpoint, stops the server, starts it again and restores the checkpoint.
Output text and token IDs match. The request takes 7,424 ms initially and
2,135 ms after restoration; native timings report 46 cached prompt tokens and
one newly processed token. These durations exclude startup and checkpoint I/O.
The checkpoint is private, atomically written, capped with other checkpoints
at 512 MiB and separate from the conversation archive.

## Actual long-history Notte chat

The short checkpoint result does **not** translate into fast production chat.
Only numerical metadata from actual chat is exported; private history is not
included in this document or the JSON.

| Implementation stage | First-token latency, seconds | Total request, seconds |
| --- | ---: | ---: |
| Initial integration, first request | 193.876 | 194.786 |
| Initial integration, following request | 186.010 | 186.890 |
| Stable prompt layout, first request | 327.304 | 328.386 |
| Stable prompt layout, following request | 314.831 | 315.967 |
| SSE drain/checkpoint connection fix, restored checkpoint | 250.093 | 251.162 |

All used the mapped 7B target. Context selection changed between implementation
stages, so this table is diagnostic evidence rather than a controlled speed
comparison. Long prompt evaluation dominates; changing history/retrieved memory
prevents full prefix reuse. The final fix drains the SSE response before saving
and uses a separate checkpoint connection, resolving the observed save failure.
Even with restoration, the final real chat still takes over four minutes.
The default Ollama path and the user's selected profile remain available.

## Genuine 14B above RAM

Row 71 runs Qwen2.5-Coder 14B Q4_K_M: **8,988,110,784 bytes**, unchanged,
with mmap and no repacking. It completes six short probes, but averages only
**0.10 token/s** on repeated prompts. Loading takes 33.896 seconds. Peak RSS is
7.94 GB with 262 MB process swap; the process reads about **230 GB** from disk
over the run. These probes use a 32-token limit and shorter prompts, so they are
not a quality comparison with the 7B suite.

The code probe **fails**: it returns
`unique_values = list(dict.fromkeys(values))` instead of the required function,
and the independent test raises `NameError`. Arithmetic returns `42`; the short
English answer is `RAM is faster than SSD.` A larger model did not pass this
specific code task and is not promoted as a faster or better default.

Mapping a model larger than RAM lets it execute but cannot supply RAM bandwidth
from an SSD. This integration does not implement Colibri's expert LRU, learned
pins or custom MoE kernels. Models with sparse experts need separate measured
support; no fluid MoE or universal 12 GB model claim is made here.

## Validation and availability

355 unit tests passed on the Pi's Python 3.13, including malformed GGUFs,
verified imports, admin access, policy bounds, process cleanup, private/atomic
checkpoint handling, prompt data preservation, SSE draining and explicit
failure without model substitution. Public hardware data contains seven rows
and 38 samples, plus the five production latency observations above.

The backend is installed on the Pi. Benchmark rows appear in the existing
native Android app's System section; this backend change requires no new APK.
The runtime can be enabled explicitly through the documented local admin CLI
or authenticated API and disabled without deleting weights or memory.
