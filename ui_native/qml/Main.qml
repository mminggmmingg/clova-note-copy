import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia

// Local Clova native UI, step U1: read-only browsing over the existing API.
// Library (subjects -> lectures) on the left, transcript on the right,
// tap a word to play the lecture from that word.
ApplicationWindow {
    id: root

    required property var api
    property string initialSessionId: ""

    visible: true
    title: session ? session.title + " — Local Clova" : "Local Clova"

    // Theme follows the desktop light/dark preference.
    readonly property bool dark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark
    readonly property color cBg: dark ? "#14171c" : "#f5f6f8"
    readonly property color cPanel: dark ? "#1b1f26" : "#ffffff"
    readonly property color cCard: dark ? "#20252d" : "#ffffff"
    readonly property color cLine: dark ? "#2c333d" : "#e1e5eb"
    readonly property color cText: dark ? "#e6e9ef" : "#1e2530"
    readonly property color cMuted: dark ? "#8d97a7" : "#6b7585"
    readonly property color cAccent: dark ? "#8fa3ff" : "#3d58d6"
    readonly property color cAccentSoft: dark ? "#262f52" : "#e7ebfd"
    readonly property color cWarn: dark ? "#f0a46d" : "#b25a1d"
    readonly property color cWarnSoft: dark ? "#3a2a1f" : "#fbeee4"

    color: cBg
    font.pixelSize: 14

    property var subjects: ({})
    property string sessionId: ""
    property var session: null
    property var segments: []
    property string errorText: ""
    property string search: ""

    // Playback state: which segment is loaded and where to seek once loaded.
    property int playingSegment: -1
    property int playingIndex: -1
    property real pendingSeekMs: -1

    Component.onCompleted: api.fetchLibrary()

    Connections {
        target: root.api
        function onLibraryLoaded(data) {
            root.errorText = ""
            const subs = {}
            for (const s of data.subjects || []) subs[s.id] = s
            root.subjects = subs
            root.rebuildLibrary(data.sessions || [])
            if (root.initialSessionId) root.openSession(root.initialSessionId)
        }
        function onSegmentsLoaded(sid, data) {
            if (sid !== root.sessionId) return
            root.session = data
            root.segments = (data.segments || []).filter(s => !s.deleted)
        }
        function onRequestFailed(what, message) {
            root.errorText = (what === "library" ? "백엔드에 연결할 수 없습니다 (" + root.api.baseUrl + "): " : "불러오지 못했습니다: ") + message
        }
    }

    property var allSessions: []
    ListModel { id: libraryModel }

    function subjectLabel(id) {
        const s = subjects[id]
        if (!s) return "미분류"
        return (s.emoji ? s.emoji + " " : "") + s.name
    }

    function rebuildLibrary(list) {
        if (list) allSessions = list
        libraryModel.clear()
        const q = search.trim().toLowerCase()
        const rows = allSessions
            .filter(s => !q || String(s.title || "").toLowerCase().includes(q))
            .map(s => ({
                sessionId: s.session_id,
                title: s.title || s.session_id,
                subject: subjectLabel(s.subject_id),
                created: s.created_at || "",
                minutes: Math.round(Number(s.recording_time_sec || s.duration_sec || 0) / 60),
                segmentsCount: Number(s.segment_count || 0),
                recording: !!s.recording
            }))
            .sort((a, b) => a.subject.localeCompare(b.subject, "ko") || b.created.localeCompare(a.created))
        for (const r of rows) libraryModel.append(r)
    }

    function openSession(sid) {
        player.stop()
        playingSegment = -1
        playingIndex = -1
        sessionId = sid
        session = null
        segments = []
        api.fetchSegments(sid)
    }

    function clock(sec) {
        sec = Math.max(0, Math.floor(Number(sec) || 0))
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60
        const mm = String(m).padStart(h ? 2 : 1, "0"), ss = String(s).padStart(2, "0")
        return h ? h + ":" + mm + ":" + ss : mm + ":" + ss
    }

    function shortDate(iso) {
        if (!iso) return ""
        const d = new Date(iso)
        const days = ["일", "월", "화", "수", "목", "금", "토"]
        return (d.getMonth() + 1) + "/" + d.getDate() + " (" + days[d.getDay()] + ")"
    }

    function wordsOf(seg) {
        if (seg.word_timeline && seg.word_timeline.length) return seg.word_timeline
        // No word timing (rejected or legacy): whole words, playable from the start.
        return String(seg.text || "").split(/\s+/).filter(w => w).map(w => ({ text: w, start_sec: 0, end_sec: -1 }))
    }

    function playAt(index, startSec) {
        const seg = segments[index]
        if (!seg || !seg.audio_available) return
        const url = api.url(seg.audio_url)
        playingSegment = seg.segment
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

    MediaPlayer {
        id: player
        objectName: "player"
        audioOutput: AudioOutput { id: audioOut; objectName: "audioOut" }
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
            if (mediaStatus === MediaPlayer.EndOfMedia && continueBox.checked && root.playingIndex + 1 < root.segments.length)
                root.playAt(root.playingIndex + 1, 0)
        }
        onErrorOccurred: (error, message) => root.errorText = "재생 오류: " + message
    }

    SplitView {
        anchors.fill: parent
        orientation: Qt.Horizontal

        // ---------------------------------------------------------------- library
        Rectangle {
            SplitView.preferredWidth: 310
            SplitView.minimumWidth: 220
            color: root.cPanel

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 14
                spacing: 10

                Label {
                    text: "Local Clova"
                    font.pixelSize: 18
                    font.weight: Font.DemiBold
                    color: root.cText
                }

                TextField {
                    Layout.fillWidth: true
                    placeholderText: "강의 검색"
                    onTextChanged: { root.search = text; root.rebuildLibrary() }
                }

                ListView {
                    id: libraryList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    model: libraryModel
                    spacing: 2
                    section.property: "subject"
                    section.delegate: Label {
                        required property string section
                        width: ListView.view.width
                        topPadding: 12
                        bottomPadding: 4
                        text: section
                        color: root.cMuted
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    delegate: ItemDelegate {
                        id: sessionItem
                        required property string sessionId
                        required property string title
                        required property string created
                        required property int minutes
                        required property int segmentsCount
                        required property bool recording
                        width: ListView.view.width
                        highlighted: sessionId === root.sessionId
                        onClicked: root.openSession(sessionId)
                        background: Rectangle {
                            radius: 8
                            color: sessionItem.highlighted ? root.cAccentSoft : (sessionItem.hovered ? root.cBg : "transparent")
                        }
                        contentItem: ColumnLayout {
                            spacing: 1
                            Label {
                                Layout.fillWidth: true
                                text: (sessionItem.recording ? "● " : "") + sessionItem.title
                                color: sessionItem.highlighted ? root.cAccent : root.cText
                                elide: Text.ElideRight
                            }
                            Label {
                                Layout.fillWidth: true
                                text: root.shortDate(sessionItem.created) + " · " + sessionItem.minutes + "분 · " + sessionItem.segmentsCount + "문장"
                                color: root.cMuted
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }
        }

        // ---------------------------------------------------------------- session
        ColumnLayout {
            SplitView.fillWidth: true
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                visible: root.errorText !== ""
                implicitHeight: errorRow.implicitHeight + 16
                color: root.cWarnSoft
                RowLayout {
                    id: errorRow
                    anchors.fill: parent
                    anchors.margins: 8
                    Label {
                        Layout.fillWidth: true
                        text: root.errorText
                        color: root.cWarn
                        wrapMode: Text.Wrap
                    }
                    Button {
                        text: "다시 시도"
                        onClicked: { root.errorText = ""; root.sessionId ? root.api.fetchSegments(root.sessionId) : root.api.fetchLibrary() }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                Layout.bottomMargin: 8
                spacing: 2
                visible: root.session !== null
                Label {
                    Layout.fillWidth: true
                    text: root.session ? root.session.title : ""
                    font.pixelSize: 20
                    font.weight: Font.DemiBold
                    color: root.cText
                    elide: Text.ElideRight
                }
                Label {
                    text: root.session
                        ? root.subjectLabel(root.session.subject_id) + " · " + root.shortDate(root.session.created_at)
                          + " · " + root.clock(root.session.recording_time_sec) + " · " + root.segments.length + "문장"
                        : ""
                    color: root.cMuted
                }
            }

            Label {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: root.session === null
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                text: root.sessionId ? "불러오는 중…" : "왼쪽에서 강의를 고르세요"
                color: root.cMuted
                font.pixelSize: 16
            }

            ListView {
                id: transcript
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: root.session !== null
                clip: true
                spacing: 8
                leftMargin: 18
                rightMargin: 18
                bottomMargin: 18
                model: root.segments
                ScrollBar.vertical: ScrollBar {}

                delegate: Rectangle {
                    id: card
                    required property var modelData
                    required property int index
                    readonly property bool playing: root.playingIndex === index
                    width: ListView.view.width - ListView.view.leftMargin - ListView.view.rightMargin
                    implicitHeight: body.implicitHeight + 24
                    radius: 10
                    color: root.cCard
                    border.color: playing ? root.cAccent : root.cLine
                    border.width: 1

                    ColumnLayout {
                        id: body
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 12
                        spacing: 6

                        RowLayout {
                            spacing: 8
                            Label {
                                text: root.clock(card.modelData.recording_start)
                                color: root.cMuted
                                font.pixelSize: 12
                                font.features: { "tnum": 1 }
                            }
                            Label {
                                text: "SEG " + card.modelData.segment
                                color: root.cMuted
                                font.pixelSize: 12
                            }
                            Rectangle {
                                visible: card.modelData.segment_stt_rejected || card.modelData.final_source === "whisper_error"
                                radius: 5
                                color: root.cWarnSoft
                                implicitWidth: chip.implicitWidth + 12
                                implicitHeight: chip.implicitHeight + 4
                                Label {
                                    id: chip
                                    anchors.centerIn: parent
                                    text: card.modelData.final_source === "whisper_error" ? "Whisper · error" : "Whisper · 반복 의심"
                                    color: root.cWarn
                                    font.pixelSize: 11
                                }
                            }
                            Item { Layout.fillWidth: true }
                            ToolButton {
                                text: card.playing && player.playbackState === MediaPlayer.PlayingState ? "❚❚" : "▶"
                                enabled: !!card.modelData.audio_available
                                onClicked: card.playing && player.playbackState === MediaPlayer.PlayingState
                                    ? player.pause() : root.playAt(card.index, 0)
                            }
                        }

                        Flow {
                            Layout.fillWidth: true
                            spacing: 5
                            Repeater {
                                model: root.wordsOf(card.modelData)
                                delegate: Text {
                                    required property var modelData
                                    readonly property real t: player.position / 1000
                                    readonly property bool active: card.playing && modelData.end_sec > 0
                                        && t >= modelData.start_sec && t < modelData.end_sec
                                    text: modelData.text
                                    color: active ? root.cAccent : root.cText
                                    font.pixelSize: 16
                                    font.weight: active ? Font.DemiBold : Font.Normal
                                    TapHandler {
                                        onTapped: root.playAt(card.index, Number(parent.modelData.start_sec) || 0)
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // ------------------------------------------------------------ player bar
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 52
                color: root.cPanel
                border.color: root.cLine
                visible: root.session !== null

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    spacing: 12
                    Button {
                        text: player.playbackState === MediaPlayer.PlayingState ? "일시정지" : "재생"
                        enabled: root.segments.length > 0
                        onClicked: {
                            if (player.playbackState === MediaPlayer.PlayingState) player.pause()
                            else if (root.playingIndex >= 0) player.play()
                            else root.playAt(0, 0)
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        color: root.cMuted
                        text: root.playingIndex >= 0
                            ? "SEG " + root.playingSegment + " · " + root.clock(player.position / 1000) + " / " + root.clock(player.duration / 1000)
                            : "단어를 누르면 그 위치부터 재생합니다"
                        elide: Text.ElideRight
                    }
                    CheckBox {
                        id: continueBox
                        text: "이어 재생"
                        checked: true
                    }
                }
            }
        }
    }
}
