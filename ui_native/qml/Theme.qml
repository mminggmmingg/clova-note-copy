pragma Singleton
import QtQuick

// Design tokens taken from the web UI (web/app_v6.css, dark default and
// html[data-theme="light"]). Sizes are CSS px == Qt logical px.
QtObject {
    // "" follows the desktop; "dark"/"light" set by --theme or the sidebar toggle.
    property string override: ""
    readonly property bool dark: override === "dark" ? true
        : override === "light" ? false
        : Qt.styleHints.colorScheme !== Qt.ColorScheme.Light

    function ink(r, g, b, a) { return Qt.rgba(r / 255, g / 255, b / 255, a) }

    // Canvas
    readonly property color bg: dark ? "#090b0e" : "#f4f6fa"
    readonly property color glow: dark ? ink(124, 140, 255, .09) : ink(108, 122, 232, .12)
    readonly property color sidebarTop: dark ? "#0d1014" : "#ffffff"
    readonly property color sidebarBottom: dark ? "#0a0d10" : "#f7f9fc"
    readonly property color header: dark ? ink(9, 11, 14, .78) : ink(250, 251, 253, .86)

    // Text
    readonly property color text: dark ? "#f4f7fb" : "#172130"
    readonly property color muted: dark ? "#8f98a7" : "#667183"
    readonly property color muted2: dark ? "#626b78" : "#8a94a3"
    readonly property color line: dark ? ink(255, 255, 255, .075) : ink(24, 36, 54, .10)
    readonly property color lineStrong: dark ? ink(255, 255, 255, .13) : ink(24, 36, 54, .17)
    readonly property color rowLine: dark ? ink(255, 255, 255, .052) : ink(24, 36, 54, .07)
    readonly property color hover: dark ? ink(255, 255, 255, .035) : ink(24, 36, 54, .04)

    // Accent / status
    readonly property color accent: dark ? "#7c8cff" : "#6775e8"
    readonly property color accent2: "#a979ff"
    readonly property color accentSoft: dark ? ink(124, 140, 255, .14) : ink(103, 117, 232, .105)
    readonly property color green: "#5ed6a0"
    readonly property color greenText: dark ? "#73dbae" : "#2f8f63"
    readonly property color greenSoft: dark ? ink(94, 214, 160, .09) : ink(53, 168, 113, .105)
    readonly property color greenLine: ink(94, 214, 160, .14)
    readonly property color warnText: dark ? "#f3bd70" : "#a8661a"
    readonly property color warnSoft: ink(245, 158, 11, .11)
    readonly property color red: "#ff6d75"

    // Sidebar pieces
    readonly property color brandSub: dark ? "#626b78" : "#536071"
    readonly property color labelRow: dark ? "#666f7c" : "#536071"
    readonly property color semester: dark ? "#5d6673" : "#536071"
    readonly property color subjectName: dark ? "#b5bdc8" : "#4e5a69"
    readonly property color subjectSub: dark ? "#596473" : "#7a8595"
    readonly property color subjectCount: dark ? "#606977" : "#8a94a3"
    readonly property color chevron: dark ? "#59616d" : "#8a94a3"
    readonly property color sessionTitle: dark ? "#afb7c3" : "#536071"
    readonly property color sessionTitleActive: dark ? "#eef1f7" : "#1d2938"
    readonly property color sessionMeta: dark ? "#555e69" : "#8a94a3"
    readonly property color sessionDot: dark ? "#3d454f" : "#c3cad4"
    readonly property color searchBg: dark ? ink(255, 255, 255, .025) : ink(255, 255, 255, .9)
    readonly property color placeholder: dark ? "#555e6a" : "#9aa4b1"
    readonly property color runtime: dark ? "#58616d" : "#536071"

    // Workspace pieces
    readonly property color pillText: dark ? "#a9b3c0" : "#596678"
    readonly property color pillBg: dark ? ink(255, 255, 255, .045) : ink(24, 36, 54, .045)
    readonly property color stats: dark ? "#5f6875" : "#7a8595"
    readonly property color time: dark ? "#5b6470" : "#8793a3"
    readonly property color segIndex: dark ? "#555e69" : "#8a94a3"
    readonly property color chipText: dark ? "#647080" : "#647183"
    readonly property color chipBg: dark ? ink(255, 255, 255, .035) : ink(24, 36, 54, .055)
    readonly property color transcript: dark ? "#f4f7fb" : "#111318"
    readonly property color playIcon: dark ? "#606a77" : "#8793a3"
    readonly property color nowPlaying: dark ? "#7f8cff" : "#5b68d8"
    readonly property color wordHover: dark ? ink(255, 255, 255, .055) : ink(24, 36, 54, .06)
    readonly property color wordPlaying: ink(255, 214, 102, .15)
    readonly property color wordPlayingUnder: ink(255, 214, 102, .22)
    readonly property color controlBg: dark ? ink(255, 255, 255, .026) : ink(255, 255, 255, .9)
    readonly property color heroText: dark ? "#e9edf3" : "#1d2938"
    readonly property color heroSub: dark ? "#727b89" : "#7a8595"
    readonly property color heroKicker: dark ? "#737d8b" : "#8a94a3"

    readonly property string family: "Noto Sans CJK KR"
}
