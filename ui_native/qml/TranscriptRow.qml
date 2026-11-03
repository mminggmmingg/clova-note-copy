import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// One transcript sentence. Mirrors .transcript-row in web/app_v6.css: a 72px
// time column (time + inline play), "SEG 001" + source chip, then the words.
// Notebook theme: handwriting on ruled paper with a red margin line, and the
// playing sentence becomes a taped yellow sticky note ("재생 중").
// Dark/light: accent frame with "NOW PLAYING".
Item {
    id: row

    property var seg: ({})
    property int index: 0
    property bool playing: false        // this row is the loaded segment
    property bool audioRunning: false   // player is actually playing
    property real positionSec: 0
    property real handSize: 21          // notebook handwriting px (web: clamp(21px, 1.38vw, 25px))

    signal wordTapped(real startSec)
    signal playToggled()

    readonly property real textPx: Theme.notebook ? handSize : 14.5
    readonly property real lineH: Theme.notebook ? Math.round(handSize * 1.52) : 26.4
    readonly property real bodyX: 84
    readonly property real wordsY: body.y + meta.height + body.spacing

    implicitHeight: Math.max(74, body.implicitHeight + (Theme.notebook ? 18 : 26))

    // Still in the sentence worker while recording (web: .transcript-row.processing).
    readonly property bool pending: !!seg.pending
    readonly property bool warn: !pending && (!!seg.segment_stt_rejected || seg.final_source === "whisper_error")
    readonly property var words: {
        if (!pending && seg.word_timeline && seg.word_timeline.length) return seg.word_timeline
        const text = pending ? (seg.segment_stt_raw || seg.whisper_raw || "Whisper 처리 중…") : (seg.text || "")
        return String(text).split(/\s+/).filter(w => w).map(w => ({ text: w, start_sec: 0, end_sec: -1 }))
    }

    function clock(sec) {
        sec = Math.max(0, Math.floor(Number(sec) || 0))
        const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60
        return h ? h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0")
                 : m + ":" + String(s).padStart(2, "0")
    }

    HoverHandler { id: rowHover }

    // ---------------------------------------------------------------- notebook paper
    // Ruled lines under every handwriting line, across the whole row.
    Repeater {
        model: Theme.notebook ? Math.max(1, Math.round(flow.height / row.lineH)) : 0
        Rectangle {
            required property int index
            x: 0
            width: row.width
            y: row.wordsY + (index + 1) * row.lineH - 2
            height: 1
            color: Theme.ruling
        }
    }
    // Red margin line between the time rail and the text.
    Rectangle {
        visible: Theme.notebook
        x: row.bodyX - 7
        width: 1
        height: row.height
        color: Theme.marginLine
    }
    Rectangle {
        anchors.fill: parent
        visible: Theme.notebook && rowHover.hovered && !row.playing
        color: Theme.hover
        radius: 7
    }

    // Sticky note behind the playing sentence (notebook).
    Item {
        visible: Theme.notebook && row.playing
        x: row.bodyX - 10
        y: body.y - 7
        width: row.width - x
        height: body.implicitHeight + 14
        rotation: -0.16
        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 5
            anchors.bottomMargin: -6
            anchors.leftMargin: 2
            anchors.rightMargin: 2
            radius: 8
            color: Theme.stickyShadow
        }
        Rectangle {
            anchors.fill: parent
            topLeftRadius: 3
            topRightRadius: 8
            bottomRightRadius: 6
            bottomLeftRadius: 4
            border.color: Theme.stickyBorder
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "#fff4bf" }
                GradientStop { position: 0.28; color: Theme.stickyNote }
                GradientStop { position: 1; color: Theme.stickyNote }
            }
        }
        Tape {
            anchors.horizontalCenter: parent.horizontalCenter
            y: -8
            width: 64
            height: 17
            rotation: -1.5
            color: Theme.ink(231, 211, 169, .68)
        }
        Label {
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: 15
            anchors.bottomMargin: 8
            text: "재생 중"
            color: Theme.nowPlaying
            font.pixelSize: 7
            font.weight: 800
            font.letterSpacing: 0.8
        }
    }

    // ---------------------------------------------------------------- dark / light
    Rectangle {
        anchors.fill: parent
        radius: row.playing ? 15 : 7
        visible: !Theme.notebook && (row.playing || rowHover.hovered)
        border.width: row.playing ? 1 : 0
        border.color: Theme.ink(137, 150, 255, .30)
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: row.playing ? Theme.ink(124, 140, 255, .13) : Theme.hover }
            GradientStop { position: 0.6; color: row.playing ? Theme.ink(124, 140, 255, .035) : Theme.hover }
            GradientStop { position: 1; color: row.playing ? Theme.ink(255, 255, 255, .012) : Theme.hover }
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
    Rectangle {
        visible: !Theme.notebook && !row.playing
        anchors.bottom: parent.bottom
        width: parent.width
        height: 1
        color: Theme.rowLine
    }
    Label {
        visible: !Theme.notebook && row.playing
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: 10
        anchors.bottomMargin: 7
        text: "NOW PLAYING"
        color: Theme.nowPlaying
        font.pointSize: Theme.pt(6.8)
        font.weight: 800
        font.letterSpacing: 0.8
    }

    // ---------------------------------------------------------------- time rail
    Column {
        x: 12
        y: Theme.notebook ? 11 : 16
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
            opacity: row.playing || rowHover.hovered ? 1 : 0.45
            visible: !!row.seg.audio_available && !row.pending
            Icon {
                anchors.centerIn: parent
                width: 12
                height: 12
                name: row.playing && row.audioRunning ? "pause" : "play"
                color: playHover.hovered ? Theme.accent : Theme.playIcon
            }
            HoverHandler { id: playHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: row.playToggled() }
        }
    }

    // ---------------------------------------------------------------- body
    ColumnLayout {
        id: body
        x: row.bodyX
        y: Theme.notebook ? 8 : 13
        width: parent.width - x - (Theme.notebook ? 64 : 54)
        spacing: Theme.notebook ? 2 : 4

        RowLayout {
            id: meta
            Layout.preferredHeight: 18
            spacing: 7
            Label {
                text: "SEG " + String(row.seg.segment || 0).padStart(3, "0")
                color: Theme.segIndex
                font.pointSize: Theme.pt(8.5)
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
                    text: row.pending ? "WHISPER · 처리 중"
                        : row.seg.final_source === "whisper_error" ? "WHISPER · ERROR"
                        : row.seg.segment_stt_rejected ? "WHISPER · 반복 의심" : "WHISPER LARGE-V3"
                    color: row.warn ? Theme.warnText : Theme.chipText
                    font.pointSize: Theme.pt(7.8)
                    font.weight: 750
                    font.letterSpacing: 0.3
                }
            }
        }

        Flow {
            id: flow
            Layout.fillWidth: true
            spacing: Theme.notebook ? 6 : 4
            Repeater {
                model: row.words
                delegate: Rectangle {
                    id: word
                    required property var modelData
                    readonly property bool active: row.playing && modelData.end_sec > 0
                        && row.positionSec >= modelData.start_sec && row.positionSec < modelData.end_sec
                    width: wordText.implicitWidth + 2
                    height: row.lineH
                    radius: 3
                    color: active ? Theme.wordPlaying : (wordHover.hovered ? Theme.wordHover : "transparent")
                    Rectangle {
                        visible: word.active
                        anchors.bottom: parent.bottom
                        anchors.bottomMargin: Theme.notebook ? 3 : 2
                        width: parent.width
                        height: Math.round(row.textPx * 0.42)
                        radius: 2
                        color: Theme.wordPlayingUnder
                    }
                    Text {
                        id: wordText
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: Theme.notebook ? 1 : 0
                        text: word.modelData.text
                        color: row.pending ? Theme.muted : Theme.transcript
                        font.family: Theme.notebook ? Theme.handFamily : Theme.family
                        font.pointSize: Theme.pt(row.textPx)
                        font.weight: word.active ? (Theme.notebook ? 700 : 800) : (Theme.notebook ? 400 : 620)
                        font.letterSpacing: Theme.notebook ? 0.13 : -0.07
                    }
                    HoverHandler { id: wordHover; enabled: !row.pending; cursorShape: Qt.PointingHandCursor }
                    TapHandler { enabled: !row.pending; onTapped: row.wordTapped(Number(word.modelData.start_sec) || 0) }
                }
            }
        }
    }
}
