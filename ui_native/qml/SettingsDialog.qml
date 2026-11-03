import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Settings: the screen theme (paper / studio / classic, applied at once),
// the transcript face, and app quit.
ModalCard {
    id: dlg
    objectName: "settingsDialog"

    required property var app
    property bool handAvailable: true

    signal themePicked(string mode)
    signal bodyFontPicked(string kind)

    title: "설정"
    cardWidth: 640

    readonly property var themes: [
        { mode: "paper", name: "종이 노트", desc: "따뜻한 종이 위의 강의록. 명조 본문, 아래쪽 녹음 막대." },
        { mode: "studio", name: "스튜디오", desc: "어두운 작업실. 녹음 바와 세션 정보, 재생 막대." },
        { mode: "classic", name: "클래식 라이트", desc: "과목 · 강의 · 본문 3단. 큰 녹음 카드." }
    ]
    readonly property var faces: [
        { kind: "auto", label: "테마 기본" },
        { kind: "serif", label: "명조" },
        { kind: "sans", label: "고딕" },
        { kind: "hand", label: "손글씨" }
    ]

    component SectionLabel: Label {
        color: Theme.muted
        font.pixelSize: 13
        font.weight: 600
    }

    SectionLabel { text: "화면 테마" }

    RowLayout {
        Layout.fillWidth: true
        Layout.bottomMargin: 6
        spacing: 12
        Repeater {
            model: dlg.themes
            delegate: Rectangle {
                id: card
                required property var modelData
                readonly property bool current: Theme.mode === modelData.mode
                Layout.fillWidth: true
                Layout.preferredWidth: 1
                implicitHeight: cardBody.implicitHeight + 20
                radius: 12
                color: hover.hovered && !current ? Theme.rowHover : "transparent"
                border.width: current ? 2 : 1
                border.color: current ? Theme.focus : Theme.dialogLine
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.name
                Accessible.checked: current
                HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: dlg.themePicked(card.modelData.mode) }

                ColumnLayout {
                    id: cardBody
                    x: 10
                    y: 10
                    width: parent.width - 20
                    spacing: 8
                    ThemePreview {
                        Layout.fillWidth: true
                        implicitHeight: 96
                        mode: card.modelData.mode
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 2
                        spacing: 6
                        Label {
                            Layout.fillWidth: true
                            text: card.modelData.name
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: 600
                        }
                        Icon {
                            visible: card.current
                            name: "check"
                            stroke: 2.2
                            color: Theme.focus
                            implicitWidth: 16
                            implicitHeight: 16
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        Layout.leftMargin: 2
                        text: card.modelData.desc
                        color: Theme.muted
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                        lineHeight: 1.25
                    }
                }
            }
        }
    }

    SectionLabel { text: "본문 글꼴" }

    Row {
        Layout.bottomMargin: 6
        spacing: 8
        Repeater {
            model: dlg.faces
            delegate: Rectangle {
                id: face
                required property var modelData
                readonly property bool current: Theme.bodyFont === modelData.kind
                readonly property bool enabled: modelData.kind !== "hand" || dlg.handAvailable
                width: faceLabel.implicitWidth + 28
                height: 36
                radius: Theme.radius
                opacity: enabled ? 1 : 0.4
                color: current ? Theme.selected : (hover.hovered ? Theme.hover : "transparent")
                border.width: 1
                border.color: current ? Theme.focus : Theme.dialogLine
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checked: current
                Label {
                    id: faceLabel
                    anchors.centerIn: parent
                    text: face.modelData.label
                    color: Theme.text
                    font.family: face.modelData.kind === "serif" ? Theme.serifFamily
                        : face.modelData.kind === "hand" ? Theme.handFamily : Theme.family
                    font.pixelSize: face.modelData.kind === "hand" ? 19 : 14
                    font.weight: face.current ? 600 : 400
                }
                HoverHandler { id: hover; cursorShape: face.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor }
                TapHandler { onTapped: if (face.enabled) dlg.bodyFontPicked(face.modelData.kind) }
            }
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.topMargin: 4
        implicitHeight: 1
        color: Theme.dialogLine
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10
        ActionButton {
            variant: "danger"
            icon: "power"
            iconSize: 15
            text: "앱 종료"
            fontPx: 13
            onClicked: { dlg.close(); dlg.app.requestShutdown() }
        }
        Label {
            Layout.fillWidth: true
            text: "런타임과 종료 컨트롤러를 끕니다. 녹음 중에는 정지 후 가능합니다."
            color: Theme.muted
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        ActionButton {
            text: "닫기"
            fontPx: 13
            onClicked: dlg.close()
        }
    }
}
