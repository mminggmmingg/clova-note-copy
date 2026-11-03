import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import "."

// Landing view when no lecture is open. Mirrors .empty-state in the web UI
// (notebook: taped paper card, colored wave bars, paper action button), but
// static: the web's endlessly animated orbit/wave keep the GPU busy.
Item {
    id: empty

    signal newSessionRequested()

    readonly property var bars: [[9, "#d98778"], [18, "#7fa18a"], [25, "#c59a54"], [15, "#7fa18a"], [8, "#d98778"]]

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 650)
        spacing: 0

        // Orbit with the core card
        Item {
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 24
            width: 126
            height: 126

            Shape {
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: Theme.notebook ? Theme.ink(151, 124, 89, .14) : Theme.ink(124, 140, 255, .11)
                    strokeWidth: 1
                    strokeStyle: ShapePath.DashLine
                    dashPattern: [3, 3]
                    fillColor: "transparent"
                    PathAngleArc { centerX: 63; centerY: 63; radiusX: 62; radiusY: 62; startAngle: 0; sweepAngle: 360 }
                }
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: 11
                radius: width / 2
                color: Theme.notebook ? Theme.ink(255, 251, 244, .45) : Theme.ink(124, 140, 255, .05)
                border.color: Theme.notebook ? Theme.ink(151, 124, 89, .15) : Theme.ink(124, 140, 255, .11)
            }

            Item {
                anchors.centerIn: parent
                width: 70
                height: 70
                rotation: Theme.notebook ? 0.7 : 0
                Rectangle {
                    visible: Theme.notebook
                    anchors.fill: parent
                    anchors.topMargin: 9
                    anchors.bottomMargin: -12
                    anchors.leftMargin: 4
                    anchors.rightMargin: 4
                    radius: 24
                    color: Theme.ink(93, 70, 44, .09)
                }
                Rectangle {
                    visible: Theme.notebook
                    anchors.fill: parent
                    anchors.topMargin: 4
                    anchors.bottomMargin: -4
                    radius: 22
                    color: Theme.ink(187, 151, 104, .12)
                }
                Rectangle {
                    anchors.fill: parent
                    topLeftRadius: Theme.notebook ? 20 : 23
                    topRightRadius: Theme.notebook ? 25 : 23
                    bottomRightRadius: Theme.notebook ? 22 : 23
                    bottomLeftRadius: Theme.notebook ? 18 : 23
                    border.color: Theme.notebook ? "#ddcdb8" : Theme.ink(147, 158, 255, .25)
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Theme.notebook ? "#fffdf8" : Theme.ink(124, 140, 255, .22) }
                        GradientStop { position: 1; color: Theme.notebook ? "#f5eadb" : Theme.ink(169, 121, 255, .09) }
                    }
                    Row {
                        anchors.centerIn: parent
                        spacing: 3
                        Repeater {
                            model: empty.bars
                            Rectangle {
                                required property var modelData
                                anchors.verticalCenter: parent.verticalCenter
                                width: 3
                                height: modelData[0]
                                radius: 1.5
                                color: Theme.notebook ? modelData[1] : "#c8ceff"
                            }
                        }
                    }
                }
                Tape {
                    visible: Theme.notebook
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: -8
                    width: 42
                    height: 13
                    rotation: -2
                    color: Theme.ink(229, 209, 166, .72)
                }
            }
        }

        Label {
            Layout.alignment: Qt.AlignHCenter
            text: "LOCAL · REALTIME · PRIVATE"
            color: Theme.heroKicker
            font.pixelSize: 9
            font.weight: 750
            font.letterSpacing: 1.44
        }
        Label {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 13
            Layout.bottomMargin: 14
            horizontalAlignment: Text.AlignHCenter
            text: "강의가 끝날 때까지\n기억은 Clova에게 맡기세요."
            color: Theme.heroText
            font.pixelSize: 43
            font.weight: 700
            font.letterSpacing: -1.9
            lineHeightMode: Text.FixedHeight
            lineHeight: 49
        }
        Label {
            Layout.fillWidth: true
            Layout.maximumWidth: 570
            Layout.alignment: Qt.AlignHCenter
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "Whisper Large-v3가 강의 음성을 로컬에서 전사합니다. 원본 음성과 타임라인은 그대로 보존되며, 전사는 하나의 기본 색상으로 표시됩니다."
            color: Theme.heroSub
            font.pixelSize: 12
            lineHeightMode: Text.FixedHeight
            lineHeight: 21
        }

        PaperButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 27
            implicitWidth: 164
            implicitHeight: 43
            radius: 11
            tape: true
            tilt: -0.18
            onClicked: empty.newSessionRequested()
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 16
                Label {
                    Layout.fillWidth: true
                    text: "새 세션 시작"
                    color: Theme.notebook ? Theme.paperText : Theme.text
                    font.pixelSize: 11
                    font.weight: 680
                }
                Label {
                    text: "→"
                    color: Theme.notebook ? Theme.paperText : Theme.text
                    font.pixelSize: 13
                }
            }
        }

        Row {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 38
            spacing: 22
            Repeater {
                model: [["01", "Whisper Large-v3"], ["02", "원문 오디오 보존"], ["03", "Live Preview + Word Seek"]]
                Row {
                    required property var modelData
                    spacing: 6
                    Label { anchors.verticalCenter: parent.verticalCenter; text: parent.modelData[0]; color: "#858f9d"; font.pixelSize: 8 }
                    Label { anchors.verticalCenter: parent.verticalCenter; text: parent.modelData[1]; color: Theme.heroSub; font.pointSize: Theme.pt(9.5) }
                }
            }
        }
    }
}
