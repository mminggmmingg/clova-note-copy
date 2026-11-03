pragma Singleton
import QtQuick

// Design tokens taken from the web UI (web/app_v6.css): dark default,
// html[data-theme="light"] and html[data-theme="notebook"]. Sizes are CSS px
// (== Qt logical px); fractional px sizes go through pt() because QML's
// font.pixelSize only takes integers.
QtObject {
    // "notebook" | "dark" | "light"; Main.qml restores the saved choice.
    property string mode: "notebook"
    readonly property bool notebook: mode === "notebook"
    readonly property bool dark: mode === "dark"

    function pt(px) { return px * 0.75 }
    function ink(r, g, b, a) { return Qt.rgba(r / 255, g / 255, b / 255, a) }
    function pick(d, l, n) { return notebook ? n : (dark ? d : l) }
    function next() { return { notebook: "dark", dark: "light", light: "notebook" }[mode] || "notebook" }

    // Canvas
    readonly property color bg: pick("#090b0e", "#f4f6fa", "#f8f1e5")
    readonly property color glow: pick(ink(124, 140, 255, .09), ink(108, 122, 232, .12), "transparent")
    readonly property color sidebarTop: pick("#0d1014", "#ffffff", "#faf5ee")
    readonly property color sidebarBottom: pick("#0a0d10", "#f7f9fc", "#f7f1e7")
    readonly property color header: pick(ink(9, 11, 14, .78), ink(250, 251, 253, .86), "#f9f3ea")
    readonly property color headerLine: pick(ink(255, 255, 255, .075), ink(24, 36, 54, .10), ink(112, 91, 67, .13))

    // Text
    readonly property color text: pick("#f4f7fb", "#172130", "#40382f")
    readonly property color heading: pick("#f4f7fb", "#172130", "#352f28")
    readonly property color muted: pick("#8f98a7", "#667183", "#756d64")
    readonly property color muted2: pick("#626b78", "#8a94a3", "#9a9186")
    readonly property color line: pick(ink(255, 255, 255, .075), ink(24, 36, 54, .10), ink(102, 84, 65, .13))
    readonly property color lineStrong: pick(ink(255, 255, 255, .13), ink(24, 36, 54, .17), ink(102, 84, 65, .22))
    readonly property color rowLine: pick(ink(255, 255, 255, .052), ink(24, 36, 54, .07), ink(96, 82, 67, .085))
    readonly property color hover: pick(ink(255, 255, 255, .035), ink(24, 36, 54, .04), ink(202, 169, 110, .06))

    // Accent / status
    readonly property color accent: pick("#7c8cff", "#6775e8", "#b98a49")
    readonly property color accentSoft: pick(ink(124, 140, 255, .14), ink(103, 117, 232, .105), ink(185, 138, 73, .11))
    readonly property color green: pick("#5ed6a0", "#5ed6a0", "#5b9972")
    readonly property color greenText: pick("#73dbae", "#2f8f63", "#5f8164")
    readonly property color greenSoft: pick(ink(94, 214, 160, .09), ink(53, 168, 113, .105), "#e3efe0")
    readonly property color greenLine: pick(ink(94, 214, 160, .14), ink(94, 214, 160, .14), ink(124, 96, 63, .13))
    readonly property color warnText: pick("#f3bd70", "#a8661a", "#a8661a")
    readonly property color warnSoft: ink(245, 158, 11, .11)
    readonly property color red: pick("#ff6d75", "#ff6d75", "#ca6e6e")

    // Paper (notebook) surfaces: buttons, cards, tape
    readonly property color paperTop: ink(255, 255, 255, .94)
    readonly property color paperBottom: ink(252, 244, 232, .96)
    readonly property color paperBorder: ink(124, 96, 63, .20)
    readonly property color paperText: "#625548"
    readonly property color paperLip: ink(175, 145, 105, .12)       // 0 3px 0 under-edge
    readonly property color paperShadow: ink(92, 71, 48, .08)       // soft drop
    readonly property color tape: ink(227, 207, 166, .62)
    readonly property color tapeBorder: ink(157, 126, 82, .08)

    // Sidebar pieces
    readonly property color brandStrong: pick("#f4f7fb", "#536071", "#342d26")
    readonly property color brandSub: pick("#626b78", "#536071", "#9a8d7e")
    readonly property color labelRow: pick("#666f7c", "#536071", "#93897d")
    readonly property color semester: pick("#5d6673", "#536071", "#93897d")
    readonly property color subjectName: pick("#b5bdc8", "#4e5a69", "#645b51")
    readonly property color subjectSub: pick("#596473", "#7a8595", "#a09280")
    readonly property color subjectCount: pick("#606977", "#8a94a3", "#606977")
    readonly property color chevron: pick("#59616d", "#8a94a3", "#93897d")
    readonly property color sessionTitle: pick("#afb7c3", "#536071", "#625a51")
    readonly property color sessionTitleActive: pick("#eef1f7", "#1d2938", "#352f28")
    readonly property color sessionMeta: pick("#555e69", "#8a94a3", "#93897d")
    readonly property color sessionDot: pick("#3d454f", "#c3cad4", "#5a5148")
    readonly property color activeFrom: pick(ink(124, 140, 255, .13), ink(103, 117, 232, .13), ink(219, 180, 104, .20))
    readonly property color activeTo: pick(ink(124, 140, 255, .035), ink(103, 117, 232, .035), ink(219, 180, 104, .055))
    readonly property color activeDot: pick("#7c8cff", "#6775e8", "#c68f57")
    readonly property color searchBg: pick(ink(255, 255, 255, .025), ink(255, 255, 255, .9), "#fffaf1")
    readonly property color searchBorder: pick(ink(255, 255, 255, .075), ink(24, 36, 54, .10), ink(124, 96, 63, .16))
    readonly property color placeholder: pick("#555e6a", "#9aa4b1", "#a89e91")
    readonly property color runtime: pick("#58616d", "#536071", "#93897d")

    // Workspace pieces
    readonly property color pillText: pick("#a9b3c0", "#596678", "#706253")
    readonly property color pillBg: pick(ink(255, 255, 255, .045), ink(24, 36, 54, .045), "#f7eddc")
    readonly property color stats: pick("#5f6875", "#7a8595", "#8a8075")
    readonly property color time: pick("#5b6470", "#8793a3", "#9b9185")
    readonly property color segIndex: pick("#555e69", "#8a94a3", "#8a8075")
    readonly property color chipText: pick("#647080", "#647183", "#756a5e")
    readonly property color chipBg: pick(ink(255, 255, 255, .035), ink(24, 36, 54, .055), ink(111, 88, 62, .065))
    readonly property color transcript: pick("#f4f7fb", "#111318", "#2d2924")
    readonly property color playIcon: pick("#606a77", "#8793a3", "#8a8075")
    readonly property color nowPlaying: pick("#7f8cff", "#5b68d8", ink(107, 82, 38, .64))
    readonly property color wordHover: pick(ink(255, 255, 255, .055), ink(24, 36, 54, .06), ink(228, 193, 91, .16))
    readonly property color wordPlaying: pick(ink(255, 214, 102, .15), ink(255, 214, 102, .15), ink(255, 222, 92, .24))
    readonly property color wordPlayingUnder: pick(ink(255, 214, 102, .22), ink(255, 214, 102, .22), ink(244, 199, 57, .28))
    readonly property color ruling: ink(101, 137, 154, .11)          // notebook ruled lines
    readonly property color marginLine: ink(199, 103, 103, .18)      // notebook red margin
    readonly property color stickyNote: "#fff0a6"
    readonly property color stickyBorder: ink(169, 128, 51, .16)
    readonly property color stickyShadow: ink(105, 81, 39, .11)
    readonly property color heroText: pick("#e9edf3", "#1d2938", "#5a5045")
    readonly property color heroSub: pick("#727b89", "#7a8595", "#7d7266")
    readonly property color heroKicker: pick("#737d8b", "#8a94a3", "#806f5b")
    readonly property color pdfTile: "#f4e7bd"
    readonly property color pdfTileBorder: ink(151, 116, 66, .33)
    readonly property color pdfRed: "#e65963"

    readonly property string family: "Noto Sans CJK KR"
    // Bundled in ui_native/fonts if present (see __main__.py); the web loads
    // the same face from Google Fonts. Falls back to the UI font otherwise.
    property string handFamily: "Nanum Pen Script"
}
