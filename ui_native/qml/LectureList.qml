import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Classic theme, second pane: the chosen subject's lectures, newest first.
Rectangle {
    id: pane
    required property var app
    readonly property var subject: app.subjectByKey(app.selectedSubject)
    readonly property var lectures: app.lecturesOf(app.selectedSubject)

    color: Theme.bg

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.paneLine
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 18
        anchors.leftMargin: 12
        anchors.rightMargin: 13
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.rightMargin: 8
            spacing: 10
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2
                Label {
                    Layout.fillWidth: true
                    text: pane.subject ? pane.subject.name : "강의"
                    color: Theme.heading
                    font.pixelSize: 20
                    font.weight: 700
                    font.letterSpacing: -0.3
                    elide: Text.ElideRight
                }
                Label {
                    text: "강의 " + pane.lectures.length + "개"
                    color: Theme.muted
                    font.pixelSize: 13
                }
            }
            // Round record button: a new lecture in this subject.
            Rectangle {
                implicitWidth: 38
                implicitHeight: 38
                radius: 19
                color: recHover.hovered ? Theme.hover : Theme.control
                Accessible.role: Accessible.Button
                Accessible.name: "새 녹음"
                Rectangle {
                    anchors.centerIn: parent
                    width: 14
                    height: 14
                    radius: 7
                    color: Theme.accent
                }
                HoverHandler { id: recHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: pane.app.openNewSessionIn(pane.app.selectedSubject) }
            }
        }

        SearchField {
            Layout.fillWidth: true
            Layout.margins: 8
            placeholder: "검색"
            text: pane.app.search
            onEdited: text => pane.app.search = text
        }

        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: pane.lectures
            boundsBehavior: Flickable.StopAtBounds
            spacing: 0
            ScrollBar.vertical: ScrollBar {
                contentItem: Rectangle { implicitWidth: 6; radius: 3; color: Theme.scrollbar; opacity: parent.size < 1 && parent.active ? 1 : 0 }
            }

            delegate: Item {
                id: card
                required property var modelData
                required property int index
                readonly property bool active: modelData.sessionId === pane.app.sessionId
                readonly property bool nextActive: index + 1 < pane.lectures.length && pane.lectures[index + 1].sessionId === pane.app.sessionId
                width: list.width
                height: cardBody.implicitHeight + 22

                Rectangle {
                    anchors.fill: parent
                    radius: 11
                    color: card.active ? Theme.chip : (hover.hovered ? Theme.rowHover : "transparent")
                }
                Rectangle {
                    visible: !card.active && !card.nextActive && card.index + 1 < pane.lectures.length
                    anchors.bottom: parent.bottom
                    x: 12
                    width: parent.width - 24
                    height: 1
                    color: Theme.line
                }
                Accessible.role: Accessible.Link
                Accessible.name: modelData.title
                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: pane.app.openSession(card.modelData.sessionId) }

                ColumnLayout {
                    id: cardBody
                    x: 12
                    y: 11
                    width: parent.width - 24
                    spacing: 3
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 7
                        Rectangle {
                            visible: card.modelData.recording
                            implicitWidth: 8
                            implicitHeight: 8
                            radius: 4
                            color: Theme.rec
                        }
                        Label {
                            Layout.fillWidth: true
                            text: card.modelData.title
                            color: Theme.heading
                            font.pixelSize: 15
                            font.weight: 600
                            elide: Text.ElideRight
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: card.modelData.recording ? "녹음 중" : [card.modelData.longDate, card.modelData.length].filter(x => x).join(" · ")
                        color: card.modelData.recording ? Theme.recText : Theme.muted
                        font.pixelSize: 13
                        font.weight: card.modelData.recording ? 600 : 400
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.fillWidth: true
                        visible: text !== ""
                        text: card.modelData.detail
                        color: Theme.muted
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }
                }
            }

            Label {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 24
                visible: pane.lectures.length === 0
                text: pane.app.search ? "검색 결과가 없습니다" : "아직 강의가 없습니다"
                color: Theme.muted
                font.pixelSize: 13
            }
        }
    }
}
