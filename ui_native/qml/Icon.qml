import QtQuick
import QtQuick.Shapes

// Small stroked icons (1.8px round stroke, 24x24 viewBox), the same set the
// design mocks use.
Item {
    id: icon
    property string name: "play"
    property color color: "white"
    property real stroke: 1.8
    implicitWidth: 18
    implicitHeight: 18

    readonly property real s: Math.min(width, height) / 24
    readonly property bool filled: ["play", "pause", "stop", "more", "record"].indexOf(name) >= 0

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: icon.filled ? "transparent" : icon.color
            strokeWidth: icon.stroke
            fillColor: icon.filled ? icon.color : "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            scale: Qt.size(icon.s, icon.s)
            PathSvg {
                path: {
                    switch (icon.name) {
                    case "play": return "M8 5.5 L19 12 L8 18.5 Z"
                    case "pause": return "M7 5 h3.5 v14 h-3.5 Z M13.5 5 h3.5 v14 h-3.5 Z"
                    case "stop": return "M7 5 h10 a2 2 0 0 1 2 2 v10 a2 2 0 0 1 -2 2 h-10 a2 2 0 0 1 -2 -2 v-10 a2 2 0 0 1 2 -2 Z"
                    case "record": return "M12 6 a6 6 0 1 1 0 12 a6 6 0 1 1 0 -12 Z"
                    case "more": return "M7.1 12 a1.6 1.6 0 1 1 -3.2 0 a1.6 1.6 0 1 1 3.2 0 Z M13.6 12 a1.6 1.6 0 1 1 -3.2 0 a1.6 1.6 0 1 1 3.2 0 Z M20.1 12 a1.6 1.6 0 1 1 -3.2 0 a1.6 1.6 0 1 1 3.2 0 Z"
                    case "chevron": return "M6 9 L12 15 L18 9"
                    case "chevron-left": return "M15 6 L9 12 L15 18"
                    case "chevron-right": return "M9 6 L15 12 L9 18"
                    case "search": return "M11 4.5 a6.5 6.5 0 1 0 0.01 0 M16 16 L20 20"
                    case "plus": return "M12 5 v14 M5 12 h14"
                    case "close": return "M6.5 6.5 L17.5 17.5 M17.5 6.5 L6.5 17.5"
                    case "check": return "M5 12.5 L9.5 17 L19 7.5"
                    case "info": return "M12 3.5 a8.5 8.5 0 1 0 0.01 0 M12 11 v5.5 M12 7.8 v0.4"
                    case "power": return "M12 3 v8 M7.5 6.5 a7 7 0 1 0 9 0"
                    case "sidebar": return "M6.5 4.5 h11 a3 3 0 0 1 3 3 v9 a3 3 0 0 1 -3 3 h-11 a3 3 0 0 1 -3 -3 v-9 a3 3 0 0 1 3 -3 Z M9.5 4.5 v15"
                    case "sliders": return "M4 7 h10 M18 7 h2 M4 17 h4 M12 17 h8 M18 7 a2 2 0 1 1 -4 0 a2 2 0 1 1 4 0 M12 17 a2 2 0 1 1 -4 0 a2 2 0 1 1 4 0"
                    case "file": return "M7 3.5 h7 l4 4 V20 a0.5 0.5 0 0 1 -0.5 0.5 h-10.5 a0.5 0.5 0 0 1 -0.5 -0.5 V4 a0.5 0.5 0 0 1 0.5 -0.5 Z M14 3.5 V8 h4"
                    case "back": return "M4.5 12 a7.5 7.5 0 1 0 2.2 -5.3 M4.5 4 v4.5 h4.5"
                    case "forward": return "M19.5 12 a7.5 7.5 0 1 1 -2.2 -5.3 M19.5 4 v4.5 h-4.5"
                    default: return ""
                    }
                }
            }
        }
    }
}
