# Open-weight ASR models from Chinese/Asian labs for Korean lecture transcription (as of 2026-11-01)

Scope: Qwen3-ASR (0.6B/1.7B + ForcedAligner, Flash API for reference), Qwen2-Audio / Qwen2.5-Omni / Qwen3-Omni, the Alibaba FunASR family (SenseVoice, Fun-ASR / Fun-ASR-Nano / Fun-ASR-MLT-Nano, Paraformer), Zhipu GLM-ASR-Nano, DataoceanAI Dolphin, FireRedASR / FireRedASR2, StepFun Step-Audio 2, Kimi-Audio, Xiaomi MiDashengLM, ByteDance Seed-ASR (closed, for reference), plus OpenMOSS MOSS-Transcribe-Diarize (Fudan/OpenMOSS, a July 2026 release that claims Korean support).
Method: primary sources (GitHub READMEs fetched raw, Hugging Face model cards and API metadata, arXiv HTML of the technical reports, GitHub issues, and the vLLM and llama.cpp support lists). Third-party Korean benchmarks are labelled as such.

Metric note: Korean is scored with CER in Qwen3-ASR, SenseVoice and the community cards. The Dolphin and Seed-ASR tables are labelled "WER" even for Korean. Text normalization differs from paper to paper, so **numbers from different sources are not directly comparable**. Comparisons are only fair within one table.

---

## Q1. Which models officially support Korean, and what Korean scores have been published (vs Whisper large-v3 on the same test set)?

### Takeaway
Official Korean support: **Qwen3-ASR 0.6B/1.7B** (plus the ForcedAligner), **SenseVoice-Small**, **Fun-ASR-MLT-Nano-2512** (not base Fun-ASR-Nano), **Dolphin**, **Qwen3-Omni** (speech input), **MOSS-Transcribe-Diarize**, and the closed Seed-ASR (ML) and Qwen3-ASR-Flash APIs. **Qwen3-ASR-1.7B has the strongest published open-weight Korean numbers**: FLEURS-ko CER 2.57, CommonVoice-ko 5.88, MLC-SLM-ko 8.61. However, the Qwen paper gives no per-language Whisper-large-v3 baseline. Same-table comparisons with Whisper-large-v3 exist only for SenseVoice (CommonVoice-ko), Dolphin (FLEURS-ko, CV17-ko, Dataocean-ko) and Seed-ASR. **GLM-ASR-Nano, FireRedASR/FireRedASR2, Fun-ASR-Nano (base), Paraformer, Step-Audio 2, Kimi-Audio and MiDashengLM have no Korean support or no Korean evaluation.**

### Cited Findings

**Qwen3-ASR (Alibaba Qwen): 0.6B and 1.7B, released 2026-01-29**
- The family has two models, Qwen3-ASR-1.7B and Qwen3-ASR-0.6B, plus Qwen3-ForcedAligner-0.6B. It covers language ID and ASR for "30 languages and 22 Chinese dialects" (52 in total), and Korean (ko) is explicitly listed. Released 2026.1.29, with native Transformers support (`-hf` checkpoints) added 2026.6.26 — [QwenLM/Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)
- Architecture: the 1.7B is Qwen3-1.7B plus a projector plus an AuT encoder (300M, 1024 hidden). The encoder downsamples 8x to a 12.5 Hz token rate and uses a dynamic flash-attention window of 1 s to 8 s, which enables both streaming and offline use. AuT was pretrained on about 40M hours of pseudo-labelled ASR data, mostly Chinese and English. The 1.7B checkpoint is about 2.35B params total in safetensors — [Qwen3-ASR tech report, arXiv 2601.21337](https://arxiv.org/html/2601.21337); [HF API metadata Qwen/Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- **Official per-language Korean results (Table A.2, CER; columns are 0.6B / 1.7B / Flash-1208 API):**
  - FLEURS ko: **3.72 / 2.57 / 2.07**
  - CommonVoice ko: **8.48 / 5.88 / 3.82**
  - MLC-SLM ko (conversational): **10.31 / 8.61 / 8.09**

  Source: [arXiv 2601.21337, Table A.2](https://arxiv.org/html/2601.21337). The paper says CER is used for Korean ("character-based languages (e.g., Mandarin Chinese, Cantonese, and Korean)") — [same](https://arxiv.org/html/2601.21337)
- Whisper-large-v3 appears in the Qwen3-ASR comparison only as **multi-language averages**, never per language. FLEURS 12-language average (includes ko): Whisper-large-v3 5.27, Qwen3-ASR-1.7B 4.90, 0.6B 7.57, GLM-ASR-Nano 16.08, Fun-ASR-MLT-Nano 10.03. CommonVoice 13-language average (includes ko): Whisper 10.77, Qwen3-ASR-1.7B 9.18. MLC-SLM 11-language average (includes ko): Whisper 15.68, Qwen3-ASR-1.7B 12.74 — [Qwen3-ASR README, Multilingual ASR Benchmarks](https://github.com/QwenLM/Qwen3-ASR)
- No official KsponSpeech or Zeroth numbers from Qwen — [arXiv 2601.21337](https://arxiv.org/html/2601.21337) (Korean appears only in the FLEURS, CommonVoice and MLC-SLM tables and the internal News-Multilingual set)
- **Third-party KsponSpeech/Zeroth results for Qwen3-ASR-1.7B (not primary; protocols differ):**
  - TeamUNIVA, on hand-reviewed, TN/ITN-normalized test sets (best of TN and ITN references per utterance), base Qwen3-ASR-1.7B CER: KsponSpeech 8.65, Zeroth 2.64, CommonVoice-ko 7.19, FLEURS-ko 1.42, ClovaCall 4.48, Korean total 6.86. Their Korean fine-tune `qwen3_asr_1.7b_ko` reaches KsponSpeech 5.94, Zeroth 2.20, CV-ko 6.03, FLEURS-ko 1.26, ClovaCall 2.83, total 4.83, while LibriSpeech WER goes from 2.50 to 2.77 (Apache-2.0) — [TeamUNIVA/qwen3_asr_1.7b_ko](https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko); [beta card](https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko_beta)
  - A Korean Zipformer author measured on KsponSpeech eval (6,000 cuts, no-punctuation CER): **Qwen3-ASR-1.7B 9.76 clean / 10.22 other / 9.99 overall**, **Whisper-large-v2 13.70 / 12.64 / 13.17**, and their own 156M streaming Zipformer 7.16. Note the Whisper baseline is v2, not v3 — [kangkyu/icefall-asr-ko-streaming-zipformer-174m](https://huggingface.co/kangkyu/icefall-asr-ko-streaming-zipformer-174m)
  - BuzzASR (Whisper-large-v3 Korean fine-tune; EMNLP 2026 Findings paper arXiv 2609.09554) reports Whisper-large-v3 zero-shot normalized CER of 5.31 on FLEURS-ko and 6.01 on CV25-ko. It claims the lowest CER versus Qwen3-ASR and other systems on combined FLEURS+CV, but **its card does not print the Qwen3-ASR numbers** — [BuzzASR/korean](https://huggingface.co/BuzzASR/korean)

**Qwen3-ASR-Flash (API, reference)**
- The paper reports snapshot "Qwen3-ASR-Flash-1208" as an API model (Korean numbers above) — [arXiv 2601.21337](https://arxiv.org/html/2601.21337)
- Alibaba Model Studio lists `qwen3-asr-flash` (sync, files up to 10 MB / 5 min, streaming output) and `qwen3-asr-flash-filetrans` (async, up to 12 h / 2 GB). Word-level timestamps on Filetrans are limited to a list of languages that includes Korean — [Alibaba Cloud Model Studio: Qwen speech recognition](https://www.alibabacloud.com/help/en/model-studio/qwen-speech-recognition)
- A dated snapshot `qwen3-asr-flash-2026-02-10` is listed on OpenRouter — [OpenRouter](https://openrouter.ai/qwen/qwen3-asr-flash-2026-02-10) (aggregator; unverified against Alibaba)

**Qwen2-Audio / Qwen2.5-Omni / Qwen3-Omni**
- Qwen2-Audio-7B-Instruct (July 2024, Apache-2.0, about 8.4B) reports ASR only on LibriSpeech, AISHELL-2 and FLEURS-zh. **No Korean evaluation** — [QwenLM/Qwen2-Audio](https://github.com/QwenLM/Qwen2-Audio); [HF card](https://huggingface.co/Qwen/Qwen2-Audio-7B-Instruct)
- Qwen2.5-Omni reports ASR on Common Voice 15 en/zh/yue/fr and FLEURS zh/en. **No Korean** — [QwenLM/Qwen2.5-Omni](https://github.com/QwenLM/Qwen2.5-Omni)
- Qwen3-Omni-30B-A3B (HF repo created 2025-09-20; card `license: other`, `license_name: apache-2.0`) lists Korean among its 19 speech-input languages. It reports only a "Fleurs-avg (19 lang)" WER (Qwen3-Omni Instruct about 5.3), and its tech report gives **no per-language Korean ASR score** — [QwenLM/Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni); [arXiv 2509.17765](https://arxiv.org/html/2509.17765); [HF card](https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct)

**SenseVoice (Alibaba Tongyi / FunAudioLLM), July 2024**
- The released SenseVoiceSmall checkpoint (234M, non-autoregressive) supports **zh, yue, en, ja, ko**. The 50+ language claim applies only to the unreleased SenseVoice-Large — [FunAudioLLM/SenseVoice README](https://github.com/FunAudioLLM/SenseVoice); [modelscope/FunASR model table](https://github.com/modelscope/FunASR)
- **CommonVoice ko CER, same table:** Whisper-Small 10.48, **Whisper-Large-v3 5.59**, **SenseVoice-Small 8.28**, SenseVoice-Large 5.21 (not released). On Korean, SenseVoice-Small is *worse* than Whisper-large-v3 — [FunAudioLLM paper, arXiv 2407.04051, Table 6](https://arxiv.org/html/2407.04051)
- Latency: SenseVoice-S takes 70 ms for 10 s of audio (RTF 0.007), against 1281 ms for Whisper-L-V3 — [arXiv 2407.04051, Table 7](https://arxiv.org/html/2407.04051)
- Training data: SenseVoice-Small used about 300k hours across the 5 languages — [arXiv 2407.04051](https://arxiv.org/html/2407.04051)

**Fun-ASR family (Alibaba Tongyi), Fun-ASR-Nano-2512 and Fun-ASR-MLT-Nano-2512, December 2025**
- **Fun-ASR-Nano-2512 (800M): Chinese, English and Japanese only, plus Chinese dialects. No Korean.** **Fun-ASR-MLT-Nano-2512 (800M): 31 languages including Korean**, trained on "hundreds of thousands of hours" — [FunAudioLLM/Fun-ASR README](https://github.com/FunAudioLLM/Fun-ASR)
- The MLT-Nano card states that its benchmark tables "do not contain a column identified as Fun-ASR-MLT-Nano-2512 … MLT per-language results will be added". So there is **no published Korean score** — [HF Fun-ASR-MLT-Nano-2512](https://huggingface.co/FunAudioLLM/Fun-ASR-MLT-Nano-2512)
- The Fun-ASR tech report's multilingual table (Fun-ASR-ML and ML-Nano against Whisper-large-v3, dolphin-small and seamless-m4t) covers only zh, en, id, th and vi. **No Korean** — [arXiv 2509.12508 §6.2.6](https://arxiv.org/html/2509.12508)
- The flagship Fun-ASR (0.7B encoder + 7B LLM, 7.7B in total) is API-only — [Fun-ASR README](https://github.com/FunAudioLLM/Fun-ASR); [arXiv 2509.12508](https://arxiv.org/html/2509.12508)

**Paraformer (FunASR)**
- Paraformer-zh and Paraformer-zh-streaming (220M) cover **zh/en only. No Korean** — [modelscope/FunASR model table](https://github.com/modelscope/FunASR)

**GLM-ASR-Nano-2512 (Zhipu / zai-org), December 2025**
- 1.5B params. The official "17 Supported Languages" chart lists Italian, English, Catalan, Ukrainian, Dutch, Spanish, German, Mandarin (FLEURS WER under 10%) and Japanese, French, Russian, Portuguese, Malay, Indonesian, Norwegian, Lithuanian, Slovenian (WER up to 20%). **Korean is not listed** — [zai-org/GLM-ASR README](https://github.com/zai-org/GLM-ASR); [languages.png](https://github.com/zai-org/GLM-ASR/blob/main/resources/languages.png)
- The HF card's language metadata is only `en`, `zh` — [HF zai-org/GLM-ASR-Nano-2512](https://huggingface.co/zai-org/GLM-ASR-Nano-2512)
- In Qwen's comparison, GLM-ASR-Nano scores much worse on multilingual sets (FLEURS 12-language average 16.08 vs Qwen3-ASR-1.7B 4.90) — [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)

**Dolphin (DataoceanAI + Tsinghua), paper March 2025**
- 40 Eastern languages plus 22 Chinese dialects, **including Korean (ko-KR)**. Trained on about 210k hours, of which **KsponSpeech is 969 h** (open source). Joint CTC-attention architecture (E-Branchformer encoder, Transformer decoder) — [DataoceanAI/Dolphin README](https://github.com/DataoceanAI/Dolphin); [languages.md](https://github.com/DataoceanAI/Dolphin/blob/main/languages.md); [arXiv 2503.20212, Table 2](https://arxiv.org/html/2503.20212)
- Released models: base (0.1B) and small (0.4B), plus CN-dialect variants (2026-05-09). **Medium (0.9B) and large (1.7B) are not public** — [Dolphin README](https://github.com/DataoceanAI/Dolphin)
- **Korean results, same tables (labelled "WER %"):**
  - FLEURS ko: Whisper base 10.3, small 5.3, medium 3.5, large-v1(?) 3.1, **large-v3 2.6**; Dolphin **base 4.8, small 3.3**, medium 2.7, large 2.5
  - CommonVoice17 ko: Whisper 24.4 / 14.3 / 10.2 / 8.9 / **large-v3 11.9**; Dolphin **base 12.1, small 8.0**, medium 7.1, large 6.5
  - Dataocean in-house ko: Whisper base 32.5, small 21.7, medium 21.1, **large-v3 14.1**; Dolphin 20.1 / **11.6** / 13.0 / 11.5

  Source: [arXiv 2503.20212, Tables 6–8](https://arxiv.org/html/2503.20212). Headers are as printed in the paper; the 5th Whisper column in Tables 7/8 is labelled "large-v1".

**FireRedASR / FireRedASR2 (Xiaohongshu FireRedTeam)**
- FireRedASR-AED-L (1.1B) and LLM-L (8.3B) were released 2025-01/02. FireRedASR2-AED and FireRedASR2-LLM were released 2026-02-12 and 2026-02-25, with a tech report on 2026-03-12. **ASR covers Chinese (Mandarin plus 20+ dialects), English and code-switching only. No Korean.** Only FireRedVAD and FireRedLID cover 100+ languages — [FireRedTeam/FireRedASR](https://github.com/FireRedTeam/FireRedASR); [FireRedTeam/FireRedASR2S](https://github.com/FireRedTeam/FireRedASR2S)

**Step-Audio 2 (StepFun)**
- Step-Audio-2-mini (about 8.3B, Apache-2.0, HF created 2025-08-28). Its multilingual ASR rows are FLEURS Arabic, CommonVoice yue and FLEURS Japanese only. **No Korean evaluation** — [stepfun-ai/Step-Audio2](https://github.com/stepfun-ai/Step-Audio2); [HF Step-Audio-2-mini](https://huggingface.co/stepfun-ai/Step-Audio-2-mini)

**Kimi-Audio (Moonshot)**
- Kimi-Audio-7B-Instruct (released 2025-04-25, about 9.8B in safetensors, card MIT). ASR is reported on LibriSpeech, FLEURS zh/en, AISHELL-1/2 and WenetSpeech. **No Korean** — [MoonshotAI/Kimi-Audio](https://github.com/MoonshotAI/Kimi-Audio); [HF card](https://huggingface.co/moonshotai/Kimi-Audio-7B-Instruct)

**MiDashengLM (Xiaomi)**
- 7B (Qwen2.5-Omni-7B Thinker decoder, August 2025; "1021" update October 2025) and 0.6B (Qwen3-0.6B decoder). It is trained on general audio captions rather than ASR transcripts, and the only ASR evaluation is LibriSpeech test-clean. **No Korean ASR evaluation** — [xiaomi-research/dasheng-lm](https://github.com/xiaomi-research/dasheng-lm)

**Seed-ASR (ByteDance), closed, July 2024 report**
- Seed-ASR (ML) covers English plus 7 other languages, including KO. On FLEURS KO it scores **3.25**, against Whisper Large-v2 14.3. The baseline figures are taken from the respective papers, and Seed-ASR used FLEURS references re-ITN'd by linguists, so this is **not a same-protocol comparison**. On in-house multilingual multi-domain KO: **Google USM 13.88, Whisper Large-v3 13.07, Seed-ASR (ML) 7.77** — [Seed-ASR, arXiv 2407.04675, Tables 11–12](https://arxiv.org/html/2407.04675)
- About 2B-param LUISE encoder plus an MoE LLM with "tens of billions" of params. Not open weights — [arXiv 2407.04675](https://arxiv.org/html/2407.04675)

**MOSS-Transcribe-Diarize 0.9B (OpenMOSS), released 2026-07-09**
- Claims transcription plus diarization across 50+ languages, with single-pass input up to 90 minutes. Won the 2nd MLC-SLM Challenge (INTERSPEECH 2026), whose 14 languages include Korean. Apache-2.0. The card shows no per-language Korean CER — [HF OpenMOSS-Team/MOSS-Transcribe-Diarize](https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize)

### Inferences
- Among open weights, Qwen3-ASR-1.7B is the clear first choice for Korean. Its official FLEURS-ko CER of 2.57 matches Whisper-large-v3's 2.6 in the Dolphin paper, but those two numbers come from different papers and normalizations. On CommonVoice-ko, Qwen3-ASR-1.7B scores 5.88, roughly level with Whisper-large-v3's 5.59 in the SenseVoice paper, again across papers. The cleanest same-protocol evidence is the third-party KsponSpeech run: Qwen3-ASR-1.7B at 9.99 against Whisper-large-**v2** at 13.17.
- For lecture speech, the FLEURS (read) and CommonVoice (read) results overstate accuracy. KsponSpeech (spontaneous) CERs of about 8.6–10 for base Qwen3-ASR-1.7B are the more realistic estimate. Korean fine-tuning brought KsponSpeech to about 5.9 in TeamUNIVA's protocol.
- For Korean, SenseVoice-Small and the public Dolphin base/small are both weaker than Whisper-large-v3 in their own papers' tables, except Dolphin-small on CV17. Their value is speed and CPU deployability, not accuracy.
- The Fun-ASR-MLT-Nano Korean claim is unbenchmarked. Treat it as unproven.

### Gaps
- No official KsponSpeech or Zeroth numbers exist for any of these models. Only Dolphin trained on KsponSpeech, and its paper does not report a KsponSpeech test score; it reports Dataocean, FLEURS and CV17.
- No per-language Whisper-large-v3 Korean baseline in the Qwen3-ASR paper. No Korean scores for Fun-ASR-MLT-Nano, Qwen3-Omni (per language), or MOSS-Transcribe-Diarize.
- The Dolphin tables say "WER" for Korean. Whether this is space-delimited WER or CER is not stated, and Whisper-large-v3 scoring 2.6 on FLEURS-ko suggests a CER-like metric. Unverified.
- The BuzzASR card claims to beat Qwen3-ASR but does not show Qwen3-ASR's numbers. The arXiv 2609.09554 paper was not checked.
- The Qwen3-ASR-Flash API language list was not confirmed from the full API reference. Korean support is implied by the paper's Flash-1208 Korean scores.

---

## Q2. Which provide word- or character-level timestamps suitable for click-to-play transcripts?

### Takeaway
For Korean, the best option is **Qwen3-ASR + Qwen3-ForcedAligner-0.6B**. It is a non-autoregressive aligner that returns word or character timestamps for 11 languages including Korean, with a published Korean accumulated-average-shift (AAS) of **37.2 ms**, or **42.2 ms on 300-second concatenations**. **Dolphin** (word timestamps since 2026-05-09) and **SenseVoiceSmall** (CTC token timestamps through FunASR) also work for Korean. Fun-ASR-MLT-Nano does **not** return timestamps. Fun-ASR-Nano, Paraformer and FireRedASR2 do, but they don't support Korean. MOSS-Transcribe-Diarize gives segment-level timestamps only.

### Cited Findings
- Qwen3-ForcedAligner-0.6B "supports timestamp prediction for arbitrary units within up to 5 minutes of speech in 11 languages" (zh, en, yue, fr, de, it, ja, **ko**, pt, ru, es). It is NAR and returns "word or character level timestamps" — [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)
- Forced-alignment AAS (ms, lower is better) for Korean: **37.2** (MFA-labelled raw) and **42.2** (MFA-labelled Concat-300s). The 10-language averages are 42.9 and 52.9, against WhisperX 133.2 / 2708.4 and NeMo Forced Aligner (NFA) 129.8 / 246.7. WhisperX and NFA have no Korean entry — [Qwen3-ASR README, Forced Alignment Benchmarks](https://github.com/QwenLM/Qwen3-ASR); [arXiv 2601.21337](https://arxiv.org/html/2601.21337)
- The ForcedAligner supports "offline batch inference in PyTorch only" (no vLLM) — [arXiv 2601.21337, Table 2](https://arxiv.org/html/2601.21337)
- Timestamps are enabled by passing `forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B"` to `Qwen3ASRModel`. "Streaming inference does not support batch inference or returning timestamps" — [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)
- Long-audio caveat: in qwen-asr 0.0.6, `transcribe()` splits audio into chunks of more than 180 s when timestamps are on (1200 s otherwise) and joins chunk texts with `""`, gluing Korean words together at chunk edges ("to thestore"). The issue was closed by its reporter without a merged fix — [Qwen3-ASR issue #217](https://github.com/QwenLM/Qwen3-ASR/issues/217)
- Third-party: a C++/ggml runtime (CrispASR) claims word-level timestamps through a GGUF build of the forced aligner — [HF discussion on Qwen3-ASR-0.6B](https://huggingface.co/Qwen/Qwen3-ASR-0.6B/discussions/12) (unverified)
- Qwen3-ASR-Flash-Filetrans API: word-level timestamps with `enable_words=true`, limited to a list that includes Korean. The page does not mention timestamps for `qwen3-asr-flash` — [Alibaba Model Studio doc](https://www.alibabacloud.com/help/en/model-studio/qwen-speech-recognition)
- SenseVoiceSmall: with `output_timestamp=True`, `timestamp` contains `[start_ms, end_ms]` pairs aligned one-to-one with `words`. Older versions returned `[token, start, end]` triples — [SenseVoice README](https://github.com/FunAudioLLM/SenseVoice)
- Fun-ASR-Nano-2512: native CTC character timestamps exist only on the ModelScope checkpoint. The HF checkpoint is the older text-only artifact, and timestamps are omitted there. **Fun-ASR-MLT-Nano: "Support returning timestamps" is unchecked** — [Fun-ASR README](https://github.com/FunAudioLLM/Fun-ASR); [HF MLT-Nano card](https://huggingface.co/FunAudioLLM/Fun-ASR-MLT-Nano-2512)
- Dolphin: "Support Word timestamps prediction for all Dolphin models" (2026-05-09), via `--word_timestamp true` — [Dolphin README](https://github.com/DataoceanAI/Dolphin)
- FireRedASR2-AED: `return_timestamp=True` gives per-token timestamps (zh/en only) — [FireRedASR2S README](https://github.com/FireRedTeam/FireRedASR2S)
- Paraformer-zh: "ASR + timestamps", zh/en — [FunASR model table](https://github.com/modelscope/FunASR)
- MOSS-Transcribe-Diarize: outputs segments with `start`, `end` and `speaker`, plus SRT/ASS export. That is segment-level, not word-level — [HF MOSS-Transcribe-Diarize](https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize)
- GLM-ASR-Nano, Step-Audio 2, Kimi-Audio, MiDashengLM and Qwen-Omni document no timestamp output — [GLM-ASR](https://github.com/zai-org/GLM-ASR); [Step-Audio2](https://github.com/stepfun-ai/Step-Audio2); [Kimi-Audio](https://github.com/MoonshotAI/Kimi-Audio); [dasheng-lm](https://github.com/xiaomi-research/dasheng-lm)

### Inferences
- For a Korean click-to-play transcript, Qwen3-ASR-1.7B followed by Qwen3-ForcedAligner in ≤5-minute windows is the only option with a published Korean alignment-accuracy figure. Expect to handle chunk boundaries and the issue #217 spacing bug yourself, for example by using VAD-based segmentation and joining Korean chunks with a space.
- The ForcedAligner can also align text from *any* ASR, such as a Whisper or Korean fine-tuned output, so it can be used on its own as a Korean aligner.
- SenseVoice and Dolphin timestamps come from CTC alignment. Their Korean word-boundary quality is unpublished.

### Gaps
- No Korean timestamp-accuracy numbers for SenseVoice, Dolphin or the Alibaba Filetrans API.
- It is unclear whether Qwen3-ForcedAligner aligns Korean at eojeol (space-delimited word) or syllable level by default. The README says "arbitrary units", so this needs testing.

---

## Q3. Which support true streaming or chunked low-latency decoding?

### Takeaway
**Qwen3-ASR** is designed for unified streaming and offline use (dynamic 1–8 s attention window, evaluated with 2-second chunks). But the official `qwen-asr` streaming path **re-feeds all accumulated audio** on each step, which a GitHub issue calls pseudo-streaming. vLLM now has a separate `Qwen3ASRRealtimeGeneration` `/v1/realtime` endpoint. **Fun-ASR-Nano** has a vLLM streaming SDK with 720 ms chunks, but not for Korean. MLT-Nano is tagged "streaming", with streaming for "some languages", which is unverified for Korean. **SenseVoice-Small** is offline NAR and very fast; streaming exists only as a community pseudo-streaming fork. **Dolphin** streaming models exist only for Chinese dialects. Paraformer-streaming is zh/en only.

### Cited Findings
- Qwen3-ASR: "Benefiting from the dynamic attention-window mechanism, the Qwen3-ASR family supports streaming inference naturally." Evaluation used a "2-second chunk size, a 5-token fallback, and keeping the last four chunks unfixed" — [arXiv 2601.21337 §4.5](https://arxiv.org/html/2601.21337)
- Offline vs streaming cost: Qwen3-ASR-1.7B average WER over LibriSpeech, FLEURS-en and FLEURS-zh goes from 2.69 offline to 3.33 streaming; the 0.6B goes from 3.48 to 4.40. **No Korean streaming numbers** — [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)
- Efficiency (vLLM 0.14.0, about 2 min audio): Qwen3-ASR-0.6B average TTFT is **92 ms** at concurrency 1 (p95 105 ms) and 820 ms at concurrency 32. Throughput reaches up to 2000x real time at concurrency 128 — [arXiv 2601.21337, Table 2](https://arxiv.org/html/2601.21337)
- "Streaming inference is only available with the vLLM backend … does not support batch inference or returning timestamps" — [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)
- Issue #148 ("Serious Issues with Real-Time Streaming"): the official implementation concatenates `audio_accum` and re-feeds all audio from session start on every chunk, so latency grows over long sessions ("essentially pseudo-streaming"). Other users confirmed degradation over time — [Qwen3-ASR issue #148](https://github.com/QwenLM/Qwen3-ASR/issues/148)
- An open PR adds an "experimental Transformers incremental streaming backend" — [Qwen3-ASR PR #223](https://github.com/QwenLM/Qwen3-ASR/pull/223)
- vLLM's Realtime Transcription table (`/v1/realtime` WebSocket) lists `Qwen3ASRRealtimeGeneration` (example `Qwen/Qwen3-ASR-0.6B`). It needs `--hf-overrides '{"architectures":["Qwen3ASRRealtimeGeneration"]}'` — [vLLM supported_models.md](https://github.com/vllm-project/vllm/blob/main/docs/models/supported_models.md)
- Issue #140: the streaming hotword feature on Qwen3-ASR-0.6B causes repetitive output of the hotword list — [Qwen3-ASR issue #140](https://github.com/QwenLM/Qwen3-ASR/issues/140)
- Fun-ASR-Nano: `FunASRNanoStreamingVLLM.from_pretrained(..., chunk_ms=720)` streaming SDK, plus a realtime WebSocket server (`serve_realtime_ws.py`) — [Fun-ASR README](https://github.com/FunAudioLLM/Fun-ASR)
- The Fun-ASR tech report builds streaming-style training data to reduce train/inference mismatch, and the multilingual Fun-ASR-ML "also support[s] streaming speech recognition for some languages" — [arXiv 2509.12508 §5.1, §5.3](https://arxiv.org/html/2509.12508). The MLT-Nano card carries the tag `streaming` — [HF MLT-Nano](https://huggingface.co/FunAudioLLM/Fun-ASR-MLT-Nano-2512)
- SenseVoiceSmall: NAR, 70 ms for 10 s of audio. The community `streaming-sensevoice` uses truncated attention for pseudo-streaming, "sacrificing some accuracy" — [SenseVoice README](https://github.com/FunAudioLLM/SenseVoice); [arXiv 2407.04051](https://arxiv.org/html/2407.04051)
- Paraformer-zh-streaming: chunked live transcription, zh/en only — [FunASR README](https://github.com/modelscope/FunASR)
- Dolphin: streaming variants (`base.cn.streaming`, `small.cn.streaming`) are CN-dialect models only — [Dolphin README](https://github.com/DataoceanAI/Dolphin)
- FireRedASR2: streaming is offered for VAD only. FireRedASR-AED and FireRedASR2-AED inputs over 60 s "may cause hallucination", and over 200 s they trigger positional-encoding errors — [FireRedASR2S README](https://github.com/FireRedTeam/FireRedASR2S); [FireRedASR README](https://github.com/FireRedTeam/FireRedASR)
- Alibaba API: `qwen3-asr-flash` supports streaming output. A separate `qwen3-asr-flash-realtime` WebSocket model exists — [Alibaba Model Studio doc](https://www.alibabacloud.com/help/en/model-studio/qwen-speech-recognition); [qwen3-asr-flash-realtime doc](https://www.alibabacloud.com/help/en/model-studio/qwen3-asr-flash-realtime)
- For contrast (not an Asian-lab model): a Korean-only icefall Zipformer gets 7.53% KsponSpeech CER with sherpa-onnx int8 at 1.28 s latency and RTF 0.049 on one CPU thread — [kangkyu/icefall-asr-ko-streaming-zipformer-174m](https://huggingface.co/kangkyu/icefall-asr-ko-streaming-zipformer-174m)

### Inferences
- Recorded lectures don't need true streaming. Offline Qwen3-ASR with VAD chunking is the better fit. For live captions, use vLLM's `/v1/realtime` Qwen3-ASR path or the `qwen-asr` streaming demo, and test long-session latency (issue #148).
- No Asian-lab open model has a published Korean streaming accuracy figure.

### Gaps
- No Korean streaming WER/CER for Qwen3-ASR or Fun-ASR-MLT-Nano. Which languages MLT-Nano streams is not documented.
- No end-to-end streaming latency figure (as opposed to TTFT) for Qwen3-ASR's 2 s chunk mode.

---

## Q4. Which have documented fine-tuning/LoRA paths, and what are the license terms?

### Takeaway
Most of these models are **Apache-2.0**: Qwen3-ASR (all three), Fun-ASR-Nano and MLT-Nano, Dolphin, FireRedASR/2, Step-Audio-2-mini, MiDashengLM and MOSS-Transcribe-Diarize. GLM-ASR-Nano weights are **MIT**, as is Kimi-Audio. **SenseVoiceSmall uses the custom FunASR Model License v1.1**; maintainers have clarified it permits commercial use but requires attribution. Fine-tuning recipes are documented for Qwen3-ASR (full SFT script, no LoRA in the official script), SenseVoice, Fun-ASR-Nano (module freeze flags), Kimi-Audio and MiDashengLM. FireRedASR2's fine-tuning code was "coming soon" as of February 2026. vLLM supports LoRA adapters at *serving* time for Qwen3-ASR and GLM-ASR.

### Cited Findings
- Qwen3-ASR 0.6B/1.7B and ForcedAligner: repository license **Apache-2.0** (repo created 2026-01-28). The HF card for the 1.7B also says apache-2.0 — [GitHub API QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR); [HF Qwen3-ASR-1.7B](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)
- Qwen3-ASR fine-tuning: the official `finetuning/qwen3_asr_sft.py` takes JSONL `{"audio": ..., "text": "language Korean<asr_text>..."}` (or `language None`). Example settings: batch 32, grad_acc 4, lr 2e-5, 1 epoch, single GPU or torchrun multi-GPU, FlashAttention 2 recommended. **The script contains no LoRA/PEFT code**, so this is full-parameter SFT — [Qwen3-ASR finetuning README](https://github.com/QwenLM/Qwen3-ASR/tree/main/finetuning) (checked by grepping `qwen3_asr_sft.py` for lora/peft/freeze; no hits)
- A community Korean full fine-tune exists, Apache-2.0: TeamUNIVA `qwen3_asr_1.7b_ko` (KsponSpeech CER from 8.65 to 5.94 in their protocol) — [HF TeamUNIVA](https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko)
- vLLM's Transcription table marks LoRA ✅ for `Qwen3ASRForConditionalGeneration` and `GlmAsrForConditionalGeneration`, and blank for FunASR and FireRedASR2 — [vLLM supported_models.md](https://github.com/vllm-project/vllm/blob/main/docs/models/supported_models.md)
- SenseVoice: `finetune.sh` via FunASR `train_ds.py`, with JSONL including `text_language` (`<|ko|>` supported). The code is **MIT**. The weights fall under the **FunASR Model Open Source License Agreement v1.1**. Maintainer clarification: "Commercial use of the official SenseVoiceSmall weights is permitted when the model license is followed", fine-tuned derivatives may remain private, and the Section 2.2 attribution and model-name requirements still apply — [SenseVoice README](https://github.com/FunAudioLLM/SenseVoice); [FunASR MODEL_LICENSE](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE)
- Fun-ASR-Nano and MLT-Nano: the model cards say **Apache-2.0**, as does the code. Fine-tuning per `docs/finetune.md`: toggle `audio_encoder_conf.freeze`, `audio_adaptor_conf.freeze` and `llm_conf.freeze`. "By default, only the LLM is fine-tuned", and "for training data less than 5000 hours, it is recommended to fine-tune the audio_encoder and audio_adaptor" — [Fun-ASR README](https://github.com/FunAudioLLM/Fun-ASR); [Fun-ASR finetune.md](https://github.com/FunAudioLLM/Fun-ASR/blob/main/docs/finetune.md)
- In Fun-ASR's own training, stage 3 updates the LLM with LoRA and stage 4 does full fine-tuning of the encoder and adaptor plus LoRA on the LLM — [arXiv 2509.12508 §4](https://arxiv.org/html/2509.12508)
- GLM-ASR-Nano-2512: HF card `license: mit`, GitHub code Apache-2.0. **No fine-tuning recipe** is documented in the README — [HF card](https://huggingface.co/zai-org/GLM-ASR-Nano-2512); [GitHub](https://github.com/zai-org/GLM-ASR)
- Dolphin: "code and model weights are released under the Apache 2.0 License". The README documents no fine-tuning recipe (it builds on ESPnet/WeNet) — [Dolphin README](https://github.com/DataoceanAI/Dolphin)
- FireRedASR / FireRedASR2S: Apache-2.0. As of 2026-02-12, "Technical report and finetuning code coming soon". The report was published 2026-03-12, and the fine-tuning code status was not verified — [FireRedASR2S README](https://github.com/FireRedTeam/FireRedASR2S)
- Step-Audio-2-mini, mini-Base and mini-Think: Apache-2.0 — [Step-Audio2 README](https://github.com/stepfun-ai/Step-Audio2)
- Kimi-Audio: weights card MIT. Code derived from Qwen2.5 is Apache-2.0, the rest MIT. A fine-tuning example was released 2025-05-29 — [Kimi-Audio README](https://github.com/MoonshotAI/Kimi-Audio); [HF card](https://huggingface.co/moonshotai/Kimi-Audio-7B-Instruct)
- MiDashengLM: Apache-2.0 "for both research and commercial use". The `mdl-toolkit` fine-tuning toolkit was released 2025-09-24 — [dasheng-lm README](https://github.com/xiaomi-research/dasheng-lm)
- Qwen2-Audio-7B-Instruct: Apache-2.0. Qwen3-Omni: card `license: other` / `license_name: apache-2.0` — [HF Qwen2-Audio](https://huggingface.co/Qwen/Qwen2-Audio-7B-Instruct); [HF Qwen3-Omni](https://huggingface.co/Qwen/Qwen3-Omni-30B-A3B-Instruct)
- MOSS-Transcribe-Diarize 0.9B: Apache-2.0 — [HF card](https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize)
- Seed-ASR: no weights; commercial Doubao/Volcengine API only — [arXiv 2407.04675](https://arxiv.org/html/2407.04675)

### Inferences
- For a commercial Korean product, Qwen3-ASR (Apache-2.0) with its official SFT script is the lowest-friction fine-tuning path, and the TeamUNIVA results show Korean SFT gains of about 2–3 points of CER on spontaneous speech. LoRA would need a custom PEFT wrapper; vLLM can then serve the adapters.
- Using SenseVoiceSmall commercially requires attribution under the custom license; review Section 2.2.

### Gaps
- No official LoRA recipe for Qwen3-ASR. Not verified whether community PEFT recipes exist.
- Paraformer weight license not checked directly; it is assumed to be the FunASR MODEL_LICENSE.
- Status of FireRedASR2 fine-tuning code after March 2026 is unknown (and moot for Korean).

---

## Q5. Which can be served without CUDA (vLLM ROCm, llama.cpp/GGUF, ONNX Runtime, CPU)?

### Takeaway
**Qwen3-ASR now has upstream llama.cpp support** (`ggml-org/Qwen3-ASR-0.6B-GGUF` / `-1.7B-GGUF` via mtmd) and runs on CPU through Transformers. But the bundled Transformers backend has a **known bug on CPU/SDPA**: the encoder's windowed attention is not applied, so clips over 8 s are encoded with full attention, unlike training. **SenseVoiceSmall is the most portable Korean-capable model**, with official ONNX, libtorch, sherpa-onnx (Korean included) and llama.cpp/GGUF builds plus a CPU Docker image. **Dolphin-base runs in sherpa-onnx.** Fun-ASR-Nano has official GGUF, but no Korean. vLLM lists Qwen3-ASR, GLM-ASR, Fun-ASR-Nano, FireRedASR2, Kimi-Audio, MiDashengLM and Qwen-Omni; **ROCm compatibility for these audio models is not documented in the sources checked.**

### Cited Findings
- Upstream llama.cpp audio-model list includes `# Qwen3-ASR` → `ggml-org/Qwen3-ASR-0.6B-GGUF`, `ggml-org/Qwen3-ASR-1.7B-GGUF`, alongside Qwen2-Audio, Qwen2.5-Omni, Qwen3-Omni, Voxtral and Ultravox — [llama.cpp docs/multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- Community Qwen3-ASR GGUF builds: Unsloth `Qwen3-ASR-1.7B-GGUF`; CrispASR C++ runtime (claims 10.5 s to process 11 s of audio on a 4-core Xeon, plus aligner GGUF); SpacemiT ONNX encoder plus GGUF decoder for RISC-V boards — [Unsloth GGUF](https://huggingface.co/unslothai/Qwen3-ASR-1.7B-GGUF); [CrispASR discussion](https://huggingface.co/Qwen/Qwen3-ASR-0.6B/discussions/12); [SpacemiT/Qwen3-ASR-0.6B](https://huggingface.co/SpacemiT/Qwen3-ASR-0.6B) (third-party, unverified)
- Qwen3-ASR Transformers-backend bug: `_prepare_attention_mask` is never called unless FA2 is used, so with `sdpa` ("the default on CPU and on GPU when FA2 is not installed") any input longer than 8 s is encoded with full attention. A commenter on a production deployment reported "a much more severe symptom" on ~180 s chunks. A fix PR (#103) has been open since February 2026 — [Qwen3-ASR issue #213](https://github.com/QwenLM/Qwen3-ASR/issues/213); [PR #103](https://github.com/QwenLM/Qwen3-ASR/pull/103)
- A native Transformers integration (`Qwen/Qwen3-ASR-1.7B-hf`, `-0.6B-hf`, `Qwen3-ForcedAligner-0.6B-hf`, with `torch.compile`) was added 2026-06-26. It is a separate code path from the `qwen-asr` package — [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR). Whether it has the #213 bug was not verified.
- The official Qwen3-ASR Docker image requires the NVIDIA Container Toolkit. vLLM serving is via `vllm serve Qwen/Qwen3-ASR-1.7B` or `qwen-asr-serve` — [Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR)
- vLLM Transcription architectures include `Qwen3ASRForConditionalGeneration`, `GlmAsrForConditionalGeneration`, `FunASRForConditionalGeneration` (Fun-ASR-Nano-2512-vllm), `FireRedASR2ForConditionalGeneration`, `MossTranscribeDiarizeForConditionalGeneration` and `Qwen3OmniMoeThinkerForConditionalGeneration`. Audio LMs include `KimiAudioForConditionalGeneration`, `MiDashengLMModel` and `Qwen2AudioForConditionalGeneration` — [vLLM supported_models.md](https://github.com/vllm-project/vllm/blob/main/docs/models/supported_models.md)
- Issue title "不再适配 vllm 0.16.0+" ("no longer compatible with vLLM 0.16.0+", closed) suggests the `qwen-asr` package pins vLLM versions — [Qwen3-ASR issue #119](https://github.com/QwenLM/Qwen3-ASR/issues/119) (only the title was read)
- SenseVoiceSmall: ONNX export (`funasr-onnx`), libtorch export, and "Run on CPU / edge — llama.cpp / GGUF (no GPU, no Python)" with an official `SenseVoiceSmall-GGUF` and built-in FSMN-VAD. Docker image with `SENSEVOICE_DEVICE=cpu`. sherpa-onnx supports 10 programming languages and iOS, Android and Raspberry Pi — [SenseVoice README](https://github.com/FunAudioLLM/SenseVoice)
- sherpa-onnx ships `sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17` (Korean) and a "VAD + speech recognition (multilingual)" demo with Dolphin-base — [k2-fsa/sherpa-onnx README](https://github.com/k2-fsa/sherpa-onnx)
- Fun-ASR-Nano: official llama.cpp/GGUF runtime (`llama-funasr-cli`, encoder f16 plus Qwen3-0.6B q8_0) and a Transformers 5.17 CPU quickstart. Both apply to the zh/en/ja checkpoint — [Fun-ASR README](https://github.com/FunAudioLLM/Fun-ASR); [FunASR README](https://github.com/modelscope/FunASR)
- GLM-ASR-Nano: Transformers (`device = "cuda" if available else "cpu"`), SGLang (dev image) and vLLM — [GLM-ASR README](https://github.com/zai-org/GLM-ASR)
- MiDashengLM-0.6B: GGUF (3–16 bit) for CPU via llama.cpp and in-browser WASM. The README lists this news item as "2025-04-21", but it appears above a 2025-10-21 entry, so the date may be a typo for 2026 (unverified) — [dasheng-lm README](https://github.com/xiaomi-research/dasheng-lm)
- Dolphin: `pip install dataoceanai-dolphin`, `load_model(..., device="cuda")` in the examples. It is PyTorch, so CPU is presumably possible, but the README does not document it — [Dolphin README](https://github.com/DataoceanAI/Dolphin)

### Inferences
- For a no-CUDA Korean deployment, there are two realistic paths: (a) Qwen3-ASR GGUF through upstream llama.cpp (Vulkan, Metal or CPU backends; Korean accuracy after quantization is unmeasured); (b) Qwen3-ASR through Transformers on CPU or ROCm PyTorch, either with PR #103 applied or using the native `-hf` integration. SenseVoiceSmall (ONNX/sherpa-onnx) is the fast, proven CPU fallback, at lower Korean accuracy (CV-ko CER 8.28 vs Whisper-v3 5.59).
- The ForcedAligner is PyTorch-only officially, so a non-CUDA timestamp pipeline means running it in PyTorch on CPU or ROCm, or using the unverified CrispASR aligner GGUF.

### Gaps
- No primary source confirms vLLM on ROCm for Qwen3-ASR or other audio models. vLLM supports ROCm as a platform, but per-model audio support on ROCm was not checked.
- No Korean accuracy measurements for quantized GGUF builds of Qwen3-ASR.
- Not verified whether Fun-ASR-MLT-Nano (the Korean-capable checkpoint) has a GGUF or ONNX build. The documented GGUF is the base Nano.

---

### Cross-cutting: hallucination behavior (supporting notes, cited)
- Qwen3-ASR-1.7B under vLLM 0.17.1: "about 1 in 10 files" spiral into token repetition, for example "I think." repeated about 2,000 times (Chinese audio). Closed as inactive with no fix — [Qwen3-ASR issue #129](https://github.com/QwenLM/Qwen3-ASR/issues/129)
- The Qwen3-ASR encoder full-attention bug on SDPA (#213) is reported to cause severe degradation on long chunks — [issue #213](https://github.com/QwenLM/Qwen3-ASR/issues/213)
- A secondary blog claims Qwen3-ASR has essentially no silence-hallucination problem — [yage.ai](https://yage.ai/share/whisper-repetition-hallucination-en-20260526.html) (not a primary source; unverified)
- Fun-ASR explicitly targets hallucination. It inserts zero-padded pure-noise segments in augmentation, applies an RL reward penalty proportional to the length of the hallucinated span, and includes hallucination-prone samples in training — [arXiv 2509.12508 §4, §5.6](https://arxiv.org/html/2509.12508)
- FireRedASR-AED and FireRedASR2-AED: input over 60 s "may cause hallucination issues" — [FireRedASR README](https://github.com/FireRedTeam/FireRedASR); [FireRedASR2S README](https://github.com/FireRedTeam/FireRedASR2S)
- No Korean-specific hallucination evaluation was found for any model. CTC/NAR models (SenseVoice, Paraformer, Dolphin's CTC branch) are structurally less prone to runaway repetition than autoregressive LLM decoders. That last point is an inference, not a published result.
