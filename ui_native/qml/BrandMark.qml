import QtQuick
import "."

// The app mark: four level bars on a rounded square.
Rectangle {
    id: mark
    property real size: 26
    width: size
    height: size
    radius: size * 0.27
    color: Theme.pick("#24211C", Theme.accent, Theme.accent)

    Repeater {
        // [x, height] on the 26 px grid
        model: [[8, 6], [11.7, 11], [15.3, 7], [19, 3]]
        Rectangle {
            required property var modelData
            readonly property real k: mark.size / 26
            x: (modelData[0] - 1) * k
            y: (13 - modelData[1] / 2 - 1) * k
            width: 2 * k
            height: (modelData[1] + 2) * k
            radius: k
            color: Theme.pick("#F6F3ED", "#0D0D0F", "#FFFFFF")
        }
    }
}
