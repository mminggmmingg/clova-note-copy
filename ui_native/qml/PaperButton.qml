import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Button in the web UI's style: a paper card with an under-lip and soft drop
// in the notebook theme, a quiet bordered button in dark/light.
// variant: "default" | "green" | "orange"
Item {
    id: btn

    property string text: ""
    property string icon: ""
    property string variant: "default"
    property bool tape: false
    property real tilt: 0
    property real radius: 9
    property int iconSize: 14
    property real fontPx: 9.5
    property real fontWeight: 650
    property bool dimmed: false
    property bool fillWidth: false

    signal clicked()

    implicitWidth: fillWidth ? 0 : (text ? content.implicitWidth + 24 : 36)
    implicitHeight: 36
    rotation: Theme.notebook ? tilt : 0
    opacity: dimmed ? 0.5 : 1

    readonly property var tone: {
        if (Theme.notebook) {
            if (variant === "green") return { top: "#edf7e9", bottom: "#dfeeda", border: Theme.ink(104, 148, 103, .22), fg: "#4f7f61" }
            if (variant === "orange") return { top: "#fff5e9", bottom: "#fae4d2", border: Theme.ink(190, 123, 81, .20), fg: "#a66749" }
            return { top: Theme.paperTop, bottom: Theme.paperBottom, border: Theme.paperBorder, fg: Theme.paperText }
        }
        if (variant === "green") return { top: Theme.ink(94, 214, 160, .12), bottom: Theme.ink(94, 214, 160, .12), border: Theme.ink(94, 214, 160, .22), fg: Theme.dark ? "#8fe3bb" : "#2f8f63" }
        if (variant === "orange") return { top: Theme.ink(243, 185, 95, .12), bottom: Theme.ink(243, 185, 95, .12), border: Theme.ink(243, 185, 95, .28), fg: Theme.dark ? "#f3c98a" : "#9a5b12" }
        const flat = Theme.dark ? Theme.ink(255, 255, 255, .026) : Theme.ink(255, 255, 255, .9)
        return { top: flat, bottom: flat, border: Theme.line, fg: Theme.dark ? "#d7dce5" : "#3a4655" }
    }

    // Notebook depth: a 3px under-lip and a soft drop shadow (no blur effect).
    Rectangle {
        visible: Theme.notebook
        anchors.fill: face
        anchors.topMargin: 6
        anchors.bottomMargin: -7
        anchors.leftMargin: 2
        anchors.rightMargin: 2
        radius: face.radius + 3
        color: Theme.paperShadow
    }
    Rectangle {
        visible: Theme.notebook
        anchors.fill: face
        anchors.topMargin: 3
        anchors.bottomMargin: -3
        radius: face.radius
        color: Theme.paperLip
    }

    Rectangle {
        id: face
        anchors.fill: parent
        radius: btn.radius
        border.color: btnHover.hovered && Theme.notebook ? Theme.ink(185, 138, 73, .32) : btn.tone.border
        gradient: Gradient {
            GradientStop { position: 0; color: btn.tone.top }
            GradientStop { position: 1; color: btn.tone.bottom }
        }
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            visible: btnHover.hovered && !Theme.notebook
            color: Theme.dark ? Theme.ink(255, 255, 255, .04) : Theme.ink(24, 36, 54, .03)
        }
    }

    RowLayout {
        id: content
        anchors.centerIn: parent
        spacing: 7
        Icon {
            visible: btn.icon !== ""
            name: btn.icon
            color: btn.tone.fg
            width: btn.iconSize
            height: btn.iconSize
        }
        Label {
            visible: btn.text !== ""
            text: btn.text
            color: btn.tone.fg
            font.pointSize: Theme.pt(btn.fontPx)
            font.weight: btn.fontWeight
        }
    }

    Tape {
        visible: btn.tape && Theme.notebook
        x: parent.width - width - 8
        y: -4
        rotation: 3
    }

    HoverHandler { id: btnHover; cursorShape: btn.dimmed ? Qt.ArrowCursor : Qt.PointingHandCursor }
    TapHandler { onTapped: if (!btn.dimmed) btn.clicked() }
}
