# Korean ASR benchmarks, commercial Korean STT services, and ASR evaluation methodology (state as of 2026-11-01)

Notes compiled 2026-11-01. Every number carries the date of the source or measurement where one could be found. "Vendor self-reported" means the number comes from the company selling the product (or a repo it runs); "independent" means a third party ran it. Numbers from different sources are generally NOT comparable, because Korean CER moves by several points depending on normalization (spacing, punctuation, numbers, AI-Hub markup). See Q4.

## Q1. What are the best published Korean CER/WER numbers on KsponSpeech, Zeroth, Common Voice ko and FLEURS ko, by which models, and when?

### Takeaway
No official, maintained Korean ASR leaderboard exists (Open ASR / Artificial Analysis do not cover Korean). Read speech is close to saturated: FLEURS ko and Zeroth sit at about 2-4% CER for the best open models (Qwen3-ASR family, Whisper-large-v3 after normalization). Spontaneous KsponSpeech is still the discriminating set: the best numbers found are about 6.1/6.5% CER (eval-clean/eval-other) for a Korean fine-tune of Qwen3-ASR-1.7B under kocer normalization (2026), and 6.64/6.77% for Return Zero's commercial engine (vendor-run, Feb 2025). The best numbers depend heavily on the scoring rules.

### Cited Findings

**KsponSpeech (AI-Hub "한국어 음성", 969 h of spontaneous two-speaker dialogue, ETRI spelling transcription; eval-clean / eval-other)**
- Original corpus paper (Applied Sciences 10(19):6936, 2020): best Transformer + augmentation baseline about 8.7% CER eval-clean / 9.7% eval-other (another table in the same paper lists 8.0 / 9.0 for its best configuration). The authors proposed CER as the primary metric plus WER and a space-normalized WER. — [MDPI](https://www.mdpi.com/2076-3417/10/19/6936)
- SpeechBrain Conformer + Transformer LM (HF model card, undated): 7.33% eval-clean / 7.99% eval-other CER. — [Hugging Face, speechbrain](https://huggingface.co/speechbrain/asr-conformer-transformerlm-ksponspeech)
- Return Zero (ddwkim) Conformer + Transformer LM release (described as a 2024 release in search results): 7.40 / 7.96 CER. — [Hugging Face, ddwkim](https://huggingface.co/ddwkim/asr-conformer-transformerlm-ksponspeech)
- Community icefall streaming Zipformer transducer, 174M params, trained on KsponSpeech + about 6,500 h of AI-Hub data (2026, self-reported, from search snippet; eval-clean/other not separated): 7.16% offline best (with KenLM), 7.53% streaming (sherpa-onnx int8, chunk 64), scored without punctuation. — [Hugging Face, kangkyu](https://huggingface.co/kangkyu/icefall-asr-ko-streaming-zipformer-174m) (unverified: snippet only)
- KoSpeech toolkit (2020): 10.31% CER on KsponSpeech, acoustic model only. — [arXiv 2009.03092](https://arxiv.org/abs/2009.03092)
- Whisper large-v2 out of the box: 13.95% CER on the KsponSpeech eval set (Phonetics and Speech Sciences 15(3), Korean venue). — [eksss.org](https://www.eksss.org/archive/view_article?pid=pss-15-3-83)
- kocer benchmark (independent library by Choi Kwan-u, v0.5.x, 2026; normalized "kocer CER", greedy decoding, spelling references): TeamUNIVA/qwen3_asr_1.7b_ko 6.08 / 6.46; TeamUNIVA beta 6.80 / 7.23; Qwen/Qwen3-ASR-1.7B 8.69 / 8.57; BuzzASR/korean 10.06 / 9.29; openai/whisper-large-v3 11.06 / 11.85; SenseVoiceSmall 13.07-13.26 / 13.67-13.77. — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- KoALa-Bench (arXiv 2604.19782, v2 dated 2026-08-31; Chung-Ang Univ. + Upstage; large audio-language models prompted for transcription; punctuation removed, whitespace collapsed; average over 4 prompts): KsponSpeech-Clean / Other CER: Raon 8.16 / 7.81, Qwen3-Omni 8.58 / 8.15, Voxtral 67.83 / 63.15, Gemini-flash 83.19 / 45.14, GPT-audio >100 / 63.64, Gemma-3n >100 / >100. — [arXiv 2604.19782](https://arxiv.org/html/2604.19782)
- Return Zero's own API benchmark (measured Feb 2025, extended Aug 2025; 3,000 sampled sentences per set; vendor-run repo): Return Zero (VITO) 6.64 / 6.77; Return Zero fine-tuned Whisper 7.78 / 7.73; NAVER CLOVA Speech 8.05 / 7.96; AWS Transcribe 8.58 / 8.89; ETRI 9.99 / 7.15; Azure batch 10.26 / 9.56; Google API v2 11.82 / 11.59; OpenAI Whisper (API) 12.06 / 11.34; Gemini 2.0 Flash 18.41 / 14.48; Deepgram Nova-2 23.48 / 21.18. — [GitHub rtzr/Awesome-Korean-Speech-Recognition](https://github.com/rtzr/Awesome-Korean-Speech-Recognition) (commit history: "25년 2월 측정" committed 2025-04-10; "Add Azure, AWS, Deepgram results" 2025-08-15)

**Zeroth-Korean (read speech)**
- kocer (2026, normalized): TeamUNIVA qwen3_asr_1.7b_ko 2.32 (best); SenseVoiceSmall 2.40-2.41; TeamUNIVA beta 2.42; whisper-large-v3 2.90; Qwen3-ASR-1.7B 2.90; BuzzASR/korean 3.08. Raw (un-normalized) CER for whisper-large-v3 on the same Zeroth sample was 6.88%, i.e. normalization alone cut it to 2.90%. — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- KoALa-Bench (2026-08-31, clean / noisy): Qwen3-Omni 3.39 / 4.02 (best), Raon 4.28 / 5.27, GPT-audio 6.87 / 9.00, Gemini-flash 13.60 / 14.56, Voxtral 46.29 / 42.91. — [arXiv 2604.19782](https://arxiv.org/html/2604.19782)

**Common Voice ko**
- Qwen3-ASR Technical Report (arXiv 2601.21337, 2026-01-30; vendor self-reported, Table A.2(a), CER): Qwen3-ASR-Flash-1208 (API) 3.82, Qwen3-ASR-1.7B 5.88, Qwen3-ASR-0.6B 8.48. — [arXiv 2601.21337](https://arxiv.org/html/2601.21337v1)
- kocer (Common Voice 27, 2026, normalized): BuzzASR/korean 3.88 (best), whisper-large-v3 5.80, TeamUNIVA qwen3 ko 5.97, Qwen3-ASR-1.7B 6.61, SenseVoiceSmall 9.7. — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- KoALa-Bench (2026-08-31, clean / noisy): Raon 4.78 / 7.39 (best), Qwen3-Omni 4.99 / 7.02, Gemini-flash 13.74 / 26.74, GPT-audio 33.05 / 36.21. — [arXiv 2604.19782](https://arxiv.org/html/2604.19782)
- BuzzASR paper (arXiv 2609.09554, Sept 2026): on combined Common Voice + FLEURS Korean test data, Qwen3 baseline 7.39% CER and Cohere baseline 9.34%. — [arXiv 2609.09554](https://arxiv.org/pdf/2609.09554) (unverified: search snippet only; BuzzASR's own Korean number not captured)

**FLEURS ko**
- Qwen3-ASR Technical Report (2026-01-30; vendor self-reported, Table A.2(b), CER): Qwen3-ASR-Flash-1208 2.07, Qwen3-ASR-1.7B 2.57, Qwen3-ASR-0.6B 3.72. The report gives no per-language Korean numbers for Whisper-large-v3, GPT-4o-transcribe, Gemini or Doubao (only aggregates). — [arXiv 2601.21337](https://arxiv.org/html/2601.21337v1)
- kocer (2026, normalized, smaller subset): TeamUNIVA qwen3 ko 4.19, whisper-large-v3 4.24, Qwen3-ASR-1.7B 4.25, BuzzASR/korean 4.28, SenseVoiceSmall 6.8. Note the independent kocer figure for Qwen3-ASR-1.7B (4.25) is much higher than Qwen's self-reported 2.57, reflecting different normalization/subset. — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- "Back to Basics: Revisiting ASR in the Age of Voice Agents" (arXiv 2603.25727, March 2026, Boson AI incl. Mu Li and Alex Smola; WildASR): reported GPT-4o Transcribe at 4.0% CER on original (undegraded) Korean FLEURS audio. — [arXiv 2603.25727](https://arxiv.org/pdf/2603.25727) (unverified: from search snippet; the PDF could not be parsed in this session)
- ElevenLabs (vendor self-reported, undated Korean landing page): FLEURS Korean WER (word-level, not CER): Scribe v1 10.7%, Gemini Flash 2 12.1%, Whisper Large v3 18.1%, Deepgram Nova 2 18.4%. — [ElevenLabs](https://elevenlabs.io/speech-to-text/korean)
- AssemblyAI docs (multilingual table updated January 2026, vendor self-reported): Universal-2 FLEURS Korean WER 14.54%; Universal-3.5 Pro shows no Korean score. — [AssemblyAI benchmarks](https://www.assemblyai.com/docs/pre-recorded-audio/benchmarks.md)

**Other Korean sets seen in passing**
- Qwen3-ASR report: MLC-SLM ko (conversational) CER 8.09 (Flash-1208), 8.61 (1.7B), 10.31 (0.6B). — [arXiv 2601.21337](https://arxiv.org/html/2601.21337v1)
- kocer: AI-Hub phone/HR domain (1,936 utts): whisper-large-v3 4.97, BuzzASR/korean 5.31, TeamUNIVA qwen3 ko 5.69, Qwen3-ASR-1.7B 10.69, SenseVoiceSmall about 21.3. — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- Qwen3-ASR-1.7B Korean fine-tune GGUF card states Korean CER fell from 6.86% to 4.83% averaged across five Korean sets. — [Hugging Face Hamster/Qwen3-ASR-1.7B-ko-GGUF](https://huggingface.co/Hamster/Qwen3-ASR-1.7B-ko-GGUF) (third-party summary; unverified)

**Leaderboards**
- The Return Zero repo explicitly says it was created because no well-organized Korean CER leaderboard existed (papers report English WER on Papers with Code). — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- Artificial Analysis' STT leaderboard (AA-WER v2) is a weighted average of AA-AgentTalk (50%), VoxPopuli-Cleaned-AA (25%) and Earnings22-Cleaned-AA (25%), i.e. English; snapshots in 2026 show Scribe v2 (ElevenLabs) about 2.2%, MAI-Transcribe-1.5 about 2.4%, Fun-Realtime-ASR-preview about 1.7%. It says nothing about Korean. — [Artificial Analysis](https://artificialanalysis.ai/speech-to-text/non-streaming); [The Decoder](https://the-decoder.com/elevenlabs-and-google-dominate-artificial-analysis-updated-speech-to-text-benchmark/) (weights and figures from search snippets; methodology page not fetched)

### Inferences
- "Best published" by dataset (Nov 2026), with the caveat that the scoring rules differ: FLEURS ko about 2.1% CER (Qwen3-ASR-Flash API, self-reported) / about 2.6% (Qwen3-ASR-1.7B open weights, self-reported); Zeroth about 2.3% (TeamUNIVA Qwen3 ko fine-tune, kocer) / 3.4% (Qwen3-Omni, KoALa); Common Voice ko about 3.8-3.9% (Qwen3-ASR-Flash self-reported; BuzzASR/korean in kocer); KsponSpeech about 6.1 / 6.5% (TeamUNIVA Qwen3 ko, kocer, 2026) vs 6.64 / 6.77% (Return Zero commercial, vendor-run, Feb 2025).
- FLEURS and Zeroth are effectively saturated and barely separate models (kocer: four models within 4.19-4.28 on FLEURS). They are a poor guide for lecture audio. KsponSpeech and domain sets (meeting, lecture, phone) separate engines far better.
- Rankings flip by dataset: BuzzASR/korean is best on Common Voice but mid-pack on KsponSpeech; whisper-large-v3 is best on phone but worst-but-one on KsponSpeech (kocer). Each model tends to win on the data closest to its training set, which argues for testing on your own lecture audio.
- General-purpose audio LLMs (GPT-audio, Gemini-flash, Voxtral, Gemma-3n) score very badly on Korean transcription in KoALa-Bench (often >45% or even >100% CER on KsponSpeech). These appear to be instruction-following/runaway-output failures rather than acoustic errors, so they should not be read as the ceiling for the dedicated transcription endpoints of the same vendors.

### Gaps
- No Korean results found from the Open ASR Leaderboard (Hugging Face). From prior knowledge its multilingual track covers only a few European languages; not re-verified this session.
- No per-language Korean FLEURS numbers found from OpenAI (gpt-4o-transcribe / gpt-transcribe), Google (Chirp 2/3) or Microsoft in primary sources. OpenAI's launch post reportedly showed a per-language FLEURS chart, but no Korean value could be extracted.
- The Whisper paper's own Korean FLEURS/Common Voice WER values were not retrieved.
- Could not find exact eval-clean/eval-other numbers for ESPnet E-Branchformer KsponSpeech recipes. A Korean KoreaScience paper (about 7,500 h of AI-Hub data) reports E-Branchformer best among Conformer/Transformer but the numbers were not captured. — [KoreaScience](https://koreascience.or.kr/article/JAKO202431643645877.page?&lang=ko)
- The kocer benchmark's run date and exact subset sizes per dataset are not stated beyond 7,418 utterances in total.

## Q2. Are there Korean lecture/classroom-speech datasets or benchmarks (AI-Hub etc.) and results on them?

### Takeaway
Yes. AI-Hub hosts "한국어 강의 음성" (dataSetSn=115: EBS TV/radio and online lecture content, mostly a single speaker) and meeting corpora (회의 음성 dataSetSn=132, 주요 영역별 회의 음성 dataSetSn=464, KconfSpeech). But the only multi-engine results on the lecture set come from Return Zero's vendor-run benchmark (Feb 2025): CLOVA Speech 7.08%, Return Zero Whisper 7.11%, Return Zero 7.35%, AWS 9.33%, ETRI 9.89%, Azure 10.5%, Gemini 2.0 Flash 10.65%, Whisper API 10.89%, Google v2 11.48%, Deepgram Nova-2 21.48% CER. The newest independent Korean multi-speaker benchmark is meeting speech (KconfSpeech, Oct 2026), where CLOVA leads five engines.

### Cited Findings
- AI-Hub "한국어 강의 음성" (v1.1) is described as EBS TV/radio broadcast content and online lecture content suited to topic- and level-specific learning, mostly one speaker; in Return Zero's 3,000-sentence sample, average audio length is 4.69 (units not stated, presumably seconds) and 31.83 characters per segment. — [GitHub rtzr README](https://github.com/rtzr/Awesome-Korean-Speech-Recognition); dataset page [AI-Hub dataSetSn=115](https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=realm&dataSetSn=115)
- Other AI-Hub sets in the same benchmark: 주요 영역별 회의 음성 v1.1 (political debate, book clubs, online meetings, broadcasts, 3+ speakers; [dataSetSn=464](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=realm&dataSetSn=464)), 회의 음성 v1.0 (EBS debate/talk, 20-40 min per file; [dataSetSn=132](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=realm&dataSetSn=132)), 상담 음성 v1.2 (call centers; [dataSetSn=100](https://www.aihub.or.kr/aihubdata/data/view.do?&dataSetSn=100)), 저음질 전화망 음성 v1.1 ([dataSetSn=571](https://www.aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=realm&dataSetSn=571)). — [GitHub rtzr README](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- Return Zero benchmark, Korean lecture column (CER %, measured Feb 2025, 3,000 sentences, vendor-run): Naver CLOVA Speech **7.08** (bold best), Return Zero fine-tuned Whisper 7.11, Return Zero (VITO) 7.35, AWS Transcribe 9.33, ETRI 9.89, Azure batch STT 10.5, Gemini 2.0 Flash 10.65, OpenAI Whisper 10.89, Google API v2 11.48, Deepgram Nova-2 21.48. On the same benchmark, Return Zero is best on average (5.91) and on meetings, consultation and KsponSpeech; CLOVA averages 7.52. — [GitHub rtzr README](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- An earlier version of the same Return Zero benchmark on its blog lists different averages (Whisper 11.39, Return Zero 6.18, Return Zero Whisper 7.79), and a 2024-era version put CLOVA at 9.52%, so the table has been revised over time. — [RTZR blog](https://blog.rtzr.ai/korean-speechai-benchmark/); [Threads post quoting the older table](https://www.threads.com/@lunamoth/post/DE1rZEmpIvN?hl=ko)
- KconfSpeech meeting benchmark (AeCeCi, independent, calls made 2026-10-13; 1,000 clips from 180 sessions, 102.6 min, mean 6.2 s; seed 2026; Zenodo DOI 10.5281/zenodo.23584880). Mean CER raw → corrected-reference: CLOVA Speech (recognizer/upload long-form, with diarization and word alignment) 12.11 → 7.69; Azure Speech (conversation REST, ko-KR) 13.79 → 10.11; OpenAI whisper-1 16.32 → 12.84; Google STT v2 `latest_long` 16.75 → 13.00; AssemblyAI default 17.23 → 13.17. — [GitHub AeCeCi/STT-Meeting-CER-Benchmark](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- Same benchmark: AI-Hub annotation marks left in references made up 5.16% of reference characters; correcting them lowered every engine's CER but left the ranking within each set unchanged. A 20-clip pilot (2026-07-22) gave CLOVA 4.65, Google 6.70, Azure 5.76, Whisper 7.89, AssemblyAI 8.80 (corrected), and Google and Whisper swapped places between the 20-clip and 1,000-clip sets. — [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- AI_LectureNote (arXiv 2607.17237, 2026-07-19): pilot study of four author-recorded Korean-English medical lectures (282 reference sentences). Compared whisper-1 vs gpt-4o-transcribe (3-min chunks) plus LLM post-processing. English-script rendering of terms rose 0.39 → 0.71 (whisper-1) and 0.26 → 0.65 (gpt-4o-transcribe); semantic drift in 34 and 36 of 282 sentences; polarity failures in 11 and 13 of 101 rows. Authors conclude English-script rendering did not imply semantic faithfulness and recommend scoring surface accuracy, term-script rendering, chunk-level consistency and meaning preservation separately. No CER reported. — [arXiv 2607.17237](https://arxiv.org/abs/2607.17237)
- A Hugging Face dataset card lists "KlecSpeech" (lecture speech) among AI-Hub speech sources, governed by AI-Hub terms. — [HF SailAjou/S2ST-ko-hibiki](https://huggingface.co/datasets/SailAjou/S2ST-ko-hibiki) (unverified: snippet only; may be AI-Hub's internal name for the lecture corpus)
- AI-Hub data terms (via data.go.kr): commercial use of models trained on AI-Hub data is not restricted, but use of AI-Hub data must be acknowledged. — [data.go.kr](https://www.data.go.kr/data/15146383/fileData.do)

### Inferences
- On lecture audio, the top three (CLOVA 7.08, RTZR Whisper 7.11, RTZR 7.35) are within about 0.3 points, which is likely within normalization noise for a 3,000-segment sample. The benchmark is run by Return Zero, yet CLOVA still won the lecture column, which makes the "Korean vendors ≈ 7% vs global APIs ≈ 9-11%" gap on lecture speech fairly credible as of Feb 2025.
- The lecture segments are short (about 4.7 s), pre-segmented clips. Real lecture STT runs on 50-90 minute files, where segmentation, long-form drift, repetition loops and term handling (English technical terms) matter, and short-clip CER does not capture them. AI_LectureNote shows that term-script rendering and semantic drift need separate metrics.
- No public benchmark covers 2025-2026-generation commercial models on Korean lecture audio (gpt-4o-transcribe/gpt-transcribe, Scribe v2, Nova-3 ko, Chirp 3, Universal-3.x). A small in-house lecture test set is the only way to rank them.

### Gaps
- Could not open the AI-Hub dataset pages (JavaScript-rendered) to confirm total hours, number of lectures, subject coverage, or transcription rules (spelling vs pronunciation) for 한국어 강의 음성.
- No academic paper found that reports results on the AI-Hub lecture set apart from the vendor table. No classroom (teacher-student interaction) Korean corpus was found.
- AI-Hub "교육/강의" sets from later build years (e.g., subject-specific lecture speech) may exist but were not found in search.

## Q3. How do commercial Korean STT services compare in published or independent evaluations, and what features do they offer?

### Takeaway
On Korean, the domestic engines (Return Zero/VITO, NAVER CLOVA Speech) have led every published multi-vendor Korean CER comparison: Return Zero's own Feb-Aug 2025 table and the independent Oct 2026 KconfSpeech meeting benchmark, where CLOVA beat Azure, Whisper, Google v2 and AssemblyAI. Global vendors publish Korean numbers only as FLEURS WER or relative gains (ElevenLabs Scribe v1 10.7% WER, AssemblyAI Universal-2 14.54% WER, Deepgram Nova-3 "up to 27%" better than Nova-2). No independent test yet covers gpt-transcribe, Scribe v2, Nova-3 ko or Chirp 3 on Korean. Prices run from about ₩1,000/h (RTZR, T1) and $0.18-0.36/h (OpenAI gpt-4o-mini-transcribe / gpt-4o-transcribe) to $0.40/h (ElevenLabs list price).

### Cited Findings

**Comparative Korean evaluations**
- Return Zero table (Feb 2025; Azure/AWS/Deepgram added Aug 2025; vendor-run). Average CER over 7 AI-Hub sets: Return Zero 5.91, RTZR Whisper 6.59, CLOVA Speech 7.52, ETRI 10.19, Azure batch 10.88, AWS Transcribe 11.11, OpenAI Whisper 11.39, Google v2 11.50, Gemini 2.0 Flash 16.58, Deepgram Nova-2 21.02. Google's meeting result was skipped because of its 10 MB / 60 s synchronous limit. — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- Independent KconfSpeech meeting test (2026-10-13): CLOVA 7.69 < Azure 10.11 < whisper-1 12.84 < Google v2 latest_long 13.00 < AssemblyAI 13.17 (corrected-reference CER). Note that it tested whisper-1 (not gpt-4o-transcribe), Google `latest_long` (not Chirp 3) and AssemblyAI's default model. — [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- Independent paper (arXiv 2603.25727, Mar 2026): GPT-4o Transcribe 4.0% CER on clean Korean FLEURS. — [arXiv 2603.25727](https://arxiv.org/pdf/2603.25727) (unverified: search snippet only)
- KoALa-Bench (2026-08-31): OpenAI "GPT-audio" and "Gemini-flash" used as prompted audio LLMs gave 6.87% and 13.60% CER on Zeroth and >45% on KsponSpeech. These are chat/audio models, not the dedicated transcription endpoints. — [arXiv 2604.19782](https://arxiv.org/html/2604.19782)

**NAVER CLOVA Speech / CLOVA Note**
- CLOVA Speech offers short-form (단문, files ≤60 s), long-form (장문, file upload) and streaming recognition; automatic sentence segmentation with per-sentence timestamps (subtitle-oriented); timeline shift; batch jobs; web builder/editor; keyword boosting; Papago translation for streaming; Korean region. — [NCP guide](https://guide.ncloud-docs.com/docs/clovaspeech-overview)
- Speaker diarization is supported only in long-form recognition, not streaming. Billing is per recognized time (pay-as-you-go), with rates shown in the console. — [search summary of NCP docs](https://api.ncloud-docs.com/docs/ai-application-service-clovaspeech) (from snippet)
- Release note 2026-07-23: per-domain keyword-boosting ID and forbidden-word ID limits for streaming raised from 1 to 30. — [NCP release note](https://api.ncloud-docs.com/docs/ai-clovaspeech-longsentence-releasenote.md) (from snippet)
- In the KconfSpeech benchmark, the CLOVA long-form endpoint was called with word alignment and diarization requested, which shows that word-level alignment is available via API. — [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- NAVER markets CLOVA Speech as offering "the highest level of Korean recognition in Korea", including media and PSTN audio (vendor claim). — [ncloud.com](https://www.ncloud.com/product/aiService/clovaSpeech)

**Return Zero (RTZR / VITO, 비토)**
- Pricing (developers.rtzr.ai, fetched 2026-11-01; KRW, excl. VAT, progressive tiers, same for batch and streaming): T1 0-1,000 h/month ₩1,000/h; T2 1,000-10,000 h ₩500/h; T3 10,000-25,000 h ₩400/h; T4 >25,000 h ₩300/h. 10-second minimum per file/session; multi-channel bills summed channel time; 600 free minutes at signup. Batch models: `sommers`, `whisper`; streaming: `sommers_ko`, `sommers_ja`, `whisper`. — [RTZR pricing](https://developers.rtzr.ai/docs/pricing/)
- Batch results are retained for 3 days. — [RTZR docs](https://developers.rtzr.ai/docs/)
- Keyword boosting (word, weight tuples; negative weights allowed) is documented for streaming with `sommers_ko` only; `sommers_ko` is described as tuned for Korean telephone speech. — [LiveKit RTZR plugin docs](https://docs.livekit.io/reference/python/v1/livekit/plugins/rtzr/index.html); [Pipecat RTZR docs](https://docs.pipecat.ai/api-reference/server/services/stt/rtzr)
- Accuracy: best average CER (5.91) in its own benchmark; 7.35 on lectures (CLOVA 7.08). — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition) (vendor self-reported)

**OpenAI**
- Official pricing (fetched 2026-11-01): gpt-4o-transcribe $2.50/$10.00 per 1M input/output tokens ≈ $0.006/min; gpt-4o-mini-transcribe $1.25/$5.00 ≈ $0.003/min; gpt-4o-transcribe-diarize ≈ $0.006/min (transcription + diarization); Whisper $0.006/min; **gpt-transcribe $0.0045/min** (newer model); gpt-live-transcribe and gpt-realtime-whisper $0.017/min (live). — [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- No Korean-specific accuracy number from OpenAI found. The only Korean numbers are third-party (4.0% CER FLEURS, unverified) and the AI_LectureNote pilot (gpt-4o-transcribe used with 3-minute chunking on Korean-English medical lectures). — [arXiv 2607.17237](https://arxiv.org/abs/2607.17237)

**Google Cloud (Chirp 3)**
- Chirp 3 lists ko-KR as GA for StreamingRecognize, Recognize and BatchRecognize. Diarization is supported for ko-KR in batch (docs inconsistent on whether sync Recognize also works), not streaming. Word-level timestamps are available in Recognize/BatchRecognize but "some transcription degradation is expected". Speech adaptation (biasing) is GA, up to 1,000 phrases. Language-agnostic `auto` mode is GA. Denoiser cannot remove background voices. GA regions are `us` and `eu` multi-regions only. No Korean accuracy figures. — [Google Cloud Chirp 3 docs](https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3)
- STT V2 pricing "starts at $0.016/min" per a secondary source; no Chirp 3-specific rate verified. — [toolworthy](https://www.toolworthy.ai/en/tool/google-cloud-speech-to-text) (secondary, unverified)

**Deepgram Nova-3**
- Korean (`ko`, `ko-KR`) was added to Nova-3 in an 11-language expansion. Deepgram says Korean, Czech and Hindi saw the largest gains, up to 27% relative WER reduction vs Nova-2 (no absolute Korean WER). A 2026-08-04 changelog lists Korean among languages with improved batch and streaming models. — [Deepgram blog](https://deepgram.com/learn/deepgram-expands-nova-3-with-11-new-languages-across-europe-and-asia); [Deepgram changelog 2026-08-04](https://developers.deepgram.com/changelog/2026/8/4) (vendor; from snippets)
- Prior generation Nova-2 was worst in Return Zero's 2025 Korean table (21.02% avg CER). A 27% relative gain would put Nova-3 at about 15% on that benchmark (my extrapolation, untested). — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)

**ElevenLabs Scribe**
- Korean page (vendor): FLEURS Korean WER Scribe v1 10.7% vs Gemini Flash 2 12.1%, Whisper Large v3 18.1%, Deepgram Nova 2 18.4%. The FAQ places Korean in the "Good (>10% to ≤25% WER)" tier. Features: word-level (and character-level) timestamps, speaker diarization, audio-event tagging; files up to 300 MB; price $0.40/hour with enterprise discounts. — [ElevenLabs Korean STT](https://elevenlabs.io/speech-to-text/korean)
- Scribe v2 tops or nearly tops the English Artificial Analysis board in 2026 (about 2.2% AA-WER); no Korean figure for v2 found. — [Artificial Analysis](https://artificialanalysis.ai/speech-to-text/non-streaming)

**AssemblyAI**
- Universal-2 FLEURS Korean WER 14.54% (docs table updated January 2026). Universal-3.5 Pro has no Korean score (supports 18 languages, falls back to Universal-2 otherwise). AssemblyAI itself warns that public benchmarks can mislead and recommends evaluating on your own audio. — [AssemblyAI benchmarks](https://www.assemblyai.com/docs/pre-recorded-audio/benchmarks.md)
- Independent KconfSpeech: AssemblyAI default model last of five (13.17% corrected CER, Oct 2026). — [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- Universal-3.5 Pro Realtime listed at $0.62/h (Sept 2026) on a competitor's comparison page. — [Soniox compare page](https://soniox.com/compare-stt/soniox-vs-assemblyai/korean) (competitor-sourced)

**Microsoft Azure Speech**
- Return Zero table: Azure batch STT 10.88% avg, 10.5% on lectures (2025). Independent KconfSpeech: Azure conversation REST (ko-KR, koreacentral, clips ≤60 s) second of five at 10.11% corrected CER (Oct 2026). — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition); [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)

**Others**
- AWS Transcribe: 11.11% avg, 9.33% on lectures, strong on low-quality phone (7.59%) in Return Zero's table (Aug 2025). — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- ETRI: 10.19% avg, 9.89% on lectures (Feb 2025). — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- Soniox (stt-rt-v5) is listed at about $0.10-0.12/h (vendor page, June 2026). Soniox claims a Korean WER of 1.25% vs 1.74% for AssemblyAI from its own 2026 60-language study (vendor claim, not verified; the comparison page fetched shows no numbers). — [Soniox](https://soniox.com/compare-stt/soniox-vs-assemblyai/korean)
- Kakao: Return Zero's README lists Kakao among APIs "not yet tested". — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)

### Inferences
- For Korean lecture/meeting audio, the evidence (one vendor-run benchmark in 2025 and one independent one in 2026) consistently puts CLOVA Speech and Return Zero about 2-5 CER points ahead of the global APIs tested (Azure, AWS, Google v2, Whisper, AssemblyAI, Deepgram Nova-2). This is a reasonable "reference ceiling" for commercial Korean STT, at roughly 7% CER on AI-Hub lecture clips (2025).
- The 2025-2026 global models (gpt-4o-transcribe / gpt-transcribe, Chirp 3, Scribe v2, Nova-3 ko, Universal-3.x) are untested on Korean domain data in any public source found. They may have closed some of the gap (the FLEURS ko numbers of 2-4% CER for top models suggest strong read-speech Korean), so they must be included in an in-house test rather than assumed worse.
- Feature fit for lecture notes: word timestamps exist on CLOVA (word alignment), ElevenLabs, Chirp 3 (with caveats) and OpenAI whisper-1 verbose_json. Diarization is long-form/batch-only on CLOVA and Chirp 3, separate model on OpenAI (gpt-4o-transcribe-diarize). Custom vocabulary: CLOVA keyword boosting, Chirp 3 adaptation (≤1,000 phrases), RTZR boosting (streaming sommers_ko only per third-party docs), Deepgram keyterm prompting (per Nova-3 marketing; not verified for Korean).
- Cost per 90-minute lecture (list prices, before tiers): RTZR about ₩1,500; gpt-4o-mini-transcribe about $0.27; gpt-transcribe about $0.41; gpt-4o-transcribe about $0.54; ElevenLabs about $0.60 (my arithmetic from the cited rates).

### Gaps
- CLOVA Speech per-unit pricing (per 15 s / per hour) was not retrievable (rates live in the JS-rendered console/pricing calculator). CLOVA Note (consumer app) quotas and accuracy were not researched beyond the API.
- Azure Speech, AWS Transcribe and Google Chirp 3 current Korean pricing were not verified from primary pricing pages.
- Samsung: no public Korean STT API or published Korean accuracy found. Kakao: no current public STT API benchmark found (Kakao's former Newtone API status unknown).
- No independent Korean numbers for gpt-4o-transcribe beyond the unverified FLEURS snippet; none at all for gpt-transcribe, Scribe v2, Nova-3 ko, Chirp 2/3, Universal-3.x or Azure's 2026 models.
- Whether RTZR batch (`sommers`) supports diarization, word timestamps and keyword boosting was not confirmed from RTZR primary docs in this session.

## Q4. What is current best practice for normalizing Korean text before computing CER, and for measuring ASR hallucination and timestamp quality?

### Takeaway
Report both raw CER and a documented normalized CER. Normalize by NFKC, removing punctuation and all spaces (CER only), mapping numbers/English/units to the reading that minimizes CER (or verbalizing them), and resolving AI-Hub markup (dual notation `(A)/(B)`, noise tags). Under such normalization, 46-65% of raw "errors" vanish. Measure hallucination separately from CER (insertion rate, n-gram repetition rate, non-speech hallucination rate, and semantic/polarity checks). Measure timestamps as mean absolute boundary shift in ms (AAS) and/or the share of word boundaries within a collar. Measure speed as RTF or RTFx on the same hardware and file set.

### Cited Findings

**Why CER, and spacing**
- Korean is agglutinative with ambiguous word boundaries, so CER is preferred. Spacing-only differences can give 50% WER but 0% CER, e.g. "커피 한 잔 주세요" vs "커피 한잔 주세요". CER = (S+D+I)/N over characters. — [GitHub rtzr README](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- KsponSpeech authors proposed CER (primary), WER and a space-normalized WER for Korean. — [MDPI KsponSpeech](https://www.mdpi.com/2076-3417/10/19/6936)

**Normalization recipes in current use**
- kocer (2026): NFKC + zero-width removal; spaces removed for CER (kept for WER); punctuation removed; fillers (음, 어, 그) optional, off by default; English acronyms/units read as Korean ("AI" → 에이아이, "50%" → 오십 퍼센트) with custom aliases; numbers expanded into candidate readings (as written, Sino-Korean, native Korean, digit-by-digit), choosing the lowest-CER match guided by a counter-word dictionary; AI-Hub dual notation `(7시)/(일곱 시)` both accepted with `dual`; AI-Hub noise tags removed with `aihub=True` (masking tags like `@이름1` kept); raw CER always reported alongside. Scoring rules frozen since v0.5.0. `breakdown()` splits errors into spacing / punctuation / numbers-English / real errors (example: 40% / 13% / 15% / 32%). — [GitHub kocer](https://github.com/Choi-kwan-u/kocer); [PyPI kocer](https://pypi.org/project/kocer/0.3.0/)
- kocer finding: across Zeroth/FLEURS/Common Voice, 46-65% of raw CER errors were notation differences. whisper-large-v3 on Zeroth went from 6.88% raw to 2.90% normalized. — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- KconfSpeech benchmark: "raw" pipeline = lowercase, remove whitespace, keep only `[0-9a-z가-힣]`. "Corrected" = in references, dual notation `(A)/(B)` keeps A, non-speech marks `b/ n/ l/ o/ u/` deleted, remaining slashes → spaces; hypotheses untouched. Markup was 5.16% of reference characters. — [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- KoALa-Bench: remove punctuation and collapse whitespace before character edit distance. — [arXiv 2604.19782](https://arxiv.org/html/2604.19782)
- The Return Zero benchmark notes that datasets differ in how they mark noise, laughter and dual transcriptions, and that this must be preprocessed for fair comparison; it chose mainly spelling-transcribed (철자전사) sets because Whisper/Google output spelling. Exact preprocessing is not published. — [GitHub rtzr README](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)
- Qwen-Audio-3.0-ASR computes CER following the normalization/scoring protocol in Fun-ASR PR #165. — [arXiv 2609.07549](https://arxiv.org/pdf/2609.07549) (from snippet)
- A Korean ASR error-audit repo reports that the two worst-CER utterances were reference/audio mismatches, half of raw edits were formatting, and meaning flips can hide under low CER. — [GitHub jigonyoo/ko-asr-error-audit](https://github.com/jigonyoo/ko-asr-error-audit) (from repo description only)

**Hallucination / repetition metrics**
- Distil-Whisper reports repeated 5-gram duplicates ("5-Dup.") and insertion error rate (IER) on long-form sets; distil-large-v2 had 1.3× fewer repetition errors than Whisper large-v2. — [arXiv 2311.00430](https://arxiv.org/pdf/2311.00430) (from snippet)
- Calm-Whisper (Interspeech 2025): IER is the common hallucination metric on speech; for non-speech audio it uses a per-clip binary rate (any non-empty output = hallucination). Whisper-large-v3 hallucinated on 99.97% of non-speech clips vs 13.52% for a Conformer-CTC model. — [ISCA archive](https://www.isca-archive.org/interspeech_2025/wang25b_interspeech.pdf) (from snippet)
- "Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio" (arXiv 2501.11378): commonly used metrics such as WER cannot differentiate hallucinatory from non-hallucinatory models. — [arXiv 2501.11378](https://arxiv.org/pdf/2501.11378) (from snippet)
- "From Text Metrics to Model Internals" (arXiv 2606.23060, 2026): evaluates WER, CER, IER, 5-gram repetition rate, stopword ratio and GPT-2 perplexity as Whisper-large-v3 hallucination detectors. Text classifiers get high recall but degrade without reference transcripts. — [arXiv 2606.23060](https://arxiv.org/html/2606.23060v1) (from snippet)
- kocer: no hallucination handling. BuzzASR's recommended repetition-suppression setting made CER worse on all five datasets, so anti-repetition decoding settings must themselves be A/B tested. — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- KoALa-Bench flags CER >100% cells (runaway/looping output) for several audio LLMs on Korean. — [arXiv 2604.19782](https://arxiv.org/html/2604.19782)
- AI_LectureNote measures semantic drift (sentence counts) and polarity failures (negation flips) separately from surface accuracy, a meaning-level complement to CER for lecture content. — [arXiv 2607.17237](https://arxiv.org/abs/2607.17237)

**Timestamp accuracy metrics**
- Qwen3-ASR report defines Accumulated Average Shift (AAS): mean absolute difference between predicted and reference timestamps over all timestamp slots (ms; references from Montreal Forced Aligner or human labels). Korean, Qwen3-ForcedAligner-0.6B: 37.2 ms (MFA-labeled raw), 42.2 ms (concatenated 300 s audio). Human-labeled multilingual average 32.4 ms. Monotonic-Aligner, NeMo Forced Aligner (NFA) and WhisperX did not support Korean in that comparison. — [arXiv 2601.21337](https://arxiv.org/html/2601.21337v1)
- Google notes that enabling word-level timestamps on Chirp 3 can degrade transcription ("some transcription degradation is expected"), so timestamp and CER runs should use the same settings. — [Google Chirp 3 docs](https://docs.cloud.google.com/speech-to-text/docs/models/chirp-3)
- WhisperX (Bain et al., Interspeech 2023) evaluates word timestamps as word-segmentation precision/recall, where a word counts as correct if its boundaries fall within a collar (200 ms) of the reference. — [arXiv 2303.00747](https://arxiv.org/abs/2303.00747) (from prior knowledge; not re-fetched this session)

**Speed (real-time factor)**
- Artificial Analysis reports a "speed factor" (seconds of audio processed per second) for STT providers. — [Artificial Analysis speed view](https://artificialanalysis.ai/speech-to-text/non-streaming?speed=speedFactor); [Smallest.ai explainer](https://smallest.ai/blog/pulse-asr-artificial-analysis-speed-factor) (from snippets)
- Convention (from prior knowledge, not re-verified): RTF = processing time / audio duration (lower is better); the Hugging Face Open ASR Leaderboard reports the inverse, RTFx = audio duration / processing time (higher is better). — [HF Open ASR Leaderboard](https://huggingface.co/spaces/hf-audio/open_asr_leaderboard)

**Building a small in-house test set (practices visible in the sources)**
- Sample per session/recording rather than per clip, with a fixed seed. Exclude items used in pilots. Log call dates, endpoints, models and parameters. Keep raw responses. Re-runs on different dates can shift results (AssemblyAI 8.70 → 8.80 between calls). — [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- Report raw CER and normalized CER together, plus an error-type breakdown (spacing / punctuation / numbers-English / real). — [GitHub kocer](https://github.com/Choi-kwan-u/kocer)
- Audit references: the worst-CER items are often reference/audio mismatches. — [GitHub jigonyoo/ko-asr-error-audit](https://github.com/jigonyoo/ko-asr-error-audit)
- 3,000 sentences per domain was Return Zero's cost/time compromise. The independent study found that 20 clips vs 1,000 clips flipped the Google/Whisper order, so tiny sets are unstable. — [GitHub rtzr](https://github.com/rtzr/Awesome-Korean-Speech-Recognition); [GitHub AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)
- Vendors themselves (AssemblyAI) recommend evaluating on your own audio because public benchmarks can mislead. — [AssemblyAI benchmarks](https://www.assemblyai.com/docs/pre-recorded-audio/benchmarks.md)
- For lectures with English technical terms, score term-script rendering and meaning preservation (semantic drift, polarity) separately from CER. — [arXiv 2607.17237](https://arxiv.org/abs/2607.17237)

### Inferences
- Suggested protocol for choosing a lecture STT engine from human-corrected CLOVA-Note-style transcripts (synthesis of the above, not a published standard):
  1. Take 10-20 full lectures (not clips) across subjects and speakers. Re-align corrected transcripts to audio at segment level, and hold out whole lectures.
  2. Freeze a normalizer (kocer or an equivalent: NFKC, strip punctuation/spaces for CER, number/English alias handling).
  3. Report raw CER, normalized CER, error-type breakdown, WER-with-spacing (for readability), IER, 5-gram repetition rate on the hypothesis, and a "loop" flag (e.g., hypothesis length / reference length > 1.5 per segment).
  4. Score timestamps as AAS (ms) and % of word boundaries within 200 ms against a forced alignment of the corrected text (note that WhisperX/NFA lacked Korean in Qwen's test; Qwen3-ForcedAligner or MFA Korean can produce references).
  5. Measure RTF/RTFx on the same hardware with wall-clock end-to-end time, including upload/queue for cloud APIs.
  6. Report a domain-term list hit rate (keyword recall) to test custom-vocabulary features.
- Because human-corrected transcripts derived from one engine's output (e.g., CLOVA Note) bias the reference toward that engine's spacing, punctuation and number style, normalization that removes spacing/punctuation and canonicalizes numbers is especially important for fairness. This is an inference; no source quantified the bias.
- Whisper-family models (including fine-tunes) are known to loop and hallucinate on non-speech, so lecture tests should include pauses, music, Q&A and silence. CER alone will hide these failures (2501.11378).

### Gaps
- No published Korean-specific timestamp benchmark across commercial APIs was found (only Qwen's aligner numbers).
- No Korean-specific hallucination benchmark was found. Hallucination metrics found are English or multilingual Whisper studies.
- No formal standard (e.g., from TTA or the 한국음성학회) for Korean CER normalization was found. kocer is a single-author open-source tool, not a community standard.
- The RTF/RTFx and WhisperX collar definitions are given from prior knowledge and were not re-fetched in this session.
