import QtQuick
import QtQuick.Shapes

// Small stroked icons matching the web UI's inline SVGs (1.8px round stroke).
Item {
    id: icon
    property string name: "play"
    property color color: "white"
    property real stroke: 1.8
    implicitWidth: 18
    implicitHeight: 18

    readonly property real s: Math.min(width, height) / 24

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: icon.color
            strokeWidth: icon.stroke
            fillColor: icon.name === "play" || icon.name === "pause" ? icon.color : "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(icon.s, icon.s)
            PathSvg {
                path: {
                    switch (icon.name) {
                    case "play": return "M9 6 L18 12 L9 18 Z"
                    case "pause": return "M8 6 h2.5 v12 h-2.5 Z M13.5 6 h2.5 v12 h-2.5 Z"
                    case "chevron": return "M7 9 L12 14 L17 9"
                    case "search": return "M10.5 4.5 a6 6 0 1 0 0.01 0 M15 15 L20 20"
                    case "play-all": return "M5 6 v12 M9 6 L18 12 L9 18 Z"
                    default: return ""
                    }
                }
            }
        }
    }
}
