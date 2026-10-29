(() => {
  "use strict";

  // V8.0-delta: gamma PDF events remain the immutable lecture source of truth.
  // Playback derives PDF viewer state from recording_time without appending events.


  // V6.4.3 recorder lease ID. sessionStorage survives a page reload in the
  // same tab, so the backend can distinguish a legitimate reconnect from a
  // second browser tab trying to capture the same session.
  const RECORDER_CLIENT_ID_KEY = "local-clova-recorder-client-id";
  let recorderClientId = sessionStorage.getItem(RECORDER_CLIENT_ID_KEY);
  if (!recorderClientId) {
    recorderClientId = (globalThis.crypto?.randomUUID?.()
      || `client-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    sessionStorage.setItem(RECORDER_CLIENT_ID_KEY, recorderClientId);
  }

  const SR = 16000;
  const CHUNK_MS = 250;

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  const state = {
    library: { subjects: [], professors: [], sessions: [] },
    sessionId: null,
    session: null,
    segments: [],
    layer: "final",
    search: "",
    running: false,
    recordingPollTimer: null,
    recordingPollBusy: false,
    recordingPollGeneration: 0,
    recordingRenderedKey: null,
    captureWarningShown: false,
    captureStalled: false,
    stream: null,
    ctx: null,
    source: null,
    processor: null,
    buffer: new Float32Array(0),
    pushing: false,
    refreshingSegments: false,
    editingSegment: null,
    playingSegment: null,
    playingWordKey: null,
    collapsedSubjects: new Set(),
    assignNewSubjectToSession: false,
    followLatest: true,
    postprocessPollTimer: null,
    postprocessPollSessionId: null,
    showDeletedSegments: false,
    autoPlayActive: false,
    autoPlayFollow: true,
    autoPlayLoading: false,
    autoPlayPaused: false,
    autoPlayUsingWebAudio: false,
    programmaticScrollUntil: 0,
    playbackRate: 1,
    playbackCtx: null,
    playbackMaster: null,
    playbackCache: new Map(),
    playbackStretchCache: new Map(),
    playbackStretchLru: [],
    playbackGeneration: 0,
    playbackSources: [],
    playbackSchedule: [],
    playbackList: [],
    playbackNextIndex: 0,
    playbackNextStartTime: 0,
    playbackResumeIndex: 0,
    playbackResumeOffset: 0,
    playbackScheduling: false,
    playbackPumpTimer: null,
    playbackRaf: null,
    playbackCumulative: [],
    playbackTotalDuration: 0,
    scrollAnimationFrame: null,
    theme: "dark",
    visualSessionId: null,
    seenSegmentIds: new Set(),
    freshSegmentUntil: new Map(),
    pdfs: [],
    activePdfId: "",
    pdfPage: 1,
    pdfReading: false,
    pdfImporting: false,
    pdfPersistChain: Promise.resolve(),
    pdfTimelineEvents: [],
    pdfTimelineSchema: "",
    pdfTimelineSessionId: "",
    pdfAutoFollow: true,
    pdfAutoFollowPauseReason: "",
    pdfLastAppliedTimelineKey: "",
    playbackRecordingTime: null,
    pdfZoom: 1,
    pdfGesturePointers: new Map(),
    pdfGesturePan: null,
    pdfGesturePinch: null,
    pdfGestureFrame: null,
    pdfGesturePending: null,
    annotationTool: "pen",
    annotationEvents: [],
    annotationStrokes: new Map(),
    annotationDraft: null,
    annotationPointer: null,
    annotationSuppressUntilClear: false,
    annotationPersistChain: Promise.resolve(),
    annotationResizeObserver: null,
    annotationPendingErase: new Set(),
    columnResizeFrame: null,
  };

  const els = {
    appShell: $("#appShell"),
    libraryNav: $("#libraryNav"),
    search: $("#sessionSearch"),
    emptyState: $("#emptyState"),
    sessionView: $("#sessionView"),
    heading: $("#sessionHeading"),
    headerSubject: $("#headerSubject"),
    headerPostStatus: $("#headerPostStatus"),
    recordingBadge: $("#recordingBadge"),
    stopBtn: $("#stopBtn"),
    resumeBtn: $("#resumeBtn"),
    autoPlayBtn: $("#autoPlayBtn"),
    autoPlayBtnText: $("#autoPlayButtonText"),
    postBtn: $("#postprocessBtn"),
    postBtnText: $("#postprocessButtonText"),
    postProgress: $("#postprocessProgress"),
    postStageLabel: $("#postprocessStageLabel"),
    postPercent: $("#postprocessPercent"),
    postFill: $("#postprocessFill"),
    postMessage: $("#postprocessMessage"),
    postElapsed: $("#postprocessElapsed"),
    postEta: $("#postprocessEta"),
    postStages: $("#postprocessStages"),
    transcriptList: $("#transcriptList"),
    transcriptEmpty: $("#transcriptEmpty"),
    liveCard: $("#liveCard"),
    unfixedText: $("#unfixedText"),
    sessionStats: $("#sessionStats"),
    deletedToggle: $("#deletedToggle"),
    returnToPlaying: $("#returnToPlaying"),
    layerSwitch: $("#layerSwitch"),
    subjectSelect: $("#subjectSelect"),
    tagList: $("#tagList"),
    tagInput: $("#tagInput"),
    addTagBtn: $("#addTagBtn"),
    description: $("#sessionDescription"),
    metaStatus: $("#metaStatus"),
    metaDate: $("#metaDate"),
    metaDuration: $("#metaDuration"),
    metaSegments: $("#metaSegments"),
    metaManual: $("#metaManual"),
    sessionModal: $("#sessionModalBackdrop"),
    subjectModal: $("#subjectModalBackdrop"),
    newSessionForm: $("#newSessionForm"),
    newSessionSubject: $("#newSessionSubject"),
    newSessionName: $("#newSessionName"),
    newSubjectForm: $("#newSubjectForm"),
    subjectName: $("#subjectName"),
    subjectSemester: $("#subjectSemester"),
    subjectEmoji: $("#subjectEmoji"),
    newSessionDenoise: $("#newSessionDenoise"),
    newSessionSttSource: $("#newSessionSttSource"),
    denoiseStrength: $("#denoiseStrength"),
    sttAudioSource: $("#sttAudioSource"),
    denoiseStrengthLabel: $("#denoiseStrengthLabel"),
    professorInput: $("#professorInput"),
    professorOptions: $("#professorOptions"),
    professorAdapterMini: $("#professorAdapterMini"),
    subjectProfessor: $("#subjectProfessor"),
    miniPlayer: $("#miniPlayer"),
    player: $("#segmentPlayer"),
    playerTitle: $("#playerTitle"),
    playerSubtitle: $("#playerSubtitle"),
    playerPrev: $("#playerPrev"),
    playerPause: $("#playerPause"),
    playerNext: $("#playerNext"),
    playbackSpeed: $("#playbackSpeed"),
    themeToggle: $("#themeToggle"),
    autoFollowToggle: $("#autoFollowToggle"),
    gaplessProgress: $("#gaplessProgress"),
    gaplessTrack: $("#gaplessTrack"),
    gaplessFill: $("#gaplessFill"),
    gaplessPosition: $("#gaplessPosition"),
    gaplessSegmentCounter: $("#gaplessSegmentCounter"),
    transcriptPane: $("#transcriptPane"),
    sidebarSplitter: $("#sidebarSplitter"),
    pdfTranscriptSplitter: $("#pdfTranscriptSplitter"),
    pdfPane: $("#pdfPane"),
    headerPdfZone: $("#headerPdfZone"),
    pdfShelf: $("#pdfShelf"),
    pdfFileInput: $("#pdfFileInput"),
    pdfDropZone: $("#pdfDropZone"),
    pdfDropOverlay: $("#pdfDropOverlay"),
    pdfDocumentView: $("#pdfDocumentView"),
    pdfPageImage: $("#pdfPageImage"),
    pdfPageSurface: $("#pdfPageSurface"),
    pdfAnnotationCanvas: $("#pdfAnnotationCanvas"),
    pdfPageLoading: $("#pdfPageLoading"),
    pdfToolPen: $("#pdfToolPen"),
    pdfToolEraser: $("#pdfToolEraser"),
    pdfToolHighlighter: $("#pdfToolHighlighter"),
    pdfPrev: $("#pdfPrev"),
    pdfNext: $("#pdfNext"),
    pdfPageLabel: $("#pdfPageLabel"),
    pdfZoomOut: $("#pdfZoomOut"),
    pdfZoomLabel: $("#pdfZoomLabel"),
    pdfZoomIn: $("#pdfZoomIn"),
    pdfZoomFit: $("#pdfZoomFit"),
    pdfCanonicalRef: $("#pdfCanonicalRef"),
    pdfPaneTitle: $("#pdfPaneTitle"),
    pdfReturnToLecture: $("#pdfReturnToLecture"),
    shutdownOverlay: $("#shutdownOverlay"),
    toastRegion: $("#toastRegion"),
  };

  function currentTranscriptScroller() {
    // PDF OFF keeps the alpha layout where sessionView owns scrolling.
    // PDF READING gives the right transcript column its own scroller.
    if (els.sessionView?.classList.contains("pdf-reading")) return els.transcriptPane;
    return els.sessionView || els.transcriptPane;
  }

  {
    const isTranscriptInteraction = (event) => {
      // In split PDF mode sessionView contains both planes. PDF touches must not
      // pause transcript tracking; only interaction inside transcriptPane does.
      if (!els.sessionView?.classList.contains("pdf-reading")) return true;
      return Boolean(event?.target?.closest?.("#transcriptPane"));
    };
    const interruptAutoFollow = (event) => {
      if (!isTranscriptInteraction(event)) return;
      if (!state.autoPlayActive) return;
      if (state.scrollAnimationFrame) {
        cancelAnimationFrame(state.scrollAnimationFrame);
        state.scrollAnimationFrame = null;
      }
      state.autoPlayFollow = false;
      updateAutoFollowToggle();
      updateReturnToPlaying();
    };

    // Both containers can become the transcript scroller depending on PDF state.
    for (const scroller of [els.sessionView, els.transcriptPane].filter(Boolean)) {
      scroller.addEventListener("wheel", interruptAutoFollow, { passive: true });
      scroller.addEventListener("touchstart", interruptAutoFollow, { passive: true });
      scroller.addEventListener("pointerdown", (event) => {
        if (event.pointerType === "touch") interruptAutoFollow(event);
      }, { passive: true });
      scroller.addEventListener("scroll", () => {
        // A layout resize can emit scroll without user intent. Only explicit
        // wheel/touch events above are allowed to pause playback follow.
        if (scroller === currentTranscriptScroller()) {
          state.followLatest = isNearTranscriptBottom();
        }
      }, { passive: true });
    }
  }

  function toast(message, kind = "info") {
    const el = document.createElement("div");
    el.className = `toast ${kind === "error" ? "error" : ""}`;
    el.textContent = message;
    els.toastRegion.appendChild(el);
    setTimeout(() => el.remove(), 3300);
  }

  const THEME_KEY = "local-clova-theme";
  const DENOISE_PREF_KEY = "local-clova-denoise-strength";
  const STT_SOURCE_PREF_KEY = "local-clova-stt-audio-source";
  const DENOISE_LABELS = ["끔", "약하게", "보통", "강하게"];
  const SIDEBAR_WIDTH_KEY = "local-clova-sidebar-width";
  const PDF_WIDTH_KEY = "local-clova-pdf-width";
  const PDF_ZOOM_KEY = "local-clova-pdf-zoom";
  const SIDEBAR_DEFAULT_WIDTH = 292;
  const PDF_DEFAULT_WIDTH = 620;


  function clampDenoiseStrength(value) {
    return Math.max(0, Math.min(3, Math.round(Number(value) || 0)));
  }

  function updateDenoiseUi(value) {
    const level = clampDenoiseStrength(value);
    if (els.denoiseStrength) els.denoiseStrength.value = String(level);
    if (els.denoiseStrengthLabel) {
      els.denoiseStrengthLabel.textContent = DENOISE_LABELS[level];
      els.denoiseStrengthLabel.dataset.level = String(level);
    }
    return level;
  }


  function normalizeSttAudioSource(value) {
    return String(value || "").toLowerCase() === "clean" ? "clean" : "raw";
  }

  function captureSettings(stream) {
    const track = stream?.getAudioTracks?.()[0];
    const settings = track?.getSettings?.() || {};
    return {
      sampleRate: settings.sampleRate ?? null,
      channelCount: settings.channelCount ?? null,
      echoCancellation: settings.echoCancellation ?? false,
      noiseSuppression: settings.noiseSuppression ?? false,
      autoGainControl: settings.autoGainControl ?? false,
      deviceId: settings.deviceId ?? null,
      browser_requested_raw: true,
    };
  }
  function parseCssRgb(color) {
    const match = String(color || "").match(/rgba?\(\s*(\d+(?:\.\d+)?)\s*[, ]+\s*(\d+(?:\.\d+)?)\s*[, ]+\s*(\d+(?:\.\d+)?)/i);
    return match ? [Number(match[1]), Number(match[2]), Number(match[3])] : null;
  }

  function auditBrightThemeContrast() {
    const candidates = document.querySelectorAll([
      ".modal-primary",
      ".new-session-button",
      ".control-button",
      ".layer-switch button",
      ".segment-action",
      ".playback-speed"
    ].join(","));
    candidates.forEach((el) => el.classList.remove("light-theme-auto-contrast"));
    if (state.theme === "dark") return;
    candidates.forEach((el) => {
      if (!(el instanceof HTMLElement) || !el.textContent?.trim()) return;
      const rgb = parseCssRgb(getComputedStyle(el).color);
      if (!rgb) return;
      const luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
      if (luminance >= 220) {
        el.classList.add("light-theme-auto-contrast");
        console.warn("[THEME CONTRAST] repaired near-white text in bright mode", el);
      }
    });
  }

  function applyTheme(theme, { persist = true } = {}) {
    const allowed = new Set(["dark", "light", "notebook"]);
    const next = allowed.has(theme) ? theme : "dark";
    state.theme = next;
    document.documentElement.dataset.theme = next;
    document.documentElement.style.colorScheme = next === "dark" ? "dark" : "light";
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute("content", next === "dark" ? "#0b0d10" : (next === "notebook" ? "#f5eddd" : "#f5f7fb"));
    }
    if (els.themeToggle) {
      const labels = {
        dark: "현재 다크 모드 · 클릭하여 라이트 모드",
        light: "현재 라이트 모드 · 클릭하여 노트북 모드",
        notebook: "현재 노트북 모드 · 클릭하여 다크 모드",
      };
      const label = labels[next];
      els.themeToggle.title = label;
      els.themeToggle.setAttribute("aria-label", label);
      els.themeToggle.classList.toggle("light-active", next === "light");
      els.themeToggle.classList.toggle("notebook-active", next === "notebook");
    }
    if (persist) localStorage.setItem(THEME_KEY, next);
    requestAnimationFrame(auditBrightThemeContrast);
    if (state.sessionId) renderTranscript();
  }

  function initTheme() {
    const saved = localStorage.getItem(THEME_KEY);
    const validSaved = ["dark", "light", "notebook"].includes(saved) ? saved : null;
    const preferred = globalThis.matchMedia?.("(prefers-color-scheme: light)")?.matches ? "light" : "dark";
    applyTheme(validSaved || preferred, { persist: false });
  }

  function toggleTheme() {
    const cycle = { dark: "light", light: "notebook", notebook: "dark" };
    applyTheme(cycle[state.theme] || "dark");
  }

  function clampNumber(value, min, max, fallback) {
    const n = Number(value);
    return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
  }

  function applySavedColumnWidths() {
    const sidebar = clampNumber(localStorage.getItem(SIDEBAR_WIDTH_KEY), 180, 430, SIDEBAR_DEFAULT_WIDTH);
    const pdf = clampNumber(localStorage.getItem(PDF_WIDTH_KEY), 320, 4096, PDF_DEFAULT_WIDTH);
    state.pdfZoom = clampNumber(localStorage.getItem(PDF_ZOOM_KEY), 0.5, 3, 1);
    document.documentElement.style.setProperty("--sidebar-w", `${sidebar}px`);
    document.documentElement.style.setProperty("--pdf-pane-w", `${pdf}px`);
  }

  function wireColumnResizer(handle, { kind }) {
    if (!handle) return;
    const reset = () => {
      if (kind === "sidebar") {
        localStorage.removeItem(SIDEBAR_WIDTH_KEY);
        document.documentElement.style.setProperty("--sidebar-w", `${SIDEBAR_DEFAULT_WIDTH}px`);
      } else {
        localStorage.removeItem(PDF_WIDTH_KEY);
        document.documentElement.style.setProperty("--pdf-pane-w", `${PDF_DEFAULT_WIDTH}px`);
      }
    };
    handle.addEventListener("dblclick", reset);
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      handle.setPointerCapture?.(event.pointerId);
      document.body.classList.add("column-resizing");
      const startX = event.clientX;
      const rootStyle = getComputedStyle(document.documentElement);
      const startWidth = kind === "sidebar"
        ? parseFloat(rootStyle.getPropertyValue("--sidebar-w")) || SIDEBAR_DEFAULT_WIDTH
        : els.pdfPane?.getBoundingClientRect().width || PDF_DEFAULT_WIDTH;
      const move = (e) => {
        const delta = e.clientX - startX;
        if (kind === "sidebar") {
          const width = clampNumber(startWidth + delta, 180, 430, SIDEBAR_DEFAULT_WIDTH);
          document.documentElement.style.setProperty("--sidebar-w", `${width}px`);
          localStorage.setItem(SIDEBAR_WIDTH_KEY, String(Math.round(width)));
        } else {
          const total = els.sessionView?.getBoundingClientRect().width || window.innerWidth;
          const fullscreen = Boolean(document.fullscreenElement || document.webkitFullscreenElement);
          const sidebarCollapsed = Boolean(els.appShell?.classList.contains("sidebar-collapsed"));
          const transcriptFloor = fullscreen && sidebarCollapsed ? 166 : 186;
          const maxPdf = Math.max(420, total - transcriptFloor - 6);
          const width = clampNumber(startWidth + delta, 420, maxPdf, PDF_DEFAULT_WIDTH);
          if (state.columnResizeFrame) cancelAnimationFrame(state.columnResizeFrame);
          state.columnResizeFrame = requestAnimationFrame(() => {
            document.documentElement.style.setProperty("--pdf-pane-w", `${width}px`);
            localStorage.setItem(PDF_WIDTH_KEY, String(Math.round(width)));
            state.columnResizeFrame = null;
          });
        }
      };
      const up = () => {
        document.body.classList.remove("column-resizing");
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        window.removeEventListener("pointercancel", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up, { once: true });
      window.addEventListener("pointercancel", up, { once: true });
    });
  }

  function pdfPageURL(pdfId, page = 1) {
    const safePage = Math.max(1, Math.round(Number(page) || 1));
    return `/api/pdf/page?pdf_id=${encodeURIComponent(pdfId)}&page=${safePage}`;
  }

  function activePdf() {
    return state.pdfs.find((item) => item.pdf_id === state.activePdfId) || null;
  }

  function renderPdfShelf() {
    if (!els.pdfShelf) return;
    els.pdfShelf.innerHTML = "";

    for (const pdf of state.pdfs) {
      const button = document.createElement("button");
      button.type = "button";
      const selected = state.pdfReading && pdf.pdf_id === state.activePdfId;
      button.className = `pdf-mini-card ${selected ? "active" : ""}`;
      button.title = selected
        ? `${pdf.original_filename || "PDF"} · 클릭하면 PDF 닫기`
        : `${pdf.original_filename || "PDF"} · 클릭하면 읽기`;
      const label = pdf.original_filename || "document.pdf";
      button.innerHTML = `
        <span class="pdf-mini-icon" aria-hidden="true"><b>PDF</b></span>
        <span class="pdf-mini-label">${escapeText(label)}</span>`;
      button.addEventListener("click", () => {
        if (state.pdfReading && state.activePdfId === pdf.pdf_id) {
          setPdfReading(false, { persist: true, manual: true });
          return;
        }
        const page = state.activePdfId === pdf.pdf_id ? state.pdfPage : 1;
        setActivePdf(pdf.pdf_id, page, { reading: true, persist: true, manual: true });
      });
      els.pdfShelf.appendChild(button);
    }

    const add = document.createElement("button");
    add.type = "button";
    add.className = "pdf-mini-add";
    add.disabled = state.pdfImporting;
    add.title = "PDF 추가 · Local Clova에 독립 복사본 저장";
    add.innerHTML = `
      <span class="pdf-mini-icon" aria-hidden="true">+</span>
      <span class="pdf-mini-label">${state.pdfImporting ? "추가 중…" : "추가"}</span>`;
    add.addEventListener("click", () => els.pdfFileInput?.click());
    els.pdfShelf.appendChild(add);
  }

  function renderPdfZoom() {
    const zoom = clampNumber(state.pdfZoom, 0.5, 3, 1);
    state.pdfZoom = zoom;
    if (els.pdfPageSurface) {
      // V8.1-alpha.1: the page surface owns fit-width so the bitmap and the
      // annotation canvas always resize as one registered sheet.
      els.pdfPageSurface.style.setProperty("--pdf-page-width", `${Math.round(zoom * 10000) / 100}%`);
    }
    if (els.pdfPageImage) els.pdfPageImage.style.setProperty("height", "auto", "important");
    requestAnimationFrame(renderAnnotationCanvas);
    if (els.pdfZoomLabel) {
      const pct = `${Math.round(zoom * 100)}%`;
      els.pdfZoomLabel.textContent = pct;
      els.pdfZoomLabel.setAttribute("aria-label", `현재 확대율 ${pct} · 100%로 초기화`);
    }
    if (els.pdfZoomOut) els.pdfZoomOut.disabled = zoom <= 0.5001;
    if (els.pdfZoomIn) els.pdfZoomIn.disabled = zoom >= 2.9999;
  }

  function setPdfZoom(value, { persist = true } = {}) {
    state.pdfZoom = clampNumber(value, 0.5, 3, 1);
    renderPdfZoom();
    if (persist) localStorage.setItem(PDF_ZOOM_KEY, String(state.pdfZoom));
  }

  function changePdfZoom(delta) {
    const step = 0.1;
    setPdfZoom(Math.round((state.pdfZoom + Number(delta || 0) * step) * 10) / 10);
  }

  function fitPdfToWidth() {
    setPdfZoom(1);
    if (els.pdfDropZone) {
      els.pdfDropZone.scrollLeft = 0;
      els.pdfDropZone.scrollTop = 0;
    }
  }


  function annotationId() {
    try {
      return `ann_${crypto.randomUUID().replaceAll("-", "")}`;
    } catch (_) {
      return `ann_${Date.now().toString(16)}${Math.random().toString(16).slice(2, 18)}`;
    }
  }

  function annotationLectureTimeContext() {
    const t = currentPlaybackRecordingTime();
    if (t != null && Number.isFinite(Number(t))) {
      return { anchor_type: "playback", time: Math.max(0, Number(t)), source: "playback_cursor" };
    }
    return { anchor_type: "page_only", time: null, source: null };
  }

  function currentAnnotationLectureTime() {
    return annotationLectureTimeContext().time;
  }

  async function captureAnnotationAnchor() {
    const local = annotationLectureTimeContext();
    if (!state.running || !state.sessionId) {
      return { anchor_type: local.anchor_type, time: local.time, source: local.source, recording_sample: null };
    }
    try {
      const data = await fetchJSON(`/api/annotation/anchor?session_id=${encodeURIComponent(state.sessionId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          client_id: recorderClientId,
          anchor_type: local.anchor_type,
          lecture_time: local.time,
          lecture_time_source: local.source,
        }),
      });
      return {
        anchor_type: String(data.anchor_type || (data.lecture_time == null ? "page_only" : "live_recording")),
        time: data.lecture_time == null ? null : Math.max(0, Number(data.lecture_time)),
        source: data.lecture_time_source == null ? null : String(data.lecture_time_source),
        recording_sample: data.recording_sample == null ? null : (Number.isFinite(Number(data.recording_sample)) ? Number(data.recording_sample) : null),
      };
    } catch (error) {
      console.debug("annotation anchor fallback", error);
      return { anchor_type: local.anchor_type, time: local.time, source: local.source, recording_sample: null };
    }
  }

  function renderAnnotationTools() {
    const tools = [
      [els.pdfToolPen, "pen"],
      [els.pdfToolEraser, "eraser"],
      [els.pdfToolHighlighter, "highlighter"],
    ];
    for (const [button, tool] of tools) {
      if (!button) continue;
      const active = state.annotationTool === tool;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function setAnnotationTool(tool) {
    if (!["pen", "eraser", "highlighter"].includes(tool)) return;
    state.annotationTool = tool;
    renderAnnotationTools();
  }

  function annotationStyle(tool) {
    if (tool === "highlighter") return { color: "#f3d34a", opacity: 0.34, width_norm: 0.018 };
    return { color: "#2563c7", opacity: 1, width_norm: 0.0024 };
  }

  function pageSurfacePoint(event) {
    const surface = els.pdfPageSurface;
    if (!surface || !state.pdfReading || !activePdf()) return null;
    const rect = surface.getBoundingClientRect();
    if (!(rect.width > 1 && rect.height > 1)) return null;
    const cx = Number(event.clientX);
    const cy = Number(event.clientY);
    if (cx < rect.left || cx > rect.right || cy < rect.top || cy > rect.bottom) return null;
    return {
      x: Math.max(0, Math.min(1, (cx - rect.left) / rect.width)),
      y: Math.max(0, Math.min(1, (cy - rect.top) / rect.height)),
      clientX: cx,
      clientY: cy,
    };
  }

  function normalizeAnnotationStroke(item) {
    if (!item || !item.annotation_id || !item.pdf_id) return null;
    const points = (Array.isArray(item.points) ? item.points : [])
      .map((pt) => ({ x: Math.max(0, Math.min(1, Number(pt.x) || 0)), y: Math.max(0, Math.min(1, Number(pt.y) || 0)) }));
    if (!points.length) return null;
    return {
      ...item,
      page: Math.max(1, Math.round(Number(item.page) || 1)),
      tool: item.tool === "highlighter" ? "highlighter" : "pen",
      points,
      erased: Boolean(item.erased),
    };
  }

  async function loadAnnotations(sessionId = state.sessionId, { quiet = true } = {}) {
    state.annotationEvents = [];
    state.annotationStrokes = new Map();
    state.annotationDraft = null;
    state.annotationPointer = null;
    state.annotationPendingErase = new Set();
    if (!sessionId) {
      renderAnnotationCanvas();
      return;
    }
    try {
      const data = await fetchJSON(`/api/annotations?session_id=${encodeURIComponent(sessionId)}`);
      if (state.sessionId !== sessionId) return;
      state.annotationEvents = Array.isArray(data.events) ? data.events : [];
      for (const raw of (Array.isArray(data.active_annotations) ? data.active_annotations : [])) {
        const stroke = normalizeAnnotationStroke(raw);
        if (stroke) state.annotationStrokes.set(stroke.annotation_id, stroke);
      }
      renderAnnotationCanvas();
    } catch (error) {
      if (!quiet) toast(`필기 불러오기 실패: ${error.message}`, "error");
      else console.debug("annotation load skipped", error);
      renderAnnotationCanvas();
    }
  }

  function canvasMetrics() {
    const canvas = els.pdfAnnotationCanvas;
    const surface = els.pdfPageSurface;
    if (!canvas || !surface) return null;
    const width = surface.clientWidth;
    const height = surface.clientHeight;
    if (!(width > 1 && height > 1)) return null;
    const maxCss = Math.max(width, height);
    const dpr = Math.max(0.5, Math.min(Number(window.devicePixelRatio) || 1, 4096 / Math.max(1, maxCss)));
    const bw = Math.max(1, Math.round(width * dpr));
    const bh = Math.max(1, Math.round(height * dpr));
    if (canvas.width !== bw || canvas.height !== bh) {
      canvas.width = bw;
      canvas.height = bh;
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { canvas, ctx, width, height, dpr };
  }

  function drawAnnotationPath(ctx, stroke, width, height) {
    const points = Array.isArray(stroke?.points) ? stroke.points : [];
    if (!points.length) return;
    const style = {
      ...annotationStyle(stroke.tool),
      color: stroke.color || annotationStyle(stroke.tool).color,
      opacity: Number.isFinite(Number(stroke.opacity)) ? Number(stroke.opacity) : annotationStyle(stroke.tool).opacity,
      width_norm: Number(stroke.width_norm) || annotationStyle(stroke.tool).width_norm,
    };
    const lineWidth = Math.max(stroke.tool === "highlighter" ? 7 : 1.5, style.width_norm * width);
    ctx.save();
    ctx.globalAlpha = Math.max(0.05, Math.min(1, style.opacity));
    ctx.strokeStyle = style.color;
    ctx.fillStyle = style.color;
    ctx.lineWidth = lineWidth;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (points.length === 1) {
      ctx.beginPath();
      ctx.arc(points[0].x * width, points[0].y * height, lineWidth / 2, 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.beginPath();
      ctx.moveTo(points[0].x * width, points[0].y * height);
      for (let i = 1; i < points.length; i += 1) ctx.lineTo(points[i].x * width, points[i].y * height);
      ctx.stroke();
    }
    ctx.restore();
  }

  function renderAnnotationCanvas() {
    const metrics = canvasMetrics();
    if (!metrics) return;
    const { ctx, width, height } = metrics;
    ctx.clearRect(0, 0, width, height);
    if (!state.pdfReading || !state.activePdfId) return;
    const page = Math.max(1, Number(state.pdfPage) || 1);
    const expectedTarget = pdfPageURL(state.activePdfId, page);
    if (!els.pdfPageImage?.complete || !els.pdfPageImage?.naturalWidth || els.pdfPageImage.dataset.target !== expectedTarget) return;
    for (const stroke of state.annotationStrokes.values()) {
      if (stroke.erased || stroke.pdf_id !== state.activePdfId || Number(stroke.page) !== page) continue;
      drawAnnotationPath(ctx, stroke, width, height);
    }
    const draft = state.annotationDraft;
    if (draft && draft.pdf_id === state.activePdfId && Number(draft.page) === page) {
      drawAnnotationPath(ctx, draft, width, height);
    }
  }

  function installAnnotationResizeObserver() {
    if (!els.pdfPageSurface || state.annotationResizeObserver) return;
    if (typeof ResizeObserver === "function") {
      state.annotationResizeObserver = new ResizeObserver(() => requestAnimationFrame(renderAnnotationCanvas));
      state.annotationResizeObserver.observe(els.pdfPageSurface);
    } else {
      window.addEventListener("resize", () => requestAnimationFrame(renderAnnotationCanvas));
    }
  }

  function persistAnnotationStroke(stroke) {
    if (!state.sessionId || !stroke) return;
    const optimistic = normalizeAnnotationStroke(stroke);
    if (!optimistic) return;
    state.annotationStrokes.set(optimistic.annotation_id, optimistic);
    renderAnnotationCanvas();
    const anchorPromise = optimistic.anchorPromise || Promise.resolve({
      anchor_type: optimistic.anchor_type || (optimistic.lecture_time == null ? "page_only" : "playback"),
      time: optimistic.lecture_time == null ? null : Number(optimistic.lecture_time),
      source: optimistic.lecture_time_source == null ? null : String(optimistic.lecture_time_source),
      recording_sample: null,
    });
    const sid = state.sessionId;
    state.annotationPersistChain = Promise.resolve(state.annotationPersistChain)
      .catch(() => {})
      .then(async () => {
        try {
          const anchor = await anchorPromise;
          const payload = {
            annotation_id: optimistic.annotation_id,
            pdf_id: optimistic.pdf_id,
            page: optimistic.page,
            tool: optimistic.tool,
            points: optimistic.points,
            anchor_type: String(anchor?.anchor_type || optimistic.anchor_type || (anchor?.time == null && optimistic.lecture_time == null ? "page_only" : "playback")),
            lecture_time: anchor?.time == null
              ? (optimistic.lecture_time == null ? null : Number(optimistic.lecture_time))
              : Number(anchor.time),
            lecture_time_source: anchor?.source == null
              ? (optimistic.lecture_time_source == null ? null : String(optimistic.lecture_time_source))
              : String(anchor.source),
            anchor_recording_sample: Number.isFinite(Number(anchor?.recording_sample)) ? Number(anchor.recording_sample) : null,
            created_at: optimistic.created_at || new Date().toISOString(),
            client_id: recorderClientId,
            pdf_follow_was_auto: Boolean(optimistic.pdf_follow_was_auto),
          };
          const data = await fetchJSON(`/api/annotation/stroke?session_id=${encodeURIComponent(sid)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (state.sessionId !== sid) return;
          const saved = normalizeAnnotationStroke(data.event);
          if (saved) state.annotationStrokes.set(saved.annotation_id, saved);
          if (data.event) state.annotationEvents.push(data.event);
          renderAnnotationCanvas();
        } catch (error) {
          if (state.sessionId === sid) {
            state.annotationStrokes.delete(optimistic.annotation_id);
            renderAnnotationCanvas();
            toast(`필기 저장 실패: ${error.message}`, "error");
          }
        }
      });
  }

  function pointSegmentDistance(px, py, ax, ay, bx, by) {
    const vx = bx - ax;
    const vy = by - ay;
    const wx = px - ax;
    const wy = py - ay;
    const len2 = vx * vx + vy * vy;
    if (len2 <= 1e-9) return Math.hypot(px - ax, py - ay);
    const t = Math.max(0, Math.min(1, (wx * vx + wy * vy) / len2));
    return Math.hypot(px - (ax + t * vx), py - (ay + t * vy));
  }

  function annotationHitAt(point) {
    const surface = els.pdfPageSurface;
    if (!surface || !point) return null;
    const rect = surface.getBoundingClientRect();
    const px = point.x * rect.width;
    const py = point.y * rect.height;
    const candidates = [...state.annotationStrokes.values()].reverse();
    for (const stroke of candidates) {
      if (stroke.erased || stroke.pdf_id !== state.activePdfId || Number(stroke.page) !== Number(state.pdfPage)) continue;
      const pts = stroke.points || [];
      if (!pts.length) continue;
      const widthPx = Math.max(stroke.tool === "highlighter" ? 7 : 1.5, (Number(stroke.width_norm) || annotationStyle(stroke.tool).width_norm) * rect.width);
      const threshold = 13 + widthPx / 2;
      if (pts.length === 1) {
        if (Math.hypot(px - pts[0].x * rect.width, py - pts[0].y * rect.height) <= threshold) return stroke;
        continue;
      }
      for (let i = 1; i < pts.length; i += 1) {
        if (pointSegmentDistance(
          px, py,
          pts[i - 1].x * rect.width, pts[i - 1].y * rect.height,
          pts[i].x * rect.width, pts[i].y * rect.height,
        ) <= threshold) return stroke;
      }
    }
    return null;
  }

  function softEraseAnnotation(stroke, anchorPromise = captureAnnotationAnchor(), createdAt = new Date().toISOString()) {
    if (!stroke || !stroke.annotation_id || state.annotationPendingErase.has(stroke.annotation_id)) return;
    const sid = state.sessionId;
    const snapshot = { ...stroke };
    state.annotationPendingErase.add(stroke.annotation_id);
    state.annotationStrokes.delete(stroke.annotation_id);
    renderAnnotationCanvas();
    state.annotationPersistChain = Promise.resolve(state.annotationPersistChain)
      .catch(() => {})
      .then(async () => {
        try {
          const anchor = await anchorPromise;
          const data = await fetchJSON(`/api/annotation/erase?session_id=${encodeURIComponent(sid)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              target_annotation_id: snapshot.annotation_id,
              operation_anchor_type: String(anchor?.anchor_type || (anchor?.time == null ? "page_only" : "playback")),
              operation_lecture_time: anchor?.time == null ? null : Number(anchor.time),
              operation_lecture_time_source: anchor?.source == null ? null : String(anchor.source),
              anchor_recording_sample: anchor?.recording_sample == null ? null : (Number.isFinite(Number(anchor.recording_sample)) ? Number(anchor.recording_sample) : null),
              created_at: createdAt,
              client_id: recorderClientId,
            }),
          });
          if (state.sessionId === sid && data.event) state.annotationEvents.push(data.event);
        } catch (error) {
          if (state.sessionId === sid) {
            state.annotationStrokes.set(snapshot.annotation_id, snapshot);
            renderAnnotationCanvas();
            toast(`지우개 저장 실패: ${error.message}`, "error");
          }
        } finally {
          state.annotationPendingErase.delete(snapshot.annotation_id);
        }
      });
  }

  function eraseAtEvent(event) {
    const point = pageSurfacePoint(event);
    if (!point) return false;
    const stroke = annotationHitAt(point);
    if (!stroke) return false;
    pausePdfAutoFollowForManualBrowse("필기");
    const anchorPromise = state.annotationPointer?.anchorPromise || captureAnnotationAnchor();
    softEraseAnnotation(stroke, anchorPromise, new Date().toISOString());
    return true;
  }

  function beginAnnotationPointer(event) {
    const point = pageSurfacePoint(event);
    if (!point || state.annotationSuppressUntilClear) return false;
    if (state.annotationTool === "eraser") {
      state.annotationPointer = {
        pointerId: event.pointerId,
        pointerType: event.pointerType,
        mode: "eraser",
        anchorPromise: captureAnnotationAnchor(),
      };
      eraseAtEvent(event);
      return true;
    }
    const followWasAuto = Boolean(state.pdfAutoFollow);
    const timeContext = annotationLectureTimeContext();
    const anchorPromise = captureAnnotationAnchor();
    const draft = {
      annotation_id: annotationId(),
      pdf_id: state.activePdfId,
      page: Math.max(1, Number(state.pdfPage) || 1),
      tool: state.annotationTool === "highlighter" ? "highlighter" : "pen",
      ...annotationStyle(state.annotationTool),
      points: [{ x: point.x, y: point.y }],
      anchor_type: timeContext.anchor_type,
      lecture_time: timeContext.time,
      lecture_time_source: timeContext.source,
      anchorPromise,
      pdf_follow_was_auto: followWasAuto,
      created_at: new Date().toISOString(),
      started: false,
    };
    state.annotationDraft = draft;
    state.annotationPointer = {
      pointerId: event.pointerId,
      pointerType: event.pointerType,
      mode: "draw",
      startX: point.clientX,
      startY: point.clientY,
      lastX: point.clientX,
      lastY: point.clientY,
    };
    renderAnnotationCanvas();
    return true;
  }

  function moveAnnotationPointer(event) {
    const pointer = state.annotationPointer;
    if (!pointer || pointer.pointerId !== event.pointerId) return;
    if (pointer.mode === "eraser") {
      eraseAtEvent(event);
      return;
    }
    const draft = state.annotationDraft;
    const point = pageSurfacePoint(event);
    if (!draft || !point) return;
    const fromStart = Math.hypot(point.clientX - pointer.startX, point.clientY - pointer.startY);
    if (!draft.started && fromStart >= 2) {
      draft.started = true;
      pausePdfAutoFollowForManualBrowse("필기");
    }
    const delta = Math.hypot(point.clientX - pointer.lastX, point.clientY - pointer.lastY);
    if (delta >= 1) {
      draft.points.push({ x: point.x, y: point.y });
      pointer.lastX = point.clientX;
      pointer.lastY = point.clientY;
      renderAnnotationCanvas();
    }
  }

  function finishAnnotationPointer(event, { cancelled = false } = {}) {
    const pointer = state.annotationPointer;
    if (!pointer || pointer.pointerId !== event.pointerId) return;
    if (pointer.mode === "draw" && state.annotationDraft) {
      const draft = state.annotationDraft;
      if (!cancelled) {
        if (!draft.started) pausePdfAutoFollowForManualBrowse("필기");
        persistAnnotationStroke({ ...draft, started: undefined });
      }
    }
    state.annotationDraft = null;
    state.annotationPointer = null;
    renderAnnotationCanvas();
  }

  function cancelAnnotationPointer() {
    state.annotationDraft = null;
    state.annotationPointer = null;
    renderAnnotationCanvas();
  }


  function pdfTouchDistance(a, b) {
    return Math.hypot(Number(a.x) - Number(b.x), Number(a.y) - Number(b.y));
  }

  function pdfTouchMidpoint(a, b) {
    return {
      x: (Number(a.x) + Number(b.x)) / 2,
      y: (Number(a.y) + Number(b.y)) / 2,
    };
  }

  function startPdfTouchPinch(stage) {
    if (state.pdfGesturePointers.size < 2) return;
    const points = [...state.pdfGesturePointers.values()].slice(0, 2);
    const distance = pdfTouchDistance(points[0], points[1]);
    if (!(distance > 4)) return;

    const midpoint = pdfTouchMidpoint(points[0], points[1]);
    const rect = stage.getBoundingClientRect();
    const viewportX = midpoint.x - rect.left;
    const viewportY = midpoint.y - rect.top;
    const scrollWidth = Math.max(1, stage.scrollWidth);
    const scrollHeight = Math.max(1, stage.scrollHeight);

    state.pdfGesturePan = null; // one-finger pan is intentionally reserved for drawing.
    state.pdfGesturePinch = {
      startDistance: distance,
      startZoom: state.pdfZoom,
      anchorX: (stage.scrollLeft + viewportX) / scrollWidth,
      anchorY: (stage.scrollTop + viewportY) / scrollHeight,
    };
  }

  function applyPendingPdfTouchPinch(stage) {
    state.pdfGestureFrame = null;
    const pending = state.pdfGesturePending;
    state.pdfGesturePending = null;
    const pinch = state.pdfGesturePinch;
    if (!pending || !pinch || !state.pdfReading) return;

    const rect = stage.getBoundingClientRect();
    const viewportX = pending.midpoint.x - rect.left;
    const viewportY = pending.midpoint.y - rect.top;

    setPdfZoom(pending.zoom, { persist: false });

    /* The same document point stays under the two-finger midpoint. Moving both
       fingers therefore pans the PDF; changing their distance zooms it. */
    const afterWidth = Math.max(1, stage.scrollWidth);
    const afterHeight = Math.max(1, stage.scrollHeight);
    stage.scrollLeft = Math.max(0, pinch.anchorX * afterWidth - viewportX);
    stage.scrollTop = Math.max(0, pinch.anchorY * afterHeight - viewportY);
  }

  function wirePdfTouchGestures() {
    const stage = els.pdfDropZone;
    if (!stage || stage.dataset.pdfTouchGestures === "1") return;
    stage.dataset.pdfTouchGestures = "1";

    stage.addEventListener("pointerdown", (event) => {
      if (!["touch", "pen"].includes(event.pointerType) || !state.pdfReading || !activePdf()) return;
      event.preventDefault();
      event.stopPropagation();
      stage.setPointerCapture?.(event.pointerId);

      if (event.pointerType === "pen") {
        beginAnnotationPointer(event);
        return;
      }

      state.pdfGesturePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (state.pdfGesturePointers.size === 1 && !state.annotationSuppressUntilClear) {
        beginAnnotationPointer(event);
        return;
      }

      /* The second touch immediately converts the interaction into navigation.
         Any uncommitted one-finger stroke is discarded; two fingers are always
         reserved for pan/pinch and never create ink. */
      if (state.pdfGesturePointers.size >= 2) {
        state.annotationSuppressUntilClear = true;
        cancelAnnotationPointer();
        startPdfTouchPinch(stage);
      }
    });

    stage.addEventListener("pointermove", (event) => {
      if (!["touch", "pen"].includes(event.pointerType)) return;
      if (event.pointerType === "pen") {
        if (!state.annotationPointer || state.annotationPointer.pointerId !== event.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        moveAnnotationPointer(event);
        return;
      }
      if (!state.pdfGesturePointers.has(event.pointerId)) return;
      event.preventDefault();
      event.stopPropagation();
      state.pdfGesturePointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

      if (state.pdfGesturePointers.size < 2) {
        if (!state.annotationSuppressUntilClear) moveAnnotationPointer(event);
        return;
      }
      state.annotationSuppressUntilClear = true;
      cancelAnnotationPointer();
      if (!state.pdfGesturePinch) startPdfTouchPinch(stage);
      const pinch = state.pdfGesturePinch;
      if (!pinch) return;

      const points = [...state.pdfGesturePointers.values()].slice(0, 2);
      const distance = pdfTouchDistance(points[0], points[1]);
      if (!(distance > 4)) return;
      const zoom = clampNumber(
        pinch.startZoom * (distance / pinch.startDistance),
        0.5,
        3,
        pinch.startZoom,
      );
      state.pdfGesturePending = {
        zoom,
        midpoint: pdfTouchMidpoint(points[0], points[1]),
      };
      if (!state.pdfGestureFrame) {
        state.pdfGestureFrame = requestAnimationFrame(() => applyPendingPdfTouchPinch(stage));
      }
    });

    const finishPointer = (event, { cancelled = false } = {}) => {
      if (!["touch", "pen"].includes(event.pointerType)) return;
      event.preventDefault();
      event.stopPropagation();

      if (event.pointerType === "pen") {
        finishAnnotationPointer(event, { cancelled });
        try { stage.releasePointerCapture?.(event.pointerId); } catch (_) {}
        return;
      }
      if (!state.pdfGesturePointers.has(event.pointerId)) return;

      const wasSingle = state.pdfGesturePointers.size === 1;
      if (wasSingle && !state.annotationSuppressUntilClear) {
        finishAnnotationPointer(event, { cancelled });
      } else if (state.annotationPointer?.pointerId === event.pointerId) {
        cancelAnnotationPointer();
      }

      state.pdfGesturePointers.delete(event.pointerId);
      try { stage.releasePointerCapture?.(event.pointerId); } catch (_) {}

      if (state.pdfGesturePointers.size >= 2) {
        startPdfTouchPinch(stage);
        return;
      }

      if (state.pdfGesturePinch) {
        state.pdfGesturePinch = null;
        localStorage.setItem(PDF_ZOOM_KEY, String(state.pdfZoom));
      }
      state.pdfGesturePending = null;
      state.pdfGesturePan = null;
      if (state.pdfGesturePointers.size === 0) {
        state.annotationSuppressUntilClear = false;
        localStorage.setItem(PDF_ZOOM_KEY, String(state.pdfZoom));
      }
    };

    stage.addEventListener("pointerup", (event) => finishPointer(event));
    stage.addEventListener("pointercancel", (event) => finishPointer(event, { cancelled: true }));
  }

  function renderPdfViewer() {
    const pdf = activePdf();
    const reading = Boolean(state.pdfReading && pdf);
    renderPdfShelf();
    renderPdfZoom();
    updatePdfAutoFollowUi();
    els.sessionView?.classList.toggle("pdf-reading", reading);

    // Changing between alpha-like PDF OFF and split PDF READING changes the
    // transcript viewport size. Keep the currently-playing SEG in view when
    // playback follow is enabled instead of letting the resize break follow.
    if (state.autoPlayActive && state.autoPlayFollow && state.playingSegment != null) {
      requestAnimationFrame(() => scrollToPlaying({ smooth: false }));
    }

    if (!reading) {
      els.pdfPageLoading?.classList.add("hidden");
      if (els.pdfPaneTitle) els.pdfPaneTitle.textContent = "PDF 자료";
      if (els.pdfCanonicalRef) els.pdfCanonicalRef.textContent = "";
      state.annotationDraft = null;
      renderAnnotationCanvas();
      return;
    }

    const totalPages = Math.max(0, Math.round(Number(pdf.page_count) || 0));
    const page = Math.max(1, Math.min(totalPages || Number.MAX_SAFE_INTEGER, Math.round(Number(state.pdfPage) || 1)));
    state.pdfPage = page;
    if (els.pdfPaneTitle) els.pdfPaneTitle.textContent = pdf.original_filename || "PDF 자료";
    if (els.pdfPageLabel) els.pdfPageLabel.textContent = totalPages ? `Page ${page} / ${totalPages}` : `Page ${page}`;
    if (els.pdfCanonicalRef) {
      els.pdfCanonicalRef.textContent = `clova://pdf/${pdf.pdf_id}/page/${page}`;
      els.pdfCanonicalRef.title = els.pdfCanonicalRef.textContent;
    }
    if (els.pdfPrev) els.pdfPrev.disabled = page <= 1;
    if (els.pdfNext) els.pdfNext.disabled = totalPages > 0 && page >= totalPages;

    if (els.pdfPageImage) {
      const target = pdfPageURL(pdf.pdf_id, page);
      if (els.pdfPageImage.dataset.target !== target) {
        els.pdfPageImage.dataset.target = target;
        els.pdfPageLoading?.classList.remove("hidden");
        state.annotationDraft = null;
        renderAnnotationCanvas();
        els.pdfPageImage.src = target;
      } else {
        renderAnnotationCanvas();
      }
    }
  }

  async function loadSessionPdfs(sessionId = state.sessionId) {
    if (!sessionId) {
      state.pdfs = [];
      state.activePdfId = "";
      state.pdfPage = 1;
      state.pdfReading = false;
      renderPdfViewer();
      return;
    }
    try {
      const data = await fetchJSON(`/api/pdfs?session_id=${encodeURIComponent(sessionId)}`);
      if (state.sessionId !== sessionId) return;
      state.pdfs = Array.isArray(data.pdfs) ? data.pdfs : [];
      state.activePdfId = data.active_pdf_id || state.pdfs.at(-1)?.pdf_id || "";
      state.pdfPage = Math.max(1, Number(data.page) || 1);
      state.pdfReading = Boolean(data.reading && state.activePdfId);
      renderPdfViewer();
    } catch (error) {
      state.pdfs = [];
      state.activePdfId = "";
      state.pdfPage = 1;
      state.pdfReading = false;
      renderPdfViewer();
      console.debug("PDF workspace load skipped", error);
    }
  }

  async function loadPdfTimeline(sessionId = state.sessionId, { quiet = true } = {}) {
    if (!sessionId) {
      state.pdfTimelineEvents = [];
      state.pdfTimelineSchema = "";
      state.pdfTimelineSessionId = "";
      state.pdfLastAppliedTimelineKey = "";
      updatePdfAutoFollowUi();
      return [];
    }
    try {
      const data = await fetchJSON(`/api/pdf/events?session_id=${encodeURIComponent(sessionId)}`);
      if (state.sessionId !== sessionId) return [];
      const events = (Array.isArray(data.events) ? data.events : [])
        .filter((item) => item && ["pdf_open", "pdf_page", "pdf_close"].includes(String(item.type || "")))
        .map((item, index) => ({
          ...item,
          time: Number(item.time) || 0,
          seq: Number(item.seq) || index + 1,
          page: Math.max(1, Math.round(Number(item.page) || 1)),
        }))
        .sort((a, b) => (a.time - b.time) || (a.seq - b.seq));
      state.pdfTimelineEvents = events;
      state.pdfTimelineSchema = String(data.schema || "");
      state.pdfTimelineSessionId = sessionId;
      state.pdfLastAppliedTimelineKey = "";
      updatePdfAutoFollowUi();
      return events;
    } catch (error) {
      state.pdfTimelineEvents = [];
      state.pdfTimelineSchema = "";
      state.pdfTimelineSessionId = sessionId;
      state.pdfLastAppliedTimelineKey = "";
      updatePdfAutoFollowUi();
      if (!quiet) toast(`PDF timeline 불러오기 실패: ${error.message}`, "error");
      else console.debug("PDF timeline load skipped", error);
      return [];
    }
  }

  function pdfTimelineStateAt(recordingTime) {
    const t = Math.max(0, Number(recordingTime) || 0);
    const events = state.pdfTimelineEvents || [];
    let lo = 0;
    let hi = events.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (Number(events[mid].time) <= t + 1e-6) {
        found = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    if (found < 0) return { state: "no_pdf", seq: 0, time: 0, key: "no_pdf:0" };
    const event = events[found];
    const seq = Number(event.seq) || found + 1;
    if (event.type === "pdf_close") {
      return { state: "no_pdf", seq, time: Number(event.time) || 0, key: `no_pdf:${seq}` };
    }
    const pdfId = String(event.pdf_id || "");
    const page = Math.max(1, Math.round(Number(event.page) || 1));
    return {
      state: pdfId ? "pdf" : "no_pdf",
      pdf_id: pdfId,
      page,
      seq,
      time: Number(event.time) || 0,
      key: pdfId ? `pdf:${seq}:${pdfId}:${page}` : `no_pdf:${seq}`,
    };
  }

  function recordingTimeForSegmentOffset(seg, offsetSec = 0) {
    if (!seg) return null;
    const exactStart = Number(seg.recording_start);
    const fallbackStart = Number(seg.start);
    const start = Number.isFinite(exactStart) ? exactStart : (Number.isFinite(fallbackStart) ? fallbackStart : 0);
    let t = start + Math.max(0, Number(offsetSec) || 0);
    const end = Number(seg.recording_end);
    if (Number.isFinite(end) && end >= start) t = Math.min(t, end);
    return Math.max(0, t);
  }

  function currentPlaybackRecordingTime() {
    if (state.autoPlayActive && state.autoPlayUsingWebAudio && state.playbackList.length) {
      const pos = currentGaplessPosition();
      const seg = state.playbackList[Math.max(0, Math.min(state.playbackList.length - 1, Number(pos.index) || 0))];
      const t = recordingTimeForSegmentOffset(seg, pos.offset);
      if (Number.isFinite(t)) return t;
    }
    if (state.playingSegment != null) {
      const seg = state.segments.find((item) => Number(item.segment) === Number(state.playingSegment));
      const offset = Number(els.player?.currentTime);
      const t = recordingTimeForSegmentOffset(seg, Number.isFinite(offset) ? offset : 0);
      if (Number.isFinite(t)) return t;
    }
    return state.playbackRecordingTime != null && Number.isFinite(Number(state.playbackRecordingTime))
      ? Number(state.playbackRecordingTime)
      : null;
  }

  function updatePdfAutoFollowUi() {
    const hasPlaybackCursor = currentPlaybackRecordingTime() != null;
    const paused = !state.pdfAutoFollow && hasPlaybackCursor && state.pdfTimelineEvents.length > 0;
    els.pdfReturnToLecture?.classList.toggle("hidden", !paused);
    if (els.pdfReturnToLecture) {
      els.pdfReturnToLecture.title = state.pdfAutoFollowPauseReason
        ? `PDF 자동 따라가기 일시정지 · ${state.pdfAutoFollowPauseReason}`
        : "PDF 자동 따라가기 일시정지";
    }
  }

  function pausePdfAutoFollowForManualBrowse(reason = "수동 PDF 탐색") {
    if (currentPlaybackRecordingTime() == null || !state.pdfTimelineEvents.length) return;
    state.pdfAutoFollow = false;
    state.pdfAutoFollowPauseReason = reason;
    updatePdfAutoFollowUi();
  }

  function applyPdfTimelineState(target, { force = false } = {}) {
    if (!target) return;
    if (!force && target.key === state.pdfLastAppliedTimelineKey) return;
    state.pdfLastAppliedTimelineKey = target.key;

    if (target.state === "no_pdf") {
      if (state.pdfReading) {
        state.pdfReading = false;
        renderPdfViewer();
      } else {
        updatePdfAutoFollowUi();
      }
      return;
    }

    if (!state.pdfs.some((item) => item.pdf_id === target.pdf_id)) {
      console.warn("[V8.0-delta] timeline PDF is not attached", target.pdf_id);
      state.pdfReading = false;
      renderPdfViewer();
      return;
    }
    const changed = state.activePdfId !== target.pdf_id
      || Number(state.pdfPage) !== Number(target.page)
      || !state.pdfReading;
    state.activePdfId = target.pdf_id;
    state.pdfPage = target.page;
    state.pdfReading = true;
    if (changed || force) renderPdfViewer();
    else updatePdfAutoFollowUi();
  }

  function syncPdfToRecordingTime(recordingTime, { force = false } = {}) {
    const t = Number(recordingTime);
    if (!Number.isFinite(t)) return;
    state.playbackRecordingTime = Math.max(0, t);
    updatePdfAutoFollowUi();
    if (!state.pdfAutoFollow) return;
    applyPdfTimelineState(pdfTimelineStateAt(t), { force });
  }

  function syncPdfToPlaybackSegment(seg, offsetSec = 0, { force = false } = {}) {
    const t = recordingTimeForSegmentOffset(seg, offsetSec);
    if (Number.isFinite(t)) syncPdfToRecordingTime(t, { force });
  }

  async function rejoinPdfLecturePosition() {
    const t = currentPlaybackRecordingTime();
    if (!Number.isFinite(t)) return;
    state.pdfAutoFollow = true;
    state.pdfAutoFollowPauseReason = "";
    state.pdfLastAppliedTimelineKey = "";
    syncPdfToRecordingTime(t, { force: true });
    updatePdfAutoFollowUi();
  }

  function persistPdfViewState() {
    if (!state.sessionId) return state.pdfPersistChain;

    // Snapshot now, then serialize writes. Rapid 1→2→3 page turns must reach
    // pdf_events.jsonl in the same order instead of racing concurrent POSTs.
    const snapshot = {
      sessionId: state.sessionId,
      pdfId: state.activePdfId || "",
      page: state.pdfPage || 1,
      reading: Boolean(state.pdfReading && state.activePdfId),
    };

    state.pdfPersistChain = Promise.resolve(state.pdfPersistChain)
      .catch(() => {})
      .then(async () => {
        try {
          return await fetchJSON(`/api/pdf/view-state?session_id=${encodeURIComponent(snapshot.sessionId)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              pdf_id: snapshot.pdfId,
              page: snapshot.page,
              reading: snapshot.reading,
              client_id: recorderClientId,
            }),
          });
        } catch (error) {
          console.debug("PDF view state persist skipped", error);
          return null;
        }
      });

    return state.pdfPersistChain;
  }

  function setActivePdf(pdfId, page = 1, { reading = true, persist = false, manual = false } = {}) {
    if (pdfId && !state.pdfs.some((item) => item.pdf_id === pdfId)) return;
    if (manual) pausePdfAutoFollowForManualBrowse("문서 선택");
    state.activePdfId = pdfId || "";
    state.pdfPage = Math.max(1, Math.round(Number(page) || 1));
    state.pdfReading = Boolean(reading && state.activePdfId);
    renderPdfViewer();
    if (persist) persistPdfViewState();
  }

  function setPdfReading(reading, { persist = false, manual = false } = {}) {
    if (manual) pausePdfAutoFollowForManualBrowse(reading ? "PDF 열기" : "PDF 닫기");
    state.pdfReading = Boolean(reading && state.activePdfId);
    renderPdfViewer();
    if (persist) persistPdfViewState();
  }

  function changePdfPage(delta, { manual = true } = {}) {
    const pdf = activePdf();
    if (!pdf || !state.pdfReading) return;
    if (manual) pausePdfAutoFollowForManualBrowse("페이지 이동");
    const totalPages = Math.max(0, Math.round(Number(pdf.page_count) || 0));
    const next = Math.max(1, state.pdfPage + Number(delta || 0));
    state.pdfPage = totalPages ? Math.min(totalPages, next) : next;
    renderPdfViewer();
    persistPdfViewState();
  }

  async function importPdfFiles(files) {
    if (!state.sessionId || state.pdfImporting) return;
    const pdfs = [...(files || [])].filter((file) => file && (file.type === "application/pdf" || /\.pdf$/i.test(file.name || "")));
    if (!pdfs.length) {
      toast("PDF 파일만 추가할 수 있습니다.", "error");
      return;
    }
    state.pdfImporting = true;
    renderPdfShelf();
    const form = new FormData();
    for (const file of pdfs) form.append("pdfs", file, file.name);
    try {
      const data = await fetchJSON(`/api/pdf/import?session_id=${encodeURIComponent(state.sessionId)}`, {
        method: "POST",
        body: form,
      });
      state.pdfs = Array.isArray(data.pdfs) ? data.pdfs : [];
      state.activePdfId = data.active_pdf_id || state.activePdfId || state.pdfs.at(-1)?.pdf_id || "";
      state.pdfPage = Math.max(1, Number(data.page) || state.pdfPage || 1);
      state.pdfReading = Boolean(data.reading && state.activePdfId);
      renderPdfViewer();
      toast(`${pdfs.length}개 PDF를 Local Clova에 복사했습니다.`);
    } catch (error) {
      toast(`PDF 추가 실패: ${error.message}`, "error");
    } finally {
      state.pdfImporting = false;
      if (els.pdfFileInput) els.pdfFileInput.value = "";
      renderPdfShelf();
    }
  }

  function wirePdfDropTarget(target, { showPaneOverlay = false } = {}) {
    if (!target) return;
    let dragDepth = 0;
    const showDrop = (show) => {
      if (showPaneOverlay) els.pdfDropOverlay?.classList.toggle("hidden", !show);
      if (target === els.headerPdfZone) target.classList.toggle("pdf-drag-over", show);
    };
    target.addEventListener("dragenter", (event) => {
      event.preventDefault();
      dragDepth += 1;
      showDrop(true);
    });
    target.addEventListener("dragover", (event) => {
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    });
    target.addEventListener("dragleave", (event) => {
      event.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (!dragDepth) showDrop(false);
    });
    target.addEventListener("drop", (event) => {
      event.preventDefault();
      dragDepth = 0;
      showDrop(false);
      importPdfFiles(event.dataTransfer?.files || []);
    });
  }

  function wirePdfWorkspace() {
    els.pdfFileInput?.addEventListener("change", () => importPdfFiles(els.pdfFileInput.files));
    els.pdfPrev?.addEventListener("click", () => changePdfPage(-1));
    els.pdfNext?.addEventListener("click", () => changePdfPage(1));
    els.pdfZoomOut?.addEventListener("click", () => changePdfZoom(-1));
    els.pdfZoomIn?.addEventListener("click", () => changePdfZoom(1));
    els.pdfZoomLabel?.addEventListener("click", () => setPdfZoom(1));
    els.pdfZoomFit?.addEventListener("click", fitPdfToWidth);
    els.pdfToolPen?.addEventListener("click", () => setAnnotationTool("pen"));
    els.pdfToolEraser?.addEventListener("click", () => setAnnotationTool("eraser"));
    els.pdfToolHighlighter?.addEventListener("click", () => setAnnotationTool("highlighter"));
    els.pdfReturnToLecture?.addEventListener("click", rejoinPdfLecturePosition);
    renderAnnotationTools();
    wirePdfTouchGestures();
    installAnnotationResizeObserver();
    els.pdfPageImage?.addEventListener("load", () => {
      els.pdfPageLoading?.classList.add("hidden");
      renderPdfZoom();
      requestAnimationFrame(renderAnnotationCanvas);
    });
    els.pdfPageImage?.addEventListener("error", () => {
      els.pdfPageLoading?.classList.add("hidden");
      if (state.pdfReading) toast("PDF 페이지 렌더링에 실패했습니다.", "error");
    });
    wirePdfDropTarget(els.headerPdfZone);
    wirePdfDropTarget(els.pdfPane, { showPaneOverlay: true });

    document.addEventListener("keydown", (event) => {
      if (!state.pdfReading || !activePdf()) return;
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target?.isContentEditable) return;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        changePdfPage(-1);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        changePdfPage(1);
      }
    });
  }

  async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);
    let data = {};
    try {
      data = await response.json();
    } catch (_) {
      data = { error: await response.text().catch(() => "") };
    }
    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  function escapeText(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function formatDuration(seconds) {
    const n = Math.max(0, Number(seconds) || 0);
    const h = Math.floor(n / 3600);
    const m = Math.floor((n % 3600) / 60);
    const s = Math.floor(n % 60);
    if (h) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    return `${m}:${String(s).padStart(2, "0")}`;
  }

  function formatCompactSeconds(seconds) {
    if (seconds == null || !Number.isFinite(Number(seconds))) return null;
    const total = Math.max(0, Math.round(Number(seconds)));
    const minutes = Math.floor(total / 60);
    const secs = total % 60;
    if (minutes) return `${minutes}분 ${secs}초`;
    return `${secs}초`;
  }

  function formatDate(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat("ko-KR", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  }

  function shortDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const now = new Date();
    if (d.toDateString() === now.toDateString()) {
      return new Intl.DateTimeFormat("ko-KR", { hour: "2-digit", minute: "2-digit" }).format(d);
    }
    return `${d.getMonth() + 1}/${d.getDate()}`;
  }

  function currentSemester() {
    const d = new Date();
    return `${d.getFullYear()}-${d.getMonth() + 1 >= 7 ? 2 : 1}`;
  }

  function getSubject(subjectId) {
    return state.library.subjects.find((x) => x.id === subjectId) || null;
  }

  function subjectLabel(subjectId) {
    const s = getSubject(subjectId);
    return s ? `${s.emoji || "📘"} ${s.name}` : "미분류";
  }

  function getProfessor(professorId) {
    return (state.library.professors || []).find((x) => x.id === professorId) || null;
  }

  function professorForSubject(subjectId) {
    const subject = getSubject(subjectId);
    return subject?.professor_id ? getProfessor(subject.professor_id) : null;
  }

  function populateProfessorOptions() {
    if (!els.professorOptions) return;
    els.professorOptions.innerHTML = "";
    const professors = [...(state.library.professors || [])]
      .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "ko"));
    for (const professor of professors) {
      const opt = document.createElement("option");
      opt.value = professor.name || "";
      if (professor.id) opt.label = professor.id;
      els.professorOptions.appendChild(opt);
    }
  }

  function adaptiveStatusInfo(adaptive) {
    return ["Whisper Large-v3", "status-done"];
  }

  function setPostStatus(adaptive) {
    const [label, cls] = adaptiveStatusInfo(adaptive);
    els.headerPostStatus.className = `status-badge ${cls}`;
    els.headerPostStatus.textContent = label;
    els.metaStatus.textContent = label;
  }

  function trainingIsRunning(adaptive = state.session?.adaptive_asr) {
    return false;
  }

  function metricPercent(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return "—";
    return `${(n * 100).toFixed(n < 0.1 ? 2 : 1)}%`;
  }

  function renderPostprocessProgress(adaptive) {
    const a = adaptive || null;
    const hasProfessor = Boolean(a?.professor_id);
    els.postProgress.classList.toggle("hidden", !hasProfessor);
    if (!hasProfessor) return;

    const t = a.training_status || { status: "idle" };
    const status = String(t.status || "idle");
    const running = status === "queued" || status === "running";
    const rejected = status === "rejected";
    const failed = status === "error";
    const done = status === "done" || status === "promoted";
    const fraction = running
      ? Math.max(0, Math.min(1, Number(t.progress || 0)))
      : a.active_adapter ? 1 : Math.min(0.95, Number(a.correction_count || 0) / Math.max(1, Number(a.min_samples || 12)));
    const percent = Math.round(fraction * 100);

    const stageName = String(t.stage || "");
    const stageMap = {
      queued: 1, prepare: 1, dataset: 1,
      baseline: 2, baseline_eval: 2,
      train: 3, training: 3,
      candidate_eval: 4, validate: 4, promoted: 4, rejected: 4, done: 4, error: 4,
    };
    const stageIndex = Number(t.stage_index || stageMap[stageName] || (a.active_adapter ? 4 : 1));

    els.postProgress.classList.toggle("complete", done && !failed && !rejected);
    els.postProgress.classList.toggle("failed", failed || rejected);
    els.postStageLabel.textContent = running
      ? (t.stage_label || "Professor LoRA 학습 중")
      : failed
        ? "LoRA 학습 실패"
        : rejected
          ? "후보 LoRA 미승격 · 기존 Adapter 유지"
          : a.active_adapter
            ? `${a.professor_name || "교수"} · ${a.active_adapter}`
            : `${a.professor_name || "교수"} · Base BatiSay`;
    els.postPercent.textContent = `${Math.max(0, Math.min(100, percent))}%`;
    els.postFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;

    const samples = Number(a.sample_count || 0);
    const corrections = Number(a.correction_count || 0);
    const newSamples = Number(a.new_sample_count || 0);
    const newCorrections = Number(a.new_correction_count || 0);
    const phrase = Number(a.phrase_count || 0);
    const utterance = Number(a.utterance_count || 0);
    els.postMessage.textContent = running
      ? (t.message || "LoRA 학습 상태를 확인하는 중")
      : failed
        ? (t.error || t.message || "trainer 오류")
        : rejected
          ? (t.message || "검증 CER가 개선되지 않아 현재 Adapter를 유지합니다.")
          : `${corrections} corrections · ${samples} samples · phrase ${phrase} · 새 correction ${newCorrections}`;

    if (running) {
      const elapsed = formatCompactSeconds(t.elapsed_sec);
      const eta = formatCompactSeconds(t.eta_sec);
      els.postElapsed.textContent = elapsed || `${corrections} corrections`;
      els.postEta.textContent = eta ? `약 ${eta} 남음` : "CER/WER 검증 예정";
    } else {
      const metrics = a.metrics || t.after || {};
      els.postElapsed.textContent = `${corrections} corrections`;
      els.postEta.textContent = `CER ${metricPercent(metrics.cer)} · WER ${metricPercent(metrics.wer)}`;
    }

    $$("#postprocessStages [data-stage-index]").forEach((item) => {
      const idx = Number(item.dataset.stageIndex || 0);
      item.classList.toggle("done", done || (stageIndex > 0 && idx < stageIndex));
      item.classList.toggle("current", running && idx === stageIndex);
    });
  }

  function concatFloat32(a, b) {
    const out = new Float32Array(a.length + b.length);
    out.set(a, 0);
    out.set(b, a.length);
    return out;
  }

  function resample(input, srcRate, dstRate) {
    if (srcRate === dstRate) return input;
    const ratio = dstRate / srcRate;
    const len = Math.round(input.length * ratio);
    const out = new Float32Array(len);
    for (let i = 0; i < len; i += 1) {
      const x = i / ratio;
      const x0 = Math.floor(x);
      const x1 = Math.min(x0 + 1, input.length - 1);
      const t = x - x0;
      out[i] = input[x0] * (1 - t) + input[x1] * t;
    }
    return out;
  }

  function openModal(kind) {
    const backdrop = kind === "session" ? els.sessionModal : els.subjectModal;
    backdrop.classList.remove("hidden");
    requestAnimationFrame(() => {
      if (kind === "session") els.newSessionName.focus();
      else els.subjectName.focus();
    });
  }

  function closeModal(kind) {
    const backdrop = kind === "session" ? els.sessionModal : els.subjectModal;
    backdrop.classList.add("hidden");
  }

  function populateSubjectSelects() {
    const subjects = [...state.library.subjects].sort((a, b) => {
      const sem = String(b.semester || "").localeCompare(String(a.semester || ""));
      return sem || String(a.name || "").localeCompare(String(b.name || ""), "ko");
    });

    const fill = (select, includeUnclassified = true) => {
      const current = select.value;
      select.innerHTML = "";
      if (includeUnclassified) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "미분류";
        select.appendChild(opt);
      }
      for (const subject of subjects) {
        const opt = document.createElement("option");
        opt.value = subject.id;
        opt.textContent = `${subject.emoji || "📘"} ${subject.semester ? `${subject.semester} · ` : ""}${subject.name}`;
        select.appendChild(opt);
      }
      if ([...select.options].some((x) => x.value === current)) select.value = current;
    };

    fill(els.subjectSelect);
    fill(els.newSessionSubject);

    if (state.session) els.subjectSelect.value = state.session.subject_id || "";
  }

  function filteredSessions() {
    const query = state.search.trim().casefold?.() || state.search.trim().toLowerCase();
    if (!query) return state.library.sessions;

    const subjectMap = new Map(state.library.subjects.map((x) => [x.id, x]));
    return state.library.sessions.filter((session) => {
      const subject = subjectMap.get(session.subject_id);
      const haystack = [
        session.title,
        session.description,
        subject?.name,
        subject?.semester,
        professorForSubject(subject?.id)?.name,
        ...(session.tags || []).map((x) => x.name),
      ].join(" ").toLowerCase();
      return haystack.includes(query.toLowerCase());
    });
  }

  function renderSidebar() {
    els.libraryNav.innerHTML = "";
    const sessions = filteredSessions();
    const bySubject = new Map();
    for (const session of sessions) {
      const key = getSubject(session.subject_id) ? session.subject_id : "";
      if (!bySubject.has(key)) bySubject.set(key, []);
      bySubject.get(key).push(session);
    }

    const trashSvg = '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>';
    const subjects = [...state.library.subjects];
    const semesterOrder = [...new Set(subjects.map((x) => x.semester || "기타"))].sort().reverse();

    const renderGroup = (subject, groupSessions, semesterContainer) => {
      const key = subject?.id || "__unclassified__";
      const group = document.createElement("div");
      group.className = `subject-group ${state.collapsedSubjects.has(key) ? "collapsed" : ""}`;

      const headRow = document.createElement("div");
      headRow.className = "subject-header-row";
      const head = document.createElement("button");
      head.type = "button";
      head.className = "subject-header";
      head.innerHTML = `
        <svg class="subject-chevron" viewBox="0 0 24 24"><path d="m7 9 5 5 5-5"/></svg>
        <span class="subject-emoji">${escapeText(subject?.emoji || "◌")}</span>
        <span class="subject-title-stack">
          <span class="subject-name">${escapeText(subject?.name || "미분류")}</span>
          ${subject?.professor_id ? `<span class="subject-professor">${escapeText(getProfessor(subject.professor_id)?.name || "교수 미지정")}</span>` : ""}
        </span>
        <span class="subject-count">${groupSessions.length}</span>`;
      head.addEventListener("click", () => {
        if (state.collapsedSubjects.has(key)) state.collapsedSubjects.delete(key);
        else state.collapsedSubjects.add(key);
        renderSidebar();
      });
      headRow.appendChild(head);

      if (subject) {
        const del = document.createElement("button");
        del.type = "button";
        del.className = "library-delete-button";
        del.title = `${subject.name} 과목 삭제`;
        del.innerHTML = trashSvg;
        del.addEventListener("click", (event) => {
          event.stopPropagation();
          deleteSubjectFromLibrary(subject, groupSessions.length);
        });
        headRow.appendChild(del);
      } else {
        const spacer = document.createElement("span");
        headRow.appendChild(spacer);
      }
      group.appendChild(headRow);

      const items = document.createElement("div");
      items.className = "session-items";
      if (!groupSessions.length) {
        const empty = document.createElement("div");
        empty.className = "no-sessions";
        empty.textContent = "아직 세션이 없습니다.";
        items.appendChild(empty);
      } else {
        for (const session of groupSessions) {
          const wrap = document.createElement("div");
          wrap.className = "session-item-wrap";
          const button = document.createElement("button");
          button.type = "button";
          button.className = `session-link ${state.sessionId === session.session_id ? "active" : ""} ${session.recording ? "recording" : ""}`;
          const tags = (session.tags || []).slice(0, 2).map((x) => x.name).join(" · ");
          button.innerHTML = `
            <span class="session-link-title">${escapeText(session.title)}</span>
            <span class="session-link-meta"><span>${shortDate(session.created_at)}</span>${tags ? `<span>·</span><span class="session-link-tags">${escapeText(tags)}</span>` : ""}</span>`;
          button.addEventListener("click", () => openSession(session.session_id));
          wrap.appendChild(button);

          const del = document.createElement("button");
          del.type = "button";
          del.className = "library-delete-button";
          del.title = `${session.title} 세션 삭제`;
          del.innerHTML = trashSvg;
          del.disabled = Boolean(session.recording || trainingIsRunning(session.adaptive_asr) || Number(session.pending_count || 0));
          del.addEventListener("click", (event) => {
            event.stopPropagation();
            deleteSessionFromLibrary(session);
          });
          wrap.appendChild(del);
          items.appendChild(wrap);
        }
      }
      group.appendChild(items);
      semesterContainer.appendChild(group);
    };

    for (const semester of semesterOrder) {
      const semesterSubjects = subjects
        .filter((x) => (x.semester || "기타") === semester)
        .sort((a, b) => String(a.name).localeCompare(String(b.name), "ko"));
      const hasAny = semesterSubjects.some((sub) => (bySubject.get(sub.id) || []).length) || !state.search;
      if (!hasAny) continue;

      const label = document.createElement("div");
      label.className = "semester-label";
      label.textContent = semester;
      els.libraryNav.appendChild(label);
      for (const subject of semesterSubjects) renderGroup(subject, bySubject.get(subject.id) || [], els.libraryNav);
    }

    const unclassified = bySubject.get("") || [];
    if (unclassified.length || !state.search) {
      const label = document.createElement("div");
      label.className = "semester-label";
      label.textContent = "기타";
      els.libraryNav.appendChild(label);
      renderGroup(null, unclassified, els.libraryNav);
    }

    if (!els.libraryNav.children.length) {
      const empty = document.createElement("div");
      empty.className = "no-sessions";
      empty.style.padding = "24px 12px";
      empty.textContent = "검색 결과가 없습니다.";
      els.libraryNav.appendChild(empty);
    }
  }

  async function loadLibrary({ quiet = false } = {}) {
    try {
      const data = await fetchJSON("/api/library");
      state.library = {
        subjects: Array.isArray(data.subjects) ? data.subjects : [],
        professors: Array.isArray(data.professors) ? data.professors : [],
        sessions: Array.isArray(data.sessions) ? data.sessions : [],
      };
      populateSubjectSelects();
      populateProfessorOptions();
      renderSidebar();
    } catch (error) {
      if (!quiet) toast(`라이브러리 로드 실패: ${error.message}`, "error");
    }
  }


  function segmentsURL(sessionId = state.sessionId) {
    const extra = state.showDeletedSegments ? "&include_deleted=1" : "";
    return `/api/segments?session_id=${encodeURIComponent(sessionId)}${extra}`;
  }


  function syncLivePreview(data = {}) {
    const text = String(data?.unfixed_text || "").trim();
    if (!els.liveCard || !els.unfixedText) return;
    els.unfixedText.textContent = text;
    els.liveCard.classList.toggle("hidden", !text);
    // Old Epsilon HTML temporarily carried inline display:none; neutralize it.
    els.liveCard.style.display = "";
    if (text && state.followLatest) followTranscriptBottom();
  }

  function playableSegments() {
    return [...(state.segments || [])]
      .filter((seg) => !seg.deleted && seg.audio_available && !seg.pending)
      .sort((a, b) => Number(a.segment || 0) - Number(b.segment || 0));
  }

  const GAPLESS_PRELOAD_COUNT = 12;
  const GAPLESS_SCHEDULE_AHEAD_SEC = 55;
  const GAPLESS_CROSSFADE_SEC = 0.016;

  function supportsWebAudio() {
    return Boolean(globalThis.AudioContext || globalThis.webkitAudioContext);
  }

  async function ensurePlaybackContext() {
    if (!supportsWebAudio()) throw new Error("Web Audio API를 지원하지 않는 브라우저입니다.");
    if (!state.playbackCtx || state.playbackCtx.state === "closed") {
      const Ctx = globalThis.AudioContext || globalThis.webkitAudioContext;
      state.playbackCtx = new Ctx({ latencyHint: "interactive" });
      state.playbackMaster = state.playbackCtx.createGain();
      state.playbackMaster.gain.value = 1;
      state.playbackMaster.connect(state.playbackCtx.destination);
    }
    if (state.playbackCtx.state === "suspended") await state.playbackCtx.resume();
    return state.playbackCtx;
  }

  function clearPlaybackCache() {
    state.playbackCache.clear();
    state.playbackStretchCache.clear();
    state.playbackStretchLru = [];
  }

  function playbackCacheKey(seg) {
    return `${state.sessionId || "session"}:${Number(seg.segment)}:${seg.audio_url || ""}`;
  }

  async function loadPlaybackBuffer(seg) {
    const key = playbackCacheKey(seg);
    if (state.playbackCache.has(key)) return state.playbackCache.get(key);
    const promise = (async () => {
      const ctx = await ensurePlaybackContext();
      const response = await fetch(seg.audio_url, { cache: "force-cache" });
      if (!response.ok) throw new Error(`SEG ${seg.segment} audio HTTP ${response.status}`);
      const bytes = await response.arrayBuffer();
      return await ctx.decodeAudioData(bytes.slice(0));
    })();
    state.playbackCache.set(key, promise);
    try {
      return await promise;
    } catch (error) {
      state.playbackCache.delete(key);
      throw error;
    }
  }

  const PITCH_LOCK_CACHE_LIMIT = 28;

  function stretchCacheKey(seg, rate) {
    return `${playbackCacheKey(seg)}:tempo=${Number(rate).toFixed(3)}`;
  }

  function touchStretchCacheKey(key) {
    state.playbackStretchLru = state.playbackStretchLru.filter((item) => item !== key);
    state.playbackStretchLru.push(key);
    while (state.playbackStretchLru.length > PITCH_LOCK_CACHE_LIMIT) {
      const stale = state.playbackStretchLru.shift();
      state.playbackStretchCache.delete(stale);
    }
  }

  // V7.4 Pitch Lock: lightweight WSOLA-style speech time-stretch.
  // AudioBufferSourceNode.playbackRate shifts pitch, so we instead create a
  // tempo-adjusted buffer whose short waveform frames keep their original pitch.
  function pitchPreservingTimeStretch(inputBuffer, tempo, ctx) {
    const rate = Math.max(0.5, Math.min(3, Number(tempo) || 1));
    if (Math.abs(rate - 1) < 0.001) return inputBuffer;

    const sampleRate = inputBuffer.sampleRate;
    const inputLength = inputBuffer.length;
    if (inputLength < 1024) return inputBuffer;

    const frameSize = Math.max(384, Math.min(1024, Math.round(sampleRate * 0.032)));
    const synthHop = Math.max(128, Math.round(frameSize / 2));
    const overlap = frameSize - synthHop;
    const analysisHop = synthHop * rate;
    const searchRadius = Math.max(24, Math.min(128, Math.round(sampleRate * 0.0045)));
    const searchStep = 4;
    const corrStep = 4;
    const channels = inputBuffer.numberOfChannels;
    const input = Array.from({ length: channels }, (_, ch) => inputBuffer.getChannelData(ch));
    const guide = input[0];

    const estimatedLength = Math.max(frameSize + 1, Math.ceil(inputLength / rate) + frameSize * 2);
    const output = Array.from({ length: channels }, () => new Float32Array(estimatedLength));
    const weights = new Float32Array(estimatedLength);
    const window = new Float32Array(frameSize);
    for (let i = 0; i < frameSize; i += 1) {
      window[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / Math.max(1, frameSize - 1));
    }

    let outPos = 0;
    let inputPos = 0;
    let expected = 0;
    let frames = 0;

    while (outPos + frameSize < estimatedLength && expected < inputLength) {
      if (frames > 0) {
        expected = Math.min(inputLength - frameSize - 1, expected + analysisHop);
        const minPos = Math.max(0, Math.round(expected - searchRadius));
        const maxPos = Math.min(inputLength - frameSize - 1, Math.round(expected + searchRadius));
        const referenceStart = Math.min(inputLength - overlap - 1, inputPos + synthHop);
        let bestPos = Math.max(minPos, Math.min(maxPos, Math.round(expected)));
        let bestScore = -Infinity;

        for (let candidate = minPos; candidate <= maxPos; candidate += searchStep) {
          let dot = 0;
          let aa = 1e-9;
          let bb = 1e-9;
          for (let j = 0; j < overlap; j += corrStep) {
            const a = guide[referenceStart + j] || 0;
            const b = guide[candidate + j] || 0;
            dot += a * b;
            aa += a * a;
            bb += b * b;
          }
          const normalized = dot / Math.sqrt(aa * bb);
          const penalty = Math.abs(candidate - expected) / Math.max(1, searchRadius) * 0.025;
          const score = normalized - penalty;
          if (score > bestScore) {
            bestScore = score;
            bestPos = candidate;
          }
        }
        inputPos = bestPos;
      }

      for (let j = 0; j < frameSize; j += 1) {
        const outIndex = outPos + j;
        const w = window[j];
        weights[outIndex] += w;
        for (let ch = 0; ch < channels; ch += 1) {
          output[ch][outIndex] += input[ch][inputPos + j] * w;
        }
      }

      outPos += synthHop;
      frames += 1;
      if (inputPos + frameSize >= inputLength - 1) break;
    }

    const targetLength = Math.max(frameSize, Math.round(inputLength / rate));
    const usefulLength = Math.max(frameSize, Math.min(targetLength, estimatedLength, outPos + frameSize - synthHop));
    const result = ctx.createBuffer(channels, usefulLength, sampleRate);
    for (let ch = 0; ch < channels; ch += 1) {
      const dest = result.getChannelData(ch);
      for (let i = 0; i < usefulLength; i += 1) {
        dest[i] = weights[i] > 1e-5 ? output[ch][i] / weights[i] : 0;
      }
    }
    return result;
  }

  async function loadPitchLockedPlaybackBuffer(seg, rate = state.playbackRate) {
    const normalizedRate = Math.max(0.5, Math.min(3, Number(rate) || 1));
    const raw = await loadPlaybackBuffer(seg);
    if (Math.abs(normalizedRate - 1) < 0.001) {
      return { buffer: raw, rawDuration: raw.duration, rate: 1 };
    }

    const key = stretchCacheKey(seg, normalizedRate);
    if (state.playbackStretchCache.has(key)) {
      touchStretchCacheKey(key);
      const buffer = await state.playbackStretchCache.get(key);
      return { buffer, rawDuration: raw.duration, rate: normalizedRate };
    }

    const promise = (async () => {
      const ctx = await ensurePlaybackContext();
      await new Promise((resolve) => setTimeout(resolve, 0));
      return pitchPreservingTimeStretch(raw, normalizedRate, ctx);
    })();
    state.playbackStretchCache.set(key, promise);
    touchStretchCacheKey(key);
    try {
      const buffer = await promise;
      return { buffer, rawDuration: raw.duration, rate: normalizedRate };
    } catch (error) {
      state.playbackStretchCache.delete(key);
      state.playbackStretchLru = state.playbackStretchLru.filter((item) => item !== key);
      throw error;
    }
  }

  function preloadPlaybackWindow(list, fromIndex, count = GAPLESS_PRELOAD_COUNT, rate = state.playbackRate) {
    const end = Math.min(list.length, fromIndex + count);
    for (let i = Math.max(0, fromIndex); i < end; i += 1) {
      loadPitchLockedPlaybackBuffer(list[i], rate).catch(() => {});
    }
  }

  function buildPlaybackTimeline(list) {
    state.playbackCumulative = [];
    let total = 0;
    for (const seg of list) {
      state.playbackCumulative.push(total);
      total += Math.max(0, Number(seg.duration_sec) || 0);
    }
    state.playbackTotalDuration = total;
  }

  function updateReturnToPlaying() {
    const show = Boolean(state.autoPlayActive && state.playingSegment != null && !state.autoPlayFollow);
    els.returnToPlaying.classList.toggle("hidden", !show);
  }

  function updateAutoFollowToggle() {
    if (!els.autoFollowToggle) return;
    const enabled = Boolean(state.autoPlayFollow);
    els.autoFollowToggle.classList.toggle("active", enabled);
    els.autoFollowToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    els.autoFollowToggle.title = enabled ? "재생 위치 자동 따라가기 끄기" : "재생 위치 자동 따라가기 켜기";
  }

  function setGaplessMode(enabled) {
    els.miniPlayer.classList.toggle("gapless-mode", Boolean(enabled));
    els.gaplessProgress.classList.toggle("hidden", !enabled);
    els.player.classList.toggle("hidden", Boolean(enabled));
    updateAutoFollowToggle();
  }

  function updatePlayerPauseButton() {
    if (!els.playerPause) return;
    const hasPlayable = Boolean(state.autoPlayActive || (els.player && els.player.src));
    const paused = state.autoPlayActive ? Boolean(state.autoPlayPaused) : Boolean(els.player?.paused);
    els.playerPause.disabled = !hasPlayable || state.autoPlayLoading;
    els.playerPause.textContent = paused ? "▶" : "Ⅱ";
    els.playerPause.title = paused ? "재생" : "일시정지";
    els.playerPause.setAttribute("aria-label", paused ? "재생" : "일시정지");
    els.playerPause.classList.toggle("paused", paused);
  }

  function updateAutoPlayButton() {
    const hasSession = Boolean(state.sessionId && state.session);
    const hasAudio = playableSegments().length > 0;
    els.autoPlayBtn.classList.toggle("hidden", !hasSession);
    els.autoPlayBtn.disabled = !hasSession || !hasAudio || state.autoPlayLoading;
    els.autoPlayBtn.classList.toggle("active", state.autoPlayActive);
    if (state.autoPlayLoading) {
      els.autoPlayBtnText.textContent = "오디오 준비 중";
    } else if (!state.autoPlayActive) {
      els.autoPlayBtnText.textContent = "전체 재생";
    } else if (state.autoPlayPaused) {
      els.autoPlayBtnText.textContent = "계속 재생";
    } else {
      els.autoPlayBtnText.textContent = "일시정지";
    }
    updateAutoFollowToggle();
    updateReturnToPlaying();
    updatePlayerPauseButton();
  }

  function cancelScrollAnimation() {
    if (state.scrollAnimationFrame) cancelAnimationFrame(state.scrollAnimationFrame);
    state.scrollAnimationFrame = null;
  }

  function easeInOutCubic(t) {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  function scrollToPlaying({ smooth = true } = {}) {
    if (state.playingSegment == null || !state.autoPlayFollow) return;
    const row = els.transcriptList.querySelector(`[data-segment="${state.playingSegment}"]`);
    if (!row) return;
    const scroller = currentTranscriptScroller();
    if (!scroller) return;
    const scrollerRect = scroller.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const rowCenterInScroll = (rowRect.top - scrollerRect.top) + scroller.scrollTop + rowRect.height / 2;
    const desiredCenter = scroller.clientHeight * 0.46;
    const maxScroll = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
    const target = Math.max(0, Math.min(maxScroll, rowCenterInScroll - desiredCenter));
    const start = scroller.scrollTop;
    const distance = target - start;
    cancelScrollAnimation();

    const reduced = globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (!smooth || reduced || Math.abs(distance) < 3) {
      state.programmaticScrollUntil = Date.now() + 180;
      scroller.scrollTop = target;
      return;
    }

    // Distance-aware inertial movement: accelerate, cruise through the midpoint,
    // then decelerate into the next transcript card instead of snapping there.
    const duration = Math.max(360, Math.min(760, 310 + Math.sqrt(Math.abs(distance)) * 11));
    const startedAt = performance.now();
    state.programmaticScrollUntil = Date.now() + duration + 180;

    const frame = (now) => {
      const t = Math.min(1, (now - startedAt) / duration);
      scroller.scrollTop = start + distance * easeInOutCubic(t);
      if (t < 1 && state.autoPlayFollow) {
        state.scrollAnimationFrame = requestAnimationFrame(frame);
      } else {
        state.scrollAnimationFrame = null;
      }
    };
    state.scrollAnimationFrame = requestAnimationFrame(frame);
  }

  function setPlayingSegment(seg, { smooth = true } = {}) {
    const next = seg ? Number(seg.segment) : null;
    const previous = state.playingSegment == null ? null : Number(state.playingSegment);
    if (previous === next) return;
    clearPlayingWord();
    if (previous != null) {
      els.transcriptList.querySelector(`[data-segment="${previous}"]`)?.classList.remove("playing");
    }
    state.playingSegment = next;
    if (next != null) {
      const row = els.transcriptList.querySelector(`[data-segment="${next}"]`);
      row?.classList.add("playing");
      els.playerTitle.textContent = `전체 재생 · SEG ${next} · 원본 음성`;
      els.playerSubtitle.textContent = (seg.text || segmentSttText(seg) || seg.qwen_raw || "").slice(0, 72);
      if (state.autoPlayActive && state.autoPlayFollow) scrollToPlaying({ smooth });
    }
    updateReturnToPlaying();
  }

  function currentGaplessPosition() {
    if (!state.autoPlayUsingWebAudio || !state.playbackCtx || !state.playbackSchedule.length) {
      return { index: state.playbackResumeIndex || 0, offset: state.playbackResumeOffset || 0 };
    }
    const now = state.playbackCtx.currentTime;
    const candidates = state.playbackSchedule.filter((item) => now >= item.startTime && now < item.endTime);
    const item = candidates.length ? candidates[candidates.length - 1] : null;
    if (item) {
      const offset = item.offsetSec + Math.max(0, now - item.startTime) * item.sourceRate;
      return { index: item.index, offset: Math.min(item.rawDuration, offset) };
    }
    const future = state.playbackSchedule.find((entry) => entry.startTime > now);
    if (future) return { index: future.index, offset: future.offsetSec };
    const last = state.playbackSchedule[state.playbackSchedule.length - 1];
    return last ? { index: last.index, offset: last.rawDuration } : { index: 0, offset: 0 };
  }

  function stopScheduledSources({ preservePosition = false } = {}) {
    let pos = null;
    if (preservePosition) pos = currentGaplessPosition();
    state.playbackGeneration += 1;
    for (const item of state.playbackSources) {
      try { item.source.onended = null; item.source.stop(); } catch (_) {}
      try { item.source.disconnect(); } catch (_) {}
      try { item.gain.disconnect(); } catch (_) {}
    }
    state.playbackSources = [];
    state.playbackSchedule = [];
    state.playbackScheduling = false;
    if (state.playbackPumpTimer) clearInterval(state.playbackPumpTimer);
    state.playbackPumpTimer = null;
    if (state.playbackRaf) cancelAnimationFrame(state.playbackRaf);
    state.playbackRaf = null;
    if (pos) {
      state.playbackResumeIndex = pos.index;
      state.playbackResumeOffset = pos.offset;
    }
  }

  function updateGaplessProgress(index, offset) {
    const list = state.playbackList;
    if (!list.length) return;
    const before = state.playbackCumulative[index] || 0;
    const elapsed = Math.max(0, before + Math.max(0, offset || 0));
    const total = Math.max(0.001, state.playbackTotalDuration || 0.001);
    const ratio = Math.max(0, Math.min(1, elapsed / total));
    els.gaplessFill.style.width = `${ratio * 100}%`;
    els.gaplessPosition.textContent = `${formatDuration(elapsed)} / ${formatDuration(total)}`;
    els.gaplessSegmentCounter.textContent = `SEG ${index + 1} / ${list.length}`;
  }

  function playbackUiLoop(generation) {
    if (!state.autoPlayActive || !state.autoPlayUsingWebAudio || generation !== state.playbackGeneration) return;
    const ctx = state.playbackCtx;
    const now = ctx.currentTime;
    const active = state.playbackSchedule
      .filter((item) => now >= item.startTime && now < item.endTime)
      .at(-1);

    if (active) {
      const offset = Math.min(active.rawDuration, active.offsetSec + Math.max(0, now - active.startTime) * active.sourceRate);
      setPlayingSegment(active.seg, { smooth: true });
      updatePlayingWord(active.seg, offset);
      state.playbackResumeIndex = active.index;
      state.playbackResumeOffset = offset;
      updateGaplessProgress(active.index, offset);
      syncPdfToPlaybackSegment(active.seg, offset);
      preloadPlaybackWindow(state.playbackList, active.index + 1, GAPLESS_PRELOAD_COUNT);
    }

    state.playbackSchedule = state.playbackSchedule.filter((item) => item.endTime > now - 1.5);
    state.playbackSources = state.playbackSources.filter((item) => item.endTime > now - 1.5);
    const finished = state.playbackNextIndex >= state.playbackList.length
      && state.playbackSchedule.length > 0
      && state.playbackSchedule.every((item) => item.endTime <= now + 0.01);
    if (finished) {
      stopPlayback({ hidePlayer: true });
      return;
    }
    state.playbackRaf = requestAnimationFrame(() => playbackUiLoop(generation));
  }

  async function scheduleGaplessMore(generation) {
    if (state.playbackScheduling || generation !== state.playbackGeneration || !state.autoPlayActive || state.autoPlayPaused) return;
    state.playbackScheduling = true;
    try {
      const ctx = state.playbackCtx;
      const list = state.playbackList;
      while (
        generation === state.playbackGeneration
        && state.playbackNextIndex < list.length
        && state.playbackNextStartTime < ctx.currentTime + GAPLESS_SCHEDULE_AHEAD_SEC
      ) {
        const index = state.playbackNextIndex;
        const seg = list[index];
        let prepared;
        try {
          prepared = await loadPitchLockedPlaybackBuffer(seg, state.playbackRate);
        } catch (error) {
          console.warn("[V7.4 PITCH LOCK] failed to prepare SEG", seg.segment, error);
          toast(`SEG ${seg.segment} 오디오를 건너뜁니다: ${error.message}`, "error");
          state.playbackNextIndex += 1;
          continue;
        }
        if (generation !== state.playbackGeneration || state.autoPlayPaused) break;

        const { buffer, rawDuration, rate } = prepared;
        const source = ctx.createBufferSource();
        const gain = ctx.createGain();
        source.buffer = buffer;
        // Tempo is already baked into the WSOLA buffer. Playing at 1.0x keeps
        // the professor's vocal pitch stable while Web Audio remains gapless.
        source.playbackRate.value = 1;
        source.connect(gain);
        gain.connect(state.playbackMaster);

        const offsetSec = index === state.playbackResumeIndex
          ? Math.max(0, Math.min(rawDuration - 0.001, state.playbackResumeOffset || 0))
          : 0;
        const processedOffsetSec = Math.max(0, Math.min(buffer.duration - 0.001, offsetSec / rate));
        const wallDuration = Math.max(0.001, buffer.duration - processedOffsetSec);
        const sourceRate = Math.max(0.001, (rawDuration - offsetSec) / wallDuration);
        const startTime = Math.max(ctx.currentTime + 0.025, state.playbackNextStartTime);
        const endTime = startTime + wallDuration;
        const fade = Math.min(GAPLESS_CROSSFADE_SEC, wallDuration * 0.22);
        gain.gain.setValueAtTime(index === state.playbackResumeIndex && offsetSec > 0 ? 1 : 0.001, startTime);
        gain.gain.linearRampToValueAtTime(1, startTime + fade);
        gain.gain.setValueAtTime(1, Math.max(startTime + fade, endTime - fade));
        gain.gain.linearRampToValueAtTime(0.001, endTime);
        source.start(startTime, processedOffsetSec);

        const item = {
          source, gain, seg, index, buffer, rawDuration, rate, sourceRate,
          startTime, endTime, offsetSec, processedOffsetSec,
        };
        state.playbackSources.push(item);
        state.playbackSchedule.push(item);
        state.playbackNextIndex += 1;
        state.playbackResumeOffset = 0;
        // Slight overlap gives a click-free, gapless transition between independent WAVs.
        state.playbackNextStartTime = Math.max(startTime + 0.001, endTime - fade);
        preloadPlaybackWindow(list, state.playbackNextIndex, GAPLESS_PRELOAD_COUNT);
      }
    } finally {
      state.playbackScheduling = false;
    }
  }

  async function launchGaplessSchedule(startIndex = 0, offsetSec = 0) {
    const list = state.playbackList.length ? state.playbackList : playableSegments();
    if (!list.length) return;
    const ctx = await ensurePlaybackContext();
    stopScheduledSources({ preservePosition: false });
    const generation = state.playbackGeneration;
    state.playbackList = list;
    buildPlaybackTimeline(list);
    state.playbackResumeIndex = Math.max(0, Math.min(list.length - 1, startIndex));
    state.playbackResumeOffset = Math.max(0, offsetSec || 0);
    state.playbackNextIndex = state.playbackResumeIndex;
    state.playbackNextStartTime = ctx.currentTime + 0.09;
    state.autoPlayPaused = false;
    state.autoPlayUsingWebAudio = true;
    state.autoPlayActive = true;
    setGaplessMode(true);
    els.miniPlayer.classList.remove("hidden");

    // Pre-decode a sizeable window before the first source is scheduled. This is
    // the key difference from V7's <audio> ended->load->play chain.
    const firstWindow = list.slice(state.playbackResumeIndex, state.playbackResumeIndex + Math.min(8, GAPLESS_PRELOAD_COUNT));
    await Promise.allSettled(firstWindow.map((seg) => loadPitchLockedPlaybackBuffer(seg, state.playbackRate)));
    if (generation !== state.playbackGeneration || !state.autoPlayActive) return;
    await scheduleGaplessMore(generation);
    state.playbackPumpTimer = setInterval(() => scheduleGaplessMore(generation), 220);
    state.playbackRaf = requestAnimationFrame(() => playbackUiLoop(generation));
    updateAutoPlayButton();
  }

  async function startGaplessAutoPlay(startIndex = 0, offsetSec = 0, { keepFollow = false } = {}) {
    const list = playableSegments();
    if (!list.length) {
      toast("재생할 원본 음성이 없습니다.", "error");
      return;
    }
    await loadPdfTimeline(state.sessionId, { quiet: true });
    state.pdfAutoFollow = true;
    state.pdfAutoFollowPauseReason = "";
    state.pdfLastAppliedTimelineKey = "";
    syncPdfToPlaybackSegment(list[Math.max(0, Math.min(list.length - 1, startIndex))], offsetSec, { force: true });
    els.player.pause();
    state.autoPlayLoading = true;
    state.autoPlayActive = true;
    state.autoPlayPaused = false;
    state.autoPlayUsingWebAudio = supportsWebAudio();
    if (!keepFollow) state.autoPlayFollow = true;
    state.playbackList = list;
    updateAutoPlayButton();
    try {
      if (!supportsWebAudio()) {
        state.autoPlayUsingWebAudio = false;
        await playSegment(list[Math.max(0, Math.min(list.length - 1, startIndex))], { autoMode: true });
        return;
      }
      await launchGaplessSchedule(startIndex, offsetSec);
    } catch (error) {
      console.error("[V7.1 GAPLESS]", error);
      stopScheduledSources({ preservePosition: false });
      state.autoPlayUsingWebAudio = false;
      toast(`Web Audio 재생 준비 실패. 기본 플레이어로 전환합니다: ${error.message}`, "error");
      await playSegment(list[Math.max(0, Math.min(list.length - 1, startIndex))], { autoMode: true });
    } finally {
      state.autoPlayLoading = false;
      updateAutoPlayButton();
    }
  }

  async function pauseGaplessPlayback() {
    if (!state.autoPlayUsingWebAudio || state.autoPlayPaused) return;
    stopScheduledSources({ preservePosition: true });
    state.autoPlayPaused = true;
    updateAutoPlayButton();
  }

  async function resumeGaplessPlayback() {
    if (!state.autoPlayUsingWebAudio || !state.autoPlayPaused) return;
    state.autoPlayLoading = true;
    updateAutoPlayButton();
    try {
      await launchGaplessSchedule(state.playbackResumeIndex, state.playbackResumeOffset);
    } finally {
      state.autoPlayLoading = false;
      updateAutoPlayButton();
    }
  }

  async function togglePlayerPause() {
    if (state.autoPlayActive) {
      if (state.autoPlayUsingWebAudio) {
        if (state.autoPlayPaused) await resumeGaplessPlayback();
        else await pauseGaplessPlayback();
      } else if (els.player.paused) {
        try {
          await els.player.play();
          state.autoPlayPaused = false;
        } catch (error) {
          toast(`재생 실패: ${error.message}`, "error");
        }
      } else {
        els.player.pause();
        state.autoPlayPaused = true;
      }
      updateAutoPlayButton();
      return;
    }

    if (!els.player?.src) return;
    if (els.player.paused) {
      try { await els.player.play(); }
      catch (error) { toast(`재생 실패: ${error.message}`, "error"); }
    } else {
      els.player.pause();
    }
    updatePlayerPauseButton();
  }

  function stopPlayback({ hidePlayer = false } = {}) {
    if (state.autoPlayUsingWebAudio) stopScheduledSources({ preservePosition: false });
    els.player.pause();
    state.autoPlayActive = false;
    state.autoPlayPaused = false;
    state.autoPlayLoading = false;
    state.autoPlayUsingWebAudio = false;
    state.autoPlayFollow = true;
    setGaplessMode(false);
    setPlayingSegment(null, { smooth: false });
    state.playbackList = [];
    state.playbackResumeIndex = 0;
    state.playbackResumeOffset = 0;
    state.playbackRecordingTime = null;
    state.pdfAutoFollow = true;
    state.pdfAutoFollowPauseReason = "";
    state.pdfLastAppliedTimelineKey = "";
    updatePdfAutoFollowUi();
    els.gaplessFill.style.width = "0%";
    if (hidePlayer) els.miniPlayer.classList.add("hidden");
    updateAutoPlayButton();
  }

  async function jumpGaplessToIndex(index, offsetSec = 0) {
    if (!state.autoPlayActive || !state.autoPlayUsingWebAudio) return;
    const list = state.playbackList;
    const target = Math.max(0, Math.min(list.length - 1, index));
    state.autoPlayLoading = true;
    updateAutoPlayButton();
    try {
      await launchGaplessSchedule(target, offsetSec);
      setPlayingSegment(list[target], { smooth: true });
      syncPdfToPlaybackSegment(list[target], offsetSec, { force: true });
    } finally {
      state.autoPlayLoading = false;
      updateAutoPlayButton();
    }
  }

  async function playRelativeSegment(delta) {
    const list = playableSegments();
    if (!list.length) return;
    let idx = list.findIndex((seg) => Number(seg.segment) === Number(state.playingSegment));
    if (idx < 0) idx = delta > 0 ? -1 : 0;
    const target = idx + delta;
    if (target < 0 || target >= list.length) {
      if (state.autoPlayActive && delta > 0) stopPlayback();
      return;
    }
    if (state.autoPlayActive && state.autoPlayUsingWebAudio) {
      await jumpGaplessToIndex(target, 0);
      return;
    }
    await playSegment(list[target], { autoMode: state.autoPlayActive });
  }

  async function startAutoPlayFromSegment(seg) {
    const list = playableSegments();
    const idx = list.findIndex((item) => Number(item.segment) === Number(seg.segment));
    if (idx < 0) return;
    await startGaplessAutoPlay(idx, 0);
  }

  async function seekGaplessFraction(fraction) {
    if (!state.autoPlayActive || !state.autoPlayUsingWebAudio || !state.playbackList.length) return;
    const f = Math.max(0, Math.min(1, fraction));
    const targetSeconds = f * state.playbackTotalDuration;
    let index = state.playbackList.length - 1;
    for (let i = 0; i < state.playbackList.length; i += 1) {
      const start = state.playbackCumulative[i] || 0;
      const duration = Math.max(0, Number(state.playbackList[i].duration_sec) || 0);
      if (targetSeconds < start + duration || i === state.playbackList.length - 1) {
        index = i;
        break;
      }
    }
    const offset = Math.max(0, targetSeconds - (state.playbackCumulative[index] || 0));
    await jumpGaplessToIndex(index, offset);
  }

  async function toggleAutoPlay() {
    const list = playableSegments();
    if (!list.length) {
      toast("재생할 원본 음성이 없습니다.", "error");
      return;
    }

    if (state.autoPlayActive) {
      if (state.autoPlayUsingWebAudio) {
        if (state.autoPlayPaused) await resumeGaplessPlayback();
        else await pauseGaplessPlayback();
      } else if (els.player.paused) {
        try { await els.player.play(); state.autoPlayPaused = false; } catch (error) { toast(`재생 실패: ${error.message}`, "error"); }
      } else {
        els.player.pause();
        state.autoPlayPaused = true;
      }
      updateAutoPlayButton();
      return;
    }

    await startGaplessAutoPlay(0, 0);
  }

  async function toggleDeletedSegments() {
    if (!state.sessionId) return;
    state.showDeletedSegments = !state.showDeletedSegments;
    els.deletedToggle.setAttribute("aria-pressed", state.showDeletedSegments ? "true" : "false");
    els.deletedToggle.classList.toggle("active", state.showDeletedSegments);
    await refreshSelectedSession();
  }

  async function deleteSegment(seg) {
    if (!state.sessionId || seg.pending || seg.deleted) return;
    const preview = String(seg.text || segmentSttText(seg) || seg.qwen_raw || "").slice(0, 90);
    const ok = window.confirm(`SEG ${seg.segment}을 삭제할까요?\n\n${preview}\n\n원본 WAV는 보존되며, LoRA 학습/전체재생/내보내기에서는 제외됩니다.`);
    if (!ok) return;
    try {
      await fetchJSON(`/api/segment/delete?session_id=${encodeURIComponent(state.sessionId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment: seg.segment }),
      });
      if (Number(state.playingSegment) === Number(seg.segment)) stopPlayback();
      await refreshSelectedSession();
      await loadLibrary({ quiet: true });
      toast(`SEG ${seg.segment}을 삭제했습니다. 원본 음성은 보존됩니다.`);
    } catch (error) {
      toast(`SEG 삭제 실패: ${error.message}`, "error");
    }
  }

  async function restoreSegment(seg) {
    if (!state.sessionId || !seg.deleted) return;
    try {
      await fetchJSON(`/api/segment/restore?session_id=${encodeURIComponent(state.sessionId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment: seg.segment }),
      });
      await refreshSelectedSession();
      await loadLibrary({ quiet: true });
      toast(`SEG ${seg.segment}을 복원했습니다.`);
    } catch (error) {
      toast(`SEG 복원 실패: ${error.message}`, "error");
    }
  }

  async function deleteSessionFromLibrary(session) {
    if (!session) return;
    const ok = window.confirm(`“${session.title}” 세션을 삭제할까요?\n\n라이브러리에서는 즉시 사라지며, 안전을 위해 세션 폴더는 Local Clova trash에 보관됩니다.`);
    if (!ok) return;
    try {
      await fetchJSON(`/api/session/delete?session_id=${encodeURIComponent(session.session_id)}`, { method: "POST" });
      if (state.sessionId === session.session_id) {
        stopPostprocessPolling();
        stopPlayback({ hidePlayer: true });
        state.sessionId = null;
        state.session = null;
        state.segments = [];
        state.showDeletedSegments = false;
      }
      await loadLibrary({ quiet: true });
      showSession();
      toast("세션을 삭제했습니다.");
    } catch (error) {
      toast(`세션 삭제 실패: ${error.message}`, "error");
    }
  }

  async function deleteSubjectFromLibrary(subject, sessionCount = 0) {
    if (!subject) return;
    const suffix = sessionCount
      ? `\n\n이 과목의 ${sessionCount}개 세션은 삭제하지 않고 “미분류”로 이동합니다.`
      : "";
    const ok = window.confirm(`“${subject.name}” 과목을 삭제할까요?${suffix}`);
    if (!ok) return;
    try {
      await fetchJSON("/api/subject/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject_id: subject.id }),
      });
      if (state.session?.subject_id === subject.id) {
        state.session.subject_id = "";
      }
      await loadLibrary({ quiet: true });
      if (state.sessionId) await refreshSelectedSession();
      showSession();
      toast("과목을 삭제했습니다. 기존 세션은 미분류로 이동했습니다.");
    } catch (error) {
      toast(`과목 삭제 실패: ${error.message}`, "error");
    }
  }

  function showSession() {
    const hasSession = Boolean(state.sessionId && state.session);
    els.emptyState.classList.toggle("hidden", hasSession);
    els.sessionView.classList.toggle("hidden", !hasSession);
    els.layerSwitch?.classList.add("hidden");
    els.headerPdfZone?.classList.toggle("hidden", !hasSession);

    if (!hasSession) {
      els.heading.textContent = "오늘의 수업을 기록해보세요";
      els.headerSubject.textContent = "미분류";
      els.recordingBadge.classList.add("hidden");
      setPostStatus(null);
      els.stopBtn.disabled = true;
      els.stopBtn.classList.remove("hidden");
      els.resumeBtn.disabled = true;
      els.resumeBtn.classList.add("hidden");
      els.autoPlayBtn.classList.add("hidden");
      els.postBtn.disabled = true;
      els.subjectSelect.disabled = true;
      els.tagInput.disabled = true;
      els.addTagBtn.disabled = true;
      els.deletedToggle.classList.add("hidden");
      renderPostprocessProgress(null);
      renderInspector();
      state.pdfs = [];
      state.activePdfId = "";
      state.pdfPage = 1;
      state.pdfReading = false;
      renderPdfViewer();
      updateAutoPlayButton();
      return;
    }

    const postRunning = trainingIsRunning(state.session.adaptive_asr);
    els.heading.textContent = state.session.title || "Untitled session";
    els.headerSubject.textContent = subjectLabel(state.session.subject_id);
    els.recordingBadge.classList.toggle("hidden", !state.running);
    setPostStatus(state.session.adaptive_asr || null);
    renderPdfViewer();

    els.stopBtn.classList.toggle("hidden", !state.running);
    els.stopBtn.disabled = !state.running;
    els.resumeBtn.classList.toggle("hidden", state.running);
    els.resumeBtn.disabled = state.running || postRunning;
    const resumeLabel = els.resumeBtn.querySelector("span");
    const detachedRecording = Boolean(state.session.recording && !state.running);
    if (resumeLabel) resumeLabel.textContent = detachedRecording ? "재연결" : "재개";
    els.resumeBtn.title = detachedRecording
      ? "브라우저 오디오 연결이 끊겼습니다. 같은 세션에 다시 연결합니다."
      : "같은 세션에서 녹음을 이어갑니다.";

    const adaptive = state.session.adaptive_asr || {};
    const correctionCount = Number(adaptive.correction_count || 0);
    const minSamples = Number(adaptive.min_samples || 12);
    const newCorrections = Number(adaptive.new_correction_count || 0);
    const minNew = Number(adaptive.min_new_samples || 8);
    const hasAdapter = Boolean(adaptive.active_adapter);
    const enoughTrainingData = hasAdapter ? newCorrections >= minNew : correctionCount >= minSamples;
    els.postBtn.classList.add("hidden");
    els.postBtn.disabled = (
      state.running
      || postRunning
      || Number(state.session.pending_count || 0) > 0
      || !adaptive.professor_id
      || !enoughTrainingData
      || !adaptive.peft_available
    );
    els.postBtnText.textContent = postRunning
      ? "학습 중..."
      : hasAdapter
        ? "Adapter 업데이트"
        : "교수 LoRA 학습";

    els.subjectSelect.disabled = postRunning;
    els.tagInput.disabled = false;
    els.addTagBtn.disabled = false;
    els.subjectSelect.value = state.session.subject_id || "";

    const deletedCount = Number(state.session.deleted_count || 0);
    els.deletedToggle.classList.toggle("hidden", deletedCount <= 0);
    els.deletedToggle.textContent = state.showDeletedSegments
      ? `삭제된 SEG ${deletedCount}개 숨기기`
      : `삭제된 SEG ${deletedCount}개 보기`;
    els.deletedToggle.classList.toggle("active", state.showDeletedSegments);
    els.deletedToggle.setAttribute("aria-pressed", state.showDeletedSegments ? "true" : "false");

    renderPostprocessProgress(state.session.adaptive_asr || null);
    renderTranscript();
    renderPdfViewer();
    renderInspector();
    updateAutoPlayButton();
  }

  function segmentSttText(seg) {
    // V6.4 native field; old V6.3 sessions are transparently mapped by the
    // backend, with whisper_raw kept only as an extra compatibility fallback.
    return seg.segment_stt_raw || seg.whisper_raw || "";
  }

  function segmentTextForLayer(seg) {
    if (seg.pending) {
      const stt = segmentSttText(seg);
      return stt || "Whisper 처리 중…";
    }
    return seg.text || segmentSttText(seg) || "";
  }

  function wordTimelineForLayer(seg) {
    if (!seg) return [];
    return Array.isArray(seg.word_timeline) ? seg.word_timeline : [];
  }

  function clearPlayingWord() {
    els.transcriptList.querySelector(".transcript-word.playing-word")?.classList.remove("playing-word");
    state.playingWordKey = null;
  }

  function renderTimedTranscriptText(node, seg) {
    const text = String(segmentTextForLayer(seg) || "");
    const timeline = wordTimelineForLayer(seg)
      .filter((item) => Number.isFinite(Number(item?.char_start)) && Number.isFinite(Number(item?.char_end)))
      .sort((a, b) => Number(a.char_start) - Number(b.char_start));

    if (!timeline.length) {
      node.textContent = text;
      return;
    }

    let cursor = 0;
    for (const item of timeline) {
      const start = Math.max(cursor, Math.min(text.length, Number(item.char_start) || 0));
      const end = Math.max(start, Math.min(text.length, Number(item.char_end) || start));
      if (end <= start) continue;
      if (start > cursor) node.appendChild(document.createTextNode(text.slice(cursor, start)));

      const span = document.createElement("span");
      span.className = `transcript-word${item.approximate ? " approximate-word" : ""}`;
      span.dataset.wordIndex = String(item.index ?? "");
      span.dataset.wordStart = String(item.start_sec ?? "");
      span.dataset.wordEnd = String(item.end_sec ?? "");
      span.textContent = text.slice(start, end);
      span.title = item.approximate
        ? "수정 문장에 투영된 음성 구간 · 클릭해서 듣기"
        : "이 단어부터 듣기";
      span.addEventListener("click", async (event) => {
        event.stopPropagation();
        const offset = Number(item.start_sec);
        if (Number.isFinite(offset)) await seekToWord(seg, offset);
      });
      node.appendChild(span);
      cursor = end;
    }
    if (cursor < text.length) node.appendChild(document.createTextNode(text.slice(cursor)));
  }

  function updatePlayingWord(seg, offsetSec) {
    if (!seg || state.playingSegment == null || Number(seg.segment) !== Number(state.playingSegment)) {
      clearPlayingWord();
      return;
    }
    const t = Number(offsetSec);
    if (!Number.isFinite(t)) return;
    const timeline = wordTimelineForLayer(seg);
    const active = timeline.find((item) => {
      const start = Number(item?.start_sec);
      const end = Number(item?.end_sec);
      return Number.isFinite(start) && Number.isFinite(end) && t >= start && t < Math.max(start + 0.035, end);
    });
    const key = active ? `${state.layer}:${seg.segment}:${active.index}` : null;
    if (key === state.playingWordKey) return;
    clearPlayingWord();
    if (!active) return;
    const row = els.transcriptList.querySelector(`[data-segment="${seg.segment}"]`);
    const word = row?.querySelector(`.transcript-word[data-word-index="${CSS.escape(String(active.index ?? ""))}"]`);
    word?.classList.add("playing-word");
    state.playingWordKey = key;
  }

  async function seekToWord(seg, offsetSec) {
    const offset = Math.max(0, Number(offsetSec) || 0);
    if (state.autoPlayActive && state.autoPlayUsingWebAudio && state.playbackList.length) {
      const index = state.playbackList.findIndex((item) => Number(item.segment) === Number(seg.segment));
      if (index >= 0) {
        await jumpGaplessToIndex(index, offset);
        updatePlayingWord(seg, offset);
        return;
      }
    }
    await playSegment(seg, { autoMode: false, offsetSec: offset });
    updatePlayingWord(seg, offset);
  }

  function sourceForSegment(seg) {
    if (seg.manually_edited) return ["Human locked", "manual"];
    if (seg.pending) return ["Whisper…", "processing"];
    if (seg.final_source === "whisper_error") return ["Whisper · error", "warning"];
    return ["Whisper Large-v3", ""];
  }

  function provenanceClassForSegment(seg) {
    return "prov-default";
  }

  function isNearTranscriptBottom() {
    const scroller = currentTranscriptScroller();
    if (!scroller) return true;
    const remaining = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    return remaining < 180;
  }

  function followTranscriptBottom({ smooth = false } = {}) {
    const scroller = currentTranscriptScroller();
    if (!state.followLatest || !scroller) return;
    requestAnimationFrame(() => {
      scroller.scrollTo({
        top: scroller.scrollHeight,
        behavior: smooth ? "smooth" : "auto",
      });
    });
  }

  function renderTranscript() {
    const wasNearBottom = isNearTranscriptBottom();
    els.transcriptList.innerHTML = "";
    state.playingWordKey = null;

    const segments = [...(state.segments || [])].sort(
      (a, b) => Number(a.segment || 0) - Number(b.segment || 0)
    );

    // V7.7 Notebook mode: a newly-created transcript card briefly behaves
    // like a fresh sticky note. Existing cards are seeded silently when a
    // session is first opened so an archived lecture does not light up at once.
    if (state.visualSessionId !== state.sessionId) {
      state.visualSessionId = state.sessionId;
      state.seenSegmentIds = new Set(segments.map((seg) => Number(seg.segment)));
      state.freshSegmentUntil = new Map();
    } else {
      const now = Date.now();
      for (const seg of segments) {
        const id = Number(seg.segment);
        if (!state.seenSegmentIds.has(id)) {
          state.seenSegmentIds.add(id);
          state.freshSegmentUntil.set(id, now + 4200);
        }
      }
      for (const [id, until] of state.freshSegmentUntil.entries()) {
        if (until <= now) state.freshSegmentUntil.delete(id);
      }
    }
    const visibleCount = Number(state.session?.segment_count ?? segments.filter((seg) => !seg.deleted).length);
    const deletedCount = Number(state.session?.deleted_count || 0);
    els.transcriptEmpty.classList.toggle("hidden", visibleCount > 0 || (state.showDeletedSegments && deletedCount > 0));

    const totalDuration = state.session?.duration_sec ?? segments.reduce((sum, item) => sum + (Number(item.duration_sec) || 0), 0);
    const pendingCount = Number(state.session?.pending_count || segments.filter((seg) => seg.pending).length || 0);
    els.sessionStats.textContent = `${visibleCount} sentences · ${formatDuration(totalDuration)} audio · ${state.session?.manual_edit_count || 0} manual edits${pendingCount ? ` · ${pendingCount} processing` : ""}${deletedCount ? ` · ${deletedCount} deleted` : ""}`;

    for (const seg of segments) {
      const row = document.createElement("article");
      const freshNote = state.theme === "notebook" && Number(state.freshSegmentUntil.get(Number(seg.segment)) || 0) > Date.now();
      row.className = `transcript-row ${state.playingSegment === seg.segment ? "playing" : ""} ${seg.pending ? "processing" : ""} ${freshNote ? "fresh-note" : ""} ${seg.deleted ? "deleted" : ""}`;
      row.dataset.segment = String(seg.segment);
      if (freshNote) {
        const remaining = Math.max(0, Number(state.freshSegmentUntil.get(Number(seg.segment))) - Date.now());
        setTimeout(() => row.classList.remove("fresh-note"), remaining + 30);
      }

      const time = document.createElement("div");
      time.className = "transcript-time";
      const timeText = document.createElement("span");
      timeText.textContent = formatDuration(seg.start || 0);
      time.appendChild(timeText);

      if (seg.audio_available) {
        const play = document.createElement("button");
        play.type = "button";
        play.className = "play-inline";
        play.title = seg.deleted ? "삭제된 SEG 원본 음성 재생" : "원본 음성 재생";
        play.innerHTML = '<svg viewBox="0 0 24 24"><path d="m9 6 9 6-9 6V6Z"/></svg>';
        play.addEventListener("click", () => playSegment(seg));
        time.appendChild(play);
      }

      const body = document.createElement("div");
      body.className = "transcript-body";

      const meta = document.createElement("div");
      meta.className = "transcript-meta";
      const idx = document.createElement("span");
      idx.className = "segment-index";
      idx.textContent = `SEG ${String(seg.segment).padStart(3, "0")}`;
      const [sourceLabel, sourceClass] = sourceForSegment(seg);
      const source = document.createElement("span");
      source.className = `source-chip ${seg.deleted ? "deleted" : sourceClass}`;
      source.textContent = seg.deleted ? "삭제됨" : sourceLabel;
      meta.append(idx, source);
      body.appendChild(meta);

      if (state.editingSegment === seg.segment && !seg.deleted) {
        const editWrap = document.createElement("div");
        editWrap.className = "segment-edit";
        const textarea = document.createElement("textarea");
        textarea.value = seg.text || "";
        const controls = document.createElement("div");
        controls.className = "segment-edit-buttons";
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.textContent = "취소";
        cancel.addEventListener("click", () => {
          state.editingSegment = null;
          renderTranscript();
        });
        const save = document.createElement("button");
        save.type = "button";
        save.className = "save";
        save.textContent = "저장";
        save.addEventListener("click", () => saveSegmentEdit(seg.segment, textarea.value, save));
        controls.append(cancel, save);
        editWrap.append(textarea, controls);
        body.appendChild(editWrap);
        requestAnimationFrame(() => textarea.focus());
      } else {
        const p = document.createElement("p");
        p.className = `transcript-text ${provenanceClassForSegment(seg)}`;
        renderTimedTranscriptText(p, seg);
        if (seg.audio_available) {
          p.style.cursor = "pointer";
          p.title = "클릭해서 원본 음성 재생";
          p.addEventListener("click", () => playSegment(seg));
        }
        body.appendChild(p);

        const actions = document.createElement("div");
        actions.className = "segment-actions";
        if (seg.audio_available) {
          const playAction = document.createElement("button");
          playAction.type = "button";
          playAction.className = "segment-action";
          playAction.title = "듣기";
          playAction.innerHTML = '<svg viewBox="0 0 24 24"><path d="m9 6 9 6-9 6V6Z"/></svg>';
          playAction.addEventListener("click", () => playSegment(seg));
          actions.appendChild(playAction);

          if (!seg.deleted) {
            const queueAction = document.createElement("button");
            queueAction.type = "button";
            queueAction.className = "segment-action queue-play";
            queueAction.title = "이 SEG부터 연속 재생";
            queueAction.innerHTML = '<svg viewBox="0 0 24 24"><path d="M5 6h8M5 12h5M5 18h5"/><path d="m14 11 6 4-6 4v-8Z"/></svg>';
            queueAction.addEventListener("click", () => startAutoPlayFromSegment(seg));
            actions.appendChild(queueAction);
          }
        }

        if (seg.deleted) {
          const restore = document.createElement("button");
          restore.type = "button";
          restore.className = "segment-action restore";
          restore.title = "SEG 복원";
          restore.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8"/><path d="M4 4v4h4"/></svg>';
          restore.addEventListener("click", () => restoreSegment(seg));
          actions.appendChild(restore);
        } else if (!seg.pending) {
          const editAction = document.createElement("button");
          editAction.type = "button";
          editAction.className = "segment-action";
          editAction.title = "수정";
          editAction.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 20h4L19 9l-4-4L4 16v4Z"/><path d="m13.5 6.5 4 4"/></svg>';
          editAction.addEventListener("click", () => {
            state.editingSegment = seg.segment;
            renderTranscript();
          });
          actions.appendChild(editAction);

          const deleteAction = document.createElement("button");
          deleteAction.type = "button";
          deleteAction.className = "segment-action delete";
          deleteAction.title = "SEG 삭제";
          deleteAction.innerHTML = '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/></svg>';
          deleteAction.disabled = trainingIsRunning(state.session?.adaptive_asr);
          deleteAction.addEventListener("click", () => deleteSegment(seg));
          actions.appendChild(deleteAction);
        }
        body.appendChild(actions);
      }

      row.append(time, body);
      els.transcriptList.appendChild(row);
    }

    if (state.autoPlayActive && state.autoPlayFollow && state.playingSegment != null) {
      requestAnimationFrame(() => scrollToPlaying({ smooth: true }));
    } else if (wasNearBottom && state.running) {
      state.followLatest = true;
      followTranscriptBottom();
    }

    updateAutoPlayButton();
  }

  function renderInspector() {
    const s = state.session;
    els.tagList.innerHTML = "";

    if (!s) {
      els.description.textContent = "세션을 선택하면 정보가 표시됩니다.";
      els.metaStatus.textContent = "—";
      els.metaDate.textContent = "—";
      els.metaDuration.textContent = "—";
      els.metaSegments.textContent = "—";
      els.metaManual.textContent = "—";
      if (els.denoiseStrength) els.denoiseStrength.disabled = true;
      if (els.sttAudioSource) els.sttAudioSource.disabled = true;
      if (els.professorInput) {
        els.professorInput.value = "";
        els.professorInput.disabled = true;
      }
      if (els.professorAdapterMini) els.professorAdapterMini.textContent = "교수를 지정하면 수정된 SEG가 자동 학습 데이터가 됩니다.";
      updateDenoiseUi(2);
      if (els.sttAudioSource) els.sttAudioSource.value = "raw";
      return;
    }

    const tags = s.tags || [];
    if (!tags.length) {
      const empty = document.createElement("span");
      empty.className = "helper-text";
      empty.style.margin = "0";
      empty.textContent = "태그가 없습니다.";
      els.tagList.appendChild(empty);
    } else {
      for (const tag of tags) {
        const chip = document.createElement("span");
        chip.className = `tag-chip ${tag.source === "manual" ? "manual" : ""}`;
        const name = document.createElement("span");
        name.textContent = tag.name;
        const source = document.createElement("span");
        source.className = "tag-source";
        source.textContent = tag.source === "manual" ? "USER" : "AI";
        const remove = document.createElement("button");
        remove.type = "button";
        remove.title = "태그 삭제";
        remove.textContent = "×";
        remove.addEventListener("click", () => removeTag(tag.name));
        chip.append(name, source, remove);
        els.tagList.appendChild(chip);
      }
    }

    els.description.textContent = s.description || "세션 설명이 없습니다.";
    const [statusLabel] = adaptiveStatusInfo(s.adaptive_asr);
    els.metaStatus.textContent = statusLabel;
    els.metaDate.textContent = formatDate(s.created_at);
    els.metaDuration.textContent = formatDuration(s.duration_sec || 0);
    els.metaSegments.textContent = String(s.segment_count ?? state.segments.length ?? 0);
    els.metaManual.textContent = String(s.manual_edit_count || 0);

    const adaptive = s.adaptive_asr || {};
    const linkedProfessor = professorForSubject(s.subject_id);
    if (els.professorInput) {
      els.professorInput.disabled = !s.subject_id || trainingIsRunning(adaptive) || state.running;
      if (document.activeElement !== els.professorInput) {
        els.professorInput.value = adaptive.professor_name || linkedProfessor?.name || "";
      }
    }
    if (els.professorAdapterMini) {
      if (!s.subject_id) {
        els.professorAdapterMini.textContent = "과목을 먼저 지정하면 교수 프로필을 연결할 수 있습니다.";
      } else if (!adaptive.professor_id) {
        els.professorAdapterMini.textContent = "교수 미지정 · Human correction은 잠금되지만 LoRA 학습 Pool에는 들어가지 않습니다.";
      } else {
        const version = adaptive.active_adapter || "Base";
        const metrics = adaptive.metrics || {};
        const metricText = Number.isFinite(Number(metrics.cer))
          ? ` · CER ${metricPercent(metrics.cer)} · WER ${metricPercent(metrics.wer)}`
          : "";
        els.professorAdapterMini.textContent = `${version} · ${Number(adaptive.sample_count || 0)} samples · 새 ${Number(adaptive.new_sample_count || 0)}${metricText}`;
      }
    }

    if (els.denoiseStrength) {
      els.denoiseStrength.disabled = trainingIsRunning(s.adaptive_asr);
      updateDenoiseUi(s.denoise_strength ?? 2);
    }
    if (els.sttAudioSource) {
      els.sttAudioSource.disabled = trainingIsRunning(s.adaptive_asr);
      els.sttAudioSource.value = normalizeSttAudioSource(s.stt_audio_source);
    }
  }

  async function openSession(sessionId, { quiet = false } = {}) {
    if (state.sessionId && state.sessionId !== sessionId) stopPostprocessPolling();
    if (state.running && state.sessionId !== sessionId) {
      toast("녹음 중에는 다른 세션으로 이동할 수 없습니다.", "error");
      return;
    }
    if (state.sessionId !== sessionId) {
      stopPlayback({ hidePlayer: true });
      clearPlaybackCache();
      state.showDeletedSegments = false;
    }
    try {
      const data = await fetchJSON(segmentsURL(sessionId));
      state.sessionId = sessionId;
      state.session = data;
      state.segments = data.segments || [];
      syncLivePreview(data);
      state.editingSegment = null;
      state.pdfs = [];
      state.activePdfId = "";
      state.pdfPage = 1;
      state.pdfReading = false;
      state.pdfTimelineEvents = [];
      state.pdfTimelineSchema = "";
      state.pdfTimelineSessionId = "";
      state.pdfAutoFollow = true;
      state.pdfAutoFollowPauseReason = "";
      state.pdfLastAppliedTimelineKey = "";
      state.playbackRecordingTime = null;
      state.annotationEvents = [];
      state.annotationStrokes = new Map();
      state.annotationDraft = null;
      state.annotationPointer = null;
      state.annotationPendingErase = new Set();
      showSession();
      await loadSessionPdfs(sessionId);
      await loadPdfTimeline(sessionId, { quiet: true });
      await loadAnnotations(sessionId, { quiet: true });
      renderSidebar();
      if (trainingIsRunning(data.adaptive_asr)) startPostprocessPolling(sessionId);
    } catch (error) {
      if (!quiet) toast(`세션 열기 실패: ${error.message}`, "error");
    }
  }

  async function refreshSelectedSession() {
    if (!state.sessionId || state.refreshingSegments) return false;
    state.refreshingSegments = true;
    try {
      const data = await fetchJSON(segmentsURL(state.sessionId));
      state.session = data;
      state.segments = data.segments || [];
      syncLivePreview(data);
      showSession();
      if (trainingIsRunning(data.adaptive_asr) && state.postprocessPollSessionId !== state.sessionId) {
        startPostprocessPolling(state.sessionId);
      }
      return true;
    } catch (error) {
      console.debug("segment refresh skipped", error);
      return false;
    } finally {
      state.refreshingSegments = false;
    }
  }

  // V8.2-beta UI hotfix, restored for epsilon:
  // While recording, poll the lightweight /api/recording/status every 500 ms
  // for live preview text and native capture health. The full session
  // (transcript, PDF viewer, annotations) is rebuilt only when segment_count
  // or pending_count changes, never on a fixed timer.
  function setRecordingBadge(text, captureError = false) {
    if (!els.recordingBadge) return;
    els.recordingBadge.replaceChildren(document.createElement("i"), text);
    els.recordingBadge.classList.toggle("capture-error", captureError);
  }

  function stopRecordingStatusPolling() {
    if (state.recordingPollTimer) clearTimeout(state.recordingPollTimer);
    state.recordingPollTimer = null;
    state.recordingPollGeneration += 1;
    state.recordingPollBusy = false;
  }

  async function pollRecordingStatus(generation) {
    if (!state.running || !state.sessionId || generation !== state.recordingPollGeneration) return;
    if (state.recordingPollBusy) {
      state.recordingPollTimer = setTimeout(() => pollRecordingStatus(generation), 300);
      return;
    }
    state.recordingPollBusy = true;
    try {
      const sessionId = state.sessionId;
      const data = await fetchJSON(`/api/recording/status?session_id=${encodeURIComponent(sessionId)}`);
      if (!state.running || generation !== state.recordingPollGeneration || sessionId !== state.sessionId) return;

      syncLivePreview(data);

      state.captureStalled = Boolean(data.capture_stalled);
      if (state.captureStalled) {
        setRecordingBadge("CAPTURE ERROR", true);
        if (!state.captureWarningShown) {
          state.captureWarningShown = true;
          toast(`오디오 PCM이 ${Number(data.capture_last_pcm_age_sec || 0).toFixed(1)}초 이상 멈췄습니다. 녹음을 정지 후 재개하세요.`, "error");
        }
      } else {
        setRecordingBadge("Recording");
        if (data.capture_alive) {
          // Healthy again: a later stall should warn again.
          state.captureWarningShown = false;
        } else if (Number(data.capture_heartbeat_age_sec ?? 0) > 3 && !state.captureWarningShown) {
          state.captureWarningShown = true;
          toast("Native 오디오 capture heartbeat가 끊겼습니다. 녹음 상태를 확인하세요.", "error");
        }
      }

      // Compare against the counts the last successful full refresh covered,
      // so a refresh skipped while another is in flight is retried next poll.
      const key = `${Number(data.segment_count || 0)}:${Number(data.pending_count || 0)}`;
      if (key !== state.recordingRenderedKey) {
        refreshSelectedSession().then((ok) => {
          if (!ok || generation !== state.recordingPollGeneration) return;
          state.recordingRenderedKey = key;
          if (state.followLatest) followTranscriptBottom({ smooth: true });
        });
      }
    } catch (error) {
      console.debug("native recording status poll skipped", error);
    } finally {
      state.recordingPollBusy = false;
      if (state.running && generation === state.recordingPollGeneration) {
        state.recordingPollTimer = setTimeout(() => pollRecordingStatus(generation), 500);
      }
    }
  }

  function beginNativeCaptureMonitoring() {
    stopRecordingStatusPolling();
    state.running = true;
    state.recordingRenderedKey = null;
    state.captureWarningShown = false;
    state.captureStalled = false;
    setRecordingBadge("Recording");
    pollRecordingStatus(state.recordingPollGeneration);
  }

  async function beginAudioCapture(existingStream = null) {
    // V8.2-epsilon: microphone PCM is owned exclusively by the HOST
    // PipeWire/native capture daemon. The browser is control/UI only.
    if (existingStream) {
      try { existingStream.getTracks().forEach((track) => track.stop()); } catch (_) {}
    }
    state.stream = null;
    state.ctx = null;
    state.source = null;
    state.processor = null;
    state.buffer = new Float32Array(0);
    beginNativeCaptureMonitoring();
  }

  async function startSession(title, subjectId, denoiseStrength = 2, sttAudioSource = "raw") {
    const submit = $("#startRecordingBtn");
    submit.disabled = true;
    let backendStarted = false;
    try {
      const data = await fetchJSON("/api/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, subject_id: subjectId || "", client_id: recorderClientId, denoise_strength: clampDenoiseStrength(denoiseStrength), stt_audio_source: normalizeSttAudioSource(sttAudioSource) }),
      });

      backendStarted = true;
      state.sessionId = data.session_id;
      state.session = {
        session_id: data.session_id,
        title: data.title,
        subject_id: data.subject_id || "",
        denoise_strength: clampDenoiseStrength(data.denoise_strength ?? denoiseStrength),
        stt_audio_source: normalizeSttAudioSource(data.stt_audio_source ?? sttAudioSource),
        recording: true,
        adaptive_asr: data.adaptive_asr || null,
        professor_id: data.professor_id || "",
        professor_name: data.professor_name || "",
        tags: [],
        description: "",
        segment_count: 0,
        pending_count: 0,
        manual_edit_count: 0,
        duration_sec: 0,
        created_at: new Date().toISOString(),
      };
      state.segments = [];
      state.layer = "final";
      state.followLatest = true;
      syncLayerButtons();
      closeModal("session");
      state.pdfs = [];
      state.activePdfId = "";
      state.pdfPage = 1;
      state.pdfReading = false;
      state.pdfTimelineEvents = [];
      state.pdfTimelineSchema = "v8.0-gamma-pdf-events-v1";
      state.pdfTimelineSessionId = state.sessionId;
      state.pdfAutoFollow = true;
      state.pdfAutoFollowPauseReason = "";
      state.pdfLastAppliedTimelineKey = "";
      state.playbackRecordingTime = null;
      state.annotationEvents = [];
      state.annotationStrokes = new Map();
      state.annotationDraft = null;
      state.annotationPointer = null;
      state.annotationPendingErase = new Set();
      renderPdfViewer();

      await beginAudioCapture();
      showSession();
      await loadLibrary({ quiet: true });
      toast("녹음을 시작했습니다.");
    } catch (error) {
      state.running = false;
      await cleanupAudio();
      if (backendStarted && state.sessionId) {
        try {
          await fetchJSON(`/api/finish?session_id=${encodeURIComponent(state.sessionId)}`, { method: "POST" });
        } catch (_) {}
      }
      toast(`녹음 시작 실패: ${error.message}`, "error");
    } finally {
      submit.disabled = false;
    }
  }

  async function pump() {
    // Native capture owns /api/chunk. Never send microphone PCM from Chrome.
    state.buffer = new Float32Array(0);
  }

  async function cleanupAudio() {
    stopRecordingStatusPolling();
    // Defensive cleanup for a tab that was opened before Hotfix 3.
    try { state.processor?.disconnect(); } catch (_) {}
    try { state.source?.disconnect(); } catch (_) {}
    if (state.ctx && state.ctx.state !== "closed") {
      try { await state.ctx.close(); } catch (_) {}
    }
    try { state.stream?.getTracks().forEach((track) => track.stop()); } catch (_) {}
    state.stream = null;
    state.ctx = null;
    state.source = null;
    state.processor = null;
    state.buffer = new Float32Array(0);
  }

  async function resumeSession() {
    if (!state.sessionId || state.running || !state.session) return;
    if (trainingIsRunning(state.session.adaptive_asr)) {
      toast("Professor LoRA 학습이 끝난 뒤 녹음을 재개할 수 있습니다.", "error");
      return;
    }

    els.resumeBtn.disabled = true;
    let backendResumed = false;

    try {
      // Playback auto-sync is review-only. Persist the visible PDF state first.
      try { await persistPdfViewState(); } catch (_) {}

      const data = await fetchJSON(`/api/resume?session_id=${encodeURIComponent(state.sessionId)}&client_id=${encodeURIComponent(recorderClientId)}`, {
        method: "POST",
      });
      backendResumed = true;

      state.session = {
        ...state.session,
        ...data,
        recording: true,
      };
      state.followLatest = true;
      syncLivePreview({ unfixed_text: "" });

      await beginAudioCapture();

      showSession();
      await loadLibrary({ quiet: true });
      followTranscriptBottom({ smooth: true });
      toast(data.reconnected ? "녹음 연결을 복구했습니다." : "같은 세션에서 녹음을 재개했습니다.");
    } catch (error) {
      state.running = false;
      await cleanupAudio();

      if (backendResumed) {
        try {
          await fetchJSON(`/api/finish?session_id=${encodeURIComponent(state.sessionId)}`, { method: "POST" });
        } catch (_) {}
      }

      await refreshSelectedSession();
      toast(`녹음 재개 실패: ${error.message}`, "error");
    } finally {
      showSession();
    }
  }

  async function stopSession() {
    if (!state.running || !state.sessionId) return;
    els.stopBtn.disabled = true;
    state.running = false;

    // Flush queued PDF state transitions while the backend still considers
    // this session recording=true. Otherwise a fast page turn immediately
    // followed by Stop could be demoted to review-only viewer state.
    try { await state.pdfPersistChain; } catch (_) {}

    await cleanupAudio();
    els.liveCard.classList.add("hidden");
    els.unfixedText.textContent = "";

    try {
      const finishData = await fetchJSON(`/api/finish?session_id=${encodeURIComponent(state.sessionId)}`, { method: "POST" });
      if (state.session) state.session.pending_count = Number(finishData.pending_count || 0);
      await refreshSelectedSession();
      await loadLibrary({ quiet: true });
      toast(finishData.pending_count ? `녹음 종료 · ${finishData.pending_count}개 구간 처리 중` : "녹음을 종료했습니다.");
    } catch (error) {
      toast(`녹음 종료 실패: ${error.message}`, "error");
    }
    showSession();
  }

  function stopPostprocessPolling() {
    if (state.postprocessPollTimer) clearTimeout(state.postprocessPollTimer);
    state.postprocessPollTimer = null;
    state.postprocessPollSessionId = null;
  }

  function startPostprocessPolling(sessionId = state.sessionId) {
    if (!sessionId) return;
    stopPostprocessPolling();
    state.postprocessPollSessionId = sessionId;

    const tick = async () => {
      if (state.postprocessPollSessionId !== sessionId || state.sessionId !== sessionId) return;
      try {
        const adaptive = await fetchJSON(`/api/professor/status?session_id=${encodeURIComponent(sessionId)}`);
        if (state.sessionId !== sessionId || !state.session) return;
        state.session.adaptive_asr = adaptive;
        state.session.professor_id = adaptive.professor_id || "";
        state.session.professor_name = adaptive.professor_name || "";
        setPostStatus(adaptive);
        renderPostprocessProgress(adaptive);
        renderInspector();

        const running = trainingIsRunning(adaptive);
        els.postBtn.disabled = running;
        els.postBtnText.textContent = running
          ? "학습 중..."
          : adaptive.active_adapter
            ? "Adapter 업데이트"
            : "교수 LoRA 학습";
        els.resumeBtn.disabled = running || state.running;
        els.subjectSelect.disabled = running;

        if (running) {
          state.postprocessPollTimer = setTimeout(tick, 700);
          return;
        }

        const status = String(adaptive.training_status?.status || "idle");
        stopPostprocessPolling();
        await refreshSelectedSession();
        await loadLibrary({ quiet: true });

        const before = adaptive.training_status?.before || {};
        const after = adaptive.training_status?.after || adaptive.metrics || {};
        if (status === "done" || status === "promoted") {
          const suffix = Number.isFinite(Number(after.cer))
            ? ` · CER ${metricPercent(before.cer)} → ${metricPercent(after.cer)}`
            : "";
          toast(`Professor LoRA 승격 완료${suffix}`);
        } else if (status === "rejected") {
          toast(`후보 LoRA를 승격하지 않았습니다 · CER ${metricPercent(before.cer)} → ${metricPercent(after.cer)}`, "error");
        } else if (status === "error") {
          toast(`LoRA 학습 실패: ${adaptive.training_status?.error || "알 수 없는 오류"}`, "error");
        }
      } catch (error) {
        console.debug("Professor LoRA status poll skipped", error);
        if (state.postprocessPollSessionId === sessionId) {
          state.postprocessPollTimer = setTimeout(tick, 1000);
        }
      }
    };

    tick();
  }

  async function postprocessSession() {
    if (!state.sessionId || state.running || !state.session) return;
    els.postBtn.disabled = true;
    els.postBtnText.textContent = "시작 중...";

    try {
      const data = await fetchJSON("/api/professor/train", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: state.sessionId }),
      });
      state.session.adaptive_asr = data.adaptive_asr || state.session.adaptive_asr || {};
      showSession();
      startPostprocessPolling(state.sessionId);
      toast("Professor LoRA 학습을 시작했습니다. 검증 CER가 나빠지면 자동 승격하지 않습니다.");
    } catch (error) {
      await refreshSelectedSession();
      toast(`LoRA 학습 시작 실패: ${error.message}`, "error");
    } finally {
      showSession();
    }
  }

  async function saveSegmentEdit(segment, text, button) {
    const trimmed = String(text || "").trim();
    if (!trimmed) {
      toast("문장을 비워둘 수 없습니다.", "error");
      return;
    }
    button.disabled = true;
    try {
      await fetchJSON(`/api/segment/edit?session_id=${encodeURIComponent(state.sessionId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ segment, text: trimmed }),
      });
      state.editingSegment = null;
      await refreshSelectedSession();
      await loadLibrary({ quiet: true });
      toast("수정 내용을 잠금 처리했습니다.");
    } catch (error) {
      toast(`수정 저장 실패: ${error.message}`, "error");
      button.disabled = false;
    }
  }

  async function playSegment(seg, { autoMode = false, offsetSec = 0 } = {}) {
    if (!seg?.audio_available) return;
    if (!autoMode) {
      await loadPdfTimeline(state.sessionId, { quiet: true });
      state.pdfAutoFollow = true;
      state.pdfAutoFollowPauseReason = "";
      state.pdfLastAppliedTimelineKey = "";
      if (state.autoPlayUsingWebAudio) stopScheduledSources({ preservePosition: false });
      state.autoPlayActive = false;
      state.autoPlayPaused = false;
      state.autoPlayUsingWebAudio = false;
      state.autoPlayFollow = true;
    } else {
      state.autoPlayActive = true;
      state.autoPlayUsingWebAudio = false;
      state.autoPlayPaused = false;
    }
    setGaplessMode(false);
    setPlayingSegment(seg, { smooth: autoMode });
    els.player.src = `${seg.audio_url}&cache=${Date.now()}`;
    const requestedOffset = Math.max(0, Number(offsetSec) || 0);
    syncPdfToPlaybackSegment(seg, requestedOffset, { force: true });
    if (requestedOffset > 0) {
      els.player.addEventListener("loadedmetadata", () => {
        const maxTime = Number.isFinite(els.player.duration)
          ? Math.max(0, els.player.duration - 0.01)
          : requestedOffset;
        try { els.player.currentTime = Math.min(requestedOffset, maxTime); } catch (_) {}
      }, { once: true });
    }
    els.player.playbackRate = state.playbackRate;
    if ("preservesPitch" in els.player) els.player.preservesPitch = true;
    if ("mozPreservesPitch" in els.player) els.player.mozPreservesPitch = true;
    if ("webkitPreservesPitch" in els.player) els.player.webkitPreservesPitch = true;
    els.playerTitle.textContent = `${autoMode ? "전체 재생 · " : ""}SEG ${seg.segment} · 원본 음성`;
    els.playerSubtitle.textContent = (seg.text || segmentSttText(seg) || seg.qwen_raw || "").slice(0, 72);
    els.miniPlayer.classList.remove("hidden");
    try {
      await els.player.play();
    } catch (error) {
      if (autoMode) state.autoPlayActive = false;
      toast(`오디오 재생 실패: ${error.message}`, "error");
    }
    updateAutoPlayButton();
  }

  async function saveSessionMeta(patch) {
    if (!state.sessionId) return;
    try {
      const data = await fetchJSON(`/api/session/meta?session_id=${encodeURIComponent(state.sessionId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      state.session = { ...(state.session || {}), ...data };
      showSession();
      await loadLibrary({ quiet: true });
    } catch (error) {
      toast(`세션 정보 저장 실패: ${error.message}`, "error");
    }
  }

  async function addTag() {
    const name = els.tagInput.value.trim();
    if (!name || !state.sessionId) return;
    els.tagInput.value = "";
    await saveSessionMeta({ add_tag: name });
  }

  async function removeTag(name) {
    await saveSessionMeta({ remove_tag: name });
  }

  async function createSubject() {
    const name = els.subjectName.value.trim();
    if (!name) return;
    const submit = els.newSubjectForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      const subject = await fetchJSON("/api/subject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          semester: els.subjectSemester.value.trim(),
          emoji: els.subjectEmoji.value.trim() || "📘",
          professor_name: els.subjectProfessor?.value.trim() || "",
        }),
      });
      closeModal("subject");
      els.newSubjectForm.reset();
      els.subjectEmoji.value = "📘";
      els.subjectSemester.value = currentSemester();
      if (els.subjectProfessor) els.subjectProfessor.value = "";
      await loadLibrary({ quiet: true });
      els.newSessionSubject.value = subject.id;
      if (state.assignNewSubjectToSession && state.sessionId) {
        await saveSessionMeta({ subject_id: subject.id });
      }
      state.assignNewSubjectToSession = false;
      toast(`${subject.name} 과목을 만들었습니다.`);
    } catch (error) {
      toast(`과목 생성 실패: ${error.message}`, "error");
    } finally {
      submit.disabled = false;
    }
  }

  function syncLayerButtons() {
    $$("#layerSwitch button").forEach((button) => {
      button.classList.toggle("active", button.dataset.layer === state.layer);
    });
  }

  function openNewSessionModal(preselectedSubject = "") {
    if (state.running) {
      toast("현재 녹음을 먼저 종료해주세요.", "error");
      return;
    }
    populateSubjectSelects();
    els.newSessionSubject.value = preselectedSubject || state.session?.subject_id || "";
    els.newSessionName.value = "";
    const savedDenoise = clampDenoiseStrength(localStorage.getItem(DENOISE_PREF_KEY) ?? 2);
    if (els.newSessionDenoise) els.newSessionDenoise.value = String(savedDenoise);
    const savedSttSource = normalizeSttAudioSource(localStorage.getItem(STT_SOURCE_PREF_KEY) || "raw");
    if (els.newSessionSttSource) els.newSessionSttSource.value = savedSttSource;
    openModal("session");
  }

  async function shutdownApp() {
    const ok = window.confirm("Local Clova ASR/LoRA 런타임과 종료 컨트롤러를 모두 종료할까요?");
    if (!ok) return;
    const button = $("#shutdownApp");
    button.disabled = true;
    try {
      const data = await fetchJSON("/api/app/shutdown", { method: "POST" });
      if (!data.ok) throw new Error("shutdown controller did not confirm");
      els.shutdownOverlay.classList.remove("hidden");
    } catch (error) {
      button.disabled = false;
      toast(`앱 종료 요청 실패: ${error.message}`, "error");
    }
  }

  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }

  function updateFullscreenButton() {
    const btn = document.getElementById("fullscreenToggle");
    if (!btn) return;
    const active = Boolean(fullscreenElement());
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
    btn.setAttribute("aria-label", active ? "전체화면 종료" : "전체화면");
    btn.title = active ? "전체화면 종료 (Esc)" : "전체화면";
    els.appShell?.classList.toggle("fullscreen-active", active);
  }

  async function toggleFullscreen() {
    // V7.7: fullscreen the document root, not only #appShell. Browsers render
    // only the fullscreen element's subtree in fullscreen mode. Our modal,
    // toast, and shutdown layers intentionally live next to #appShell, so
    // fullscreening only #appShell made interactions such as “새 세션” open
    // invisibly until fullscreen was exited. Using <html> keeps every app
    // overlay in the fullscreen rendering tree and is safer for future V8 UI.
    const target = document.documentElement;
    try {
      if (!fullscreenElement()) {
        if (target.requestFullscreen) await target.requestFullscreen({ navigationUI: "hide" });
        else if (target.webkitRequestFullscreen) target.webkitRequestFullscreen();
      } else {
        if (document.exitFullscreen) await document.exitFullscreen();
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
      }
    } catch (error) {
      console.warn("Fullscreen request failed:", error);
      toast("전체화면 전환에 실패했습니다. 브라우저 권한을 확인해주세요.", "error");
    }
    updateFullscreenButton();
  }

  function wireEvents() {
    $("#newSessionBtn").addEventListener("click", () => openNewSessionModal());
    $("#heroNewSession").addEventListener("click", () => openNewSessionModal());
    $("#sidebarNewSubject").addEventListener("click", () => {
      state.assignNewSubjectToSession = false;
      openModal("subject");
    });
    $("#newSubjectBtn").addEventListener("click", () => {
      state.assignNewSubjectToSession = Boolean(state.sessionId);
      openModal("subject");
    });

    els.search.addEventListener("input", () => {
      state.search = els.search.value;
      renderSidebar();
    });

    els.newSessionForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const title = els.newSessionName.value.trim();
      if (!title) return;
      const denoiseStrength = 0;
      const sttAudioSource = "raw";
      startSession(title, els.newSessionSubject.value, denoiseStrength, sttAudioSource);
    });

    els.newSubjectForm.addEventListener("submit", (event) => {
      event.preventDefault();
      createSubject();
    });

    $$('[data-close-modal="session"]').forEach((x) => x.addEventListener("click", () => closeModal("session")));
    $$('[data-close-modal="subject"]').forEach((x) => x.addEventListener("click", () => closeModal("subject")));
    [els.sessionModal, els.subjectModal].forEach((backdrop) => {
      backdrop.addEventListener("mousedown", (event) => {
        if (event.target === backdrop) backdrop.classList.add("hidden");
      });
    });

    els.stopBtn.addEventListener("click", stopSession);
    els.resumeBtn.addEventListener("click", resumeSession);
    els.autoPlayBtn.addEventListener("click", toggleAutoPlay);
    els.postBtn?.addEventListener("click", postprocessSession);
    els.deletedToggle.addEventListener("click", toggleDeletedSegments);
    els.returnToPlaying.addEventListener("click", () => {
      state.autoPlayFollow = true;
      updateAutoFollowToggle();
      updateReturnToPlaying();
      scrollToPlaying({ smooth: true });
    });
    $("#shutdownApp").addEventListener("click", shutdownApp);

    els.subjectSelect.addEventListener("change", () => saveSessionMeta({ subject_id: els.subjectSelect.value }));
    if (els.denoiseStrength) {
      els.denoiseStrength.addEventListener("input", () => updateDenoiseUi(els.denoiseStrength.value));
      els.denoiseStrength.addEventListener("change", async () => {
        const level = updateDenoiseUi(els.denoiseStrength.value);
        localStorage.setItem(DENOISE_PREF_KEY, String(level));
        await saveSessionMeta({ denoise_strength: level });
        toast(`노이즈 캔슬링: ${DENOISE_LABELS[level]} · 다음 SEG부터 적용`);
      });
    }
    if (els.sttAudioSource) {
      els.sttAudioSource.addEventListener("change", async () => {
        const source = normalizeSttAudioSource(els.sttAudioSource.value);
        localStorage.setItem(STT_SOURCE_PREF_KEY, source);
        await saveSessionMeta({ stt_audio_source: source });
        toast(`BatiSay 입력: ${source === "raw" ? "RAW 원본" : "CLEAN 정제본"} · 다음 SEG부터 적용`);
      });
    }
    els.addTagBtn.addEventListener("click", addTag);
    els.tagInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        addTag();
      }
    });

    if (els.professorInput) {
      const commitProfessor = async () => {
        if (!state.session?.subject_id || trainingIsRunning(state.session?.adaptive_asr)) return;
        const name = els.professorInput.value.trim();
        try {
          await fetchJSON("/api/subject/professor", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ subject_id: state.session.subject_id, professor_name: name }),
          });
          await loadLibrary({ quiet: true });
          await refreshSelectedSession();
          toast(name ? `${name} 교수 프로필을 과목에 연결했습니다.` : "교수 연결을 해제했습니다.");
        } catch (error) {
          toast(`교수 저장 실패: ${error.message}`, "error");
        }
      };
      els.professorInput.addEventListener("change", commitProfessor);
      els.professorInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          els.professorInput.blur();
        }
      });
    }

    els.layerSwitch?.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-layer]");
      if (!button) return;
      state.layer = "final";
      syncLayerButtons();
      renderTranscript();
    });

    els.player.addEventListener("play", () => {
      if (!state.autoPlayUsingWebAudio) state.autoPlayPaused = false;
      updateAutoPlayButton();
    });
    els.player.addEventListener("timeupdate", () => {
      if (state.autoPlayUsingWebAudio || state.playingSegment == null) return;
      const seg = state.segments.find((item) => Number(item.segment) === Number(state.playingSegment));
      if (seg) {
        updatePlayingWord(seg, els.player.currentTime);
        syncPdfToPlaybackSegment(seg, els.player.currentTime);
      }
    });
    els.player.addEventListener("seeking", () => {
      if (state.autoPlayUsingWebAudio || state.playingSegment == null) return;
      const seg = state.segments.find((item) => Number(item.segment) === Number(state.playingSegment));
      if (seg) {
        updatePlayingWord(seg, els.player.currentTime);
        syncPdfToPlaybackSegment(seg, els.player.currentTime, { force: true });
      }
    });
    els.player.addEventListener("pause", () => {
      if (state.autoPlayActive && !state.autoPlayUsingWebAudio) state.autoPlayPaused = true;
      updateAutoPlayButton();
    });
    els.player.addEventListener("ended", async () => {
      if (state.autoPlayActive && !state.autoPlayUsingWebAudio) {
        await playRelativeSegment(1);
        return;
      }
      if (!state.autoPlayActive) setPlayingSegment(null, { smooth: false });
      clearPlayingWord();
    });
    els.playerPrev.addEventListener("click", () => playRelativeSegment(-1));
    els.playerPause.addEventListener("click", togglePlayerPause);
    els.playerNext.addEventListener("click", () => playRelativeSegment(1));
    els.playbackSpeed.addEventListener("change", async () => {
      const nextRate = Math.max(.5, Math.min(3, Number(els.playbackSpeed.value) || 1));
      if (Math.abs(nextRate - state.playbackRate) < 0.001) return;
      const pos = state.autoPlayActive && state.autoPlayUsingWebAudio ? currentGaplessPosition() : null;
      state.playbackRate = nextRate;
      els.player.playbackRate = state.playbackRate;
      if ("preservesPitch" in els.player) els.player.preservesPitch = true;
      if ("mozPreservesPitch" in els.player) els.player.mozPreservesPitch = true;
      if ("webkitPreservesPitch" in els.player) els.player.webkitPreservesPitch = true;
      if (pos && !state.autoPlayPaused) {
        state.autoPlayLoading = true;
        updateAutoPlayButton();
        try {
          // Pre-warm the new tempo while the old scheduled audio keeps playing.
          // Then capture the fresh source-time position and switch schedules.
          const warm = state.playbackList.slice(pos.index, pos.index + 6);
          await Promise.allSettled(warm.map((seg) => loadPitchLockedPlaybackBuffer(seg, nextRate)));
          const freshPos = currentGaplessPosition();
          state.playbackResumeIndex = freshPos.index;
          state.playbackResumeOffset = freshPos.offset;
          await launchGaplessSchedule(freshPos.index, freshPos.offset);
        } finally {
          state.autoPlayLoading = false;
          updateAutoPlayButton();
        }
      }
    });
    els.autoFollowToggle.addEventListener("click", () => {
      state.autoPlayFollow = !state.autoPlayFollow;
      updateAutoFollowToggle();
      updateReturnToPlaying();
      if (state.autoPlayFollow) scrollToPlaying({ smooth: true });
    });
    els.gaplessTrack.addEventListener("click", async (event) => {
      const rect = els.gaplessTrack.getBoundingClientRect();
      if (!rect.width) return;
      await seekGaplessFraction((event.clientX - rect.left) / rect.width);
    });
    els.themeToggle.addEventListener("click", toggleTheme);
    wireColumnResizer(els.sidebarSplitter, { kind: "sidebar" });
    wireColumnResizer(els.pdfTranscriptSplitter, { kind: "pdf" });
    wirePdfWorkspace();
    const fullscreenToggle = document.getElementById("fullscreenToggle");
    if (fullscreenToggle) fullscreenToggle.addEventListener("click", toggleFullscreen);
    document.addEventListener("fullscreenchange", updateFullscreenButton);
    document.addEventListener("webkitfullscreenchange", updateFullscreenButton);
    $("#closePlayer").addEventListener("click", () => stopPlayback({ hidePlayer: true }));

    $("#collapseSidebar").addEventListener("click", () => {
      if (window.innerWidth <= 760) els.appShell.classList.remove("sidebar-open");
      else els.appShell.classList.toggle("sidebar-collapsed");
    });
    $("#openSidebar").addEventListener("click", () => els.appShell.classList.add("sidebar-open"));
    $("#reopenSidebar").addEventListener("click", () => {
      els.appShell.classList.remove("sidebar-collapsed");
      if (window.innerWidth <= 760) els.appShell.classList.add("sidebar-open");
    });
    $("#toggleInspector").addEventListener("click", () => {
      els.appShell.classList.toggle("inspector-open");
    });
    $("#closeInspector").addEventListener("click", () => els.appShell.classList.remove("inspector-open"));

    document.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        openNewSessionModal();
      }
      if (event.key === "Escape") {
        closeModal("session");
        closeModal("subject");
        els.appShell.classList.remove("sidebar-open", "inspector-open");
      }
    });
  }


  // =========================================================
  // V8.2-epsilon.4 UI cleanup
  // Whisper-only production UI. Legacy nodes stay in the DOM for old-session
  // compatibility, but users never see or interact with retired ASR controls.
  // This function does not touch capture, VAD, segmentation, preview, final
  // Whisper inference, word_audio_map, or playback.
  // =========================================================
  function enforceEpsilon4Ui() {
    state.layer = "final";

    const legacyIds = [
      "postprocessBtn",
      "layerSwitch",
      "postprocessProgress",
      "newSessionDenoise",
      "denoiseStrength",
      "denoiseStrengthLabel",
      "sttAudioSource",
    ];
    for (const id of legacyIds) {
      const node = document.getElementById(id);
      if (!node) continue;
      node.classList.add("hidden");
      node.setAttribute("aria-hidden", "true");
      if ("disabled" in node) node.disabled = true;
    }

    document.querySelectorAll(".professor-section").forEach((node) => {
      node.classList.add("hidden");
      node.setAttribute("aria-hidden", "true");
    });
  }

  async function bootstrap() {
    enforceEpsilon4Ui();
    applySavedColumnWidths();
    initTheme();
    updateFullscreenButton();
    els.subjectSemester.value = currentSemester();
    wireEvents();
    await loadLibrary();
    showSession();

    const newestRecording = state.library.sessions.find((s) => s.recording);
    if (newestRecording) await openSession(newestRecording.session_id, { quiet: true });

    // While recording, pollRecordingStatus() drives refreshes. This loop only
    // covers the tail after Stop while final Whisper segments are pending.
    setInterval(() => {
      if (
        state.sessionId
        && !state.running
        && Number(state.session?.pending_count || 0) > 0
      ) {
        refreshSelectedSession();
      }
    }, 700);

    setInterval(() => loadLibrary({ quiet: true }), 7000);
  }

  bootstrap();
})();
