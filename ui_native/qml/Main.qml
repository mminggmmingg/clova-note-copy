import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtMultimedia
import "."

// Local Clova native UI, step U1: read-only browsing over the existing API,
// styled after the web UI (web/app_v6.css). Sidebar (semester -> subject ->
// lecture) on the left; header, stats and transcript on the right; tap a
// word to play the lecture from that word.
ApplicationWindow {
    id: root

    required property var api
    property string initialSessionId: ""
    property string initialTheme: ""

    visible: true
    title: session ? session.title + " — Local Clova" : "Local Clova"
    color: Theme.bg
    font.family: Theme.family

    property var library: ({ subjects: [], professors: [], sessions: [] })
    property string search: ""
    property string sessionId: ""
    property var session: null
    property var segments: []
    property string errorText: ""

    // Playback: which segment is loaded and where to seek once it loads.
    property int playingIndex: -1
    property real pendingSeekMs: -1
    readonly property bool audioRunning: player.playbackState === MediaPlayer.PlayingState

    Component.onCompleted: {
        if (initialTheme) Theme.override = initialTheme
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
        function onRequestFailed(what, message) {
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

    // semester -> subject -> lectures, filtered by the search box.
    readonly property var libraryGroups: {
        const q = search.trim().toLowerCase()
        const bySubject = {}
        for (const s of library.sessions || []) {
            const tags = (s.tags || []).map(t => t.name)
            if (q && !(String(s.title || "") + " " + tags.join(" ")).toLowerCase().includes(q)) continue
            const key = s.subject_id || "none"
            ;(bySubject[key] = bySubject[key] || []).push({
                sessionId: s.session_id,
                title: s.title || s.session_id,
                created: s.created_at || "",
                recording: !!s.recording,
                meta: [shortDate(s.created_at), tags.slice(0, 2).join(" · ")].filter(x => x).join(" · ")
            })
        }
        const semesters = {}
        for (const key of Object.keys(bySubject)) {
            const subj = subjectOf(key)
            const sessions = bySubject[key].sort((a, b) => b.created.localeCompare(a.created))
            const semester = subj ? (subj.semester || "학기 미지정") : "미분류"
            ;(semesters[semester] = semesters[semester] || []).push({
                key: key,
                emoji: subj ? (subj.emoji || "📘") : "◌",
                name: subj ? subj.name : "미분류",
                professor: subj ? professorName(subj.professor_id) : "",
                sessions: sessions
            })
        }
        return Object.keys(semesters)
            .sort((a, b) => (a === "미분류") - (b === "미분류") || b.localeCompare(a))
            .map(sem => ({ semester: sem, subjects: semesters[sem].sort((a, b) => a.name.localeCompare(b.name, "ko")) }))
    }

    function openSession(sid) {
        player.stop()
        playingIndex = -1
        pendingSeekMs = -1
        sessionId = sid
        session = null
        segments = []
        api.fetchSegments(sid)
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

    // Soft accent glow at the top, like the web .app-shell background.
    Shape {
        anchors.fill: parent
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
            SplitView.preferredWidth: 292
            SplitView.minimumWidth: 200
            SplitView.maximumWidth: 430
            groups: root.libraryGroups
            currentSessionId: root.sessionId
            onSessionClicked: sid => root.openSession(sid)
            onSearchEdited: text => root.search = text
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
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.line }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 30
                        anchors.rightMargin: 26
                        spacing: 20

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            RowLayout {
                                spacing: 7
                                visible: root.session !== null
                                Rectangle {
                                    implicitWidth: pillText.implicitWidth + 14
                                    implicitHeight: 19
                                    radius: 9.5
                                    color: Theme.pillBg
                                    border.color: Theme.line
                                    Label {
                                        id: pillText
                                        anchors.centerIn: parent
                                        text: {
                                            const s = root.session ? root.subjectOf(root.session.subject_id) : null
                                            return s ? (s.emoji ? s.emoji + " " : "") + s.name : "미분류"
                                        }
                                        color: Theme.pillText
                                        font.pointSize: 6.375
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
                                        font.pointSize: 6.375
                                        font.weight: 750
                                        font.letterSpacing: 0.3
                                    }
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                text: root.session ? root.session.title : "오늘의 수업을 기록해보세요"
                                color: Theme.text
                                font.pixelSize: 17
                                font.weight: 690
                                font.letterSpacing: -0.34
                                elide: Text.ElideRight
                            }
                        }

                        // "전체 재생" control button
                        Rectangle {
                            visible: root.session !== null && root.segments.length > 0
                            implicitWidth: playAllRow.implicitWidth + 24
                            implicitHeight: 36
                            radius: 9
                            color: playAllHover.hovered ? Theme.ink(243, 185, 95, Theme.dark ? .16 : .22) : Theme.ink(243, 185, 95, Theme.dark ? .10 : .16)
                            border.color: Theme.ink(243, 185, 95, Theme.dark ? .24 : .45)
                            RowLayout {
                                id: playAllRow
                                anchors.centerIn: parent
                                spacing: 7
                                Icon { name: root.audioRunning ? "pause" : "play-all"; color: Theme.dark ? "#f3c98a" : "#9a5b12"; width: 14; height: 14 }
                                Label {
                                    text: root.audioRunning ? "일시정지" : (root.playingIndex >= 0 ? "계속 재생" : "전체 재생")
                                    color: Theme.dark ? "#f3c98a" : "#9a5b12"
                                    font.pointSize: 7.875
                                    font.weight: 650
                                }
                            }
                            HoverHandler { id: playAllHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler {
                                onTapped: {
                                    if (root.audioRunning) player.pause()
                                    else if (root.playingIndex >= 0) player.play()
                                    else { continueToggle.checked = true; root.playAt(0, 0) }
                                }
                            }
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
                    readonly property real columnWidth: Math.min(900, width - 68)
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
                        onWordTapped: startSec => root.playAt(index, startSec)
                        onPlayToggled: root.togglePlay(index)
                    }

                    ScrollBar.vertical: ScrollBar {
                        contentItem: Rectangle {
                            implicitWidth: 6
                            radius: 3
                            color: Theme.dark ? "#232a33" : Theme.ink(24, 36, 54, .18)
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
                    GradientStop { position: 0; color: Theme.ink(0, 0, 0, 0) }
                    GradientStop { position: 0.55; color: Qt.alpha(Theme.bg, 0.85) }
                    GradientStop { position: 1; color: Theme.bg }
                }
            }

            // Floating now-playing bar (opaque, over the fade above).
            Rectangle {
                id: playerBar
                visible: root.playingIndex >= 0
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 22
                implicitWidth: barRow.implicitWidth + 20
                implicitHeight: 44
                radius: 14
                color: Theme.dark ? "#141920" : "#ffffff"
                border.color: Theme.lineStrong

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
                        font.pointSize: 7.875
                        font.weight: 650
                        TapHandler { onTapped: continueToggle.checked = !continueToggle.checked }
                    }
                }
            }
        }
    }
}
