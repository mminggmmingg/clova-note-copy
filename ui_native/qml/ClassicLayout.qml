import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// 클래식 라이트: subjects | lectures | the open lecture, with a large
// recording card (or playback card) above the transcript.
Item {
    id: layout
    required property var app
    property alias transcript: tv

    RowLayout {
        anchors.fill: parent
        spacing: 0

        SubjectList {
            Layout.preferredWidth: 224
            Layout.fillHeight: true
            app: layout.app
        }
        LectureList {
            Layout.preferredWidth: 300
            Layout.fillHeight: true
            app: layout.app
        }

        Item {
            id: main
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
                font.pixelSize: 14
            }

            ColumnLayout {
                visible: layout.app.session !== null || layout.app.errorText !== ""
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.topMargin: 26
                anchors.horizontalCenter: parent.horizontalCenter
                width: Math.min(760, parent.width - 80)
                spacing: 0

                // Title, meta and actions
                RowLayout {
                    Layout.fillWidth: true
                    visible: layout.app.session !== null
                    spacing: 10
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Label {
                            Layout.fillWidth: true
                            text: layout.app.session ? layout.app.session.title : ""
                            color: Theme.heading
                            font.pixelSize: 28
                            font.weight: 700
                            font.letterSpacing: -0.5
                            elide: Text.ElideRight
                        }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 6
                            Label {
                                text: layout.app.sessionMeta
                                color: Theme.muted
                                font.pixelSize: 14
                            }
                            Repeater {
                                model: layout.app.pdfs
                                delegate: Label {
                                    required property var modelData
                                    required property int index
                                    text: "· " + (modelData.original_filename || "PDF")
                                    color: Theme.text
                                    font.pixelSize: 14
                                    font.underline: pdfHover.hovered
                                    Accessible.role: Accessible.Link
                                    HoverHandler { id: pdfHover; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: layout.app.notYet("PDF 보기와 필기") }
                                }
                            }
                        }
                    }
                    ActionButton {
                        Layout.alignment: Qt.AlignTop
                        visible: layout.app.session !== null && !layout.app.recording
                        dotColor: Theme.rec
                        text: layout.app.actionBusy ? "재개 중…" : "이어서 녹음"
                        fontPx: 14
                        dimmed: layout.app.actionBusy || layout.app.pendingCount > 0
                        onClicked: layout.app.resumeClicked()
                    }
                    ActionButton {
                        id: infoButton
                        Layout.alignment: Qt.AlignTop
                        icon: "info"
                        iconSize: 18
                        accessibleName: "세션 정보"
                        onClicked: layout.app.showInfo(infoButton)
                    }
                }

                // Recording card
                Rectangle {
                    visible: layout.app.recording
                    Layout.fillWidth: true
                    Layout.topMargin: 22
                    implicitHeight: 104
                    radius: 18
                    color: Theme.surface
                    border.color: layout.app.captureWarning !== "" ? "#F2B8B5" : Theme.surfaceLine
                    Accessible.role: Accessible.StatusBar
                    Accessible.name: "녹음 상태"
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 20
                        anchors.rightMargin: 20
                        spacing: 22
                        ColumnLayout {
                            spacing: 4
                            Label {
                                text: layout.app.clock(layout.app.recordingSec)
                                color: Theme.heading
                                font.pixelSize: 40
                                font.weight: 600
                                font.letterSpacing: -0.5
                                font.features: { "tnum": 1 }
                            }
                            Row {
                                spacing: 6
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 7
                                    height: 7
                                    radius: 3.5
                                    color: Theme.accent
                                    opacity: layout.app.blink || layout.app.captureWarning !== "" ? 1 : 0.45
                                }
                                Label {
                                    text: "녹음 중 · " + layout.app.micText
                                    color: Theme.recText
                                    font.pixelSize: 13
                                    font.weight: 600
                                }
                            }
                        }
                        Item {
                            Layout.fillWidth: true
                            implicitHeight: 56
                            LevelMeter {
                                anchors.fill: parent
                                anchors.rightMargin: 5
                                levels: layout.app.levels
                                color: "#C7C7CC"
                                hotColor: Theme.accent
                                hot: 5
                            }
                            Rectangle {
                                anchors.right: parent.right
                                width: 2
                                height: parent.height
                                radius: 1
                                color: Theme.accent
                            }
                        }
                        Column {
                            spacing: 6
                            Rectangle {
                                width: 60
                                height: 60
                                radius: 30
                                color: "#FFFFFF"
                                border.width: 3
                                border.color: stopHover.hovered ? "#B8B8BE" : "#D1D1D6"
                                opacity: layout.app.actionBusy ? 0.6 : 1
                                Accessible.role: Accessible.Button
                                Accessible.name: "녹음 정지"
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 22
                                    height: 22
                                    radius: 5
                                    color: Theme.accent
                                }
                                HoverHandler { id: stopHover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: layout.app.stopRecording() }
                            }
                            Label {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: layout.app.actionBusy ? "정지 중…" : "정지"
                                color: Theme.muted
                                font.pixelSize: 12
                            }
                        }
                    }
                }

                // Playback card
                Rectangle {
                    visible: layout.app.session !== null && !layout.app.recording && layout.app.hasAudio
                    Layout.fillWidth: true
                    Layout.topMargin: 22
                    implicitHeight: 92
                    radius: 18
                    color: Theme.surface
                    border.color: Theme.surfaceLine
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 20
                        anchors.rightMargin: 20
                        spacing: 18
                        Rectangle {
                            implicitWidth: 52
                            implicitHeight: 52
                            radius: 26
                            color: playHover.hovered ? "#3A3A3C" : "#1C1C1E"
                            Accessible.role: Accessible.Button
                            Accessible.name: layout.app.audioRunning ? "일시정지" : "재생"
                            Icon {
                                anchors.centerIn: parent
                                anchors.horizontalCenterOffset: layout.app.audioRunning ? 0 : 2
                                width: 20
                                height: 20
                                name: layout.app.audioRunning ? "pause" : "play"
                                color: "#FFFFFF"
                            }
                            HoverHandler { id: playHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: layout.app.togglePlayback() }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Scrubber {
                                Layout.fillWidth: true
                                trackHeight: 6
                                value: layout.app.lectureEnd > 0 ? layout.app.playheadSec / layout.app.lectureEnd : 0
                                trackColor: "#E5E5EA"
                                fillColor: "#1C1C1E"
                                onSeek: f => layout.app.seekLecture(f * layout.app.lectureEnd)
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    Layout.fillWidth: true
                                    text: layout.app.clock(layout.app.playheadSec)
                                    color: Theme.text
                                    font.pixelSize: 13
                                    font.weight: 600
                                    font.features: { "tnum": 1 }
                                }
                                Label {
                                    text: "−" + layout.app.clock(Math.max(0, layout.app.lectureEnd - layout.app.playheadSec))
                                    color: Theme.muted
                                    font.pixelSize: 13
                                    font.features: { "tnum": 1 }
                                }
                            }
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

                Banner {
                    Layout.fillWidth: true
                    Layout.topMargin: visible ? 12 : 0
                    text: layout.app.captureWarning
                }
                Banner {
                    Layout.fillWidth: true
                    Layout.topMargin: visible ? 12 : 0
                    tone: "warn"
                    text: layout.app.errorText
                    actionText: "다시 시도"
                    onAction: layout.app.retry()
                }

                TranscriptView {
                    id: tv
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.topMargin: 12
                    visible: layout.app.session !== null
                    app: layout.app
                    sidePadding: 0
                    maxColumn: 100000
                    header: Item { height: 10 }
                }
            }
        }
    }
}
