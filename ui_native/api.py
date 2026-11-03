"""Async client for the Local Clova HTTP API, exposed to QML.

The native UI keeps the Flask API as a fixed contract (V8.3 plan, U1-U5):
every read goes through the same endpoints the browser UI uses.
"""
import json
from urllib.parse import quote

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class ApiClient(QObject):
    libraryLoaded = Signal("QVariant")
    segmentsLoaded = Signal(str, "QVariant")
    requestFailed = Signal(str, str)  # what, message

    def __init__(self, base_url: str, parent=None):
        super().__init__(parent)
        self._base = base_url.rstrip("/")
        self._net = QNetworkAccessManager(self)

    @Property(str, constant=True)
    def baseUrl(self):
        return self._base

    @Slot(str, result=str)
    def url(self, path):
        """Absolute URL for an API path such as a segment's audio_url."""
        return path if path.startswith(("http://", "https://")) else self._base + path

    @Slot()
    def fetchLibrary(self):
        self._get("/api/library", "library", self.libraryLoaded.emit)

    @Slot(str)
    def fetchSegments(self, session_id):
        self._get(
            f"/api/segments?session_id={quote(session_id)}",
            "segments",
            lambda data: self.segmentsLoaded.emit(session_id, data),
        )

    def _get(self, path, what, on_ok):
        reply = self._net.get(QNetworkRequest(QUrl(self._base + path)))

        def done():
            reply.deleteLater()
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.requestFailed.emit(what, reply.errorString())
                return
            try:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
            except ValueError as exc:
                self.requestFailed.emit(what, f"invalid JSON: {exc}")
                return
            on_ok(data)

        reply.finished.connect(done)
