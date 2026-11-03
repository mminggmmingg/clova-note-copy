import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Session facts, the lecture's PDFs and (studio) the keyboard shortcuts.
// Shown as a panel in the studio theme and as a popover elsewhere.
ColumnLayout {
    id: info
    required property var app
    property bool showShortcuts: false

    readonly property var s: app.session
    readonly property var subject: s ? app.subjectOf(s.subject_id) : null
    readonly property var rows: !s ? [] : [
        ["과목", subject ? subject.name : "미분류"],
        ["교수", s.professor_name || ""],
        ["날짜", app.shortDate(s.created_at) + " " + app.timeOfDay(s.created_at)],
        ["길이", app.recording ? app.clock(app.recordingSec) + " (녹음 중)" : app.humanLength(s.recording_time_sec)],
        ["문장", (app.segments.length - app.pendingCount) + (app.pendingCount ? " · 처리 중 " + app.pendingCount : "")
                 + (s.manual_edit_count ? " · 수정 " + s.manual_edit_count : "")],
        ["엔진", "Whisper Large-v3"]
    ].filter(r => r[1] !== "")

    spacing: 16

    component Kicker: Label {
        color: Theme.muted
        font.pixelSize: 12
        font.weight: 500
        font.letterSpacing: 0.3
    }
    component Divider: Rectangle {
        Layout.fillWidth: true
        implicitHeight: 1
        color: Theme.panelLine
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 10
        Kicker { text: "세션" }
        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 10
            rowSpacing: 8
            Repeater {
                model: info.rows.length * 2
                Label {
                    required property int index
                    readonly property bool key: index % 2 === 0
                    Layout.preferredWidth: key ? 52 : -1
                    Layout.fillWidth: !key
                    text: info.rows[Math.floor(index / 2)][key ? 0 : 1]
                    color: key ? Theme.muted : Theme.text
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }
        }
    }

    Divider {}

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 6
        Kicker { text: "자료" }
        Repeater {
            model: info.app.pdfs
            delegate: Rectangle {
                id: pdf
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: 48
                radius: 8
                color: pdfHover.hovered ? Theme.hover : "transparent"
                Accessible.role: Accessible.Link
                Accessible.name: modelData.original_filename || "PDF"
                HoverHandler { id: pdfHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: info.app.notYet("PDF 보기와 필기") }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 6
                    anchors.rightMargin: 6
                    spacing: 10
                    Rectangle {
                        implicitWidth: 30
                        implicitHeight: 36
                        radius: 5
                        color: Theme.chip
                        Label {
                            anchors.centerIn: parent
                            text: "PDF"
                            color: Theme.recText
                            font.pixelSize: 9
                            font.weight: 700
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: pdf.modelData.original_filename || "PDF"
                        color: Theme.text
                        font.pixelSize: 13
                        elide: Text.ElideMiddle
                    }
                }
            }
        }
        ActionButton {
            implicitHeight: 32
            variant: "ghost"
            icon: "plus"
            iconSize: 14
            text: "자료 추가"
            fontPx: 13
            fontWeight: 400
            onClicked: info.app.notYet("PDF 추가")
        }
    }

    Divider { visible: info.showShortcuts }

    GridLayout {
        visible: info.showShortcuts
        Layout.fillWidth: true
        columns: 1
        rowSpacing: 8
        Repeater {
            model: [["새 녹음", "Ctrl N"], ["녹음 정지", "Ctrl ."], ["최신 문장으로", "End"], ["설정", "Ctrl ,"]]
            delegate: Label {
                required property var modelData
                Layout.fillWidth: true
                text: modelData[0]
                color: Theme.subtle
                font.pixelSize: 12
                Label {
                    anchors.right: parent.right
                    text: parent.modelData[1]
                    color: Theme.muted
                    font.family: Theme.monoFamily
                    font.pixelSize: 12
                }
            }
        }
    }
}
