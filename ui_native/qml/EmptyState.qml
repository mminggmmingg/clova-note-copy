import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Landing view when no lecture is open. Mirrors .empty-state in the web UI,
// but static: the web's endlessly animated orbit/wave keep the GPU busy.
Item {
    id: empty

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 650)
        spacing: 0

        // Orbit with the wave core
        Item {
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 24
            width: 126
            height: 126
            Rectangle {
                anchors.fill: parent
                radius: width / 2
                color: "transparent"
                border.color: Theme.ink(124, 140, 255, .11)
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.ink(124, 140, 255, .06) }
                    GradientStop { position: 1; color: "transparent" }
                }
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: 11
                radius: width / 2
                color: "transparent"
                border.color: Theme.ink(124, 140, 255, .11)
            }
            Rectangle {
                anchors.centerIn: parent
                width: 70
                height: 70
                radius: 23
                border.color: Theme.ink(147, 158, 255, .25)
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.ink(124, 140, 255, .22) }
                    GradientStop { position: 1; color: Theme.ink(169, 121, 255, .09) }
                }
                Row {
                    anchors.centerIn: parent
                    spacing: 3
                    Repeater {
                        model: [9, 18, 25, 15, 10]
                        Rectangle {
                            required property int modelData
                            anchors.verticalCenter: parent.verticalCenter
                            width: 3
                            height: modelData
                            radius: 1.5
                            color: "#c8ceff"
                        }
                    }
                }
            }
        }

        Label {
            Layout.alignment: Qt.AlignHCenter
            text: "LOCAL · REALTIME · PRIVATE"
            color: Theme.heroKicker
            font.pixelSize: 9
            font.weight: 750
            font.letterSpacing: 1.4
        }
        Label {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 13
            Layout.bottomMargin: 14
            horizontalAlignment: Text.AlignHCenter
            text: "강의가 끝날 때까지\n기억은 Clova에게 맡기세요."
            color: Theme.heroText
            font.pixelSize: 38
            font.weight: 700
            font.letterSpacing: -1.6
            lineHeight: 1.13
        }
        Label {
            Layout.fillWidth: true
            Layout.maximumWidth: 570
            Layout.alignment: Qt.AlignHCenter
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "Whisper Large-v3가 강의 음성을 로컬에서 전사합니다. 원본 음성과 타임라인은 그대로 보존되며, 왼쪽에서 강의를 고르면 단어를 눌러 그 위치부터 들을 수 있습니다."
            color: Theme.heroSub
            font.pixelSize: 12
            lineHeight: 1.75
        }
        Row {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 38
            spacing: 22
            Repeater {
                model: [["01", "Whisper Large-v3"], ["02", "원문 오디오 보존"], ["03", "Word Seek"]]
                Row {
                    required property var modelData
                    spacing: 6
                    Label { text: parent.modelData[0]; color: Theme.muted; font.pixelSize: 8 }
                    Label { text: parent.modelData[1]; color: Theme.muted2; font.pointSize: 7.125 }
                }
            }
        }
    }
}
