import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Labeled text field. With `options` set it becomes a drop-down instead:
// options = [{ value, label }], and `value` holds the chosen value.
ColumnLayout {
    id: field

    property string label: ""
    property alias text: input.text
    property alias placeholder: input.placeholderText
    property alias maximumLength: input.maximumLength
    property var options: null
    property string value: ""
    readonly property Item editor: options ? combo : input

    signal accepted()

    spacing: 7

    function focusEditor() { editor.forceActiveFocus() }

    Label {
        text: field.label
        color: Theme.muted
        font.pixelSize: 13
        font.weight: 600
    }

    component FieldBox: Rectangle {
        property bool focused: false
        radius: Theme.radius
        color: Theme.fieldBg
        border.width: focused || !Theme.classic ? 1 : 0
        border.color: focused ? Theme.focus : Theme.fieldLine
    }

    TextField {
        id: input
        visible: !field.options
        Layout.fillWidth: true
        implicitHeight: 40
        leftPadding: 12
        rightPadding: 12
        color: Theme.text
        placeholderTextColor: Theme.muted
        selectionColor: Theme.wordPlaying
        selectedTextColor: Theme.text
        font.pixelSize: 15
        selectByMouse: true
        background: FieldBox { focused: input.activeFocus }
        onAccepted: field.accepted()
        Accessible.name: field.label
    }

    ComboBox {
        id: combo
        visible: !!field.options
        Layout.fillWidth: true
        implicitHeight: 40
        model: field.options || []
        textRole: "label"
        valueRole: "value"
        font.pixelSize: 15
        leftPadding: 12
        Accessible.name: field.label
        onActivated: field.value = currentValue
        Component.onCompleted: currentIndex = Math.max(0, indexOfValue(field.value))
        Connections {
            target: field
            function onValueChanged() { combo.currentIndex = Math.max(0, combo.indexOfValue(field.value)) }
            function onOptionsChanged() { combo.currentIndex = Math.max(0, combo.indexOfValue(field.value)) }
        }
        background: FieldBox { focused: combo.activeFocus || combo.popup.visible }
        contentItem: Label {
            leftPadding: 0
            rightPadding: 28
            verticalAlignment: Text.AlignVCenter
            text: combo.displayText
            color: Theme.text
            font: combo.font
            elide: Text.ElideRight
        }
        indicator: Icon {
            x: combo.width - width - 12
            y: (combo.height - height) / 2
            width: 14
            height: 14
            name: "chevron"
            color: Theme.muted
        }
        delegate: ItemDelegate {
            id: option
            required property var modelData
            required property int index
            width: combo.width
            height: 36
            highlighted: combo.highlightedIndex === index
            contentItem: Label {
                text: option.modelData.label
                color: Theme.text
                font.pixelSize: 15
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle { radius: 6; color: option.highlighted ? Theme.hover : "transparent" }
        }
        popup: Popup {
            y: combo.height + 4
            width: combo.width
            implicitHeight: Math.min(contentItem.implicitHeight + 8, 300)
            padding: 4
            contentItem: ListView {
                clip: true
                implicitHeight: contentHeight
                model: combo.popup.visible ? combo.delegateModel : null
                currentIndex: combo.highlightedIndex
                ScrollIndicator.vertical: ScrollIndicator {}
            }
            background: Rectangle {
                radius: Theme.radius
                color: Theme.dialogBg
                border.color: Theme.dialogLine
            }
        }
    }
}
