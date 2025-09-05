from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QLabel, QDialogButtonBox, QFormLayout, QComboBox

class UserDetailDialog(QDialog):
    def __init__(self, user_data=None, parent=None):
        super().__init__(parent)
        self.is_edit_mode = user_data is not None
        
        title = "Modifica Utente" if self.is_edit_mode else "Aggiungi Nuovo Utente"
        self.setWindowTitle(title)
        
        data = user_data or {}
        
        layout = QFormLayout(self)
        self.username_edit = QLineEdit(data.get('username', ''))
        self.first_name_edit = QLineEdit(data.get('first_name', ''))
        self.last_name_edit = QLineEdit(data.get('last_name', ''))
        self.password_edit = QLineEdit()
        self.role_combo = QComboBox()
        self.role_combo.addItems(['technician', 'moderator', 'admin'])
        self.role_combo.setCurrentText(data.get('role', 'technician'))
        
        if self.is_edit_mode:
            self.username_edit.setReadOnly(True) # Non si può cambiare lo username
            self.password_edit.setPlaceholderText("Lasciare vuoto per non cambiare")
        
        layout.addRow("Username:", self.username_edit)
        layout.addRow("Nome:", self.first_name_edit)
        layout.addRow("Cognome:", self.last_name_edit)
        layout.addRow("Password:", self.password_edit)
        layout.addRow("Ruolo:", self.role_combo)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        """Restituisce i dati inseriti nella dialog."""
        data = {
            "username": self.username_edit.text().strip(),
            "first_name": self.first_name_edit.text().strip(),
            "last_name": self.last_name_edit.text().strip(),
            "role": self.role_combo.currentText(),
            "password": self.password_edit.text()
        }
        # In modalità modifica, non includere la password se il campo è vuoto
        if self.is_edit_mode and not data["password"]:
            del data["password"]
        return data