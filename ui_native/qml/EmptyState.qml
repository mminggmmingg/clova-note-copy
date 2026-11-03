import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Shown when no lecture is open: one line of what this is and the record
// button. Static: nothing here animates.
Item {
    id: empty
    signal newSessionRequested()

    ColumnLayout {
        anchors.centerIn: parent
        width: Math.min(parent.width - 48, 460)
        spacing: 0

        BrandMark {
            Layout.alignment: Qt.AlignHCenter
            Layout.bottomMargin: 22
            size: 44
        }
        Label {
            Layout.fillWidth: true
            horizontalAlignment: Text.AlignHCenter
            text: "오늘 강의를 기록해 볼까요"
            color: Theme.heading
            font.family: Theme.titleFamily
            font.pixelSize: 28
            font.weight: Theme.paper ? 600 : 700
            font.letterSpacing: -0.5
            wrapMode: Text.Wrap
        }
        Label {
            Layout.fillWidth: true
            Layout.topMargin: 10
            horizontalAlignment: Text.AlignHCenter
            text: "녹음을 시작하면 Whisper Large-v3가 문장 단위로 전사합니다. 음성과 전사는 이 기기에만 저장됩니다."
            color: Theme.muted
            font.pixelSize: 14
            wrapMode: Text.Wrap
            lineHeight: 1.35
        }
        ActionButton {
            Layout.alignment: Qt.AlignHCenter
            Layout.topMargin: 26
            implicitHeight: 42
            variant: "primary"
            dotColor: Theme.paper ? Theme.rec : (Theme.studio ? "#0D0D0F" : "#FFFFFF")
            text: "새 녹음"
            hint: "Ctrl N"
            onClicked: empty.newSessionRequested()
        }
    }
}
