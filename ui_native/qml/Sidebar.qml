import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Left column: brand, search, semester -> subject -> lecture tree, runtime
// footer. Mirrors .sidebar in web/app_v6.css.
Rectangle {
    id: sidebar

    // [{semester, subjects: [{key, emoji, name, professor, sessions: [...]}]}]
    property var groups: []
    property string currentSessionId: ""
    property var collapsed: ({})

    signal sessionClicked(string sessionId)
    signal searchEdited(string text)

    gradient: Gradient {
        GradientStop { position: 0; color: Theme.sidebarTop }
        GradientStop { position: 1; color: Theme.sidebarBottom }
    }

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.line
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.rightMargin: 1
        spacing: 0

        // Brand
        RowLayout {
            Layout.preferredHeight: 72
            Layout.leftMargin: 18
            Layout.rightMargin: 16
            spacing: 11

            Rectangle {
                width: 32
                height: 32
                radius: 10
                border.color: Theme.ink(143, 155, 255, .23)
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: Theme.ink(124, 140, 255, .22) }
                    GradientStop { position: 1; color: Theme.ink(169, 121, 255, .10) }
                }
                Row {
                    anchors.centerIn: parent
                    spacing: 2
                    Repeater {
                        model: [8, 16, 11]
                        Rectangle {
                            required property int modelData
                            anchors.verticalCenter: parent.verticalCenter
                            width: 3
                            height: modelData
                            radius: 1.5
                            gradient: Gradient {
                                GradientStop { position: 0; color: Theme.accent }
                                GradientStop { position: 1; color: "#b8c0ff" }
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Local Clova"
                    color: Theme.text
                    font.pixelSize: 14
                    font.weight: 700
                    font.letterSpacing: -0.14
                }
                Label {
                    Layout.fillWidth: true
                    text: "LECTURE INTELLIGENCE · V8.3 NATIVE"
                    color: Theme.brandSub
                    font.pixelSize: 10
                    font.letterSpacing: 0.8
                    elide: Text.ElideRight
                }
            }
        }

        // Search
        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 4
            Layout.bottomMargin: 15
            implicitHeight: 38
            radius: 10
            color: searchField.activeFocus ? Theme.ink(124, 140, 255, .04) : Theme.searchBg
            border.color: searchField.activeFocus ? Theme.ink(124, 140, 255, .38) : Theme.line

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 8
                Icon { name: "search"; color: Theme.muted2; width: 15; height: 15 }
                TextField {
                    id: searchField
                    Layout.fillWidth: true
                    placeholderText: "세션 검색"
                    placeholderTextColor: Theme.placeholder
                    color: Theme.text
                    font.pixelSize: 12
                    background: null
                    padding: 0
                    onTextChanged: sidebar.searchEdited(text)
                }
            }
        }

        // Library label
        Label {
            Layout.fillWidth: true
            Layout.leftMargin: 17
            Layout.preferredHeight: 28
            verticalAlignment: Text.AlignVCenter
            text: "수업 라이브러리"
            color: Theme.labelRow
            font.pixelSize: 10
            font.weight: 700
            font.letterSpacing: 0.85
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
                leftPadding: 9
                rightPadding: 9
                bottomPadding: 16

                Repeater {
                    model: sidebar.groups
                    delegate: Column {
                        id: semesterGroup
                        required property var modelData
                        width: parent.width - 18

                        Label {
                            width: parent.width
                            topPadding: 14
                            bottomPadding: 6
                            leftPadding: 8
                            text: semesterGroup.modelData.semester
                            color: Theme.semester
                            font.pixelSize: 10
                            font.weight: 700
                            font.letterSpacing: 0.8
                        }

                        Repeater {
                            model: semesterGroup.modelData.subjects
                            delegate: Column {
                                id: subjectGroup
                                required property var modelData
                                readonly property bool isCollapsed: !!sidebar.collapsed[modelData.key]
                                width: semesterGroup.width
                                bottomPadding: 4

                                // Subject header (tap to collapse)
                                Rectangle {
                                    width: parent.width
                                    height: 34 + (subjectGroup.modelData.professor ? 8 : 0)
                                    radius: 8
                                    color: subjectHover.hovered ? Theme.hover : "transparent"
                                    HoverHandler { id: subjectHover }
                                    TapHandler {
                                        onTapped: {
                                            const next = Object.assign({}, sidebar.collapsed)
                                            next[subjectGroup.modelData.key] = !subjectGroup.isCollapsed
                                            sidebar.collapsed = next
                                        }
                                    }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 7
                                        anchors.rightMargin: 7
                                        spacing: 8
                                        Icon {
                                            name: "chevron"
                                            color: Theme.chevron
                                            width: 13
                                            height: 13
                                            rotation: subjectGroup.isCollapsed ? -90 : 0
                                            Behavior on rotation { NumberAnimation { duration: 180 } }
                                        }
                                        Label {
                                            Layout.preferredWidth: 22
                                            horizontalAlignment: Text.AlignHCenter
                                            text: subjectGroup.modelData.emoji
                                            font.pixelSize: 14
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 1
                                            Label {
                                                Layout.fillWidth: true
                                                text: subjectGroup.modelData.name
                                                color: subjectHover.hovered ? Theme.text : Theme.subjectName
                                                font.pixelSize: 12
                                                font.weight: 650
                                                elide: Text.ElideRight
                                            }
                                            Label {
                                                visible: !!subjectGroup.modelData.professor
                                                Layout.fillWidth: true
                                                text: subjectGroup.modelData.professor || ""
                                                color: Theme.subjectSub
                                                font.pixelSize: 9
                                                font.weight: 560
                                                elide: Text.ElideRight
                                            }
                                        }
                                        Label {
                                            text: subjectGroup.modelData.sessions.length
                                            color: Theme.subjectCount
                                            font.pixelSize: 9
                                        }
                                    }
                                }

                                // Lectures
                                Column {
                                    visible: !subjectGroup.isCollapsed
                                    width: parent.width
                                    leftPadding: 7

                                    Repeater {
                                        model: subjectGroup.modelData.sessions
                                        delegate: Rectangle {
                                            id: link
                                            required property var modelData
                                            readonly property bool active: modelData.sessionId === sidebar.currentSessionId
                                            width: subjectGroup.width - 7
                                            height: Math.max(48, linkText.implicitHeight + 14)
                                            radius: 9
                                            gradient: Gradient {
                                                orientation: Gradient.Horizontal
                                                GradientStop { position: 0; color: link.active ? Theme.ink(124, 140, 255, .13) : (linkHover.hovered ? Theme.hover : "transparent") }
                                                GradientStop { position: 1; color: link.active ? Theme.ink(124, 140, 255, .035) : (linkHover.hovered ? Theme.hover : "transparent") }
                                            }
                                            HoverHandler { id: linkHover; cursorShape: Qt.PointingHandCursor }
                                            TapHandler { onTapped: sidebar.sessionClicked(link.modelData.sessionId) }

                                            // Dot (accent with halo when active, red when recording)
                                            Rectangle {
                                                x: 17 - (link.active || link.modelData.recording ? 3 : 0)
                                                y: 15 - (link.active || link.modelData.recording ? 3 : 0)
                                                width: link.active || link.modelData.recording ? 11 : 5
                                                height: width
                                                radius: width / 2
                                                color: link.modelData.recording ? Theme.ink(255, 109, 117, .12)
                                                     : link.active ? Theme.ink(124, 140, 255, .11) : "transparent"
                                                Rectangle {
                                                    anchors.centerIn: parent
                                                    width: 5
                                                    height: 5
                                                    radius: 2.5
                                                    color: link.modelData.recording ? Theme.red : link.active ? Theme.accent : Theme.sessionDot
                                                }
                                            }

                                            Column {
                                                id: linkText
                                                anchors.left: parent.left
                                                anchors.right: parent.right
                                                anchors.leftMargin: 31
                                                anchors.rightMargin: 9
                                                anchors.verticalCenter: parent.verticalCenter
                                                spacing: 4
                                                Label {
                                                    width: parent.width
                                                    text: link.modelData.title
                                                    color: link.active ? Theme.sessionTitleActive : Theme.sessionTitle
                                                    font.pointSize: 8.625
                                                    font.weight: 540
                                                    elide: Text.ElideRight
                                                }
                                                Label {
                                                    width: parent.width
                                                    text: link.modelData.meta
                                                    color: Theme.sessionMeta
                                                    font.pixelSize: 9
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // Footer
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 1
            color: Theme.line
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 18
            Layout.topMargin: 14
            Layout.bottomMargin: 17
            spacing: 7
            Rectangle {
                width: 6
                height: 6
                radius: 3
                color: Theme.green
                Rectangle {
                    anchors.centerIn: parent
                    width: 14
                    height: 14
                    radius: 7
                    color: Theme.ink(94, 214, 160, .18)
                    z: -1
                }
            }
            Label {
                Layout.fillWidth: true
                text: "On-device · Private"
                color: Theme.runtime
                font.pixelSize: 9
                font.letterSpacing: 0.3
            }
            // Theme toggle (dark <-> light), like the web footer button.
            Rectangle {
                Layout.rightMargin: 14
                width: 30
                height: 30
                radius: 9
                color: themeHover.hovered ? Theme.hover : "transparent"
                border.color: Theme.line
                Label {
                    anchors.centerIn: parent
                    text: Theme.dark ? "☾" : "☀"
                    color: Theme.muted
                    font.pixelSize: 14
                }
                HoverHandler { id: themeHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: Theme.override = Theme.dark ? "light" : "dark" }
            }
        }
    }
}
