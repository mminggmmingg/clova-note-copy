# Open-weight ASR models from US/European labs for Korean lecture transcription (state as of 2026-11-01)

Scope: Microsoft (VibeVoice-ASR family, Phi-4-multimodal), NVIDIA (Canary, Parakeet, the new Nemotron 3.5 speech models), Meta (Omnilingual ASR, SeamlessM4T v2), Moonshine AI (formerly Useful Sensors), Kyutai, IBM Granite Speech, Mistral Voxtral, and Google Gemma 3n / Gemma 4 audio. Whisper large-v3 is used as the baseline. Unless a line says otherwise, every number comes from the vendor's own model card or technical report and was not independently reproduced. Metric warning: Korean is reported as CER by some vendors (NVIDIA, Moonshine, VibeVoice-Streaming) and as WER by others (Mistral, VibeVoice-ASR offline). Korean WER is usually several times higher than CER on the same output, so the two cannot be compared directly.

## Which of these models actually support Korean? (official language lists)

### Takeaway
Seven open-weight families from US/European labs officially support Korean ASR as of Nov 2026:
- NVIDIA's new **Nemotron 3.5 Transcribe 30B-A4B** (Oct 2026) and **Nemotron 3.5 ASR Streaming 0.6B** (mid-2026)
- **Microsoft VibeVoice-ASR** (7B offline, 7B/1.5B streaming, BitNet CPU)
- **Mistral Voxtral Realtime 4B** (Feb 2026)
- **Meta Omnilingual ASR** (kor_Hang) and **SeamlessM4T v2**
- **Moonshine tiny-ko/base-ko** (non-streaming only, under a restrictive license)

The older NVIDIA Canary/Parakeet models, Canary-Qwen, Kyutai STT, IBM Granite Speech, Voxtral Mini/Small 2507 and Phi-4-multimodal **do not** support Korean ASR. Gemma 3n/Gemma 4 audio is "multilingual" but publishes no language list that names Korean.

### Cited Findings

**Microsoft VibeVoice-ASR family (supports Korean)**

*VibeVoice-ASR (offline)*
- Open-sourced 2026-01-21. Transformers integration followed on 2026-03-06, Azure AI Foundry Labs on 2026-03-12. [GitHub microsoft/VibeVoice](https://github.com/microsoft/VibeVoice)
- MIT license. The HF page reports 9B parameters (BF16 safetensors), while the GitHub repo and secondary sources call it "7B". This is a size discrepancy. [HF microsoft/VibeVoice-ASR](https://huggingface.co/microsoft/VibeVoice-ASR); [GitHub](https://github.com/microsoft/VibeVoice)
- Claims "over 50 languages" (HF tag: "51 languages"). The HF card has no text language list (only a chart image), so Korean is **not named in the card text**. [HF](https://huggingface.co/microsoft/VibeVoice-ASR)
- The technical report does evaluate Korean, in its MLC-Challenge Korean row (see the scores section). It says SFT "predominantly focused on English, Chinese, and code-switching data." [arXiv 2601.18184](https://arxiv.org/html/2601.18184)
- Architecture: VibeVoice acoustic and semantic tokenizers (about 7.5 tokens/s) feeding a decoder-only LLM backbone ("e.g., Qwen 2.5"). Curriculum training grew the context from 8,192 to 65,536 tokens. [arXiv 2601.18184](https://arxiv.org/html/2601.18184)

*VibeVoice-ASR-Streaming-7B*
- Released 2026-09-03; HF repo created 2026-09-02; report arXiv 2609.02812, Sep 2. [GitHub](https://github.com/microsoft/VibeVoice); [HF](https://huggingface.co/microsoft/VibeVoice-ASR-Streaming-7B)
- MIT license. The HF page lists 9B params even though the name says 7B. [HF](https://huggingface.co/microsoft/VibeVoice-ASR-Streaming-7B)
- Official 10-language list: Chinese, English, French, German, Italian, Japanese, **Korean**, Portuguese, Russian, Spanish. [HF](https://huggingface.co/microsoft/VibeVoice-ASR-Streaming-7B)
- The report says both 1.5B and 7B streaming weights were released. [arXiv 2609.02812](https://arxiv.org/html/2609.02812)

*VibeVoice-ASR-BitNet (CPU engine)*
- Released 2026-07-23; report arXiv 2607.21075. MIT license. [GitHub](https://github.com/microsoft/VibeVoice); [HF](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet)
- The card lists "English, Chinese, French, Italian, **Korean**, Portuguese, Vietnamese, and more" (tag: "7 languages"). [HF](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet)
- Secondary sources say it swaps the 7B LLM for a Qwen2.5-1.5B decoder. Unverified from a primary source. [interfaze.ai summary](https://interfaze.ai/models/microsoftvibevoice-asr-bitnet.md)

**Microsoft Phi-4-multimodal-instruct (no Korean audio)**
- Released Feb 2025. 5.6B params, MIT license. [HF](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)
- Audio languages: English, Chinese, German, French, Italian, Japanese, Spanish, Portuguese. **Korean is a text language only.** [HF](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)
- The card's Appendix B says the model "is originally not designed for Korean speech-to-text task." The original model scores **99.16% CER on Zeroth-test**. [HF](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)

**NVIDIA Nemotron 3.5 Transcribe 30B-A4B (supports Korean; new, Oct 2026)**
- Released 2026-10-28 on HF, GitHub (NeMo Speech), NGC and build.nvidia.com. The HF repo was created 2026-10-07. [HF card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B); [HF API listing](https://huggingface.co/api/models?author=nvidia&pipeline_tag=automatic-speech-recognition&sort=createdAt&direction=-1&limit=60)
- About 34B total / about 4.3B active parameters. The backbone is a Mamba-2/Transformer hybrid MoE with a "Parallel Expert Encoder". Ships in BF16, FP8 and NVFP4. [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)
- License: OpenMDW-1.1, "ready for commercial or non-commercial use". [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)
- 40 languages, 1-hour audio, 64k context. **Korean is listed as supported**: ASR in the "Leading quality" tier, translation to/from English, multispeaker ASR, and code-switching. [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)
- Limitation: "Audio understanding, reasoning, and spoken instruction following were evaluated only in English." [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)

**NVIDIA Nemotron 3.5 ASR Streaming 0.6B (supports Korean)**
- The card says released 06/04/2026; the HF repo was created 2026-05-15. [HF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)
- FastConformer cache-aware RNNT with language-ID prompt conditioning. 0.6B params, OpenMDW-1.1, commercial use allowed. [HF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)
- 40 language-locales in three tiers. **ko-KR is in the "Transcription-ready" tier** (19 locales). The "Adaptation-ready" locales need fine-tuning first. [HF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)

**NVIDIA Canary and Parakeet (no Korean)**
- Canary-1B-v2: released 2025-08-14. 978M params, CC-BY-4.0. [HF](https://huggingface.co/nvidia/canary-1b-v2)
  - 25 languages: Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish, French, German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish, Portuguese, Romanian, Slovak, Slovenian, Spanish, Swedish, Russian, Ukrainian. **No Korean.**
- Canary-1B and Canary-1B-flash support only 4 languages, per the v2 card. [HF canary-1b-v2](https://huggingface.co/nvidia/canary-1b-v2) (Which 4: en/de/es/fr, from memory and not re-fetched.)
- Parakeet-TDT-0.6B-v3: released 2025-08-14. 600M params, CC-BY-4.0. Same 25 European languages, **no Korean**. [HF](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- Canary-Qwen-2.5B: released 2025-07-17. CC-BY-4.0. "English data only". [HF](https://huggingface.co/nvidia/canary-qwen-2.5b)
- nemotron-labs-unified-asr-0.6b: the card says 10/27/26. OpenMDW-1.1. Same 25 European languages, "Korean is not supported". [HF](https://huggingface.co/nvidia/nemotron-labs-unified-asr-0.6b)
- Other 2025–2026 NVIDIA ASR releases are English or single-language: nemotron-speech-streaming-en-0.6b (2025-12-17), parakeet-unified-en-0.6b (2026-04-07), parakeet-ctc-0.6b-Vietnamese (2026-01-15). No Korean Parakeet exists. [HF API listing](https://huggingface.co/api/models?author=nvidia&pipeline_tag=automatic-speech-recognition&sort=createdAt&direction=-1&limit=60)

**Meta Omnilingual ASR (Korean included)**
- Paper arXiv 2511.09690 (Nov 2025). v2 CTC/LLM checkpoints plus "LLM Unlimited" v2 variants followed in a December 2025 update. Code and models are Apache 2.0; the dataset is CC-BY-4.0. [GitHub](https://github.com/facebookresearch/omnilingual-asr)
- Sizes: CTC and LLM-ASR at 300M/1B/3B/7B, plus a 7B zero-shot model (about 7.8B). [GitHub](https://github.com/facebookresearch/omnilingual-asr)
- "1600+" languages. **`kor_Hang` is present in the official lang_ids list.** [lang_ids.py](https://raw.githubusercontent.com/facebookresearch/omnilingual-asr/main/src/omnilingual_asr/models/wav2vec2_llama/lang_ids.py)
- The paper lists Zeroth Korean among its training sources. [arXiv 2511.09690](https://arxiv.org/html/2511.09690)

**Meta SeamlessM4T v2 large (Korean included)**
- 2.3B params, **CC-BY-NC-4.0 (non-commercial)**. Paper Dec 2023. [HF](https://huggingface.co/facebook/seamless-m4t-v2-large)
- 101 speech-input languages. `kor` is marked "Sp, Tx" as a source, so it accepts Korean speech. [HF](https://huggingface.co/facebook/seamless-m4t-v2-large)

**Moonshine (Korean included, non-streaming only)**
- moonshine-tiny-ko: 27M params, released Sep 2025 (repo 2025-09-01). [HF](https://huggingface.co/UsefulSensors/moonshine-tiny-ko); [HF API](https://huggingface.co/api/models?author=moonshine-ai&limit=100)
- moonshine-base-ko: repo created 2025-09-25. [HF API](https://huggingface.co/api/models?author=moonshine-ai&limit=100)
- Paper: "Flavors of Moonshine", arXiv 2509.02523. [arXiv](https://arxiv.org/html/2509.02523)
- **No Korean streaming Moonshine model exists.** The streaming line is English (Jan 2026) plus ja/de/es/vi/ar/zh/tl (2026-08-24). [HF API](https://huggingface.co/api/models?author=moonshine-ai&limit=100)

**Kyutai STT (no Korean)**
- stt-1b-en_fr supports English and French. stt-2.6b-en is English only. CC-BY 4.0. Repos created June 2025. [HF](https://huggingface.co/kyutai/stt-1b-en_fr); [HF API ko listing](https://huggingface.co/api/models?language=ko&pipeline_tag=automatic-speech-recognition&sort=likes&direction=-1&limit=80)

**IBM Granite Speech (no Korean)**
- granite-4.0-1b-speech: released 2026-03-06. granite-speech-4.1-2b: released 2026-04-29. Both Apache 2.0.
- ASR in English, French, German, Spanish, Portuguese and Japanese only. **No Korean.** [HF 4.0-1b](https://huggingface.co/ibm-granite/granite-4.0-1b-speech); [HF 4.1-2b](https://huggingface.co/ibm-granite/granite-speech-4.1-2b)

**Mistral Voxtral (Korean only in Realtime)**
- Voxtral Mini 3B 2507 (Jul 2025, Apache 2.0) transcribes 8 languages: English, Spanish, French, Portuguese, Hindi, German, Dutch, Italian. **No Korean.** The Small 24B 2507 language list was not re-fetched. [HF Voxtral-Mini-3B-2507](https://huggingface.co/mistralai/Voxtral-Mini-3B-2507)
- Voxtral Realtime (Voxtral-Mini-4B-Realtime-2602): open weights, Apache 2.0, announced 2026-02-04. About 4B params (≈3.4B LM + ≈970M encoder). [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602); [Mistral blog](https://mistral.ai/news/voxtral-transcribe-2)
  - 13 languages: English, Chinese, Hindi, Spanish, Arabic, French, Portuguese, Russian, German, Japanese, **Korean**, Italian, Dutch.
- Voxtral Mini Transcribe V2, the batch model, is **API-only** ($0.003/min). [Mistral blog](https://mistral.ai/news/voxtral-transcribe-2)

**Google Gemma (Korean not named)**
- Gemma 4 E2B/E4B/12B-Unified are "trained for multilingual speech recognition", but **no ASR language list is published**. Korean appears only as a translation target in an AST prompt example. [Google AI Gemma audio docs](https://ai.google.dev/gemma/docs/capabilities/audio)
- The Gemma 4 E4B card says "35+ languages out of the box, pretrained on 140+", without an audio-specific list. [HF gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it)
- The Gemma 3n card says "over 140 spoken languages" with no Korean-specific ASR claim. [HF gemma-3n-E4B-it](https://huggingface.co/google/gemma-3n-E4B-it)

**Hugging Face language tags**
- HF's `language=ko` ASR filter also returned models that are not Korean-capable, such as parakeet-tdt-0.6b-v2 and canary-1b. Trust the official language list on each card, not the HF tags. [HF API ko listing](https://huggingface.co/api/models?language=ko&pipeline_tag=automatic-speech-recognition&sort=likes&direction=-1&limit=80)

### Inferences
- For Korean, the realistic US/European open-weight shortlist in Nov 2026 is:
  - Nemotron 3.5 Transcribe (offline, best published Korean number)
  - Nemotron 3.5 ASR Streaming 0.6B (live captions)
  - VibeVoice-ASR / -Streaming (long-form plus speakers)
  - Voxtral Realtime (live)
  - Omnilingual ASR (broad, but no Korean number published)
- SeamlessM4T v2 (non-commercial) and Moonshine Korean (restricted license, tiny/base only) are secondary options.
- Phi-4-multimodal can be made Korean-capable only by fine-tuning (see the fine-tuning section).
- The "Western models are English/European-only" generalization was true for 2024–2025 NVIDIA, Kyutai, IBM and Mistral releases. It is no longer true for NVIDIA's and Mistral's 2026 releases.

### Gaps
- VibeVoice-ASR (7B offline): the full official 50+ language list is only a chart image or an external link. Korean support is inferred from the report's Korean evaluation and from the Streaming/BitNet cards, not from a text list on the 7B card.
- Gemma 3n / Gemma 4: no official ASR language list naming Korean was found.
- Voxtral Small 24B 2507: language list not re-fetched (assumed to match Mini 2507; unverified).
- Release dates for Gemma 3n and Gemma 4 do not appear on the HF cards. The Gemma 4 E4B card cites a tech report "Published Jul 2" (2026).

## What Korean scores have been published, compared with Whisper large-v3 on the same test set?

### Takeaway
Published Korean numbers are sparse and almost never measured against Whisper large-v3 on the same test set by the same party.
- Best published open-weight number: **Nemotron 3.5 Transcribe at 2.78% CER on FLEURS-ko**.
- Nemotron 3.5 ASR Streaming 0.6B: 7.1–8.3% CER on FLEURS-ko.
- Voxtral Realtime: 14.3–19.8% **WER** on FLEURS-ko.
- VibeVoice-ASR: about 9.7% WER on MLC-Challenge Korean conversational speech.
- Moonshine tiny-ko: 8.9% CER on FLEURS-ko, beating Whisper tiny/base but not Whisper small/medium.

No vendor published KsponSpeech results, and only Phi-4 (after fine-tuning) published Zeroth.

### Cited Findings

**NVIDIA Nemotron 3.5 Transcribe 30B-A4B**
- FLEURS Korean **CER 2.78%** and FLEURS Korean language ID 100.00%. Speech translation: ko→en 24.23 BLEU, en→ko 27.68 BLEU. [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)
- No Common Voice ko number, and no Whisper comparison for Korean on the card. [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)

**NVIDIA Nemotron 3.5 ASR Streaming 0.6B** (FLEURS Korean CER by chunk latency) [HF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)

| Mode | 80 ms | 160 ms | 320 ms | 560 ms | 1.12 s |
|---|---|---|---|---|---|
| LangID-prompted | 7.59 | 7.70 | 7.27 | 7.18 | 7.12 |
| Auto-detect | 8.31 | 8.18 | 7.81 | 7.49 | 7.30 |

- No Whisper comparison on the card. [HF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)

**Mistral Voxtral Realtime** (FLEURS Korean WER, the only same-table comparison with an offline Whisper) [arXiv 2602.11298, Table 7](https://arxiv.org/html/2602.11298); [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)
- Voxtral Realtime by delay: **19.81 @160 ms, 17.56 @240 ms, 15.74 @480 ms (default), 14.90 @960 ms, 14.30 @2400 ms**.
- Offline Voxtral Mini Transcribe V2 (API-only): 12.29.
- "Whisper (offline)": 14.30. The extraction did not name the Whisper checkpoint, so whether it is large-v3 is unverified.
- GPT-4o mini Transcribe: 19.46. ElevenLabs Scribe v2 Realtime: 11.90.

**Microsoft VibeVoice-ASR (offline)** (MLC-Challenge Korean, Table 2; long-form multi-speaker conversational) [arXiv 2601.18184](https://arxiv.org/html/2601.18184)

| System | DER | cpWER | tcpWER | WER |
|---|---|---|---|---|
| VibeVoice-ASR | 4.52 | 15.35 | 16.07 | **9.65** |
| Gemini-2.5-Pro | 17.57 | 19.23 | 29.81 | 10.18 |
| Gemini-3-Pro | 39.28 | 19.39 | 57.33 | 11.21 |

- No Whisper baseline, and no FLEURS-ko or Common Voice-ko numbers. [arXiv 2601.18184](https://arxiv.org/html/2601.18184)

**Microsoft VibeVoice-ASR-BitNet (CPU)**
- MLC-KO WER **11.15**, versus 9.83 for VibeVoice-ASR-7B as quoted on the BitNet card. The report's 9.65 and this card's 9.83 differ slightly; setting unknown. [HF](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet)

**Microsoft VibeVoice-ASR-Streaming-7B** (MLC-Challenge Korean, recognition-only, Table 1) [arXiv 2609.02812](https://arxiv.org/html/2609.02812)
- VibeVoice-ASR-Streaming 7B: **CER 9.09**. Gemini 3.5 Transcribe Live: 9.59. GPT Realtime Whisper: 24.98. GPT Live Transcribe: 32.18. ElevenLabs Scribe v2 Realtime: 31.53.
- Speaker-attributed (Table 2): CER 9.09, cpCER 23.22, versus Azure CT at 10.32 / 23.97. [arXiv 2609.02812](https://arxiv.org/html/2609.02812)

**Moonshine** (Korean CER, Table 9: Common Voice 17 / FLEURS) [arXiv 2509.02523](https://arxiv.org/html/2509.02523); [HF](https://huggingface.co/UsefulSensors/moonshine-tiny-ko)
- moonshine-tiny-ko (final, 27M): **14.94 / 8.9**
- Whisper tiny: 37.27 / 15.83
- Whisper base: 19.42 / 11.95
- Whisper small: 12.32 / 8.47
- Whisper medium: 9.38 / 6.99
- Whisper large-v3 is not reported. No moonshine-base-ko numbers appear in the paper.

**Microsoft Phi-4-multimodal** (Zeroth-test, 457 samples) [HF card Appendix B](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)
- Original model: CER 99.16 / WER 99.63.
- After full audio-encoder fine-tune: 1.61 / 3.54.
- After LoRA (4 epochs): 2.72 / 7.19.

**Meta Omnilingual ASR**
- No Korean-specific CER appears in the paper text or the README. [arXiv 2511.09690](https://arxiv.org/html/2511.09690); [GitHub](https://github.com/facebookresearch/omnilingual-asr)
- Aggregate FLEURS-81 test CER: 7B LLM-ASR 5.6 versus Whisper large-v3 22.6. The paper reports an "80% win rate (65 out of 81)" over Whisper large-v3 on FLEURS-81. [arXiv 2511.09690](https://arxiv.org/html/2511.09690)

**Meta SeamlessM4T v2, IBM Granite, Kyutai, NVIDIA Canary/Parakeet**
- SeamlessM4T v2: the HF card gives no Korean ASR number (metrics sit in a separate zip). [HF](https://huggingface.co/facebook/seamless-m4t-v2-large)
- Granite, Kyutai, Canary/Parakeet: no Korean evaluation, since they do not support Korean (cards above).

**Google Gemma 4**
- E4B: FLEURS "0.08" and CoVoST 35.54. The metric (WER or CER, as a fraction) and the language breakdown are not stated, and there is no Korean number. [HF](https://huggingface.co/google/gemma-4-E4B-it)

**Whisper large-v3 Korean baseline (third-party only)**
- A third-party Korean model card reports whisper-large-v3 at **5.31% CER on FLEURS-ko and 6.01% on Common Voice 25 ko** (zero-shot). Not a primary OpenAI source, and the normalization is the card author's. [BuzzASR/korean](https://huggingface.co/BuzzASR/korean)
- No OpenAI primary per-language large-v3 Korean table was retrievable as text (OpenAI publishes it as a chart image). [search result summary; no primary URL]

**HF Open ASR Leaderboard**
- It has a multilingual track (FLEURS, MCV and MLS data; updated "as of 24 July 2026"). The README does not list the languages, so Korean inclusion is unconfirmed. [GitHub huggingface/open_asr_leaderboard](https://github.com/huggingface/open_asr_leaderboard)

### Inferences
- If BuzzASR's third-party Whisper large-v3 figure of about 5.3% CER on FLEURS-ko is roughly right, then:
  - Nemotron 3.5 Transcribe (2.78% CER) would be about 2× better than Whisper large-v3 on FLEURS-ko.
  - Nemotron Streaming 0.6B (about 7–8% CER) would be somewhat worse than offline Whisper large-v3, but it is streaming and about 1/3 the size.
  - Moonshine tiny-ko (8.9% CER) sits between Whisper base and Whisper small.
- Voxtral Realtime at 2.4 s delay ties the "Whisper (offline)" row (14.30 WER) in Mistral's own table. At the 480 ms default it is about 1.4 WER points worse.
- FLEURS is read speech. Lecture audio (spontaneous, domain jargon, long-form) will score worse. MLC-Challenge conversational Korean (VibeVoice about 9.7 WER / 9.1 CER) is probably closer to real lecture difficulty than FLEURS.

### Gaps
- No vendor in scope published **KsponSpeech** results.
- Only Phi-4 (after Korean fine-tuning) published **Zeroth**.
- No vendor published **Common Voice ko**, except Moonshine (CV17).
- No same-party, same-normalization comparison of any of these models with **Whisper large-v3** on FLEURS-ko was found, apart from Mistral's unnamed "Whisper (offline)" row. This needs an independent evaluation, for example in the user's own Korean lecture test set.
- Omnilingual ASR and SeamlessM4T v2 per-language Korean CER was not found in retrievable text.

## Which provide word timestamps and streaming suitable for a live lecture caption + click-to-play transcript?

### Takeaway
No single Korean-capable open model has documented support for both live streaming and word-level timestamps. A two-model design is needed:
- **Live captions:** Nemotron 3.5 ASR Streaming 0.6B (80 ms–1.12 s chunks, Korean CER about 7–8%) or Voxtral Realtime (80–2400 ms delay, vLLM `/v1/realtime`).
- **Final click-to-play transcript:** Nemotron 3.5 Transcribe (word timestamps via a CTC alignment head, 1-hour input, speaker tags) or VibeVoice-ASR (60-minute single pass with speaker plus timestamp segments).

VibeVoice-ASR-Streaming emits **no timestamps**.

### Cited Findings

**Nemotron 3.5 ASR Streaming 0.6B** [HF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)
- Cache-aware streaming with chunk options of 80/160/320/560/1120 ms (`att_context_size` [56,0] through [56,13]).
- Claims about 17× more concurrent streams than Parakeet RNNT 1.1B at 80 ms (240 vs 14 on one H100).
- Word timestamps are **not mentioned** on the card.

**Voxtral Realtime** [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602); [arXiv 2602.11298](https://arxiv.org/html/2602.11298)
- `transcription_delay_ms` is configurable in 80 ms multiples from 80 to 1200, plus 2400. Default 480 ms. Served over a vLLM realtime WebSocket endpoint `/v1/realtime`. [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)
- Timestamps are **not documented** for inference. The model emits one token per 80 ms frame with [P] padding and [W] word-boundary tokens and is trained on word-level-timestamp tuples. [arXiv 2602.11298](https://arxiv.org/html/2602.11298)
- The API-only Mini Transcribe V2 does offer word timestamps, diarization and context biasing. [Mistral blog](https://mistral.ai/news/voxtral-transcribe-2)

**VibeVoice-ASR-Streaming** [arXiv 2609.02812](https://arxiv.org/html/2609.02812)
- 2.9 s chunks (22 frames) or 2.0 s chunks (15 frames), each with a 0.5 s lookahead. First output after about 3.5 s or 2.5 s respectively.
- Appendix A: "no timestamps are emitted". Output is speaker-labelled text.

**Nemotron 3.5 Transcribe** [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)
- Word timestamps come from a CTC alignment head in the vLLM server (middleware flag plus request option). They are also available in Transformers, but **not** with DFlash2 speculative decoding, and not in the SGLang-Omni integration.
- Explicitly "an offline model… not a real-time streaming ASR service".

**VibeVoice-ASR (offline)**
- Outputs "Who / When / What" (speaker, timestamps, content). [HF](https://huggingface.co/microsoft/VibeVoice-ASR)
- The report does not say whether timestamps are word- or segment-level. Word-level timestamps appear only in its data pipeline (from Whisper). [arXiv 2601.18184](https://arxiv.org/html/2601.18184)
- The GitHub README mentions a "vLLM streaming option" for the ASR model. [GitHub](https://github.com/microsoft/VibeVoice)

**Non-Korean models, for reference**
- Kyutai STT has word timestamps, streaming (0.5 s delay) and semantic VAD, but only English/French. [HF](https://huggingface.co/kyutai/stt-1b-en_fr)
- Canary-1B-v2 and Parakeet-TDT-0.6B-v3 have word/segment (and, for Parakeet, char) timestamps, but no Korean. [HF canary-1b-v2](https://huggingface.co/nvidia/canary-1b-v2); [HF parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
- Granite-speech-4.1-2b-plus adds word timestamps and speaker-attributed ASR, but no Korean. [HF granite-speech-4.1-2b](https://huggingface.co/ibm-granite/granite-speech-4.1-2b)

**Other Korean-capable models**
- Moonshine Korean models are non-streaming (legacy). [Moonshine LICENSE](https://raw.githubusercontent.com/moonshine-ai/moonshine/main/LICENSE); [HF API](https://huggingface.co/api/models?author=moonshine-ai&limit=100)
- Omnilingual ASR's README does not mention timestamps or streaming. [GitHub](https://github.com/facebookresearch/omnilingual-asr)

### Inferences
- Live-caption candidates for Korean, from the published numbers:
  - Nemotron Streaming 0.6B: commercial-OK license, small, about 7–8% CER on FLEURS-ko.
  - Voxtral Realtime: Apache 2.0, 4B, 14–16% WER on FLEURS-ko at practical delays.
- NeMo RNNT/TDT models generally support timestamps through `transcribe(..., timestamps=True)`, as the Parakeet v3 card shows. It is plausible but **unverified** that the Nemotron streaming RNNT supports the same for Korean.
- For click-to-play, a final pass with Nemotron 3.5 Transcribe (word timestamps) is the documented route. Alternatively, run VibeVoice-ASR (segment timestamps) and then a separate Korean forced aligner, since Omnilingual's CTC models could serve as an aligner (inference, untested).

### Gaps
- Whether the timestamps of Nemotron 3.5 ASR Streaming, Voxtral Realtime and VibeVoice-ASR (7B) are exposed at word level for Korean is unverified.
- No published latency or accuracy evaluation on Korean lecture-style audio exists for any of these streaming models.

## What are license terms and fine-tuning paths?

### Takeaway
Licenses for the Korean-capable models:
- **Commercial-friendly:** VibeVoice family (MIT), Nemotron 3.5 family (OpenMDW-1.1), Voxtral Realtime (Apache 2.0), Omnilingual ASR (Apache 2.0), Phi-4-mm (MIT).
- **Restrictive:** SeamlessM4T v2 (CC-BY-NC-4.0) and Moonshine Korean (Moonshine Community License, which revokes rights above US$1M annual revenue).

Fine-tuning paths:
- NeMo: Nemotron, plus a HF blog for the streaming model.
- VibeVoice: `finetuning-asr` folder.
- Phi-4-mm: `sample_finetune_speech.py`, with documented Korean LoRA and full-encoder results.
- Omnilingual: CTC/LLM recipes.
- Voxtral Realtime: no official recipe.

### Cited Findings

**Microsoft VibeVoice-ASR family (MIT)**
- License: MIT for the repo, the ASR weights and the BitNet weights. [GitHub](https://github.com/microsoft/VibeVoice); [HF](https://huggingface.co/microsoft/VibeVoice-ASR); [HF BitNet](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet)
- Fine-tuning code lives in the `finetuning-asr` folder, released 2026-01-21. LoRA is not mentioned on the HF card. [GitHub](https://github.com/microsoft/VibeVoice); [HF](https://huggingface.co/microsoft/VibeVoice-ASR)
- SFT data: MLC-SLM and Fisher training splits, Muse music, about 6,000 h of synthetic context-aware audio, and refined long-form data. [arXiv 2601.18184](https://arxiv.org/html/2601.18184)

**NVIDIA Nemotron 3.5 family (OpenMDW-1.1)**
- Nemotron 3.5 Transcribe and Streaming 0.6B are OpenMDW-1.1, "commercial or non-commercial use". [HF Transcribe](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B); [HF Streaming](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)
- Transcribe: "can be adapted… with the fine-tuning toolkit in NeMo Speech". [HF Transcribe](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)
- Streaming: a HF blog covers fine-tuning for language accuracy. [HF Streaming](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)

**NVIDIA Canary/Parakeet (CC-BY-4.0)**
- Commercial use allowed; no Korean. [HF canary-1b-v2](https://huggingface.co/nvidia/canary-1b-v2); [HF parakeet-tdt-0.6b-v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)

**Mistral Voxtral Realtime (Apache 2.0)**
- No official fine-tuning guidance. The Hub lists 5 community adapters and 23 finetunes. [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)

**Meta Omnilingual ASR (Apache 2.0)**
- Fine-tuning recipes and a data-prep guide exist for the CTC and LLM models. "LLM Unlimited" variants do **not** support fine-tuning recipes. [GitHub](https://github.com/facebookresearch/omnilingual-asr)

**Meta SeamlessM4T v2 (CC-BY-NC-4.0)**
- Non-commercial license. The card references a fine-tuning README in seamless_communication. [HF](https://huggingface.co/facebook/seamless-m4t-v2-large)

**Moonshine Korean (Moonshine Community License)** [Moonshine LICENSE](https://raw.githubusercontent.com/moonshine-ai/moonshine/main/LICENSE); [GitHub](https://github.com/moonshine-ai/moonshine)
- Korean tiny/base are under the Moonshine Community License. Streaming models and English tiny/base are MIT.
- Terms:
  - Commercial use requires registration.
  - Rights terminate if annual revenue exceeds US$1M.
  - Distributions must display "Powered by Moonshine AI".
  - Using outputs to build foundation models is prohibited.
- The license text partly references "Stability", an apparent template carry-over.
- Fine-tuning: the docs only mention "domain customization".

**Microsoft Phi-4-multimodal (MIT)** [HF](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)
- Provides `sample_finetune_speech.py`. vLLM serves speech/vision LoRA adapters (`--enable-lora`).
- Korean recipe: about 35K samples from Zeroth, CV17-ko, MINDS-14-ko and custom tech-talk audio, 4 epochs, batch 16, one A100 80GB.
  - Full audio-encoder unfreeze reached Zeroth CER 1.61.
  - LoRA reached 2.72.
- Released community checkpoint: [daekeun-ml/Phi-4-multimodal-finetune-ko-speech](https://huggingface.co/daekeun-ml/Phi-4-multimodal-finetune-ko-speech). The card calls it a "PoC… not production-quality".

**IBM Granite Speech (Apache 2.0)**
- Colab fine-tuning notebook; no Korean. [HF granite-speech-4.1-2b](https://huggingface.co/ibm-granite/granite-speech-4.1-2b); [HF granite-4.0-1b-speech](https://huggingface.co/ibm-granite/granite-4.0-1b-speech)

**Kyutai STT (CC-BY 4.0)**
- No Korean. [HF](https://huggingface.co/kyutai/stt-1b-en_fr)

**Google Gemma**
- Gemma 4 E4B: the HF metadata says "apache-2.0", but the link points to a "gemma_4_license" document. The governing terms are ambiguous and should be checked.
- The card notes the 12B Unified model can be fine-tuned in one pass (no separate encoders). The Hub lists 444 adapters. [HF gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it)
- Gemma 3n is under the Gemma Terms of Use. [HF gemma-3n-E4B-it](https://huggingface.co/google/gemma-3n-E4B-it)

### Inferences
- For a product that may be commercialized:
  - Nemotron 3.5 (OpenMDW), VibeVoice (MIT), Voxtral Realtime (Apache) and Omnilingual (Apache) are the clean choices.
  - Avoid SeamlessM4T v2 (NC).
  - Moonshine Korean is usable only below the US$1M revenue threshold and with branding.
- Domain adaptation to Korean lecture jargon:
  - NeMo fine-tuning of Nemotron Streaming 0.6B is the cheapest documented path (0.6B params).
  - VibeVoice's hotword/context prompting offers zero-training biasing, as do Granite's keyword prompts (no Korean) and Voxtral V2 context biasing (API-only; non-English is "experimental").

### Gaps
- The OpenMDW-1.1 license text (obligations, attribution, field-of-use limits) was not reviewed in this pass.
- Whether VibeVoice's `finetuning-asr` supports LoRA, and its GPU memory needs, is not documented on the card.
- No published Korean fine-tuning results exist for Nemotron, VibeVoice, Voxtral or Omnilingual.

## Which can run without CUDA (PyTorch ROCm, ONNX, CPU, GGUF)?

### Takeaway
Korean-capable options with documented non-CUDA paths:
- **VibeVoice-ASR-BitNet:** CPU-only GGUF via microsoft/VibeASR.cpp, real time from 3 threads.
- **Nemotron 3.5 ASR Streaming 0.6B:** q8_0 GGUF via NeMo-Speech.cpp.
- **Moonshine tiny/base-ko:** on-device library plus community GGUF.

The large models (Nemotron 3.5 Transcribe, VibeVoice-ASR 7B, Voxtral Realtime) are documented for NVIDIA GPUs. ROCm is officially documented for **none** of them, though Transformers-based ones may work on PyTorch ROCm (unverified).

### Cited Findings

**VibeVoice-ASR-BitNet** [HF](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet); [GitHub](https://github.com/microsoft/VibeVoice)
- 1.58 GB quantized (0.65 GB VAE encoder plus 0.92 GB LM), versus 4.62 GB FP16.
- GGUF on ggml with AVX2/NEON kernels (repo microsoft/VibeASR.cpp).
- RTF 1.98 on 1 thread and 0.77 on 3 threads (AMD EPYC 7V13, 20 s clip).
- The card shows llama.cpp/Ollama examples, though with a tag mismatch.
- The GitHub README says no GPU is required and does not mention ROCm.

**Nemotron 3.5 ASR Streaming 0.6B**
- NeMo, NeMo-Speech.cpp (native C++, q8_0 GGUF), and Transformers ≥ 5.13.0. Listed hardware is NVIDIA only (Ampere through Volta, Jetson). [HF](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)

**Nemotron 3.5 Transcribe**
- vLLM 0.32.0, SGLang-Omni 0.2.0, Transformers (from source), and "GGML… for supported GPUs, including native Windows".
- Deployment target: 1× H100 80 GB. FP8 and NVFP4 variants exist. Listed GPUs include the RTX 5090 and L40S. [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)

**Voxtral Realtime** [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)
- Official: vLLM (recommended; single GPU ≥16 GB) and Transformers ≥ 5.2.0.
- Untested community ports: pure C, MLX, Rust, and ExecuTorch.
- No official llama.cpp/GGUF or ONNX.

**Moonshine**
- Runtime library for Python, JS/WASM, iOS, Android, macOS, Linux, Windows and Raspberry Pi, on-device. [GitHub](https://github.com/moonshine-ai/moonshine)
- Community GGUF builds of moonshine-tiny-ko / base-ko exist for transcribe.cpp. [HF handy-computer/moonshine-base-ko-gguf](https://huggingface.co/handy-computer/moonshine-base-ko-gguf)

**Meta Omnilingual ASR**
- fairseq2/PyTorch with listed per-model VRAM (about 2 GiB for CTC-300M up to about 20 GiB for the 7B zero-shot). No ONNX/GGUF or ROCm mention. [GitHub](https://github.com/facebookresearch/omnilingual-asr)

**Microsoft Phi-4-multimodal**
- A separate `Phi-4-multimodal-instruct-onnx` model exists (ONNX). [HF](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)

**Google Gemma 4**
- The card links AMD Developer Cloud notebooks (implying AMD GPU usability via Transformers) and community quantizations. [HF](https://huggingface.co/google/gemma-4-E4B-it)

**Non-Korean models, for reference**
- Granite Speech 4.x offers llama.cpp GGUF (Q8_0) and mlx-audio, but no Korean. [HF granite-speech-4.1-2b](https://huggingface.co/ibm-granite/granite-speech-4.1-2b)
- Parakeet-TDT-0.6B-v3 offers NeMo-Speech.cpp GGUF, but no Korean. [HF](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)

### Inferences
- On an AMD/ROCm or CPU-only workstation, the lowest-risk Korean options are:
  - VibeVoice-ASR-BitNet (CPU GGUF, MLC-KO WER 11.15, MIT)
  - Nemotron Streaming 0.6B via NeMo-Speech.cpp GGUF (CPU support implied by the "native C++ runtime" but not explicitly stated)
  - Moonshine Korean (license caveat)
- Nemotron 3.5 Transcribe (34B MoE) is realistically a datacenter or RTX 5090-class NVIDIA model.

### Gaps
- No official ROCm support statement was found for any model in scope.
- NeMo-Speech.cpp CPU performance for the Korean streaming model was not documented.
- Whether VibeASR.cpp's BitNet build exposes timestamps or speaker labels was not documented ("not mentioned" on the card).

## Long-form handling (1–2 h lecture), diarization and hallucination behavior

### Takeaway
None of the Korean-capable models takes a full 2-hour lecture in one documented pass:
- VibeVoice-ASR and Nemotron 3.5 Transcribe cap at about 60 minutes per pass (so split at about 55–60 min with overlap).
- Voxtral Realtime streams indefinitely with a sliding window (about 3 h at the default context).
- Omnilingual's standard CTC/LLM models accept only clips under 40 s ("Unlimited" v2 variants lift this).
- Gemma audio is limited to 30 s clips, and Phi-4-mm to about 40 s.

Diarization is built in for VibeVoice (offline and streaming) and Nemotron 3.5 Transcribe.

### Cited Findings

**VibeVoice-ASR**
- Up to 60 minutes in a single pass (64K tokens), no chunking. Jointly does ASR, diarization and timestamps. Supports hotwords and context. [HF](https://huggingface.co/microsoft/VibeVoice-ASR)
- Labels non-speech as [Silence]/[Music] "to prevent the model from hallucinating text during silence or background noise".
- Gemini was evaluated on 240 s chunks because of its long-input timestamp errors and hallucinations.
- No VibeVoice hallucination rate is reported. [arXiv 2601.18184](https://arxiv.org/html/2601.18184)

**Nemotron 3.5 Transcribe** [HF](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)
- Trained on recordings up to one hour (65,536-token context). The long-form leaderboard used 55-minute chunks with 5 s overlap. "Not guaranteed to generalize beyond these limits".
- Speaker tags (`<spk:0>`) with a built-in Nemotron-3-Diarization speaker encoder.
- Known errors include "hallucinated speech, incorrect language choice, and speaker attribution errors".

**Voxtral Realtime**
- Sliding-window attention for unbounded streams. 1 h needs `--max-model-len` ≥ 45000. The default of 131072 tokens is about 3 h. [HF](https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602)
- No hallucination discussion in the paper. [arXiv 2602.11298](https://arxiv.org/html/2602.11298)

**Omnilingual ASR**
- "Currently only audio files shorter than 40 seconds are accepted" for the CTC/LLM suites. LLM Unlimited v2 handles unlimited length (benchmarked on 15-minute audio). [GitHub](https://github.com/facebookresearch/omnilingual-asr)

**Gemma 4 / Gemma 3n**
- 30 s maximum audio clip. Gemma 4 uses 25 tokens/s, Gemma 3n 6.25 tokens/s. [Google AI Gemma audio docs](https://ai.google.dev/gemma/docs/capabilities/audio)

**Phi-4-multimodal**
- About 40 s suggested for audio tasks, 30 min for summarization. [HF](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)

**Moonshine Korean**
- The card warns the model "can produce text not present in the audio" and that repetitive output is likely. It suggests capping output at about 13 tokens per second of audio. Worse on short or clipped segments. [HF](https://huggingface.co/UsefulSensors/moonshine-tiny-ko)

**Canary-1B-v2 (non-Korean reference)**
- Uses dynamic chunking with 1 s overlap for long audio. Hallucination rate of 134.7 characters/min on MUSAN noise. [HF](https://huggingface.co/nvidia/canary-1b-v2)

**Parakeet-TDT-0.6B-v3 (non-Korean reference)**
- Up to 24 min with full attention (A100 80GB), up to 3 h with local attention. [HF](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)

**Kyutai STT (non-Korean reference)**
- "Perform well with audio as long as 2 hours". [HF](https://huggingface.co/kyutai/stt-1b-en_fr)

### Inferences
- For a 1–2 hour Korean lecture, the safest offline plan is to split at about 55–60 minutes with a few seconds of overlap for Nemotron 3.5 Transcribe or VibeVoice-ASR. Within each hour-long segment, diarization stays consistent.
- VibeVoice's explicit non-speech tags and both vendors' hour-long single-pass design should reduce the Whisper-style repetition loops this repo already handles (recent commit "Detect and retry Whisper repetition loops"). This is unmeasured for Korean.
- Small seq2seq models (Moonshine) still need repetition guards.

### Gaps
- No Korean-specific hallucination or repetition-rate measurements were published for any model in scope.
- Speaker-label consistency across separately processed 1-hour chunks is not addressed by any vendor.
