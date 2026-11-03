import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// 종이 노트: the library on the paper ground, the lecture as a white page
// (title and meta scroll with the text), and a dark recording pill — or a
// playback pill — floating under the page.
Item {
    id: layout
    required property var app
    property alias transcript: tv
    readonly property bool recPill: app.recording
    readonly property bool playPill: !app.recording && app.session !== null && app.hasAudio

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            visible: layout.app.sidebarOpen
            Layout.preferredWidth: 268
            Layout.fillHeight: true
            app: layout.app
        }

        Item {
            id: main
            Layout.fillWidth: true
            Layout.fillHeight: true

            ActionButton {
                visible: !layout.app.sidebarOpen
                x: 16
                y: 18
                variant: "ghost"
                icon: "sidebar"
                iconSize: 18
                accessibleName: "사이드바 열기"
                onClicked: layout.app.sidebarOpen = true
            }

            // The page, with a flat drop under it (no blur effect).
            Rectangle {
                anchors.fill: page
                anchors.topMargin: 4
                anchors.bottomMargin: -4
                radius: 18
                color: Theme.ink(60, 50, 30, .05)
            }
            Rectangle {
                id: page
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.topMargin: 16
                anchors.bottomMargin: layout.recPill || layout.playPill ? 100 : 20
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(820, parent.width - (layout.app.sidebarOpen ? 40 : 140))
                radius: 16
                color: Theme.surface
                border.color: Theme.surfaceLine

                EmptyState {
                    anchors.fill: parent
                    visible: layout.app.sessionId === ""
                    onNewSessionRequested: layout.app.openNewSession()
                }
                Label {
                    anchors.centerIn: parent
                    visible: layout.app.sessionId !== "" && layout.app.session === null && layout.app.errorText === ""
                    text: "불러오는 중…"
                    color: Theme.muted
                    font.pixelSize: 14
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 1
                    spacing: 0
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 40
                        Layout.rightMargin: 40
                        Layout.topMargin: visible ? 18 : 0
                        visible: layout.app.captureWarning !== "" || layout.app.errorText !== ""
                        spacing: 8
                        Banner { Layout.fillWidth: true; text: layout.app.captureWarning }
                        Banner {
                            Layout.fillWidth: true
                            tone: "warn"
                            text: layout.app.errorText
                            actionText: "다시 시도"
                            onAction: layout.app.retry()
                        }
                    }
                    TranscriptView {
                        id: tv
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: layout.app.session !== null
                        app: layout.app
                        sidePadding: 56
                        maxColumn: 708
                        bottomMargin: 48
                        header: pageHeader
                    }
                }
            }

            // Recording pill
            Item {
                visible: layout.recPill
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 26
                width: recRow.implicitWidth + 26
                height: 52
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: 6
                    anchors.bottomMargin: -6
                    radius: height / 2
                    color: Theme.ink(30, 25, 15, .14)
                }
                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    color: "#24211C"
                    Accessible.role: Accessible.StatusBar
                    Accessible.name: "녹음 상태"
                }
                RowLayout {
                    id: recRow
                    anchors.verticalCenter: parent.verticalCenter
                    x: 18
                    spacing: 14
                    Rectangle {
                        implicitWidth: 9
                        implicitHeight: 9
                        radius: 4.5
                        color: "#E5574B"
                        // Flips with each status poll instead of animating.
                        opacity: layout.app.blink || layout.app.captureWarning !== "" ? 1 : 0.45
                    }
                    Label {
                        text: layout.app.captureWarning !== "" ? "확인 필요" : "녹음 중"
                        color: "#F6F3ED"
                        font.pixelSize: 14
                        font.weight: 600
                    }
                    Label {
                        text: layout.app.clock(layout.app.recordingSec)
                        color: "#F6F3ED"
                        font.pixelSize: 15
                        font.weight: 600
                        font.features: { "tnum": 1 }
                    }
                    LevelMeter {
                        implicitWidth: 57
                        implicitHeight: 22
                        levels: layout.app.levels
                        color: "#A9C7A0"
                    }
                    Label {
                        text: layout.app.micText
                        color: layout.app.captureWarning !== "" ? "#FF9A8F" : "#CFC9BD"
                        font.pixelSize: 13
                    }
                    Rectangle {
                        implicitWidth: stopRow.implicitWidth + 30
                        implicitHeight: 36
                        radius: 18
                        color: stopHover.hovered ? "#FFFFFF" : "#F6F3ED"
                        opacity: layout.app.actionBusy ? 0.6 : 1
                        Accessible.role: Accessible.Button
                        Accessible.name: "녹음 정지"
                        Row {
                            id: stopRow
                            anchors.centerIn: parent
                            spacing: 7
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 10
                                height: 10
                                radius: 2
                                color: "#C8443A"
                            }
                            Label {
                                text: layout.app.actionBusy ? "정지 중…" : "정지"
                                color: "#24211C"
                                font.pixelSize: 14
                                font.weight: 600
                            }
                        }
                        HoverHandler { id: stopHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: layout.app.stopRecording() }
                    }
                }
            }

            // Playback pill
            Item {
                visible: layout.playPill
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 26
                width: Math.min(580, parent.width - 48)
                height: 56
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: 5
                    anchors.bottomMargin: -5
                    radius: height / 2
                    color: Theme.ink(30, 25, 15, .08)
                }
                Rectangle {
                    anchors.fill: parent
                    radius: height / 2
                    color: "#FFFFFF"
                    border.color: "#E3DDD2"
                }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 10
                    spacing: 12
                    Rectangle {
                        implicitWidth: 40
                        implicitHeight: 40
                        radius: 20
                        color: playHover.hovered ? "#3A352D" : "#24211C"
                        Accessible.role: Accessible.Button
                        Accessible.name: layout.app.audioRunning ? "일시정지" : "재생"
                        Icon {
                            anchors.centerIn: parent
                            anchors.horizontalCenterOffset: layout.app.audioRunning ? 0 : 1
                            width: 16
                            height: 16
                            name: layout.app.audioRunning ? "pause" : "play"
                            color: "#F6F3ED"
                        }
                        HoverHandler { id: playHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: layout.app.togglePlayback() }
                    }
                    Label {
                        text: layout.app.clock(layout.app.playheadSec)
                        color: Theme.text
                        font.pixelSize: 14
                        font.weight: 600
                        font.features: { "tnum": 1 }
                    }
                    Scrubber {
                        Layout.fillWidth: true
                        value: layout.app.lectureEnd > 0 ? layout.app.playheadSec / layout.app.lectureEnd : 0
                        trackColor: "#EAE4D9"
                        fillColor: "#24211C"
                        onSeek: f => layout.app.seekLecture(f * layout.app.lectureEnd)
                    }
                    Label {
                        text: layout.app.clock(layout.app.lectureEnd)
                        color: Theme.muted
                        font.pixelSize: 13
                        font.features: { "tnum": 1 }
                    }
                    ActionButton {
                        implicitHeight: 32
                        radius: 8
                        text: layout.app.rateText
                        fontPx: 13
                        accessibleName: "재생 속도 " + layout.app.rateText
                        onClicked: layout.app.cycleRate()
                    }
                }
            }
        }
    }

    // Title, meta and PDFs at the top of the page; they scroll with the text.
    Component {
        id: pageHeader
        ColumnLayout {
            width: tv.columnWidth
            spacing: 0
            readonly property var s: layout.app.session
            readonly property var subject: s ? layout.app.subjectOf(s.subject_id) : null

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 38
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Label {
                        Layout.fillWidth: true
                        text: subject ? subject.name + (subject.semester ? " · " + subject.semester.replace(/^(\d{4})-(\d)$/, "$1-$2학기") : "") : "미분류"
                        color: Theme.muted
                        font.pixelSize: 13
                        elide: Text.ElideRight
                    }
                    Label {
                        Layout.fillWidth: true
                        Layout.topMargin: 6
                        text: s ? s.title : ""
                        color: Theme.heading
                        font.family: Theme.serifFamily
                        font.pixelSize: 32
                        font.weight: 600
                        font.letterSpacing: -0.6
                        wrapMode: Text.Wrap
                    }
                    Flow {
                        Layout.fillWidth: true
                        Layout.topMargin: 14
                        spacing: 10
                        Label {
                            height: 28
                            verticalAlignment: Text.AlignVCenter
                            text: layout.app.sessionMeta
                            color: Theme.muted
                            font.pixelSize: 13
                        }
                        Repeater {
                            model: layout.app.pdfs
                            delegate: Rectangle {
                                id: chip
                                required property var modelData
                                width: chipRow.implicitWidth + 20
                                height: 28
                                radius: 7
                                color: chipHover.hovered ? Theme.control : Theme.chip
                                Accessible.role: Accessible.Link
                                Accessible.name: modelData.original_filename || "PDF"
                                Row {
                                    id: chipRow
                                    anchors.centerIn: parent
                                    spacing: 6
                                    Icon { anchors.verticalCenter: parent.verticalCenter; name: "file"; width: 14; height: 14; color: Theme.subtle }
                                    Label { text: chip.modelData.original_filename || "PDF"; color: Theme.subtle; font.pixelSize: 13 }
                                }
                                HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: layout.app.notYet("PDF 보기와 필기") }
                            }
                        }
                        ActionButton {
                            implicitHeight: 28
                            radius: 7
                            variant: "ghost"
                            icon: "plus"
                            iconSize: 13
                            text: "자료 추가"
                            fontPx: 13
                            fontWeight: 400
                            onClicked: layout.app.notYet("PDF 추가")
                        }
                    }
                }
                ActionButton {
                    Layout.alignment: Qt.AlignTop
                    visible: s !== null && !layout.app.recording
                    implicitHeight: 34
                    icon: "play"
                    iconSize: 11
                    text: layout.app.actionBusy ? "재개 중…" : "이어서 녹음"
                    fontPx: 13
                    dimmed: layout.app.actionBusy || layout.app.pendingCount > 0
                    onClicked: layout.app.resumeClicked()
                }
                ActionButton {
                    id: infoButton
                    Layout.alignment: Qt.AlignTop
                    variant: "ghost"
                    icon: "info"
                    iconSize: 19
                    accessibleName: "세션 정보"
                    onClicked: layout.app.showInfo(infoButton)
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.topMargin: 28
                Layout.bottomMargin: 14
                implicitHeight: 1
                color: Theme.line
            }
        }
    }
}
