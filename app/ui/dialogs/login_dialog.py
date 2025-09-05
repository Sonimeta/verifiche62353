# pip install PySide6 requests
from PySide6.QtCore import Qt, QTimer, QPoint, QSettings
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QLabel, QDialogButtonBox, QMessageBox,
    QFormLayout, QFrame, QGraphicsDropShadowEffect, QSizePolicy, QSpacerItem
)
import requests

# Config di fallback se non esiste il modulo app.config
try:
    from app import config
    from app.config import STYLESHEET
except ModuleNotFoundError:
    class DummyConfig:
        SERVER_URL = "http://localhost:8000"
    config = DummyConfig()
    STYLESHEET = ""

# --- Extra stylesheet moderno per una UI più curata ---
EXTRA_STYLESHEET = r"""
* { font-family: 'Segoe UI', 'Inter', system-ui; }
QDialog { background: transparent; }
QFrame#card {
    background: #ffffff;
    border-radius: 16px;
}
QLabel#title {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    background: transparent;
    alignment: center;
}
QLabel#subtitle {
    font-size: 13px;
    color: #64748b;
    background: transparent;
}
QLabel { color: #334155; background: transparent; }

QLineEdit#input {
    padding: 8px 12px;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    background: #ffffff;
    selection-background-color: #bfdbfe;
}
QLineEdit#input:focus {
    border: 1px solid #2563eb;
    background: #ffffff;
}
QLineEdit#input:disabled {
    color: #94a3b8;
    background: #f8fafc;
}

QDialogButtonBox QPushButton {
    padding: 8px 14px;
    border-radius: 10px;
    background: #e2e8f0;
    border: none;
}
QDialogButtonBox QPushButton:hover { background: #cbd5e1; }
QDialogButtonBox QPushButton:pressed { background: #94a3b8; }
QDialogButtonBox QPushButton:disabled { background: #e5e7eb; color: #94a3b8; }

/* Pulsante primario (Login) usando :default */
QDialogButtonBox QPushButton:default {
    background: #2563eb;
    color: white;
}
QDialogButtonBox QPushButton:default:hover { background: #1d4ed8; }
QDialogButtonBox QPushButton:default:pressed { background: #1e40af; }
"""


class LoginDialog(QDialog):
    """
    Versione "solo riquadro": la finestra mostra unicamente la card bianca con ombra,
    senza spazio/grigio intorno. È anche frameless e con sfondo trasparente
    per un look pulito.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LoginDialog")
        self.setWindowTitle("Login - Safety Test Manager")
        self.setModal(True)
        self.token_data = None

        # --- Mostra SOLO il riquadro ---
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ------- Root layout -------
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(0)

        # ------- Card con ombra -------
        self.card = QFrame()
        self.card.setObjectName("card")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(28, 28, 28, 20)
        card_layout.setSpacing(18)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 16)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.card.setGraphicsEffect(shadow)

        title = QLabel("Accedi")
        title.setObjectName("title")
        subtitle = QLabel("Inserisci le tue credenziali per continuare.")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)

        # ------- Form -------
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignTop)

        self.username_edit = QLineEdit()
        self.settings = QSettings("MyCompany", "SafetyTester")
        self.username_edit.setText(self.settings.value("last_username",""))
        self.username_edit.setObjectName("input")
        self.username_edit.setPlaceholderText("Nome utente")
        self.username_edit.setClearButtonEnabled(True)

        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("input")
        self.password_edit.setPlaceholderText("Password")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setClearButtonEnabled(True)

        # Toggle mostra/nascondi password
        self.toggle_action = QAction("Mostra", self.password_edit)
        self.toggle_action.triggered.connect(self._toggle_password)
        self.password_edit.addAction(self.toggle_action, QLineEdit.TrailingPosition)

        form_layout.addRow(QLabel("Nome Utente:"), self.username_edit)
        form_layout.addRow(QLabel("Password:"), self.password_edit)

        # ------- Pulsanti -------
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Login")
        buttons.button(QDialogButtonBox.Cancel).setText("Annulla")

        buttons.button(QDialogButtonBox.Ok).setDefault(True)
        buttons.button(QDialogButtonBox.Ok).setAutoDefault(True)

        buttons.accepted.connect(self.attempt_login)
        buttons.rejected.connect(self.reject)

        # Invio = login, Esc = annulla
        self.password_edit.returnPressed.connect(self.attempt_login)
        self.username_edit.returnPressed.connect(self.password_edit.setFocus)
        self.addAction(self._make_esc_action())

        # Compose
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addLayout(form_layout)
        card_layout.addSpacing(8)
        card_layout.addWidget(buttons)

        root.addWidget(self.card, 0, Qt.AlignCenter)

        # Stile e dimensioni compatte
        self._apply_style()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

        # Drag finestra
        self._drag_pos: QPoint | None = None
        self.card.mousePressEvent = self._start_drag
        self.card.mouseMoveEvent = self._do_drag
        self.card.mouseReleaseEvent = self._end_drag

    # ------------------ UI helpers ------------------

    def _make_esc_action(self):
        act = QAction(self)
        act.setShortcut("Esc")
        act.triggered.connect(self.reject)
        return act

    def _apply_style(self):
        combined = ""
        try:
            combined = STYLESHEET
        except Exception:
            combined = ""
        self.setStyleSheet(combined + "\n" + EXTRA_STYLESHEET)

    def _toggle_password(self):
        if self.password_edit.echoMode() == QLineEdit.Password:
            self.password_edit.setEchoMode(QLineEdit.Normal)
            self.toggle_action.setText("Nascondi")
        else:
            self.password_edit.setEchoMode(QLineEdit.Password)
            self.toggle_action.setText("Mostra")

    # ------------------ Login logic ------------------

    def attempt_login(self):
        username = self.username_edit.text().strip()
        self.settings.setValue("last_username", username)
        password = self.password_edit.text()

        if not username or not password:
            QMessageBox.warning(self, "Dati Mancanti", "Inserire nome utente e password.")
            self._highlight_empty()
            return

        token_url = f"{config.SERVER_URL}/token"

        try:
            self.setEnabled(False)
            response = requests.post(
                token_url,
                data={"username": username, "password": password},
                timeout=10,
            )

            if response.status_code == 200:
                try:
                    self.token_data = response.json()
                except ValueError:
                    QMessageBox.critical(self, "Errore Server", "Risposta non valida dal server (JSON non parsabile).")
                    self.setEnabled(True)
                    return
                self.accept()
            elif response.status_code in (401, 422):
                QMessageBox.warning(self, "Login Fallito", "Nome utente o password non corretti.")
                self.setEnabled(True)
            else:
                QMessageBox.critical(self, "Errore Server", f"Errore inatteso: {response.status_code}")
                self.setEnabled(True)

        except requests.RequestException as e:
            detail = ""
            try:
                if e.response is not None and 'application/json' in e.response.headers.get('content-type',''):
                    detail = e.response.json().get("detail","")
            except Exception:
                pass
            QMessageBox.critical(self, "Errore di Connessione", f"Connessione fallita.\n{detail or e}")

            self.setEnabled(True)

    def _highlight_empty(self):
        base = self.styleSheet()
        for w in (self.username_edit, self.password_edit):
            if not w.text().strip():
                w.setStyleSheet(base + " QLineEdit#input { border: 1px solid #f87171; }")
        QTimer.singleShot(700, self._apply_style)

    # --------- drag della finestra frameless ---------
    def _start_drag(self, e):
        if e.buttons() & Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def _do_drag(self, e):
        if self._drag_pos is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def _end_drag(self, e):
        self._drag_pos = None
