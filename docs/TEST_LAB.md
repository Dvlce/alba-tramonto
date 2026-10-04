# Notte Test Lab and project evolution site

The public project site is `/optimization`, with information, repository-curated
news, measured benchmarks, IT/EN text and a dated evolution timeline. It reads
only `docs/OPTIMIZATION_HISTORY.json` and `docs/SSD_RUNTIME_RESULTS.json`.
It never reads the private Test Lab database, personal chat, diary or credentials.
Public report/figure downloads use a fixed filename allowlist. News means actual
documented project changes, not generated external headlines.

Notte's **Test Lab** tab and Android's native **Test Lab** menu provide:

* An installed local model, a shared prompt, 512/1024/2048 context and 8–256
  output tokens. Oversized prompts are rejected rather than silently truncated.
* Normal Ollama, optimized SSD or a sequential comparison. Normal means the
  existing Ollama chat API without custom SSD runtime, checkpoint restore or
  draft. Its built-in kernels and existing model quantization remain.
* Mapped, verified draft or native CPU policies with the SSD runtime's RAM,
  temperature, swap, deadline and process cleanup guards. The regular Ollama
  model above 6 GiB is refused on the existing 8 GB Pi; use SSD-only for explicit
  oversized experiments. Model downloads/builds require the documented admin
  setup and are never initiated from a lab prompt.
* The actual generated responses, first-token latency including startup,
  total execution duration, declared token counts/decode rate, before/after
  system metrics and optimized-process peak metrics. Missing data stays missing.
* Automatic bar charts, private JSON export and a standalone HTML report with
  embedded SVG charts. Errors and interrupted partial responses are retained.

The installed tag's `/api/show` GGUF SHA must equal the registered SSD SHA before
an optimized/comparison run starts. A retagged Ollama model must be registered
again. No smaller-model substitution occurs. Inputs and outputs are stored in
`core_lab_runs`, separate from chat/RAG/training examples. Activity logs contain
run identifiers and status, not private lab prompt bodies. Production profile,
language, SSD flags, moods and daily training configuration are not changed.

Runs share the existing inference lock, run one backend at a time and yield to
foreground chat. A foreground lab request cancels background reflection/study
after cleanup, but refuses a concurrent chat or training. Stop cancels the run,
saves partial output and terminates the native process group. On a service
restart, stale `running` rows are marked `interrupted`.

Comparison conditions are explicit: normal first, startup included, no global
OS file-cache eviction and no private conversation history. The second path can
benefit from already cached weights. Ollama and llama.cpp apply their respective
model templates; temperature 0 and seed 42 do not guarantee identical kernels
or outputs. Text equality is reported separately. Ollama's stream does not
provide token IDs, so cross-backend token identity remains **unavailable**.
The tool does not label a faster response more intelligent or automatically
execute arbitrary user-generated code as a quality check.

## API

All private endpoints require an existing administrator session; POST also
requires the current CSRF token and the existing origin/body/rate checks.

```text
GET  /api/notte/lab
POST /api/notte/lab
GET  /api/notte/lab/{id}/export
GET  /api/notte/project        (native client, curated public data only)
GET  /optimization/data       (public, curated data only)
```

```json
{
  "model": "qwen2.5-coder:7b",
  "prompt": "Quanto fa 17+25? Rispondi solo con il numero.",
  "mode": "compare",
  "policy": "mapped",
  "context": 512,
  "output": 16
}
```

The action is asynchronous (202). `/api/notte/status` includes current lab
samples and the 30 most recent runs. Private exports retrieve a saved run by ID.
`POST /api/notte/action` with `{"action":"stop"}` cancels the current run.
SQLite rows and private exports are included in the existing encrypted backups;
no web account or external telemetry service is required.

## Native Android 1.4

Android uses Views, Spinners and a Canvas bar-chart view, with Italian/English
labels, JSON exports and HTML/SVG report export. Polling updates result views
without rebuilding the form or clearing its prompt. Project updates also render
as native cards; opening the information website is an explicit external link.
`/notte#lab` and `/notte#project` select the corresponding native section when
Android App Links are enabled. A new APK is required for these new menu entries;
the existing certificate/package remain, permitting an in-place upgrade.

Compilation and emulator tests run on GitHub. Release candidates have a CI-only
temporary signature and are subsequently signed locally with the established
private release key; that key is never sent to CI or the repository.

## Validation and reports

The unit suite exercises model identity mismatch, bounds, cancelled partial
output, preserved settings, negative speed changes, SSE/NDJSON metrics,
restart recovery, admin/CSRF boundaries and public/private separation.
The browser fixture checks IT/EN, desktop/mobile layout, fixed prompt height,
input preservation, SVG report downloads and unpublished private marker data.
Native instrumentation covers menu navigation, selected-model requests,
Canvas charts, input preservation and native evolution cards. Fixture rates
are never included as real hardware benchmark measurements.

Follow [the reporting convention](TESTING_REPORTS.md) for every test campaign.
Hardware test results for this new lab are recorded in
[the measured comparison report](TEST_LAB_RESULTS.md), separately from the
[previous controlled SSD experiments](SSD_RUNTIME_RESULTS.md).
