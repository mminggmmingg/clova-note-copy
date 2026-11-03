import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// 스튜디오: a dark workroom. Breadcrumb bar, a recording bar with the input
// level, the transcript beside a session info panel, and a transport bar for
// playback.
Item {
    id: layout
    required property var app
    property alias transcript: tv

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Sidebar {
            visible: layout.app.sidebarOpen
            Layout.preferredWidth: 240
            Layout.fillHeight: true
            app: layout.app
        }

        ColumnLayout {
            id: main
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // Breadcrumb bar
            Item {
                Layout.fillWidth: true
                implicitHeight: 52
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.paneLine }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: layout.app.sidebarOpen ? 20 : 10
                    anchors.rightMargin: 14
                    spacing: 10
                    ActionButton {
                        visible: !layout.app.sidebarOpen
                        implicitHeight: 30
                        variant: "ghost"
                        icon: "sidebar"
                        accessibleName: "사이드바 열기"
                        onClicked: layout.app.sidebarOpen = true
                    }
                    Label {
                        visible: layout.app.session !== null
                        text: {
                            const s = layout.app.session ? layout.app.subjectOf(layout.app.session.subject_id) : null
                            return s ? s.name : "미분류"
                        }
                        color: Theme.muted
                        font.pixelSize: 13
                    }
                    Icon {
                        visible: layout.app.session !== null
                        name: "chevron-right"
                        stroke: 2
                        color: "#5F5F67"
                        implicitWidth: 12
                        implicitHeight: 12
                    }
                    Label {
                        Layout.fillWidth: true
                        text: layout.app.session ? layout.app.session.title : "Local Clova"
                        color: Theme.text
                        font.pixelSize: 13
                        font.weight: 500
                        elide: Text.ElideRight
                    }
                    ActionButton {
                        visible: layout.app.session !== null && !layout.app.recording
                        implicitHeight: 30
                        radius: 7
                        dotColor: Theme.rec
                        text: layout.app.actionBusy ? "재개 중…" : "이어서 녹음"
                        fontPx: 12
                        fontWeight: 500
                        dimmed: layout.app.actionBusy || layout.app.pendingCount > 0
                        onClicked: layout.app.resumeClicked()
                    }
                    ActionButton {
                        visible: layout.app.session !== null
                        implicitHeight: 30
                        radius: 7
                        icon: "file"
                        iconSize: 14
                        text: "자료 " + layout.app.pdfs.length
                        fontPx: 12
                        fontWeight: 400
                        onClicked: layout.app.notYet("PDF 보기와 필기")
                    }
                }
            }

            // Recording bar
            Rectangle {
                visible: layout.app.recording
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.topMargin: 16
                implicitHeight: 60
                radius: 12
                color: Theme.surface
                border.color: layout.app.captureWarning !== "" ? "#7A2A2E" : Theme.surfaceLine
                Accessible.role: Accessible.StatusBar
                Accessible.name: "녹음 상태"
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 16
                    anchors.rightMargin: 12
                    spacing: 18
                    Row {
                        spacing: 6
                        Item {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 18
                            height: 18
                            // The halo flips with each status poll instead of animating.
                            Rectangle { anchors.fill: parent; radius: 9; color: Theme.ink(255, 95, 87, .16); visible: layout.app.blink }
                            Rectangle { anchors.centerIn: parent; width: 10; height: 10; radius: 5; color: Theme.rec }
                        }
                        Label {
                            text: layout.app.clock(layout.app.recordingSec)
                            color: Theme.text
                            font.family: Theme.monoFamily
                            font.pixelSize: 20
                            font.weight: 500
                            font.letterSpacing: 0.5
                        }
                    }
                    LevelMeter {
                        Layout.fillWidth: true
                        implicitHeight: 28
                        levels: layout.app.levels
                        color: "#4A4A52"
                        hotColor: "#FF8A84"
                        hot: 6
                    }
                    Row {
                        spacing: 6
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 6
                            height: 6
                            radius: 3
                            color: layout.app.captureWarning !== "" ? Theme.rec : Theme.ok
                        }
                        Label {
                            text: layout.app.micText + (layout.app.levelText ? " · " + layout.app.levelText : "")
                            color: layout.app.captureWarning !== "" ? Theme.recText : "#A8A8B0"
                            font.pixelSize: 12
                        }
                    }
                    ActionButton {
                        implicitHeight: 34
                        variant: "danger"
                        icon: "stop"
                        iconSize: 12
                        text: layout.app.actionBusy ? "정지 중…" : "정지"
                        hint: "Ctrl ."
                        fontPx: 13
                        dimmed: layout.app.actionBusy
                        onClicked: layout.app.stopRecording()
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                Layout.topMargin: visible ? 12 : 0
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

            // Transcript + session panel
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 20
                Layout.rightMargin: 20
                spacing: 20

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
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
                        font.pixelSize: 13
                    }
                    TranscriptView {
                        id: tv
                        anchors.fill: parent
                        visible: layout.app.session !== null
                        app: layout.app
                        sidePadding: 0
                        maxColumn: 100000
                        header: Item { height: 18 }
                    }
                }

                Rectangle {
                    visible: layout.app.session !== null && main.width > 900
                    Layout.preferredWidth: 260
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: 18
                    implicitHeight: info.implicitHeight + 32
                    radius: 12
                    color: "transparent"
                    border.color: Theme.panelLine
                    SessionInfo {
                        id: info
                        x: 16
                        y: 16
                        width: parent.width - 32
                        app: layout.app
                        showShortcuts: true
                    }
                }
            }

            // Transport bar
            Item {
                visible: layout.app.session !== null && !layout.app.recording && layout.app.hasAudio
                Layout.fillWidth: true
                implicitHeight: 64
                Rectangle { width: parent.width; height: 1; color: Theme.paneLine }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 24
                    anchors.rightMargin: 20
                    spacing: 14
                    ActionButton {
                        variant: "ghost"
                        icon: "back"
                        iconSize: 18
                        accessibleName: "10초 뒤로"
                        onClicked: layout.app.skip(-10)
                    }
                    Rectangle {
                        implicitWidth: 38
                        implicitHeight: 38
                        radius: 19
                        color: playHover.hovered ? "#FFFFFF" : "#F4F4F6"
                        Accessible.role: Accessible.Button
                        Accessible.name: layout.app.audioRunning ? "일시정지" : "재생"
                        Icon {
                            anchors.centerIn: parent
                            anchors.horizontalCenterOffset: layout.app.audioRunning ? 0 : 1
                            width: 15
                            height: 15
                            name: layout.app.audioRunning ? "pause" : "play"
                            color: "#121214"
                        }
                        HoverHandler { id: playHover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: layout.app.togglePlayback() }
                    }
                    ActionButton {
                        variant: "ghost"
                        icon: "forward"
                        iconSize: 18
                        accessibleName: "10초 앞으로"
                        onClicked: layout.app.skip(10)
                    }
                    Label {
                        text: layout.app.clock(layout.app.playheadSec)
                        color: "#C4C4CA"
                        font.family: Theme.monoFamily
                        font.pixelSize: 12
                    }
                    Scrubber {
                        Layout.fillWidth: true
                        value: layout.app.lectureEnd > 0 ? layout.app.playheadSec / layout.app.lectureEnd : 0
                        trackColor: "#26262B"
                        fillColor: Theme.accent
                        knob: false
                        onSeek: f => layout.app.seekLecture(f * layout.app.lectureEnd)
                    }
                    Label {
                        text: layout.app.clock(layout.app.lectureEnd)
                        color: Theme.muted
                        font.family: Theme.monoFamily
                        font.pixelSize: 12
                    }
                    ActionButton {
                        implicitHeight: 30
                        radius: 7
                        text: layout.app.rateText
                        fontPx: 12
                        fontWeight: 500
                        accessibleName: "재생 속도 " + layout.app.rateText
                        onClicked: layout.app.cycleRate()
                    }
                    ActionButton {
                        implicitHeight: 30
                        radius: 7
                        text: layout.app.continuePlayback ? "이어 재생 켜짐" : "이어 재생 꺼짐"
                        fontPx: 12
                        fontWeight: 400
                        onClicked: layout.app.continuePlayback = !layout.app.continuePlayback
                    }
                }
            }
        }
    }
}
