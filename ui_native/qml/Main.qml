import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import "."

// Local Clova native UI over the existing API. The window holds the state and
// the recording/playback logic; the look comes from one of three layouts
// picked in Settings (PaperLayout, StudioLayout, ClassicLayout), all reading
// the same properties and calling the same functions here. Audio is captured
// by the host daemon, never by this app, so closing the window does not stop
// a recording.
ApplicationWindow {
    id: root

    required property var api
    property string initialSessionId: ""
    property string initialTheme: ""
    property string handFamily: ""      // set by __main__.py; "" if the font is missing

    visible: true
    title: session ? session.title + " — Local Clova" : "Local Clova"
    color: Theme.bg
    font.family: Theme.family

    property var library: ({ subjects: [], professors: [], sessions: [] })
    property string search: ""
    property string sessionId: ""
    property var session: null
    property var segments: []
    property var pdfs: []
    property string errorText: ""
    property bool sidebarOpen: true
    property string selectedSubject: ""     // classic theme's lecture list
    property bool subjectChosen: false

    // Playback: which segment is loaded and where to seek once it loads.
    property int playingIndex: -1
    property real pendingSeekMs: -1
    property bool continuePlayback: true
    property real playbackRate: 1
    readonly property bool audioRunning: player.playbackState === MediaPlayer.PlayingState
    readonly property real playerPositionSec: player.position / 1000
    readonly property bool hasAudio: segments.some(s => s.audio_available && !s.pending)
    readonly property real lectureEnd: {
        let end = 0
        for (const s of segments) end = Math.max(end, Number(s.end) || 0)
        return end || Number(session ? session.recording_time_sec : 0) || 0
    }
    readonly property real playheadSec: playingIndex >= 0 && segments[playingIndex]
        ? (Number(segments[playingIndex].start) || 0) + playerPositionSec : 0
    readonly property string rateText: (playbackRate % 1 === 0 ? playbackRate.toFixed(1) : String(playbackRate)) + "×"

    // Recording. The backend's session.recording is the truth; while it is
    // set, /api/recording/status is polled every 500 ms (as the web does) and
    // the transcript is refetched only when segment/pending counts change.
    readonly property bool recording: !!(session && session.recording)
    property var recStatus: null
    property bool statusBusy: false
    property int statusFailures: 0
    property bool segmentsBusy: false
    property var requestedKey: null     // counts a running refresh will cover
    property string renderedKey: ""     // counts the shown transcript covers
    property bool followLatest: true    // keep the newest sentence in view
    property bool actionBusy: false     // start/resume/stop/shutdown in flight
    property bool shuttingDown: false
    property bool blink: false          // recording dot, flipped per status poll
    property var levels: []             // input level (dBFS) per status poll, oldest first
    readonly property string liveText: recording && recStatus ? String(recStatus.unfixed_text || "").trim() : ""
    readonly property int pendingCount: segments.filter(s => s.pending).length
    readonly property real recordingSec: recording && recStatus ? Number(recStatus.recording_time_sec) || 0
        : (session ? Number(session.recording_time_sec) || 0 : 0)
    readonly property var recordingElsewhere: (library.sessions || []).find(s => s.recording && s.session_id !== sessionId) || null
    readonly property string captureWarning: {
        if (!recording) return ""
        if (statusFailures >= 6) return "녹음 상태를 받을 수 없습니다. 백엔드 연결을 확인하세요."
        if (!recStatus) return ""
        if (recStatus.capture_stalled)
            return "오디오 PCM이 " + Number(recStatus.capture_last_pcm_age_sec || 0).toFixed(1) + "초 이상 멈췄습니다. 녹음을 정지 후 재개하세요."
        if (!recStatus.capture_alive && Number(recStatus.capture_heartbeat_age_sec ?? 0) > 3)
            return "Native 오디오 capture heartbeat가 끊겼습니다. 녹음 상태를 확인하세요."
        return ""
    }
    readonly property string micText: captureWarning !== "" ? "마이크 확인 필요" : "마이크 정상"
    readonly property string levelText: levels.length ? String(Math.round(levels[levels.length - 1])).replace("-", "−") + " dB" : ""

    // Date line under the title: start time while recording, length after.
    readonly property string sessionMeta: {
        if (!session) return ""
        const parts = [longDate(session.created_at)]
        if (recording) parts.push(timeOfDay(session.created_at) + " 시작")
        else {
            parts.push(humanLength(session.recording_time_sec))
            const n = segments.length - pendingCount
            if (n) parts.push("문장 " + n + "개")
            if (session.manual_edit_count) parts.push("수정 " + session.manual_edit_count)
        }
        return parts.filter(x => x).join(" · ")
    }

    Settings {
        id: prefs
        category: "ui"
        property string theme: "paper"
        property string bodyFont: "auto"
    }

    Component.onCompleted: {
        // Themes before the redesign: notebook, dark, light.
        const legacy = { notebook: "paper", dark: "studio", light: "classic" }
        let mode = initialTheme || prefs.theme || "paper"
        mode = legacy[mode] || mode
        if (["paper", "studio", "classic"].indexOf(mode) < 0) mode = "paper"
        if (!initialTheme && prefs.theme !== mode) prefs.theme = mode
        Theme.handFamily = handFamily || Theme.family
        Theme.bodyFont = prefs.bodyFont === "hand" && !handFamily ? "auto" : (prefs.bodyFont || "auto")
        Theme.mode = mode
        api.fetchLibrary()
    }

    function setTheme(mode) {
        Theme.mode = mode
        prefs.theme = mode
        if (recording) Qt.callLater(followBottom)
    }
    function setBodyFont(kind) {
        Theme.bodyFont = kind
        prefs.bodyFont = kind
    }

    Connections {
        target: root.api
        function onLibraryLoaded(data) {
            root.errorText = ""
            root.library = data
            if (!root.subjectChosen) {
                const latest = (data.sessions || []).slice().sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0]
                root.selectedSubject = latest ? root.subjectKeyOf(latest) : ((data.subjects || [])[0] || {}).id || ""
            }
            if (root.initialSessionId && !root.sessionId) root.openSession(root.initialSessionId)
        }
        function onSegmentsLoaded(sid, data) {
            if (sid !== root.sessionId) return
            root.segmentsBusy = false
            if (root.requestedKey !== null) {
                root.renderedKey = root.requestedKey
                root.requestedKey = null
            }
            root.errorText = ""
            // A new array resets the list (and its scroll), so either follow
            // the newest sentence or put the reader back where they were.
            const refresh = root.session !== null
            const follow = root.followLatest
            const view = root.transcript()
            const keepY = view ? view.contentY : 0
            root.session = data
            root.segments = (data.segments || []).filter(s => !s.deleted)
            if (root.recording && (follow || !refresh)) Qt.callLater(root.followBottom)
            else if (!refresh) Qt.callLater(() => {
                const v = root.transcript()
                if (v) v.toTop()
            })
            else Qt.callLater(() => {
                const v = root.transcript()
                if (v) v.contentY = keepY
                root.followLatest = follow
            })
        }
        function onPdfsLoaded(sid, data) {
            if (sid === root.sessionId) root.pdfs = data.pdfs || []
        }
        function onRecordingStatusLoaded(sid, data) {
            root.statusBusy = false
            if (sid !== root.sessionId) return
            root.statusFailures = 0
            root.recStatus = data
            root.blink = !root.blink
            const db = Number(data.vad_input_rms_dbfs_1s)
            if (data.recording && data.vad_input_rms_dbfs_1s !== undefined && isFinite(db)) {
                const next = root.levels.concat([db])
                root.levels = next.length > 160 ? next.slice(next.length - 160) : next
            }
            if (!data.recording) {
                // Stopped elsewhere (web UI, backend restart): pick up the result.
                root.refreshSegments(null)
                root.api.fetchLibrary()
                return
            }
            const key = Number(data.segment_count || 0) + ":" + Number(data.pending_count || 0)
            if (key !== root.renderedKey && !root.segmentsBusy) root.refreshSegments(key)
        }
        function onRequestFailed(what, message) {
            if (what === "pdfs") return
            if (what === "status") {
                root.statusBusy = false
                root.statusFailures += 1
                return
            }
            if (what === "segments") root.segmentsBusy = false
            root.errorText = (what === "library" ? "백엔드에 연결할 수 없습니다 (" + root.api.baseUrl + "). " : "불러오지 못했습니다. ") + message
        }
        function onActionDone(action, sid, data) {
            root.actionBusy = false
            if (action === "start") {
                newSessionDialog.close()
                root.openSession(sid, {
                    session_id: sid,
                    title: data.title,
                    subject_id: data.subject_id || "",
                    created_at: new Date().toISOString(),
                    recording: true,
                    segments: [],
                    pending_count: 0,
                    recording_time_sec: 0,
                    manual_edit_count: 0
                })
                root.api.fetchLibrary()
                toast.show("녹음을 시작했습니다.")
            } else if (action === "resume") {
                if (sid === root.sessionId && root.session) {
                    root.beginMonitoring()
                    root.session = Object.assign({}, root.session, data, { recording: true })
                    root.followBottom()
                }
                root.api.fetchLibrary()
                toast.show(data.reconnected ? "녹음 연결을 복구했습니다." : "같은 세션에서 녹음을 재개했습니다.")
            } else if (action === "finish") {
                if (sid === root.sessionId && root.session) {
                    root.session = Object.assign({}, root.session, { recording: false, pending_count: Number(data.pending_count || 0) })
                    root.recStatus = null
                    root.refreshSegments(null)
                }
                root.api.fetchLibrary()
                toast.show(data.pending_count ? "녹음 종료 · " + data.pending_count + "개 구간 처리 중" : "녹음을 종료했습니다.")
            } else if (action === "subject") {
                subjectDialog.close()
                if (newSessionDialog.visible) newSessionDialog.subjectId = data.id || ""
                if (data.id) { root.selectedSubject = data.id; root.subjectChosen = true }
                root.api.fetchLibrary()
                toast.show((data.name || "새") + " 과목을 만들었습니다.")
            } else if (action === "shutdown") {
                if (!data.ok) {
                    toast.show("앱 종료 요청 실패: 종료 컨트롤러가 확인하지 않았습니다.")
                    return
                }
                shutdownDialog.close()
                player.stop()
                root.shuttingDown = true
                quitTimer.start()
            }
        }
        function onActionFailed(action, sid, message) {
            root.actionBusy = false
            const what = { start: "녹음 시작", resume: "녹음 재개", finish: "녹음 종료", subject: "과목 생성", shutdown: "앱 종료 요청" }[action] || action
            toast.show(what + " 실패: " + message)
            // A failed stop/resume can leave either state; ask the backend.
            if ((action === "finish" || action === "resume") && sid === root.sessionId) root.refreshSegments(null)
        }
    }

    Timer {
        interval: 500
        repeat: true
        running: root.recording && !root.shuttingDown
        onTriggered: {
            if (root.statusBusy) return
            root.statusBusy = true
            root.api.fetchRecordingStatus(root.sessionId)
        }
    }
    // After a stop the last sentences are still in Whisper; watch them land.
    Timer {
        interval: 1500
        repeat: true
        running: !root.recording && root.session !== null && root.pendingCount > 0 && !root.shuttingDown
        onTriggered: if (!root.segmentsBusy) root.refreshSegments(null)
    }
    Timer {
        id: quitTimer
        interval: 1600
        onTriggered: Qt.quit()
    }

    Shortcut { sequence: "Ctrl+N"; onActivated: root.openNewSession() }
    Shortcut { sequence: "Ctrl+."; onActivated: root.stopRecording() }
    Shortcut { sequence: "Ctrl+,"; onActivated: root.openSettings() }
    Shortcut { sequence: "End"; enabled: root.session !== null; onActivated: root.followBottom() }
    Shortcut { sequence: "F11"; onActivated: root.visibility === Window.FullScreen ? root.showNormal() : root.showFullScreen() }

    // ------------------------------------------------------------ helpers
    function transcript() {
        return workspace.item ? workspace.item.transcript : null
    }
    function subjectOf(id) {
        return (library.subjects || []).find(s => s.id === id) || null
    }
    function subjectKeyOf(s) {
        return subjectOf(s.subject_id) ? s.subject_id : ""
    }
    function subjectByKey(key) {
        return key ? subjectOf(key) : { id: "", name: "미분류", semester: "" }
    }
    function professorName(id) {
        const p = (library.professors || []).find(p => p.id === id)
        return p ? p.name : ""
    }
    function clock(sec) {
        sec = Math.max(0, Math.floor(Number(sec) || 0))
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60
        return h ? h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
                 : m + ":" + String(s).padStart(2, "0")
    }
    function shortDate(iso) {
        if (!iso) return ""
        const d = new Date(iso)
        return (d.getMonth() + 1) + "/" + d.getDate()
    }
    function monthDay(iso) {
        if (!iso) return ""
        const d = new Date(iso)
        return (d.getMonth() + 1) + "월 " + d.getDate() + "일"
    }
    function longDate(iso) {
        if (!iso) return ""
        const d = new Date(iso)
        return monthDay(iso) + " " + "일월화수목금토"[d.getDay()] + "요일"
    }
    function timeOfDay(iso) {
        if (!iso) return ""
        const d = new Date(iso)
        const h = d.getHours(), m = String(d.getMinutes()).padStart(2, "0")
        return (h < 12 ? "오전 " : "오후 ") + ((h + 11) % 12 + 1) + ":" + m
    }
    function humanLength(sec) {
        sec = Math.round(Number(sec) || 0)
        if (sec <= 0) return ""
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60)
        if (h) return h + "시간" + (m ? " " + m + "분" : "")
        return m ? m + "분" : sec + "초"
    }
    function notYet(what) {
        toast.show(what + "은(는) 다음 단계에서 연결됩니다. 지금은 웹 UI에서 사용하세요.")
    }
    function currentSemester() {
        const d = new Date()
        return d.getFullYear() + "-" + (d.getMonth() + 1 >= 7 ? 2 : 1)
    }
    // Korean collation as in the web (Chrome "ko"): Hangul before Latin.
    function koCompare(a, b) {
        const ha = /^[가-힣ㄱ-ㅎ]/.test(a), hb = /^[가-힣ㄱ-ㅎ]/.test(b)
        if (ha !== hb) return ha ? -1 : 1
        return String(a).localeCompare(String(b))
    }

    // New-session subject picker: newest semester first, then by name.
    readonly property var subjectOptions: [{ value: "", label: "미분류" }].concat(
        (library.subjects || []).slice()
            .sort((a, b) => String(b.semester || "").localeCompare(String(a.semester || "")) || koCompare(a.name, b.name))
            .map(x => ({ value: x.id, label: x.name + (x.semester ? " · " + x.semester : "") })))

    // ------------------------------------------------------------ library
    function lectureOf(s) {
        const tags = (s.tags || []).map(t => t.name)
        return {
            sessionId: s.session_id,
            title: s.title || s.session_id,
            created: s.created_at || "",
            recording: !!s.recording,
            date: shortDate(s.created_at),
            longDate: monthDay(s.created_at),
            length: s.recording ? "" : humanLength(s.recording_time_sec || s.duration_sec),
            detail: [s.segment_count ? "문장 " + s.segment_count + "개" : "", tags.slice(0, 2).join(" · ")].filter(x => x).join(" · "),
            haystack: (String(s.title || "") + " " + tags.join(" ")).toLowerCase()
        }
    }
    // subject id ("" = unclassified) -> lectures matching the search, newest first
    readonly property var lecturesBySubject: {
        const q = search.trim().toLowerCase()
        const out = {}
        for (const s of library.sessions || []) {
            const lecture = lectureOf(s)
            if (q && !lecture.haystack.includes(q)) continue
            const key = subjectKeyOf(s)
            ;(out[key] = out[key] || []).push(lecture)
        }
        for (const key of Object.keys(out)) out[key].sort((a, b) => b.created.localeCompare(a.created))
        return out
    }
    function lecturesOf(key) {
        return lecturesBySubject[key || ""] || []
    }
    // semester -> subjects, the same grouping as the web renderSidebar():
    // semesters newest first, subjects by name, unclassified last under "기타".
    function semesterGroups(makeSubject, keep) {
        const subjects = library.subjects || []
        const semesters = [...new Set(subjects.map(x => x.semester || "기타"))].sort().reverse()
        const groups = []
        for (const semester of semesters) {
            const list = subjects
                .filter(x => (x.semester || "기타") === semester)
                .sort((a, b) => koCompare(a.name, b.name))
                .map(x => makeSubject(x.id, x.name, x.professor_id))
                .filter(keep)
            if (list.length) groups.push({ semester: semester, subjects: list })
        }
        const loose = makeSubject("", "미분류", "")
        if (keep(loose) && loose.count) {
            if (groups.length && groups[groups.length - 1].semester === "기타") groups[groups.length - 1].subjects.push(loose)
            else groups.push({ semester: "기타", subjects: [loose] })
        }
        return groups
    }
    // Paper / studio tree (lectures filtered by the search).
    readonly property var libraryGroups: {
        const q = search.trim()
        const current = sessionId
        return semesterGroups((key, name, professorId) => {
            const sessions = lecturesBySubject[key] || []
            return { key: key, name: name, professor: professorName(professorId), sessions: sessions,
                     count: sessions.length, hasCurrent: sessions.some(l => l.sessionId === current) }
        }, g => !q || g.sessions.length)
    }
    // Classic subject pane (every subject, unfiltered counts).
    readonly property var subjectIndex: {
        const counts = {}
        for (const s of library.sessions || []) {
            const key = subjectKeyOf(s)
            counts[key] = (counts[key] || 0) + 1
        }
        return semesterGroups((key, name) => ({ key: key, name: name, count: counts[key] || 0 }), g => true)
    }

    // ------------------------------------------------------------ sessions
    // `initial` shows a just-started session before its first fetch returns.
    function openSession(sid, initial) {
        player.stop()
        playingIndex = -1
        pendingSeekMs = -1
        sessionId = sid
        session = initial || null
        segments = []
        pdfs = []
        const known = (library.sessions || []).find(s => s.session_id === sid)
        if (known || initial) {
            selectedSubject = known ? subjectKeyOf(known) : (subjectOf(initial.subject_id) ? initial.subject_id : "")
            subjectChosen = true
        }
        beginMonitoring()
        refreshSegments(null)
        api.fetchPdfs(sid)
    }

    function refreshSegments(key) {
        if (!sessionId) return
        segmentsBusy = true
        requestedKey = key
        api.fetchSegments(sessionId)
    }

    function retry() {
        errorText = ""
        if (sessionId) api.fetchSegments(sessionId)
        else api.fetchLibrary()
    }

    function beginMonitoring() {
        recStatus = null
        statusFailures = 0
        renderedKey = ""
        followLatest = true
        levels = []
    }

    function followBottom() {
        const view = transcript()
        if (view) view.positionViewAtEnd()
        followLatest = true
    }

    function openSettings() {
        if (!shuttingDown) settingsDialog.open()
    }
    function openSubjectDialog() {
        if (!shuttingDown) subjectDialog.openFresh()
    }
    function showInfo(anchor) {
        if (session) infoPopup.openAt(anchor)
    }

    // ------------------------------------------------------------ recording actions
    // One microphone: refuse a second recording while any session records.
    function blockedByOtherRecording() {
        if (!recordingElsewhere) return false
        toast.show("‘" + (recordingElsewhere.title || recordingElsewhere.session_id) + "’ 세션이 녹음 중입니다. 먼저 정지해주세요.")
        openSession(recordingElsewhere.session_id)
        return true
    }

    function openNewSession() {
        openNewSessionIn(session ? (session.subject_id || "") : "")
    }
    // subjectKey: the subject preselected in the dialog.
    function openNewSessionIn(subjectKey) {
        if (actionBusy || shuttingDown) return
        if (recording) { toast.show("현재 녹음을 먼저 정지해주세요."); return }
        if (blockedByOtherRecording()) return
        newSessionDialog.subjectId = subjectKey || ""
        newSessionDialog.open()
    }

    function startRecording(title, subjectId) {
        title = String(title || "").trim()
        if (!title || actionBusy) return
        actionBusy = true
        api.startRecording(title, subjectId || "")
    }

    function stopRecording() {
        if (!recording || actionBusy) return
        actionBusy = true
        api.finishRecording(sessionId)
    }

    function resumeRecording() {
        if (!session || recording || actionBusy) return
        if (blockedByOtherRecording()) return
        actionBusy = true
        api.resumeRecording(sessionId)
    }

    function resumeClicked() {
        if (pendingCount > 0) toast.show("마지막 문장 처리가 끝난 뒤 재개할 수 있습니다.")
        else resumeRecording()
    }

    function requestShutdown() {
        if (actionBusy || shuttingDown) return
        if (recording || recordingElsewhere) { toast.show("녹음을 먼저 정지해주세요."); return }
        shutdownDialog.open()
    }

    // ------------------------------------------------------------ playback
    function firstAudioIndex(from) {
        for (let i = Math.max(0, from); i < segments.length; i++)
            if (segments[i].audio_available && !segments[i].pending) return i
        return -1
    }

    function playAt(index, startSec) {
        const seg = segments[index]
        if (!seg || !seg.audio_available) return
        const url = api.url(seg.audio_url)
        playingIndex = index
        if (player.source.toString() !== url) {
            pendingSeekMs = Math.max(0, startSec * 1000)
            player.source = url
        } else {
            player.position = Math.max(0, startSec * 1000)
        }
        player.play()
        const view = transcript()
        if (view) {
            view.positionViewAtIndex(index, ListView.Contain)
            view.keepTop = view.atYBeginning
        }
    }

    function togglePlay(index) {
        if (playingIndex === index && audioRunning) player.pause()
        else if (playingIndex === index) player.play()
        else playAt(index, 0)
    }

    function togglePlayback() {
        if (audioRunning) player.pause()
        else if (playingIndex >= 0) player.play()
        else {
            const i = firstAudioIndex(0)
            if (i >= 0) playAt(i, 0)
        }
    }

    // Lecture time -> the segment holding it (or the next one with audio).
    function seekLecture(t) {
        t = Math.max(0, Math.min(lectureEnd, Number(t) || 0))
        let idx = -1
        for (let i = 0; i < segments.length; i++) {
            const s = segments[i]
            if (!s.audio_available || s.pending) continue
            idx = i
            if (Number(s.end) > t) break
        }
        if (idx < 0) return
        const s = segments[idx]
        const length = Math.max(0, (Number(s.end) || 0) - (Number(s.start) || 0))
        playAt(idx, Math.min(Math.max(0, t - (Number(s.start) || 0)), Math.max(0, length - 0.25)))
    }

    function skip(seconds) {
        seekLecture(playheadSec + seconds)
    }

    function cycleRate() {
        const rates = [1, 1.25, 1.5, 2, 0.75]
        playbackRate = rates[(rates.indexOf(playbackRate) + 1) % rates.length]
    }

    MediaPlayer {
        id: player
        objectName: "player"
        playbackRate: root.playbackRate
        audioOutput: AudioOutput { objectName: "audioOut" }
        // Qt 6.12's FFmpeg backend loads a new source asynchronously and, when
        // switching, first re-reports LoadedMedia for the *old* media. A seek
        // before the new media finishes loading is dropped, so the requested
        // start is applied on the first Loaded/Buffered after LoadingMedia.
        property bool loadingNewSource: false
        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.LoadingMedia) {
                loadingNewSource = true
            } else if (loadingNewSource && (mediaStatus === MediaPlayer.LoadedMedia || mediaStatus === MediaPlayer.BufferedMedia)) {
                loadingNewSource = false
                if (root.pendingSeekMs >= 0) {
                    position = root.pendingSeekMs
                    root.pendingSeekMs = -1
                }
            }
            if (mediaStatus === MediaPlayer.EndOfMedia && root.continuePlayback) {
                const next = root.firstAudioIndex(root.playingIndex + 1)
                if (next >= 0) root.playAt(next, 0)
            }
        }
        onErrorOccurred: (error, message) => root.errorText = "재생 오류: " + message
    }

    // ------------------------------------------------------------ layout
    Loader {
        id: workspace
        anchors.fill: parent
        sourceComponent: Theme.studio ? studioLayout : (Theme.classic ? classicLayout : paperLayout)
    }
    Component { id: paperLayout; PaperLayout { app: root } }
    Component { id: studioLayout; StudioLayout { app: root } }
    Component { id: classicLayout; ClassicLayout { app: root } }

    // ------------------------------------------------------------ dialogs
    ModalCard {
        id: newSessionDialog
        objectName: "newSessionDialog"
        property alias subjectId: subjectField.value
        title: "새 녹음"
        lead: "과목을 고르고 제목을 입력하면 바로 녹음을 시작합니다."
        onOpened: { titleField.text = ""; titleField.focusEditor() }

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            FormField {
                id: subjectField
                Layout.fillWidth: true
                label: "과목"
                options: root.subjectOptions
            }
            ActionButton {
                Layout.alignment: Qt.AlignBottom
                implicitHeight: 40
                icon: "plus"
                iconSize: 16
                accessibleName: "과목 추가"
                onClicked: subjectDialog.openFresh()
            }
        }
        FormField {
            id: titleField
            objectName: "sessionTitleField"
            Layout.fillWidth: true
            label: "강의 제목"
            placeholder: "예: 스레드 동기화"
            onAccepted: root.startRecording(text, newSessionDialog.subjectId)
        }
        ActionButton {
            Layout.fillWidth: true
            Layout.topMargin: 6
            fillWidth: true
            implicitHeight: 44
            variant: "primary"
            dotColor: Theme.pick(Theme.rec, "#0D0D0F", "#FFFFFF")
            text: root.actionBusy ? "녹음 시작 중…" : "녹음 시작"
            dimmed: root.actionBusy || titleField.text.trim() === ""
            onClicked: root.startRecording(titleField.text, newSessionDialog.subjectId)
        }
    }

    ModalCard {
        id: subjectDialog
        objectName: "subjectDialog"
        title: "과목 추가"
        cardWidth: 420
        function openFresh() {
            emojiField.text = "📘"
            nameField.text = ""
            semesterField.text = root.currentSemester()
            professorField.text = ""
            open()
        }
        function submit() {
            const name = nameField.text.trim()
            if (!name || root.actionBusy) return
            root.actionBusy = true
            root.api.createSubject(name, semesterField.text.trim(), emojiField.text.trim() || "📘", professorField.text.trim())
        }
        onOpened: nameField.focusEditor()

        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            FormField { id: nameField; objectName: "subjectNameField"; Layout.fillWidth: true; label: "과목명"; placeholder: "예: 운영체제"; onAccepted: subjectDialog.submit() }
            // Kept for the web UI, which shows it next to the subject.
            FormField { id: emojiField; Layout.preferredWidth: 76; label: "아이콘"; maximumLength: 8 }
        }
        FormField { id: semesterField; Layout.fillWidth: true; label: "학기"; placeholder: "예: 2026-2"; onAccepted: subjectDialog.submit() }
        FormField { id: professorField; Layout.fillWidth: true; label: "교수"; placeholder: "예: 김OO 교수"; onAccepted: subjectDialog.submit() }
        ActionButton {
            Layout.fillWidth: true
            Layout.topMargin: 6
            fillWidth: true
            implicitHeight: 44
            variant: "primary"
            text: "과목 추가"
            dimmed: root.actionBusy || nameField.text.trim() === ""
            onClicked: subjectDialog.submit()
        }
    }

    ModalCard {
        id: shutdownDialog
        objectName: "shutdownDialog"
        title: "앱 종료"
        lead: "Local Clova ASR/LoRA 런타임과 종료 컨트롤러를 모두 종료할까요? 녹음과 전사는 그대로 남습니다."
        cardWidth: 420
        RowLayout {
            Layout.fillWidth: true
            spacing: 8
            ActionButton {
                Layout.fillWidth: true
                fillWidth: true
                implicitHeight: 42
                text: "취소"
                onClicked: shutdownDialog.close()
            }
            ActionButton {
                Layout.fillWidth: true
                fillWidth: true
                implicitHeight: 42
                variant: "danger"
                icon: "power"
                iconSize: 15
                text: root.actionBusy ? "종료 요청 중…" : "종료"
                dimmed: root.actionBusy
                onClicked: {
                    root.actionBusy = true
                    root.api.shutdownApp()
                }
            }
        }
    }

    SettingsDialog {
        id: settingsDialog
        app: root
        handAvailable: root.handFamily !== ""
        onThemePicked: mode => root.setTheme(mode)
        onBodyFontPicked: kind => root.setBodyFont(kind)
    }

    // Session facts as a popover under the info button (paper, classic).
    Popup {
        id: infoPopup
        objectName: "infoPopup"
        parent: Overlay.overlay
        width: 300
        padding: 18
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        function openAt(anchor) {
            const p = anchor.mapToItem(Overlay.overlay, anchor.width, anchor.height + 6)
            x = p.x - width
            y = p.y
            open()
        }
        margins: 12     // Popup keeps itself this far inside the window

        background: Rectangle {
            radius: 12
            color: Theme.dialogBg
            border.color: Theme.dialogLine
        }
        contentItem: SessionInfo { app: root }
    }

    // After shutdown: a static card, nothing animated (the web's spinning
    // overlay kept the GPU busy), then the window closes.
    Rectangle {
        parent: Overlay.overlay
        anchors.fill: parent
        z: 900
        visible: root.shuttingDown
        color: Theme.bg
        MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons }
        ColumnLayout {
            anchors.centerIn: parent
            spacing: 0
            BrandMark { Layout.alignment: Qt.AlignHCenter; size: 44 }
            Label {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 20
                text: "Local Clova 종료 완료"
                color: Theme.heading
                font.family: Theme.titleFamily
                font.pixelSize: 22
                font.weight: Theme.paper ? 600 : 700
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 8
                text: "런타임을 종료했습니다. 이 창은 곧 닫힙니다."
                color: Theme.muted
                font.pixelSize: 14
            }
        }
    }

    // Toast (on the overlay, so it shows above an open dialog)
    Rectangle {
        id: toast
        objectName: "toast"
        property string message: ""
        function show(text) {
            message = text
            opacity = 1
            toastTimer.interval = Math.max(2600, text.length * 75)
            toastTimer.restart()
        }
        parent: Overlay.overlay
        z: 1000
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 96
        width: Math.min(toastLabel.implicitWidth + 36, root.width - 40)
        height: toastLabel.implicitHeight + 22
        radius: Theme.pick(22, 10, 14)
        opacity: 0
        visible: opacity > 0
        color: Theme.toastBg
        border.color: Theme.studio ? "#3A3A40" : "transparent"
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Label {
            id: toastLabel
            anchors.centerIn: parent
            width: Math.min(implicitWidth, root.width - 76)
            text: toast.message
            color: Theme.toastText
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        Timer { id: toastTimer; interval: 2600; onTriggered: toast.opacity = 0 }
    }
}
