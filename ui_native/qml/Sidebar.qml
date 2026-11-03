import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Library tree for the paper and studio themes: brand, 새 녹음, search, then
// semester -> subject -> lecture, and a footer with settings and quit.
Rectangle {
    id: sidebar

    required property var app
    property var collapsed: ({})
    property bool searchOpen: Theme.paper || app.search !== ""

    color: Theme.sidebarBg

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: Theme.sidebarLine
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: Theme.pick(20, 14, 18)
        anchors.bottomMargin: Theme.pick(14, 12, 14)
        anchors.leftMargin: Theme.pick(18, 10, 12)
        anchors.rightMargin: Theme.pick(14, 11, 12)
        spacing: Theme.pick(18, 14, 14)

        // Brand
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.studio ? 6 : 0
            spacing: 10
            BrandMark { size: Theme.studio ? 22 : 26 }
            Label {
                Layout.fillWidth: true
                text: "Local Clova"
                color: Theme.text
                font.pixelSize: Theme.studio ? 14 : 15
                font.weight: Theme.studio ? 600 : 700
                font.letterSpacing: -0.2
            }
            ActionButton {
                implicitHeight: Theme.studio ? 30 : 32
                variant: "ghost"
                icon: Theme.studio ? "search" : "sidebar"
                iconSize: Theme.studio ? 16 : 18
                accessibleName: Theme.studio ? "검색" : "사이드바 접기"
                onClicked: {
                    if (Theme.studio) {
                        sidebar.searchOpen = !sidebar.searchOpen
                        if (sidebar.searchOpen) Qt.callLater(() => searchField.focusInput())
                        else { searchField.text = ""; sidebar.app.search = "" }
                    } else {
                        sidebar.app.sidebarOpen = false
                    }
                }
            }
        }

        ActionButton {
            Layout.fillWidth: true
            implicitHeight: Theme.studio ? 34 : 40
            fillWidth: true
            alignLeft: true
            icon: Theme.studio ? "" : "plus"
            dotColor: Theme.studio ? Theme.rec : "transparent"
            text: "새 녹음"
            hint: "Ctrl N"
            fontPx: Theme.studio ? 13 : 14
            fontWeight: Theme.studio ? 500 : 600
            onClicked: sidebar.app.openNewSession()
        }

        SearchField {
            id: searchField
            Layout.fillWidth: true
            visible: sidebar.searchOpen
            placeholder: "강의, 태그 검색"
            text: sidebar.app.search
            onEdited: text => sidebar.app.search = text
        }

        ScrollView {
            id: scroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.topMargin: -4
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            Column {
                width: scroll.availableWidth
                spacing: Theme.studio ? 1 : 2

                Repeater {
                    model: sidebar.app.libraryGroups
                    delegate: Column {
                        id: semesterGroup
                        required property var modelData
                        required property int index
                        width: parent.width
                        spacing: Theme.studio ? 1 : 2

                        Label {
                            width: parent.width
                            topPadding: semesterGroup.index === 0 ? 4 : 14
                            bottomPadding: Theme.studio ? 6 : 4
                            leftPadding: 8
                            text: semesterGroup.modelData.semester === "기타" ? "기타" : semesterGroup.modelData.semester.replace(/^(\d{4})-(\d)$/, "$1-$2학기")
                            color: Theme.muted
                            font.pixelSize: Theme.studio ? 11 : 12
                            font.weight: Theme.studio ? 500 : 600
                            font.letterSpacing: Theme.studio ? 0.3 : 0
                        }

                        Repeater {
                            model: semesterGroup.modelData.subjects
                            delegate: Column {
                                id: subjectGroup
                                required property var modelData
                                readonly property bool isCollapsed: !!sidebar.collapsed[modelData.key]
                                    || (sidebar.collapsed[modelData.key] === undefined && !modelData.hasCurrent && sidebar.app.search === "")
                                width: semesterGroup.width
                                spacing: Theme.studio ? 1 : 2

                                // Subject row (tap to fold)
                                Rectangle {
                                    width: parent.width
                                    height: Theme.studio ? 30 : 34
                                    radius: Theme.studio ? 6 : 8
                                    color: subjectHover.hovered ? Theme.hover : "transparent"
                                    Accessible.role: Accessible.Button
                                    Accessible.name: subjectGroup.modelData.name + (subjectGroup.isCollapsed ? " 펼치기" : " 접기")
                                    HoverHandler { id: subjectHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler {
                                        onTapped: {
                                            const next = Object.assign({}, sidebar.collapsed)
                                            next[subjectGroup.modelData.key] = !subjectGroup.isCollapsed
                                            sidebar.collapsed = next
                                        }
                                    }
                                    RowLayout {
                                        anchors.fill: parent
                                        anchors.leftMargin: 8
                                        anchors.rightMargin: 8
                                        spacing: Theme.studio ? 9 : 8
                                        Icon {
                                            visible: !Theme.studio
                                            name: subjectGroup.isCollapsed ? "chevron-right" : "chevron"
                                            color: Theme.muted
                                            stroke: 2
                                            implicitWidth: 14
                                            implicitHeight: 14
                                        }
                                        Rectangle {
                                            visible: Theme.studio
                                            implicitWidth: 9
                                            implicitHeight: 9
                                            radius: 3
                                            color: Theme.subjectColor(subjectGroup.modelData.key)
                                        }
                                        Label {
                                            Layout.fillWidth: true
                                            text: subjectGroup.modelData.name
                                            color: subjectGroup.isCollapsed ? Theme.subtle : Theme.text
                                            font.pixelSize: Theme.studio ? 13 : 14
                                            font.weight: !subjectGroup.isCollapsed && Theme.paper ? 600 : 400
                                            elide: Text.ElideRight
                                        }
                                        Label {
                                            text: subjectGroup.modelData.sessions.length
                                            color: Theme.muted
                                            font.pixelSize: Theme.studio ? 11 : 12
                                        }
                                    }
                                }

                                // Lectures
                                Column {
                                    visible: !subjectGroup.isCollapsed
                                    width: parent.width
                                    leftPadding: Theme.studio ? 0 : 22
                                    spacing: Theme.studio ? 1 : 2

                                    Label {
                                        visible: subjectGroup.modelData.sessions.length === 0
                                        leftPadding: Theme.studio ? 41 : 25
                                        topPadding: 6
                                        bottomPadding: 8
                                        text: "아직 강의가 없습니다"
                                        color: Theme.muted
                                        font.pixelSize: 12
                                    }

                                    Repeater {
                                        model: subjectGroup.modelData.sessions
                                        delegate: Rectangle {
                                            id: link
                                            required property var modelData
                                            readonly property bool active: modelData.sessionId === sidebar.app.sessionId
                                            readonly property bool marked: active || modelData.recording
                                            width: subjectGroup.width - (Theme.studio ? 0 : 22)
                                            height: Theme.studio ? 30 : (active ? 36 : 34)
                                            radius: Theme.studio ? 6 : 8
                                            color: active ? Theme.selected : (linkHover.hovered ? Theme.hover : "transparent")
                                            Accessible.role: Accessible.Link
                                            Accessible.name: modelData.title
                                            HoverHandler { id: linkHover; cursorShape: Qt.PointingHandCursor }
                                            TapHandler { onTapped: sidebar.app.openSession(link.modelData.sessionId) }

                                            // Paper: the active card's soft shadow.
                                            Rectangle {
                                                visible: link.active && Theme.paper
                                                z: -1
                                                anchors.fill: parent
                                                anchors.topMargin: 1
                                                anchors.bottomMargin: -1
                                                radius: parent.radius
                                                color: Theme.ink(60, 50, 30, .07)
                                            }

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: link.marked ? (Theme.studio ? 26 : 10) : (Theme.studio ? 41 : 25)
                                                anchors.rightMargin: Theme.studio ? 8 : 10
                                                spacing: Theme.studio ? 9 : 8
                                                Rectangle {
                                                    visible: link.marked
                                                    implicitWidth: Theme.studio ? 6 : 7
                                                    implicitHeight: implicitWidth
                                                    radius: implicitWidth / 2
                                                    color: link.modelData.recording ? Theme.rec : Theme.accent
                                                }
                                                Label {
                                                    Layout.fillWidth: true
                                                    text: link.modelData.title
                                                    color: link.active ? Theme.heading : Theme.subtle
                                                    font.pixelSize: Theme.studio ? 13 : 14
                                                    font.weight: link.active && Theme.paper ? 600 : 400
                                                    elide: Text.ElideRight
                                                }
                                                Label {
                                                    text: link.modelData.recording ? (Theme.studio ? "REC" : "녹음 중") : link.modelData.date
                                                    color: link.modelData.recording ? Theme.recText : Theme.muted
                                                    font.pixelSize: Theme.studio ? 11 : 12
                                                    font.weight: link.modelData.recording && Theme.paper ? 600 : 400
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                ActionButton {
                    width: parent.width
                    implicitHeight: Theme.studio ? 30 : 34
                    fillWidth: true
                    alignLeft: true
                    variant: "ghost"
                    icon: "plus"
                    iconSize: 14
                    text: "과목 추가"
                    fontPx: Theme.studio ? 13 : 14
                    fontWeight: 400
                    onClicked: sidebar.app.openSubjectDialog()
                }
            }
        }

        SidebarFooter {
            Layout.fillWidth: true
            app: sidebar.app
        }
    }
}
