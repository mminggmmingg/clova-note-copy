import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Classic theme, first pane: semesters and their subjects with a letter badge.
Rectangle {
    id: pane
    required property var app
    color: Theme.sidebarBg

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.sidebarLine
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: 18
        anchors.bottomMargin: 14
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        spacing: 6

        RowLayout {
            Layout.leftMargin: 8
            Layout.bottomMargin: 10
            spacing: 9
            BrandMark { size: 24 }
            Label {
                text: "Local Clova"
                color: Theme.text
                font.pixelSize: 15
                font.weight: 700
            }
        }

        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: scroll.availableWidth
                spacing: 2

                Repeater {
                    model: pane.app.subjectIndex
                    delegate: Column {
                        id: semesterGroup
                        required property var modelData
                        required property int index
                        width: parent.width
                        spacing: 2

                        Label {
                            leftPadding: 8
                            topPadding: semesterGroup.index === 0 ? 4 : 16
                            bottomPadding: 4
                            text: semesterGroup.modelData.semester === "기타" ? "기타" : semesterGroup.modelData.semester.replace(/^(\d{4})-(\d)$/, "$1-$2학기")
                            color: Theme.muted
                            font.pixelSize: 12
                            font.weight: 600
                        }

                        Repeater {
                            model: semesterGroup.modelData.subjects
                            delegate: Rectangle {
                                id: item
                                required property var modelData
                                readonly property bool current: modelData.key === pane.app.selectedSubject
                                width: semesterGroup.width
                                height: 36
                                radius: 9
                                color: current ? Theme.selected : (hover.hovered ? Theme.hover : "transparent")
                                Accessible.role: Accessible.Button
                                Accessible.name: modelData.name
                                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: pane.app.selectedSubject = item.modelData.key }
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    spacing: 10
                                    Rectangle {
                                        implicitWidth: 20
                                        implicitHeight: 20
                                        radius: 6
                                        color: Theme.subjectColor(item.modelData.key)
                                        Label {
                                            anchors.centerIn: parent
                                            text: String(item.modelData.name || "?").charAt(0)
                                            color: "#FFFFFF"
                                            font.pixelSize: 11
                                            font.weight: 700
                                        }
                                    }
                                    Label {
                                        Layout.fillWidth: true
                                        text: item.modelData.name
                                        color: Theme.text
                                        font.pixelSize: 14
                                        font.weight: item.current ? 600 : 400
                                        elide: Text.ElideRight
                                    }
                                    Label {
                                        text: item.modelData.count
                                        color: Theme.muted
                                        font.pixelSize: 13
                                    }
                                }
                            }
                        }
                    }
                }

                ActionButton {
                    width: parent.width
                    implicitHeight: 36
                    fillWidth: true
                    alignLeft: true
                    variant: "ghost"
                    icon: "plus"
                    iconSize: 18
                    text: "과목 추가"
                    fontWeight: 400
                    onClicked: pane.app.openSubjectDialog()
                }
            }
        }

        SidebarFooter {
            Layout.fillWidth: true
            app: pane.app
        }
    }
}
