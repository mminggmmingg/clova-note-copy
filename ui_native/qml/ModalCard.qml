import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Modal card: title, a short lead, then the form (children go below the
// lead). Plain dim behind it, no blur and no animation, so an open dialog
// costs nothing while recording.
Popup {
    id: dlg

    property string title: ""
    property string lead: ""
    property real cardWidth: 460
    default property alias form: formColumn.data

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(cardWidth, (parent ? parent.width : cardWidth) - 48)
    modal: true
    focus: true
    padding: 26
    topPadding: 24
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: Theme.dim }

    background: Rectangle {
        radius: Theme.pick(16, 12, 16)
        color: Theme.dialogBg
        border.color: Theme.dialogLine
    }

    contentItem: ColumnLayout {
        spacing: 0
        Label {
            Layout.fillWidth: true
            Layout.rightMargin: 34
            text: dlg.title
            color: Theme.heading
            font.family: Theme.titleFamily
            font.pixelSize: 22
            font.weight: Theme.paper ? 600 : 700
            font.letterSpacing: -0.4
            wrapMode: Text.Wrap
        }
        Label {
            Layout.topMargin: 6
            Layout.fillWidth: true
            visible: dlg.lead !== ""
            text: dlg.lead
            color: Theme.muted
            font.pixelSize: 14
            wrapMode: Text.Wrap
            lineHeight: 1.3
        }
        ColumnLayout {
            id: formColumn
            Layout.topMargin: 20
            Layout.fillWidth: true
            spacing: 14
        }
    }

    ActionButton {
        parent: dlg.background
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: 14
        anchors.topMargin: 14
        implicitHeight: 32
        variant: "ghost"
        icon: "close"
        iconSize: 16
        accessibleName: "닫기"
        onClicked: dlg.close()
    }
}
