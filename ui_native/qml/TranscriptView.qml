import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// The lecture's sentences in one centered column, the live (not yet
// committed) sentence at the end while recording. Each layout sets `header`
// (paper puts the page title there) and the margins.
ListView {
    id: view
    objectName: "transcript"

    required property var app
    property real sidePadding: 32
    property real maxColumn: 860

    readonly property real columnWidth: Math.max(200, Math.min(maxColumn, width - sidePadding * 2))
    leftMargin: Math.round((width - columnWidth) / 2)
    rightMargin: leftMargin
    bottomMargin: 32
    // The margins center the column; the view keeps the contentX it had
    // when it was first laid out (before it had a width), so re-anchor it.
    flickableDirection: Flickable.VerticalFlick
    onLeftMarginChanged: contentX = -leftMargin
    clip: true
    spacing: Theme.pick(8, 2, 8)
    model: app.segments
    boundsBehavior: Flickable.StopAtBounds

    header: Item { width: view.columnWidth; height: 16 }

    footer: Column {
        width: view.columnWidth
        topPadding: view.spacing

        // Live sentence: the streaming Whisper text, then a static caret.
        Item {
            id: live
            visible: view.app.liveText !== ""
            width: parent.width
            height: visible ? liveFlow.implicitHeight + pad * 2 : 0
            readonly property real pad: Theme.pick(9, 10, 8)
            readonly property real timeWidth: Theme.pick(52, 64, 50)
            readonly property real padX: Theme.studio ? 12 : 0
            Rectangle {
                anchors.fill: parent
                radius: 8
                color: Theme.liveRow
            }
            Label {
                x: live.padX
                y: live.pad + Math.round((Theme.bodyLine - height) / 2)
                text: Theme.liveLabel
                color: Theme.accentText
                font.family: Theme.timeFamily
                font.pixelSize: Theme.classic ? 13 : 12
                font.weight: 600
            }
            Flow {
                id: liveFlow
                x: live.padX + live.timeWidth + Theme.pick(14, 12, 14)
                y: live.pad
                width: parent.width - x - live.padX
                spacing: Math.round(Theme.bodyPx * 0.22)
                Repeater {
                    model: view.app.liveText.split(/\s+/).filter(w => w)
                    Text {
                        required property string modelData
                        height: Theme.bodyLine
                        verticalAlignment: Text.AlignVCenter
                        text: modelData
                        color: Theme.liveText
                        font.family: Theme.bodyFamily
                        font.pointSize: Theme.pt(Theme.bodyPx)
                    }
                }
                Item {
                    width: 2
                    height: Theme.bodyLine
                    Rectangle {
                        anchors.verticalCenter: parent.verticalCenter
                        width: 2
                        height: Math.round(Theme.bodyPx * 1.15)
                        radius: 1
                        color: Theme.accent
                    }
                }
            }
            onHeightChanged: if (view.app.recording && view.app.followLatest) Qt.callLater(view.app.followBottom)
        }

        // Nothing committed yet.
        Column {
            visible: view.app.session !== null && view.app.segments.length === 0 && view.app.liveText === ""
            width: parent.width
            topPadding: 36
            spacing: 6
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: view.app.recording ? "듣고 있어요" : "녹음된 문장이 없습니다"
                color: Theme.text
                font.pixelSize: 15
                font.weight: 600
            }
            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                text: view.app.recording ? "말이 시작되면 문장 단위로 여기에 쌓입니다." : "이 세션에는 전사된 문장이 없습니다."
                color: Theme.muted
                font.pixelSize: 13
            }
        }
    }

    // Scrolling up while recording stops following the newest sentence;
    // scrolling back to the end resumes it.
    onMovementEnded: {
        app.followLatest = atYEnd
        keepTop = atYBeginning
    }

    // The header grows upward when it changes height (PDFs arrive, the
    // title wraps), so a reader still at the top is kept there.
    property bool keepTop: true
    function toTop() {
        keepTop = true
        positionViewAtBeginning()
    }
    onOriginYChanged: if (keepTop && !app.recording) Qt.callLater(positionViewAtBeginning)

    delegate: TranscriptRow {
        required property var modelData
        required property int index
        width: view.columnWidth
        seg: modelData
        playing: view.app.playingIndex === index
        audioRunning: view.app.audioRunning
        positionSec: playing ? view.app.playerPositionSec : 0
        onWordTapped: startSec => view.app.playAt(index, startSec)
        onPlayToggled: view.app.togglePlay(index)
    }

    ScrollBar.vertical: ScrollBar {
        onPressedChanged: if (!pressed) {
            view.app.followLatest = view.atYEnd
            view.keepTop = view.atYBeginning
        }
        contentItem: Rectangle {
            implicitWidth: 6
            radius: 3
            color: Theme.scrollbar
            // Only while scrolling or hovered, and only when there is more.
            opacity: parent.size < 1 && parent.active ? 1 : 0
        }
    }
}
