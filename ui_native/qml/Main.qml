import QtCore
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtMultimedia
import "."

// Local Clova native UI, step U1: read-only browsing over the existing API,
// styled after the web UI (web/app_v6.css), notebook theme by default.
// Sidebar (semester -> subject -> lecture) on the left; header, stats and
// transcript on the right; tap a word to play the lecture from that word.
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
            root.session = data
            root.segments = (data.segments || []).filter(s => !s.deleted)
        }
        function onPdfsLoaded(sid, data) {
            if (sid === root.sessionId) root.pdfs = data.pdfs || []
        }
        function onRequestFailed(what, message) {
            if (what === "pdfs") return
            root.errorText = (what === "library" ? "백엔드에 연결할 수 없습니다 (" + root.api.baseUrl + "). " : "불러오지 못했습니다. ") + message
        }
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

    // Korean collation as in the web (Chrome "ko"): Hangul before Latin.
    function koCompare(a, b) {
        const ha = /^[가-힣ㄱ-ㅎ]/.test(a), hb = /^[가-힣ㄱ-ㅎ]/.test(b)
        if (ha !== hb) return ha ? -1 : 1
        return String(a).localeCompare(String(b))
    }

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

    function openSession(sid) {
        player.stop()
        playingIndex = -1
        pendingSeekMs = -1
        sessionId = sid
        session = null
        segments = []
        pdfs = []
        api.fetchSegments(sid)
        api.fetchPdfs(sid)
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
            onNewSessionRequested: root.notYet("새 세션 녹음")
            onNewSubjectRequested: root.notYet("과목 만들기")
            onQuitRequested: root.notYet("앱 종료(녹음 스택 정지)")
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

                        // Actions
                        PaperButton {
                            visible: root.session === null
                            icon: "stop"
                            iconSize: 9
                            text: "정지"
                            dimmed: true
                        }
                        PaperButton {
                            visible: root.session !== null
                            icon: "play"
                            iconSize: 12
                            text: "재개"
                            variant: "green"
                            tilt: 0.12
                            onClicked: root.notYet("녹음 재개")
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
                    onNewSessionRequested: root.notYet("새 세션 녹음")
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
                        height: 52
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.verticalCenterOffset: -9
                            text: root.session
                                ? root.segments.length + " sentences · " + root.clock(root.session.recording_time_sec)
                                  + " audio · " + (root.session.manual_edit_count || 0) + " manual edits"
                                : ""
                            color: Theme.stats
                            font.pixelSize: 10
                        }
                    }

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

    // Toast
    Rectangle {
        id: toast
        property string message: ""
        function show(text) { message = text; opacity = 1; toastTimer.restart() }
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
