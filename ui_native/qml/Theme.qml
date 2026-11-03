pragma Singleton
import QtQuick

// Design tokens for the three themes picked in Settings (designs in the V8.3
// plan, "디자인 시안"):
//   paper   — 종이 노트: warm paper ground, a white page card, serif body,
//             a dark recording pill at the bottom (after Granola / Craft).
//   studio  — 스튜디오: dark workroom, recording bar, session info panel,
//             transport bar (after Linear).
//   classic — 클래식 라이트: subjects | lectures | transcript, a large
//             recording card (after Apple Voice Memos / Bear).
// Sizes are CSS px (== Qt logical px); fractional sizes go through pt().
QtObject {
    property string mode: "paper"
    // Transcript face: "auto" (the theme's own) | "serif" | "sans" | "hand".
    property string bodyFont: "auto"
    // Set by Main.qml from __main__.py; the UI font when the bundled face is missing.
    property string handFamily: "Nanum Pen Script"

    readonly property bool paper: mode === "paper"
    readonly property bool studio: mode === "studio"
    readonly property bool classic: mode === "classic"

    function pick(p, s, c) { return studio ? s : (classic ? c : p) }
    function pt(px) { return px * 0.75 }
    function ink(r, g, b, a) { return Qt.rgba(r / 255, g / 255, b / 255, a) }

    // Fonts (all installed with the system or bundled in ui_native/fonts).
    readonly property string family: "Noto Sans CJK KR"
    readonly property string serifFamily: "Noto Serif CJK KR"
    readonly property string monoFamily: "Noto Sans Mono CJK KR"
    readonly property string titleFamily: paper ? serifFamily : family
    readonly property string timeFamily: studio ? monoFamily : family
    readonly property string bodyKind: bodyFont !== "auto" ? bodyFont : pick("serif", "sans", "sans")
    readonly property string bodyFamily: bodyKind === "serif" ? serifFamily : (bodyKind === "hand" ? handFamily : family)
    readonly property real bodyPx: bodyKind === "hand" ? 24 : pick(17, 15.5, 17)
    readonly property real bodyLine: Math.round(bodyPx * (bodyKind === "hand" ? 1.45 : pick(1.8, 1.75, 1.75)))

    // Grounds and surfaces
    readonly property color bg: pick("#F6F3ED", "#121214", "#FFFFFF")
    readonly property color sidebarBg: pick("#F6F3ED", "#0D0D0F", "#F2F2F0")
    readonly property color sidebarLine: pick("transparent", "#1E1E22", "#E3E3E1")
    readonly property color paneLine: pick("#E9E4DA", "#1E1E22", "#ECECEF")
    readonly property color surface: pick("#FFFFFF", "#17171A", "#FAFAFA")
    readonly property color surfaceLine: pick("#E9E4DA", "#26262B", "#ECECEF")
    readonly property color panelLine: pick("#E9E4DA", "#222226", "#ECECEF")
    readonly property color control: pick("#EDE8DF", "#17171A", "#F2F2F0")
    readonly property color chip: pick("#F3EFE7", "#1D1D22", "#F2F2F0")
    readonly property color hover: pick(ink(60, 50, 30, .06), "#18181C", "#E9E9E7")
    readonly property color rowHover: pick("#FCFAF6", "#16161A", "#FAFAFA")
    readonly property color selected: pick("#FFFFFF", "#1D1D22", "#E2E2E0")

    // Text
    readonly property color text: pick("#24211C", "#E9E9EC", "#1C1C1E")
    readonly property color heading: pick("#1F1C18", "#F4F4F6", "#1C1C1E")
    readonly property color body: pick("#2E2A24", "#DCDCE0", "#1C1C1E")
    readonly property color subtle: pick("#3D3830", "#B9B9C0", "#4A4A4F")
    readonly property color muted: pick("#6B655B", "#8E8E96", "#6E6E73")
    readonly property color line: pick("#EFEAE1", "#222226", "#F0F0F2")

    // Accent and status
    readonly property color accent: pick("#3E6A4F", "#8B8EFF", "#E5484D")
    readonly property color accentText: pick("#3E6A4F", "#A9ABFF", "#C9302C")
    readonly property color focus: pick("#3E6A4F", "#8B8EFF", "#0A84FF")
    readonly property color rec: pick("#E5574B", "#FF5F57", "#E5484D")
    readonly property color recText: pick("#B23A31", "#FF8A84", "#C9302C")
    readonly property color ok: pick("#3E6A4F", "#63C29A", "#34C759")
    readonly property color warnText: pick("#8A5A12", "#F0B45A", "#9A5B00")
    readonly property color warnBg: pick("#FBF3E2", "#2A2213", "#FFF6E5")
    readonly property color errorText: pick("#9E3128", "#FF8A84", "#B42318")
    readonly property color errorBg: pick("#FBEDEB", "#2A1517", "#FDECEC")

    // Transcript
    readonly property color playingRow: pick("#FBF8F1", "#1D1D22", "transparent")
    readonly property color playingTime: pick("#24211C", "#A9ABFF", "#C9302C")
    readonly property color wordPlaying: pick("#FCE7A0", ink(139, 142, 255, .26), "#FFE58F")
    readonly property color wordHover: pick(ink(60, 50, 30, .07), ink(255, 255, 255, .06), ink(0, 0, 0, .05))
    readonly property color liveRow: pick("transparent", "#16161D", "transparent")
    readonly property color liveText: pick("#6B655B", "#B4B5D8", "#6E6E73")
    readonly property string liveLabel: pick("지금", "LIVE", "실시간")
    readonly property color scrollbar: pick(ink(60, 50, 30, .22), "#2E2E34", "#D1D1D6")

    // Dialogs, fields, toast
    readonly property color dim: pick(ink(36, 33, 28, .28), ink(0, 0, 0, .6), ink(0, 0, 0, .22))
    readonly property color dialogBg: pick("#FFFFFF", "#17171A", "#FFFFFF")
    readonly property color dialogLine: pick("#E9E4DA", "#26262B", "#E5E5EA")
    readonly property color fieldBg: pick("#FFFFFF", "#0D0D0F", "#F2F2F0")
    readonly property color fieldLine: pick("#E3DDD2", "#26262B", "transparent")
    readonly property color toastBg: pick("#24211C", "#26262B", "#1C1C1E")
    readonly property color toastText: pick("#F6F3ED", "#F4F4F6", "#FFFFFF")
    readonly property real radius: pick(10, 8, 9)

    // One color per subject (studio squares, classic letter badges); white
    // text on the classic colors passes 4.5:1.
    readonly property var subjectPalette: pick(
        ["#5B8C6B", "#B07A3E", "#5A7FA8", "#9A6A8E", "#7A8B3E", "#A65A4E"],
        ["#6E9BF5", "#E3A857", "#63C29A", "#C384E8", "#5EC2B7", "#F0A05A"],
        ["#2563EB", "#B45309", "#047857", "#6D28D9", "#BE185D", "#0E7490"])
    function subjectColor(key) {
        if (!key) return pick("#9A9186", "#5F5F67", "#8E8E93")
        let h = 0
        for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0
        return subjectPalette[h % subjectPalette.length]
    }
}
