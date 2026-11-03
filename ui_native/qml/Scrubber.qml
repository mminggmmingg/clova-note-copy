import QtQuick
import QtQuick.Controls
import "."

// Seek bar over the whole lecture. Dragging only moves the knob; the seek
// happens on release, so a drag does not reload segment audio on every move.
Item {
    id: bar
    property real value: 0               // 0..1
    property real trackHeight: 4
    property color trackColor: Theme.line
    property color fillColor: Theme.accent
    property bool knob: true
    property color knobColor: "#FFFFFF"
    property color knobLine: fillColor
    signal seek(real fraction)

    property real dragValue: -1
    readonly property real shown: dragValue >= 0 ? dragValue : Math.max(0, Math.min(1, value))

    implicitHeight: 20
    Accessible.role: Accessible.Slider
    Accessible.name: "재생 위치"

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: bar.trackHeight
        radius: height / 2
        color: bar.trackColor
        Rectangle {
            width: parent.width * bar.shown
            height: parent.height
            radius: parent.radius
            color: bar.fillColor
        }
    }
    Rectangle {
        visible: bar.knob
        x: Math.round(bar.width * bar.shown - width / 2)
        anchors.verticalCenter: parent.verticalCenter
        width: 16
        height: 16
        radius: 8
        color: bar.knobColor
        border.width: 2
        border.color: bar.knobLine
    }
    MouseArea {
        anchors.fill: parent
        anchors.topMargin: -6
        anchors.bottomMargin: -6
        cursorShape: Qt.PointingHandCursor
        function at(x) { return Math.max(0, Math.min(1, x / Math.max(1, bar.width))) }
        onPressed: mouse => bar.dragValue = at(mouse.x)
        onPositionChanged: mouse => { if (pressed) bar.dragValue = at(mouse.x) }
        onReleased: mouse => {
            const f = at(mouse.x)
            bar.dragValue = -1
            bar.seek(f)
        }
        onCanceled: bar.dragValue = -1
    }
}
