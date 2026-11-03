"""Async client for the Local Clova HTTP API, exposed to QML.

The native UI keeps the Flask API as a fixed contract (V8.3 plan, U1-U5):
every read and every recording action goes through the same endpoints the
browser UI uses. The UI is control-only; audio comes from the host capture
daemon, never from this process.
"""
import json
from urllib.parse import quote

from PySide6.QtCore import Property, QByteArray, QObject, QUrl, Signal, Slot
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

# Stop waits up to 25 s for the capture daemon to flush RAW (_native_capture_stop).
ACTION_TIMEOUT_MS = 60000
READ_TIMEOUT_MS = 15000
STATUS_TIMEOUT_MS = 4000


class ApiClient(QObject):
    libraryLoaded = Signal("QVariant")
    segmentsLoaded = Signal(str, "QVariant")
    pdfsLoaded = Signal(str, "QVariant")
    recordingStatusLoaded = Signal(str, "QVariant")
    requestFailed = Signal(str, str)  # what, message
    # Write actions: "start" | "resume" | "finish" | "subject" | "shutdown".
    actionDone = Signal(str, str, "QVariant")  # action, session_id, data
    actionFailed = Signal(str, str, str)  # action, session_id, message

    def __init__(self, base_url: str, client_id: str = "", parent=None):
        super().__init__(parent)
        self._base = base_url.rstrip("/")
        # Recorder lease id (api_resume): the same client may reconnect to a
        # session it is still recording without waiting for the lease timeout.
        self._client_id = client_id
        self._net = QNetworkAccessManager(self)

    @Property(str, constant=True)
    def baseUrl(self):
        return self._base

    @Slot(str, result=str)
    def url(self, path):
        """Absolute URL for an API path such as a segment's audio_url."""
        return path if path.startswith(("http://", "https://")) else self._base + path

    # ------------------------------------------------------------ reads
    @Slot()
    def fetchLibrary(self):
        self._send("GET", "/api/library", None, READ_TIMEOUT_MS,
                   self.libraryLoaded.emit, lambda msg: self.requestFailed.emit("library", msg))

    @Slot(str)
    def fetchSegments(self, session_id):
        self._send("GET", f"/api/segments?session_id={quote(session_id)}", None, READ_TIMEOUT_MS,
                   lambda data: self.segmentsLoaded.emit(session_id, data),
                   lambda msg: self.requestFailed.emit("segments", msg))

    @Slot(str)
    def fetchPdfs(self, session_id):
        self._send("GET", f"/api/pdfs?session_id={quote(session_id)}", None, READ_TIMEOUT_MS,
                   lambda data: self.pdfsLoaded.emit(session_id, data),
                   lambda msg: self.requestFailed.emit("pdfs", msg))

    @Slot(str)
    def fetchRecordingStatus(self, session_id):
        self._send("GET", f"/api/recording/status?session_id={quote(session_id)}", None, STATUS_TIMEOUT_MS,
                   lambda data: self.recordingStatusLoaded.emit(session_id, data),
                   lambda msg: self.requestFailed.emit("status", msg))

    # ------------------------------------------------------------ recording
    @Slot(str, str)
    def startRecording(self, title, subject_id):
        body = {
            "title": title,
            "subject_id": subject_id,
            "client_id": self._client_id,
            # The web UI's defaults; the new-session form does not expose them.
            "denoise_strength": 2,
            "stt_audio_source": "raw",
        }
        self._action("start", "", "/api/start", body)

    @Slot(str)
    def resumeRecording(self, session_id):
        self._action("resume", session_id,
                     f"/api/resume?session_id={quote(session_id)}&client_id={quote(self._client_id)}")

    @Slot(str)
    def finishRecording(self, session_id):
        self._action("finish", session_id, f"/api/finish?session_id={quote(session_id)}")

    @Slot(str, str, str, str)
    def createSubject(self, name, semester, emoji, professor_name):
        body = {"name": name, "semester": semester, "emoji": emoji, "professor_name": professor_name}
        self._action("subject", "", "/api/subject", body)

    @Slot()
    def shutdownApp(self):
        self._action("shutdown", "", "/api/app/shutdown")

    # ------------------------------------------------------------ plumbing
    def _action(self, action, session_id, path, body=None):
        self._send("POST", path, body, ACTION_TIMEOUT_MS,
                   lambda data: self.actionDone.emit(action, session_id or str(data.get("session_id") or ""), data),
                   lambda msg: self.actionFailed.emit(action, session_id, msg))

    def _send(self, method, path, body, timeout_ms, on_ok, on_fail):
        request = QNetworkRequest(QUrl(self._base + path))
        request.setTransferTimeout(timeout_ms)
        if method == "GET":
            reply = self._net.get(request)
        else:
            request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            payload = json.dumps(body if body is not None else {}).encode("utf-8")
            reply = self._net.post(request, QByteArray(payload))

        def done():
            reply.deleteLater()
            raw = bytes(reply.readAll())
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                data = None
            if reply.error() != QNetworkReply.NetworkError.NoError:
                # Flask answers 4xx/5xx with {"error": ...}; prefer that text
                # over Qt's generic "server replied: CONFLICT".
                message = data.get("error") if isinstance(data, dict) and data.get("error") else reply.errorString()
                on_fail(str(message))
                return
            if not isinstance(data, dict):
                on_fail("invalid JSON response")
                return
            on_ok(data)

        reply.finished.connect(done)
