import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Filled search box with a leading magnifier.
Rectangle {
    id: box
    property alias text: input.text
    property string placeholder: "검색"
    signal edited(string text)

    implicitHeight: Theme.pick(38, 32, 35)
    radius: Theme.radius
    color: Theme.control
    border.width: input.activeFocus || Theme.studio ? 1 : 0
    border.color: input.activeFocus ? Theme.focus : "#26262B"

    function focusInput() { input.forceActiveFocus() }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 11
        anchors.rightMargin: 10
        spacing: 8
        Icon { name: "search"; color: Theme.muted; implicitWidth: 15; implicitHeight: 15 }
        TextField {
            id: input
            Layout.fillWidth: true
            placeholderText: box.placeholder
            placeholderTextColor: Theme.muted
            color: Theme.text
            selectionColor: Theme.wordPlaying
            selectedTextColor: Theme.text
            font.pixelSize: Theme.studio ? 13 : 14
            background: null
            padding: 0
            Accessible.name: box.placeholder
            onTextEdited: box.edited(text)
        }
    }
}
