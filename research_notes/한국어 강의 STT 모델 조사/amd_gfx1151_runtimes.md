# ASR inference runtimes on AMD Strix Halo (Ryzen AI Max+ 395 / Radeon 8060S gfx1151 / XDNA2 NPU) under Linux — status as of 2026-11-01

Scope: Linux only (target Ubuntu 24.04, kernel 7.0). Every claim is dated. "Primary" means AMD/upstream docs, release notes, or the GitHub issue/repo itself. Single-user community reports are marked as such. Windows-only paths are flagged as Windows-only.

## 1. What is the official ROCm/PyTorch status for gfx1151 as of late 2026, and which versions work for audio models (flash attention, bf16, rocBLAS/hipBLASLt issues)?

### Takeaway
As of Nov 2026, gfx1151 (Strix Halo) is officially supported on Linux. The current ROCm Core SDK 10.1.0 (2026-10-05) lists Ubuntu 24.04.5 with the HWE 7.0 kernel, which matches the target machine. PyTorch 2.12–2.14 wheels for gfx1151 come from AMD's TheRock multi-arch pip index, and upstream PyTorch ROCm wheel builds include gfx1151 too. Inference works, but there are open gfx1151 problems: bf16 NaN and corruption reports (mostly training), an AOTriton flash-attention path that is still experimental, and a hipBLASLt default that only arrived in PyTorch 2.14. Use fp16 for inference where you can. It is the only dtype AMD officially validated on Ryzen APUs.

### Cited Findings
**ROCm release timeline and versioning (primary)**
- ROCm GitHub releases: 7.1.0 (2025-11-03), 7.1.1 (2025-11-26), 7.2.0 (2026-01-23), 7.2.1 (2026-03-25), 7.2.2 (2026-04-14), 7.2.3 (2026-05-04), 7.2.4 (2026-05-29), 7.14.0 (2026-07-16) — [ROCm/ROCm releases](https://github.com/ROCm/ROCm/releases)
- TheRock ("ROCm Core SDK") releases: 7.13 (2026-05-15), 7.14.0 (2026-07-15), 10.0.0 (2026-08-26), 7.14.1 (2026-08-31), 10.1.0 (2026-10-05, marked Latest) — [ROCm/TheRock releases](https://github.com/ROCm/TheRock/releases)
- The ROCm 7.14.0 notes say it "transitions ROCm to TheRock" and "follows the versioning discontinuity that began with the 7.9.0 preview." The jump to 10.x happened after that. — [ROCm 7.14.0 release notes](https://github.com/ROCm/ROCm/releases/tag/rocm-7.14.0); [ROCm 10.1.0 release notes](https://rocm.docs.amd.com/en/latest/about/release-notes.html) ("Since ROCm 7.14, ROCm uses TheRock as its build and release system")
- TheRock's own docs say the new `repo.amd.com` layout "starts with ROCm 10.1 nightly releases and ROCm 10.0 stable releases." ROCm 7.14 nightlies are only in legacy indexes. — [TheRock RELEASES.md](https://github.com/ROCm/TheRock/blob/main/RELEASES.md)

**gfx1151 official support, in chronological order**
- ROCm 7.1.0 (2025-11-03): hipBLAS 3.1.0 notes "gfx1150, gfx1151, gfx1200, and gfx1201 support enabled," and rocBLAS notes "gfx1150 and gfx1151 enabled." — [ROCm 7.1.0 release notes](https://github.com/ROCm/ROCm/releases/tag/rocm-7.1.0)
- The "ROCm on Radeon and Ryzen" docs, which cover releases through 7.2.1 (Mar 2026), list gfx1150/gfx1151 under ROCm 7.2.1. They name Ryzen AI Max+ 395, 390 and 385, list Ubuntu 24.04.4, and show PyTorch 2.9.1 + ROCm 7.2.1 + Python 3.12 as "Official production support." Caveat from the same page: "Only FP16 has been officially validated, but other data types may work as well." — [Radeon/Ryzen native Linux compatibility](https://rocm.docs.amd.com/projects/radeon-ryzen/en/latest/docs/compatibility/compatibilityryz/native_linux/native_linux_compatibility.html)
- ROCm 7.14.0 (2026-07-16) adds the Ryzen AI MAX PRO 400 parts (gfx1151, "Gorgon Halo"). Framework support moved to PyTorch 2.12.0, JAX 0.10.0, vLLM 0.23.0 and SGLang 0.5.13, replacing PyTorch 2.9.1 and vLLM 0.19.1. — [ROCm 7.14.0 release notes](https://github.com/ROCm/ROCm/releases/tag/rocm-7.14.0)
- ROCm 10.1.0 lists Ryzen AI Max 300 / PRO 300 as "gfx1151 Strix Halo" and the PRO 400 as "gfx1151 Gorgon Halo." Supported OS: Ubuntu 26.04.1 (GA kernel 7.0), Ubuntu 24.04.5 (HWE kernel 7.0), and Windows 11 25H2. Kernel driver: "Inbox kernel driver in supported Ubuntu version." PyTorch 2.14.0 is listed, plus hipBLASLt 1.4.1 for "Instinct/Radeon/Ryzen." — [ROCm 10.1.0 release notes](https://rocm.docs.amd.com/en/latest/about/release-notes.html); [ROCm compatibility matrix](https://rocm.docs.amd.com/en/latest/compatibility/compatibility-matrix.html). The matrix page also lists PyTorch 2.14/2.13/2.12. Discrepancy: my fetch of the matrix page reported a date of 2026-08-26 for 10.1.0, while the release notes and the GitHub tag say 2026-10-05. 2026-08-26 is the 10.0.0 date, so this is probably a page artifact.
- ROCm 10.1.0 adds validated gfx1151 SystemDBs to MIOpen and changes rocBLAS gemm behavior on gfx11. — [ROCm 10.1.0 release notes](https://rocm.docs.amd.com/en/latest/about/release-notes.html)
- Older statements that "there is no official ROCm build for gfx1151" (llm-tracker, page dated 2025-08-08) and "stable ROCm does not ship gfx1151 kernels" (TheRock issue, 2026-03-13) are superseded. They describe the 2025 to early-2026 state. — [llm-tracker Strix Halo](https://llm-tracker.info/_TOORG/Strix-Halo); [ROCm/TheRock #9198 (ex-ROCm #6034)](https://github.com/ROCm/ROCm/issues/6034)

**PyTorch wheels for gfx1151**
- TheRock multi-arch index: `pip install --index-url https://stable.repo.amd.com/rocm/whl-next/` (or `nightly.repo.amd.com`). Select the GPU with an extra, e.g. `torch[device-gfx1151]`. The device table lists "AMD Ryzen AI Max+ PRO 395 | gfx1151 | device-gfx1151." Compatible sets: torch 2.14 / torchaudio 2.11 / torchvision 0.29, and back through 2.11. — [TheRock RELEASES.md](https://github.com/ROCm/TheRock/blob/main/RELEASES.md)
- TheRock builds PyTorch 2.13, 2.14 and 2.15 from ROCm/pytorch release branches. 2.10–2.12 are "Previously built." AOTriton is marked supported on Linux and Windows. — [TheRock external-builds/pytorch README](https://github.com/ROCm/TheRock/blob/main/external-builds/pytorch/README.md)
- Upstream PyTorch's manywheel ROCm build script sets `PYTORCH_ROCM_ARCH="gfx908;gfx90a;gfx942;gfx950;gfx1030;gfx1100;gfx1101;gfx1102;gfx1103;gfx1200;gfx1201;gfx1150;gfx1151;gfx1250"` on main (checked 2026-11-01). — [pytorch/pytorch .ci/docker/manywheel/build.sh](https://github.com/pytorch/pytorch/blob/main/.ci/docker/manywheel/build.sh)
- History: before official wheels, users relied on TheRock nightlies (e.g. `torch 2.11.0a0+rocm7.11.0a20260106`) or community wheels (scottt). — [ROCm #6034](https://github.com/ROCm/ROCm/issues/6034); [scottt rocm-TheRock releases](https://github.com/scottt/rocm-TheRock/releases/v6.5.0rc-pytorch)

**Known gfx1151 issues relevant to audio-model inference**
- hipBLASLt default: ROCm 7.14 known issue "Lower-than-expected LLM inference performance on RDNA3 Radeon GPUs and Ryzen AI MAX / MAX+ Series Processors" with PyTorch earlier than 2.14. Workaround: `TORCH_BLAS_PREFER_HIPBLASLT=1`. This "becomes the default for these architectures in PyTorch 2.14." — [ROCm 7.14.0 release notes](https://github.com/ROCm/ROCm/releases/tag/rocm-7.14.0)
- bf16 instability (TheRock #9198, opened 2026-03-13, still open in triage on 2026-10-16). Reported on PyTorch 2.11 nightly / ROCm 7.11: NaNs with small batch, head_dim 32, deep networks, and high learning rates. These are mostly training, but there are also inference reports: "0x1016 hardware exceptions and BF16 output corruption" with an OCR model on ROCm 7.1 / PyTorch 2.13 (2026-08-09), a MusicGen SIGABRT (2026-04-14), and "unable to fine-tune Whisper" (2026-04-20). An AMD engineer asked whether the OCR reporter had tried ROCm 7.14 and got no recorded answer. — [ROCm #6034 → TheRock #9198](https://github.com/ROCm/ROCm/issues/6034)
- Flash attention / SDPA: `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1` cut SDPA from ~44 ms to ~2.3 ms per call on gfx1151 (Mar 2026). On 2026-03-17 AMD said this is "still an experimental feature" and will become the default "once we get it stable." The same flag plus `MIOPEN_DEBUG_CONV_DIRECT=0` stopped `hipErrorLaunchFailure` crashes in one LoRA workload (2026-05-17). — [ROCm #6034](https://github.com/ROCm/ROCm/issues/6034)
- SDPA with non-contiguous inputs is much slower on gfx1151 at long sequence lengths. Making the inputs contiguous first gave up to +41% (PyTorch 2.14.0a0+rocm7.15 nightly, 2026-07-16; issue closed). The PyTorch HIP notes now cite gfx1151 as a case where `.contiguous()` before SDPA "has been observed to be a large win." — [pytorch #190154](https://github.com/pytorch/pytorch/issues/190154); [PyTorch HIP notes](https://github.com/pytorch/pytorch/blob/main/docs/source/notes/hip.rst)
- `HSA_OVERRIDE_GFX_VERSION` "was never meant to be a consumer-oriented feature" (AMD, 2026-03-17). Native gfx1151 builds should not need it. — [ROCm #6034](https://github.com/ROCm/ROCm/issues/6034)
- `PYTORCH_HIP_ALLOC_CONF=backend:malloc` in some shell profiles crashes PyTorch on gfx1151 (2026-03). — [ROCm #6034](https://github.com/ROCm/ROCm/issues/6034)
- Historical (2025): rocBLAS gfx1151 kernels ran 2–6× slower than gfx1100 kernels (ROCm issue #4748), hipBLASLt was absent for gfx1151 in ROCm 6.4.1, and AOTriton had "Flash attention was not compiled for current AMD GPU architecture" errors. These describe 2025-era ROCm 6.4.x only. — [llm-tracker Strix Halo (2025)](https://llm-tracker.info/_TOORG/Strix-Halo)

### Inferences
- On Ubuntu 24.04.5 with the HWE 7.0 kernel, the officially supported path is ROCm 10.1 (TheRock) with the inbox amdgpu driver. For PyTorch-based ASR (HF Transformers Whisper, Qwen3-ASR via transformers, NeMo), use TheRock `torch[device-gfx1151]` 2.14, which gets the hipBLASLt default. On older torch, set `TORCH_BLAS_PREFER_HIPBLASLT=1`.
- For inference, prefer fp16 over bf16 on gfx1151 until the bf16 reports are resolved. fp16 is the only dtype AMD validated, and the bf16 NaN/corruption reports are open.
- Benchmark `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1` for attention-heavy encoders such as the Whisper encoder. A ~19× SDPA speedup was reported, but AMD calls the flag experimental, so validate output accuracy as well.

**Compatibility map (summary, synthesized from all sections; dates are the latest evidence found)**

| Runtime | gfx1151 iGPU on Linux | Evidence level / date |
|---|---|---|
| ROCm | Official (7.2.1 Radeon/Ryzen docs; 10.1.0 lists Ubuntu 24.04.5 HWE 7.0) | Primary, 2026-03 → 2026-10 |
| PyTorch | TheRock `torch[device-gfx1151]` 2.11–2.14; upstream manywheel includes gfx1151 | Primary, 2026-11 |
| whisper.cpp HIP | Works (ROCm 7.0.1, 2025-10). Needs `GGML_HIP_NO_VMM`. Build broke on ROCm 7.1.x hipBLAS API (2025-12); a long-run crash was reported | Community, 2025-10 → 2026-09 |
| whisper.cpp Vulkan (RADV) | Expected to work; no Linux gfx1151 Whisper benchmark found. Ubuntu 24.04 glslc is too old for best ggml-Vulkan kernels | Community / proxy, 2026-07 |
| CTranslate2 / faster-whisper | Works with the official CT2 ROCm wheel (gfx1151 in build targets) | Primary + community benchmark, 2026-04 → 2026-10 |
| ONNX Runtime | ROCm EP removed after 1.22 (1.22.1 wheel lacks gfx1151 kernels). MIGraphX plugin EP exists, but there is no gfx1151 ASR report | Community + primary, 2026-06 → 2026-10 |
| vLLM | Officially listed (needs ROCm ≥ 7.0.2). Qwen3-ASR is a supported model. Many open gfx1151 bugs; no Qwen3-ASR-on-gfx1151 report | Primary, 2026-10/11 |
| llama.cpp mtmd | Qwen3-ASR 0.6B/1.7B, Voxtral, Qwen2.5/3-Omni, Gemma 4 audio GGUF supported. No gfx1151-specific audio report | Primary docs, 2026-11 |
| NeMo (Parakeet) | Works on ROCm torch (gfx1100) with CUDA-graph decoder disabled; not reported on gfx1151 | Community, 2026-07 |
| XDNA2 NPU | Whisper large-v3-turbo runs via FastFlowLM on Linux (Strix Point measured). Ryzen AI SW Linux: NPU-only, no Whisper listed; whisper.cpp-NPU is Windows-only | Primary + community, 2026-03 → 2026-10 |

### Gaps
- I could not open the full ROCm 10.0.0 release notes or the 7.14/10.x "AMD hardware support" table rows for Ryzen AI Max 300. That the 300 series stayed supported through 7.14 is inferred from the 7.2.1 docs and the 10.1 table.
- I did not confirm which pytorch.org stable release (2.10, 2.11, …) first shipped gfx1151 kernels in its `rocm*` wheel index. Only the current main build script was checked.
- No AMD statement says whether bf16 issue TheRock #9198 is fixed in ROCm 10.x.

## 2. How do whisper.cpp HIP vs Vulkan backends compare on Strix Halo (speed, stability, flash-attention), and are there known gfx1151 bugs?

### Takeaway
Both backends run on gfx1151, but I found no published like-for-like whisper.cpp HIP vs Vulkan benchmark on Linux Strix Halo. Evidence is limited to HIP-only and Windows-Vulkan-only data points, plus llama.cpp (same ggml backends) as a proxy. In the proxy, HIP wins prefill and Vulkan wins token generation. Whisper's runtime is dominated by the encoder, which looks like prefill, so HIP may have the edge there, but that is unverified. On the HIP side, `GGML_HIP_NO_VMM=ON` is needed on gfx1151, and there are reports of a build break with ROCm 7.1.x and a long-run memory-aperture crash. On the Vulkan side, Ubuntu 24.04's stock `glslc` is too old and silently drops some ggml-Vulkan kernels.

### Cited Findings
**whisper.cpp HIP on gfx1151**
- whisper.cpp 1.8.0 builds and runs with HIP on Strix Halo: Ubuntu 25.04, ROCm 7.0.1, `-DGGML_HIP=ON -DGPU_TARGETS=gfx1151`, flash attention enabled (`flash attn = 1`) with no problems reported. ggml-base.en transcribed 2043.9 s of audio in 35.3 s (encode ~23.89 ms/run, decode ~1.82 ms/run), an RTF of about 0.017 (my calculation). The ffmpeg 8.0 whisper filter took ~19 s with `queue=15` (2025-10-07). — [whisper.cpp discussion #3460](https://github.com/ggml-org/whisper.cpp/discussions/3460) / [issue #3459](https://github.com/ggml-org/whisper.cpp/issues/3459)
- Bug: "ROCm 7.1.x breaks HIP backend in ggml." `hipblasGemmEx` / `hipblasGemmStridedBatchedEx` type mismatches (`hipblasDatatype_t` vs `hipDataType` / `hipblasComputeType_t`) stopped compilation on Arch ROCm 7.1.0/7.1.1 (opened 2025-12-03). It was closed by the stale bot on 2026-09-06, not by a confirmed fix. — [whisper.cpp #3553](https://github.com/ggml-org/whisper.cpp/issues/3553)
- Bug: on Strix Halo (Framework Desktop, Debian Trixie, ROCm 7), whisper.cpp crashed within about 24 h with `HSA_STATUS_ERROR_MEMORY_APERTURE_VIOLATION` (opened 2025-12-25, closed 2026-06-27; the resolution is not shown in the thread). — [whisper.cpp #3576](https://github.com/ggml-org/whisper.cpp/issues/3576)
- The dedicated whisper.cpp Strix Halo container project (created 2026-09-16) ships a `rocm-fedora43` image ("HIP, gfx1151, no VMM", standalone validation pending) and a `vulkan-radv` image ("Experimental; GPU validation pending"). It states "No performance results are claimed yet." — [dohr-michael/whisper-strix-halo-toolboxes](https://github.com/dohr-michael/whisper-strix-halo-toolboxes)
- Community benchmark (ROCm 6.4.3, 2025-10): "whisper.cpp Large-v3 Model + GPU: 4.45x faster than real-time (11s audio in 1.27s)" on the 8060S, against CTranslate2 large-v3 GPU at 9× (11 s in 1.22 s). Note the internal inconsistency: 11 s / 1.27 s ≈ 8.7×, not 4.45×. Treat this number as unreliable. — [davidguttman/whisper-rocm](https://github.com/davidguttman/whisper-rocm)
- Latest whisper.cpp release: v1.9.5 (2026-10-06). — [whisper.cpp releases](https://github.com/ggml-org/whisper.cpp/releases)

**whisper.cpp Vulkan**
- A reply in the Strix Halo thread (2025-11-20): whisper.cpp v1.8.1 Vulkan (`-DGGML_VULKAN=ON`, full Vulkan SDK needed) with ggml-large-v3-turbo transcribed 1 h 20 min of audio in about 3 min (≈27× real time, my calculation). This was on Windows, not Linux, and the thread excerpt does not clearly confirm the reply's hardware was Strix Halo. — [whisper.cpp discussion #3460](https://github.com/ggml-org/whisper.cpp/discussions/3460)
- Vulkan flash-attention crashes exist on other AMD parts. whisper-server crashed in `amdvlk64.dll` with flash attention on an RX 9070 XT (RDNA4, Windows AMDVLK, 2026-05). Beam size 8 + VAD crashed on a Radeon 780M (RDNA3 iGPU, 2026-03). Both are closed. Neither is gfx1151 on Linux RADV. — [whisper.cpp #3806](https://github.com/ggml-org/whisper.cpp/issues/3806); [whisper.cpp #3723](https://github.com/ggml-org/whisper.cpp/issues/3723)
- I found no open whisper.cpp issue that mentions gfx1151, the 8060S or Strix Halo on Vulkan (GitHub search, 2026-11-01). — [whisper.cpp issues](https://github.com/ggml-org/whisper.cpp/issues)

**Proxy: llama.cpp (same ggml HIP/Vulkan backends) on gfx1151**
- "Known-good" gfx1151 HIP stack (2026-03-22): ROCm 7.2.0, `GPU_TARGETS=gfx1151 GGML_HIP_ROCWMMA_FATTN=ON GGML_HIP_NO_VMM=ON`. `GGML_HIP_NO_VMM=ON` is needed because HIP VMM "doesn't work right on this GPU." Update (2026-07-23, kernel 7.0.14, llama.cpp b9870): Vulkan decode is about 80 t/s vs HIP about 59 t/s, while HIP still wins prefill. The author moved generation to Vulkan. Ubuntu 24.04's `glslc` 2023.8 "fails the integer_dot.comp probe," which silently drops the q8_1 integer-dot Vulkan kernels, so a newer glslc (e.g. 2026.3-dev) is required. — [llama.cpp discussion #20856](https://github.com/ggml-org/llama.cpp/discussions/20856)
- A separate HIP vs Vulkan benchmark (ROCm 7.2.2, Ubuntu 26.04) found "no single winner": HIP was about 48% faster on synthetic prefill and Vulkan about 18% faster on generation. Search-snippet level; I did not fetch the repo. — [nabe2030/hip-vs-vulkan-evo-x2](https://github.com/nabe2030/hip-vs-vulkan-evo-x2)
- 2025 state (ROCm 6.4.x): Vulkan pp512 was 881.71 t/s vs HIP 348.96 t/s. HIP needed hipBLASLt (`ROCBLAS_USE_HIPBLASLT=1`) plus rocWMMA and FA to match (986 t/s). — [llm-tracker Strix Halo](https://llm-tracker.info/_TOORG/Strix-Halo)

**Packaging**
- Lemonade Server's `whispercpp` engine lists `vulkan`, `rocm` ("Supported AMD ROCm iGPU/dGPU families") and `cpu` backends on Linux. Its `npu` backend is Windows-only. — [lemonade-sdk/lemonade README](https://github.com/lemonade-sdk/lemonade)

### Inferences
- For Whisper on gfx1151, I expect HIP (with rocWMMA FA and `GGML_HIP_NO_VMM=ON`) to be competitive or better on the encoder, which is compute-bound and prefill-like. Vulkan may win the autoregressive decoder, but Whisper's decoder is small relative to the encoder for large-v3. Turbo has only 4 decoder layers, which shrinks the decode share further. This is an inference from llama.cpp behavior, not a Whisper measurement. Benchmark both with `whisper-bench` and real lecture audio.
- If you build whisper.cpp Vulkan on Ubuntu 24.04, install a newer `glslc` (shaderc) than the distro's 2023.8. Otherwise some integer-dot kernels may be silently skipped.
- Pin a known-good ROCm and whisper.cpp pair, and run long-duration soak tests, given the 24-hour aperture-violation crash report.

### Gaps
- I found no published Linux whisper.cpp large-v3 or large-v3-turbo encode times or RTF on gfx1151 for either backend, and no HIP vs Vulkan Whisper comparison.
- I could not confirm whether the ROCm 7.1 hipBLAS API break (#3553) was fixed upstream in ggml or whether current whisper.cpp builds cleanly against ROCm 7.14/10.x. ggml/llama.cpp builds against ROCm 7.2 are reported working, which suggests it was fixed, but this is unverified for whisper.cpp.

## 3. Can vLLM and Transformers run Qwen3-ASR or other audio LLMs on gfx1151? Any reports?

### Takeaway
vLLM officially lists gfx1151 (it needs ROCm 7.0.2 or newer) and lists Qwen3-ASR as a supported model. Prebuilt ROCm 10.0 wheels and community containers exist. I found no report of Qwen3-ASR (or any audio LLM) actually running in vLLM on gfx1151, and AMD's ROCm 7.14 notes say Qwen3-ASR "might not function correctly" under SGLang on Radeon. vLLM on gfx1151 still has many open correctness and performance bugs. llama.cpp's mtmd officially supports Qwen3-ASR GGUFs and other audio LLMs, which is probably the lowest-risk path on gfx1151, though no gfx1151-specific audio report exists either.

### Cited Findings
**vLLM on gfx1151**
- vLLM ROCm docs list: "Ryzen AI MAX / AI 300 Series (gfx1151/1150)," which "requires ROCm 7.0.2 or above." Prebuilt wheels target ROCm 10.0 (pip-installed TheRock ROCm SDK "including the GPU kernels for every supported architecture"), require Python 3.12 only, and install with `uv pip install vllm --extra-index-url https://wheels.vllm.ai/rocm/`. Legacy `rocm72` wheels are no longer built. — [vLLM ROCm installation doc](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/gpu.rocm.inc.md)
- ROCm 7.14.0 officially supports vLLM 0.23.0, and lists the known issue that vLLM v0.21.0–v0.25.0 has long warmup on Radeon (fixed in v0.26.0). — [ROCm 7.14.0 release notes](https://github.com/ROCm/ROCm/releases/tag/rocm-7.14.0)
- vLLM supported models include `Qwen3ASRForConditionalGeneration` (Qwen/Qwen3-ASR-1.7B) in both the generative and transcription tables. Also listed: Voxtral, Whisper, Granite Speech, Qwen2-Audio, Qwen2.5-Omni, Qwen3-Omni, Kimi-Audio, VibeVoice-ASR, GLM-ASR, FunASR, FireRedASR2, Cohere-Transcribe, and Nemotron 3.5 ASR (via an out-of-tree plugin). By default vLLM refuses audio longer than 600 s (`VLLM_MAX_AUDIO_DECODE_DURATION_S`). — [vLLM supported_models.md](https://github.com/vllm-project/vllm/blob/main/docs/models/supported_models.md)
- Open gfx1151 vLLM bugs (as of 2026-11-01): #57493 "ROCM_ATTN returns different outputs for the same greedy request after other requests" (2026-09-18); #57494 q_gemm.cu fails to compile (missing half atomicAdd); #57614 Navi paged attention accepts unsupported ALiBi / block size 32; #50436 shipped gfx1151 tuned configs unreachable; #63455 AWQ decodes 2.5× slower than BF16 on gfx1151 (2026-10-24). Open PRs include a new `ROCM_RDNA_ATTN` attention backend (#63383, 2026-10-23) and gfx1151 unified-attention tuning (#56232, #52684). — [vLLM issues search "gfx1151"](https://github.com/vllm-project/vllm/issues?q=gfx1151); [vLLM PR #63383](https://github.com/vllm-project/vllm/pull/63383)
- V1 engine on gfx1151: the original report (2026-01-12) said HIP-graph capture hung and `--enforce-eager` was required. On 2026-07-30 a user reported that graph capture "completes on gfx1151 now" with ROCm 7.14 and vLLM 0.26.1 (gpt-oss-20b), but with no measurable speedup at batch 1 (13.20 vs 13.15 tok/s). A user on 2026-08-15 still described vLLM as "ultra-slow fallback mode": the custom paged attention was incompatible (Triton fallback) and there were no tuned FP8 configs. — [vLLM #32180](https://github.com/vllm-project/vllm/issues/32180)
- Community container: kyuz0's `vllm-therock-gfx1151` tracks "stable ROCm 10.0" and the latest stable vLLM (repo pushed 2026-10-20). Tested models are text/VL LLMs only (Llama 3.1 8B, Gemma 4, gpt-oss, Qwen3.6-35B-A3B). AITER is limited to paths verified on gfx1151, and `ROCM_AITER_FA` is not offered because its decode kernel "has no Navi implementation." — [kyuz0/amd-strix-halo-vllm-toolboxes](https://github.com/kyuz0/amd-strix-halo-vllm-toolboxes)
- Lemonade lists a `vllm` engine with a `rocm` backend for "Strix Halo iGPU (gfx1151)" on Linux, marked † experimental. — [lemonade-sdk/lemonade README](https://github.com/lemonade-sdk/lemonade)
- AMD known issue (ROCm 7.14): with SGLang on Radeon GPUs, "some models might not function correctly … including certain Mixture-of-Experts (MoE) models … and Qwen3-ASR models." The recommendation is to use the latest upstream SGLang. — [ROCm 7.14.0 release notes](https://github.com/ROCm/ROCm/releases/tag/rocm-7.14.0)
- A community report of gfx1151 vLLM issues notes that support is "highly sensitive to ROCm wheel provenance and ABI alignment" and that vision paths can fall back to CPU or run out of memory. Search-snippet level; not fetched. — [randomvariable/vllm #4](https://github.com/randomvariable/vllm/issues/4)

**Transformers / qwen-asr**
- The `qwen-asr` package supports transformers (default) and vLLM (`qwen-asr[vllm]`) backends. The official examples use `device_map="cuda:0"` and recommend `flash-attn` (CUDA) for the forced aligner. The docs say nothing about ROCm. — [Qwen3-ASR docs](https://docsearch.algolia.com/mcp/docs/repo/qwenlm/qwen3-asr); [Qwen/Qwen3-ASR-0.6B model card](https://huggingface.co/Qwen/Qwen3-ASR-0.6B)
- A GitHub search of QwenLM/Qwen3-ASR issues for "ROCm OR AMD" returned no results (2026-11-01). — [QwenLM/Qwen3-ASR issues](https://github.com/QwenLM/Qwen3-ASR/issues)
- Whisper fine-tuning (Transformers) failed on gfx1151 in one report (2026-04-20, nightly ROCm). — [ROCm #6034](https://github.com/ROCm/ROCm/issues/6034)

**llama.cpp / GGUF audio (mtmd)**
- llama.cpp `libmtmd` supports audio input in `llama-server` (OpenAI-compatible `/chat/completions`), `llama-cli` and `llama-mtmd-cli`. Listed audio models: Ultravox 0.5, Voxtral-Mini-3B-2507, Qwen3-ASR-0.6B / 1.7B (`ggml-org/Qwen3-ASR-*-GGUF`), Qwen2.5-Omni 3B/7B, Qwen3-Omni-30B-A3B, and Gemma 4 E2B/E4B. The docs say Qwen2-Audio has no pre-quantized GGUF "as they have very poor result." — [llama.cpp docs/multimodal.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md)
- llama.cpp runs on gfx1151 with both HIP and Vulkan (see section 2). A GitHub search found no llama.cpp issue about audio or mtmd on gfx1151. — [llama.cpp discussion #20856](https://github.com/ggml-org/llama.cpp/discussions/20856)

### Inferences
- Lowest-risk route to Qwen3-ASR on gfx1151 today: llama.cpp mtmd with the official GGUFs on Vulkan or HIP. Alternatively, qwen-asr's transformers backend on TheRock PyTorch 2.14 in fp16, with SDPA instead of flash-attn. vLLM should be treated as experimental on gfx1151 for ASR, given the nondeterminism bug in `ROCM_ATTN` (#57493) and the absence of audio-model validation.
- If you try vLLM, use the official ROCm 10.0 wheel (Python 3.12) or kyuz0's container, and compare outputs against a CPU/CUDA reference. Greedy nondeterminism would directly hurt ASR reproducibility.

### Gaps
- No primary or community report found of Qwen3-ASR, Voxtral, Whisper, or any other audio model running in vLLM or Transformers on gfx1151, and no throughput numbers.
- No report found of llama.cpp mtmd Qwen3-ASR accuracy or speed on gfx1151, or of GGUF ASR transcription quality compared with the reference implementation.

## 4. Is CTranslate2 (faster-whisper/WhisperX) usable on ROCm/gfx1151? (Also: ONNX Runtime and NeMo)

### Takeaway
Yes. CTranslate2's official ROCm Python wheels (attached to each GitHub release as `rocm-python-wheels-Linux.zip`) are compiled with gfx1151 in the HIP targets against ROCm 7.2. A reproducible community recipe ran faster-whisper large-v3 fp16 at 6.5–11.5× real time on Strix Halo (Apr 2026). The one WhisperX-specific gap: I found no report, though its components (CT2 plus PyTorch) both run. ONNX Runtime is weaker: the ROCm EP was removed after 1.22 and its last wheel lacks gfx1151 kernels, and no gfx1151 ASR report exists for the MIGraphX plugin EP. NeMo Parakeet works on ROCm PyTorch (shown on gfx1100) with the CUDA-graph decoder disabled.

### Cited Findings
**CTranslate2 / faster-whisper**
- CT2's Linux ROCm wheel build script installs ROCm 7.2.0 and sets `PYTORCH_ROCM_ARCH="gfx1030;gfx1100;gfx1101;gfx1102;gfx1150;gfx1151;gfx1200;gfx1201"`, which is passed as `-DCMAKE_HIP_ARCHITECTURES`. The Windows ROCm build uses TheRock `rocm[libraries,devel]==10.0.0`. — [CTranslate2 prepare_build_environment_linux_rocm.sh](https://github.com/OpenNMT/CTranslate2/blob/master/python/tools/prepare_build_environment_linux_rocm.sh); [CI workflow](https://github.com/OpenNMT/CTranslate2/blob/master/.github/workflows/ci.yml)
- Latest CT2 release v4.8.4 (2026-10-25) ships `rocm-python-wheels-Linux.zip`. Changes include "Use the caching allocator by default on HIP (#2118)," a Wav2Vec2-BERT fp16 fix, and new audio ops. Earlier: v4.8.3 (2026-10-13), v4.8.2 (2026-08-31), v4.8.0 (2026-06-06), v4.7.2 (2026-05-19). — [CTranslate2 releases](https://github.com/OpenNMT/CTranslate2/releases)
- Recipe (Ubuntu 26.04, ROCm 7.2.2 from AMD's apt repo, inbox amdgpu, no `HSA_OVERRIDE_GFX_VERSION`, CT2 4.7.1 official ROCm wheel, device name `"cuda"`, dated Apr 2026). Supported compute types on the device: float16, bfloat16, float32, int8, int8_float16, int8_float32, int8_bfloat16. Benchmarks for faster-whisper large-v3 fp16, beam 5:
  - 11 s English JFK clip: about 11.5× real time (runs 3–10).
  - 30 min 44 s Japanese, VAD off, `condition_on_previous_text=False`: 6.56× real time, 4 min 41 s wall time, peak VRAM about 35.2 GB.
  - 3-minute Japanese clips with default settings: 3.11× and 3.35×.
  - Known issues: defaults produced hallucinations, dropped segments and U+FFFD characters on Japanese, and `amd-smi` shows N/A on the APU (use `rocm-smi -u`). Turbo was not tested.
  — [nabe2030/faster-whisper-rocm-strix-halo](https://github.com/nabe2030/faster-whisper-rocm-strix-halo)
- Earlier community build (ROCm 6.4.3, CT2 from source with `-DCMAKE_HIP_ARCHITECTURES=gfx1151`, 2025-10): CT2 large-v3 GPU 9× real time (11 s in 1.22 s), tiny 138×, large-v3 CPU 4.06×. The Docker ROCm 6.1 image fell back to CPU because rocBLAS TensileLibrary lacked gfx1151. — [davidguttman/whisper-rocm](https://github.com/davidguttman/whisper-rocm)
- CTranslate2 on AMD GPUs is also described in an AMD ROCm blog (date not checked). — [ROCm blog: CTranslate2 on AMD GPUs](https://rocm.blogs.amd.com/artificial-intelligence/ctranslate2/README.html)

**ONNX Runtime**
- ONNX Runtime marks the AMD ROCm EP as deprecated and lists MIGraphX as the AMD provider. — [ONNX Runtime Execution Providers](https://onnxruntime.ai/docs/execution-providers/); [MIGraphX EP docs](https://onnxruntime.ai/docs/execution-providers/MIGraphX-ExecutionProvider.html)
- The ROCm EP "was last shipped in ONNX Runtime 1.22.x (AMD replaced it with MIGraphX in 1.23+)." On gfx1151, the `onnxruntime_rocm` 1.22.1 wheel's precompiled Tensile kernels cover gfx900–gfx1201 "but not gfx1151," so it needs `HSA_OVERRIDE_GFX_VERSION=11.0.0` ("without it, inference segfaults on gfx1151"). This was verified with Parakeet TDT 0.6B ONNX on a Ryzen AI Max+ 395 on a ROCm 7.2 base. ROCm output was "97% word-identical to CPU" (punctuation-only differences). The PR was opened 2026-10-26 and closed unmerged. — [achetronic/parakeet PR #28](https://github.com/achetronic/parakeet/pull/28)
- The MIGraphX EP is now also distributed as a plugin EP (`onnxruntime-ep-migraphx`). Requesting it with `providers=["MIGraphXExecutionProvider", ...]` silently gives a CPU-only session. `SessionOptions.add_provider_for_devices` works (reported 2026-10-23, open). — [onnxruntime #33556](https://github.com/microsoft/onnxruntime/issues/33556)
- On a Framework Desktop (Strix Halo), onnxruntime-migraphx "fails silently" (Fedora 44, 2026-06-19). The AMD reply: the MIGraphX and ORT EP in ROCm 7.2.4 are built only for Python 3.12, and pip otherwise falls back to a community wheel. — [AMDMIGraphX #4997](https://github.com/ROCm/AMDMIGraphX/issues/4997)

**NeMo (Parakeet/Canary)**
- `nvidia/parakeet-tdt-0.6b-v3` on ROCm PyTorch (torch 2.9.1+rocm6.4, AMD gfx1100) crashes with "Failed to dlopen libcuda.so.1" when `cuda-python` is installed. Workarounds: `decoding.greedy.use_cuda_graph_decoder = False` or uninstall `cuda-python`. The reporter "transcribed ~650 h of audio on ROCm this way" (2026-07-11, open). The NeMo GitHub repo now resolves to `NVIDIA-NeMo/Speech`. — [NVIDIA-NeMo/Speech #15905](https://github.com/NVIDIA-NeMo/Speech/issues/15905)

### Inferences
- faster-whisper on gfx1151 is the most thoroughly documented GPU ASR path. Use the CT2 ROCm wheel from the GitHub release zip (not PyPI) with a matching system ROCm 7.2.x in `/opt/rocm/lib`. The wheel links against system ROCm libraries. Whether it runs against ROCm 10.x / TheRock libraries was not verified.
- WhisperX should work in principle: faster-whisper (CT2 ROCm) plus wav2vec2 alignment and pyannote diarization on TheRock PyTorch. This is not verified by any report. Watch for PyTorch/CT2 ROCm library version clashes in one process; the whisper-rocm repo notes that PyTorch bundles its own ROCm libraries.
- NeMo Parakeet/Canary on gfx1151 is plausible via TheRock PyTorch with the CUDA-graph decoder disabled, but has only been shown on gfx1100.

### Gaps
- No faster-whisper large-v3-turbo, distil, or int8 benchmark on gfx1151 found. No WhisperX report found.
- No report of Whisper ONNX via the MIGraphX EP on gfx1151, and no ONNX Runtime Vulkan EP source found.
- I did not determine which CT2 version first shipped official ROCm wheels.

## 5. Can the XDNA2 NPU run ASR on Linux today, and with what toolchain?

### Takeaway
Yes, with limits. On Linux, Whisper large-v3-turbo runs on the XDNA2 NPU through FastFlowLM (FLM). FLM has had native Linux support since 2026-03-11 and is integrated with Lemonade. The stack is the in-kernel `amdxdna` driver (mainline since 6.14; kernel 7.0 is fine) plus XRT (`libxrt-npu2`) and NPU firmware ≥ 1.1.0.0. FLM's NPU kernels are closed-source binaries, though free to use. AMD's own Ryzen AI Software on Linux (1.9.0) supports only an NPU flow for CNN, BERT-class and LLM models, and does not list Whisper. The whisper.cpp NPU backend (Ryzen AI 1.7+, Lemonade) is Windows-only.

### Cited Findings
- Kernel/driver: the amdxdna driver is required. It is "in the Linux 7.0+ kernel," with `amdxdna-dkms` backports for 6.x. On Ubuntu 24.04, add `ppa:lemonade-team/stable` and install `libxrt-npu2` and `amdxdna-dkms`. Requirements: `linux-firmware` ≥ 20260221, NPU firmware ≥ 1.1.0.0, and memlock raised above 8 MB. The NPU "won't be detected if `amd_iommu=off`" is set, which Strix Halo users often set for llama.cpp. Supported: Strix Halo, Strix/Kraken Point, Gorgon Point. XDNA1 is unsupported. The page says LLMs and Whisper run on the XDNA2 NPU under Linux (2026-03-11). — [Lemonade: FLM on Linux](https://lemonade-server.ai/flm_npu_linux.html)
- The amd/xdna-driver README says kernel ≥ 6.10 is required, Ubuntu 25.04's kernel 6.14 includes amdxdna, and the kernel driver lives in `drivers/accel/amdxdna/`. — [amd/xdna-driver](https://github.com/amd/xdna-driver)
- FLM "supports all Ryzen AI Series chips with XDNA2 NPUs (Strix, Strix Halo, Kraken, and Gorgon Point)." Linux support was announced 2026-03-11. Orchestration code is MIT, but "the NPU-accelerated binary kernels are not open source" (free for commercial use). The repo now resolves to `ROCm/FastFlowLM`. Latest release v1.0.11 (2026-10-29). — [FastFlowLM README](https://github.com/ROCm/FastFlowLM); [FLM releases](https://github.com/FastFlowLM/FastFlowLM/releases)
- FLM v1.0.10 (2026-10-22) changes to Whisper:
  - `/v1/audio/transcriptions` now supports `language`, `prompt` and `response_format` (json/text/srt/vtt/verbose_json with timestamps).
  - A decode-loop fix removed a forced timestamp every 16 tokens, which "took the word error rate from 7.2% to 3.1%" on 82 English clips.
  - The language token is now fed to the decoder (before, it was detected but never passed back).
  - Fixed repetition at 30 s window boundaries.
  - Fixed a Lemonade-on-Linux launch failure from v1.0.8/1.0.9.
  — [FLM v1.0.10 release](https://github.com/FastFlowLM/FastFlowLM/releases/tag/v1.0.10)
- Measured on Linux (Arch, kernel 7.1.9, Strix Point Ryzen AI 9 365, not Strix Halo; FLM v1.0.2, XRT 2.21.75; post dated Sep 3, year implied 2026):
  - Model: `whisper-v3:turbo` (q4nx, about 650 MB) on the NPU.
  - Speed: a 30 s clip in about 5.2 s warm, RTF ≈ 0.17–0.19, against whisper.cpp CPU at 16 threads with RTF 0.22.
  - Power: about 20 W package and about 45 J per transcription on the NPU, against about 73 W and about 410 J on the CPU.
  - Limits: FLM weights and xclbins are FLM-specific (not usable in llama.cpp or ONNX Runtime), and memlock must be unlimited.
  — [DEV: Running Whisper + LLMs on an AMD NPU under Linux](https://dev.to/jac-76/running-whisper-llms-on-an-amd-npu-under-linux-2o1h)
- Ryzen AI Software 1.9.0 Linux page: Ubuntu 24.04, kernel ≥ 6.10, Python 3.12, XRT plus the amdxdna plugin. "Linux currently supports NPU only flow." Model types: CNN (INT8/BF16), NLP encoders such as BERT (BF16), and LLMs. Whisper/ASR is not listed. — [Ryzen AI SW Linux](https://ryzenai.docs.amd.com/en/latest/linux.html)
- Ryzen AI release notes: 1.7 "Whisper.cpp integration enabling scalable ASR support." 1.7.1 "installer is also available on Linux." 1.8 Whisper.cpp short audio: "3-second audio RTF reduced to 13.9% (Whisper small)," plus "Model generation is not supported on Linux in this release. Models generated on Windows are compatible with Linux." The platform for Whisper.cpp NPU is not stated. — [Ryzen AI release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html)
- Lemonade lists `whispercpp` + `npu` (XDNA2) as Windows-only and `flm` + `npu` as Windows and Linux. — [lemonade-sdk/lemonade README](https://github.com/lemonade-sdk/lemonade)
- An older ZimaOS hands-on on a Ryzen AI MAX+ 395 concluded the Linux XDNA2 inference stack "has not passed the engineering-validation threshold" and listed whisper.cpp on the NPU as "Planned." It predates the March 2026 FLM Linux release (undated; search-snippet level). — [ZimaOS AMD NPU test](https://www.zimaspace.com/docs/hardware/amd-ryzen-ai-npu-on-zimaos)
- Phoronix covered Ryzen AI NPUs becoming "finally useful under Linux for running LLMs" (not fetched). — [Phoronix](https://www.phoronix.com/news/AMD-Ryzen-AI-NPUs-Linux-LLMs)

### Inferences
- On Ubuntu 24.04 with kernel 7.0, the in-tree amdxdna should already be present. You still need user-space XRT (`libxrt-npu2` from the Lemonade PPA), current linux-firmware, unlimited memlock, and IOMMU left enabled. Then FLM (`flm serve`) exposes an OpenAI-compatible `/v1/audio/transcriptions` for Whisper large-v3-turbo.
- Use FLM v1.0.10 or later. Earlier versions fed no language token to the decoder, which matters for non-English audio such as Korean, and cut segments every 16 tokens.
- The NPU path is attractive mainly for power (about 10× less energy than CPU in the Strix Point test) and for keeping the iGPU free for an LLM. Its throughput (RTF ≈ 0.18) is far below the iGPU paths (faster-whisper large-v3 RTF ≈ 0.09–0.15 on gfx1151).

### Gaps
- No Strix Halo-specific NPU Whisper RTF found. No FLM Whisper accuracy data for Korean or other non-English languages. No confirmation of which Whisper sizes besides v3-turbo are in FLM's Linux catalog.
- No primary source confirms that AMD's own whisper.cpp-on-NPU (Ryzen AI SW) path works on Linux. Lemonade lists it as Windows-only.

## 6. What RTF/throughput numbers exist for ASR on Strix Halo or similar RDNA3.5 APUs?

### Takeaway
Published numbers are sparse and come from single community runs on short or one-off clips. The best documented is faster-whisper large-v3 fp16 on gfx1151: 11.5× real time on an 11 s clip and 6.56× on 30 min of Japanese with VAD off. I found no published Strix Halo number for large-v3-turbo on the iGPU under Linux. The only turbo figures are from Windows Vulkan (≈27×, hardware not confirmed) and the XDNA2 NPU on Strix Point (RTF ≈ 0.18).

### Cited Findings
| Engine / backend | Model | Hardware / OS / stack | Result | Date | Source |
|---|---|---|---|---|---|
| faster-whisper (CT2 4.7.1 ROCm wheel), fp16, beam 5 | large-v3 | Strix Halo gfx1151, Ubuntu 26.04, ROCm 7.2.2 | 11.5× RT (11 s EN); 6.56× RT (30 m 44 s JA, VAD off, no prev-text cond.); 3.11–3.35× with defaults (3 min JA); peak VRAM ~35.2 GB | Apr 2026 | [nabe2030](https://github.com/nabe2030/faster-whisper-rocm-strix-halo) |
| CTranslate2 (source build) | large-v3 / tiny | gfx1151, ROCm 6.4.3 | 9× RT (11 s in 1.22 s) / 138× | Oct 2025 | [davidguttman/whisper-rocm](https://github.com/davidguttman/whisper-rocm) |
| whisper.cpp HIP | large-v3 | gfx1151, ROCm 6.4.3 | "4.45×" (11 s in 1.27 s, which is internally inconsistent) | Oct 2025 | [davidguttman/whisper-rocm](https://github.com/davidguttman/whisper-rocm) |
| whisper.cpp 1.8.0 HIP, FA on | base.en | gfx1151, Ubuntu 25.04, ROCm 7.0.1 | 2043.9 s audio in 35.3 s (RTF ≈ 0.017) | 2025-10-07 | [whisper.cpp #3460](https://github.com/ggml-org/whisper.cpp/discussions/3460) |
| whisper.cpp 1.8.1 Vulkan | large-v3-turbo | Windows (hardware not explicitly confirmed as Strix Halo) | 1 h 20 m in ~3 min (≈27× RT) | 2025-11-20 | [whisper.cpp #3460](https://github.com/ggml-org/whisper.cpp/discussions/3460) |
| FastFlowLM NPU | whisper-v3:turbo (q4nx) | Strix Point XDNA2 (Ryzen AI 9 365), Arch, kernel 7.1.9 | RTF ≈ 0.18 (30 s clip in ~5.2 s), ~20 W package | 2026 (Sep 3 post) | [dev.to](https://dev.to/jac-76/running-whisper-llms-on-an-amd-npu-under-linux-2o1h) |
| whisper.cpp CPU, 16 threads | large-v3-turbo | Strix Point CPU | RTF 0.22 | 2026 | [dev.to](https://dev.to/jac-76/running-whisper-llms-on-an-amd-npu-under-linux-2o1h) |
| Ryzen AI SW whisper.cpp NPU | Whisper small | Ryzen AI NPU (platform not stated; likely Windows) | 3 s audio RTF 13.9% | Ryzen AI 1.8 | [Ryzen AI relnotes](https://ryzenai.docs.amd.com/en/latest/relnotes.html) |
| ONNX Runtime ROCm EP 1.22.1 | Parakeet TDT 0.6B | gfx1151 (HSA override 11.0.0), ROCm 7.2 | accuracy only (97% word-identical to CPU), no speed figure | 2026-10-26 | [parakeet PR #28](https://github.com/achetronic/parakeet/pull/28) |
| NeMo | parakeet-tdt-0.6b-v3 | gfx1100 dGPU (not APU), torch 2.9.1+rocm6.4 | ~650 h transcribed, no RTF given | 2026-07-11 | [NeMo #15905](https://github.com/NVIDIA-NeMo/Speech/issues/15905) |

- Reference point (not AMD): on discrete NVIDIA GPUs, turbo is "about twice as fast as large-v3 on the same hardware," and large-v3-turbo int8 ranges 27–58× real time across datacenter GPUs. — [RunPod Whisper GPU benchmarks](https://www.runpod.io/articles/guides/best-gpu-for-whisper)

### Inferences
- Applying the roughly 2× turbo-vs-large-v3 rule from NVIDIA data, faster-whisper large-v3-turbo on gfx1151 might reach about 12–20× real time on long-form audio with VAD off. That is an extrapolation, not a measurement.
- In the only head-to-head (Oct 2025, ROCm 6.4.3), CT2 was about 2× whisper.cpp HIP on large-v3. That result is old and the whisper.cpp figure is internally inconsistent, so re-benchmark on ROCm 10.x with current whisper.cpp v1.9.5.
- The ~35 GB peak VRAM in the faster-whisper run likely reflects allocator caching in unified memory rather than model needs. CT2 4.8.4 made the caching allocator the default on HIP. This is unverified.

### Gaps
- No Linux iGPU RTF found for whisper large-v3-turbo on gfx1151 in any engine. No HIP vs Vulkan Whisper numbers. No Qwen3-ASR, Voxtral, or Parakeet throughput on gfx1151. No WER measurements on gfx1151 vs CPU/CUDA references, beyond the Parakeet "97% word-identical" note. No Phoronix or OpenBenchmarking whisper.cpp GPU result for Strix Halo found.
