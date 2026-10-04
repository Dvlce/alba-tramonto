# Raspberry Pi inference and training results

Measured on 4 October 2026 on the existing Raspberry Pi 5, 8 GB RAM, NVMe, Ollama 0.34.2 CPU. All models and training ran on the Pi. Android emulation ran in GitHub Actions; no LLM ran on the Mac.

## Inference protocol

64 samples across eight model tags. Four policies: context 1024 with 2 threads and mmap; context 1024 with 4 threads and mmap; context 2048 with 4 threads and mmap; context 1024 with 4 threads without mmap. Each policy was tested cold after unloading, then warm. Ollama loaded one model at a time. Temperature 0, output limit 140 tokens.

Task: produce `unique(values)` while preserving order. Independent cases cover repeated integers, an empty list and case-sensitive strings. This small task measures runtime behavior and detects a basic coding error; it does not rank general intelligence.

| Model · Q4_K_M | Warm tokens/s | Warm first token | Code tests passed |
| --- | ---: | ---: | ---: |
| `qwen2.5:1.5b` | 12.76–13.36 | 85–167 ms | 0/8 |
| `qwen2.5-coder:1.5b` | 12.49–13.34 | 87–102 ms | 0/8 |
| `qwen2.5-coder:3b` | 5.99–6.29 | 167–185 ms | 8/8 |
| `qwen2.5-coder:7b` | 2.63–2.94 | 356–434 ms | 8/8 |
| `qwen3:4b-instruct-2507-q4_K_M` | 4.68–5.11 | 215–373 ms | 8/8 |
| `llama3.2:1b-instruct-q4_K_M` | 14.27–15.84 | 73–176 ms | 8/8 |
| `gemma3:1b` | 13.23–14.06 | 163–229 ms | 8/8 |
| `notte-personal:20261004-7` | 26.71–29.31 | 48–80 ms | 0/8 |

Qwen 1.5B and its Coder variant returned `list(set(values))`, losing order. The default therefore uses Qwen 1.5B for general chat and Coder 3B for code. The 7B model is selectable, with a substantial throughput cost. Llama and Gemma remain installed and selectable. The personal 0.5B passed its four training promotion checks but failed this additional task; it remains an explicit personal-model chat, not the default coder.

## Full production chat

Using the real Notte prompt, persistent state and conversation history, a short Italian RAM/SSD question took 8.344 seconds to the first token and 17.774 seconds total with a cold model. The following warm question took 2.897 seconds to the first token and 8.180 seconds total. Generation ran at 11.35–11.45 tokens/s. These are individual samples; the short benchmark above does not represent full-chat latency. Streaming shows partial text while generating.

## Actual personal training

Cycle #7 trained 13 project/verified examples for 13 steps, updated 22,528 LoRA parameters, and changed validation loss from 0.592517 to 0.363670. Weight delta L1: 127.0597. Full-worker RSS peak including saving: 3574.0 MiB. Total training/conversion/import/promotion cycle: 83 seconds.

The adapter was merged in 512 MB shards, converted to Q4_K_M GGUF and imported into Ollama. Four independently executed holdout functions passed: `cube`, `is_positive`, `last_or_none`, `maximum`. This establishes a real adapter update and a bounded promotion check, not broad capability gains. Failed preparatory runs stay in the private activity/version history.

Daily training at 03:00 Europe/Rome resumes the active adapter, unloads cached inference weights first and reserves RAM. Foreground Notte chat cancels training before loading the chat model. The current worker budget is 4500 MiB; systemd adds a 5 GiB cap where the memory controller is available. A validation or functional failure keeps the previous accepted model.

[Raw numerical samples and code results](PI_INFERENCE_RESULTS.json). Training dataset contents and private user data are excluded.

## SSD and Colibri scope

The dense models already reside on NVMe. `mmap`, a smaller context, a warm model, compact state and avoiding embedding swaps reduce resource use. Dense models still need their weights for every token. [Colibri](https://github.com/JustVugg/colibri) routes and streams selected experts for supported MoE architectures; this release provides a common local inference policy and measured matrix, not universal expert streaming.

Additional tested model tags: [Llama 3.2 1B Q4](https://ollama.com/library/llama3.2:1b-instruct-q4_K_M), [Gemma 3 1B](https://ollama.com/library/gemma3:1b).
