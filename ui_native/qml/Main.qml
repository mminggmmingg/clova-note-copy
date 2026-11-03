import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtMultimedia
import "."

// Local Clova native UI over the existing API, styled after the web UI
// (web/app_v6.css), notebook theme by default. Sidebar (semester -> subject
// -> lecture) on the left; header, stats and transcript on the right; tap a
// word to play the lecture from that word. U2: start/stop/resume recording
// and watch it live. Audio is captured by the host daemon, never by this app,
// so closing the window does not stop a recording.
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

    // Playback: which segment is loaded and where to seek once it loads.
    property int playingIndex: -1
    property real pendingSeekMs: -1
    readonly property bool audioRunning: player.playbackState === MediaPlayer.PlayingState

    // Web: clamp(21px, 1.38vw, 25px) for notebook handwriting.
    readonly property real handSize: Math.max(21, Math.min(25, width * 0.0138))

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
    readonly property string liveText: recording && recStatus ? String(recStatus.unfixed_text || "").trim() : ""
    readonly property int pendingCount: segments.filter(s => s.pending).length
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

    Settings {
        id: prefs
        category: "ui"
        property string theme: "notebook"
    }

    Component.onCompleted: {
        Theme.mode = initialTheme || prefs.theme || "notebook"
        Theme.handFamily = handFamily || Theme.family
        api.fetchLibrary()
    }

    Connections {
        target: root.api
        function onLibraryLoaded(data) {
            root.errorText = ""
            root.library = data
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
            const keepY = transcript.contentY
            root.session = data
            root.segments = (data.segments || []).filter(s => !s.deleted)
            if (root.recording && (follow || !refresh)) Qt.callLater(root.followBottom)
            else if (refresh) Qt.callLater(() => { transcript.contentY = keepY; root.followLatest = follow })
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

    Shortcut {
        sequence: "Ctrl+N"
        onActivated: root.openNewSession()
    }

    // ------------------------------------------------------------ helpers
    function subjectOf(id) {
        return (library.subjects || []).find(s => s.id === id) || null
    }
    function professorName(id) {
        const p = (library.professors || []).find(p => p.id === id)
        return p ? p.name : ""
    }
    function shortDate(iso) {
        if (!iso) return ""
        const d = new Date(iso)
        return (d.getMonth() + 1) + "/" + d.getDate()
    }
    function clock(sec) {
        sec = Math.max(0, Math.floor(Number(sec) || 0))
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60
        return h ? h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
                 : m + ":" + String(s).padStart(2, "0")
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
            .map(x => ({ value: x.id, label: (x.emoji ? x.emoji + " " : "") + x.name + (x.semester ? " · " + x.semester : "") })))

    // semester -> subject -> lectures, same grouping as the web renderSidebar():
    // semesters newest first, subjects by name (empty ones too unless
    // searching), unclassified lectures last under "기타".
    readonly property var libraryGroups: {
        const q = search.trim().toLowerCase()
        const bySubject = {}
        for (const s of library.sessions || []) {
            const tags = (s.tags || []).map(t => t.name)
            if (q && !(String(s.title || "") + " " + tags.join(" ")).toLowerCase().includes(q)) continue
            const key = subjectOf(s.subject_id) ? s.subject_id : ""
            ;(bySubject[key] = bySubject[key] || []).push({
                sessionId: s.session_id,
                title: s.title || s.session_id,
                created: s.created_at || "",
                recording: !!s.recording,
                meta: [shortDate(s.created_at), tags.slice(0, 2).join(" · ")].filter(x => x).join(" · ")
            })
        }
        for (const key of Object.keys(bySubject))
            bySubject[key].sort((a, b) => b.created.localeCompare(a.created))

        const subjects = library.subjects || []
        const semesters = [...new Set(subjects.map(x => x.semester || "기타"))].sort().reverse()
        const groups = []
        for (const semester of semesters) {
            const list = subjects
                .filter(x => (x.semester || "기타") === semester)
                .sort((a, b) => koCompare(a.name, b.name))
                .map(x => ({
                    key: x.id,
                    emoji: x.emoji || "📘",
                    name: x.name,
                    professor: professorName(x.professor_id),
                    sessions: bySubject[x.id] || []
                }))
                .filter(g => !q || g.sessions.length)
            if (list.length) groups.push({ semester: semester, subjects: list })
        }
        const loose = bySubject[""] || []
        if (loose.length || !q)
            groups.push({ semester: "기타", subjects: [{ key: "", emoji: "◌", name: "미분류", professor: "", sessions: loose }] })
        return groups
    }

    // `initial` shows a just-started session before its first fetch returns.
    function openSession(sid, initial) {
        player.stop()
        playingIndex = -1
        pendingSeekMs = -1
        sessionId = sid
        session = initial || null
        segments = []
        pdfs = []
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

    function beginMonitoring() {
        recStatus = null
        statusFailures = 0
        renderedKey = ""
        followLatest = true
    }

    function followBottom() {
        transcript.positionViewAtEnd()
        followLatest = true
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
        if (actionBusy || shuttingDown) return
        if (recording) { toast.show("현재 녹음을 먼저 정지해주세요."); return }
        if (blockedByOtherRecording()) return
        newSessionDialog.subjectId = session ? (session.subject_id || "") : ""
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

    function requestShutdown() {
        if (actionBusy || shuttingDown) return
        if (recording || recordingElsewhere) { toast.show("녹음을 먼저 정지해주세요."); return }
        shutdownDialog.open()
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
        transcript.positionViewAtIndex(index, ListView.Contain)
    }

    function togglePlay(index) {
        if (playingIndex === index && audioRunning) player.pause()
        else if (playingIndex === index) player.play()
        else playAt(index, 0)
    }

    MediaPlayer {
        id: player
        objectName: "player"
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
            if (mediaStatus === MediaPlayer.EndOfMedia && continueToggle.checked && root.playingIndex + 1 < root.segments.length)
                root.playAt(root.playingIndex + 1, 0)
        }
        onErrorOccurred: (error, message) => root.errorText = "재생 오류: " + message
    }

    // Soft accent glow at the top (dark/light), like the web .app-shell.
    Shape {
        anchors.fill: parent
        visible: !Theme.notebook
        ShapePath {
            strokeWidth: -1
            fillGradient: RadialGradient {
                centerX: root.width * 0.46
                centerY: -root.height * 0.2
                centerRadius: Math.hypot(root.width, root.height) * 0.34
                focalX: centerX
                focalY: centerY
                GradientStop { position: 0; color: Theme.glow }
                GradientStop { position: 1; color: "transparent" }
            }
            PathLine { x: root.width; y: 0 }
            PathLine { x: root.width; y: root.height }
            PathLine { x: 0; y: root.height }
            PathLine { x: 0; y: 0 }
        }
    }

    SplitView {
        anchors.fill: parent
        handle: Item {
            implicitWidth: 5
            HoverHandler { cursorShape: Qt.SplitHCursor }
        }

        Sidebar {
            visible: root.sidebarOpen
            SplitView.preferredWidth: 292
            SplitView.minimumWidth: 220
            SplitView.maximumWidth: 430
            groups: root.libraryGroups
            currentSessionId: root.sessionId
            onSessionClicked: sid => root.openSession(sid)
            onSearchEdited: text => root.search = text
            onCollapseRequested: root.sidebarOpen = false
            onNewSessionRequested: root.openNewSession()
            onNewSubjectRequested: subjectDialog.openFresh()
            onQuitRequested: root.requestShutdown()
            onThemeCycled: { Theme.mode = Theme.next(); prefs.theme = Theme.mode }
        }

        // ------------------------------------------------------------ workspace
        Item {
            SplitView.fillWidth: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Header
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 84
                    color: Theme.header
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.headerLine }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: root.sidebarOpen ? 30 : 64
                        anchors.rightMargin: 26
                        spacing: 16

                        ColumnLayout {
                            spacing: 4
                            Layout.maximumWidth: 460
                            RowLayout {
                                spacing: 7
                                Rectangle {
                                    implicitWidth: pillText.implicitWidth + 14
                                    implicitHeight: 19
                                    radius: 9.5
                                    color: Theme.pillBg
                                    border.color: Theme.notebook ? Theme.ink(124, 96, 63, .13) : Theme.line
                                    Label {
                                        id: pillText
                                        anchors.centerIn: parent
                                        text: {
                                            const s = root.session ? root.subjectOf(root.session.subject_id) : null
                                            return s ? (s.emoji ? s.emoji + " " : "") + s.name : "미분류"
                                        }
                                        color: Theme.pillText
                                        font.pointSize: Theme.pt(8.5)
                                        font.weight: 750
                                        font.letterSpacing: 0.3
                                    }
                                }
                                Rectangle {
                                    implicitWidth: badgeText.implicitWidth + 14
                                    implicitHeight: 19
                                    radius: 9.5
                                    color: Theme.greenSoft
                                    border.color: Theme.greenLine
                                    Label {
                                        id: badgeText
                                        anchors.centerIn: parent
                                        text: "Whisper Large-v3"
                                        color: Theme.greenText
                                        font.pointSize: Theme.pt(8.5)
                                        font.weight: 750
                                        font.letterSpacing: 0.3
                                    }
                                }
                                // Recording badge (web .recording-badge): elapsed
                                // capture time; "CAPTURE ERROR" with a red rim on a stall.
                                Rectangle {
                                    id: recBadge
                                    readonly property bool failing: root.captureWarning !== ""
                                    visible: root.recording
                                    implicitWidth: recRow.implicitWidth + 14
                                    implicitHeight: 19
                                    radius: 9.5
                                    color: Theme.pick(Theme.ink(255, 109, 117, .11), Theme.ink(255, 109, 117, .10), "#f7dfdf")
                                    border.color: failing ? Theme.red : Theme.ink(255, 109, 117, .13)
                                    Row {
                                        id: recRow
                                        anchors.centerIn: parent
                                        spacing: 5
                                        Rectangle {
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 6
                                            height: 6
                                            radius: 3
                                            color: Theme.red
                                            // Flips with each status poll instead of animating.
                                            opacity: root.blink || recBadge.failing ? 1 : 0.35
                                        }
                                        Label {
                                            text: recBadge.failing ? "CAPTURE ERROR"
                                                : "녹음 중 " + root.clock(root.recStatus ? root.recStatus.recording_time_sec : root.session ? root.session.recording_time_sec : 0)
                                            color: Theme.pick("#ff8d93", "#c2414b", "#a35f5f")
                                            font.pointSize: Theme.pt(8.5)
                                            font.weight: 750
                                            font.letterSpacing: 0.3
                                            font.features: { "tnum": 1 }
                                        }
                                    }
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                text: root.session ? root.session.title : "오늘의 수업을 기록해보세요"
                                color: Theme.heading
                                font.pixelSize: 17
                                font.weight: 690
                                font.letterSpacing: -0.34
                                elide: Text.ElideRight
                            }
                        }

                        // PDF shelf: the session's PDFs and an "add" tile.
                        Row {
                            visible: root.session !== null
                            spacing: 8
                            Repeater {
                                model: root.pdfs
                                delegate: Item {
                                    id: tile
                                    required property var modelData
                                    width: 54
                                    height: 62
                                    Rectangle {
                                        anchors.fill: parent
                                        anchors.topMargin: 2
                                        anchors.bottomMargin: -2
                                        radius: 10
                                        color: Theme.ink(151, 116, 66, .12)
                                        visible: Theme.notebook
                                    }
                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 10
                                        color: Theme.notebook ? Theme.pdfTile : Theme.accentSoft
                                        border.color: Theme.notebook ? Theme.pdfTileBorder : Theme.line
                                    }
                                    Rectangle {
                                        id: doc
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        y: 4
                                        width: 30
                                        height: 36
                                        radius: 4
                                        color: "#ffffff"
                                        border.color: Theme.pdfRed
                                        Rectangle {
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.margins: 1
                                            height: 11
                                            color: Theme.pdfRed
                                            Label {
                                                anchors.centerIn: parent
                                                text: "PDF"
                                                color: "white"
                                                font.pixelSize: 7
                                                font.weight: 800
                                            }
                                        }
                                    }
                                    Label {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        anchors.bottom: parent.bottom
                                        anchors.bottomMargin: 4
                                        width: parent.width - 4
                                        horizontalAlignment: Text.AlignHCenter
                                        text: tile.modelData.original_filename || "PDF"
                                        color: Theme.notebook ? "#5b4e41" : Theme.muted
                                        font.pointSize: Theme.pt(7.5)
                                        font.weight: 700
                                        elide: Text.ElideRight
                                    }
                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: root.notYet("PDF 보기와 필기") }
                                }
                            }
                            Item {
                                width: 54
                                height: 62
                                Shape {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    y: 4
                                    width: 36
                                    height: 36
                                    ShapePath {
                                        strokeColor: Theme.notebook ? Theme.ink(110, 130, 230, .6) : Theme.muted2
                                        strokeWidth: 1
                                        strokeStyle: ShapePath.DashLine
                                        dashPattern: [3, 2]
                                        fillColor: "transparent"
                                        startX: 4; startY: 0
                                        PathLine { x: 32; y: 0 }
                                        PathArc { x: 36; y: 4; radiusX: 4; radiusY: 4 }
                                        PathLine { x: 36; y: 32 }
                                        PathArc { x: 32; y: 36; radiusX: 4; radiusY: 4 }
                                        PathLine { x: 4; y: 36 }
                                        PathArc { x: 0; y: 32; radiusX: 4; radiusY: 4 }
                                        PathLine { x: 0; y: 4 }
                                        PathArc { x: 4; y: 0; radiusX: 4; radiusY: 4 }
                                    }
                                    Icon {
                                        anchors.centerIn: parent
                                        name: "plus"
                                        width: 16
                                        height: 16
                                        color: Theme.notebook ? "#6e82e6" : Theme.muted
                                    }
                                }
                                Label {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 4
                                    text: "추가"
                                    color: Theme.muted2
                                    font.pointSize: Theme.pt(7.5)
                                }
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: root.notYet("PDF 추가") }
                            }
                        }

                        Item { Layout.fillWidth: true }

                        // Actions: 정지 while recording, 재개 otherwise (as the web).
                        PaperButton {
                            visible: root.session === null || root.recording
                            icon: "stop"
                            iconSize: 9
                            text: root.recording && root.actionBusy ? "정지 중…" : "정지"
                            variant: root.recording ? "red" : "default"
                            dimmed: !root.recording || root.actionBusy
                            onClicked: root.stopRecording()
                        }
                        PaperButton {
                            visible: root.session !== null && !root.recording
                            icon: "play"
                            iconSize: 12
                            text: root.actionBusy ? "재개 중…" : "재개"
                            variant: "green"
                            tilt: 0.12
                            dimmed: root.actionBusy || root.pendingCount > 0
                            onClicked: root.pendingCount > 0 ? toast.show("마지막 문장 처리가 끝난 뒤 재개할 수 있습니다.") : root.resumeRecording()
                        }
                        PaperButton {
                            visible: root.session !== null && root.segments.length > 0
                            icon: root.audioRunning ? "pause" : "play-all"
                            iconSize: 13
                            text: root.audioRunning ? "일시정지" : (root.playingIndex >= 0 ? "계속 재생" : "전체 재생")
                            variant: "orange"
                            tilt: -0.12
                            onClicked: {
                                if (root.audioRunning) player.pause()
                                else if (root.playingIndex >= 0) player.play()
                                else { continueToggle.checked = true; root.playAt(0, 0) }
                            }
                        }
                        PaperButton {
                            icon: "info"
                            iconSize: 17
                            onClicked: root.notYet("세션 정보 패널")
                        }
                    }
                }

                // Capture warning while recording (stall, lost heartbeat, no status).
                Rectangle {
                    Layout.fillWidth: true
                    visible: root.captureWarning !== ""
                    implicitHeight: captureLabel.implicitHeight + 18
                    color: Theme.pick(Theme.ink(255, 109, 117, .10), Theme.ink(255, 109, 117, .08), "#f7e2df")
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.ink(255, 109, 117, .22) }
                    Label {
                        id: captureLabel
                        anchors.verticalCenter: parent.verticalCenter
                        x: 30
                        width: parent.width - 56
                        text: root.captureWarning
                        color: Theme.pick("#ff8d93", "#b3343e", "#9c4f4f")
                        font.pixelSize: 12
                        font.weight: 650
                        wrapMode: Text.Wrap
                    }
                }

                // Error banner
                Rectangle {
                    Layout.fillWidth: true
                    visible: root.errorText !== ""
                    implicitHeight: errorRow.implicitHeight + 18
                    color: Theme.warnSoft
                    RowLayout {
                        id: errorRow
                        anchors.fill: parent
                        anchors.leftMargin: 30
                        anchors.rightMargin: 26
                        Label {
                            Layout.fillWidth: true
                            text: root.errorText
                            color: Theme.warnText
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }
                        Label {
                            text: "다시 시도"
                            color: Theme.warnText
                            font.pixelSize: 11
                            font.weight: 700
                            TapHandler {
                                onTapped: {
                                    root.errorText = ""
                                    if (root.sessionId) root.api.fetchSegments(root.sessionId)
                                    else root.api.fetchLibrary()
                                }
                            }
                        }
                    }
                }

                EmptyState {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.sessionId === ""
                    onNewSessionRequested: root.openNewSession()
                }

                Label {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.sessionId !== "" && root.session === null && root.errorText === ""
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    text: "불러오는 중…"
                    color: Theme.muted
                    font.pixelSize: 12
                }

                // Transcript
                ListView {
                    id: transcript
                    objectName: "transcript"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: root.session !== null
                    clip: true
                    spacing: 0
                    readonly property real columnWidth: Math.min(Theme.notebook ? 1040 : 900, width - 68)
                    leftMargin: (width - columnWidth) / 2
                    rightMargin: leftMargin
                    topMargin: 22
                    bottomMargin: 110
                    model: root.segments
                    boundsBehavior: Flickable.StopAtBounds

                    header: Item {
                        width: transcript.columnWidth
                        height: root.segments.length || !root.session ? 52 : 52 + emptyHint.implicitHeight + 24
                        Label {
                            y: 17
                            text: root.session
                                ? (root.segments.length - root.pendingCount) + " sentences · "
                                  + root.clock(root.recording && root.recStatus ? root.recStatus.recording_time_sec : root.session.recording_time_sec)
                                  + " audio · " + (root.session.manual_edit_count || 0) + " manual edits"
                                  + (root.pendingCount ? " · " + root.pendingCount + " processing" : "")
                                : ""
                            color: Theme.stats
                            font.pixelSize: 10
                        }
                        Column {
                            id: emptyHint
                            visible: root.session !== null && root.segments.length === 0
                            y: 52
                            width: parent.width
                            spacing: 6
                            Label {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "아직 확정된 문장이 없습니다."
                                color: Theme.text
                                font.pixelSize: 13
                                font.weight: 700
                            }
                            Label {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: root.recording ? "말하기 시작하면 문장 단위로 여기에 쌓입니다." : "녹음된 문장이 없는 세션입니다."
                                color: Theme.muted
                                font.pixelSize: 11
                            }
                        }
                    }

                    footer: LiveCard {
                        width: transcript.columnWidth
                        visible: root.liveText !== ""
                        height: visible ? implicitHeight : 0
                        text: root.liveText
                        handSize: root.handSize
                        onHeightChanged: if (root.recording && root.followLatest) Qt.callLater(root.followBottom)
                    }

                    // Scrolling up while recording stops following the newest
                    // sentence; scrolling back to the end resumes it.
                    onMovementEnded: root.followLatest = atYEnd

                    delegate: TranscriptRow {
                        required property var modelData
                        required property int index
                        width: transcript.columnWidth
                        seg: modelData
                        playing: root.playingIndex === index
                        audioRunning: root.audioRunning
                        positionSec: playing ? player.position / 1000 : 0
                        handSize: root.handSize
                        onWordTapped: startSec => root.playAt(index, startSec)
                        onPlayToggled: root.togglePlay(index)
                    }

                    ScrollBar.vertical: ScrollBar {
                        onPressedChanged: if (!pressed) root.followLatest = transcript.atYEnd
                        contentItem: Rectangle {
                            implicitWidth: 6
                            radius: 3
                            color: Theme.pick("#232a33", Theme.ink(24, 36, 54, .18), Theme.ink(102, 84, 65, .30))
                        }
                    }
                }
            }

            // Fade the transcript out under the floating bar.
            Rectangle {
                visible: root.session !== null
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.rightMargin: 10
                height: 96
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.alpha(Theme.bg, 0) }
                    GradientStop { position: 0.55; color: Qt.alpha(Theme.bg, 0.85) }
                    GradientStop { position: 1; color: Theme.bg }
                }
            }

            // Floating now-playing bar.
            Item {
                id: playerBar
                visible: root.playingIndex >= 0
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 22
                implicitWidth: barRow.implicitWidth + 20
                implicitHeight: 44

                Rectangle {
                    visible: Theme.notebook
                    anchors.fill: parent
                    anchors.topMargin: 6
                    anchors.bottomMargin: -8
                    anchors.leftMargin: 3
                    anchors.rightMargin: 3
                    radius: 16
                    color: Theme.ink(91, 73, 52, .10)
                }
                Rectangle {
                    anchors.fill: parent
                    radius: 14
                    color: Theme.pick("#141920", "#ffffff", "#fcf8ef")
                    border.color: Theme.notebook ? Theme.ink(112, 91, 67, .14) : Theme.lineStrong
                }

                RowLayout {
                    id: barRow
                    anchors.centerIn: parent
                    spacing: 12

                    Rectangle {
                        width: 30
                        height: 30
                        radius: 9
                        color: Theme.accentSoft
                        Icon {
                            anchors.centerIn: parent
                            width: 14
                            height: 14
                            name: root.audioRunning ? "pause" : "play"
                            color: Theme.accent
                        }
                        TapHandler { onTapped: root.audioRunning ? player.pause() : player.play() }
                    }
                    Label {
                        text: root.playingIndex >= 0 && root.segments[root.playingIndex]
                            ? "SEG " + String(root.segments[root.playingIndex].segment).padStart(3, "0")
                            : ""
                        color: Theme.segIndex
                        font.pixelSize: 9
                        font.weight: 750
                        font.letterSpacing: 0.6
                    }
                    Label {
                        text: root.clock(player.position / 1000) + " / " + root.clock(player.duration / 1000)
                        color: Theme.muted
                        font.pixelSize: 11
                        font.features: { "tnum": 1 }
                    }
                    Rectangle { width: 1; height: 18; color: Theme.line }
                    Label {
                        id: continueToggle
                        property bool checked: true
                        text: checked ? "이어 재생 켜짐" : "이어 재생 꺼짐"
                        color: checked ? Theme.accent : Theme.muted2
                        font.pointSize: Theme.pt(10.5)
                        font.weight: 650
                        TapHandler { onTapped: continueToggle.checked = !continueToggle.checked }
                    }
                }
            }

            // Fullscreen toggle (bottom-right), like the web's floating paper tab.
            PaperButton {
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.rightMargin: 22
                anchors.bottomMargin: 16
                implicitWidth: 46
                implicitHeight: 46
                radius: 13
                tilt: 0.45
                icon: "expand"
                iconSize: 19
                onClicked: root.visibility === Window.FullScreen ? root.showNormal() : root.showFullScreen()
            }
        }
    }

    // Reopen tab when the sidebar is collapsed.
    PaperButton {
        visible: !root.sidebarOpen
        x: 14
        y: 24
        icon: "chevron-left"
        rotation: 180
        iconSize: 16
        onClicked: root.sidebarOpen = true
    }

    // ------------------------------------------------------------ dialogs
    PaperDialog {
        id: newSessionDialog
        objectName: "newSessionDialog"
        property alias subjectId: subjectField.value
        kicker: "NEW RECORDING"
        title: "새 세션"
        lead: "과목을 고르고 제목을 입력하면 바로 녹음을 시작합니다."
        onOpened: { titleField.text = ""; titleField.focusEditor() }

        RowLayout {
            Layout.fillWidth: true
            spacing: 9
            PaperField {
                id: subjectField
                Layout.fillWidth: true
                label: "과목"
                options: root.subjectOptions
            }
            PaperButton {
                Layout.alignment: Qt.AlignBottom
                implicitWidth: 41
                implicitHeight: 41
                radius: 10
                icon: "plus"
                iconSize: 13
                onClicked: subjectDialog.openFresh()
            }
        }
        PaperField {
            id: titleField
            objectName: "sessionTitleField"
            Layout.fillWidth: true
            label: "세션 제목"
            placeholder: "예: Coordinate Frame과 Relative Pose"
            onAccepted: root.startRecording(text, newSessionDialog.subjectId)
        }
        PaperButton {
            Layout.fillWidth: true
            Layout.topMargin: 5
            fillWidth: true
            implicitHeight: 43
            radius: 10
            variant: "primary"
            tape: true
            dotColor: Theme.red
            fontPx: 10.5
            text: root.actionBusy ? "녹음 시작 중…" : "녹음 시작"
            dimmed: root.actionBusy || titleField.text.trim() === ""
            onClicked: root.startRecording(titleField.text, newSessionDialog.subjectId)
        }
    }

    PaperDialog {
        id: subjectDialog
        objectName: "subjectDialog"
        kicker: "NEW SUBJECT"
        title: "과목 만들기"
        cardWidth: 410
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
            spacing: 9
            PaperField { id: emojiField; Layout.preferredWidth: 78; label: "아이콘"; maximumLength: 8 }
            PaperField { id: nameField; objectName: "subjectNameField"; Layout.fillWidth: true; label: "과목명"; placeholder: "예: 로보틱스"; onAccepted: subjectDialog.submit() }
        }
        PaperField { id: semesterField; Layout.fillWidth: true; label: "학기"; placeholder: "예: 2026-2"; onAccepted: subjectDialog.submit() }
        PaperField { id: professorField; Layout.fillWidth: true; label: "교수"; placeholder: "예: 김OO 교수"; onAccepted: subjectDialog.submit() }
        PaperButton {
            Layout.fillWidth: true
            Layout.topMargin: 5
            fillWidth: true
            implicitHeight: 43
            radius: 10
            variant: "primary"
            fontPx: 10.5
            text: "과목 추가"
            dimmed: root.actionBusy || nameField.text.trim() === ""
            onClicked: subjectDialog.submit()
        }
    }

    PaperDialog {
        id: shutdownDialog
        objectName: "shutdownDialog"
        kicker: "SHUT DOWN"
        title: "앱 종료"
        lead: "Local Clova ASR/LoRA 런타임과 종료 컨트롤러를 모두 종료할까요? 녹음과 전사는 그대로 남습니다."
        cardWidth: 410
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 4
            spacing: 9
            PaperButton {
                Layout.fillWidth: true
                fillWidth: true
                implicitHeight: 43
                radius: 10
                fontPx: 10.5
                text: "취소"
                onClicked: shutdownDialog.close()
            }
            PaperButton {
                Layout.fillWidth: true
                fillWidth: true
                implicitHeight: 43
                radius: 10
                fontPx: 10.5
                variant: "red"
                icon: "power"
                text: root.actionBusy ? "종료 요청 중…" : "종료"
                dimmed: root.actionBusy
                onClicked: {
                    root.actionBusy = true
                    root.api.shutdownApp()
                }
            }
        }
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
        Column {
            anchors.centerIn: parent
            spacing: 0
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 56
                height: 56
                radius: 18
                color: Theme.notebook ? Theme.paperTop : Theme.accentSoft
                border.color: Theme.notebook ? Theme.paperBorder : Theme.line
                Icon { anchors.centerIn: parent; width: 22; height: 22; name: "power"; color: Theme.notebook ? Theme.paperText : Theme.accent }
            }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                topPadding: 19
                text: "Local Clova 종료 완료"
                color: Theme.heading
                font.pixelSize: 18
                font.weight: 700
            }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                topPadding: 8
                text: "런타임을 종료했습니다. 이 창은 곧 닫힙니다."
                color: Theme.muted
                font.pointSize: Theme.pt(11)
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
        anchors.bottomMargin: 84
        width: Math.min(toastLabel.implicitWidth + 32, root.width - 40)
        height: toastLabel.implicitHeight + 20
        radius: 12
        opacity: 0
        visible: opacity > 0
        color: Theme.pick("#141920", "#ffffff", "#fcf8ef")
        border.color: Theme.notebook ? Theme.ink(112, 91, 67, .14) : Theme.lineStrong
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Label {
            id: toastLabel
            anchors.centerIn: parent
            width: Math.min(implicitWidth, root.width - 72)
            text: toast.message
            color: Theme.text
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        Timer { id: toastTimer; interval: 2600; onTriggered: toast.opacity = 0 }
    }
}
