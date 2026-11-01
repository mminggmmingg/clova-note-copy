# Qwen3-ASR 조합이 Whisper Large-v3에 먼저 도전한다

2026년 11월 기준, Local Clova의 다음 ASR 엔진으로 가장 먼저 로컬 벤치마크에 올릴 후보는 **Qwen3-ASR-1.7B(특히 TeamUNIVA의 한국어 파인튜닝판)와 Qwen3-ForcedAligner-0.6B 조합**이다. 같은 정규화 규칙으로 잰 독립 벤치마크에서 이 한국어 파인튜닝판은 KsponSpeech 자발화 CER을 **6.08/6.46%**로 낮췄다. 같은 표의 Whisper Large-v3는 11.06/11.85%였다. 정렬기는 한국어 단어 경계 오차 **37.2 ms**라는, 후보 가운데 유일한 공개 한국어 타임스탬프 수치를 갖고 있다. 2순위는 지금의 whisper.cpp 서버에 그대로 꽂히는 **BatiSay-ko-turbo/large v1.1**, 3순위는 공개 한국어 수치가 가장 좋은 **NVIDIA Nemotron 3.5 Transcribe 30B-A4B**(FLEURS-ko CER 2.78%)다. Nemotron은 gfx1151에서 돌아가는지부터 확인해야 한다. 4순위는 프리뷰 전용 **Nemotron 3.5 ASR Streaming 0.6B**다. 어떤 공개 수치도 이 앱의 조건, 즉 노트북 마이크로 녹음한 1–2시간짜리 단일 화자 강의에 영어 용어와 수식이 섞인 음성을 재지 않았다. 게다가 같은 Whisper Large-v3의 KsponSpeech CER이 출처에 따라 11%에서 23%까지 흔들린다. 그래서 최종 판정은 사용자가 교정한 세그먼트로 직접 내려야 한다. 실제 병목은 모델보다 런타임이다. Linux gfx1151에서 ASR이 검증된 경로는 whisper.cpp HIP와 CTranslate2 ROCm뿐이다. Qwen3-ASR, Nemotron, VibeVoice를 이 칩의 PyTorch ROCm이나 vLLM에서 돌렸다는 보고는 하나도 없다. 상용 API의 천장은 한국어 강의 클립 기준 CER 약 7%(CLOVA Speech, 리턴제로)이고, 공개 가중치의 한국어 파인튜닝 모델은 적어도 KsponSpeech에서는 그 수준에 이미 닿았다.

## 같은 Whisper Large-v3가 출처에 따라 CER 11%에서 23%까지 움직인다

한국어 ASR 수치를 읽기 전에 정규화 문제부터 짚어야 한다. 띄어쓰기, 숫자 표기("7시"와 "일곱 시"), 영어 표기("AI"와 "에이아이"), AI-Hub의 이중 전사 표기 때문에 **같은 모델의 같은 테스트셋 CER이 두 배 이상 차이 난다**. kocer는 Zeroth, FLEURS, Common Voice에서 원시 CER 오류의 **46–65%가 표기 차이**라고 집계했다. 실제로 Whisper Large-v3의 Zeroth CER은 원시 6.88%에서 정규화 후 2.90%로 떨어진다 ([kocer](https://github.com/Choi-kwan-u/kocer)). 그러니 출처가 다른 두 수치를 나란히 놓고 우열을 가리면 안 된다.

| 모델 / 테스트셋 | CER | 출처와 채점 방식 |
|---|---|---|
| Whisper Large-v3 / KsponSpeech eval-clean | 11.06 | kocer: NFKC, 공백·문장부호 제거, 숫자·영어 별칭 허용 ([kocer](https://github.com/Choi-kwan-u/kocer)) |
| 〃 | 약 12 | BatiSay 카드의 "raw" 수치 ([batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)) |
| 〃 | 18.00 | OpenKoASR: Kspon 정규화, CER 100% 초과 샘플 제외 ([OpenKoASR](https://raw.githubusercontent.com/GT-KIM/open-korean-automatic-speech-recognition/main/leaderboard.md)) |
| 〃 | 23.12 | 같은 저장소의 legacy 실행 ([OpenKoASR repo](https://github.com/GT-KIM/open-korean-automatic-speech-recognition)) |
| Qwen3-ASR-1.7B / FLEURS-ko | 1.42 | TeamUNIVA: TN/ITN 참조 중 유리한 쪽 채택 ([TeamUNIVA](https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko)) |
| 〃 | 2.57 | Qwen 기술보고서, 자체 보고 ([arXiv 2601.21337](https://arxiv.org/html/2601.21337)) |
| 〃 | 4.25 | kocer ([kocer](https://github.com/Choi-kwan-u/kocer)) |

공정한 비교는 한 표 안에서만 가능하다. 공개 모델 여러 개를 같은 규칙으로 잰 가장 넓은 표가 kocer다. 이 표를 보면 데이터셋에 따라 순위가 뒤집힌다는 사실이 바로 드러난다.

| kocer 정규화 CER (%) | Kspon clean | Kspon other | AI-Hub 전화 | CV27 ko | FLEURS ko | Zeroth |
|---|---|---|---|---|---|---|
| TeamUNIVA qwen3_asr_1.7b_ko | **6.08** | **6.46** | 5.69 | 5.97 | 4.19 | **2.32** |
| Qwen3-ASR-1.7B | 8.69 | 8.57 | 10.69 | 6.61 | 4.25 | 2.90 |
| BuzzASR/korean (Whisper-v3 파인튜닝) | 10.06 | 9.29 | 5.31 | **3.88** | 4.28 | 3.08 |
| Whisper Large-v3 | 11.06 | 11.85 | **4.97** | 5.80 | 4.24 | 2.90 |
| SenseVoiceSmall | 약 13.1 | 약 13.7 | 약 21.3 | 9.7 | 6.8 | 2.40 |

출처: [kocer](https://github.com/Choi-kwan-u/kocer)

이 표에서 읽을 것은 세 가지다. 첫째, FLEURS와 Zeroth 같은 낭독 음성은 포화됐다. 네 모델이 FLEURS에서 4.19–4.28 사이에 몰려 있어 엔진을 가려내지 못한다. 둘째, 강의에 가장 가까운 자발화(KsponSpeech)에서는 **Qwen3 계열이 Whisper Large-v3보다 일관되게 낫다**. OpenKoASR도 같은 방향이다. Kspon clean에서 Qwen3-ASR-1.7B는 16.26, Large-v3는 18.00, turbo는 19.53이었다 ([OpenKoASR](https://raw.githubusercontent.com/GT-KIM/open-korean-automatic-speech-recognition/main/leaderboard.md)). 셋째, **저음질 전화 음성에서는 Qwen3-ASR이 크게 무너진다**. kocer에서 10.69 대 4.97, OpenKoASR 저음질 전화망에서 19.91 대 10.63이다 ([OpenKoASR](https://raw.githubusercontent.com/GT-KIM/open-korean-automatic-speech-recognition/main/leaderboard.md)). 노트북 마이크로 강의실을 원거리 녹음한 음성은 8 kHz 협대역 전화도 아니고 깨끗한 자발화도 아니다. 이 열화 민감성이 강의실 잔향에서 어떻게 나타날지는 공개 자료로 알 수 없고, 로컬 측정으로만 확인할 수 있다.

상용 API의 천장도 같은 주의를 붙여 읽어야 한다. 리턴제로가 직접 운영한 벤치마크(2025년 2월 측정)의 AI-Hub "한국어 강의 음성" 열에서는 **CLOVA Speech 7.08, 리턴제로 Whisper 7.11, 리턴제로 7.35**가 상위권이었다. 그 아래로 AWS 9.33, Azure 10.5, OpenAI Whisper API 10.89, Google v2 11.48이 이어졌다 ([rtzr 벤치마크](https://github.com/rtzr/Awesome-Korean-Speech-Recognition)). 판매사가 돌린 표인데도 경쟁사 CLOVA가 강의 열 1위를 차지했다는 점이 이 표의 신뢰도를 높인다. 2026년 10월의 독립 회의 음성 벤치마크 KconfSpeech에서도 CLOVA가 교정 참조 기준 **7.69%**로 Azure 10.11%와 whisper-1 12.84%를 앞섰다 ([AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)). 공개 가중치 쪽 TeamUNIVA 파인튜닝판의 Kspon 6.08/6.46(kocer)은 리턴제로 자체 측정치 6.64/6.77과 비슷한 범위다. 채점 규칙이 달라 직접 비교는 할 수 없지만, "로컬 모델은 상용보다 한참 못하다"는 2024년의 상식은 KsponSpeech 기준으로 더 이상 맞지 않는다. 2025–2026년 세대의 글로벌 API(gpt-transcribe, Scribe v2, Chirp 3, Nova-3 ko)는 한국어 도메인 데이터로 독립 검증된 적이 없다. 참고로 가격은 OpenAI gpt-transcribe가 분당 $0.0045, 리턴제로가 시간당 ₩1,000부터다 ([OpenAI 가격](https://developers.openai.com/api/docs/pricing); [RTZR 가격](https://developers.rtzr.ai/docs/pricing/)).

## 한국어를 실제로 지원하는 공개 모델은 손에 꼽힌다

### Qwen3-ASR 계열은 자발화 한국어에서 앞서지만 열화 음성에 약하다

Qwen3-ASR(2026-01-29 공개, Apache-2.0)는 0.6B와 1.7B 두 크기이고 한국어를 공식 지원한다. 300M AuT 인코더에 1–8초 동적 어텐션 창을 써서 스트리밍과 오프라인을 한 모델로 처리한다 ([Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR); [arXiv 2601.21337](https://arxiv.org/html/2601.21337)). 자체 보고 한국어 CER은 1.7B 기준 FLEURS 2.57, CommonVoice 5.88, 대화체 MLC-SLM 8.61이다 ([arXiv 2601.21337](https://arxiv.org/html/2601.21337)). 더 의미 있는 것은 커뮤니티 파인튜닝이다. **TeamUNIVA qwen3_asr_1.7b_ko**(Apache-2.0)는 KsponSpeech를 8.65에서 5.94로 낮추면서도 **LibriSpeech 영어 WER은 2.50에서 2.77로 거의 그대로**였다 ([TeamUNIVA](https://huggingface.co/TeamUNIVA/qwen3_asr_1.7b_ko)). 영어 기술 용어가 잦은 강의에서는 이 점이 결정적일 수 있다. 다음 절에서 보듯 Whisper 한국어 파인튜닝은 영어 능력을 크게 잃었기 때문이다. 이 파인튜닝판의 GGUF 변환본도 제3자가 올려 두었다 ([Hamster GGUF](https://huggingface.co/Hamster/Qwen3-ASR-1.7B-ko-GGUF)).

사용자가 예전에 쓴 Qwen3-ASR 경로는 이번에 권하는 경로와 다르다. 저장소의 V8.2-delta 어댑터는 Qwen3-ASR의 **네이티브 스트리밍 런타임**을 감쌌고, vLLM을 MIOpen을 끈 채로 띄웠다 ([로컬 어댑터](../asr/engines/qwen3_asr.py); [로컬 vLLM 런처](../vllm_no_miopen.py)). 공식 스트리밍 경로에는 세 가지 문제가 있다. 매 청크마다 세션 시작부터 쌓인 오디오를 통째로 다시 넣는 "의사 스트리밍"이라 긴 세션일수록 느려진다 ([issue #148](https://github.com/QwenLM/Qwen3-ASR/issues/148)). 타임스탬프를 반환하지 않는다 ([README](https://github.com/QwenLM/Qwen3-ASR)). 그리고 vLLM 0.17.1에서는 "약 10개 파일 중 1개"가 토큰 반복에 빠졌다는 보고가 해결 없이 닫혔다 ([issue #129](https://github.com/QwenLM/Qwen3-ASR/issues/129)). Transformers 백엔드에도 버그가 있다. FA2가 없으면(SDPA 기본값) **8초가 넘는 입력에 학습 때와 다른 전체 어텐션이 적용된다**. 수정 PR #103은 2026년 2월부터 열려 있다 ([issue #213](https://github.com/QwenLM/Qwen3-ASR/issues/213); [PR #103](https://github.com/QwenLM/Qwen3-ASR/pull/103)). 이 앱의 세그먼트는 1–28초라 대부분 이 버그 구간에 든다. 예전 실험이 실망스러웠다면 원인의 일부가 모델이 아니라 이런 경로 문제였을 수 있다. 재시험은 세그먼트별 오프라인 추론에 PR #103을 적용하거나, 2026-06-26 추가된 네이티브 Transformers 통합(`-hf` 체크포인트, 이 버그 해당 여부는 미확인)을 써서 해야 한다.

### Whisper 한국어 파인튜닝은 한국어를 얻고 영어 용어를 잃는다

OpenAI는 2024년 10월 turbo 이후 공개 Whisper 가중치를 내지 않았고, 2025–2026년 신모델은 모두 API 전용이다 ([openai/whisper #2363](https://github.com/openai/whisper/discussions/2363); [9to5Mac](https://9to5mac.com/2026/05/07/openai-has-new-voice-models-that-reason-translate-and-transcribe-as-you-speak/)). 한국어 파인튜닝 가운데 2026년에도 버전을 올리며 관리되는 계열은 BatiAI의 **batisay** 하나다. ko-large v1.1(2026-07-05, large-v3 기반 1.55B)은 자체 "strict" 정규화로 Kspon eval_clean 6.83, eval_other 8.01, AI-Hub 회의 7.13을 보고했다. 학습 데이터에는 **AI-Hub 강의 음성(115)**이 포함됐지만, 강의 도메인 테스트 결과는 공개하지 않았다 ([batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)). ko-turbo v1.1(809M)은 6.99/8.33으로 large와 거의 같고, q5_0 GGUF가 548 MB다 ([batisay-ko-turbo](https://huggingface.co/batiai/batisay-ko-turbo)). 라이선스는 BatiAI Community License v2.0이다. 개인, 학술, 사내 사용은 무료이고, 외부 SaaS와 임베디드 제품은 별도 협상이 필요하다.

문제는 영어다. Whisper medium을 KsponSpeech 약 1,000시간으로 파인튜닝하자 **LibriSpeech-other WER이 6.74에서 57.56으로** 무너졌다 ([Oh, Kim & Park 2023](https://www.eksss.org/archive/view_article?pid=pss-15-3-75)). KAIST 연구에서는 large-v2를 일반 KsponSpeech로 파인튜닝하자 일반 CER은 14.66에서 10.48로 좋아졌지만, 기상 전문용어 CER은 **18.35에서 24.57로 오히려 나빠졌다**. "EPS", "hPa" 같은 약어는 "킴", "퀘토 파스칼"처럼 한글 음차로 나왔다 ([arXiv 2410.18444](https://arxiv.org/pdf/2410.18444)). 기성 Whisper-Large도 한국어-영어 코드스위칭 벤치마크 HiKE에서 MER 26.1로 약하다. GPT-4o-transcribe는 21.8이었다 ([HiKE](https://arxiv.org/html/2509.24613v4)). batisay 카드는 코드스위칭을 전혀 언급하지 않고, 출력에 엉뚱한 라틴 문자 한 글자가 섞이는 문제만 알려져 있다 ([batisay-ko-large](https://huggingface.co/batiai/batisay-ko-large)). 그래서 batisay는 순수 한국어 구간에서는 이득이 크고 영어 용어에서는 손해가 날 수 있다. 어느 쪽이 큰지는 사용자의 강의로만 판정할 수 있다. 저장소에는 이미 경고 신호가 하나 있다. 9월에 사용자 강의 20초 클립으로 돌린 Korean turbo 파인튜닝이 "의미가 없었다는"을 여섯 번 반복했다 ([로컬 결과](../bench_results/turbo-korean.json)).

### 2026년 서구 모델이 처음 한국어를 넣었지만 수치는 FLEURS뿐이다

2024–2025년 NVIDIA, Kyutai, IBM, Mistral 모델은 영어와 유럽어 전용이었다. 2026년 들어 이 판도가 바뀌었다. **Nemotron 3.5 Transcribe 30B-A4B**(2026-10-28, OpenMDW-1.1, 상업 사용 가능)는 총 약 34B, 활성 약 4.3B의 Mamba-2/Transformer 하이브리드 MoE다. 한국어를 "Leading quality" 등급에 넣었고 코드스위칭과 화자 분리도 지원한다고 밝혔다. FLEURS-ko CER은 **2.78%**이고, vLLM 서버의 CTC 정렬 헤드로 **단어 타임스탬프**를 낸다 ([HF 카드](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)). 형제 모델 **Nemotron 3.5 ASR Streaming 0.6B**(cache-aware RNNT)는 ko-KR을 "Transcription-ready" 등급에 두었고, FLEURS-ko CER은 청크 지연 80 ms에서 7.59, 1.12 s에서 7.12다 ([HF 카드](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)). Canary-1B-v2, Parakeet-TDT-0.6B-v3, Canary-Qwen, 2026-10-27의 unified-asr는 모두 **한국어 미지원**이다 ([canary-1b-v2](https://huggingface.co/nvidia/canary-1b-v2); [nemotron-labs-unified-asr](https://huggingface.co/nvidia/nemotron-labs-unified-asr-0.6b)).

Microsoft **VibeVoice-ASR**(MIT, HF 표기 9B)는 60분을 한 번에 처리하며 화자, 시간, 내용을 함께 내고, 핫워드와 문맥 주입을 지원한다. MLC 한국어 대화 음성 WER은 **9.65**로 Gemini-2.5-Pro(10.18)보다 낫다. 다만 SFT가 "영어, 중국어, 코드스위칭 위주"였고, 타임스탬프가 단어 단위인지는 밝히지 않았다 ([arXiv 2601.18184](https://arxiv.org/html/2601.18184)). 스트리밍 7B는 MLC-KO CER 9.09로 GPT Realtime Whisper(24.98)를 크게 앞서지만 **타임스탬프를 내지 않는다** ([arXiv 2609.02812](https://arxiv.org/html/2609.02812)). CPU용 BitNet판은 MLC-KO WER 11.15에 1.58 GB이고, EPYC 3스레드에서 RTF 0.77이다 ([VibeVoice-ASR-BitNet](https://huggingface.co/microsoft/VibeVoice-ASR-BitNet)). Mistral **Voxtral Realtime 4B**(Apache 2.0)도 한국어를 넣었다. 그러나 같은 표에서 FLEURS-ko WER이 기본 지연 480 ms에서 15.74로, 오프라인 Whisper의 14.30보다 나쁘고 추론 타임스탬프도 문서화되지 않았다 ([arXiv 2602.11298](https://arxiv.org/html/2602.11298)). Meta **Omnilingual ASR**(Apache 2.0)는 `kor_Hang`을 포함하고 FLEURS-81 집계에서 Whisper Large-v3를 크게 앞서지만(CER 5.6 대 22.6), 한국어 단독 수치가 없다 ([arXiv 2511.09690](https://arxiv.org/html/2511.09690); [lang_ids](https://raw.githubusercontent.com/facebookresearch/omnilingual-asr/main/src/omnilingual_asr/models/wav2vec2_llama/lang_ids.py)).

### 나머지 후보 대부분은 한국어 미지원이거나 증거가 없다

GLM-ASR-Nano(공식 17개 언어에 한국어 없음), FireRedASR/FireRedASR2, Fun-ASR-Nano 기본판, Paraformer, Kyutai STT, IBM Granite Speech, Voxtral Mini/Small 2507은 **한국어를 지원하지 않는다** ([GLM-ASR](https://github.com/zai-org/GLM-ASR); [FireRedASR2S](https://github.com/FireRedTeam/FireRedASR2S); [Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR); [Granite 4.1](https://huggingface.co/ibm-granite/granite-speech-4.1-2b)). Phi-4-multimodal은 원본 상태에서 Zeroth CER이 99.16%다 ([Phi-4-mm](https://huggingface.co/microsoft/Phi-4-multimodal-instruct)). 한국어를 지원하지만 근거가 약한 모델도 있다. Fun-ASR-MLT-Nano는 한국어 점수와 타임스탬프가 없다 ([MLT-Nano](https://huggingface.co/FunAudioLLM/Fun-ASR-MLT-Nano-2512)). MOSS-Transcribe-Diarize는 세그먼트 단위 타임스탬프만 낸다 ([MOSS](https://huggingface.co/OpenMOSS-Team/MOSS-Transcribe-Diarize)). SeamlessM4T v2는 비상업 라이선스이고, Moonshine tiny-ko는 연매출 100만 달러 제한 라이선스에 FLEURS 8.9%다 ([Moonshine 논문](https://arxiv.org/html/2509.02523)). 범용 오디오 LLM을 전사용으로 프롬프트하면 KoALa-Bench에서 크게 무너졌다. Voxtral은 Kspon 67.83%, Gemma-3n은 100% 초과였다. 그나마 Raon(8.16/7.81)과 Qwen3-Omni(8.58/8.15)가 버텼다 ([KoALa-Bench](https://arxiv.org/html/2604.19782)). 하지만 Qwen3-Omni는 30B-A3B 범용 모델이고 타임스탬프 출력을 문서화하지 않았다 ([Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni)). Raon은 이번 조사 자료에 크기와 타임스탬프 정보가 없다. 저장소에 받아 둔 KRAFTON Raon-Speech-9B가 KoALa-Bench의 "Raon"과 같은 모델인지도 확인되지 않았다. 프리뷰용 경량 후보로는 두 모델을 볼 만하다. **SenseVoice-Small**은 10초 음성을 70 ms에 처리하는 비자기회귀 모델이고 sherpa-onnx로 CPU에서 돈다 ([arXiv 2407.04051](https://arxiv.org/html/2407.04051); [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)). **Dolphin-small**(0.4B, KsponSpeech 969시간 포함 학습, 2026-05부터 단어 타임스탬프)은 자기 논문 표에서 CV17-ko 8.0 대 11.9로 Whisper Large-v3를 이겼다 ([arXiv 2503.20212](https://arxiv.org/html/2503.20212); [Dolphin](https://github.com/DataoceanAI/Dolphin)).

| 후보 | 한국어 근거 (같은 표 비교) | 단어 타임스탬프 | 스트리밍 | 라이선스 |
|---|---|---|---|---|
| Qwen3-ASR-1.7B / TeamUNIVA ko | Kspon 8.69 / 6.08 vs Whisper-v3 11.06 (kocer) | ForcedAligner로 가능, 한국어 37.2 ms | vLLM 전용, 의사 스트리밍 | Apache-2.0 |
| batisay-ko-large / turbo v1.1 | Kspon 6.83 / 6.99, 자체 strict 정규화 | whisper.cpp DTW/토큰 | whisper.cpp 방식 | BatiAI Community |
| Nemotron 3.5 Transcribe | FLEURS 2.78, Whisper 비교 없음 | CTC 정렬 헤드 | 없음(오프라인) | OpenMDW-1.1 |
| Nemotron 3.5 Streaming 0.6B | FLEURS 7.1–8.3 | 미확인 | 80 ms–1.12 s 청크 | OpenMDW-1.1 |
| VibeVoice-ASR 7B | MLC-KO WER 9.65 | 단위 미확인 | 별도 7B(타임스탬프 없음) | MIT |
| Voxtral Realtime 4B | FLEURS WER 15.74 vs Whisper 14.30 | 미문서화 | 80–2400 ms | Apache-2.0 |
| SenseVoice-Small | Kspon 약 13.1 vs Whisper 11.06 (kocer) | CTC 토큰 | 의사 스트리밍(커뮤니티) | FunASR(출처 표시) |

## 환각은 Whisper 구조의 문제이고, 타임스탬프는 ASR과 분리할 수 있다

Whisper는 소리가 없어도 글자를 낸다. 2026년 대규모 측정에서 **모든 OpenAI 체크포인트가 무음 벤치마크 클립의 100%에서 무언가를 출력**했고, Large-v3는 실내 잡음 클립의 61.9%에서 단어를 썼다. 반복 루프 꼬리는 turbo가 훨씬 길었다. 실제 반복 대비 출력 반복의 p95 비율이 Large-v3는 1.00, **turbo는 18.3**이었다 ([arXiv 2609.32560](https://arxiv.org/html/2609.32560v1)). Calm-Whisper 연구는 비음성 클립에서 Large-v3가 99.97%, Conformer-CTC가 13.52% 환각을 보였다고 보고했다 ([Calm-Whisper](https://www.isca-archive.org/interspeech_2025/wang25b_interspeech.pdf)). 오류가 나는 원인이 모델 구조에 있다는 뜻이다. 사용자의 운영 데이터도 이 그림과 맞는다. VAD로 자르고 `-mc 0`(이전 문맥 없음)으로 돌렸더니 저장된 Whisper final 8,494개 중 **13개(0.15%)**가 반복 검사에 걸렸다. 재시도 설정(temperature 0.4, best_of 5)은 같은 루프 16개 중 12개를 풀었고, `suppress_nst`는 9개만 풀면서 "시청해주셔서 감사합니다" 환각을 새로 만들었다 ([로컬 handoff](../LOCAL_CLOVA_V8_2_EPSILON_HANDOFF_2026-10-29.md)). 지금의 방어선(Silero VAD, 문맥 없음, 재시도)은 문헌이 권하는 표준 조합과 같고, 효과도 있다. 남은 위험은 루프보다 **비음성 구간을 VAD가 통과시켰을 때의 환각**이다. 운영 데이터는 이 위험을 아직 재지 않았다.

새 후보들의 환각 특성은 대부분 측정되지 않았다. 구조로 보면 RNNT(Nemotron Streaming)와 CTC/NAR(SenseVoice, Dolphin CTC 가지, Omnilingual CTC)는 자기회귀 디코더처럼 폭주 반복에 빠지기 어렵다. 다만 이것은 구조에서 나온 추론이지 한국어 측정치가 아니다. LLM 디코더 계열은 예외가 아니다. Qwen3-ASR은 vLLM 반복 보고(#129)와 스트리밍 핫워드 반복(#140)이 있다 ([issue #140](https://github.com/QwenLM/Qwen3-ASR/issues/140)). Nemotron Transcribe는 알려진 오류로 "환각된 발화"를 직접 명시했다 ([HF 카드](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Transcribe-30B-A4B)). VibeVoice는 무음과 음악을 [Silence]/[Music]으로 라벨링해 학습했다고 밝혔지만 환각률은 내놓지 않았다 ([arXiv 2601.18184](https://arxiv.org/html/2601.18184)). 반복 억제 디코딩 설정도 공짜가 아니다. kocer에서 BuzzASR가 권장한 반복 억제 설정은 **다섯 데이터셋 모두에서 CER을 악화**시켰다 ([kocer](https://github.com/Choi-kwan-u/kocer)). 그러니 디코딩 옵션 자체도 A/B 대상이다.

타임스탬프 쪽은 이 조사에서 가장 실용적인 발견이 나온다. **Qwen3-ForcedAligner-0.6B는 어떤 ASR이 낸 텍스트든 정렬할 수 있다**. 한국어 누적 평균 이동(AAS)은 37.2 ms, 300초를 이어 붙인 음성에서는 42.2 ms다. 10개 언어 평균에서 WhisperX는 133.2 ms, NeMo Forced Aligner는 129.8 ms였고, 두 도구는 한국어 항목이 아예 없었다 ([Qwen3-ASR README](https://github.com/QwenLM/Qwen3-ASR); [arXiv 2601.21337](https://arxiv.org/html/2601.21337)). 이에 비해 whisper.cpp의 단어 분할(`-ml 1`)은 "실험적" 표시가 붙어 있고, DTW 정렬 헤드 프리셋은 기본 모델용이라 파인튜닝 모델에서는 어긋날 수 있다. 한국어 단어 경계 정확도를 잰 연구도 없다 ([whisper.cpp CLI](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/examples/cli/README.md); [issue #2480](https://github.com/ggml-org/whisper.cpp/issues/2480)). WhisperX의 한국어 정렬기는 어절 단위이고, 사전에 없는 숫자와 기호(라틴 문자로 적힌 영어 용어도 같은 문제로 추정)에는 시간을 주지 못한다 ([WhisperX alignment.py](https://raw.githubusercontent.com/m-bain/whisperX/main/whisperx/alignment.py)). 정렬기는 5분 이하 입력만 받고 PyTorch 전용이다. 이 앱의 1–28초 세그먼트는 그 제약 안에 넉넉히 들어간다. 따라서 **ASR을 바꾸지 않고도 click-to-play 품질을 따로 올릴 수 있다**. Whisper 출력을 그대로 두고 단어 시간만 정렬기로 다시 매기는 구성이 가장 값싼 대조군이다. 정렬기가 어절 단위로 정렬하는지 음절 단위로 정렬하는지는 직접 시험해야 한다.

## gfx1151에서 검증된 길은 whisper.cpp와 CTranslate2 둘뿐이다

플랫폼 자체는 2026년 하반기에 정리됐다. ROCm 10.1.0(2026-10-05)은 gfx1151 Strix Halo와 **Ubuntu 24.04.5 HWE 커널 7.0**을 공식 지원 목록에 올렸고, PyTorch 2.14를 명시한다 ([ROCm 10.1.0 릴리스 노트](https://rocm.docs.amd.com/en/latest/about/release-notes.html)). PyTorch 휠은 TheRock 인덱스의 `torch[device-gfx1151]`로 받는다 ([TheRock RELEASES.md](https://github.com/ROCm/TheRock/blob/main/RELEASES.md)). 남은 함정도 분명하다. AMD가 Ryzen APU에서 공식 검증한 dtype은 **fp16뿐**이다 ([Radeon/Ryzen 호환표](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityryz/native_linux/native_linux_compatibility.html)). bf16 NaN과 출력 손상 보고(TheRock #9198)는 2026-10-16 기준 여전히 열려 있다. AOTriton 플래시 어텐션은 SDPA를 44 ms에서 2.3 ms로 줄이지만 AMD 스스로 "실험적"이라고 부른다 ([ROCm #6034 → TheRock #9198](https://github.com/ROCm/ROCm/issues/6034)). 그러니 Nemotron이나 VibeVoice처럼 bf16으로 배포되는 모델은 fp16으로 바꿔 돌릴 수 있는지부터 따져야 한다.

현재 엔진의 속도는 저장소의 9월 벤치에 있다. whisper.cpp HIP, Large-v3 FP16, beam 5 + best-of 5 설정에서 **20초 세그먼트 하나가 7.02초**(RTF 0.35) 걸렸다. 그중 인코딩이 1.80초, 빔 디코딩이 4.44초였다. q8_0(7.61초)와 q5_0(7.76초)는 오히려 느렸다 ([로컬 fp16 로그](../bench_results/whispercpp/large-v3-fp16.log); [q8_0](../bench_results/whispercpp/large-v3-q8_0.log); [q5_0](../bench_results/whispercpp/large-v3-q5_0.log)). 90분 통파일은 2,608초(RTF 0.48)가 걸렸고, 인코딩 30초 창당 2.04초로 20초 세그먼트의 인코딩 시간과 거의 같았다 ([로컬 90분 로그](../bench_results/whisper_stress/20260918-211711-90m.log)). 두 가지가 읽힌다. 세그먼트가 짧아도 30초 창 하나만큼의 인코딩 비용을 다 낸다. 그리고 시간 대부분은 빔 디코딩이 먹는다. 비교 기준으로, Strix Halo에서 CTranslate2 ROCm 휠로 돌린 faster-whisper Large-v3 fp16(beam 5)은 11초 영어 클립에서 실시간의 11.5배(RTF 0.087), VAD 없이 30분 일본어에서 6.56배(RTF 0.15)였다 ([nabe2030](https://github.com/nabe2030/faster-whisper-rocm-strix-halo)). 언어와 클립이 달라 직접 비교는 못 하지만, **같은 모델이라도 런타임을 바꾸면 2–4배 빨라질 여지**가 있다. FLEURS-ko에서는 beam 1 같은 디코딩 설정 변경이 CER을 잡음 수준 이상으로 바꾸지 않았다는 측정도 있다 ([PR #740](https://github.com/zkaelxz/U00/pull/740)).

| 후보 | gfx1151 Linux 권장 경로 | 증거 수준 | 핵심 위험 |
|---|---|---|---|
| Whisper Large-v3 (현행) | whisper.cpp HIP (`GGML_HIP_NO_VMM`), 대안 CT2 ROCm 휠 | 로컬 측정 + 커뮤니티 | 24시간 내 메모리 aperture 크래시 보고 ([#3576](https://github.com/ggml-org/whisper.cpp/issues/3576)) |
| batisay v1.1 | 같은 whisper.cpp (GGUF 제공), CT2는 직접 변환 | whisper.cpp는 검증, 모델은 미검증 | turbo DTW 헤드 프리셋, q5_0 장문 열화 |
| Qwen3-ASR + Aligner | TheRock PyTorch 2.14 fp16 + PR #103, 또는 llama.cpp mtmd GGUF(ASR만) | 보고 없음 ([Qwen3-ASR 이슈 검색](https://github.com/QwenLM/Qwen3-ASR/issues)) | SDPA 창 버그, 정렬기는 PyTorch 전용 |
| Nemotron 3.5 Transcribe | vLLM ROCm 또는 Transformers(소스), bf16 약 68 GB | 보고 없음, 공식 대상은 H100 | vLLM gfx1151 비결정성 버그 ([#57493](https://github.com/vllm-project/vllm/issues?q=gfx1151)) |
| Nemotron Streaming 0.6B | NeMo + TheRock PyTorch(CUDA graph 디코더 끔), NeMo-Speech.cpp GGUF | Parakeet가 gfx1100에서만 확인 ([NeMo #15905](https://github.com/NVIDIA-NeMo/Speech/issues/15905)) | gfx1151 미검증 |
| VibeVoice-ASR | Transformers/vLLM, BitNet은 CPU GGUF | CPU 경로만 문서화 | ROCm 언급 없음 |
| Whisper turbo on NPU | FastFlowLM `/v1/audio/transcriptions` | Strix Point에서 RTF 약 0.18 ([dev.to](https://dev.to/jac-76/running-whisper-llms-on-an-amd-npu-under-linux-2o1h)) | 한국어 정확도 미측정, 커널 비공개 |

vLLM은 gfx1151을 공식 지원 목록에 올렸지만, 같은 탐욕 디코딩 요청이 다른 요청 뒤에 오면 결과가 달라지는 `ROCM_ATTN` 버그가 열려 있다. ASR 재현성에는 치명적이다. AMD는 ROCm 7.14 노트에서 SGLang의 Qwen3-ASR이 Radeon에서 "제대로 동작하지 않을 수 있다"고 적었다 ([vLLM ROCm 설치 문서](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/gpu.rocm.inc.md); [ROCm 7.14.0 노트](https://github.com/ROCm/ROCm/releases/tag/rocm-7.14.0)). llama.cpp mtmd는 Qwen3-ASR GGUF를 공식 지원하고 HIP와 Vulkan 모두 gfx1151에서 돌지만, 오디오 모델을 이 칩에서 돌린 보고는 없다 ([llama.cpp multimodal](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)). ONNX Runtime ROCm EP는 1.22 이후 제거됐고, 마지막 휠에는 gfx1151 커널이 없다 ([parakeet PR #28](https://github.com/achetronic/parakeet/pull/28)). 따라서 sherpa-onnx 계열(SenseVoice, Dolphin-base)은 사실상 CPU 경로다.

XDNA2 NPU는 Linux에서도 쓸 수 있게 됐다. FastFlowLM이 2026-03-11부터 Linux에서 Whisper large-v3-turbo를 NPU로 돌린다. v1.0.10(2026-10-22)에서 디코더에 언어 토큰을 넘기지 않던 버그와 30초 창 경계 반복 문제가 고쳐졌다 ([Lemonade FLM Linux](https://lemonade-server.ai/flm_npu_linux.html); [FLM v1.0.10](https://github.com/FastFlowLM/FastFlowLM/releases/tag/v1.0.10)). 한국어 정확도는 아무도 재지 않았고, 모델은 turbo 하나뿐이며, 환각 위험도 turbo 그대로다. 그래도 NPU는 **프리뷰 경로에 잘 맞는다**. 사용자의 프리뷰는 저장되지 않는 최신값 전용이고, 2026-10-29 세션에서는 final과 같은 서버를 공유하다 ReadTimeout이 5번 났다 ([로컬 handoff](../LOCAL_CLOVA_V8_2_EPSILON_HANDOFF_2026-10-29.md)). 프리뷰를 NPU(FLM turbo)나 CPU(SenseVoice, Nemotron Streaming GGUF)로 옮기면 final은 iGPU를 혼자 쓴다. 틀려도 저장되지 않는 프리뷰는 위험한 엔진을 실험하기에 가장 안전한 자리다.

## 교수 한 명보다 강의 도메인에 맞춘 적응이 더 큰 효과를 낸다

사용자의 요구는 "인간 교정으로 교수별 LoRA"다. 그런데 2026년 연구는 화자별 적응보다 묶음 적응 쪽을 지지한다. Whisper tiny–medium에 화자당 약 13–17분으로 LoRA(r=16, q/v)를 붙인 실험에서, 여러 화자를 묶은 **pooled 어댑터가 화자별 어댑터를 이겼다**. VoxPopuli small 기준 무적응 11.13에서 pooled는 8.65, 화자별은 10.37이었다. 적응 이득은 기저 오류가 높고 안정적인 그룹에 몰렸다 ([Katkov & Liotta, arXiv 2610.17019](https://arxiv.org/html/2610.17019)). 반면 도메인 적응은 효과가 컸다. KAIST는 TTS로 합성한 전문용어 문장만으로 기상 용어 CER을 **18.35에서 10.64로** 낮췄다 ([arXiv 2410.18444](https://arxiv.org/pdf/2410.18444)). HiKE에서는 실제 코드스위칭 데이터로 Whisper-Medium의 MER이 31.3에서 9.0으로 떨어졌지만, 그 대가로 단일 한국어 CER이 3.4에서 6.0으로 올랐다 ([HiKE](https://arxiv.org/html/2509.24613v4)). 기저 오류가 극단적으로 높은 단일 화자(마비말장애, Large-v3 WER 128.4%)는 1.4시간 전체 파인튜닝으로 15.8%까지 내려갔다. 이때 LoRA rank 8은 전체 파인튜닝보다 상대적으로 15–39% 나빴다 ([arXiv 2606.31722](https://arxiv.org/pdf/2606.31722)). 적응 설계에서 MLP층(fc1/fc2)이 어텐션보다 중요했고, **학습 손실은 체크포인트 순위를 거꾸로 매겼다** ([arXiv 2609.32560](https://arxiv.org/html/2609.32560v1)). 정리하면, 교정 데이터를 "교수 A 전용"으로 쪼개기보다 "강의 전체 + 과목 용어 TTS 문장 + 일반 한국어 리플레이"로 묶어 학습하고, 반드시 보류한 강의로 선택하는 편이 낫다.

엔진별 적응 경로는 다르다. Whisper 계열은 HF PEFT로 LoRA를 학습한 뒤 어댑터를 병합하고 `convert-h5-to-ggml.py`로 whisper.cpp 모델을 만든다. batisay의 GGUF 배포가 한국어 large-v3와 turbo 파인튜닝에서 이 경로가 통한다는 증거다. 다만 변환 후 "완전히 쓸 수 없는 결과"가 나왔다는 사례도 있어 변환 뒤 재검증이 필수다 ([whisper.cpp models](https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/models/README.md); [HF 토론](https://huggingface.co/Sandiago21/whisper-large-v2-german-2/discussions/3)). whisper.cpp는 어댑터를 런타임에 얹지 못하므로 교수마다 전체 모델 파일(turbo q5_0 약 550 MB, large 1.1–1.7 GB)이 생긴다. Qwen3-ASR의 공식 스크립트는 **LoRA 없는 전체 파라미터 SFT**다. 대신 vLLM이 Qwen3-ASR용 LoRA 어댑터 서빙을 지원하므로, 커스텀 PEFT 래퍼로 학습하면 어댑터 교체형 운영이 가능하다 ([Qwen3-ASR finetuning](https://github.com/QwenLM/Qwen3-ASR/tree/main/finetuning); [vLLM supported models](https://github.com/vllm-project/vllm/blob/main/docs/models/supported_models.md)). Nemotron은 두 모델 모두 NeMo 파인튜닝 툴킷 경로가 문서화돼 있다 ([HF Streaming 카드](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)). 걸리는 것은 이 칩에서의 학습이다. gfx1151에서는 "Whisper를 파인튜닝할 수 없다"는 보고(2026-04-20)와 bf16 NaN 보고가 있고, 한 LoRA 작업은 AOTriton 실험 플래그와 `MIOPEN_DEBUG_CONV_DIRECT=0`을 켜고서야 크래시를 피했다 ([ROCm #6034](https://github.com/ROCm/ROCm/issues/6034)). 128 GB 통합 메모리는 용량 면에서는 넉넉하다. 그러나 학습은 fp16/fp32 혼합으로, 작은 실험부터 수치 안정성을 확인하며 진행해야 한다. 덧붙여 지금 저장소의 Professor LoRA는 여전히 batisay-ko-large 어댑터를 만들고 있어 운영 ASR과 끊겨 있다 ([로컬 handoff](../LOCAL_CLOVA_V8_2_EPSILON_HANDOFF_2026-10-29.md)). 엔진 선택이 이 연결 방향까지 정한다.

## 벤치마크할 네 후보와 판정 프로토콜

### 기대 성능과 실현 가능성으로 매긴 순위

| 순위 | 후보 | 역할 | 뽑은 이유 | 가장 큰 위험 |
|---|---|---|---|---|
| 1 | Qwen3-ASR-1.7B(기본판, TeamUNIVA ko) + Qwen3-ForcedAligner-0.6B, 프리뷰는 0.6B | final + 단어 시간 | 같은 표 자발화 CER에서 Whisper-v3 대비 ko판 약 45%, 기본판 약 21% 낮음, 영어 능력 보존, 한국어 정렬 37 ms, Apache-2.0, SFT와 vLLM LoRA 경로 | 열화 음성 약점, SDPA 8초 버그, gfx1151 실행 보고 없음 |
| 2 | batisay-ko-turbo v1.1 / ko-large v1.1 | final(드롭인) | 현행 whisper.cpp에 모델 파일만 교체, 강의 코퍼스로 학습, Professor LoRA 파이프라인과 같은 계열 | 영어 용어 음차·손실, turbo 루프, 비상업 외 라이선스 |
| 3 | Nemotron 3.5 Transcribe 30B-A4B | 상한 탐색 | 공개 한국어 최고치(FLEURS 2.78), 한국어 코드스위칭 명시, CTC 단어 타임스탬프 | ROCm 문서 없음, bf16 약 68 GB, 속도 미지수 |
| 4 | Nemotron 3.5 ASR Streaming 0.6B | 프리뷰 / 실시간 | 80 ms–1.12 s 청크에서 FLEURS 7.1–7.7(언어 지정), RNNT라 루프에 덜 취약, 작아서 CPU/GGUF 가능 | 타임스탬프와 gfx1151 실행 미확인 |

1순위를 Qwen 조합으로 둔 근거는 간단하다. 사용자의 강의가 가장 닮은 데이터(KsponSpeech 자발화)에서 같은 규칙으로 잰 격차가 가장 크다. 영어 용어 보존 근거(TeamUNIVA의 LibriSpeech 2.50→2.77)도 후보 중 유일하다. 사용자가 이미 써 본 모델이라는 점은 감점 사유가 아니다. 예전 경로는 의사 스트리밍에 타임스탬프가 없는 구성이었다. 2순위 batisay는 통합 비용이 사실상 0이라 가장 먼저 돌려볼 수 있다. 저장소에 있는 batisay가 v1.1(2026-07-05)인지는 확인해야 한다. 3순위 Nemotron Transcribe는 성능 근거가 FLEURS 하나뿐이고 실행 가능성이 가장 불확실하다. 그래서 정확도 평가에 앞서 "fp16/bf16으로 gfx1151에서 세그먼트 100개를 끝까지 돌릴 수 있는가"를 반나절짜리 실현성 검사로 먼저 끝낸다. 4순위는 final 후보가 아니라 프리뷰 경로 분리용이다. FLM NPU의 turbo와 CPU의 SenseVoice-Small을 같은 프리뷰 슬롯의 대안으로 함께 잰다. VibeVoice-ASR은 핫워드 주입과 무음 라벨이 매력적이다. 그러나 단일 강사, 세그먼트 기반인 이 앱에서는 장점(60분 문맥, 화자 분리)을 쓰기 어렵고 단어 타임스탬프도 불명확해 명단에서 뺐다. 대조군 두 개를 반드시 함께 돌린다. 하나는 **Whisper Large-v3 + Qwen3-ForcedAligner**(타임스탬프만 개선), 다른 하나는 **Whisper Large-v3 on CTranslate2 ROCm**(속도만 개선)이다. 새 모델의 이득이 모델 자체에서 오는지, 정렬기나 런타임에서 오는지 갈라 볼 수 있다.

### 사용자 교정 데이터로 돌리는 평가 프로토콜

데이터는 저장된 세션에서 사람이 교정한 세그먼트를 쓴다. 강의 단위로 고정 seed로 뽑고, 가능하면 10–20개 강의에서 2,000개 이상을 확보한다. 20개 클립과 1,000개 클립에서 엔진 순위가 뒤집힌 사례가 있으니 소량 표본은 피해야 한다 ([AeCeCi](https://github.com/AeCeCi/STT-Meeting-CER-Benchmark)). 이후 LoRA 실험에 쓸 강의는 처음부터 통째로 따로 떼어 둔다. 주의할 편향이 하나 있다. 교정 참조는 Whisper 출력에서 출발했으므로, 사람이 고치지 않은 띄어쓰기, 숫자 표기, 영어 표기가 Whisper 쪽으로 기울어 있다. 이 편향을 재려면 약 100개 세그먼트를 Whisper 출력 없이 오디오만 듣고 새로 전사한다. 그 뒤 Whisper의 CER을 "교정 참조"와 "블라인드 참조"로 각각 계산해 차이를 본다. 모든 엔진에는 앱이 실제로 보내는 것과 똑같은 VAD 절단 WAV(같은 이득, 16 kHz)를 넣는다. 엔진마다 다른 VAD를 쓰면 엔진이 아니라 분할을 비교하게 된다. 정규화는 kocer v0.5.x처럼 규칙이 동결된 도구로 고정하고, 과목 용어 별칭만 추가한다 ([kocer](https://github.com/Choi-kwan-u/kocer)). 엔진 사이 차이는 강의 단위 쌍 부트스트랩 95% 신뢰구간으로 판정한다 ([PR #740](https://github.com/zkaelxz/U00/pull/740)).

| 축 | 측정 방법 | 데이터 | 채택 기준(제안) |
|---|---|---|---|
| 원시 CER | NFC와 앞뒤 공백만 정리하고 문자 편집거리 | 교정 세그먼트 전체 | 보고용 |
| 정규화 CER | kocer: NFKC, 공백·문장부호 제거, 숫자·영어 별칭, 오류 유형 분해(띄어쓰기/문장부호/숫자·영어/실오류) | 〃 | Whisper 대비 상대 10% 이상 개선, 신뢰구간이 0을 포함하지 않음 |
| 영어 용어 | 참조에서 라틴 문자 토큰, 그리스 문자·수식 읽기를 자동 추출. 라틴 표기 정확 재현율, 한글 음차도 맞게 치는 "양 표기 허용" 재현율(HiKE 방식), 음차 비율 ([HiKE](https://arxiv.org/html/2509.24613v4)) | 용어 포함 세그먼트 | 정확 재현율이 Whisper보다 2%p 넘게 떨어지지 않음 |
| 의미 보존 | 100문장 표본에서 의미 이탈과 부정 반전 수 ([AI_LectureNote](https://arxiv.org/abs/2607.17237)) | 무작위 표본 | Whisper 이하 |
| 비음성 환각 | 비어 있지 않은 출력 비율(Calm-Whisper 방식), 잡음 1분당 출력 글자 수, "시청해주셔서 감사합니다" 류 문구 적중 | 사람이 전부 지운 세그먼트, `lecture_raw.wav`에서 뽑은 판서·환기·웅성거림 구간(1–28 s), Scicom 무음 벤치 ([arXiv 2609.32560](https://arxiv.org/html/2609.32560v1)) | Whisper보다 낮음 |
| 반복 루프 | 앱의 `detect_whisper_repetition_loop()` 적중률, 5-gram 반복률, 가설/참조 길이비 1.5 초과 비율, 재시도 구제율 | 교정 세그먼트 + 장문 2편 | 현행 0.15% 이하 |
| 타임스탬프 | 30개 세그먼트의 단어 시작점 300–500개를 파형 도구로 직접 표시(정렬기와 무관한 참조). AAS, 200 ms 이내 비율, 부호 있는 시작 오차 분포 | 수작업 표시셋 | 중앙값 100 ms 이하, 95% 이상이 실제 시작보다 100 ms 넘게 늦지 않음 |
| 속도(final) | gfx1151 웜 상태 HTTP 왕복 벽시계 시간. 길이 구간(≤6, 6–15, 15–28 s)별 RTF p50/p95, 최대 메모리(`rocm-smi -u`), 콜드 로드 시간 | 교정 세그먼트 | p95 RTF 0.35(현행 20 s 세그먼트 수준) 이하 |
| 속도(프리뷰) | final과 동시에 돌리며 6 s 창 지연 p95와 타임아웃 수 | 녹음 재생 시뮬레이션 | p95 2 s 이하, 타임아웃 0 |
| 안정성 | 1–2시간 강의 2편을 전체 앱 파이프라인으로 처리, 24시간 연속 부하 | 실제 녹음 | 크래시와 비결정성 0 |

타임스탬프 참조를 Qwen3-ForcedAligner나 다른 정렬기로 만들면 그 정렬기를 쓰는 후보에게 유리해진다. 그래서 작은 수작업 표시셋이 꼭 필요하다. click-to-play에서는 시작점이 조금 이른 것은 무해하고 늦는 것은 단어 앞부분을 잘라 먹으므로, 오차를 절댓값만이 아니라 부호를 붙여 본다. 디코딩 옵션(빔 크기, 반복 억제, temperature 재시도)은 엔진마다 권장값과 앱의 루프 가드를 붙인 값 두 가지로 돌려 옵션 효과를 분리한다. 상용 천장을 알고 싶다면 교정 세그먼트 100–200개를 CLOVA Speech 장문 API에 한 번 보내 같은 채점기로 잰다. 다만 강의 음성을 외부로 보내는 일이므로, 앱의 완전 로컬 원칙과 교수 동의를 먼저 확인해야 한다. 한 엔진이 위 기준을 통과하면 바로 다음 단계로 넘어간다. 보류해 둔 강의로 pooled LoRA, 교수별 LoRA, 용어 TTS 증강 세 가지를 비교하고, 선택은 학습 손실이 아니라 보류 강의의 정규화 CER과 용어 재현율로 한다.

## 결론

이번 조사의 가장 큰 발견은 "어떤 모델이 최고인가"보다 **이 앱의 구조가 후보 평가를 바꾼다**는 점이다. Silero VAD로 자른 1–28초 세그먼트 구조는 새 모델들의 장문 약점을 대부분 무력화한다. Qwen의 180초 청크 이어붙이기 버그, Omnilingual의 40초 제한, 정렬기의 5분 제한, Nemotron과 VibeVoice의 60분 상한이 모두 문제가 되지 않는다. 대신 장문 모델이 내세우는 장점(시간 단위 문맥, 화자 분리)도 함께 지운다. 그래서 단일 강사, 세그먼트 기반 앱에서는 짧은 입력에서 강하고 영어를 잃지 않는 중형 모델 + 독립 정렬기 조합이 구조적으로 유리하다. 같은 이유로 타임스탬프 품질과 프리뷰 지연은 ASR 교체와 따로 개선할 수 있다. 정렬기를 붙이고, 프리뷰를 NPU나 CPU로 분리하면 된다. 엔진 교체 결정은 순수하게 정규화 CER, 영어 용어, 비음성 환각 세 축으로 좁혀진다.

두 번째 함의는 위험의 위치가 옮겨 갔다는 것이다. 2024년에는 "로컬 한국어 모델이 상용을 따라잡을 수 있는가"가 질문이었다. 2026년 11월의 질문은 "따라잡은 모델이 이 AMD 칩에서 재현 가능하게 도는가"다. Whisper가 지금 운영 엔진인 진짜 이유는 정확도가 아니라 whisper.cpp HIP라는 검증된 경로에 있다. 따라서 1순위 후보의 첫 관문은 CER이 아니다. TheRock PyTorch 2.14 fp16에서 PR #103을 적용한 Qwen3-ASR이 세그먼트 100개를 비결정성 없이 처리하는지가 먼저다. 이 관문을 넘으면 Professor LoRA를 Qwen3 쪽에 다시 연결할 근거가 생긴다. 넘지 못하면 batisay와 Whisper 정렬기 대조군이 현실적인 다음 단계다.
