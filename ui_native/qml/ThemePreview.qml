import QtQuick
import "."

// A small drawing of each theme's layout for the settings dialog. Colors are
// the theme's own, not the current theme's.
Rectangle {
    id: preview
    property string mode: "paper"

    radius: 8
    clip: true
    border.color: Theme.dialogLine
    color: mode === "studio" ? "#121214" : (mode === "classic" ? "#FFFFFF" : "#F6F3ED")

    component Bar: Rectangle { height: 3; radius: 1.5 }

    // 종이 노트: library on the ground, a white page, the dark pill.
    Item {
        anchors.fill: parent
        visible: preview.mode === "paper"
        Column {
            x: 8; y: 10; spacing: 6
            Rectangle { width: 30; height: 7; radius: 3; color: "#FFFFFF"; border.color: "#E3DDD2" }
            Bar { width: 26; color: "#CFC9BD" }
            Bar { width: 30; color: "#CFC9BD" }
            Bar { width: 22; color: "#CFC9BD" }
        }
        Rectangle {
            x: 48; y: 7; width: parent.width - 58; height: parent.height - 30
            radius: 5; color: "#FFFFFF"; border.color: "#E9E4DA"
            Column {
                x: 10; y: 8; spacing: 5
                Bar { width: 42; height: 5; color: "#1F1C18" }
                Bar { width: preview.width - 90; color: "#D5CEC1" }
                Bar { width: preview.width - 100; color: "#D5CEC1" }
                Bar { width: preview.width - 95; color: "#D5CEC1" }
            }
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.horizontalCenterOffset: 20
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 6
            width: 46; height: 11; radius: 5.5; color: "#24211C"
            Rectangle { x: 5; anchors.verticalCenter: parent.verticalCenter; width: 4; height: 4; radius: 2; color: "#E5574B" }
        }
    }

    // 스튜디오: dark sidebar, recording bar, transcript, info panel.
    Item {
        anchors.fill: parent
        visible: preview.mode === "studio"
        Rectangle {
            width: 38; height: parent.height; color: "#0D0D0F"
            Column {
                x: 6; y: 10; spacing: 6
                Rectangle { width: 26; height: 7; radius: 2; color: "#17171A"; border.color: "#26262B" }
                Bar { width: 22; color: "#3A3A40" }
                Bar { width: 26; color: "#3A3A40" }
                Bar { width: 18; color: "#3A3A40" }
            }
        }
        Rectangle {
            x: 46; y: 10; width: parent.width - 54; height: 14; radius: 3; color: "#17171A"; border.color: "#26262B"
            Rectangle { x: 5; anchors.verticalCenter: parent.verticalCenter; width: 4; height: 4; radius: 2; color: "#FF5F57" }
            Rectangle { anchors.right: parent.right; anchors.rightMargin: 4; anchors.verticalCenter: parent.verticalCenter; width: 12; height: 6; radius: 2; color: "#D93A40" }
        }
        Column {
            x: 46; y: 32; spacing: 6
            Bar { width: preview.width - 100; color: "#4A4A52" }
            Bar { width: preview.width - 110; color: "#4A4A52" }
            Bar { width: preview.width - 104; color: "#4A4A52" }
            Bar { width: 30; color: "#8B8EFF" }
        }
        Rectangle { anchors.right: parent.right; anchors.rightMargin: 8; y: 32; width: 22; height: 40; radius: 3; color: "transparent"; border.color: "#26262B" }
    }

    // 클래식 라이트: subjects | lectures | transcript with the big card.
    Item {
        anchors.fill: parent
        visible: preview.mode === "classic"
        Rectangle {
            width: 30; height: parent.height; color: "#F2F2F0"
            Column {
                x: 5; y: 10; spacing: 6
                Repeater {
                    model: ["#2563EB", "#B45309", "#047857"]
                    Rectangle { required property string modelData; width: 6; height: 6; radius: 2; color: modelData }
                }
            }
        }
        Rectangle {
            x: 30; width: 36; height: parent.height; color: "#FFFFFF"
            Rectangle { x: 0; width: 1; height: parent.height; color: "#E3E3E1" }
            Rectangle { x: 35; width: 1; height: parent.height; color: "#ECECEF" }
            Rectangle { x: 4; y: 10; width: 28; height: 14; radius: 3; color: "#F2F2F0" }
            Column {
                x: 6; y: 30; spacing: 8
                Bar { width: 22; color: "#C7C7CC" }
                Bar { width: 18; color: "#C7C7CC" }
            }
        }
        Rectangle {
            x: 74; y: 10; width: parent.width - 82; height: 22; radius: 5; color: "#FAFAFA"; border.color: "#ECECEF"
            Rectangle { anchors.right: parent.right; anchors.rightMargin: 5; anchors.verticalCenter: parent.verticalCenter; width: 12; height: 12; radius: 6; color: "#FFFFFF"; border.color: "#D1D1D6"
                Rectangle { anchors.centerIn: parent; width: 5; height: 5; radius: 1; color: "#E5484D" } }
        }
        Column {
            x: 74; y: 42; spacing: 6
            Bar { width: preview.width - 90; color: "#C7C7CC" }
            Bar { width: preview.width - 100; color: "#C7C7CC" }
            Bar { width: preview.width - 94; color: "#C7C7CC" }
        }
    }
}
