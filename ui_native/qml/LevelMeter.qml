import QtQuick
import "."

// Input level bars from /api/recording/status: one bar per status poll
// (vad_input_rms_dbfs_1s, every 500 ms), newest on the right. Nothing
// animates; the bars change only when a new level arrives.
Item {
    id: meter

    property var levels: []              // dBFS, oldest first
    property int barWidth: 3
    property int gap: 3
    property real minBar: 3
    property color color: Theme.muted
    property color hotColor: color       // the newest `hot` bars
    property int hot: 0
    property real floorDb: -62
    property real ceilDb: -14

    readonly property int count: Math.max(1, Math.floor((width + gap) / (barWidth + gap)))

    implicitHeight: 24

    Row {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: meter.gap
        Repeater {
            model: meter.count
            Rectangle {
                required property int index
                readonly property int at: meter.levels.length - meter.count + index
                readonly property real db: at >= 0 ? Number(meter.levels[at]) : -120
                readonly property real frac: Math.max(0, Math.min(1, (db - meter.floorDb) / (meter.ceilDb - meter.floorDb)))
                anchors.verticalCenter: parent.verticalCenter
                visible: at >= 0                 // no level yet: leave the slot empty
                width: meter.barWidth
                height: Math.round(meter.minBar + (meter.height - meter.minBar) * frac)
                radius: meter.barWidth / 2
                color: index >= meter.count - meter.hot ? meter.hotColor : meter.color
            }
        }
    }
}
