"""Start the Local Clova native UI.

  .venv-ui/bin/python -m ui_native                      # backend on :8000
  .venv-ui/bin/python -m ui_native --backend http://127.0.0.1:8001
  .venv-ui/bin/python -m ui_native --open-session <id> --screenshot shot.png

--screenshot renders offscreen, saves a PNG once data has loaded, and exits
(used to check layouts without opening a window).
"""
import argparse
import os
import sys
from pathlib import Path

QML_MAIN = Path(__file__).with_name("qml") / "Main.qml"
FONT_DIR = Path(__file__).with_name("fonts")
# Notebook-theme handwriting (the web loads it from Google Fonts).
HAND_FAMILIES = ("Nanum Pen Script", "Nanum Pen", "나눔손글씨 펜", "NanumPen")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ui_native", description="Local Clova native UI")
    ap.add_argument("--backend", default="http://127.0.0.1:8000")
    ap.add_argument("--open-session", default="")
    ap.add_argument("--screenshot", type=Path)
    ap.add_argument("--size", default="1280x820", help="window size WxH")
    ap.add_argument("--theme", choices=["notebook", "dark", "light"], help="override the remembered theme")
    args, qt_args = ap.parse_known_args(argv)

    if args.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")

    # Import after the platform environment is set.
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication
    from PySide6.QtQml import QQmlApplicationEngine
    from PySide6.QtQuickControls2 import QQuickStyle

    from .api import ApiClient

    app = QGuiApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Local Clova")
    app.setOrganizationName("LocalClova")  # QtCore Settings: remembers the theme
    app.setDesktopFileName("local-clova")
    # One CJK font for Hangul and Latin alike: mixed-script words in a
    # transcript line then share metrics instead of jumping baselines.
    app.setFont(QFont("Noto Sans CJK KR"))
    for font_file in sorted(FONT_DIR.glob("*.[ot]tf")):
        QFontDatabase.addApplicationFont(str(font_file))
    families = set(QFontDatabase.families())
    hand_family = next((f for f in HAND_FAMILIES if f in families), "")
    QQuickStyle.setStyle("Basic")

    api = ApiClient(args.backend)
    width, height = (int(x) for x in args.size.lower().split("x"))
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({
        "api": api,
        "initialSessionId": args.open_session,
        "initialTheme": args.theme or "",
        "handFamily": hand_family,
        "width": width,
        "height": height,
    })
    engine.load(str(QML_MAIN))
    if not engine.rootObjects():
        return 1

    if args.screenshot:
        window = engine.rootObjects()[0]
        saved = []

        def grab():
            if saved:
                return
            saved.append(True)
            window.grabWindow().save(str(args.screenshot))
            app.quit()

        if args.open_session:
            api.segmentsLoaded.connect(lambda *_: QTimer.singleShot(1500, grab))
        else:
            api.libraryLoaded.connect(lambda *_: QTimer.singleShot(1000, grab))
        api.requestFailed.connect(lambda *_: QTimer.singleShot(500, grab))
        QTimer.singleShot(20000, grab)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
