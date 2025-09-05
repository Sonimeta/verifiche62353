import qtawesome as qta
from datetime import date, timedelta
import logging
import json
import sys
import os   
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QComboBox, QGroupBox, QFormLayout, QMessageBox, QFileDialog, 
    QStyle, QStatusBar, QListWidget, QListWidgetItem, QLineEdit, QDialog, QMenu, QInputDialog, QCheckBox, QTableWidgetItem)
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtCore import Qt, QSettings, QDate, QCoreApplication, QThread, QProcess
from app.data_models import AppliedPart
from app.ui.dialogs.user_manager_dialog import UserManagerDialog

# La main_window importa solo i moduli necessari per la UI e i servizi
from app import auth_manager, config, services
from app.ui.dialogs.utility_dialogs import AppliedPartsOrderDialog
from app.ui.widgets import TestRunnerWidget, ControlPanelWidget
from app.backup_manager import restore_from_backup
from app.ui.dialogs import (DbManagerDialog, VisualInspectionDialog, DeviceDialog, 
                            InstrumentManagerDialog, InstrumentSelectionDialog)
from app.workers.sync_worker import SyncWorker
from app.ui.dialogs.conflict_dialog import ConflictResolutionDialog
from app import auth_manager
from app.ui.dialogs.signature_manager_dialog import SignatureManagerDialog
from app.hardware.fluke_esa612 import FlukeESA612
from app.ui.dialogs.profile_manager_dialog import ProfileManagerDialog



class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Safety Test Manager - {config.VERSIONE}")
        app_icon = QIcon("logo.png") 
        self.setWindowIcon(app_icon)
        self.setWindowState(Qt.WindowMaximized)
        self.setGeometry(100, 100, 1280, 720)
        self.settings = QSettings("MyCompany", "SafetyTester")
        self.logo_path = self.settings.value("logo_path", "")
        self.relogin_requested = False
        self.restart_after_sync = False
        self.current_mti_info = None
        self.current_technician_name = ""
        self.test_runner_widget = None

        self.create_menu_bar()
        self.setStatusBar(QStatusBar(self))

        main_widget = QWidget()
        self.main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        self.create_left_panel()
        self.create_right_panel()

        self.apply_permissions()
        self.load_all_data()

    def create_menu_bar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        self.logout_action = QAction(qta.icon('fa5s.sign-out-alt'), "Logout", self)
        self.logout_action.triggered.connect(self.logout)

        self.ripristina_db_action = QAction(qta.icon('fa5s.server'), "ripristina database", self)
        self.ripristina_db_action.triggered.connect(self.restore_database)

        file_menu.addAction(self.ripristina_db_action)
        file_menu.addAction(self.logout_action)

        settings_menu = menubar.addMenu("Impostazioni")

        self.full_sync_action = QAction(qta.icon('fa5s.server'), "Sincronizza Tutto (Reset Locale)...", self)
        self.full_sync_action.triggered.connect(lambda: self.run_synchronization(full_sync=True))
        settings_menu.addAction(self.full_sync_action)

        self.force_push_action = QAction(qta.icon('fa5s.cloud-upload-alt'), "Forza Upload (tutti i dati)...", self)
        self.force_push_action.triggered.connect(self.confirm_and_force_push)
        settings_menu.addAction(self.force_push_action)

        settings_menu.addSeparator()

        self.set_com_port_action = QAction(qta.icon('fa5s.plug'), "Imposta Porta COM...", self)
        self.set_com_port_action.triggered.connect(self.configure_com_port)
        settings_menu.addAction(self.set_com_port_action)

        self.manage_instruments_action = QAction(qta.icon('fa5s.tools'), "Gestisci Strumenti di Misura...", self)
        self.manage_instruments_action.triggered.connect(self.open_instrument_manager)
        settings_menu.addAction(self.manage_instruments_action)
        settings_menu.addSeparator()

        self.set_logo_action = QAction(qta.icon('fa5s.image'), "Imposta Logo Azienda...", self)
        self.set_logo_action.triggered.connect(self.set_company_logo)
        settings_menu.addAction(self.set_logo_action)

        
        self.manage_users_action = QAction(qta.icon('fa5s.users-cog'), "Gestisci Utenti...", self)
        self.manage_users_action.triggered.connect(self.open_user_manager)
        settings_menu.addAction(self.manage_users_action)

        self.manage_profiles_action = QAction(qta.icon('fa5s.clipboard-list'), "Gestisci Profili...", self)
        self.manage_profiles_action.triggered.connect(self.open_profile_manager)
        settings_menu.addAction(self.manage_profiles_action)

        self.manage_signature_action = QAction(qta.icon('fa5s.file-signature'), "Gestisci Firma...", self)
        self.manage_signature_action.triggered.connect(self.open_signature_manager)
        settings_menu.addAction(self.manage_signature_action)

    def create_left_panel(self):
        left_panel_widget = QWidget()
        left_layout = QVBoxLayout(left_panel_widget)
        self.control_panel = ControlPanelWidget(self)
        self.manage_button = QPushButton(qta.icon('fa5s.database'), " Gestione Anagrafiche")
        self.sync_button = QPushButton(qta.icon('fa5s.sync-alt'), " Sincronizza")
        self.manage_button.setObjectName("secondary_button")
        self.manage_button.clicked.connect(self.open_db_manager)
        self.sync_button.clicked.connect(self.run_synchronization)
        left_layout.addWidget(self.control_panel)
        left_layout.addWidget(self.manage_button)
        left_layout.addWidget(self.sync_button)
        left_layout.addStretch()
        self.main_layout.addWidget(left_panel_widget, 1)

    def create_right_panel(self):
        right_panel_widget = QWidget()
        self.right_layout = QVBoxLayout(right_panel_widget)
        self.selection_container = QWidget()
        selection_layout = QVBoxLayout(self.selection_container)
        session_group = self._create_session_group()
        search_group = self._create_search_group()
        manual_group = self._create_manual_selection_group()
        start_buttons_layout = QHBoxLayout()
        self.start_manual_button = QPushButton(qta.icon('fa5s.play'), " Avvia Verifica Manuale")
        self.start_auto_button = QPushButton(qta.icon('fa5s.robot'), " Avvia Verifica Automatica")
        self.start_manual_button.clicked.connect(lambda: self.start_verification(manual_mode=True))
        self.start_auto_button.clicked.connect(lambda: self.start_verification(manual_mode=False))
        start_buttons_layout.addStretch()
        start_buttons_layout.addWidget(self.start_manual_button)
        start_buttons_layout.addWidget(self.start_auto_button)
        selection_layout.addWidget(session_group)
        selection_layout.addWidget(search_group)
        selection_layout.addWidget(manual_group)
        selection_layout.addLayout(start_buttons_layout)
        selection_layout.addStretch()
        self.test_runner_container = QWidget()
        self.test_runner_layout = QVBoxLayout(self.test_runner_container)
        self.test_runner_container.hide()
        self.right_layout.addWidget(self.selection_container)
        self.right_layout.addWidget(self.test_runner_container)
        self.create_device_details_panel()
        self.right_layout.addWidget(self.device_details_group)

        self.main_layout.addWidget(right_panel_widget, 3)

        # collega il cambio selezione anche al pannello dettagli
        self.device_selector.currentIndexChanged.connect(self.on_device_selection_changed)
    def create_device_details_panel(self):
        from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QPushButton, QWidget, QGridLayout, QLabel

        self.device_details_group = QGroupBox("Dettagli dispositivo", self)
        box_layout = QVBoxLayout(self.device_details_group)

        # Contenitore con griglia 2xN
        self.device_details_widget = QWidget(self.device_details_group)
        self.device_details_layout = QGridLayout(self.device_details_widget)
        self.device_details_layout.setColumnStretch(0, 1)
        self.device_details_layout.setColumnStretch(1, 2)
        self.device_details_layout.setColumnStretch(2, 1)
        self.device_details_layout.setColumnStretch(3, 2)

        box_layout.addWidget(self.device_details_widget)

        # Pulsante Modifica
        self.btn_edit_device = QPushButton("Modifica…", self.device_details_group)
        self.btn_edit_device.clicked.connect(self.on_edit_selected_device)
        box_layout.addWidget(self.btn_edit_device)

        # Carica subito i dettagli (se già selezionato un device)
        self.on_device_selection_changed(self.device_selector.currentIndex())

    def _create_session_group(self):
        group = QGroupBox("Sessione di Verifica Corrente")
        layout = QFormLayout(group)
        self.current_instrument_label = QLabel("Nessuno strumento selezionato")
        self.current_technician_label = QLabel("Nessun tecnico impostato")
        change_session_btn = QPushButton("Imposta / Cambia Sessione...")
        change_session_btn.clicked.connect(self.setup_session)
        layout.addRow("Strumento in Uso:", self.current_instrument_label)
        layout.addRow("Tecnico:", self.current_technician_label)
        layout.addRow(change_session_btn)
        return group

    def on_device_selection_changed(self, _idx: int):
        """Ripopola il pannello dettagli in base al device selezionato."""
        dev_id = self.device_selector.currentData()
        if not dev_id or dev_id == -1:
            self._clear_device_details()
            return
        self.update_device_details_view(dev_id)

    def _clear_device_details(self):
        for i in reversed(range(self.device_details_layout.count())):
            item = self.device_details_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
            self.device_details_layout.removeItem(item)

    def update_device_details_view(self, dev_id: int):
        """Mostra i dettagli in una griglia 2xN (campo/valore affiancati)."""
        # Svuota la griglia precedente
        for i in reversed(range(self.device_details_layout.count())):
            item = self.device_details_layout.itemAt(i)
            if item.widget():
                item.widget().deleteLater()
            self.device_details_layout.removeItem(item)

        row = services.database.get_device_by_id(dev_id)
        if not row:
            return

        dev = dict(row)

        # Recupero destinazione + cliente
        dest_name = "—"
        try:
            dest_row = services.database.get_destination_by_id(dev.get("destination_id"))
            if dest_row:
                dest = dict(dest_row)
                cust_row = services.database.get_customer_by_id(dest.get("customer_id"))
                cust_name = (dict(cust_row).get("name") if cust_row else None)
                dest_name = f"{dest.get('name')} — {cust_name}" if cust_name else (dest.get('name') or "—")
        except Exception:
            pass

        # Profilo leggibile
        prof_key = dev.get("default_profile_key")
        prof_label = prof_key or "—"
        try:
            from app import config
            prof_obj = config.PROFILES.get(prof_key)
            if prof_obj:
                prof_label = getattr(prof_obj, "name", prof_key) or prof_key
        except Exception:
            pass

        interval = dev.get("verification_interval")
        interval_label = str(interval) if interval not in (None, "") else "—"

        # Coppie da mostrare (ordine logico)
        fields = [
            ("Descrizione", dev.get("description") or "—"),
            ("Modello", dev.get("model") or "—"),
            ("Produttore", dev.get("manufacturer") or "—"),
            ("S/N", dev.get("serial_number") or "—"),
            ("Reparto", dev.get("department") or "—"),
            ("Destinazione", dest_name),
            ("Profilo", prof_label),
            ("Intervallo", interval_label),
            ("Inventario Cliente", dev.get("customer_inventory") or "—"),
            ("Inventario AMS", dev.get("ams_inventory") or "—"),
        ]

        # Inserimento nella griglia 2xN → 2 colonne di coppie (Campo | Valore)
        row_idx = 0
        for i in range(0, len(fields), 2):
            for col, (campo, valore) in enumerate(fields[i:i+2]):
                label_field = QLabel(f"<b>{campo}:</b>")
                label_value = QLabel(str(valore))
                self.device_details_layout.addWidget(label_field, row_idx, col * 2)
                self.device_details_layout.addWidget(label_value, row_idx, col * 2 + 1)
            row_idx += 1
    
    def on_edit_selected_device(self):
        dev_id = self.device_selector.currentData()
        if not dev_id or dev_id == -1:
            QMessageBox.warning(self, "Attenzione", "Seleziona un dispositivo da modificare.")
            return

        try:
            from app.ui.dialogs.detail_dialogs import DeviceDialog

            row = services.database.get_device_by_id(dev_id)
            if not row:
                QMessageBox.critical(self, "Errore", "Impossibile caricare i dati del dispositivo.")
                return

            dev = dict(row)
            dest_id = dev.get("destination_id")

            # ricava il customer_id dalla destinazione
            dest_row = services.database.get_destination_by_id(dest_id) if dest_id else None
            customer_id = dict(dest_row).get("customer_id") if dest_row else None

            # ✅ usa i parametri giusti attesi dal costruttore
            dlg = DeviceDialog(customer_id=customer_id,
                            destination_id=dest_id,
                            device_data=dev,
                            parent=self)

            if dlg.exec():
                data = dlg.get_data()

                services.update_device(
                    dev_id,
                    data["destination_id"],
                    data["serial"],
                    data["desc"],
                    data["mfg"],
                    data["model"],
                    data.get("department"),
                    data.get("applied_parts", []),
                    data.get("customer_inv"),
                    data.get("ams_inv"),
                    data.get("verification_interval"),
                    data.get("default_profile_key"),
                    reactivate=False
                )

                # aggiorna il pannello dettagli
                self.update_device_details_view(dev_id)
                QMessageBox.information(self, "Salvato", "Dispositivo aggiornato.")

        except Exception as e:
            logging.error("Errore durante la modifica del dispositivo", exc_info=True)
            QMessageBox.critical(self, "Errore", f"Modifica non riuscita:\n{e}")

    def _create_search_group(self):
        group = QGroupBox("Ricerca Rapida Dispositivo")
        layout = QHBoxLayout(group)
        self.global_device_search_edit = QLineEdit()
        self.global_device_search_edit.setPlaceholderText("Inserisci S/N o Inventario AMS...")
        self.global_device_search_edit.returnPressed.connect(self.perform_global_device_search)
        search_btn = QPushButton("Cerca")
        search_btn.clicked.connect(self.perform_global_device_search)
        layout.addWidget(self.global_device_search_edit)
        layout.addWidget(search_btn)
        return group

    def setup_session(self):
        """
        Apre la dialog per selezionare lo strumento e il tecnico per la sessione di verifica.
        """
        dialog = InstrumentSelectionDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.current_mti_info = dialog.getSelectedInstrumentData()
            
            # Con il nuovo sistema di login, il nome del tecnico è quello dell'utente loggato
            user_info = auth_manager.get_current_user_info()
            self.current_technician_name = user_info.get('full_name')

            if self.current_mti_info:
                instrument_name = self.current_mti_info.get('instrument', 'N/A')
                serial_number = self.current_mti_info.get('serial', 'N/A')
                self.current_instrument_label.setText(f"<b>{instrument_name} (S/N: {serial_number})</b>")
                self.current_technician_label.setText(f"<b>{self.current_technician_name}</b>")
                logging.info(f"Sessione impostata per tecnico '{self.current_technician_name}' con strumento S/N {serial_number}.")
                self.statusBar().showMessage("Sessione di verifica impostata. Pronto per iniziare.", 5000)
            else:
                QMessageBox.warning(self, "Dati Mancanti", "Selezionare uno strumento valido.")

    def _create_manual_selection_group(self):
        group = QGroupBox("Selezione Manuale")
        layout = QFormLayout(group)
        self.destination_selector = QComboBox()
        self.destination_selector.setEditable(True)
        self.destination_selector.completer().setFilterMode(Qt.MatchContains)
        self.device_selector = QComboBox() 
        self.device_selector.setEditable(True)
        self.device_selector.completer().setFilterMode(Qt.MatchContains)
        self.profile_selector = QComboBox()
        self.filter_unverified_checkbox = QCheckBox("Mostra solo dispositivi da verificare (ultimi 60 giorni)")
        self.filter_unverified_checkbox.setChecked(False)
        device_layout = QHBoxLayout() 
        device_layout.addWidget(self.device_selector, 1)
        add_device_btn = QPushButton(qta.icon('fa5s.plus'), "")
        add_device_btn.setToolTip("Aggiungi nuovo dispositivo alla destinazione"); 
        add_device_btn.clicked.connect(self.quick_add_device)
        device_layout.addWidget(add_device_btn)
        layout.addRow("Destinazione:", self.destination_selector)
        layout.addRow("Dispositivo:", device_layout)
        layout.addRow(self.filter_unverified_checkbox)
        layout.addRow("Profilo:", self.profile_selector)
        self.destination_selector.currentIndexChanged.connect(self.on_destination_selected)
        self.device_selector.currentIndexChanged.connect(self.on_device_selected)
        self.filter_unverified_checkbox.stateChanged.connect(self.on_destination_selected)
        return group
        
    def load_all_data(self):
        self.load_destinations()
        self.load_profiles()
        self.load_control_panel_data()

    def load_destinations(self):
        self.destination_selector.blockSignals(True)
        self.destination_selector.clear()
        self.destination_selector.addItem("Seleziona una destinazione...", -1)
        destinations = services.database.get_all_destinations_with_customer()
        for dest in destinations:
            self.destination_selector.addItem(f"{dest['customer_name']} / {dest['name']}", dest['id'])
        self.destination_selector.blockSignals(False)

    def load_profiles(self):
        self.profile_selector.clear()
        for key, profile in config.PROFILES.items():
            self.profile_selector.addItem(profile.name, key)

    def load_control_panel_data(self):
        self.control_panel.load_data()

    def on_destination_selected(self):
        """
        Populates the device list based on the selected destination and the
        state of the filter checkbox.
        """
        self.device_selector.blockSignals(True)
        self.device_selector.clear()
        
        destination_id = self.destination_selector.currentData()
        if not destination_id or destination_id == -1:
            self.device_selector.blockSignals(False)
            self.on_device_selected() # Clear the profile selection
            return

        devices = []
        if self.filter_unverified_checkbox.isChecked():
            # If the filter is active, calculate the date range (last 60 days)
            end_date = date.today()
            start_date = end_date - timedelta(days=60)
            # Call the new, corrected database function with the date range
            devices = services.database.get_unverified_devices_for_destination_in_period(
                destination_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
            )
        else:
            # If the filter is off, load all devices for the destination
            devices = services.database.get_devices_for_destination(destination_id)
        for dev_row in devices:
            dev = dict(dev_row)
            display_text = f"{dev.get('description')} (S/N: {dev.get('serial_number')}) - (Inv AMS: {dev.get('ams_inventory')})"
            self.device_selector.addItem(display_text, dev.get('id'))
        if self.device_selector.count() > 0:
            self.device_selector.setCurrentIndex(0)

        self.device_selector.blockSignals(False)
        self.on_device_selected() # Manually trigger to update the profile for the first item
        self.on_device_selection_changed(self.device_selector.currentIndex())

    def on_device_selected(self):
        device_id = self.device_selector.currentData()
        self.profile_selector.blockSignals(True)
        if not device_id or device_id == -1: self.profile_selector.setCurrentIndex(0); self.profile_selector.blockSignals(False); return
        
        device_data = services.database.get_device_by_id(device_id)
        if device_data and device_data.get('default_profile_key'):
            index = self.profile_selector.findData(device_data['default_profile_key'])
            if index != -1: self.profile_selector.setCurrentIndex(index)
            else: self.profile_selector.setCurrentIndex(0)
        else: self.profile_selector.setCurrentIndex(0)
        self.profile_selector.blockSignals(False)
    
    def start_verification(self, manual_mode: bool):
        # 1. Controlli preliminari sulla sessione
        if not self.current_mti_info or not self.current_technician_name:
            QMessageBox.warning(self, "Sessione non Impostata", "Impostare strumento e tecnico prima di avviare una verifica.")
            return
            
        device_id = self.device_selector.currentData()
        if not device_id or device_id == -1 or self.destination_selector.currentIndex() <= 0:
            QMessageBox.warning(self, "Attenzione", "Selezionare una destinazione e un dispositivo validi."); return
            
        # 2. Recupero dei dati necessari dal database
        device_info_row = services.database.get_device_by_id(device_id)
        if not device_info_row:
            QMessageBox.critical(self, "Errore", "Impossibile trovare i dati del dispositivo selezionato."); return
        device_info = dict(device_info_row)

        profile_key = self.profile_selector.currentData()
        if not profile_key:
            QMessageBox.warning(self, "Attenzione", "Selezionare un profilo di verifica."); return
        
        selected_profile = config.PROFILES[profile_key]
        
        if device_info.get('default_profile_key') != profile_key:
            try:
                logging.info(f"Updating default profile for device ID {device_id} to '{profile_key}'.")
                
                # Prepare all data for the update call
                update_data = {
                    "destination_id": device_info['destination_id'],
                    "default_profile_key": profile_key, # The new profile
                    "serial": device_info['serial_number'],
                    "desc": device_info['description'],
                    "mfg": device_info['manufacturer'],
                    "model": device_info['model'],
                    "department": device_info['department'],
                    "customer_inv": device_info['customer_inventory'],
                    "ams_inv": device_info['ams_inventory'],
                    "applied_parts": [AppliedPart(**pa) for pa in device_info.get('applied_parts', [])],
                    "verification_interval": device_info['verification_interval']
                }
                services.update_device(device_id, **update_data)
            except Exception as e:
                logging.error(f"Failed to save default profile for device ID {device_id}: {e}")
                QMessageBox.warning(self, "Salvataggio Profilo Fallito", 
                                    "Non è stato possibile salvare il profilo scelto come predefinito, ma la verifica può continuare.")

        # 4. Gestione della logica per le Parti Applicate
        profile_needs_ap = any(test.is_applied_part_test for test in selected_profile.tests)
        applied_parts = [AppliedPart(**pa) for pa in device_info.get('applied_parts', [])]
        
        if not manual_mode and profile_needs_ap and applied_parts:
            order_dialog = AppliedPartsOrderDialog(applied_parts, self)
            if order_dialog.exec() != QDialog.Accepted:
                self.statusBar().showMessage("Verifica annullata dall'utente.", 3000)
                return

        if profile_needs_ap and not applied_parts:
            msg_box = QMessageBox(QMessageBox.Question, "Parti Applicate Mancanti",
                                f"Il profilo '{selected_profile.name}' richiede test su Parti Applicate, ma il dispositivo non ne ha.",
                                QMessageBox.NoButton, self)
            btn_edit = msg_box.addButton("Modifica Dispositivo", QMessageBox.ActionRole)
            msg_box.addButton("Continua (Salta Test P.A.)", QMessageBox.ActionRole)
            btn_cancel = msg_box.addButton("Annulla Verifica", QMessageBox.RejectRole)
            msg_box.exec()
            
            clicked_btn = msg_box.clickedButton()
            if clicked_btn == btn_edit:
                # L'utente vuole modificare il dispositivo, dobbiamo passargli il customer_id
                destination_info = dict(services.database.get_destination_by_id(device_info['destination_id']))
                customer_id = destination_info['customer_id']
                edit_dialog = DeviceDialog(customer_id, destination_id=device_info['destination_id'], device_data=device_info, parent=self)
                if edit_dialog.exec():
                    services.update_device(device_id, **edit_dialog.get_data())
                    self.on_destination_selected() # Ricarica i dispositivi
                return
            elif clicked_btn == btn_cancel:
                return

        # 5. Esecuzione dell'ispezione visiva
        inspection_dialog = VisualInspectionDialog(self)
        if inspection_dialog.exec() == QDialog.Accepted:
            visual_inspection_data = inspection_dialog.get_data()
            
            if self.test_runner_widget:
                self.test_runner_widget.deleteLater()

            # Recupera le informazioni finali necessarie
            destination_info = dict(services.database.get_destination_by_id(device_info['destination_id']))
            customer_info = dict(services.database.get_customer_by_id(destination_info['customer_id']))
            report_settings = {"logo_path": self.logo_path}
            current_user = auth_manager.get_current_user_info()
            
            self.test_runner_widget = TestRunnerWidget(
                device_info, customer_info, self.current_mti_info, report_settings,
                profile_key, visual_inspection_data, 
                current_user.get('full_name'), 
                current_user.get('username'),
                manual_mode, self
            )
            self.test_runner_layout.addWidget(self.test_runner_widget)
            
            # --- MODIFICA CHIAVE: Esegui lo scambio delle schermate ---
            self.set_selection_enabled(False)
    
    def reset_main_ui(self):
        """Ripristina l'interfaccia alla schermata di selezione."""
        QApplication.restoreOverrideCursor()
        if self.test_runner_widget:
            self.test_runner_widget.deleteLater()
            self.test_runner_widget = None
        
        self.set_selection_enabled(True)
        self.load_control_panel_data() # Ricarica i dati per aggiornare le scadenze

    def set_selection_enabled(self, enabled):
        """Mostra/nasconde i widget di selezione o di test."""
        if enabled:
            self.selection_container.show()
            self.test_runner_container.hide()
        else:
            self.selection_container.hide()
            self.test_runner_container.show()
        self.menuBar().setEnabled(enabled)
    
    def quick_add_device(self):
        """Apre la dialog per aggiungere un dispositivo alla destinazione corrente."""
        destination_id = self.destination_selector.currentData()
        if not destination_id or destination_id == -1:
            QMessageBox.warning(self, "Attenzione", "Selezionare una destinazione prima di aggiungere un dispositivo."); return
        
        # Per creare la DeviceDialog abbiamo bisogno del customer_id, lo recuperiamo dalla destinazione
        destination_data = services.database.get_destination_by_id(destination_id)
        if not destination_data: return # Sicurezza
        customer_id = destination_data['customer_id']

        dialog = DeviceDialog(customer_id=customer_id, destination_id=destination_id, parent=self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                services.add_device(**data)
                self.on_destination_selected() # Ricarica la lista
            except ValueError as e:
                QMessageBox.warning(self, "Errore", str(e))

    def confirm_and_force_push(self):
        reply = QMessageBox.question(
            self, "Conferma Forza Upload",
            ("Questa azione segna TUTTI i dati locali come da sincronizzare e li invierà al server "
            "alla prossima sincronizzazione.\n\nProcedere?"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            stats = services.force_full_push()
            # subito dopo, avvia una sync normale
            self.run_synchronization(full_sync=False)
            QMessageBox.information(self, "Operazione completata",
                                    "Tutti i dati sono stati marcati come da sincronizzare.\n"
                                    "Ho avviato la sincronizzazione.")
        except Exception as e:
            logging.exception("Errore durante force_full_push")
            QMessageBox.critical(self, "Errore", f"Impossibile preparare il full push:\n{e}")

    def restore_database(self):
        reply = QMessageBox.question(self, 'Conferma Ripristino Database',
                                     "<b>ATTENZIONE:</b> L'operazione è irreversibile.\n\nL'applicazione verrà chiusa al termine. Vuoi continuare?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.No: return
        backup_path, _ = QFileDialog.getOpenFileName(self, "Seleziona un file di backup", "backups", "File di Backup (*.bak)")
        if not backup_path: return
        success = restore_from_backup(backup_path)
        if success:
            QMessageBox.information(self, "Ripristino Completato", "Database ripristinato con successo. L'applicazione verrà chiusa.")
        else:
            QMessageBox.critical(self, "Errore di Ripristino", "Errore durante il ripristino. Controllare i log.")
        QApplication.quit()

    def set_company_logo(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Seleziona Logo", "", "Image Files (*.png *.jpg *.jpeg)")
        if filename:
            self.logo_path = filename
            self.settings.setValue("logo_path", filename)
            QMessageBox.information(self, "Impostazioni Salvate", f"Logo impostato su:\n{filename}")

    def open_instrument_manager(self):
        dialog = InstrumentManagerDialog(self)
        dialog.exec()

    def closeEvent(self, event):
        """UI/UX: Salva la geometria della finestra prima di chiudere."""
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)

    def apply_permissions(self):
        """
        Controlla il ruolo dell'utente loggato e nasconde o disabilita
        le funzionalità non autorizzate.
        """
        user_role = auth_manager.get_current_role()
        user_info = auth_manager.get_current_user_info()

        # Mostra l'utente loggato nella barra del titolo per chiarezza
        self.setWindowTitle(f"Safety Test Manager {config.VERSIONE} - Utente: {user_info['full_name']}")

        # --- INIZIO LOGICA PERMESSI ---
        is_technician = (user_role == 'technician')

        # Nascondi le voci di menu per i tecnici
        if hasattr(self, 'manage_profiles_action'):
            self.manage_profiles_action.setVisible(not is_technician)
        if hasattr(self, 'manage_users_action'):
            self.manage_users_action.setVisible(not is_technician)
        if hasattr (self, 'force_push_action' ):
            self.force_push_action.setVisible(not is_technician)
        if hasattr (self, 'manage_instruments_action' ):
            self.manage_instruments_action.setVisible(not is_technician)
        # --- FINE LOGICA PERMESSI ---

    def update_device_list(self):
        """
        Popola la lista dei dispositivi in base allo stato del checkbox del filtro.
        """
        customer_id = self.customer_selector.currentData()
        self.device_selector.clear()

        if not customer_id or customer_id == -1:
            return

        devices = []
        if self.filter_unverified_checkbox.isChecked():
            # Se il filtro è attivo, calcola il periodo (ultimi 60 giorni)
            end_date = date.today()
            start_date = end_date - timedelta(days=60)
            # Chiama la nuova funzione del database
            devices = services.database.get_unverified_devices_in_period(
                customer_id, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
            )
        else:
            # Se il filtro non è attivo, carica tutti i dispositivi
            devices = services.database.get_devices_for_customer(customer_id)

        # Popola il menu a tendina con la lista ottenuta
        for dev_row in devices:
            dev = dict(dev_row)
            display_text = f"{dev.get('description')} (S/N: {dev.get('serial_number')} - (Inv AMS: {dev.get('ams_inventory')})"
            if dev.get('ams_inventory'):
                display_text += f" / Inv. AMS: {dev.get('ams_inventory')}"
            display_text += ")"
            self.device_selector.addItem(display_text, dev.get('id'))

    def open_profile_manager(self):
        """Apre la finestra di dialogo per la gestione dei profili."""
        dialog = ProfileManagerDialog(self)
        dialog.exec()
        
        # Se i profili sono cambiati, ricarica il ComboBox nella UI principale
        if dialog.profiles_changed:
            logging.info("I profili sono stati modificati. Ricaricamento in corso...")
            # Ricarica i profili dal file JSON
            profiles_path = os.path.join(config.BASE_DIR, "profiles.json")
            config.load_verification_profiles(profiles_path)
            # Aggiorna il ComboBox
            self.profile_selector.clear()
            self.profile_selector.addItems(config.PROFILES.keys())
            QMessageBox.information(self, "Profili Aggiornati", "La lista dei profili è stata aggiornata.")

    def open_signature_manager(self):
        """Apre la finestra di dialogo per la gestione della firma."""
        dialog = SignatureManagerDialog(self)
        dialog.exec()

    def logout(self):
        """
        Logs out the user and signals the main script to show the login screen again.
        """
        reply = QMessageBox.question(self, 'Conferma Logout', 
                                     'Sei sicuro di voler effettuare il logout?',
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            auth_manager.logout()
            self.relogin_requested = True # Set the flag
            self.close() # Close this window

    def open_user_manager(self):
        """Apre la finestra di dialogo per la gestione degli utenti."""
        dialog = UserManagerDialog(self)
        dialog.exec()

    def configure_com_port(self):
        """Apre una dialog per configurare la porta COM globale."""
      
        # Recupera la porta attuale dalle impostazioni
        current_port = self.settings.value("global_com_port", "COM1")

        # Ottieni le porte disponibili
        try:
            available_ports = FlukeESA612.list_available_ports()
        except:
            available_ports = ["COM1", "COM2", "COM3", "COM4"]
    
        # Mostra dialog di selezione
        port, ok = QInputDialog.getItem(
            self, 
            "Configura Porta COM",
            "Seleziona la porta COM per lo strumento di misura:",
            available_ports,
            available_ports.index(current_port) if current_port in available_ports else 0,
            False
        )
    
        if ok and port:
            self.settings.setValue("global_com_port", port)
            QMessageBox.information(self, "Impostazioni Salvate", 
                                f"Porta COM impostata su: {port}\n\nQuesta verrà utilizzata per tutti gli strumenti.")
    

    def run_synchronization(self, full_sync=False):
        """Starts the synchronization process in a worker thread."""
        if full_sync:
            reply = QMessageBox.question(self, 'Conferma Sincronizzazione Totale',
                                         "<b>ATTENZIONE:</b> Questa operazione eliminerà tutti i dati locali e li riscaricherà dal server. Le modifiche non sincronizzate andranno perse.\n\nSei sicuro di voler continuare?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                return

        self.statusBar().showMessage("Sincronizzazione in corso...")
        self.sync_button.setEnabled(False)

        self.thread = QThread()
        self.worker = SyncWorker(full_sync=full_sync) # Pass the flag to the worker
        self.worker.moveToThread(self.thread)
        
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_sync_finished)
        self.worker.error.connect(self.on_sync_error)
        self.worker.conflict.connect(self.on_sync_conflict)
        
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    def on_sync_finished(self, message):
        """
        Slot chiamato al termine della sincronizzazione. Ora avvia il riavvio.
        """
        self.statusBar().showMessage(f"Sincronizzazione completata.", 10000)
        self.sync_button.setEnabled(True)
        
        # Mostra il messaggio di successo all'utente
        QMessageBox.information(self, "Sincronizzazione Completata", 
                                f"{message}\n\nL'applicazione verrà ora riavviata per applicare tutte le modifiche.")
        
        # Imposta il flag e chiudi la finestra per avviare il riavvio
        self.restart_after_sync = True
        self.close()

    def on_sync_error(self, error_message):
        """Slot chiamato in caso di errore di sincronizzazione."""
        self.statusBar().showMessage(f"Errore di sincronizzazione.", 5000)
        self.sync_button.setEnabled(True)
        QMessageBox.critical(self, "Errore di Sincronizzazione", error_message)

    def on_sync_conflict(self, conflicts):
        self.statusBar().showMessage(f"Conflitto rilevato ({len(conflicts)} record).", 5000)
        QMessageBox.warning(self, "Conflitto di Sincronizzazione",
                            "Sono stati rilevati dei conflitti. Risolvili uno per uno.")

        # Per ora gestiamo un conflitto alla volta
        for conflict in conflicts:
            dialog = ConflictResolutionDialog(conflict, self)
            if dialog.exec() == QDialog.Accepted:
                resolution = dialog.resolution
                if resolution == "keep_local":
                    services.resolve_conflict_keep_local(conflict['table'], conflict['uuid'])
                elif resolution == "use_server":
                    services.resolve_conflict_use_server(conflict['table'], conflict['server_version'])
            else: # L'utente ha premuto Annulla
                QMessageBox.information(self, "Sincronizzazione Interrotta", "La sincronizzazione verrà riprovata più tardi.")
                self.sync_action.setEnabled(True)
                return # Interrompi il ciclo di risoluzione

        # Dopo aver risolto (o se non ce n'erano), riprova a sincronizzare
        QMessageBox.information(self, "Riprova Sincronizzazione", "Le risoluzioni sono state applicate. Verrà ora tentata una nuova sincronizzazione.")
        self.run_synchronization()

    def open_db_manager(self):
        current_role = auth_manager.get_current_role()
        # Passa il ruolo al costruttore della dialog
        dialog = DbManagerDialog(role=current_role, parent=self)
        dialog.setWindowState(Qt.WindowMaximized)
        dialog.exec()
        self.load_destinations()
        self.load_control_panel_data()

    def perform_global_device_search(self):
        """Cerca un dispositivo e seleziona la destinazione e il dispositivo corretti."""
        search_term = self.global_device_search_edit.text().strip()
        if not search_term: return
        
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            device_results = services.search_device_globally(search_term)
            if not device_results:
                QMessageBox.warning(self, "Ricerca Fallita", f"Nessun dispositivo trovato per '{search_term}'.")
                return

            device = dict(device_results[0])
            destination_id = device['destination_id']
            device_id = device['id']

            # Seleziona la destinazione corretta nel ComboBox
            dest_index = self.destination_selector.findData(destination_id)
            if dest_index != -1:
                self.destination_selector.setCurrentIndex(dest_index)
            
            # Forza l'aggiornamento della lista dispositivi e poi seleziona quello giusto
            QApplication.processEvents() 
            device_index = self.device_selector.findData(device_id)
            if device_index != -1:
                self.device_selector.setCurrentIndex(device_index)
                self.on_device_selection_changed(self.device_selector.currentIndex())
        finally:
            QApplication.restoreOverrideCursor()

    def setup_verification_session(self):
        dialog = InstrumentSelectionDialog(self)
        if dialog.exec() == QDialog.Accepted:
            # Qui usiamo sempre i dati dell'utente loggato per coerenza
            self.current_mti_info = dialog.getSelectedInstrumentData()
            user_info = auth_manager.get_current_user_info()
            self.current_technician_name = user_info.get('full_name') # Il nome è quello dell'utente loggato

            if self.current_mti_info:
                self.current_instrument_label.setText(f"<b>{self.current_mti_info.get('instrument')} (S/N: {self.current_mti_info.get('serial')})</b>")
                self.current_technician_label.setText(f"<b>{self.current_technician_name}</b>")
                logging.info(f"Sessione impostata per tecnico '{self.current_technician_name}'.")
                self.statusBar().showMessage("Sessione impostata. Pronto per avviare le verifiche.", 5000)
            else:
                QMessageBox.warning(self, "Dati Mancanti", "Selezionare uno strumento valido.")