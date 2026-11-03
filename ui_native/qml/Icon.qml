import QtQuick
import QtQuick.Shapes

// Small stroked icons matching the web UI's inline SVGs (1.8px round stroke,
// 24x24 viewBox).
Item {
    id: icon
    property string name: "play"
    property color color: "white"
    property real stroke: 1.8
    implicitWidth: 18
    implicitHeight: 18

    readonly property real s: Math.min(width, height) / 24
    readonly property bool filled: name === "play" || name === "pause" || name === "stop"

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: icon.color
            strokeWidth: icon.stroke
            fillColor: icon.filled ? icon.color : "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(icon.s, icon.s)
            PathSvg {
                path: {
                    switch (icon.name) {
                    case "play": return "M9 6 L18 12 L9 18 Z"
                    case "pause": return "M8 6 h2.5 v12 h-2.5 Z M13.5 6 h2.5 v12 h-2.5 Z"
                    case "stop": return "M7 7 h10 v10 h-10 Z"
                    case "chevron": return "M7 9 L12 14 L17 9"
                    case "chevron-left": return "M15 6 L9 12 L15 18"
                    case "search": return "M10.5 4.5 a6 6 0 1 0 0.01 0 M15 15 L20 20"
                    case "play-all": return "M5 6 v12 M9 6 L18 12 L9 18 Z"
                    case "plus": return "M12 5 v14 M5 12 h14"
                    case "info": return "M12 3 a9 9 0 1 0 0.01 0 M12 11 v6 M12 7.5 v0.5"
                    case "expand": return "M4 9 V4 h5 M20 9 V4 h-5 M4 15 v5 h5 M20 15 v5 h-5 M4 4 l6 6 M20 4 l-6 6 M4 20 l6 -6 M20 20 l-6 -6"
                    case "power": return "M12 3 v8 M7.5 6.5 a7 7 0 1 0 9 0"
                    case "moon": return "M20 14.5 A8 8 0 1 1 9.5 4 A6.5 6.5 0 0 0 20 14.5 Z"
                    case "sun": return "M12 8 a4 4 0 1 0 0.01 0 M12 2.5 v2 M12 19.5 v2 M2.5 12 h2 M19.5 12 h2 M5.3 5.3 l1.4 1.4 M17.3 17.3 l1.4 1.4 M5.3 18.7 l1.4 -1.4 M17.3 6.7 l1.4 -1.4"
                    case "notebook": return "M6 3 h11 a2 2 0 0 1 2 2 v14 a2 2 0 0 1 -2 2 h-11 Z M9 3 v18 M12 8 h4 M12 12 h4"
                    default: return ""
                    }
                }
            }
        }
    }
}
