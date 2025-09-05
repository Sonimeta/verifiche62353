import json
from datetime import datetime
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton,
    QCalendarWidget, QDialogButtonBox, QFormLayout, QComboBox, QCheckBox, QSpinBox,
    QGroupBox, QTableWidget, QTableWidgetItem, QMessageBox, QLineEdit, QStyle, QHeaderView, QAbstractItemView, QListWidget, QListWidgetItem, QHBoxLayout)
from PySide6.QtCore import Qt, QDate, QSettings, QLocale
from PySide6.QtGui import QTextCharFormat, QBrush, QColor
from app import services

class SingleCalendarRangeDialog(QDialog):
    """
    Una dialog che permette di selezionare un intervallo di date
    su un singolo QCalendarWidget. (Versione corretta e ottimizzata)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Intervallo di Date")
        self.setMinimumWidth(400)

        self.start_date = None
        self.end_date = None
        self.selecting_start = True
        self.previous_range = None

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.start_label = QLabel("Nessuna")
        self.end_label = QLabel("Nessuna")
        form_layout.addRow("<b>Data Inizio:</b>", self.start_label)
        form_layout.addRow("<b>Data Fine:</b>", self.end_label)
        layout.addLayout(form_layout)
        
        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        self.calendar.setNavigationBarVisible(True)
        self.calendar.setLocale(QLocale(QLocale.Italian, QLocale.Italy))
        self.calendar.setFirstDayOfWeek(Qt.Monday)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        layout.addWidget(self.calendar)

        self.info_label = QLabel("Fai clic su una data per selezionare l'inizio dell'intervallo.")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        layout.addWidget(self.buttons)
        
        self.calendar.clicked.connect(self._on_date_clicked)
        
        self.range_format = QTextCharFormat()
        self.range_format.setBackground(QBrush(QColor("#dbeafe")))

    def _on_date_clicked(self, date):
        if self.start_date and self.end_date:
            self.previous_range = (self.start_date, self.end_date)
        
        if self.selecting_start:
            self.start_date = date
            self.end_date = None
            self.start_label.setText(f"<b>{date.toString('dd/MM/yyyy')}</b>")
            self.end_label.setText("Nessuna")
            self.info_label.setText("Ora fai clic sulla data di fine dell'intervallo.")
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            self.selecting_start = False
        else:
            self.end_date = date
            if self.start_date > self.end_date:
                self.start_date, self.end_date = self.end_date, self.start_date
            
            self.start_label.setText(f"<b>{self.start_date.toString('dd/MM/yyyy')}</b>")
            self.end_label.setText(f"<b>{self.end_date.toString('dd/MM/yyyy')}</b>")
            self.info_label.setText("Intervallo selezionato. Clicca di nuovo per ricominciare.")
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
            self.selecting_start = True
        
        self._update_highlight()

    def _update_highlight(self):
        default_format = QTextCharFormat()
        if self.previous_range:
            d = self.previous_range[0]
            while d <= self.previous_range[1]:
                self.calendar.setDateTextFormat(d, default_format)
                d = d.addDays(1)
        
        if self.start_date and self.end_date:
            d = self.start_date
            while d <= self.end_date:
                self.calendar.setDateTextFormat(d, self.range_format)
                d = d.addDays(1)
        elif self.start_date:
             self.calendar.setDateTextFormat(self.start_date, self.range_format)

    def get_date_range(self):
        if self.start_date and self.end_date:
            return (self.start_date.toString("yyyy-MM-dd"), 
                    self.end_date.toString("yyyy-MM-dd"))
        return None, None

class ImportReportDialog(QDialog):
    """Finestra che mostra un report dettagliato (es. righe ignorate)."""
    def __init__(self, title, report_details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        # Impostiamo una dimensione minima per renderla più grande
        self.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(self)
        label = QLabel("Le seguenti righe del file non sono state importate:")
        layout.addWidget(label)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText("\n".join(report_details))
        layout.addWidget(text_edit)
        
        # Usiamo un pulsante standard che sarà tradotto dal sistema
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

class DateSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Data")
        layout = QVBoxLayout(self)
        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        self.calendar.setSelectedDate(QDate.currentDate())
        layout.addWidget(self.calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    def getSelectedDate(self):
        return self.calendar.selectedDate().toString("yyyy-MM-dd")
    
class MappingDialog(QDialog):
    def __init__(self, file_columns, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mappatura Colonne Importazione")
        self.setMinimumWidth(450)
        self.required_fields = { 'matricola': 'Matricola (S/N)', 'descrizione': 'Descrizione', 'costruttore': 'Costruttore', 'modello': 'Modello', 'reparto': 'Reparto (Opzionale)', 'inv_cliente': 'Inventario Cliente (Opzionale)', 'inv_ams': 'Inventario AMS (Opzionale)', 'verification_interval': 'Intervallo Verifica (Mesi, Opzionale)' }
        self.file_columns = ["<Nessuna>"] + file_columns
        self.combo_boxes = {}
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        info_label = QLabel("Associa le colonne del tuo file con i campi del programma.\nI campi obbligatori sono Matricola e Descrizione.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        for key, display_name in self.required_fields.items():
            label = QLabel(f"{display_name}:")
            combo = QComboBox()
            combo.addItems(self.file_columns)
            form_layout.addRow(label, combo)
            self.combo_boxes[key] = combo
        layout.addLayout(form_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.try_auto_mapping()

    def try_auto_mapping(self):
        for key, combo in self.combo_boxes.items():
            for i, col_name in enumerate(self.file_columns):
                if key.lower().replace("_", "") in col_name.lower().replace(" ", "").replace("/", ""):
                    combo.setCurrentIndex(i); break

    def get_mapping(self):
        mapping = {}
        for key, combo in self.combo_boxes.items():
            selected_col = combo.currentText()
            if selected_col != "<Nessuna>": mapping[key] = selected_col
        if 'matricola' not in mapping or 'descrizione' not in mapping:
            QMessageBox.warning(self, "Campi Mancanti", "Assicurati di aver mappato almeno i campi Matricola e Descrizione.")
            return None
        return mapping
    
class VisualInspectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ispezione Visiva Preliminare")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Valutare tutti i punti seguenti prima di procedere con le misure elettriche."))
        
        self.checklist_items = [
            "Involucro e parti meccaniche integri, senza danni.",
            "Cavo di alimentazione e spina senza danneggiamenti.",
            "Cavi paziente, connettori e accessori integri.",
            "Marcature e targhette di sicurezza leggibili.",
            "Assenza di sporcizia o segni di versamento di liquidi.",
            "Fusibili (se accessibili) di tipo e valore corretti."
        ]
        
        # --- MODIFICA 1: Creiamo una lista per contenere i QComboBox ---
        self.controls = []
        form_layout = QFormLayout()

        # --- MODIFICA 2: Sostituiamo le checkbox con etichette e ComboBox ---
        for item_text in self.checklist_items:
            combo = QComboBox()
            combo.addItems(["Seleziona...", "OK", "KO", "N/A"])
            # Colleghiamo la modifica del combo al controllo del pulsante OK
            combo.currentIndexChanged.connect(self.check_all_selected)
            
            # Aggiungiamo il controllo al layout del form
            form_layout.addRow(QLabel(item_text), combo)
            self.controls.append((item_text, combo))
        
        layout.addLayout(form_layout)
            
        layout.addWidget(QLabel("\nNote aggiuntive:"))
        self.notes_edit = QTextEdit()
        layout.addWidget(self.notes_edit)
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText("Conferma e Procedi")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        # Controlla lo stato iniziale
        self.check_all_selected()

    def check_all_selected(self):
        """
        --- MODIFICA 3: Logica aggiornata per abilitare il pulsante OK ---
        Abilita il pulsante 'OK' solo se per ogni voce è stata fatta una scelta
        (cioè non è più su "Seleziona...").
        """
        is_all_selected = all(combo.currentIndex() > 0 for _, combo in self.controls)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(is_all_selected)

    def get_data(self):
        """
        --- MODIFICA 4: Logica aggiornata per salvare i dati ---
        Restituisce i dati della dialog, salvando il risultato scelto.
        """
        return {
            "notes": self.notes_edit.toPlainText(),
            "checklist": [{"item": text, "result": combo.currentText()} for text, combo in self.controls]
        }

class VerificationViewerDialog(QDialog):
    def __init__(self, verification_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Dettagli Verifica del {verification_data.get('verification_date')}")
        self.setMinimumSize(700, 400)
        data = verification_data or {}
        layout = QVBoxLayout(self)
        info_label = QLabel(f"<b>Profilo:</b> {data.get('profile_name')}<br><b>Esito Globale:</b> {data.get('overall_status')}")
        layout.addWidget(info_label)
        visual_data = data.get('visual_inspection', {})
        if visual_data:
            visual_group = QGroupBox("Ispezione Visiva")
            visual_layout = QVBoxLayout(visual_group)
            visual_data = data.get('visual_inspection', {})
            for item in visual_data.get('checklist', []): visual_layout.addWidget(QLabel(f"- {item['item']} [✓]"))
            if visual_data.get('notes'): visual_layout.addWidget(QLabel(f"\n<b>Note:</b> {visual_data['notes']}"))
            layout.addWidget(visual_group)
        results_table = QTableWidget(); results_table.setColumnCount(4); results_table.setHorizontalHeaderLabels(["Test / P.A.", "Limite", "Valore", "Esito"]); layout.addWidget(results_table)
        results = data.get('results', [])
        for res in results:
            row = results_table.rowCount(); results_table.insertRow(row)
            results_table.setItem(row, 0, QTableWidgetItem(res.get('name', '')))
            results_table.setItem(row, 1, QTableWidgetItem(res.get('limit', '')))
            results_table.setItem(row, 2, QTableWidgetItem(res.get('value', '')))
            is_passed = res.get('passed', False) 
            passed_item = QTableWidgetItem("PASSATO" if is_passed else "FALLITO")
            passed_item.setBackground(QColor('#D4EDDA') if is_passed else QColor('#F8D7DA'))
            results_table.setItem(row, 3, passed_item)
        results_table.resizeColumnsToContents()
        close_button = QPushButton("Chiudi"); close_button.clicked.connect(self.accept); layout.addWidget(close_button)

class InstrumentSelectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Strumento")
        self.settings = QSettings("MyCompany", "SafetyTester")
        self.instruments = services.get_all_instruments()
        layout = QFormLayout(self)
        self.combo = QComboBox()
        default_idx = -1
        if self.instruments:
            for i, inst_row in enumerate(self.instruments):
                instrument = dict(inst_row)
                self.combo.addItem(f"{instrument.get('instrument_name')} (S/N: {instrument.get('serial_number')})", instrument.get('id'))
                if instrument.get('is_default'): default_idx = i
            if default_idx != -1: self.combo.setCurrentIndex(default_idx)
        layout.addRow("Strumento:", self.combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def getSelectedInstrumentData(self):
        """Restituisce un dizionario con i dati dello strumento selezionato, inclusa la porta COM."""
        if not self.instruments:
            return None
            
        selected_id = self.combo.currentData()
        instrument_row = next((inst for inst in self.instruments if inst['id'] == selected_id), None)
        
        if instrument_row:
            instrument = dict(instrument_row)
            settings = QSettings("MyCompany", "SafetyTester")
            global_com_port = settings.value("global_com_port", "COM1")
            return {
                "instrument": instrument.get('instrument_name'),
                "serial": instrument.get('serial_number'), 
                "version": instrument.get('fw_version'), 
                "cal_date": instrument.get('calibration_date'),
                "com_port": global_com_port
            }
        return None
    
    def getTechnicianName(self):
        user = services.auth_manager.get_current_user()
        return user["full_name"] if user else ""
    
class MonthYearSelectionDialog(QDialog):
    """Una semplice dialog per selezionare un mese e un anno."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Periodo")
        
        layout = QFormLayout(self)
        
        # ComboBox per i mesi
        self.month_combo = QComboBox()
        mesi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", 
                "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        self.month_combo.addItems(mesi)
        # Seleziona il mese corrente come default
        self.month_combo.setCurrentIndex(datetime.now().month - 1)
        
        # SpinBox per l'anno
        self.year_spin = QSpinBox()
        self.year_spin.setRange(2020, 2099)
        self.year_spin.setValue(datetime.now().year)
        
        layout.addRow("Mese:", self.month_combo)
        layout.addRow("Anno:", self.year_spin)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_selected_period(self):
        """Restituisce mese (numero) e anno selezionati."""
        # L'indice del ComboBox è 0-11, quindi aggiungiamo 1 per avere 1-12
        month = self.month_combo.currentIndex() + 1
        year = self.year_spin.value()
        return month, year

class AppliedPartsOrderDialog(QDialog):
    """
    Mostra al tecnico l'ordine in cui collegare le parti applicate
    prima di avviare un test automatico.
    """
    def __init__(self, applied_parts, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ordine Collegamento Parti Applicate")
        self.setMinimumSize(500, 300)

        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "<b>Attenzione:</b> Collegare le seguenti parti applicate allo strumento nell'ordine indicato prima di procedere."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["Ordine", "Nome Parte Applicata", "Codice Strumento"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        
        layout.addWidget(table)
        
        # Popola la tabella con i dati forniti
        table.setRowCount(0)
        for i, part in enumerate(applied_parts):
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(i + 1)))
            table.setItem(row, 1, QTableWidgetItem(part.name))
            table.setItem(row, 2, QTableWidgetItem(part.code))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Pronto per Iniziare")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

class DateRangeSelectionDialog(QDialog):
    """A dialog for selecting a start and end date."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Periodo di Riferimento")
        layout = QVBoxLayout(self)

        # Start Date
        layout.addWidget(QLabel("Data di Inizio:"))
        self.start_calendar = QCalendarWidget(self)
        self.start_calendar.setGridVisible(True)
        self.start_calendar.setSelectedDate(QDate.currentDate().addMonths(-1))
        layout.addWidget(self.start_calendar)

        # End Date
        layout.addWidget(QLabel("Data di Fine:"))
        self.end_calendar = QCalendarWidget(self)
        self.end_calendar.setGridVisible(True)
        self.end_calendar.setSelectedDate(QDate.currentDate())
        layout.addWidget(self.end_calendar)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_date_range(self):
        start_date = self.start_calendar.selectedDate().toString("yyyy-MM-dd")
        end_date = self.end_calendar.selectedDate().toString("yyyy-MM-dd")
        return start_date, end_date

class VerificationStatusDialog(QDialog):
    """Displays lists of verified and unverified devices."""
    def __init__(self, verified_devices, unverified_devices, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stato Verifiche Dispositivi")
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)

        # Verified devices group
        verified_group = QGroupBox(f"Dispositivi Verificati ({len(verified_devices)})")
        verified_layout = QVBoxLayout(verified_group)
        self.verified_list = QListWidget()
        for device in verified_devices:
            self.verified_list.addItem(f"{device['description']} (S/N: {device['serial_number']})")
        verified_layout.addWidget(self.verified_list)
        layout.addWidget(verified_group)

        # Unverified devices group
        unverified_group = QGroupBox(f"Dispositivi da Verificare ({len(unverified_devices)})")
        unverified_layout = QVBoxLayout(unverified_group)
        self.unverified_list = QListWidget()
        for device in unverified_devices:
            self.unverified_list.addItem(f"{device['description']} (S/N: {device['serial_number']})")
        unverified_layout.addWidget(self.unverified_list)
        layout.addWidget(unverified_group)

        close_button = QPushButton("Chiudi")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

class DeviceSearchDialog(QDialog):
    """
    Una finestra di dialogo per cercare un dispositivo in tutto il database
    e restituire i suoi dati.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cerca Dispositivo da Copiare")
        self.setMinimumSize(500, 300)
        self.selected_device_data = None

        layout = QVBoxLayout(self)
        
        # Layout di ricerca
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cerca per descrizione, modello o S/N...")
        search_button = QPushButton("Cerca")
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_button)
        layout.addLayout(search_layout)

        # Lista dei risultati
        self.results_list = QListWidget()
        layout.addWidget(self.results_list)

        # Pulsanti OK/Annulla
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Connessioni
        search_button.clicked.connect(self.perform_search)
        self.search_input.returnPressed.connect(self.perform_search)
        self.results_list.itemDoubleClicked.connect(self.accept_selection)

    def perform_search(self):
        search_term = self.search_input.text().strip()
        if len(search_term) < 3:
            QMessageBox.warning(self, "Ricerca", "Inserisci almeno 3 caratteri per avviare la ricerca.")
            return
        
        results = services.search_device_globally(search_term)
        self.results_list.clear()
        
        if not results:
            self.results_list.addItem("Nessun dispositivo trovato.")
        else:
            for device_row in results:
                device = dict(device_row)
                # --- MODIFICA CHIAVE ---
                # Ora prendiamo il nome del cliente direttamente dai risultati della ricerca
                customer_name = device.get('customer_name', 'Sconosciuto')
                
                display_text = f"{device['description']} (Modello: {device['model']}) - Cliente: {customer_name}"
                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, device)
                self.results_list.addItem(item)

    def accept_selection(self):
        selected_item = self.results_list.currentItem()
        if not selected_item or not selected_item.data(Qt.UserRole):
            QMessageBox.warning(self, "Selezione Mancante", "Seleziona un dispositivo dalla lista.")
            return
        
        self.selected_device_data = selected_item.data(Qt.UserRole)
        self.accept()


class CustomerSelectionDialog(QDialog):
    """
    Una finestra di dialogo per selezionare un cliente da una lista.
    """
    def __init__(self, customers, current_customer_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sposta Dispositivo")
        self.setMinimumWidth(400)
        self.selected_customer_id = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Seleziona il nuovo cliente di destinazione per il dispositivo."))
        layout.addWidget(QLabel(f"<b>Cliente attuale:</b> {current_customer_name}"))

        self.customer_combo = QComboBox()
        # Popola il menu a tendina con i clienti forniti
        for customer in customers:
            self.customer_combo.addItem(customer['name'], customer['id'])
        
        layout.addWidget(self.customer_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        self.selected_customer_id = self.customer_combo.currentData()
        super().accept()

class DestinationDetailDialog(QDialog):
    """Dialog per inserire/modificare i dettagli di una destinazione."""
    def __init__(self, destination_data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dettagli Destinazione / Sede")
        data = destination_data or {}
        layout = QFormLayout(self)
        self.name_edit = QLineEdit(data.get('name', ''))
        self.address_edit = QLineEdit(data.get('address', ''))
        layout.addRow("Nome Destinazione/Reparto:", self.name_edit)
        layout.addRow("Indirizzo (Opzionale):", self.address_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {
            "name": self.name_edit.text().strip(),
            "address": self.address_edit.text().strip()
        }

class DestinationSelectionDialog(QDialog):
    """
    Una finestra di dialogo per selezionare una destinazione da un elenco
    di tutti i clienti e di tutte le loro destinazioni.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Nuova Destinazione")
        self.setMinimumWidth(500)
        self.selected_destination_id = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Seleziona la nuova destinazione per il dispositivo:"))
        
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.completer().setFilterMode(Qt.MatchContains)
        self.combo.completer().setCaseSensitivity(Qt.CaseInsensitive)
        
        all_customers = services.get_all_customers()
        for cust in all_customers:
            # --- INIZIO LOGICA CORRETTA ---
            # 1. Aggiungi SEMPRE il nome del cliente come separatore
            self.combo.addItem(f"--- {cust['name']} ---")
            last_index = self.combo.count() - 1
            self.combo.model().item(last_index).setSelectable(False)

            # 2. SOLO DOPO, controlla se ci sono destinazioni da aggiungere sotto di esso
            destinations = services.database.get_destinations_for_customer(cust['id'])
            if destinations:
                for dest in destinations:
                    self.combo.addItem(f"  {dest['name']} ({cust['name']})", dest['id'])
            # --- FINE LOGICA CORRETTA ---

        layout.addWidget(self.combo)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept_selection)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept_selection(self):
        self.selected_destination_id = self.combo.currentData()
        # Controlliamo che l'utente non abbia selezionato un separatore
        if not self.selected_destination_id or not isinstance(self.selected_destination_id, int):
            QMessageBox.warning(self, "Selezione non valida", "Per favore, seleziona una destinazione valida dall'elenco.")
            return
            
        super().accept()


class SingleCalendarRangeDialog(QDialog):
    """
    Una dialog che permette di selezionare un intervallo di date
    su un singolo QCalendarWidget. (Versione corretta e ottimizzata)
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seleziona Intervallo di Date")
        self.setMinimumWidth(400)

        # Stato della selezione
        self.start_date = None
        self.end_date = None
        self.selecting_start = True
        
        # --- CORREZIONE: Memorizziamo l'intervallo precedente per una pulizia efficiente ---
        self.previous_range = None

        # Setup UI
        layout = QVBoxLayout(self)
        form_layout = QFormLayout()
        self.start_label = QLabel("Nessuna")
        self.end_label = QLabel("Nessuna")
        form_layout.addRow("<b>Data Inizio:</b>", self.start_label)
        form_layout.addRow("<b>Data Fine:</b>", self.end_label)
        layout.addLayout(form_layout)
        
        self.calendar = QCalendarWidget(self)
        self.calendar.setGridVisible(True)
        self.calendar.setNavigationBarVisible(True) # Assicurati che i pulsanti di navigazione siano visibili
        self.calendar.setLocale(QLocale(QLocale.Italian, QLocale.Italy)) # Imposta la localizzazione italiana
        self.calendar.setFirstDayOfWeek(Qt.Monday) # Imposta lunedì come primo giorno della settimana
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        layout.addWidget(self.calendar)

        self.info_label = QLabel("Fai clic su una data per selezionare l'inizio dell'intervallo.")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
        layout.addWidget(self.buttons)
        
        self.calendar.clicked.connect(self._on_date_clicked)
        
        self.range_format = QTextCharFormat()
        self.range_format.setBackground(QBrush(QColor("#dbeafe")))

    def _on_date_clicked(self, date):
        """Gestisce la logica di selezione dell'intervallo."""
        # --- CORREZIONE: Memorizza l'intervallo corrente prima di modificarlo ---
        if self.start_date and self.end_date:
            self.previous_range = (self.start_date, self.end_date)
        
        if self.selecting_start:
            self.start_date = date
            self.end_date = None
            self.start_label.setText(f"<b>{date.toString('dd/MM/yyyy')}</b>")
            self.end_label.setText("Nessuna")
            self.info_label.setText("Ora fai clic sulla data di fine dell'intervallo.")
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(False)
            self.selecting_start = False
        else:
            self.end_date = date
            if self.start_date > self.end_date:
                self.start_date, self.end_date = self.end_date, self.start_date
            
            self.start_label.setText(f"<b>{self.start_date.toString('dd/MM/yyyy')}</b>")
            self.end_label.setText(f"<b>{self.end_date.toString('dd/MM/yyyy')}</b>")
            self.info_label.setText("Intervallo selezionato. Clicca di nuovo per ricominciare.")
            self.buttons.button(QDialogButtonBox.Ok).setEnabled(True)
            self.selecting_start = True
        
        self._update_highlight()

    def _update_highlight(self):
        """Evidenzia le date nell'intervallo selezionato in modo efficiente."""
        default_format = QTextCharFormat()
        
        # --- CORREZIONE: Pulisce solo l'intervallo precedente, non tutto il calendario ---
        if self.previous_range:
            d = self.previous_range[0]
            while d <= self.previous_range[1]:
                self.calendar.setDateTextFormat(d, default_format)
                d = d.addDays(1)
        
        # Applica il nuovo formato solo al nuovo intervallo
        if self.start_date and self.end_date:
            d = self.start_date
            while d <= self.end_date:
                self.calendar.setDateTextFormat(d, self.range_format)
                d = d.addDays(1)
        elif self.start_date: # Evidenzia la sola data di inizio quando si è a metà selezione
             self.calendar.setDateTextFormat(self.start_date, self.range_format)


    def get_date_range(self):
        """Restituisce le date selezionate."""
        if self.start_date and self.end_date:
            return (self.start_date.toString("yyyy-MM-dd"), 
                    self.end_date.toString("yyyy-MM-dd"))
        return None, None