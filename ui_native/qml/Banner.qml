import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// One-line notice: tone "error" (capture problems) or "warn" (backend
// errors), with an optional action on the right.
Rectangle {
    id: banner
    property string text: ""
    property string tone: "error"
    property string actionText: ""
    signal action()

    visible: text !== ""
    implicitHeight: visible ? row.implicitHeight + 20 : 0
    radius: Theme.radius
    color: tone === "error" ? Theme.errorBg : Theme.warnBg

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 8
        spacing: 10
        Label {
            Layout.fillWidth: true
            text: banner.text
            color: banner.tone === "error" ? Theme.errorText : Theme.warnText
            font.pixelSize: 13
            font.weight: 500
            wrapMode: Text.Wrap
        }
        ActionButton {
            visible: banner.actionText !== ""
            implicitHeight: 30
            variant: "ghost"
            text: banner.actionText
            fontPx: 13
            onClicked: banner.action()
        }
    }
}
