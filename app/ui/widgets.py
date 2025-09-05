import logging
import os
import re
import time
from PySide6.QtCore import Qt, QTimer, QDate
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (QApplication, QDialog, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton,
                               QStackedWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QHeaderView, QListWidget,
                               QListWidgetItem, QFileDialog, QStyle, QFormLayout,)

from app import auth_manager, config, services
from app.data_models import AppliedPart
from app.hardware.fluke_esa612 import FLUKE_ERROR_CODES, FlukeESA612

class ControlPanelWidget(QWidget):
    """
    Il widget che funge da pannello di controllo / dashboard principale.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Colonna Sinistra: Statistiche
        stats_group = QGroupBox("Dashboard")
        stats_layout = QFormLayout(stats_group)
        stats_layout.setRowWrapPolicy(QFormLayout.WrapAllRows)
        self.customers_stat_label = QLabel("...")
        self.devices_stat_label = QLabel("...")
        stats_layout.addRow("Numero Clienti:", self.customers_stat_label)
        stats_layout.addRow("Numero Dispositivi:", self.devices_stat_label)
        
        # Colonna Destra: Scadenze
        scadenze_group = QGroupBox("Verifiche Scadute o in Scadenza (30 gg)")
        scadenze_layout = QVBoxLayout(scadenze_group)
        self.scadenze_list = QListWidget()
        scadenze_layout.addWidget(self.scadenze_list)
        
        layout.addWidget(stats_group, 1)
        layout.addWidget(scadenze_group, 2)
        
        self.load_data()

    def load_data(self):
        """Carica e aggiorna i dati visualizzati nel pannello di controllo."""
        logging.info("Caricamento dati per il pannello di controllo...")
        try:
            stats = services.get_stats()
            self.customers_stat_label.setText(f"<b>{stats.get('customers', 0)}</b>")
            self.devices_stat_label.setText(f"<b>{stats.get('devices', 0)}</b>")
            
            self.scadenze_list.clear()
            devices_to_check = services.get_devices_needing_verification()
            if not devices_to_check:
                self.scadenze_list.addItem("Nessuna verifica in scadenza.")
            else:
                today = QDate.currentDate()
                for device_row in devices_to_check:
                    device = dict(device_row)
                    next_date_str = device.get('next_verification_date')
                    if not next_date_str: continue
                    
                    next_date = QDate.fromString(next_date_str, "yyyy-MM-dd")
                    item_text = f"<b>{device.get('description')}</b> (S/N: {device.get('serial_number')})<br><small><i>{device.get('customer_name')}</i> - Scadenza: {next_date.toString('dd/MM/yyyy')}</small>"
                    
                    list_item = QListWidgetItem()
                    label = QLabel(item_text)
                    
                    if next_date < today:
                        label.setStyleSheet("color: #BF616A; font-weight: bold;") # Rosso
                        list_item.setIcon(QApplication.style().standardIcon(QStyle.SP_MessageBoxCritical))
                    else:
                        label.setStyleSheet("color: #EBCB8B;") # Giallo/Ambra
                        list_item.setIcon(QApplication.style().standardIcon(QStyle.SP_MessageBoxWarning))

                    self.scadenze_list.addItem(list_item)
                    self.scadenze_list.setItemWidget(list_item, label)
        except Exception as e:
            logging.error(f"Impossibile caricare i dati della dashboard: {e}", exc_info=True)
            self.customers_stat_label.setText("<b style='color:red;'>Errore</b>")
            self.devices_stat_label.setText("<b style='color:red;'>Errore</b>")

class TestRunnerWidget(QWidget):
    """
    Widget che guida l'utente attraverso l'esecuzione di una verifica (versione completa e corretta).
    """
    def __init__(self, device_info, customer_info, mti_info, report_settings, profile_name, visual_inspection_data, technician_name, technician_username, manual_mode: bool, parent=None):
        super().__init__(parent)
        self.device_info = device_info
        self.customer_info = customer_info
        self.mti_info = mti_info
        self.report_settings = report_settings
        self.profile_name = profile_name
        self.visual_inspection_data = visual_inspection_data
        self.technician_name = technician_name
        self.technician_username = technician_username # <-- Parametro corretto
        self.manual_mode = manual_mode
        self.parent_window = parent
        
        self.current_profile = config.PROFILES.get(profile_name)
        self.applied_parts = [AppliedPart(**pa) for pa in device_info.get('applied_parts', [])]
        
        self.results = []
        self.is_running_auto = False
        self.saved_verification_id = None
        self.fluke_connection = None

        self.test_plan = self._build_test_plan()
        self.current_step_index = -1
        
        self.setup_ui()
        self.next_step() # Avvia sempre il primo passo

    def _build_test_plan(self):
        plan = []
        standard_tests = [t for t in self.current_profile.tests if not t.is_applied_part_test]
        for test in standard_tests:
            plan.append({'test': test, 'applied_part': None})

        pa_test_definitions = [t for t in self.current_profile.tests if t.is_applied_part_test]
        for pa_on_device in self.applied_parts:
            key_to_find = f"::{pa_on_device.part_type}"
            for test_def in pa_test_definitions:
                if key_to_find in test_def.limits:
                    plan.append({'test': test_def, 'applied_part': pa_on_device})
        return plan

    def setup_ui(self):
        layout = QVBoxLayout(self)
        test_group = QGroupBox(f"Verifica su: {self.device_info.get('description')} (S/N: {self.device_info.get('serial_number')})")
        test_layout = QVBoxLayout(test_group)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, len(self.test_plan)); self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True); self.progress_bar.setFormat("Passo %v di %m")
        self.test_name_label = QLabel("Inizio verifica..."); self.test_name_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.test_name_label.setTextFormat(Qt.RichText)
        self.limit_label = QLabel("Limite:")
        self.stacked_widget = QStackedWidget()
        self.manual_page = QWidget()
        manual_layout = QHBoxLayout(self.manual_page)
        self.value_input = QLineEdit(); self.value_input.setPlaceholderText("Inserisci il valore manualmente...")
        self.read_instrument_btn = QPushButton("Leggi da Strumento")
        self.read_instrument_btn.setIcon(QApplication.style().standardIcon(QStyle.SP_DialogYesButton))
        self.read_instrument_btn.clicked.connect(self.read_value_from_instrument)
        manual_layout.addWidget(self.value_input); manual_layout.addWidget(self.read_instrument_btn)
        self.auto_page = QWidget()
        auto_layout = QVBoxLayout(self.auto_page)
        auto_status_label = QLabel("Esecuzione della sequenza automatica in corso...")
        auto_status_label.setAlignment(Qt.AlignCenter)
        auto_layout.addWidget(auto_status_label)
        self.stacked_widget.addWidget(self.manual_page); self.stacked_widget.addWidget(self.auto_page)
        self.final_buttons_layout = QHBoxLayout()
        self.action_button = QPushButton("Avanti"); self.action_button.clicked.connect(self.next_step)
        self.save_db_button = QPushButton("Salva Verifica"); self.save_db_button.clicked.connect(self.save_verification_to_db)
        self.generate_pdf_button = QPushButton("Genera Report PDF"); self.generate_pdf_button.clicked.connect(self.generate_pdf_report_from_summary)
        self.print_pdf_button = QPushButton("Stampa Report"); self.print_pdf_button.clicked.connect(self.print_pdf_report_from_summary)
        self.finish_button = QPushButton("Fine"); self.finish_button.clicked.connect(self._handle_finish_clicked)
        self.final_buttons_layout.addWidget(self.action_button); self.final_buttons_layout.addWidget(self.save_db_button); self.final_buttons_layout.addWidget(self.generate_pdf_button); self.final_buttons_layout.addWidget(self.print_pdf_button); self.final_buttons_layout.addStretch(); self.final_buttons_layout.addWidget(self.finish_button)
        self.save_db_button.hide(); self.generate_pdf_button.hide(); self.print_pdf_button.hide(); self.finish_button.hide()
        self.value_input.returnPressed.connect(self.action_button.click)
        self.results_table = QTableWidget(0, 4); self.results_table.setHorizontalHeaderLabels(["Test / P.A.", "Limite", "Valore", "Esito"]); self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        test_layout.addWidget(self.progress_bar); test_layout.addWidget(self.test_name_label); test_layout.addWidget(self.limit_label); test_layout.addWidget(self.stacked_widget); test_layout.addWidget(self.results_table); test_layout.addLayout(self.final_buttons_layout)
        layout.addWidget(test_group)
        self.setLayout(layout)

    def _handle_finish_clicked(self):
        """
        Gestisce il click sul pulsante 'Fine', mostrando un avviso se la verifica
        non è stata salvata.
        """
        # Controlla se la verifica NON è stata salvata
        if not self.saved_verification_id:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Verifica non salvata")
            msg_box.setText("La verifica non è stata salvata. Cosa vuoi fare?")
            msg_box.setIcon(QMessageBox.Question)
            
            # Aggiungi i pulsanti personalizzati
            btn_save_exit = msg_box.addButton("Salva ed Esci", QMessageBox.AcceptRole)
            btn_exit = msg_box.addButton("Esci senza Salvare", QMessageBox.DestructiveRole)
            btn_cancel = msg_box.addButton("Annulla", QMessageBox.RejectRole)
            
            msg_box.exec()
            
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == btn_save_exit:
                # Se l'utente vuole salvare, chiama la funzione di salvataggio
                # e poi chiudi se il salvataggio va a buon fine.
                if self.save_verification_to_db():
                    self.parent_window.reset_main_ui()
            elif clicked_button == btn_exit:
                # Se l'utente vuole uscire comunque, chiudi
                self.parent_window.reset_main_ui()
            else: # L'utente ha premuto Annulla o ha chiuso la finestra
                return
        else:
            # Se la verifica è già stata salvata, esci normalmente
            self.parent_window.reset_main_ui()

    def _handle_instrument_error(self, error_code):
        error_message = FLUKE_ERROR_CODES.get(error_code, "Errore sconosciuto dello strumento.")
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Avviso dallo Strumento")
        msg_box.setText(f"Lo strumento ha riportato un avviso:\n\n<b>{error_message}</b>")
        msg_box.setInformativeText("Vuoi riprovare la misura o annullare l'intera verifica?")
        retry_button = msg_box.addButton("Riprova", QMessageBox.AcceptRole)
        cancel_button = msg_box.addButton("Annulla Verifica", QMessageBox.RejectRole)
        msg_box.exec()
        return "retry" if msg_box.clickedButton() == retry_button else "cancel"

    def read_value_from_instrument(self):
        current_step = self.test_plan[self.current_step_index]
        current_test = current_step['test']
        current_pa = current_step['applied_part']
        while True:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.read_instrument_btn.setEnabled(False)
            self.parent_window.statusBar().showMessage("Comunicazione con lo strumento in corso...")
            try:
                test_function_map = {
                    "Tensione alimentazione": "esegui_test_tensione_rete",
                    "Resistenza conduttore di terra": "esegui_test_resistenza_terra",
                    "Corrente dispersione diretta dispositivo": "esegui_test_dispersione_diretta",
                    "Corrente dispersione diretta P.A.": "esegui_test_dispersione_parti_applicate",
                }
                method_name = test_function_map.get(current_test.name)
                if not method_name:
                    raise NotImplementedError(f"Funzione di test non implementata per '{current_test.name}'.")
                with FlukeESA612(self.mti_info.get('com_port')) as fluke:
                    target_function = getattr(fluke, method_name)
                    kwargs = {}
                    if current_test.parameter:
                        kwargs['parametro_test'] = current_test.parameter
                    if current_pa:
                        kwargs['pa_code'] = current_pa.code
                    result = target_function(**kwargs)
            
                # --- LOGICA CORRETTA ---
                if result and result.startswith('!'):
                    QApplication.restoreOverrideCursor()
                    choice = self._handle_instrument_error(result)
                    if choice == "retry":
                        continue
                    else:
                        self.parent_window.reset_main_ui()
                        return
                else:
                    self.value_input.setText(str(result))
                    self.parent_window.statusBar().showMessage("Lettura completata.", 3000)
                    break
             # --- FINE LOGICA CORRETTA ---

            except (ValueError, ConnectionError, IOError, NotImplementedError) as e:
                QMessageBox.critical(self, "Errore di Comunicazione o Configurazione", f"Si è verificato un errore:\n{e}")
                self.parent_window.statusBar().showMessage("Errore di comunicazione.", 5000)
                break
            finally:
                self.read_instrument_btn.setEnabled(True)
                QApplication.restoreOverrideCursor()

    def execute_single_auto_test(self, fluke=None, test=None, applied_part=None):
        if test is None:
            step_data = self.test_plan[self.current_step_index]
            test, applied_part = step_data['test'], step_data['applied_part']
            QApplication.setOverrideCursor(Qt.WaitCursor)
        self.parent_window.statusBar().showMessage(f"Esecuzione: {test.name}...")
        try:
            if not self.fluke_connection:
                self.fluke_connection = FlukeESA612(self.mti_info.get('com_port'))
                self.fluke_connection.connect()
            
            test_function_map = {"Tensione alimentazione": "esegui_test_tensione_rete", "Resistenza conduttore di terra": "esegui_test_resistenza_terra", "Corrente dispersione diretta dispositivo": "esegui_test_dispersione_diretta", "Corrente dispersione diretta P.A.": "esegui_test_dispersione_parti_applicate"}
            method_name = test_function_map.get(test.name)
            if not method_name: raise NotImplementedError(f"Test non implementato: '{test.name}'.")
            target_function = getattr(self.fluke_connection, method_name)
            kwargs = {'parametro_test': test.parameter} if test.parameter else {}
            if applied_part: kwargs['pa_code'] = applied_part.code
            result = target_function(**kwargs)
            
            if result and result.startswith('!'):
                QApplication.restoreOverrideCursor()
                choice = self._handle_instrument_error(result)
                if choice == "retry": QTimer.singleShot(100, self.execute_single_auto_test)
                else: self.parent_window.reset_main_ui()
                return
            else:
                self.value_input.setText(str(result))
                QTimer.singleShot(100, self.next_step)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Errore Sequenza Automatica", f"Sequenza interrotta:\n{e}")
            self.parent_window.reset_main_ui()

    def run_automatic_sequence(self):
        if self.is_running_auto: return
        self.is_running_auto = True
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.parent_window.statusBar().showMessage("Esecuzione sequenza automatica...")
        try:
            with FlukeESA612(self.mti_info.get('com_port')) as fluke:
                for i, step in enumerate(self.test_plan):
                    self.current_step_index = i
                    self.progress_bar.setValue(i + 1)
                    self.execute_single_auto_test(fluke, step['test'], step['applied_part'])
            logging.info("Sequenza automatica completata.")
            self.show_summary()
        except (ValueError, ConnectionError, IOError, NotImplementedError, InterruptedError) as e:
            logging.error(f"Errore o interruzione durante la sequenza automatica: {e}", exc_info=False)
            if not isinstance(e, InterruptedError):
                 QMessageBox.critical(self, "Errore Sequenza Automatica", f"La sequenza è stata interrotta:\n{e}")
            self.parent_window.reset_main_ui()
        finally:
            self.is_running_auto = False
            QApplication.restoreOverrideCursor()

    def next_step(self):
        if self.current_step_index > -1:
            current_step = self.test_plan[self.current_step_index]
            if "PAUSA MANUALE" not in current_step['test'].name:
                if not self.record_result():
                    return
        self.current_step_index += 1
        if self.current_step_index >= len(self.test_plan):
            self.show_summary()
            return
        self.progress_bar.setValue(self.current_step_index + 1)
        next_step_data = self.test_plan[self.current_step_index]
        self.display_test(next_step_data['test'], next_step_data['applied_part'])
        if not self.manual_mode and "PAUSA MANUALE" not in next_step_data['test'].name:
            QTimer.singleShot(100, self.execute_single_auto_test)

    def record_result(self):
        current_step = self.test_plan[self.current_step_index]
        test = current_step['test']
        applied_part = current_step['applied_part']
        value_str = self.value_input.text().strip().replace(',', '.')
        if not value_str:
            if self.manual_mode:
                QMessageBox.warning(self, "Valore Mancante", "Inserire un valore.")
                self.value_input.setStyleSheet("border: 1px solid red;")
                return False
        try:
            cleaned_value_str = re.sub(r'[^\d.-]', '', value_str)
            value_float = float(cleaned_value_str)
        except (ValueError, TypeError):
            if self.manual_mode:
                QMessageBox.warning(self, "Valore Non Valido", "Inserire un valore numerico.")
                self.value_input.setStyleSheet("border: 1px solid red;")
                return False
        self.value_input.setStyleSheet("")
        result_name = f"{test.name} ({test.parameter})" if test.parameter else test.name
        limit_key = "::ST"
        if applied_part:
            result_name = f"{test.name} - {applied_part.name} - {applied_part.part_type}"
            limit_key = f"::{applied_part.part_type}"
        limit_obj = test.limits.get(limit_key)
        is_passed = True
        limit_value = None
        unit = limit_obj.unit if limit_obj else ""
        if limit_obj and limit_obj.high_value is not None:
            is_passed = (value_float <= limit_obj.high_value)
            limit_value = limit_obj.high_value
        result_data = {"name": result_name, "value": value_str, "limit_value": limit_value, "unit": unit, "passed": is_passed}
        self.results.append(result_data)
        self.update_results_table(result_data)
        return True

    def display_test(self, test, applied_part=None):
        is_pause = "PAUSA MANUALE" in test.name
        
        self.stacked_widget.setCurrentIndex(0)
        self.test_name_label.setText("Pausa Manuale" if is_pause else f"{test.name} {test.parameter or ''}".strip())
        
        if is_pause:
            pause_message = test.parameter.strip() if test.parameter.strip() else "Preparare l'apparecchio per il prossimo test."
            self.limit_label.setText(f"<b>{pause_message}</b><br>Premere 'Continua...' per proseguire.")
            self.value_input.hide()
            self.read_instrument_btn.hide()
            self.action_button.setText("Continua...")
        else:

            # Se non è una pausa, esegui la logica normale per mostrare un test
            self.value_input.show()
            self.read_instrument_btn.show()
            self.stacked_widget.setCurrentIndex(0)
            self.action_button.setText("Avanti")
            self.value_input.clear()
            self.value_input.setFocus()
            
            limit_key = "::ST"
            test_title = f"{test.name} {test.parameter if test.parameter else ''}".strip()
            
            if applied_part:
                test_title += f"\n<i style='color:#AAA;'>Parte Applicata: {applied_part.name} (Tipo {applied_part.part_type})</i>"
                limit_key = f"::{applied_part.part_type}"
            
            self.test_name_label.setText(test_title)
            
            limit_obj = test.limits.get(limit_key)
            limit_text = "<b>Limite:</b> Non specificato"
            if limit_obj:
                if limit_obj.high_value is not None:
                    limit_text = f"<b>Limite:</b> ≤ {limit_obj.high_value} {limit_obj.unit}"
                else:
                    limit_text = f"<b>Limite:</b> N/A (misura in {limit_obj.unit})"
            self.limit_label.setText(limit_text)

    def update_results_table(self, last_result):
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        limit_text = "N/A"
        if last_result['limit_value'] is not None:
            limit_text = f"≤ {last_result['limit_value']} {last_result['unit']}"
        self.results_table.setItem(row, 0, QTableWidgetItem(last_result['name']))
        self.results_table.setItem(row, 1, QTableWidgetItem(limit_text))
        self.results_table.setItem(row, 2, QTableWidgetItem(f"{last_result['value']} {last_result['unit']}".strip()))
        passed_item = QTableWidgetItem("PASSATO" if last_result['passed'] else "FALLITO")
        passed_item.setBackground(QColor('#A3BE8C') if last_result['passed'] else QColor('#BF616A'))
        self.results_table.setItem(row, 3, passed_item)
        self.results_table.scrollToBottom()

    def show_summary(self):
        if self.fluke_connection: 
            self.fluke_connection.disconnect()
            self.fluke_connection = None
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self.progress_bar.setFormat("Completato!")
        self.test_name_label.setText("Verifica Completata")
        self.limit_label.setText("Salvare i dati per poter generare il report, oppure terminare.")
        self.stacked_widget.hide()
        self.action_button.hide()
        self.save_db_button.show()
        self.generate_pdf_button.show()
        self.print_pdf_button.show()
        self.finish_button.show()
        self.generate_pdf_button.setEnabled(False)
        self.print_pdf_button.setEnabled(False)
        self.finish_button.setEnabled(True)
        self.save_db_button.setEnabled(True)

    def print_pdf_report_from_summary(self):
        """
        Chiama il servizio di stampa per la verifica corrente.
        """
        if not self.saved_verification_id:
            QMessageBox.warning(self, "Attenzione", "È necessario prima salvare la verifica nel database.")
            return
        
        try:
            report_settings = {"logo_path": self.report_settings.get("logo_path")}
            services.print_pdf_report(
                verification_id=self.saved_verification_id, 
                device_id=self.device_info['id'], 
                report_settings=report_settings
            )
        except Exception as e:
            logging.error(f"Errore durante la stampa del report per verifica ID {self.saved_verification_id}", exc_info=True)
            QMessageBox.critical(self, "Errore di Stampa", f"Impossibile stampare il report:\n{e}")

    def save_verification_to_db(self):
        self.parent_window.statusBar().showMessage("Salvataggio verifica in corso...")
        try:
            _, new_id = services.finalizza_e_salva_verifica(
                device_id=self.device_info['id'], profile_name=self.profile_name,
                results=self.results, visual_inspection_data=self.visual_inspection_data,
                mti_info=self.mti_info, technician_name=self.technician_name,
                technician_username=self.technician_username
            )
            self.saved_verification_id = new_id
            self.save_db_button.setEnabled(False)
            self.save_db_button.setText("Verifica Salvata!")
            self.generate_pdf_button.setEnabled(True)
            self.print_pdf_button.setEnabled(True)
            self.finish_button.setEnabled(True)
            self.parent_window.statusBar().showMessage(f"Verifica ID {new_id} salvata con successo.", 5000)
            return True # <-- AGGIUNGI: Ritorna True in caso di successo
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile salvare la verifica: {e}")
            self.parent_window.statusBar().showMessage("Salvataggio fallito.", 5000)
            return False # <-- AGGIUNGI: Ritorna False in caso di errore
            
    def generate_pdf_report_from_summary(self):
        if not self.saved_verification_id:
            QMessageBox.warning(self, "Attenzione", "È necessario prima salvare la verifica nel database.")
            return
            
        if not self.device_info:
            QMessageBox.critical(self, "Errore Dati", "Informazioni sul dispositivo non disponibili. Impossibile generare il report.")
            return

        # --> INIZIO MODIFICA <--
        # Questo idiom (valore or '') garantisce di avere sempre una stringa, anche se il valore è None
        ams_inv = (self.device_info.get('ams_inventory') or '').strip()
        serial_num = (self.device_info.get('serial_number') or '').strip()
        base_name = ams_inv if ams_inv else serial_num
        if not base_name:
            base_name = f"Report_Verifica_{self.saved_verification_id}"
        safe_base_name = re.sub(r'[\\/*?:"<>|]', '_', base_name)
        default_filename = os.path.join(os.getcwd(), f"{safe_base_name} VE.pdf")
        filename, _ = QFileDialog.getSaveFileName(self, "Salva Report PDF", default_filename, "PDF Files (*.pdf)")
        if not filename: return
        try:
            services.generate_pdf_report(
                filename, verification_id=self.saved_verification_id, 
                device_id=self.device_info['id'], report_settings=self.report_settings
            )
            QMessageBox.information(self, "Successo", f"Report generato con successo:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile generare il report: {e}")