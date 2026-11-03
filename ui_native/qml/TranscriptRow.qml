import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// One transcript sentence: a time column, then the words. Tap a word to play
// the lecture from that word; tap the time to play or pause the sentence.
// Sentences still in Whisper are muted with a "다듬는 중" note.
Item {
    id: row

    property var seg: ({})
    property bool playing: false        // this row is the loaded segment
    property bool audioRunning: false   // player is actually playing
    property real positionSec: 0

    signal wordTapped(real startSec)
    signal playToggled()

    readonly property bool pending: !!seg.pending
    readonly property bool warn: !pending && (!!seg.segment_stt_rejected || seg.final_source === "whisper_error")
    readonly property bool canPlay: !!seg.audio_available && !pending
    readonly property var words: {
        if (!pending && seg.word_timeline && seg.word_timeline.length) return seg.word_timeline
        const text = pending ? (seg.segment_stt_raw || seg.whisper_raw || "Whisper 처리 중…") : (seg.text || "")
        return String(text).split(/\s+/).filter(w => w).map(w => ({ text: w, start_sec: 0, end_sec: -1 }))
    }

    readonly property real timeWidth: Theme.pick(52, 64, 50)
    readonly property real gap: Theme.pick(14, 12, 14)
    readonly property real padX: Theme.studio ? 12 : 0
    readonly property real padY: Theme.pick(9, 10, 8)
    readonly property bool bold: playing && Theme.classic

    implicitHeight: body.implicitHeight + padY * 2

    function clock(sec) {
        sec = Math.max(0, Math.floor(Number(sec) || 0))
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60
        return h ? h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
                 : m + ":" + String(s).padStart(2, "0")
    }

    HoverHandler { id: rowHover }

    Rectangle {
        anchors.fill: parent
        anchors.leftMargin: Theme.paper ? -14 : 0
        anchors.rightMargin: Theme.paper ? -14 : 0
        radius: Theme.pick(12, 8, 10)
        color: row.playing ? Theme.playingRow : (rowHover.hovered && !row.pending ? Theme.rowHover : "transparent")
    }

    Label {
        x: row.padX
        y: row.padY + Math.round((Theme.bodyLine - height) / 2)
        width: row.timeWidth
        text: row.clock(row.seg.start)
        color: row.playing ? Theme.playingTime : (timeHover.hovered ? Theme.accentText : Theme.muted)
        font.family: Theme.timeFamily
        font.pixelSize: Theme.classic ? 13 : 12
        font.weight: row.playing ? 600 : 400
        font.features: { "tnum": 1 }
        Accessible.role: Accessible.Button
        Accessible.name: row.clock(row.seg.start) + (row.playing && row.audioRunning ? " 일시정지" : " 재생")
        HoverHandler { id: timeHover; enabled: row.canPlay; cursorShape: Qt.PointingHandCursor }
        TapHandler { enabled: row.canPlay; onTapped: row.playToggled() }
    }

    ColumnLayout {
        id: body
        x: row.padX + row.timeWidth + row.gap
        y: row.padY
        width: row.width - x - row.padX
        spacing: 3

        Flow {
            id: flow
            Layout.fillWidth: true
            spacing: Math.round(Theme.bodyPx * 0.22)
            Repeater {
                model: row.words
                delegate: Rectangle {
                    id: word
                    required property var modelData
                    readonly property bool active: row.playing && modelData.end_sec > 0
                        && row.positionSec >= modelData.start_sec && row.positionSec < modelData.end_sec
                    width: wordText.implicitWidth + 2
                    height: Theme.bodyLine
                    radius: 3
                    color: active ? Theme.wordPlaying : (wordHover.hovered ? Theme.wordHover : "transparent")
                    Text {
                        id: wordText
                        anchors.centerIn: parent
                        text: word.modelData.text
                        color: row.pending ? Theme.muted : (word.active && Theme.studio ? Theme.heading : Theme.body)
                        font.family: Theme.bodyFamily
                        font.pointSize: Theme.pt(Theme.bodyPx)
                        font.weight: row.bold ? 600 : 400
                    }
                    HoverHandler { id: wordHover; enabled: row.canPlay; cursorShape: Qt.PointingHandCursor }
                    TapHandler { enabled: row.canPlay; onTapped: row.wordTapped(Number(word.modelData.start_sec) || 0) }
                }
            }
        }

        // Paper and classic: a quiet note; studio: a small outlined chip.
        Rectangle {
            visible: row.pending || row.warn
            implicitWidth: note.implicitWidth + (Theme.studio ? 14 : 0)
            implicitHeight: Theme.studio ? 20 : note.implicitHeight
            radius: 5
            color: "transparent"
            border.width: Theme.studio ? 1 : 0
            border.color: row.warn ? Theme.warnText : "#2E2E34"
            Label {
                id: note
                anchors.centerIn: parent
                text: row.pending ? (Theme.studio ? "처리 중" : "문장 다듬는 중…")
                    : row.seg.final_source === "whisper_error" ? "Whisper 오류 · 원문 오디오는 보존됨"
                    : "반복 의심 · 원문 확인 필요"
                color: row.warn ? Theme.warnText : (Theme.studio ? "#A8A8B0" : Theme.muted)
                font.pixelSize: Theme.studio ? 11 : 12
            }
        }
    }
}
