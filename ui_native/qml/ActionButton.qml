import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Text and/or icon button in the current theme.
// variant: "default" | "primary" | "danger" | "ghost"
// hint: a shortcut shown after the text ("Ctrl N"); dotColor: a small round
// dot before the text (the record dot).
Item {
    id: btn

    property string text: ""
    property string icon: ""
    property string variant: "default"
    property string hint: ""
    property real radius: Theme.radius
    property int iconSize: 16
    property int fontPx: 14
    property int fontWeight: 600
    property bool dimmed: false
    property bool fillWidth: false
    property bool alignLeft: false
    property color dotColor: "transparent"
    property string accessibleName: text

    signal clicked()

    implicitWidth: fillWidth ? 0 : (text ? content.implicitWidth + 26 : implicitHeight)
    implicitHeight: 36
    opacity: dimmed ? 0.5 : 1

    readonly property var tone: {
        switch (variant) {
        case "primary": return {
            bg: Theme.pick("#24211C", "#8B8EFF", "#C9302C"), hover: Theme.pick("#3A352D", "#A0A3FF", "#B5281F"),
            line: "transparent", fg: Theme.pick("#F6F3ED", "#0D0D0F", "#FFFFFF"), hint: Theme.pick("#CFC9BD", "#2E2F66", "#FFE1DF") }
        case "danger": return {
            bg: Theme.pick("#FBEDEB", "#D93A40", "#C9302C"), hover: Theme.pick("#F7E2DF", "#E5484D", "#B5281F"),
            line: Theme.pick("#F0D3CF", "transparent", "transparent"), fg: Theme.pick("#B23A31", "#FFFFFF", "#FFFFFF"),
            hint: Theme.pick("#B23A31", "#FFE1DF", "#FFE1DF") }
        case "ghost": return {
            bg: "transparent", hover: Theme.hover, line: "transparent", fg: Theme.muted, hint: Theme.muted }
        default: return {
            bg: Theme.pick("#FFFFFF", "transparent", "#F2F2F0"), hover: Theme.pick("#FBF9F5", "#18181C", "#E9E9E7"),
            line: Theme.pick("#E3DDD2", "#26262B", "transparent"), fg: Theme.pick("#24211C", "#C4C4CA", "#1C1C1E"),
            hint: Theme.muted }
        }
    }

    Accessible.role: Accessible.Button
    Accessible.name: accessibleName
    Accessible.onPressAction: if (!btn.dimmed) btn.clicked()

    Rectangle {
        anchors.fill: parent
        radius: btn.radius
        color: hover.hovered && !btn.dimmed ? btn.tone.hover : btn.tone.bg
        border.width: btn.tone.line !== "transparent" ? 1 : 0
        border.color: btn.tone.line
    }

    RowLayout {
        id: content
        anchors.verticalCenter: parent.verticalCenter
        x: btn.alignLeft ? 12 : Math.round((parent.width - width) / 2)
        width: btn.alignLeft ? parent.width - 24 : implicitWidth
        spacing: 8
        Rectangle {
            visible: btn.dotColor.a > 0
            implicitWidth: 8
            implicitHeight: 8
            radius: 4
            color: btn.dotColor
        }
        Icon {
            visible: btn.icon !== ""
            name: btn.icon
            color: btn.tone.fg
            implicitWidth: btn.iconSize
            implicitHeight: btn.iconSize
        }
        Label {
            visible: btn.text !== ""
            Layout.fillWidth: btn.alignLeft
            text: btn.text
            color: btn.tone.fg
            font.pixelSize: btn.fontPx
            font.weight: btn.fontWeight
            elide: Text.ElideRight
        }
        Label {
            visible: btn.hint !== ""
            text: btn.hint
            color: btn.tone.hint
            font.family: Theme.studio ? Theme.monoFamily : Theme.family
            font.pixelSize: 12
            font.weight: 400
        }
    }

    HoverHandler { id: hover; cursorShape: btn.dimmed ? Qt.ArrowCursor : Qt.PointingHandCursor }
    TapHandler { onTapped: if (!btn.dimmed) btn.clicked() }
}
