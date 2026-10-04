# Benchmark reports and evolution history

Requested reporting convention: every new benchmark/test campaign includes a
report, documentation of the change and bar charts showing measured results.
Record improvements, regressions, failed quality checks and uncompleted tests.
Do not generate another model run just to populate a chart when measurements
already exist. Model execution and heavy compilation stay on the Raspberry;
offline report rendering can run on the Mac without running an AI model.

For performance campaigns, retain machine/model identities, commit/backend
revision, weight SHA, quantization, context, sampling, cache conditions, actual
outputs or private-content-free metrics, and quality assertions. Compare the
same workload before/after; explicitly mark unmatched workloads. Use bars with
units and the preferred direction. Show each prompt type as well as averages
so a regression cannot disappear in a headline. Never infer general intelligence
from a tiny speed or coding suite.

For functional/security checks, document passed, failed and skipped counts with
the environment and command. Charts can summarize outcomes when useful; they
are not performance improvements. Keep private conversation text and credentials
out of published artifacts.

Current example: [SSD evolution report](SSD_RUNTIME_RESULTS.md), raw
[JSON](SSD_RUNTIME_RESULTS.json), four PNG/SVG figures in `ssd-results/` and
the offline renderer `plot_ssd_results.py`.

Rebuild figures from the recorded data without invoking any model:

```sh
python3 -m venv /tmp/alba-report-venv
/tmp/alba-report-venv/bin/pip install matplotlib==3.10.8
/tmp/alba-report-venv/bin/python docs/plot_ssd_results.py
```

Matplotlib is a reporting dependency only; do not add it to the Raspberry's
inference service requirements. For future campaigns, retain the new dataset
and adapt the renderer to its measured tasks instead of overwriting evidence
from earlier evolutions.
