# Whisper-family ASR options for local Korean university-lecture transcription (state as of 2026-11-01)

Scope note: Whisper family only (official checkpoints, derived runtimes/tools, Korean fine-tunes on Hugging Face). Qwen3-ASR and GPT-4o-transcribe appear only as reference points where a source evaluated them alongside Whisper. AMD Strix Halo runtime support is covered by another researcher. This file only names which runtime path each model can use.

Reading guide for numbers: Korean CER for the *same* model varies by up to 2x between evaluations. The main causes are KsponSpeech's dual-transcription labels, number/Latin-script normalization and spacing. **Only compare numbers that come from the same evaluation (same source row/table).** Every model-card number below is self-reported unless stated otherwise.

---

## Q1. What are the best published Korean CER/WER numbers for large-v3 vs large-v3-turbo vs Korean fine-tunes, and on which test sets?

### Takeaway
Out of the box, large-v3 is slightly but consistently better than large-v3-turbo on Korean. Independent evaluations put the gap at about 0.2–1.5 CER points: OpenKoASR (Oct 2026) has large-v3 at 18.00 vs turbo 19.53 CER on KsponSpeech clean and 16.46 vs 17.13 on other. A FLEURS-ko check (Oct 2026, 60 utterances) has 4.08 vs 4.60. Turbo is about 2.2x faster. Korean fine-tunes report much lower numbers on their own evaluations. The strongest documented one is BatiAI's batisay-ko-large v1.1 (Jul 2026): KsponSpeech eval_clean 6.83 / eval_other 8.01 / Zeroth 1.26 CER. Its turbo sibling scores 6.99 / 8.33. These are self-reported under a "strict" normalization, so they cannot be compared with independent leaderboards.

### Cited Findings

**Official OpenAI checkpoints**
- **large-v3**: released 2023-11-06 (`openai-whisper==20231106`). It uses 128 mel bins instead of 80 and was trained on about 1M h of weakly labeled audio plus 4M h pseudo-labeled by large-v2, for 2.0 epochs. Korean was evaluated with **CER** (not WER) on Common Voice 15 and FLEURS because of inconsistent spacing. For FLEURS, parenthesized Latin-script phrases were stripped from the Korean labels with regexes. The Korean numbers exist only in a chart image (not machine-readable). — [openai/whisper discussion #1762](https://github.com/openai/whisper/discussions/1762)
- **large-v3-turbo**: released 2024-10-01. It has 4 decoder layers (vs 32) and was fine-tuned 2 more epochs on large-v3's multilingual transcription data, *excluding translation* data. It shows "larger degradation on some languages like Thai and Cantonese" and is described as "similar to large-v2" overall. No Korean-specific numbers were published. — [openai/whisper discussion #2363](https://github.com/openai/whisper/discussions/2363)
- Sizes: large-v3 is about 1.55B params ([batisay-ko-large card](https://huggingface.co/batiai/batisay-ko-large) states 1.55B for its large-v3 base). Turbo-architecture models are about 809M ([batisay-ko-turbo card](https://huggingface.co/batiai/batisay-ko-turbo)). In whisper.cpp, ggml `large-v3-turbo` is 1.5 GiB and `large-v3-turbo-q5_0` is 547 MiB — [whisper.cpp models/README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/models/README.md)
- License: OpenAI Whisper weights are MIT (stated as the license inherited by distil-whisper) — [distil-large-v3.5 card](https://huggingface.co/distil-whisper/distil-large-v3.5)
- **No newer open-weight Whisper since turbo (Oct 2024).** OpenAI's 2025–2026 speech-to-text releases are API-only: gpt-4o-transcribe / gpt-4o-mini-transcribe (Mar 2025), and "GPT-Realtime-Whisper", a streaming STT model launched May 2026 at $0.017/min. — [9to5Mac, 2026-05-07](https://9to5mac.com/2026/05/07/openai-has-new-voice-models-that-reason-translate-and-transcribe-as-you-speak/); [Wikipedia: Whisper](https://en.wikipedia.org/wiki/Whisper_(speech_recognition_system)). (UNVERIFIED from primary source: openai.com returned 403. Details come from search snippets. A third-party page also claims "gpt-transcribe" in July 2026 and whisper-1 deprecation on 2026-08-26, which I could not confirm.)

**Independent Korean evaluations of the official models (newest first)**
- **OpenKoASR leaderboard** (runs 2026-10-08/09, RTX 3090 Ti, "Kspon" normalization, samples with CER > 100% excluded, 3,000 utterances per Kspon subset). Main CER / WER / macro RTFx — [OpenKoASR leaderboard.md](https://raw.githubusercontent.com/GT-KIM/open-korean-automatic-speech-recognition/main/leaderboard.md); [repo](https://github.com/GT-KIM/open-korean-automatic-speech-recognition)
  - KsponSpeech clean: Qwen3-ASR-1.7B 16.26 / 39.85; **large-v3 18.00 / 39.41 / 24.96x**; Qwen3-ASR-0.6B 18.58; **large-v3-turbo 19.53 / 41.44 / 54.56x**; medium 21.01; small 23.22; base 30.40; tiny 37.27
  - KsponSpeech other: Qwen3-ASR-1.7B 14.26; Qwen3-0.6B 16.32; **large-v3 16.46 / 39.50**; **turbo 17.13 / 40.74**; medium 19.08; small 21.35
  - AIHub low-quality telephone (all subsets): **large-v3 10.63 / 28.40**; **turbo 10.85 / 28.80**; Qwen3-ASR-1.7B 19.91; medium 30.08
  - The same repo's "legacy" run reports large-v3 KsponSpeech clean at CER 23.12 / WER 29.52. That gives three different large-v3 Kspon numbers depending on protocol.
- **FLEURS ko_kr**, first 60 test utterances (741 s), CPU only, run 2026-10-04, bootstrap 95% CI — [zkaelxz/U00 PR #740](https://github.com/zkaelxz/U00/pull/740)
  - faster-whisper large-v3 4.08 (CI 2.5–5.9), turbo 4.60 (2.9–6.6), medium 4.93, Qwen3-ASR-1.7B 3.34 (1.9–5.1)
  - Large-v3 beat turbo by 0.52 points (paired CI −0.98 to −0.11). Turning VAD off hurt large-v3 (5.11). A Korean initial_prompt hurt large-v3 (4.63) and medium (5.37).
  - About 105 of turbo's 124 character errors fell in utterances containing digits or Latin text.
  - Hallucinations: 0 in every row (clean read speech).
- **HiKE benchmark** (EACL Findings 2026; v4 2026-01-13), FLEURS monolingual Korean CER: "Whisper-Large" (version not specified) 3.2, Medium 3.4, Small 4.5, Base 7.8, Tiny 11.9; GPT-4o-transcribe 2.5; SenseVoice-Small 6.4 — [HiKE arXiv 2509.24613v4](https://arxiv.org/html/2509.24613v4)
- **KAIST, Korean meteorological experts** (arXiv 2410.18444 v3, 2025-09-14), zero-shot on KsponSpeechEval (3k): large-v2 CER 14.66 / WER 29.97 / sWER 20.75; medium 14.33; small 16.75; tiny 32.67. Large-v2 fine-tuned on KsponSpeech (parameter-efficient): 10.48 CER — [arXiv 2410.18444](https://arxiv.org/pdf/2410.18444)
- **ENERZAi blog** (byline 2025-09-26; page metadata says 2026-10-28, a conflict): whisper-large-v3 KsponSpeech Eval-Other CER 11.13% — [ENERZAi](https://enerzai.com/resources/blog/small-models-big-heat-conquering-korean-asr-with-low-bit-whisper)
- The batisay-ko-large card cites "OpenAI Whisper Large v3 raw" at about 12% CER on KsponSpeech eval_clean — [batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)
- Oh, Kim & Park (2023, Phonetics & Speech Sciences 15(3)), zero-shot CER: medium kspon-evalclean 11.94 / evalother 11.96; base 22.85 / 21.12; tiny 33.57 / 30.90 — [eksss.org](https://www.eksss.org/archive/view_article?pid=pss-15-3-75)

**Korean fine-tunes (self-reported)**
- **batisay-ko-large v1.1** (BatiAI). Base: large-v3, 1.55B. v1.0 released 2026-06-11, v1.1 on 2026-07-05.
  - Data: about 5,000 h multi-domain plus a 1,352 h generalization cycle. Sources: KsponSpeech, Zeroth-Korean, AI Hub meeting (132), **lecture (115)**, conversation (130) and counseling (100), plus 571 h of real 8 kHz telephone speech.
  - CER v1.1 (v1.0): Kspon eval_clean 6.83 (7.82); eval_other 8.01 (8.94); AI Hub meeting 7.13 (8.25); counseling 8 kHz 5.33 (9.97); conversation 2.12 (3.88); Zeroth 1.26 (1.68). N=500 per domain (Zeroth N=250), "strict" normalization.
  - Not reported: FLEURS and Common Voice.
  - Formats: safetensors F32 3.1 GB; GGUF/ggml q8_0 1.7 GB, q5_0 1.1 GB, q4_0 880 MB; separate MLX and CoreML repos. No CT2 build.
  - License: BatiAI Community License v2.0. Free for personal, academic, non-profit, internal-company and government use. External SaaS, embedded products and companies with ≥1B KRW revenue must negotiate. Converts to Apache 2.0 four years after release.
  - — [batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)
- **batisay-ko-turbo v1.1** (BatiAI). Base: large-v3-turbo, 809M. v1.0 released 2026-06-15, v1.1 on 2026-06-20.
  - Data: about 4,300 h selected from more than 25,000 h, including KsponSpeech and AI Hub sets (general, meetings, **lectures**, conversation, 8 kHz call center, noisy calls). Three progressive cycles with KsponSpeech replay. Transcription annotations stripped from labels.
  - CER: Kspon eval_clean 6.99, eval_other 8.33, meetings 8.90, call center 5.67, conversation 3.00 (500 utterances/domain).
  - Real long calls: 14.85% (MLX) vs 17.1% (ggml q5_0) vs 19.11% (base). Small sample, scored against automatic transcripts.
  - Formats: GGUF q5_0 548 MB (recommended), q4_0 453 MB, q8_0 834 MB, f32 1.6 GB; MLX fp16. Same license as large.
  - — [batisay-ko-turbo](https://huggingface.co/batiai/batisay-ko-turbo)
- **batisay-ko-base**: Apache 2.0 (fully free). Kspon eval_clean 7.77, eval_other 12.28; 19.11% on real calls — [batisay-ko-turbo card](https://huggingface.co/batiai/batisay-ko-turbo). (The org page lists it but gives no separate details — [batiai org](https://huggingface.co/batiai).)
- **ghost613/whisper-large-v3-turbo-korean**: base turbo (0.8B, F32), trained on Bingsu/zeroth-korean (206 h 43 m).
  - Zeroth test split into 50% validation / 50% test (about 2 h 22 m each). Test CER 7.58 → **2.06**, WER 26.75 → 4.89. Validation CER 6.67 → 1.78.
  - Card says "Models did not converge, better results are possible".
  - No license, hyperparameters or date. Its "Whisper family" collection was updated 2024-10-29.
  - — [ghost613 card](https://huggingface.co/ghost613/whisper-large-v3-turbo-korean)
- **o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2**: base turbo. Custom Zeroth-derived set (102,263 samples, 93/7 random split).
  - WER 19.91, "CER 0.0660". The unit is ambiguous: probably a fraction, i.e. 6.6%, given WER 19.9.
  - "still being incrementally fine-tuned in stages". Dataset updated 2025-01-20. No license stated. The card title says "Large v2", which conflicts with the stated base.
  - — [o0dimplz0o card](https://huggingface.co/o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2)
- **SungBeom/whisper-small-ko**: Whisper small, Apache-2.0. Trained on 13,946 h from 7 AI Hub corpora (customer service, conversation, free speech, call center, in-car, elderly commands, etc.). WER 9.48 on its own held-out "part 1" at epoch 0.2. No CER, no per-test-set results, no dates — [SungBeom card](https://huggingface.co/SungBeom/whisper-small-ko)
- Other small or stale cards (search snippets only, not fetched):
  - spow12/whisper-medium-zeroth_korean: WER 3.96 / CER 1.71. Text says KsponSpeech, but the dataset tag is Bingsu/zeroth-korean — [card](https://huggingface.co/spow12/whisper-medium-zeroth_korean)
  - TARARARAK whisper-base Kspon: CER 14.30, in progress, mid-2024 — [card](https://huggingface.co/TARARARAK/Whisper_Korean_fine-tune)
  - imTak whisper_large_v3_turbo_korean: WER 5.27 on its own set — [card](https://huggingface.co/imTak/whisper_large_v3_ko_ft_ft)
- **ENERZAi EZWhisper** (commercial blog; weights availability not stated): Whisper-Small retrained with a Korean-centric tokenizer on about 50K h. CER 6.45 vs 18.05 for the original tokenizer on an *unnamed* Korean test set. Also claims a 1.58-bit QAT model — [ENERZAi](https://enerzai.com/resources/blog/small-models-big-heat-conquering-korean-asr-with-low-bit-whisper)
- Oh et al. (2023): Whisper **medium** fine-tuned on KsponSpeech (about 1,000 h) reached evalclean 7.61 / evalother 8.36. Also spon-debate 7.42 and spon-present 4.74 (presentation speech, closest to lectures), but broadcast got slightly worse (14.03 → 14.75) — [eksss.org](https://www.eksss.org/archive/view_article?pid=pss-15-3-75)
- Non-Whisper reference: TeamUNIVA/qwen3_asr_1.7b_ko self-reports CER FLEURS-ko 1.26, KsponSpeech 5.94, Zeroth 2.20. Base Qwen3-ASR-1.7B: Kspon 8.65, Zeroth 2.64 (search snippet; not fetched) — [TeamUNIVA card](https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko)

**Derived / distilled variants**
- **distil-whisper (distil-large-v3.5)**: **English-only**, 756M, MIT, trained on about 98k h. About 1.5x faster than turbo (long-form RTFx 49.34 vs 33.81). Can serve as a speculative-decoding draft for large-v3. No Korean distillation published — [distil-large-v3.5 card](https://huggingface.co/distil-whisper/distil-large-v3.5)
- **faster-whisper / CTranslate2**: same weights re-packaged. Claims "up to 4 times faster" than openai/whisper at the same accuracy, with int8 on CPU/GPU. The README documents CUDA 12 and CPU and does not mention ROCm — [faster-whisper](https://github.com/SYSTRAN/faster-whisper)

### Inferences
- For a lecture app, the realistic quality ranking on Korean spontaneous speech is: Korean multi-domain fine-tune (batisay-ko-large ≈ batisay-ko-turbo) > large-v3 > turbo > medium. This holds only if BatiAI's numbers transfer to lecture audio. Their training data explicitly includes the AI Hub lecture corpus, but they do not report a lecture-domain test.
- Converting batisay's "strict" CER against "large-v3 raw ≈12%" suggests roughly a 40–45% relative CER reduction on KsponSpeech clean. OpenKoASR's 18.00% for the same model under different normalization shows that absolute levels are protocol-dependent. An in-house test set of real lectures is required before choosing.
- The large-v3 vs turbo gap (≈0.2–1.5 CER points) is small relative to fine-tune gains. Turbo's 2.2x speed, and the fact that batisay-ko-turbo nearly matches batisay-ko-large, make the turbo-sized Korean fine-tune the efficiency sweet spot. The caveat is turbo's worse repetition-loop behavior (see Q3).
- Zeroth-Korean is read speech with a small vocabulary, and fine-tunes reach 1–2% CER there. It is a poor proxy for lecture audio. KsponSpeech eval_other and AI Hub meeting/lecture sets are closer.

### Gaps
- Official per-language Korean CER for large-v3/turbo on FLEURS and Common Voice 15 exists only as a chart image in OpenAI's GitHub. I could not read exact values.
- No independent (third-party) evaluation of batisay, ghost613 or other Korean fine-tunes on a common test set was found. OpenKoASR does not include fine-tunes. The baryonlabs/ko-asr-arena Space was asleep and showed no data.
- No published Korean Common Voice numbers for any fine-tune. FLEURS-ko was reported only for official models (PR #740, HiKE).
- No lecture-domain (university lecture) Korean benchmark for any Whisper model was found.
- CrisperWhisper 2.0 and whisper-timestamped report no Korean accuracy numbers.

---

## Q2. Which Korean fine-tunes are actively maintained in 2025–2026, and do they degrade on English code-switching (English technical terms inside Korean speech)?

### Takeaway
BatiAI's batisay family (ko-large, ko-turbo, ko-base; June–July 2026, with ggml/GGUF builds) is the only Korean Whisper fine-tune line I found with 2026 releases, versioning and multi-domain evaluation. Most other HF Korean fine-tunes are one-off 2023–2024 Zeroth/Kspon experiments, many unconverged. No Korean fine-tune card reports code-switching results. Indirect evidence says Korean-only fine-tuning damages English recognition and domain terms: LibriSpeech-other WER 6.74 → 57.56 after Kspon fine-tuning (medium), and weather-term CER rose after KsponSpeech fine-tuning. Off-the-shelf large Whisper is already weak on Korean-English code-switching (HiKE MER 26.1).

### Cited Findings
- **Maintenance status**
  - batisay-ko-large: v1.0 2026-06-11 → v1.1 2026-07-05 — [card](https://huggingface.co/batiai/batisay-ko-large)
  - batisay-ko-turbo: v1.0 2026-06-15 → v1.1 2026-06-20 — [card](https://huggingface.co/batiai/batisay-ko-turbo)
  - Downstream adoption: the HearingAid Windows captioning app added batisay-ko-turbo q5_0 (574 MB) and q8_0 (874 MB) — [HearingAid PR #10](https://github.com/hyeseong1835/HearingAid/pull/10)
  - o0dimplz0o turbo-Zeroth-KO-v2 says it is still being trained "in stages" (dataset updated 2025-01-20) — [card](https://huggingface.co/o0dimplz0o/Whisper-Large-v3-turbo-STT-Zeroth-KO-v2)
  - ghost613 turbo-korean: collection updated 2024-10-29, "did not converge" — [card](https://huggingface.co/ghost613/whisper-large-v3-turbo-korean)
  - SungBeom whisper-small-ko: no dates; 205 downloads last month — [card](https://huggingface.co/SungBeom/whisper-small-ko)
  - TARARARAK whisper-base Kspon: commits mid-2024 (search snippet) — [card](https://huggingface.co/TARARARAK/Whisper_Korean_fine-tune)
- **batisay known issues**: batisay-ko-large v1.1 has stray single Latin letters (e.g., "o", "l") in output, to be stripped in post-processing. Neither batisay card discusses English code-switching — [batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large); [batisay-ko-turbo](https://huggingface.co/batiai/batisay-ko-turbo)
- **English degradation after Korean fine-tuning** (Oh, Kim & Park 2023): fine-tuning Whisper on about 1,000 h of KsponSpeech "severely degraded" English (LibriSpeech test-other WER): medium 6.74 → 57.56, base 11.95 → 42.05, tiny 15.79 → 113.17. Some English audio was output in Korean even with the English prompt set — [eksss.org](https://www.eksss.org/archive/view_article?pid=pss-15-3-75)
- **Domain/technical-term degradation** (KAIST, arXiv 2410.18444 v3, 2025-09)
  - Fine-tuning large-v2 on general KsponSpeech improved KsponSpeechEval CER (14.66 → 10.48) but *worsened* specialized weather-term queries. WeatherDev CER 11.78 → 16.92; WeatherTest 18.35 → 24.57.
  - Fine-tuning on TTS-synthesized domain sentences cut WeatherTest CER to 10.64.
  - Example: English acronyms and units (EPS, KIM, hPa) were rendered as Hangul phonetics in zero-shot output ("킴", "퀘토 파스칼") and recovered after domain fine-tuning.
  - — [arXiv 2410.18444](https://arxiv.org/pdf/2410.18444)
- **HiKE** Korean-English code-switching benchmark (EACL Findings 2026)
  - Data: 1,121 utterances, about 2.2 h, 13 bilingual speakers. Topics include academic (157), software development (162) and medical (76).
  - Overall MER / PIER: Whisper-Large 26.1 / 36.0; Medium 31.3 / 41.3; Small 43.5; GPT-4o-transcribe 21.8 / 28.8; SenseVoice-Small 32.5.
  - Fine-tuning Whisper-Medium on natural intra-sentential CS (AIHub) cut MER 31.3 → 9.0 but raised monolingual Korean CER 3.4 → 6.0. Synthetic inter-sentential CS gave MER 22.1 with Korean CER 3.7.
  - Loanwords (e.g., 버스/bus) are accepted in either script. This reduced measurement noise by 4.9% MER on average.
  - — [HiKE v4](https://arxiv.org/html/2509.24613v4)
- **Gated LoRA for personalized Korean-English CS** (Korea Univ., arXiv 2406.02562, Apr 2024)
  - Data: AI Hub "KECS" Korean-English code-switching set (3,502,911 train / 439,607 test utterances).
  - Whisper-small zero-shot WER 45.14 / CER 35.76 → full FT 29.95 / 15.28 → LoRA 33.58 / 17.60 (7.3M trainable params).
  - — [arXiv 2406.02562](https://arxiv.org/pdf/2406.02562)
- **FLEURS-ko error analysis**: most of turbo's errors (about 105/124 characters) came from utterances with digits or Latin text. Number and Latin-script formatting dominates Korean CER on technical-ish content — [PR #740](https://github.com/zkaelxz/U00/pull/740)
- **General finding**: fine-tunes damage multilingual ability. Every fine-tune in a 66-run large-v3 sweep was worse than base on FLEURS (58 languages; best 0.381 vs 0.305 CER). The Malay fine-tunes collapsed to over 1.0 typical CER on other languages — [Zolkepli, arXiv 2609.32560 (2026-09-26)](https://arxiv.org/html/2609.32560v1)

### Inferences
- Expect any Korean-only fine-tune, including batisay, to be weaker than base large-v3 on English technical terms spoken inside Korean. Two mechanisms are likely: (a) Hangul transliteration of English terms, and (b) loss of English capability. This is inferred from the Oh et al. and KAIST results. It has not been measured for batisay. KsponSpeech's labeling conventions may push fine-tunes toward Hangul spellings of English words; I found no source confirming this.
- For lecture transcription with many English terms (CS, engineering, medicine), the decision should rest on a small in-house test set that is code-switching-heavy. HiKE (academic and software-dev subsets) is the best public proxy and could be run against large-v3, turbo, batisay-ko-turbo and batisay-ko-large.
- A practical hybrid: run a Korean fine-tune for the bulk of the transcript, use prompt/hotword lists or LLM post-correction for technical terms, or do domain adaptation with TTS-synthesized lecture-term sentences (the KAIST recipe).

### Gaps
- No published code-switching evaluation for batisay, ghost613, SungBeom or any other Korean Whisper fine-tune.
- HiKE did not specify which "Whisper-Large" version it used, and it did not test large-v3-turbo.
- Whether batisay's training labels keep English words in Latin script or Hangul is undocumented.
- License for ghost613 and o0dimplz0o models is not stated, so commercial use is unclear.

---

## Q3. What is known about Whisper hallucination/repetition loops and the best mitigations (VAD, no-context, temperature fallback, compression-ratio checks, CrisperWhisper)?

### Takeaway
Whisper reliably emits text on non-speech. A 2026 study found every OpenAI checkpoint wrote something on 100% of its no-speech clips. large-v3 is widely reported to hallucinate more than v2, and turbo has far worse repetition-loop tails than large-v3 (p95 repeat ratio 18.3 vs 1.00). Defenses that work without retraining:
- Silero VAD gating before decoding (the single most cited fix)
- disabling previous-text conditioning (`condition_on_previous_text=False` / whisper.cpp `--max-context 0`)
- suppressing non-speech tokens
- keeping the default temperature fallback with entropy/compression and logprob thresholds
- bag-of-hallucinations post-filters
- repetition penalties / no-repeat-ngram (batisay bakes these in)

Research fixes (Calm-Whisper head fine-tuning; LoRA with non-speech negatives plus spoken positives; Whisper-CD contrastive decoding) cut hallucination substantially but are English-evaluated. CrisperWhisper 2.0 is non-commercial and not validated on Korean.

### Cited Findings
- **Frequency and harm**: about 1.4% of audio segments contained hallucinations (Whisper API, Spring 2023), and about 38% of those contained explicit harms. Hallucinations were more common for aphasic speakers, linked to longer non-speech pauses — [Careless Whisper, Koenecke et al., FAccT 2024, arXiv 2402.08021](https://arxiv.org/html/2402.08021v2)
- **Non-speech-induced hallucination** (Barański et al., ICASSP 2025): non-speech segments induce "a set of hallucinations that appear frequently". A "bag of hallucinations" (BoH) used for post-processing reduces WER — [arXiv 2501.11378](https://arxiv.org/abs/2501.11378). Search-snippet-only details (UNVERIFIED): the rate rises for files longer than 30 s, and beam size 1 gave the lowest rate — [ResearchGate](https://www.researchgate.net/publication/388232036_Investigation_of_Whisper_ASR_Hallucinations_Induced_by_Non-Speech_Audio)
- **2026 large-scale measurement** (Zolkepli, arXiv 2609.32560, 2026-09-26)
  - Every OpenAI checkpoint (large-v2, large-v3, large-v3-turbo) emitted something on 100% of no-speech benchmark clips.
  - large-v3 emitted words on 61.9% of room-tone clips. On 4,421 VAD-confirmed voice-free real clips, every OpenAI checkpoint wrote something.
  - **Repetition loops**: p95 ratio of emitted to true repeats was 1.00 for large-v3 vs **18.3 for turbo**.
  - 53.6% of large-v3's outputs on blank clips were phrases from a 40,891-phrase hallucination lexicon, so blocklists work only once a clip is known to be blank.
  - Best fix: LoRA r=64, lr 5e-4, on attention + MLP (fc1/fc2), trained on non-speech negatives plus synthetic spoken positives. Silence hallucination 61.9% → 2.4%; phrase recovery 69.8 → 82.7%; LibriSpeech WER 0.035 → 0.041. But FLEURS multilingual got worse.
  - Suppression-only training causes deletions (one fine-tune deleted 58% of repeated speech).
  - Decoder-side knobs (beam, temperature fallback) were not evaluated.
  - Benchmark/lexicon released at `Scicom-intl/Whisper-Hallucination`.
  - — [arXiv 2609.32560](https://arxiv.org/html/2609.32560v1)
- **Calm-Whisper** (Interspeech 2025): 3 of 20 decoder self-attention heads in large-v3 account for more than 75% of hallucinations on UrbanSound. Fine-tuning only those heads on non-speech data gives over 80% reduction in non-speech hallucination with less than 0.1% WER degradation on LibriSpeech. No released weights stated — [arXiv 2505.12969](https://arxiv.org/abs/2505.12969)
- **Whisper-CD** (Sungkyunkwan Univ., arXiv 2603.06193, 2026-03-06)
  - Training-free contrastive decoding against three negatives (noise, silence, temporal shift). English long-form only.
  - large-v3 greedy with previous-context: Earnings22 WER 520.94 → 57.08; TED-LIUM 66.42 → 25.62; REV-16 173.69 → 21.38.
  - Turbo: CORAAL 38.75 → 14.43; TED-LIUM 12.93 → 10.11.
  - Turbo RTF 0.0239 → 0.0346, still faster than beam search.
  - Temperature fallback disabled in experiments; no code link found.
  - These baseline WERs show how catastrophic loops get with greedy decoding plus context on long audio.
  - — [arXiv 2603.06193](https://arxiv.org/html/2603.06193v1)
- Search-snippet-only (UNVERIFIED, not fetched):
  - A mechanistic study reports that ablating head 13 in layer 18 suppressed repetition by 78.1% — [arXiv 2508.15882](https://arxiv.org/pdf/2508.15882)
  - "Hallucination Space Projection", a gated low-rank projection driven by the no-speech probability — [arXiv 2609.04561](https://arxiv.org/html/2609.04561)
- **Community reports on v3 vs v2**
  - v3 "hallucinates multiple times per 10 minutes" where v2 rarely did. A Japanese user estimated 1–3 hallucinations per 45-min video for v2 vs 5–10+ for v3, mostly in silent or music-only sections. One commenter attributes the stray text to credit notes in training transcripts — [discussion #1762](https://github.com/openai/whisper/discussions/1762)
  - For turbo, users call hallucinations and looping the biggest drawback, and suggest Silero VAD, trimming the file start and `--hallucination_silence_threshold` — [discussion #2363](https://github.com/openai/whisper/discussions/2363)
- **CrisperWhisper 1.0** (Interspeech 2024)
  - Adjusted tokenizer plus fine-tuning on noise/pause perturbations; timestamps from DTW on cross-attention.
  - On the AphasiaBank recordings Koenecke et al. flagged, it produced no harmful hallucinations but did produce repetitive loops on 10 recordings. The mitigation was removing tokens with duration under 50 ms.
  - English/German only.
  - — [arXiv 2408.16589](https://arxiv.org/pdf/2408.16589); [GitHub](https://github.com/nyrahealth/CrisperWhisper)
- **CrisperWhisper 2.0**
  - Sizes: large, turbo, medium, small (plus commercial-only Pro). Verbatim/intended modes across "most languages Whisper supports".
  - Benchmark covers 10 languages; only English and German use human-labeled sets. **Korean not mentioned.**
  - Anti-looping mitigation on by default, no numbers given.
  - Nyra Health **Non-Commercial Research License** for weights (inference code MIT).
  - Production runtime is CTranslate2 on NVIDIA; Transformers/PyTorch path for other platforms.
  - — [CrisperWhisper2.0_large card](https://huggingface.co/nyralabs/CrisperWhisper2.0_large)
- **whisper.cpp knobs and defaults** — [whisper.cpp CLI README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/examples/cli/README.md); [main README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/README.md)
  - `--suppress-nst` (default false)
  - `--max-context N` (default −1 = unlimited previous text)
  - `--entropy-thold` 2.40, `--logprob-thold` −1.00, `--no-speech-thold` 0.60
  - Temperature fallback: `--temperature-inc` 0.20, disable with `--no-fallback`
  - Beam size 5, best-of 5
  - Built-in Silero VAD: `--vad --vad-model …`, `silero-v6.2.0`; threshold 0.50, min speech 250 ms, min silence 100 ms, pad 30 ms, overlap 0.10 s
- **batisay recommended settings**
  - whisper.cpp: `--suppress-nst --max-context 0`, which the author says reduces repeated text and decoder collapse on long audio — [batisay-ko-turbo](https://huggingface.co/batiai/batisay-ko-turbo)
  - batisay-ko-large v1.1 generation_config bakes in suppress_tokens, `no_repeat_ngram_size=3`, `repetition_penalty=1.3`.
  - Long-form: q5_0 large degrades badly (CER 33.8% vs 19.2% q8_0), and a synthetic long-form test showed turbo-q5 7.9% vs large-f32 18.3%. Long-form large decoding appears more failure-prone.
  - — [batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)
- **faster-whisper**: Silero `vad_filter` is off by default for `WhisperModel.transcribe` (default removes silence over 2 s when on) and on by default in `BatchedInferencePipeline` — [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **WhisperX**: VAD preprocessing "reduces hallucination" and enables batching. `condition_on_prev_text` defaults to False to reduce hallucination — [WhisperX](https://github.com/m-bain/whisperX)
- **whisper-timestamped**: VAD options `silero` (default), `auditok`, `auditok:v3.1`. Notes that newer Silero versions can false-alarm on silence. `detect_disfluencies` marks fillers as `[*]` — [whisper-timestamped](https://github.com/linto-ai/whisper-timestamped)
- **ESPnet-converted Whisper on Korean** showed over 60% CER from failing to emit end-of-sequence, causing repeated insertions. Stand-alone Whisper inference did not — [Oh et al. 2023](https://www.eksss.org/archive/view_article?pid=pss-15-3-75)
- On clean read FLEURS-ko, 0 hallucinations in every configuration, and decoding-setting changes (beam 1, temperature fallback off, condition on previous text) moved CER by no more than noise — [PR #740](https://github.com/zkaelxz/U00/pull/740)

### Inferences
- Lectures are long-form, contain pauses, board-writing silences, Q&A gaps and room noise, which is exactly the regime where Whisper loops and hallucinates. A robust local pipeline for this app should be:
  1. Silero VAD segmentation (whisper.cpp `--vad`, or faster-whisper `vad_filter=True`)
  2. no previous-text conditioning (`--max-context 0` / `condition_on_previous_text=False`)
  3. `--suppress-nst`
  4. default temperature fallback with entropy/logprob/no-speech thresholds
  5. a Korean hallucination blocklist post-filter. Korean YouTube-style outro phrases are commonly reported anecdotally, but I found no source with a Korean list. The Scicom 100-language lexicon may contain them.
  6. n-gram repetition collapse
- Turbo-based models (including batisay-ko-turbo) need loop guards more than large-v3 does, given the 18.3 vs 1.00 p95 repetition ratio. The batisay author's own recommended flags are consistent with this.
- The repo's recent commits ("Detect and retry Whisper repetition loops in final transcripts") match the literature: retry with temperature or no-context on compression-ratio or repetition detection is the standard mitigation.
- CrisperWhisper is not a fit for a Korean product: non-commercial license, no Korean validation, CT2/NVIDIA-centric production path.

### Gaps
- No published Korean-specific hallucination study or Korean hallucination-phrase list was found. A Korean search returned nothing relevant.
- No head-to-head quantitative comparison of VAD vs no-context vs temperature fallback vs compression-ratio checks on the same data was found. The Zolkepli paper explicitly left decoder-side ablations as future work.
- Calm-Whisper and Whisper-CD weights or code availability is unconfirmed, and neither was tested on Korean.

---

## Q4. How good are Whisper word timestamps (whisper.cpp token timestamps, DTW, WhisperX forced alignment) for Korean?

### Takeaway
No Korean-specific word-timestamp accuracy benchmark was found. The options:
- **whisper.cpp**: experimental `-ml 1` word splitting and `--dtw` token timestamps. Turbo needed a separate alignment-head preset, and early builds broke.
- **whisper-timestamped**: DTW on cross-attention, AGPL, no published accuracy numbers.
- **WhisperX**: forced alignment with `kresnik/wav2vec2-large-xlsr-korean` for `ko`, treating Korean as space-delimited, so "words" are eojeol. Characters outside the aligner's vocabulary (digits, symbols and likely Latin letters) get no timing.
- **CrisperWhisper 2.0**: the best published boundary accuracy (about 30–41 ms), but only for English/German-labeled evaluations.

### Cited Findings
- **whisper.cpp** — [CLI README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/examples/cli/README.md); [main README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/README.md)
  - Word-level timestamps via `-ml 1` (marked experimental), `-sow/--split-on-word`, `-wt/--word-thold` 0.01
  - `-dtw MODEL` for token-level timestamps
  - `-ojf` full JSON output with token details
- **whisper.cpp DTW with turbo** (issue #2480): `--dtw large.v3` failed on large-v3-turbo ("tried to set alignment head on text layer 8, but model only has 4 text layers"). The reporter derived turbo heads {2,4},{2,11},{3,3},{3,6},{3,11},{3,14}. The issue was closed 2024-10-15 without a linked PR on the page — [issue #2480](https://github.com/ggml-org/whisper.cpp/issues/2480). A third-party doc says large-v3-turbo works properly only on whisper.cpp builds from November 2024 or later (search snippet) — [Remotion docs](https://www.remotion.dev/docs/install-whisper-cpp/transcribe)
- **WhisperX alignment for Korean** (source code) — [whisperx/alignment.py](https://raw.githubusercontent.com/m-bain/whisperX/main/whisperx/alignment.py)
  - Default align model `"ko": "kresnik/wav2vec2-large-xlsr-korean"`
  - `LANGUAGES_WITHOUT_SPACES = ["ja", "zh"]`, so Korean is split on spaces (eojeol-level words)
- **WhisperX limitations** — [WhisperX README](https://github.com/m-bain/whisperX)
  - Words with characters missing from the alignment dictionary (e.g., numbers with symbols) can't be aligned and get no timing
  - Overlapping speech isn't handled well
  - BSD-2-Clause; backend faster-whisper; README documents CUDA 12.8 and CPU
- The kresnik Korean wav2vec2-XLSR aligner reportedly scores 4.74% WER / 1.78% CER on Zeroth (secondary aggregator, UNVERIFIED) — [PromptLayer](https://www.promptlayer.com/models/wav2vec2-large-xlsr-korean)
- **whisper-timestamped**: DTW on cross-attention weights; no extra inference pass with greedy decoding; per-word confidence scores. It claims start/end estimation is "more accurate" than timestamp-token methods (whisper.cpp, stable-ts) but gives no benchmark numbers. Marked experimental. AGPL-3.0 (dtw-python GPL-3). No language-specific notes — [whisper-timestamped](https://github.com/linto-ai/whisper-timestamped)
- **faster-whisper**: `word_timestamps=True` yields `segment.words` — [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **CrisperWhisper**: its tokenizer change targets unsharp timestamps around pauses and disfluencies ([arXiv 2408.16589](https://arxiv.org/pdf/2408.16589)). 2.0 reports a mean word-boundary error of about 29.6 ms on TIMIT read speech and about 41 ms on conversational speech, but Korean is not mentioned ([CrisperWhisper 2.0 card](https://huggingface.co/nyralabs/CrisperWhisper2.0_large)). The paper notes that arbitrary selection of alignment heads is a weakness ([arXiv 2408.16589](https://arxiv.org/pdf/2408.16589)).
- A Korean user reports that large-series subtitles appear *earlier* than speech — [discussion #2363](https://github.com/openai/whisper/discussions/2363)
- batisay cards do not discuss timestamp behavior — [batisay-ko-turbo](https://huggingface.co/batiai/batisay-ko-turbo); [batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)

### Inferences
- For a lecture app (click-a-word-to-seek, segment-level sync), segment timestamps plus VAD boundaries are reliable enough. True word-level accuracy for Korean is unmeasured.
- WhisperX's Korean aligner likely cannot align English technical terms written in Latin script, because its vocabulary is Hangul characters, so code-switched words would lose timing. This is an inference from the "characters missing from dictionary" limitation and is unverified.
- Fine-tuned models (batisay, etc.) may shift cross-attention alignment heads. DTW presets tuned for the base model might degrade on fine-tunes (CrisperWhisper notes head selection is arbitrary). WhisperX's external aligner is model-agnostic, which is an advantage when using a fine-tune.
- whisper.cpp DTW on turbo-architecture fine-tunes (batisay-ko-turbo) needs the turbo head preset and a post-Nov-2024 build. Verify on the actual build.

### Gaps
- No quantitative Korean word-boundary error study (ms) for any method.
- Unconfirmed whether current whisper.cpp ships a named `large.v3.turbo` DTW preset (the issue page shows no linked PR).
- No information on how WhisperX handles Korean digits and English acronyms in practice, beyond the generic limitation.

---

## Q5. What LoRA/fine-tuning recipes exist for adapting Whisper to one speaker or domain, how much data is needed, and can a LoRA-tuned HF Whisper be converted to whisper.cpp ggml or CTranslate2?

### Takeaway
The standard recipe is HF Transformers + PEFT LoRA (r 16–64 on q/v or attention+MLP projections, optionally int8 base). It fits on 8–16 GB GPUs and produces adapters of about 60 MB. For one speaker, 2026 evidence says per-speaker LoRA adapters often do not beat a pooled adapter on typical speech (about 13–17 min/speaker tested). Gains concentrate where baseline errors are high, and full fine-tuning beats rank-8 LoRA by 15–39% relative in hard domains. Domain adaptation, via real or TTS-synthesized domain sentences (KAIST) or natural code-switch data (HiKE), produces large gains but erodes general/other-language accuracy. Conversion works: merge the adapter into a full HF model, then run `ct2-transformers-converter` (faster-whisper) or `convert-h5-to-ggml.py` (whisper.cpp) and quantize. batisay's GGUF releases prove the HF → ggml path for Korean large-v3/turbo fine-tunes.

### Cited Findings
- **HF PEFT int8 + LoRA recipe** (official task guide, PEFT v0.7.1) — [PEFT int8-asr guide](https://huggingface.co/docs/peft/v0.7.1/task_guides/int8-asr)
  - Base whisper-large-v2 loaded in 8-bit, then `prepare_model_for_int8_training`
  - `LoraConfig(r=32, lora_alpha=64, target_modules=["q_proj","v_proj"], lora_dropout=0.05)`: 15.7M of 1.56B trainable (1.01%)
  - lr 1e-3, batch 8, 3 epochs, fp16, warmup 50
  - Common Voice 11 Marathi
- Search-snippet-only (UNVERIFIED):
  - The PEFT 0.2.0 release notes say full fine-tuning OOM'd on a T4, while LoRA trained with a 60 MB checkpoint, WER 13.64 (full) vs 14.01 (LoRA) — [newreleases.io PEFT 0.2.0](https://newreleases.io/project/pypi/peft/release/0.2.0)
  - AWS reports 3 epochs on 12 h of Common Voice takes 6–8 h on an 8 GB-class GPU — [AWS blog](https://aws.amazon.com/blogs/machine-learning/fine-tune-whisper-models-on-amazon-sagemaker-with-lora)
- **Personalization evidence (2026)**: Katkov & Liotta, arXiv 2610.17019 (2026-10-17) — [arXiv 2610.17019](https://arxiv.org/html/2610.17019)
  - Setup: Whisper tiny–medium; LoRA on q/v, r=16, α=32, dropout 0.1; 200 utterances per Common Voice group and 80 per LibriSpeech/VoxPopuli group (≈13–17 min, my estimate from reported durations)
  - Pooled LoRA outperformed per-speaker LoRA on the hardest 10% of Common Voice groups for every model (medium: +6.66 vs +5.06 absolute WER gain)
  - VoxPopuli small: zero-shot 11.13 → pooled 8.65 vs personalized 10.37
  - LibriSpeech gains were negligible
  - Conclusion: personalization helps mainly for groups with high, stable baseline error, and should be tested against a matched pooled adapter
- **Data-quantity curve** (Huber, Kernahan & Waibel, KIT/CMU, arXiv 2606.31722, 2026) — [arXiv 2606.31722](https://arxiv.org/pdf/2606.31722)
  - Single dysarthric speaker, whisper-large-v3 baseline 128.4% WER
  - Full fine-tuning: 15.8% WER with 1.4 h of data; 10.7% (read) / 16.1% (corrections) with 22.5 h; 9.7% best; 7.8% with all read data (about 92 h)
  - LoRA rank 8 was 15–39% relative worse than full fine-tuning
  - Whisper was a stronger base than Qwen3-ASR-1.7B
- **Speaker adaptation (SAML, Interspeech 2024)**: about 6–10 min per speaker; 29.1% / 31.1% relative WER reduction on quantised Whisper / Conformer (search snippet; table not verified) — [SAML](https://www.isca-archive.org/interspeech_2024/zhao24d_interspeech.pdf)
- **Domain adaptation, Korean** (KAIST, arXiv 2410.18444 v3, 2025-09) — [arXiv 2410.18444](https://arxiv.org/pdf/2410.18444)
  - All fine-tuned models were parameter-efficient
  - TTS-synthesized domain text (Google TTS) fine-tuning cut domain-term CER from 18.35 to 10.64 (WeatherTest)
  - General-domain Kspon fine-tuning hurt domain terms
  - The combination recovered general CER (10.54) at a domain cost (17.46)
- **Korean code-switch adaptation**
  - HiKE: Whisper-Medium, 1 epoch, batch 16, lr 1e-5 on natural AIHub CS data: MER 31.3 → 9.0, Korean CER 3.4 → 6.0 — [HiKE v4](https://arxiv.org/html/2509.24613v4)
  - Gated LoRA paper: Whisper-small LoRA (7.3M params) reached CER 17.60 vs 15.28 for full FT on AI Hub KECS — [arXiv 2406.02562](https://arxiv.org/pdf/2406.02562)
- **LoRA design lessons** (2026): adapting MLP layers (fc1, fc2) mattered more than adding attention-only parameters; training loss ranked checkpoints backwards (unreliable for selection); every fine-tune hurt FLEURS multilingual — [arXiv 2609.32560](https://arxiv.org/html/2609.32560v1)
- **Korean full fine-tune data scale**
  - batisay-ko-large: about 5,000 h + 1,352 h — [card](https://huggingface.co/batiai/batisay-ko-large)
  - batisay-ko-turbo: about 4,300 h, with KsponSpeech replay each cycle to avoid forgetting — [card](https://huggingface.co/batiai/batisay-ko-turbo)
  - Oh et al.: medium on about 1,000 h Kspon in about 26 GPU-hours; large-v2 did not fit a 48 GB GPU for full FT in 2023 — [eksss.org](https://www.eksss.org/archive/view_article?pid=pss-15-3-75)
  - ghost613: about 207 h of Zeroth — [card](https://huggingface.co/ghost613/whisper-large-v3-turbo-korean)
- **Conversion to CTranslate2**: the faster-whisper README gives `ct2-transformers-converter --model <hub-id-or-local-dir> --output_dir … --copy_files tokenizer.json preprocessor_config.json --quantization float16` for "Transformers-compatible Whisper models (OpenAI or fine-tuned)" — [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- **Conversion to whisper.cpp ggml**: `python3 whisper.cpp/models/convert-h5-to-ggml.py <hf-model-dir> <openai-whisper-repo> <out-dir>`. HF models are in a "slightly different format compared to the original OpenAI format". Quantized variants (q5_0 etc.) are produced separately — [whisper.cpp models/README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/models/README.md)
- **Proof the path works for Korean fine-tunes**: BatiAI ships ggml q4_0/q5_0/q8_0/f32 builds of its large-v3 and turbo Korean fine-tunes for whisper.cpp — [batisay-ko-turbo](https://huggingface.co/batiai/batisay-ko-turbo); [batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)
  - Quantization sensitivity: large q5_0 degraded long-form CER (33.8% vs 19.2% at q8_0); q5_0 is about 98% and q4_0 about 96% of original accuracy on short-form — [batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)
- Community examples (search snippets, UNVERIFIED): an NbAiLab export script runs both ct2-transformers-converter and convert-h5-to-ggml.py on the same fine-tuned model ([NbAiLab export_models.sh](https://huggingface.co/NbAiLabBeta/nb-whisper-tiny/blame/00fb3d50d6dbcf5decb204bf23f7255f3f8bd83a/export_models.sh)). One user reported "completely unusable results" after convert-h5-to-ggml.py on a fine-tune ([HF discussion](https://huggingface.co/Sandiago21/whisper-large-v2-german-2/discussions/3)), so validate output after conversion.
- **Alternative to LoRA for Korean small models**: retraining Whisper-Small with a Korean-centric tokenizer on about 50K h gave CER 6.45 vs 18.05 for the original tokenizer (unnamed test set; commercial vendor claim) — [ENERZAi](https://enerzai.com/resources/blog/small-models-big-heat-conquering-korean-asr-with-low-bit-whisper)

### Inferences
- LoRA adapters must be merged into the base weights first (PEFT `merge_and_unload()`, then save a full HF checkpoint) before either converter can be used. Neither whisper.cpp nor CTranslate2 documentation fetched here describes loading separate LoRA adapters at inference. This is standard PEFT practice, but I did not fetch a primary doc confirming the merge API. Each per-speaker adapter therefore becomes a full model file (about 550 MB at turbo q5_0, about 1.1–1.7 GB for large).
- For this app, "adapt to one professor" is likely lower-value than "adapt to the lecture domain/terminology":
  - The 2026 personalization study shows pooled adapters usually match per-speaker ones on typical speech.
  - The KAIST result shows domain-term fine-tuning (even TTS-synthetic) cuts domain-term CER by about 40%.
  - A plausible recipe: LoRA (r 32–64, attention+MLP) on a Korean fine-tune or large-v3/turbo. Use a few hours of the target domain's lectures with corrected transcripts, plus TTS sentences containing course terminology, plus KsponSpeech/general replay to limit forgetting (batisay's replay strategy). Evaluate on a held-out lecture set and a code-switching set, not on training loss.
- Data needed (rough, from the cited studies): about 10–20 min per speaker yields small gains on already-good speech. About 1–2 h gives large gains when the baseline is badly mismatched. Tens of hours are needed to approach a plateau. Domain fine-tunes in Korean used 200 h (Zeroth) to 5,000+ h (batisay).
- Training needs a CUDA/ROCm PyTorch environment (bitsandbytes int8 historically CUDA-centric). Whether LoRA training is practical on Strix Halo is for the AMD-runtime researcher. Inference after merging and conversion can use whisper.cpp (Vulkan/HIP backends are listed in the README) or CTranslate2.

### Gaps
- No Korean-specific study on how many minutes of a single speaker's lectures are needed for measurable CER gains.
- No primary-source confirmation fetched for PEFT `merge_and_unload` usage with Whisper, or for whisper.cpp/CT2 lacking runtime LoRA support (stated as inference).
- CTranslate2 ROCm status was not checked here (left to the AMD-runtime researcher).
- No Korean streaming evaluation was found for any streaming wrapper. WhisperLiveKit and similar wrappers were not researched.

### Cited Findings (addendum: runtime paths and streaming, objective items not covered by a key question)
- Runtime-path notes only (not deep-dived):
  - whisper.cpp lists `-DGGML_VULKAN=1`, `-DGGML_HIP=1`, OpenVINO and AMD Ryzen AI NPU (`-DWHISPER_VITISAI=1`) backends ([README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/README.md))
  - faster-whisper and WhisperX READMEs document only CUDA and CPU ([faster-whisper](https://github.com/SYSTRAN/faster-whisper), [WhisperX](https://github.com/m-bain/whisperX))
  - CrisperWhisper 2.0's CT2 path is NVIDIA-only ([card](https://huggingface.co/nyralabs/CrisperWhisper2.0_large))
  - batisay ships ggml and MLX (MLX is Apple-only) and works in Transformers ≥4.57 ([batisay-ko-turbo](https://huggingface.co/batiai/batisay-ko-turbo))
- **Streaming / near-real-time options**:
  - whisper.cpp `whisper-stream` (SDL2) re-transcribes a sliding window, sampling every 0.5 s (`--step 500 --length 5000`) — [whisper.cpp README](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/README.md)
  - UFAL **SimulStreaming** (2025) merges the Simul-Whisper AlignAtt policy (cross-attention-guided, no fine-tuning) with the Whisper-Streaming interface. It supports large-v3 and beam decoding, and claims best-in-IWSLT-2025 simultaneous speech translation (self-claim). The older Whisper-Streaming uses LocalAgreement, re-processing the buffer each chunk, which is less efficient — [SimulStreaming GitHub](https://github.com/ufal/SimulStreaming); [CUNI IWSLT 2025 paper](https://arxiv.org/html/2506.17077v1)
  - OpenAI's streaming "GPT-Realtime-Whisper" (May 2026) is API-only, not local — [9to5Mac](https://9to5mac.com/2026/05/07/openai-has-new-voice-models-that-reason-translate-and-transcribe-as-you-speak/) (search snippet)
