import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// "이 기기에서만 처리", then settings and quit.
RowLayout {
    id: footer
    required property var app
    spacing: 4

    Rectangle {
        Layout.leftMargin: 8
        Layout.rightMargin: 4
        implicitWidth: 7
        implicitHeight: 7
        radius: 3.5
        color: Theme.ok
    }
    Label {
        Layout.fillWidth: true
        text: "이 기기에서만 처리"
        color: Theme.muted
        font.pixelSize: 12
        elide: Text.ElideRight
    }
    ActionButton {
        implicitHeight: 32
        variant: "ghost"
        icon: "sliders"
        iconSize: 17
        accessibleName: "설정"
        onClicked: footer.app.openSettings()
    }
    ActionButton {
        implicitHeight: 32
        variant: "ghost"
        icon: "power"
        iconSize: 17
        accessibleName: "앱 종료"
        onClicked: footer.app.requestShutdown()
    }
}
