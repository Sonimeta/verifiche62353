# app/ui/dialogs/profile_manager_dialog.py
import json
import os
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, 
                               QMessageBox, QDialogButtonBox, QLineEdit, QTableWidget,
                               QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox,
                               QDoubleSpinBox, QComboBox, QLabel, QFormLayout, QListWidgetItem, QWidget)
from PySide6.QtCore import Qt
from app.data_models import VerificationProfile, Test, Limit
from app import services, config
import database

class ProfileDetailDialog(QDialog):
    """Dialog per creare o modificare un singolo profilo di verifica."""
    def __init__(self, profile: VerificationProfile = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dettagli Profilo di Verifica" if profile else "Nuovo Profilo di Verifica")
        self.setMinimumSize(800, 600)

        self.profile = profile or VerificationProfile(name="", tests=[])
        
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.profile_name_edit = QLineEdit(self.profile.name)
        form_layout.addRow("Nome Profilo:", self.profile_name_edit)
        layout.addLayout(form_layout)

        layout.addWidget(QLabel("Test del Profilo:"))
        self.tests_table = QTableWidget()
        self.tests_table.setColumnCount(5)
        self.tests_table.setHorizontalHeaderLabels(["Nome Test", "Parametro / Messaggio Pausa", "Limite Alto (μA/Ω)", "Parte Applicata?", "Tipo P.A."])
        self.tests_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.tests_table)

        buttons_layout = QHBoxLayout()
        add_test_btn = QPushButton("Aggiungi Test")
        remove_test_btn = QPushButton("Rimuovi Test Selezionato")
        buttons_layout.addStretch(); buttons_layout.addWidget(add_test_btn); buttons_layout.addWidget(remove_test_btn)
        layout.addLayout(buttons_layout)
        
        dialog_buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(dialog_buttons)

        add_test_btn.clicked.connect(self.add_test_row)
        remove_test_btn.clicked.connect(self.remove_test_row)
        dialog_buttons.accepted.connect(self.accept_changes)
        dialog_buttons.rejected.connect(self.reject)

        self.populate_table() # This line caused the error

    # --- THIS IS THE MISSING FUNCTION ---
    def populate_table(self):
        self.tests_table.setRowCount(0)
        for test in self.profile.tests:
            self.add_test_row(test_data=test)
    # --- END OF MISSING FUNCTION ---

    def on_test_type_changed(self, row):
        name_combo = self.tests_table.cellWidget(row, 0)
        is_pause = "PAUSA MANUALE" in name_combo.currentText()
        
        for col in range(1, 5):
            widget = self.tests_table.cellWidget(row, col)
            if widget:
                # The parameter field should always be enabled
                is_param_field = (col == 1)
                widget.setEnabled(is_param_field or not is_pause)
        
        param_edit = self.tests_table.cellWidget(row, 1)
        if is_pause:
            param_edit.setPlaceholderText("Inserisci il messaggio per la pausa...")
        else:
            param_edit.setPlaceholderText("")

    def add_test_row(self, test_data: Test = None):
        row = self.tests_table.rowCount()
        self.tests_table.insertRow(row)

        name_combo = QComboBox()
        test_names = ["Tensione alimentazione", "Resistenza conduttore di terra", "Corrente dispersione diretta dispositivo", "Corrente dispersione diretta P.A.", "--- PAUSA MANUALE ---"]
        name_combo.addItems(test_names)
        if test_data: name_combo.setCurrentText(test_data.name)
        self.tests_table.setCellWidget(row, 0, name_combo)
        
        param_edit = QLineEdit(test_data.parameter if test_data else "")
        self.tests_table.setCellWidget(row, 1, param_edit)

        limit_spinbox = QDoubleSpinBox(); limit_spinbox.setDecimals(3); limit_spinbox.setRange(0, 99999.999)
        if test_data and test_data.limits:
            first_limit_key = next(iter(test_data.limits))
            limit_value = test_data.limits[first_limit_key].high_value or 0.0
            limit_spinbox.setValue(limit_value)
        self.tests_table.setCellWidget(row, 2, limit_spinbox)
        
        checkbox_container = QWidget(); checkbox_layout = QHBoxLayout(checkbox_container)
        is_ap_checkbox = QCheckBox(); is_ap_checkbox.setChecked(test_data.is_applied_part_test if test_data else False)
        checkbox_layout.addWidget(is_ap_checkbox); checkbox_layout.setAlignment(Qt.AlignCenter); checkbox_layout.setContentsMargins(0,0,0,0)
        self.tests_table.setCellWidget(row, 3, checkbox_container)
        
        ap_type_combo = QComboBox(); ap_type_combo.addItems(["ST", "B", "BF", "CF"])
        if test_data and test_data.limits:
            first_limit_key = next(iter(test_data.limits))
            ap_type_str = first_limit_key.strip(": ")
            ap_type_combo.setCurrentText(ap_type_str)
        self.tests_table.setCellWidget(row, 4, ap_type_combo)

        name_combo.currentIndexChanged.connect(lambda: self.on_test_type_changed(row))
        self.on_test_type_changed(row)

    def remove_test_row(self):
        current_row = self.tests_table.currentRow()
        if current_row > -1: self.tests_table.removeRow(current_row)

    def accept_changes(self):
        if not self.profile_name_edit.text().strip():
            QMessageBox.warning(self, "Nome Mancante", "Il nome del profilo non può essere vuoto.")
            return

        self.profile.name = self.profile_name_edit.text().strip()
        self.profile.tests = []
        for row in range(self.tests_table.rowCount()):
            name = self.tests_table.cellWidget(row, 0).currentText()
            param = self.tests_table.cellWidget(row, 1).text()
            
            if "PAUSA MANUALE" in name:
                self.profile.tests.append(Test(name=name, parameter=param, limits={}, is_applied_part_test=False))
                continue
            
            limit_val = self.tests_table.cellWidget(row, 2).value()
            checkbox_container = self.tests_table.cellWidget(row, 3)
            is_ap_checkbox = checkbox_container.findChild(QCheckBox)
            is_ap = is_ap_checkbox.isChecked() if is_ap_checkbox else False
            ap_type = self.tests_table.cellWidget(row, 4).currentText()
            unit = "uA" if "Corrente" in name else ("Ohm" if "Resistenza" in name else "V")
            limits = {f"::{ap_type}": Limit(unit=unit, high_value=limit_val if limit_val > 0 else None)}
            self.profile.tests.append(Test(name=name, parameter=param, limits=limits, is_applied_part_test=is_ap))
        
        self.accept()


class ProfileManagerDialog(QDialog):
    """Dialog per visualizzare e gestire i profili dal database."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestione Profili di Verifica (Sincronizzati)")
        self.setMinimumSize(500, 400)
        self.profiles_changed = False

        layout = QVBoxLayout(self)
        self.profiles_list_widget = QListWidget()
        layout.addWidget(self.profiles_list_widget)

        buttons_layout = QHBoxLayout()
        add_btn = QPushButton("Nuovo...")
        edit_btn = QPushButton("Modifica...")
        delete_btn = QPushButton("Elimina")
        buttons_layout.addStretch()
        buttons_layout.addWidget(add_btn)
        buttons_layout.addWidget(edit_btn)
        buttons_layout.addWidget(delete_btn)
        layout.addLayout(buttons_layout)

        close_button = QDialogButtonBox(QDialogButtonBox.Close)
        layout.addWidget(close_button)

        # Connessioni
        add_btn.clicked.connect(self.add_profile)
        edit_btn.clicked.connect(self.edit_profile)
        delete_btn.clicked.connect(self.delete_profile)
        self.profiles_list_widget.itemDoubleClicked.connect(self.edit_profile)
        close_button.rejected.connect(self.reject)

        self.load_profiles_from_db()

    def load_profiles_from_db(self):
        """Carica i profili dal database e li mostra nella lista."""
        self.profiles_list_widget.clear()
      
        with database.DatabaseConnection() as conn:
            db_profiles = conn.execute("SELECT id, profile_key, name FROM profiles WHERE is_deleted = 0 ORDER BY name").fetchall()
        
        for profile in db_profiles:
            item = QListWidgetItem(profile['name'])
            item.setData(Qt.UserRole, {'id': profile['id'], 'key': profile['profile_key']})
            self.profiles_list_widget.addItem(item)
    
    def add_profile(self):
        dialog = ProfileDetailDialog(parent=self)
        if dialog.exec():
            new_profile = dialog.profile
            new_key = new_profile.name.replace(" ", "_").lower()
            
            # Controlla se una chiave simile esiste già
            with database.DatabaseConnection() as conn:
                existing = conn.execute("SELECT id FROM profiles WHERE profile_key = ?", (new_key,)).fetchone()
            if existing:
                QMessageBox.critical(self, "Errore", "Un profilo con un nome simile esiste già.")
                return
            
            services.add_profile_with_tests(new_key, new_profile.name, new_profile.tests)
            self.profiles_changed = True
            self.load_profiles_from_db()

    def edit_profile(self):
        selected_item = self.profiles_list_widget.currentItem()
        if not selected_item:
            return
        
        item_data = selected_item.data(Qt.UserRole)
        profile_id = item_data['id']
        profile_key = item_data['key']

        profile_to_edit = config.PROFILES.get(profile_key)
        if not profile_to_edit:
            QMessageBox.critical(self, "Errore", "Impossibile trovare il profilo da modificare. Prova a riavviare l'applicazione.")
            return

        dialog = ProfileDetailDialog(profile=profile_to_edit, parent=self)
        if dialog.exec():
            updated_profile = dialog.profile
            services.update_profile_with_tests(profile_id, updated_profile.name, updated_profile.tests)
            self.profiles_changed = True
            self.load_profiles_from_db()

    def delete_profile(self):
        selected_item = self.profiles_list_widget.currentItem()
        if not selected_item:
            return
        
        reply = QMessageBox.question(self, "Conferma Eliminazione",
                                     f"Sei sicuro di voler eliminare il profilo '{selected_item.text()}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            profile_id = selected_item.data(Qt.UserRole)['id']
            services.delete_profile(profile_id)
            self.profiles_changed = True
            self.load_profiles_from_db()