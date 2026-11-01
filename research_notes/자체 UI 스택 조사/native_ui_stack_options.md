# Native desktop UI stack options for Local Clova (Linux / GNOME Wayland), as of 2026-11-01

Scope: replacing the ~4,200-line vanilla-JS single page (served by Flask in Docker) with a native UI on Ubuntu 24.04, GNOME/Wayland, HP ZBook Ultra G1a (touch + active pen, AMD Strix Halo iGPU). Stacks covered: Qt 6 (QML/Widgets; C++, PySide6, Rust bindings), GTK 4/libadwaita (gtk-rs, PyGObject), Tauri 2 (WebKitGTK), Slint, Flutter desktop, egui/iced.

Research budget note: 15 search/fetch calls. Several things below are marked "training knowledge, not re-verified in this session"; treat them as needing a check before a decision. Search-engine summaries (not the full primary page) were the basis for some citations; that is noted where it matters.

## Q1. Which stack has the best-supported stylus pressure + touch gestures on GNOME Wayland in 2026?

### Takeaway
Qt 6 and GTK 4 are the only two stacks with a native, toolkit-level Wayland tablet-v2 path that delivers pressure/tilt as first-class events. Both are proven by shipping pen apps (Krita/Okular-class Qt apps; Rnote on GTK 4). Tauri/WebKitGTK has a reported "pressure always 0" problem; Flutter on Linux needs a third-party plugin for pressure; Slint, egui and iced showed no evidence of pressure support in this session.

### Cited Findings
- **Qt 6 (Wayland client) implements `zwp_tablet_tool_v2`**. The pressure handler normalises the raw 32-bit value by 65535 and buffers it until the frame event, then builds a `QTabletEvent` with pressure, tilt and buttons — [Qt 6 qtwayland source, qwaylandtabletv2.cpp](https://code.woboq.org/qt6/qtwayland/src/client/qwaylandtabletv2.cpp.html); [header](https://codebrowser.dev/qt6/qtwayland/src/client/qwaylandtabletv2_p.h.html)
- `QTabletEvent::pressure()` returns 0.0 (not touching) to 1.0 (maximum) — [Qt 6.2 QTabletEvent docs](https://doc.qt.io/qt-6.2/qtabletevent.html)
- The Wayland pen pipeline goes compositor (libinput) → tablet-v2 protocol → toolkit. A KDE blog post (read via an aggregator, not the original) describes Qt turning incoming tablet-v2 events into `QTabletEvent` and delivering them to all UI elements — [KDE blog via flosshub aggregator](https://flosshub.org/aggregator/images/posts/building-a-modern-drupal-theme-with-storybook?page=10)
- **GTK 4 / Rnote**: Rnote is a GTK 4 + libadwaita app that depends on Poppler — [AOSC package listing](https://packages.aosc.io/packages/rnote); [Rnote repo](https://github.com/flxzt/rnote)
- In Rnote issues, users with pressure broken on X11 said it worked when they switched to Wayland. The maintainer said stylus/pressure recognition "happens inside libinput and GTK". The issues date from 2022–2024 — [rnote #19](https://github.com/flxzt/rnote/issues/19); [rnote #194](https://github.com/flxzt/rnote/issues/194)
- GTK exposes pen pressure through device axes that an app reads from the event — [Wacom developer docs, GTK overview](https://developer-docs.wacom.com/docs/icbt/linux/gtk/gtk-overview/)
- Old GTK Wayland stylus bugs: in GTK issue #3443, the stylus pointer was displaced from the pen position on Wayland (gtk4-demo Paint) but not on Xorg. GTK issue #2198 covers GTK 3 apps crashing on Wayland stylus input, where an earlier fix was only partial. I did not check whether either is still open in 2026 — [GTK #3443](https://gitlab.gnome.org/GNOME/gtk/-/issues/3443); [GTK #2198](https://gitlab.gnome.org/GNOME/gtk/-/issues/2198)
- **Tauri / WebKitGTK**: an April 2024 Reddit report from a Tauri-on-Linux developer says `PointerEvent.pressure` always returned 0 (X/Y worked). Epiphany, which is also WebKitGTK, showed no pressure either, while Firefox did. The report is anecdotal and had no visible answer — [r/WebKit post, Apr 2024 (mirror)](https://lr.eu.psf.lt/r/WebKit)
- Firefox's GTK backend added pressure/tilt for PointerEvent from GDK axes in Oct 2024. This shows the browser-engine layer, not GTK, has to do this work — [Tor/Mullvad mirror of the Firefox patch](https://gitlab.torproject.org/tpo/applications/mullvad-browser/-/commit/18531f025b2ace38d02f414ff37bbf8631a4a799); [seul.org commit list, Oct 2024](https://archives.seul.org/or/cvs/Oct-2024/msg00114.html)
- **Flutter on Linux**: in Saber issue #90, Flutter on Linux did not report pressure and classified the pen as a finger on one laptop. Maintainers pointed at Flutter's handling, since Krita and Xournal++ read pressure fine on the same machine — [saber #90](https://github.com/adil192/saber/issues/90)
- A third-party Flutter plugin, `stylet`, adds pressure, tilt and barrel rotation on Linux via Wayland tablet-v2 or GTK. Its pub.dev table lists pressure and tilt as supported on Linux — [stylet on pub.dev](https://pub.dev/packages/stylet); [stylet docs](https://pub.dev/documentation/stylet/latest/)
- **Slint**: the `PointerEvent` passed to `TouchArea` exposes button, kind and modifiers. The search summary also reported a touch/finger id field. No pressure field was found — [Slint PointerEvent (Python API)](https://docs.slint.dev/latest/docs/python/api/language/classes/pointerevent/); [Slint PointerEvent (C++ API)](https://docs.slint.dev/latest/docs/cpp/api/slint/language/pointerevent/)
- Pressure handling is inconsistent across Linux apps even on the same hardware. On one Fedora KDE system, Krita/GIMP read pressure and MyPaint did not — [Framework community thread](https://community.frame.work/t/inconsistencies-with-stylus-pressure-recognition-across-programs-oss/75317)

### Inferences
- **Ranking for pen + touch on GNOME Wayland (best → worst):** Qt 6 ≈ GTK 4 > Flutter (with the `stylet` plugin) > Tauri/WebKitGTK > Slint / egui / iced.
- **Qt vs GTK:** both consume the same mutter tablet-v2 stream. They differ in API ergonomics more than in data quality.
  - Qt Quick has declarative pointer handlers: `PointHandler`/`DragHandler` filtered by device type, plus `PinchHandler`. That maps directly to "one-finger draw, two-finger pan/pinch, pen draws". This is training knowledge, not re-verified in this session.
  - GTK 4 has `GtkGestureStylus` (axes incl. pressure/tilt) and `GtkGestureZoom`/`GtkGestureDrag` controllers. Also training knowledge for the controller names.
- **Hardware:** the ZBook Ultra G1a pen is almost certainly a USB-HID/I2C-HID pen digitiser handled by libinput, so both toolkits get it via mutter. This was not verified against this specific model.
- **Per-stack summary matrix** (my synthesis; individual facts are cited elsewhere in these notes or listed as gaps):

| Stack | Wayland pen pressure | Touch pan/pinch | PDF path | Long-list perf | Port effort from JS | Maturity (Nov 2026) |
|---|---|---|---|---|---|---|
| Qt 6 QML (C++ or PySide6) | Native tablet-v2 → QTabletEvent / pointer handlers | PinchHandler / multi-touch built in | Qt PDF (PDFium, LGPLv3/GPLv2) + own ink layer | ListView virtualisation (delegate recycling) | High (rewrite UI in QML; JS knowledge helps) | Very mature; 6.12 LTS reported Sep 2026 |
| Qt 6 + Rust (CXX-Qt / Qt Bridge for Rust) | Same as Qt | Same as Qt | Same as Qt | Same as Qt | Highest (two languages + build glue) | CXX-Qt 0.10 (Aug 2026); Qt Bridge for Rust only Tech Preview (Oct 2026) |
| GTK 4 + libadwaita (gtk-rs / PyGObject) | Native tablet-v2 → GtkGestureStylus (proven by Rnote) | GtkGestureZoom/Drag | Poppler (GPL) + Cairo/snapshot ink layer | GtkListView (recycling) | High (imperative widget code) | Mature; renderer churn 4.14–4.16 |
| Tauri 2 (WebKitGTK) | Reported pressure=0 in WebKitGTK | Web touch events (WebKitGTK quality unknown) | PDF.js in WebKitGTK | DOM; WebKitGTK reported slower than Chromium | Lowest (reuse existing JS) | Tauri 2 stable; Linux graphics caveats documented |
| Flutter Linux | Only via 3rd-party `stylet` plugin | Flutter gestures OK | pdfrx (PDFium) | ListView.builder OK | High (Dart rewrite) | Linux is the weakest Flutter desktop target |
| Slint | No pressure field found | Not verified | None built in | Not verified | High | Mature for embedded; no PDF/pen ecosystem |
| egui / iced | No evidence found | Not verified | None built in | egui immediate mode; iced not verified | High | Not recommended for this app |

### Gaps
- No 2026-dated GNOME/mutter or Qt bug report on tablet-v2 regressions was found, so recent regressions could not be confirmed or ruled out.
- No source found on whether WebKitGTK fixed `PointerEvent.pressure` after April 2024. A search of the WebKit Bugzilla is needed.
- Slint pinch-gesture support and any Slint pressure roadmap were not found.
- No primary source was found for winit/egui/iced tablet or pressure support; the search returned only unrelated hardware pages. My training knowledge is that winit has had tablet/pen PRs but no stable cross-platform pressure API. This is not verified.
- No source specific to the HP ZBook Ultra G1a's pen digitiser on Linux was found. Testing with `libinput debug-events` and `libinput list-devices` is recommended.

## Q2. Which has the most practical PDF rendering + ink annotation path (Qt PDF, Poppler, PDFium, MuPDF bindings)?

### Takeaway
Qt PDF (PDFium-based, LGPLv3) gives a complete QML multi-page viewer out of the box. Ink annotation is drawn by the app as its own overlay layer. GTK 4 apps (Rnote, Xournal++) use Poppler for rendering and their own stroke model. On every stack, annotations are best stored in the app's own timeline-linked stroke format, not written into the PDF.

### Cited Findings
- **Qt PDF** "uses PDFium to parse and render PDF documents". C++ classes: `QPdfDocument`, `QPdfPageRenderer`, `QPdfPageNavigator`, `QPdfSearchModel`, `QPdfBookmarkModel`, `QPdfLinkModel`, `QPdfView` — [Qt PDF docs (doc-snapshots)](https://doc-snapshots.qt.io/qtpdf/qtpdf-index.html)
- Qt PDF's QML viewers are `PdfMultiPageView` (recommended for whole-document scrolling), `PdfScrollablePageView` and `PdfPageView`. Lower-level QML types include `PdfDocument`, `PdfPageImage`, `PdfSelection` and `PdfSearchModel` — [Qt PDF docs](https://doc-snapshots.qt.io/qtpdf/qtpdf-index.html)
- **Qt PDF license**: LGPLv3 or GPLv2, with a commercial option from The Qt Company — [Qt PDF docs](https://doc-snapshots.qt.io/qtpdf/qtpdf-index.html)
- The Qt PDF docs page describes viewing, rendering, search, navigation, bookmarks, links and text selection. It says nothing about annotation editing — [Qt PDF docs](https://doc-snapshots.qt.io/qtpdf/qtpdf-index.html)
- Caution: the fetched page was a doc-snapshots (development) build. The page's version string read as "6.140.0", which looks like a snapshot artefact, not a release number.
- **Rnote** (GTK 4 + libadwaita, Rust) lists Poppler as a dependency for PDF import — [AOSC package listing](https://packages.aosc.io/packages/rnote)
- **Xournal++** is still C++/GTK 3. A GTK 4/libadwaita port is "not actively being worked on currently", and maintainers say the direction is unclear — [xournalpp discussion #7212](https://github.com/xournalpp/xournalpp/discussions/7212); [xournalpp #4339](https://www.github.com/xournalpp/xournalpp/issues/4339)
- **Saber** (Flutter) is a handwriting app that targets Linux. Its pen-input problems on Linux are tracked in issue #90 — [saber #90](https://github.com/adil192/saber/issues/90)

### Inferences
- **Most practical path for this app: Qt Quick `PdfMultiPageView`, or a custom `ListView` of `PdfPageImage` delegates, plus a transparent ink layer per page.**
  - The ink layer would be a QML `Shape`/`Canvas`, or for performance a custom `QQuickItem` (scene-graph geometry) fed by stylus pointer events.
  - Strokes are stored in your own schema: page, points with pressure, and an audio-time timestamp. That schema is what links strokes to the timeline, and PDF annotation objects cannot carry it anyway.
  - Optionally export flattened annotated PDFs later with a separate tool (e.g. PyMuPDF or pikepdf in the Python side). That tooling suggestion is training knowledge.
- **GTK path**: Poppler (GLib bindings, renders to Cairo), page textures in a `GtkListView`/custom widget, and strokes drawn via `GtkSnapshot`. This is exactly Rnote's architecture, so a working open-source reference exists, in Rust.
  - Poppler is GPL-licensed (training knowledge). That is fine for a personal, open-source app.
- **MuPDF**: very fast and good at annotation writing, but AGPL/commercial (training knowledge). Probably only useful on the Python side (PyMuPDF) for export, not in the UI.
- **PDFium** is what both Qt PDF and Flutter's pdfrx use. pdfrx being PDFium-based is training knowledge, not re-verified here.
- PDF.js (the current web UI path) remains viable only if staying on a web view (Tauri), which brings back the DOM dependency.

### Gaps
- Qt PDF rendering performance on large slide decks (hundreds of pages, high-DPI, fractional scale) was not measured or found.
- I did not confirm whether Qt PDF's `PdfMultiPageView` lets you overlay custom items per page cleanly, versus building a custom `ListView` of `PdfPageImage`.
- I did not verify pdfrx's Linux maturity in 2026.
- No 2026 source compared Poppler vs PDFium rendering speed or quality.

## Q3. Is a staged migration possible (keep Flask APIs and swap the front end first; Tauri as an intermediate step; QML without WebEngine)?

### Takeaway
Yes. The lowest-risk sequence keeps the Flask HTTP/SSE API as the contract, builds a QML (no WebEngine) or GTK front end against it page by page, and only later replaces Flask with a Rust/C++ core. Tauri as an intermediate step mostly buys a window frame. It brings documented WebKitGTK graphics issues, a reported missing pen pressure, and slower rendering than Chromium, so it is a weak stepping stone for a pen-centric UI.

### Cited Findings
- Tauri's official Linux graphics page says WebKitGTK and GPU drivers can disagree, most often on NVIDIA. Symptoms are blank windows, resize flicker and crashes, mostly tied to the DMABUF renderer. Workarounds:
  - `WEBKIT_DISABLE_DMABUF_RENDERER=1`, which loses the fast path.
  - `WEBKIT_DISABLE_COMPOSITING_MODE=1`, a last resort.
  - Source: [Tauri v2 docs, Linux Graphics Issues](https://v2.tauri.app/develop/debug/linux-graphics/)
- The same Tauri page notes high input latency or low frame rate in WebGL-heavy views on Linux, even when the same code is fast in a regular browser — [Tauri v2 docs, Linux Graphics Issues](https://v2.tauri.app/develop/debug/linux-graphics/)
- Wry maintainers acknowledged "WebkitGTK isn't that great". Users reported much slower rendering than Chromium and slow startup on weaker hardware. This is a 2023 issue — [wry #890](https://github.com/tauri-apps/wry/issues/890)
- WebKitGTK `PointerEvent.pressure` was reported as always 0 in a Tauri app (Apr 2024) — [r/WebKit mirror](https://lr.eu.psf.lt/r/WebKit)
- **Qt Bridge for Rust**: Qt's own Rust↔Qt Quick bridge reached Technology Preview on 2026-10-27, with APIs and requirements still subject to change. It supports cross-thread invocation (e.g. from a tokio runtime) and shares foundations with CXX-Qt — [Qt blog, Qt Bridges technology preview](https://www.qt.io/blog/qt-bridges-technology-preview-rust-csharp?hs_amp=true); [Qt Bridges public beta for Rust](https://qt.io/blog/qt-bridges-public-beta-for-rust); [Rust UI framework via bridging technology](https://qt.io/blog/rust-ui-framework-via-bridging-technology)
- Qt Bridge for Rust needs a C++ toolchain and qmake on PATH — [Qt blog](https://qt.io/blog/rust-ui-framework-via-bridging-technology)
- **CXX-Qt (KDAB)** crates.io versions: 0.8.1 (2026-02-17), 0.9.0 (2026-06-23), 0.9.1 (2026-07-03), 0.10.0 (2026-08-24). These dates come from a search summary of the crates.io API; I did not read the release notes — [crates.io cxx-qt](https://crates.io/api/v1/crates/cxx-qt)
- KDAB's guidance describes CXX-Qt as composing QObject subclasses from items in a Rust module — [Rust Foundation / KDAB guest post](https://rustfoundation.org/media/best-practices-for-integrating-rust-and-qt-in-embedded-systems/)
- Qt 6.12 LTS appears on the Qt blog dated 2026-09-30. This comes from a search snippet; I did not open the post — [Qt blog listing](https://www.qt.io/blog/?p=37365)

### Inferences
- **Recommended staging:**
  1. **Stage 0:** move Flask out of Docker, or just expose it on a Unix socket or localhost-only port. Keep the existing JSON endpoints and live-update channel (SSE or WebSocket) as the frozen contract.
  2. **Stage 1:** a QML app using `QNetworkAccessManager` (REST/SSE) or `QtWebSockets` against Flask. Port views in order of value: PDF + ink first (the biggest win over the browser), then the transcript list, then the library and status.
     - This needs no Qt WebEngine, so there is no Chromium.
     - PySide6 is the fastest way to do this, because the existing backend team language is Python.
  3. **Stage 2:** move audio playback and timeline into the native app (Qt Multimedia or a GStreamer/PipeWire path). The browser's gapless audio is the hardest thing to match.
  4. **Stage 3:** replace Flask with a Rust or C++ core daemon over a Unix socket, keeping the Python ASR workers. With CXX-Qt 0.10 or the Qt Bridge for Rust, the core could also be linked into the UI process.
- **Tauri as a stepping stone:** it reuses the 4,200-line JS almost as-is. But on Linux it uses WebKitGTK, not Chromium. Expected regressions versus Chrome today:
  - pen pressure
  - rendering speed
  - DMABUF quirks
  - Moving to Tauri does not move you toward QML, because the UI code is not reused. So it is a detour unless the goal is only to drop Chrome quickly. Tauri's CEF/Chromium runtime work would remove the WebKitGTK issues but re-adds Chrome. CEF status was not verified.
- **Python vs Rust for the UI process:** PySide6 gives the shortest port time. Rust bindings are now two competing official-ish paths (KDAB CXX-Qt, stable-ish; Qt Bridge for Rust, preview). That suggests C++ or PySide6 for the UI and Rust for a separate core daemon, rather than Rust-in-UI, until the Qt Bridge stabilises.

### Gaps
- Status of Tauri's CEF runtime on Linux in 2026 was not found.
- No source checked for Qt Multimedia gapless playback quality on Linux. My training knowledge is that Qt 6 Multimedia uses an FFmpeg backend by default since Qt 6.5, with a GStreamer backend optional; not re-verified.
- No source found on PySide6 vs C++ QML performance for long ListViews. The common guidance is to keep models in C++/Rust or efficient Python `QAbstractListModel` implementations, but it was not verified.
- Ubuntu 24.04's archive Qt version (training knowledge: Qt 6.4.x) is far behind 6.12. Using pip PySide6 wheels or the Qt online installer/aqtinstall avoids this, but the exact versions were not verified.

## Q4. What IPC/architecture patterns are recommended between a native UI and Python ML workers (Unix socket + JSON/protobuf, gRPC, shared memory for audio)?

### Takeaway
I found no authoritative 2026 source on this exact pattern, so this section is mostly engineering inference. A Unix domain socket carrying length-prefixed JSON (or MessagePack) events, with audio exchanged as files or PipeWire streams rather than through IPC, fits a single-user local app best. gRPC and shared memory add cost without clear benefit at this scale.

### Cited Findings
- Qt Bridge for Rust supports cross-thread invocation (e.g. from a tokio runtime) and direct `serde_json` support. That makes a Rust core receiving JSON from Python workers and pushing it to QML a supported shape — [Qt Bridges public beta for Rust](https://qt.io/blog/qt-bridges-public-beta-for-rust); [Qt Bridges technology preview](https://www.qt.io/blog/qt-bridges-technology-preview-rust-csharp?hs_amp=true)
- The Wayland input chain is compositor → protocol → toolkit. Input never crosses into the core process, so pen latency stays inside the UI process regardless of the IPC choice — [KDE blog via aggregator](https://flosshub.org/aggregator/images/posts/building-a-modern-drupal-theme-with-storybook?page=10)

### Inferences
- **Recommended shape:**
  - **UI process** (QML or GTK) owns rendering, pen input, PDF and ink, and local playback.
  - **Core daemon** (Rust or C++, or Flask during migration) owns the session DB, the timeline index and the capture-daemon status.
  - **Python ASR workers** (whisper.cpp server plus post-processing) are spawned and supervised by the core.
- **Transport:** a Unix domain socket in `$XDG_RUNTIME_DIR` with newline-delimited or length-prefixed JSON messages. It works natively with `QLocalSocket` in Qt, `GSocketClient`/`GUnixSocketAddress` in GTK, tokio `UnixStream` in Rust, and `asyncio.start_unix_server` in Python. Typical messages are `segment.partial`, `segment.final`, `word.timings`, `capture.status`, `job.progress`.
  - Switch to MessagePack or protobuf only if profiling shows JSON cost. About 600 segments per 2 h is tiny.
- **gRPC:** workable (Python and Rust both have good stacks, Qt has QtGrpc in recent versions; training knowledge). But it is more build and tooling weight than a personal app needs. It mainly earns its keep when strong schemas across many services matter.
- **Audio:** don't push PCM over IPC.
  - Capture already writes via `pw-record`. Have the core write finalized segment files (e.g. Opus/FLAC or WAV chunks), and have both the ASR worker and the UI read those files.
  - For live monitoring, the UI can open its own PipeWire stream.
  - Shared memory (memfd plus a ring buffer) is only justified if the UI must render a live waveform at high rate.
- **D-Bus:** an alternative for daemon status, since it is a GNOME-native session bus. It is overkill for streaming transcript data, but nice for "capture daemon running/recording" state and a GNOME Shell indicator.
- **Keep timestamps in one clock domain**: audio sample index or ms from session start. Transcript words, PDF page-view events and ink strokes then all join on the same axis. This is an architectural recommendation, not sourced.

### Gaps
- No primary source (Qt/KDE/GNOME blog or well-known open-source app) was found documenting a native-UI ↔ Python-ML IPC pattern for comparison.
- QtGrpc/QtProtobuf module status in Qt 6.12 was not verified.

## Q5. Concrete pitfalls reported for each stack on Wayland/AMD (rendering backends, fractional scaling, tablet input bugs)?

### Takeaway
GTK 4's 2024 renderer transition (GL "ngl" → Vulkan) produced AMD and fractional-scaling bugs, now largely patched. Tauri/WebKitGTK has documented DMABUF/compositing problems and slower rendering. Flutter on Linux misclassifies pens. Qt's Wayland tablet path is mature, but no 2026-dated issues were surveyed.

### Cited Findings
- **GTK 4 renderers**:
  - GTK developers said in Jan 2024 they would not make the Vulkan renderer the default yet, partly because WebKit's GTK 4 port and GL-based widgets didn't work with it — [GTK blog, New renderers for GTK, 2024-01-28](https://blog.gtk.org/2024/01/28/new-renderers-for-gtk/)
  - The new unified GL renderer ("ngl") became the default as a trial in the 4.13.6 snapshot. This comes from a search summary — [GTK blog Jan 2024 archive](https://blog.gtk.org/2024/01/)
- **GTK 4 + AMD + fractional scaling**:
  - A merge request added Vulkan fractional-scale support and clip fixes that let a user run GTK 4 with Vulkan on an AMD card again (crash fixed) — [GTK MR !5783](https://gitlab.gnome.org/GNOME/gtk/-/merge_requests/5783)
  - GTK 4.15.1 issue: blurry UI with the Vulkan renderer at 125% scaling — [GTK #6730](https://gitlab.gnome.org/GNOME/gtk/-/issues/6730)
  - Black borders and erratic scaling on GNOME 47 with AMD and GTK 4.15.3's Vulkan renderer. The workaround was `GSK_RENDERER=gl` — [NixOS Discourse](https://discourse.nixos.org/t/fix-for-black-borders-in-gnome-47-using-amd/56853)
  - A VTE issue on font rendering with Wayland fractional scaling under the ngl/Vulkan renderers — [VTE #2736](https://gitlab.gnome.org/GNOME/vte/-/issues/2736)
- **GTK stylus**: pointer/stylus displacement on Wayland in gtk4-demo Paint, not seen on Xorg — [GTK #3443](https://gitlab.gnome.org/GNOME/gtk/-/issues/3443). GTK 3 apps crashing with stylus on Wayland — [GTK #2198](https://gitlab.gnome.org/GNOME/gtk/-/issues/2198)
- **Compositor/libinput level, affects all toolkits**:
  - KWin issue: many apps handle Wayland stylus events poorly (DnD, right/left-click) — [KWin #184](https://invent.kde.org/plasma/kwin/-/issues/184)
  - libinput pressure-offset bug, where the same pen worked on X but not Wayland — [freedesktop #103086](https://bugs.freedesktop.org/show_bug.cgi?id=103086)
  - KDE discussion on whether strokes should register with zero/missing pressure — [discuss.kde.org](https://discuss.kde.org/t/should-kwin-receive-stylus-stroke-input-even-with-missing-zero-pressure-input/35449)
- **Tauri/WebKitGTK**: DMABUF renderer issues (blank window, resize flicker/crash), env-var workarounds, and WebGL latency — [Tauri Linux Graphics Issues](https://v2.tauri.app/develop/debug/linux-graphics/). Slower rendering than Chromium — [wry #890](https://github.com/tauri-apps/wry/issues/890). Pressure reported as 0 — [r/WebKit mirror](https://lr.eu.psf.lt/r/WebKit)
- **Flutter Linux**: pen detected as finger with no pressure — [saber #90](https://github.com/adil192/saber/issues/90). Fixed only via the third-party `stylet` plugin — [stylet](https://pub.dev/packages/stylet)
- **Xournal++**: still GTK 3 with no active GTK 4 port. That is a signal that porting a large pen app to GTK 4 is costly — [xournalpp #7212](https://github.com/xournalpp/xournalpp/discussions/7212)

### Inferences
- **Ubuntu 24.04 ships GTK 4.14** (training knowledge, not re-verified), i.e. the ngl-default era, before most Vulkan fixes. A GTK 4 app on 24.04 would likely run on the GL renderer. Newer GTK via Flatpak (GNOME runtime) would run newer renderers. Test both with `GSK_RENDERER=gl|ngl|vulkan`.
- **Qt on Wayland/AMD:** Qt Quick defaults to the OpenGL RHI backend on Linux (training knowledge). Mesa radeonsi on Strix Halo should be well supported, though no Strix-Halo-specific Qt report was found. Two knobs to try if rendering issues appear:
  - `QSG_RHI_BACKEND=vulkan` (or `opengl`)
  - `QT_QPA_PLATFORM=wayland`, which is the default on Wayland sessions in Qt 6 (training knowledge)
- **Fractional scaling:** Qt 6.5+ supports `wp_fractional_scale_v1` (training knowledge, not verified this session). Use the Qt 6.8+ (ideally 6.12 LTS) runtime, not Ubuntu's archive Qt, so the session-wide 125%/150% scale renders crisp.
- **Tablet input:** the pitfalls are mostly compositor/libinput/hardware-level, so they hit every toolkit. Validate the pen with `libinput debug-events` and a known-good app (Rnote or Krita) before blaming the toolkit.
- **Packaging pitfalls:**
  - Qt apps outside the distro: Qt runtime from pip (PySide6) or aqtinstall. For a personal app, a venv or a Flatpak with the KDE runtime are both workable.
  - GTK 4: a Flatpak with the GNOME runtime gives the newest GTK and libadwaita.
  - Tauri: .deb/AppImage bundling WebKitGTK 4.1 deps.
  - These are general training knowledge, not verified this session.
- **Licensing:**
  - Qt PDF is LGPLv3/GPLv2 (cited above). The rest of Qt essentials are LGPLv3 (training knowledge). For a single-user, open-source personal app, LGPL obligations are trivially met.
  - GTK is LGPL and Poppler is GPL (training knowledge).
  - Tauri is MIT/Apache-2.0 (training knowledge).
  - Slint is GPLv3, a royalty-free license for desktop, or commercial (training knowledge, not verified this session).

### Gaps
- No 2026-dated Qt Wayland tablet or touch bug reports were surveyed, so it is unknown whether Qt 6.10–6.12 has open regressions on mutter.
- No Strix Halo (RDNA 3.5 iGPU)-specific rendering issues were found for any stack.
- The current default GTK renderer in GTK 4.18/4.20 (likely what newer GNOME runtimes ship) was not confirmed. Training knowledge says GTK 4.16 made Vulkan the default on Wayland; not re-verified.
- Okular and Saber's documented reasons for choosing their stacks (Qt+Poppler and Flutter) were not fetched. Only Xournal++'s GTK 4 status and Rnote's dependency list were sourced.
- Slint and egui/iced Wayland input bugs: none found; their pen ecosystems appear too thin to be practical for this app, but that is an absence-of-evidence inference.
