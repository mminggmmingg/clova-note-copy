import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Labeled text field in the web UI's .form-field style (warm paper in the
// notebook theme). With `options` set it becomes a drop-down instead:
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
        color: Theme.pick("#7d8794", "#536071", "#786d61")
        font.pointSize: Theme.pt(9.5)
        font.weight: 680
    }

    component FieldBox: Rectangle {
        property bool focused: false
        radius: 10
        border.color: focused ? Theme.pick(Theme.ink(124, 140, 255, .5), Theme.ink(103, 117, 232, .5), Theme.ink(185, 138, 73, .42))
                              : Theme.pick(Theme.ink(255, 255, 255, .09), Theme.ink(24, 36, 54, .14), Theme.ink(124, 96, 63, .18))
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.pick("#0b0e12", "#ffffff", "#fffdf8") }
            GradientStop { position: 1; color: Theme.pick("#0b0e12", "#ffffff", "#fbf5eb") }
        }
    }

    TextField {
        id: input
        visible: !field.options
        Layout.fillWidth: true
        implicitHeight: 41
        leftPadding: 12
        rightPadding: 12
        color: Theme.pick("#e8ecf2", "#172130", "#4f453b")
        placeholderTextColor: Theme.pick("#48515c", "#9aa4b1", "#aa9d8e")
        font.pointSize: Theme.pt(12)
        selectByMouse: true
        background: FieldBox { focused: input.activeFocus }
        onAccepted: field.accepted()
    }

    ComboBox {
        id: combo
        visible: !!field.options
        Layout.fillWidth: true
        implicitHeight: 41
        model: field.options || []
        textRole: "label"
        valueRole: "value"
        font.pointSize: Theme.pt(12)
        leftPadding: 12
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
            verticalAlignment: Text.AlignVCenter
            text: combo.displayText
            color: Theme.pick("#e8ecf2", "#172130", "#4f453b")
            font: combo.font
            elide: Text.ElideRight
        }
        indicator: Icon {
            x: combo.width - width - 12
            y: (combo.height - height) / 2
            width: 12
            height: 12
            name: "chevron"
            color: Theme.muted2
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
                color: Theme.pick("#e8ecf2", "#172130", "#4f453b")
                font.pointSize: Theme.pt(12)
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle { color: option.highlighted ? Theme.hover : "transparent" }
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
                radius: 10
                color: Theme.pick("#14181e", "#ffffff", "#fffaf0")
                border.color: Theme.lineStrong
            }
        }
    }
}
