import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Modal card in the web UI's .modal style: kicker, title, a short lead, then
// the form (children go below the lead). Plain dim behind it, no blur and no
// animation, so an open dialog costs nothing while recording.
Popup {
    id: dlg

    property string kicker: ""
    property string title: ""
    property string lead: ""
    property real cardWidth: 480
    default property alias form: formColumn.data

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(cardWidth, (parent ? parent.width : cardWidth) - 48)
    modal: true
    focus: true
    padding: 27
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle {
        color: Theme.pick(Theme.ink(0, 0, 0, .68), Theme.ink(45, 55, 72, .35), Theme.ink(72, 59, 45, .30))
    }

    background: Item {
        Rectangle {
            visible: Theme.notebook
            anchors.fill: parent
            anchors.topMargin: 3
            anchors.bottomMargin: -3
            radius: 19
            color: Theme.paperLip
        }
        Rectangle {
            anchors.fill: parent
            radius: 19
            border.color: Theme.pick(Theme.ink(255, 255, 255, .11), Theme.ink(24, 36, 54, .12), Theme.ink(124, 96, 63, .16))
            gradient: Gradient {
                GradientStop { position: 0; color: Theme.pick("#14181e", "#ffffff", "#fdf9f2") }
                GradientStop { position: 1; color: Theme.pick("#0e1115", "#f7f9fc", "#fbf3e7") }
            }
        }
    }

    contentItem: ColumnLayout {
        spacing: 0
        Label {
            text: dlg.kicker
            color: Theme.pick("#7580b2", "#6775e8", "#9a7b52")
            font.pointSize: Theme.pt(8)
            font.weight: 800
            font.letterSpacing: 1.3
        }
        Label {
            Layout.topMargin: 8
            text: dlg.title
            color: Theme.heading
            font.pixelSize: 24
            font.weight: 700
            font.letterSpacing: -0.84
        }
        Label {
            Layout.topMargin: 6
            Layout.bottomMargin: 20
            Layout.fillWidth: true
            visible: dlg.lead !== ""
            text: dlg.lead
            color: Theme.muted
            font.pointSize: Theme.pt(10.5)
            wrapMode: Text.Wrap
            lineHeight: 1.35
        }
        ColumnLayout {
            id: formColumn
            Layout.fillWidth: true
            spacing: 13
        }
    }

    // × in the corner
    Rectangle {
        parent: dlg.background
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: 14
        anchors.topMargin: 13
        width: 30
        height: 30
        radius: 8
        color: closeHover.hovered ? Theme.hover : "transparent"
        Label {
            anchors.centerIn: parent
            text: "×"
            color: closeHover.hovered ? Theme.text : Theme.muted2
            font.pixelSize: 20
        }
        HoverHandler { id: closeHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: dlg.close() }
    }
}
