import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// One transcript sentence. Mirrors .transcript-row in web/app_v6.css:
// 72px time column (time + inline play), body with "SEG 001" + source chip,
// then the words; the playing row gets the accent frame and "NOW PLAYING".
Item {
    id: row

    property var seg: ({})
    property int index: 0
    property bool playing: false        // this row is the loaded segment
    property bool audioRunning: false   // player is actually playing
    property real positionSec: 0

    signal wordTapped(real startSec)
    signal playToggled()

    implicitHeight: Math.max(74, body.implicitHeight + 26)

    readonly property bool warn: !!seg.segment_stt_rejected || seg.final_source === "whisper_error"
    readonly property var words: {
        if (seg.word_timeline && seg.word_timeline.length) return seg.word_timeline
        return String(seg.text || "").split(/\s+/).filter(w => w).map(w => ({ text: w, start_sec: 0, end_sec: -1 }))
    }

    function clock(sec) {
        sec = Math.max(0, Math.floor(Number(sec) || 0))
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60
        return h ? h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
                 : m + ":" + String(s).padStart(2, "0")
    }

    HoverHandler { id: rowHover }

    // Background: subtle hover, or the accent frame while playing.
    Rectangle {
        anchors.fill: parent
        radius: row.playing ? 15 : 7
        visible: row.playing || rowHover.hovered
        border.width: row.playing ? 1 : 0
        border.color: Theme.ink(137, 150, 255, .30)
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: row.playing ? Theme.ink(124, 140, 255, .13) : Theme.ink(255, 255, 255, Theme.dark ? .018 : 0) }
            GradientStop { position: 0.6; color: row.playing ? Theme.ink(124, 140, 255, .035) : Theme.ink(255, 255, 255, Theme.dark ? .018 : 0) }
            GradientStop { position: 1; color: row.playing ? Theme.ink(255, 255, 255, .012) : Theme.ink(255, 255, 255, Theme.dark ? .018 : 0) }
        }
        Rectangle {
            visible: row.playing
            x: 1
            y: 8
            width: 4
            height: parent.height - 16
            radius: 2
            color: Theme.ink(124, 140, 255, .82)
        }
    }

    // Row separator
    Rectangle {
        visible: !row.playing
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.rowLine
    }

    // Time column
    Column {
        x: 12
        y: 16
        width: 60
        spacing: 7
        Label {
            text: row.clock(row.seg.start)
            color: Theme.time
            font.pixelSize: 9
            font.features: { "tnum": 1 }
        }
        Rectangle {
            width: 25
            height: 25
            radius: 7
            color: playHover.hovered ? Theme.accentSoft : "transparent"
            border.color: playHover.hovered ? Theme.ink(124, 140, 255, .14) : "transparent"
            opacity: row.playing || rowHover.hovered ? 1 : 0.45
            visible: !!row.seg.audio_available
            Icon {
                anchors.centerIn: parent
                width: 12
                height: 12
                name: row.playing && row.audioRunning ? "pause" : "play"
                color: playHover.hovered ? "#c4caff" : Theme.playIcon
            }
            HoverHandler { id: playHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: row.playToggled() }
        }
    }

    // Body
    ColumnLayout {
        id: body
        x: 84
        y: 13
        width: parent.width - x - 64
        spacing: 4

        RowLayout {
            Layout.preferredHeight: 18
            spacing: 7
            Label {
                text: "SEG " + String(row.seg.segment || 0).padStart(3, "0")
                color: Theme.segIndex
                font.pointSize: 6.375
                font.weight: 750
                font.letterSpacing: 0.6
            }
            Rectangle {
                implicitWidth: chip.implicitWidth + 12
                implicitHeight: 17
                radius: 5
                color: row.warn ? Theme.warnSoft : Theme.chipBg
                Label {
                    id: chip
                    anchors.centerIn: parent
                    text: row.seg.final_source === "whisper_error" ? "WHISPER · ERROR"
                        : row.seg.segment_stt_rejected ? "WHISPER · 반복 의심" : "WHISPER LARGE-V3"
                    color: row.warn ? Theme.warnText : Theme.chipText
                    font.pointSize: 5.85
                    font.weight: 750
                    font.letterSpacing: 0.3
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: 4
            Repeater {
                model: row.words
                delegate: Rectangle {
                    id: word
                    required property var modelData
                    readonly property bool active: row.playing && modelData.end_sec > 0
                        && row.positionSec >= modelData.start_sec && row.positionSec < modelData.end_sec
                    width: wordText.implicitWidth + 2
                    height: 26.4
                    radius: 3
                    color: active ? Theme.wordPlaying : (wordHover.hovered ? Theme.wordHover : "transparent")
                    Rectangle {
                        visible: word.active
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: 2
                        width: parent.width
                        height: 6
                        radius: 2
                        color: Theme.wordPlayingUnder
                    }
                    Text {
                        id: wordText
                        anchors.centerIn: parent
                        text: word.modelData.text
                        color: Theme.transcript
                        font.family: Theme.family
                        font.pointSize: 10.875
                        font.weight: word.active ? 800 : 620
                        font.letterSpacing: -0.07
                    }
                    HoverHandler { id: wordHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: row.wordTapped(Number(word.modelData.start_sec) || 0) }
                }
            }
        }
    }

    Label {
        visible: row.playing
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 10
        anchors.bottomMargin: 7
        text: "NOW PLAYING"
        color: Theme.nowPlaying
        font.pointSize: 5.1
        font.weight: 800
        font.letterSpacing: 0.8
    }
}
