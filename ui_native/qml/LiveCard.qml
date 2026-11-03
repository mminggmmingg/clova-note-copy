import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Live preview of the sentence still being spoken (web .live-card): the
// streaming Whisper text that has not been committed as a segment yet.
// Static, no pulsing dot: nothing here repaints except when the text changes.
Item {
    id: card

    property string text: ""
    property real handSize: 21

    implicitHeight: box.implicitHeight + 15

    Rectangle {
        visible: Theme.notebook
        anchors.fill: box
        anchors.topMargin: 3
        anchors.bottomMargin: -3
        radius: box.radius
        color: Theme.paperLip
    }

    Rectangle {
        id: box
        y: 15
        width: parent.width
        implicitHeight: column.implicitHeight + 27
        radius: 13
        border.color: Theme.pick(Theme.ink(124, 140, 255, .15), Theme.ink(103, 117, 232, .16), Theme.ink(185, 138, 73, .24))
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.pick(Theme.ink(124, 140, 255, .075), Theme.ink(103, 117, 232, .08), "#fff8e6") }
            GradientStop { position: 1; color: Theme.pick(Theme.ink(124, 140, 255, .025), Theme.ink(255, 255, 255, .65), "#fdf6ea") }
        }

        ColumnLayout {
            id: column
            x: 15
            y: 13
            width: parent.width - 30
            spacing: Theme.notebook ? 4 : 9

            RowLayout {
                Layout.fillWidth: true
                Rectangle {
                    width: 5
                    height: 5
                    radius: 2.5
                    color: Theme.pick("#7c8cff", "#6775e8", Theme.red)
                }
                Label {
                    Layout.fillWidth: true
                    text: "실시간 인식 · LIVE"
                    color: Theme.pick("#9ca8ff", "#5b68d8", "#a3744a")
                    font.pointSize: Theme.pt(8.5)
                    font.weight: 700
                    font.letterSpacing: 0.45
                }
                Label {
                    text: "WHISPER LARGE-V3"
                    color: Theme.pick("#6e7890", "#8a94a3", "#9a8d7e")
                    font.pointSize: Theme.pt(8.5)
                    font.weight: 700
                    font.letterSpacing: 0.45
                }
            }

            Label {
                Layout.fillWidth: true
                text: card.text
                color: Theme.pick("#c9d0ff", "#3f4bb0", "#5a4a3a")
                font.family: Theme.notebook ? Theme.handFamily : Theme.family
                font.pointSize: Theme.pt(Theme.notebook ? card.handSize : 14)
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.notebook ? Math.round(card.handSize * 1.52) : 24
                wrapMode: Text.Wrap
            }
        }
    }
}
