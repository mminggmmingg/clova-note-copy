import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Left column: brand, new session, search, semester -> subject -> lecture tree,
// runtime footer with theme toggle and app quit. Mirrors .sidebar in
// web/app_v6.css (all three themes).
Rectangle {
    id: sidebar

    // [{semester, subjects: [{key, emoji, name, professor, sessions: [...]}]}]
    property var groups: []
    property string currentSessionId: ""
    property var collapsed: ({})

    signal sessionClicked(string sessionId)
    signal searchEdited(string text)
    signal collapseRequested()
    signal newSessionRequested()
    signal newSubjectRequested()
    signal quitRequested()
    signal themeCycled()

    gradient: Gradient {
        GradientStop { position: 0; color: Theme.sidebarTop }
        GradientStop { position: 1; color: Theme.sidebarBottom }
    }

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.headerLine
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

            Item {
                width: 32
                height: 32
                rotation: Theme.notebook ? -0.8 : 0
                Rectangle {
                    visible: Theme.notebook
                    anchors.fill: parent
                    anchors.topMargin: 2
                    anchors.bottomMargin: -2
                    radius: 10
                    color: Theme.ink(180, 150, 112, .14)
                }
                Rectangle {
                    id: mark
                    anchors.fill: parent
                    topLeftRadius: Theme.notebook ? 9 : 10
                    topRightRadius: Theme.notebook ? 12 : 10
                    bottomRightRadius: 10
                    bottomLeftRadius: Theme.notebook ? 8 : 10
                    border.color: Theme.notebook ? "#ddcfbb" : Theme.ink(143, 155, 255, .23)
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Theme.notebook ? "#fffdf7" : Theme.ink(124, 140, 255, .22) }
                        GradientStop { position: 1; color: Theme.notebook ? "#f7eddf" : Theme.ink(169, 121, 255, .10) }
                    }
                    Row {
                        anchors.centerIn: parent
                        spacing: 2
                        Repeater {
                            model: [[8, "#d98778"], [16, "#c59a54"], [11, "#7fa18a"]]
                            Rectangle {
                                required property var modelData
                                anchors.verticalCenter: parent.verticalCenter
                                width: 3
                                height: modelData[0]
                                radius: 1.5
                                color: Theme.notebook ? modelData[1] : Theme.accent
                            }
                        }
                    }
                }
                Tape {
                    visible: Theme.notebook
                    x: 8
                    y: -4
                    width: 17
                    height: 6
                    rotation: 2
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4
                Label {
                    text: "Local Clova"
                    color: Theme.brandStrong
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
                    wrapMode: Text.WordWrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
            }

            PaperButton {
                icon: "chevron-left"
                iconSize: 16
                onClicked: sidebar.collapseRequested()
            }
        }

        // New session
        PaperButton {
            Layout.fillWidth: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 4
            Layout.bottomMargin: 14
            implicitHeight: 46
            fillWidth: true
            radius: 12
            tape: true
            tilt: -0.18
            onClicked: sidebar.newSessionRequested()
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10
                Rectangle {
                    width: 23
                    height: 23
                    radius: 7
                    color: Theme.notebook ? "#f2e6d4" : Theme.ink(255, 255, 255, .08)
                    Icon { anchors.centerIn: parent; name: "plus"; width: 14; height: 14; color: Theme.notebook ? "#736557" : Theme.text }
                }
                Label {
                    Layout.fillWidth: true
                    text: "새 세션"
                    color: Theme.notebook ? Theme.paperText : Theme.text
                    font.pixelSize: 16
                    font.weight: 650
                }
                Rectangle {
                    implicitWidth: kbd.implicitWidth + 12
                    implicitHeight: 16
                    radius: 5
                    color: Theme.notebook ? "#f2e6d4" : Theme.ink(255, 255, 255, .055)
                    border.color: Theme.notebook ? Theme.ink(124, 96, 63, .12) : Theme.line
                    Label {
                        id: kbd
                        anchors.centerIn: parent
                        text: "Ctrl N"
                        color: Theme.notebook ? "#736557" : Theme.muted2
                        font.pixelSize: 9
                        font.weight: 650
                    }
                }
            }
        }

        // Search
        Rectangle {
            Layout.fillWidth: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.bottomMargin: 15
            implicitHeight: 38
            radius: 10
            color: searchField.activeFocus && !Theme.notebook ? Theme.ink(124, 140, 255, .04) : Theme.searchBg
            border.color: searchField.activeFocus ? Theme.ink(185, 138, 73, .38) : Theme.searchBorder

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 8
                Icon { name: "search"; color: Theme.muted2; width: 15; height: 15 }
                TextField {
                    id: searchField
                    Layout.fillWidth: true
                    placeholderText: "세션, 태그 검색"
                    placeholderTextColor: Theme.placeholder
                    color: Theme.text
                    font.pixelSize: 12
                    background: null
                    padding: 0
                    onTextChanged: sidebar.searchEdited(text)
                }
            }
        }

        // Library label + new subject
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 17
            Layout.rightMargin: 17
            Layout.preferredHeight: 28
            Label {
                Layout.fillWidth: true
                text: "수업 라이브러리"
                color: Theme.labelRow
                font.pixelSize: 10
                font.weight: 700
                font.letterSpacing: 0.85
            }
            PaperButton {
                icon: "plus"
                iconSize: 12
                implicitWidth: 24
                implicitHeight: 24
                onClicked: sidebar.newSubjectRequested()
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

                                    Label {
                                        visible: subjectGroup.modelData.sessions.length === 0
                                        leftPadding: 31
                                        topPadding: 6
                                        bottomPadding: 10
                                        text: "아직 세션이 없습니다."
                                        color: Theme.pick("#505865", "#8a94a3", "#a09280")
                                        font.pixelSize: 10
                                    }

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
                                                GradientStop { position: 0; color: link.active ? Theme.activeFrom : (linkHover.hovered ? Theme.hover : "transparent") }
                                                GradientStop { position: 1; color: link.active ? Theme.activeTo : (linkHover.hovered ? Theme.hover : "transparent") }
                                            }
                                            HoverHandler { id: linkHover; cursorShape: Qt.PointingHandCursor }
                                            TapHandler { onTapped: sidebar.sessionClicked(link.modelData.sessionId) }

                                            // Dot (with a halo when active or recording)
                                            Rectangle {
                                                readonly property bool ring: link.active || link.modelData.recording
                                                x: 17 - (ring ? 3 : 0)
                                                y: 15 - (ring ? 3 : 0)
                                                width: ring ? 11 : 5
                                                height: width
                                                radius: width / 2
                                                color: link.modelData.recording ? Theme.ink(255, 109, 117, .12)
                                                     : link.active ? Qt.alpha(Theme.activeDot, .16) : "transparent"
                                                Rectangle {
                                                    anchors.centerIn: parent
                                                    width: 5
                                                    height: 5
                                                    radius: 2.5
                                                    color: link.modelData.recording ? Theme.red : link.active ? Theme.activeDot : Theme.sessionDot
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
                                                    font.pointSize: Theme.pt(11.5)
                                                    font.weight: link.active ? 560 : 400
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
            color: Theme.headerLine
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 18
            Layout.rightMargin: 14
            Layout.topMargin: 12
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
                    color: Qt.alpha(Theme.green, .2)
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
            PaperButton {
                implicitWidth: 31
                implicitHeight: 31
                iconSize: 16
                icon: Theme.notebook ? "notebook" : (Theme.dark ? "moon" : "sun")
                onClicked: sidebar.themeCycled()
            }
        }
        PaperButton {
            Layout.fillWidth: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 9
            Layout.bottomMargin: 15
            implicitHeight: 37
            fillWidth: true
            onClicked: sidebar.quitRequested()
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                spacing: 9
                Icon { name: "power"; width: 15; height: 15; color: Theme.notebook ? "#65584b" : Theme.muted }
                Label {
                    Layout.fillWidth: true
                    text: "앱 종료"
                    color: Theme.notebook ? "#65584b" : Theme.muted
                    font.pixelSize: 11
                }
            }
        }
    }
}
