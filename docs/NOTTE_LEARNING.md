# Notte: teaching, public sources and local model training

The administrator's **Learning / Apprendimento** panel is at `/notte#learning`. It separates searchable knowledge from changes to model weights, and shows measured comparisons rather than an estimated percentage of the internet learned.

## Teach a lesson

Give the lesson a title and paste its content. Saving immediately stores and indexes the document: the next relevant Notte conversation can retrieve it without waiting for embeddings or a consolidation cycle. Updating a title replaces that lesson's text without counting it twice. The form retains a draft during live updates and reloads in the same browser session.

To include an example in the next weight-training run, open **Use in the next training / Usa anche nel prossimo addestramento**, and provide both a question and the ideal answer. These explicit examples are recorded separately from the searchable document. Saving a lesson does not itself change neural weights.

## Wikipedia and GitHub

Enter a Wikipedia topic or article URL; choose a language code and one to three articles. The importer reads plain article text, stores its canonical URL and revision, and immediately creates searchable chunks. Each stored document is bounded to 64,000 characters to fit the Pi's retrieval workload. The topic is unrestricted; the initial autonomous rotation covers Italian, Python, JavaScript, HTML, CSS, HTTP, Git and asynchronous programming.

Enter a public GitHub `owner/repo` or repository URL to read its current commit and up to six selected text files. README and documentation take priority over Python/web source files. Dotfiles, dependencies and build outputs are excluded. Files are read as data, never executed. Importing again checks the current commit and reuses an unchanged revision. The existing isolated programming curriculum also contributes its cached repository documents to searchable knowledge; an explicit source import checks GitHub for updates.

The reader identifies itself with the project name and repository URL as required by [Wikimedia's User-Agent policy](https://foundation.wikimedia.org/wiki/Policy%3AWikimedia_Foundation_User-Agent_Policy/en). It uses fixed provider API endpoints, does not follow redirects, bounds downloads and respects disabled connectors. Failed or interrupted acquisitions remain visible with their completed/total document count. Public GitHub access is subject to [GitHub's API rate limits](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api); an exhausted quota is an error, not learned knowledge.

Relevant factual questions can trigger a bounded public-source lookup. Ordinary greetings and personal questions do not. This can be disabled using **Consult online sources / Consulta le fonti online quando serve**. Private repositories require credentials and are outside this public-source reader.

## Public Reddit readings

Choose **Reddit public / Reddit pubblico** in the source form, select a recommended community or enter `r/name` or its public Reddit URL, and read one to twelve posts. The hourly autonomous reader alternates programming communities (`learnpython`, `Python`, `webdev`, `learnprogramming`, `programming`) with humor communities (`dadjokes`, `cleanjokes`, `jokes`). Automatic reading requires autonomy, web access, the Reddit connector and the Reddit reading switch to be enabled. These controls also govern background access; disabling the connector excludes the stored Reddit material from retrieval.

The reader imports text from the public Atom/RSS feed, including post bodies where available, rather than just the old 1,600-character excerpts. It does not download comment threads, images, private communities or author profiles. Canonical post links, feed revisions and source labels remain visible. The Learning panel reports actual post and word counts, and failed downloads do not increase them. The cache retains at most 192 posts for seven days; repeat requests reuse the same source and wait at least ten minutes before fetching the same community again. Downloads are bounded to 256 KiB and redirects are rejected.

Reddit posts are unverified retrieval context, **excluded from LoRA training examples**. Relevant Italian humor requests can retrieve English source examples; the chat instructions ask Notte to invent original Italian jokes, adapt wordplay, cite used sources and avoid unsolicited jokes in serious answers. This makes the readings available immediately, but does not prove an improvement in humor or alter benchmark scores. Original examples supplied through the teaching form can separately be included in a later training run.

Reddit has [announced the end of public RSS support on November 13, 2026](https://support.reddithelp.com/hc/en-us/articles/54353370049684-Changelog-October-8-2026). The connector shows this limitation and stops automatic RSS collection at that date. Continuing direct access then requires a platform-approved integration; unavailable feeds are reported without alternate scraping or access-control bypasses. [Reddit's Data API Terms](https://redditinc.com/policies/data-api-terms) do not grant permission to use user content for AI weight training.

## Real CPU training

The existing pinned `Qwen/Qwen2.5-Coder-0.5B-Instruct` base remains unchanged. Notte trains a LoRA adapter locally on the Raspberry Pi. This personalizes a pretrained model; it does not train a foundation model from scratch or copy all of Wikipedia/GitHub.

The dataset contains project-authored Italian and Python/web examples, sandbox-verified curriculum solutions, explicit administrator question/answer pairs, and bounded prose extracted from attributed public documents. Raw chat archives, credentials, arbitrary repository code and generated answers are not automatically training targets. Public GitHub prose is eligible only when its metadata declares MIT, Apache-2.0 or a supported BSD license. Source URL, revision and license stay with document-based samples; the full private dataset is not published.

Compatible legacy adapters are expanded without discarding their trained tensors: the restored tensors are checked for exact equality, and added layers start with a zero LoRA contribution. Incompatible adapter configurations retain their existing architecture.

Each run:

1. Measures the current personal model on a fixed evaluation suite.
2. Unloads cached inference models and runs an offline, isolated CPU worker.
3. Trains the last six attention layers through 67,584 adapter parameters (legacy two-layer checkpoints contain 22,528 parameters) with task-specific system messages, deterministic sampling, response-only loss, a 192-token sequence limit and up to 96 steps. Long samples can be truncated; the report records their count and actual response tokens consumed.
4. Evaluates ten held-out prompt/answer targets periodically and retains the best checkpoint with a Python-loss regression guard. No holdout prompt is inserted into the training dataset.
5. Merges and converts an accepted adapter to GGUF Q4_K_M, then runs the same generation tests on the candidate.
6. Promotes only a candidate with improved held-out loss, changed weights, all four independent Python execution tests passing, and no decrease in the six Italian/web textual checks.

The six Italian/web checks use expected keywords, not a comprehensive semantic judge. Passing this small suite does not establish general superiority. Both successful and rejected candidates retain their metrics and logs. An unchanged dataset does not trigger another automatic daily training run; manual training remains available.

An accepted model can be used by ordinary Notte conversations in the fast profile, through **Use validated model / Usa il modello validato**. The dedicated Coding and advanced profiles retain their configured models. Switching the preference does not erase knowledge or alter the original base models. The active adapter and one previous accepted adapter/model remain available for rollback; failed candidates and large conversion intermediates are removed while their reports remain.

The worker pauses for resource pressure and other model work. A new foreground chat stops training to free RAM, preserving the last accepted version. The daily schedule uses Europe/Rome and the configured local hour.

## What the numbers mean

| Metric | Definition |
|---|---|
| Archived words | Count of word tokens in the currently stored source/lesson text; refreshed documents are counted once. |
| Indexed documents % | Stored documents with searchable chunks divided by stored documents. It is not a percentage of Wikipedia learned. |
| Training progress % | Completed optimization steps divided by planned steps. Baseline evaluation, loading, conversion and final tests are separate phases. |
| Dataset words | Word count of prompts and reference answers prepared for that run, including samples that may be truncated by the sequence limit. |
| Used response tokens | Actual unmasked response tokens consumed across optimization steps. |
| Python tests | Four generated functions executed against independent cases in the isolated sandbox. |
| Italian/web checks | Six indicative textual checks on generated answers. |
| Validation loss | Average held-out loss on the same adapter/base before and after optimization; lower is better. |
| Generation speed | Generated tokens divided by Ollama-reported generation time across the fixed suite; excludes model-loading time. |

The **Before and after / Prima e dopo** histogram uses measured values with a separate scale for each metric and an accessible table. Missing measurements are dashes. A rejected run is labeled as rejected and cannot silently replace the active checkpoint. Detailed private logs and datasets remain in the **Personal model / Modello personale** section.

## Validation and measurements

Regression coverage includes immediate retrieval, updates/deduplication, connector exclusion, provider URL validation, source provenance, failures/interruption, request-size bounds, ordinary-chat model routing, promotion/rejection and skipping unchanged daily datasets. Browser checks exercise lesson entry, draft retention, reloads, tables/histograms and a 390-pixel phone viewport.

Measured on 11 October 2026 on the existing Raspberry Pi 5 (8 GB RAM, NVMe, CPU only). Both candidates passed promotion and retained a rollback checkpoint.

| Measurement | Previous model #17 | New model #18 |
|---|---:|---:|
| Validation loss | 1.073382 | 1.058148 |
| Python execution tests | 4 / 4 | 4 / 4 |
| Italian/web textual checks | 5 / 6 | 5 / 6 |
| Generation speed on the same suite | 26.39 token/s | 26.65 token/s |
| Total evaluation time, including loading | 27.458 s | 19.408 s |

The loss decreased **1.42%**; measured test success remained **90%**. Speed differences on one short suite can reflect cache and runtime variation. The new run used 68 examples, 2,080 dataset words, 68 optimization steps and 67,584 trainable parameters. Weight delta L1 was 211.1468; worker RSS peaked at 3,729.98 MiB. The corpus contained 32 immediately searchable documents and 54,269 archived words, including four successfully acquired Wikipedia articles.

[Raw aggregate measurements and model/adapter hashes](NOTTE_LEARNING_RESULTS.json) record both runs, without private lesson contents, model weights or chat transcripts.

A separate real-model probe created a new, random laboratory identifier in a temporary database. The model answered using that newly taught identifier, and retrieval still found it after reopening the database. The probe used the accepted model #18, reported 96 output tokens and completed in 5.753 seconds. Its temporary lesson was removed with the test database; production conversations and lessons were not used.
