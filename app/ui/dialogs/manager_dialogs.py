import logging
import pandas as pd
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QLineEdit, QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView, QPushButton,
    QMessageBox, QFileDialog, QProgressDialog, QStyle)
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QColor, QBrush

from app import services, auth_manager
from .detail_dialogs import CustomerDialog, DeviceDialog, InstrumentDetailDialog
from .utility_dialogs import (DateRangeSelectionDialog, VerificationStatusDialog, MonthYearSelectionDialog, 
                              MappingDialog, ImportReportDialog, VerificationViewerDialog, 
                              DateSelectionDialog, DestinationDetailDialog, DestinationSelectionDialog, SingleCalendarRangeDialog)
from app.workers.import_worker import ImportWorker
from app.workers.stm_import_worker import StmImportWorker
from app.workers.export_worker import DailyExportWorker
from app.workers.bulk_report_worker import BulkReportWorker
from app import config
from app.workers.table_export_worker import TableExportWorker

import re
import os


class NumericTableWidgetItem(QTableWidgetItem):
    """Un QTableWidgetItem personalizzato che si ordina numericamente."""
    def __lt__(self, other):
        try:
            # Prova a confrontare i valori come numeri
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            # Se non sono numeri, confrontali come testo
            return super().__lt__(other)
        
class DbManagerDialog(QDialog):
    def __init__(self, role, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.user_role = role 
        self.setWindowTitle("Gestione Anagrafiche")
        self.setMinimumSize(1280, 768)
        self.setup_ui()
        self.load_customers_table()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        top_actions_layout = self.create_top_actions()
        main_layout.addLayout(top_actions_layout)

        top_row_layout = QHBoxLayout()
        bottom_row_layout = QHBoxLayout()

        customers_group = QGroupBox("Clienti")
        cust_layout = QVBoxLayout(customers_group)
        self.customer_search_box = QLineEdit(); self.customer_search_box.setPlaceholderText("Cerca cliente...")
        self.customer_table = QTableWidget(0, 2); self.customer_table.setHorizontalHeaderLabels(["ID", "Nome"])
        self.setup_table_style(self.customer_table)
        cust_buttons_layout = self.create_customer_buttons()
        cust_layout.addWidget(self.customer_search_box); cust_layout.addWidget(self.customer_table); cust_layout.addLayout(cust_buttons_layout)
        top_row_layout.addWidget(customers_group, 1)

        self.destinations_group = QGroupBox("Destinazioni / Sedi")
        dest_layout = QVBoxLayout(self.destinations_group)
        self.destination_table = QTableWidget(0, 3); self.destination_table.setHorizontalHeaderLabels(["ID", "Nome", "Indirizzo"])
        self.setup_table_style(self.destination_table)
        dest_buttons_layout = self.create_destination_buttons()
        dest_layout.addWidget(self.destination_table); dest_layout.addLayout(dest_buttons_layout)
        top_row_layout.addWidget(self.destinations_group, 1)

        self.devices_group = QGroupBox("Dispositivi")
        dev_layout = QVBoxLayout(self.devices_group)
        self.device_search_box = QLineEdit(); self.device_search_box.setPlaceholderText("Cerca dispositivo...")
        self.device_table = QTableWidget(0, 10) # Aggiunta una colonna per lo stato
        self.device_table.setHorizontalHeaderLabels(["ID", "Descrizione", "Reparto", "S/N", "Costruttore", "Modello", "Inv. Cliente", "Inv. AMS", "Int. Verifica (Mesi)", "Stato"])
        self.setup_table_style(self.device_table)
        dev_buttons_layout = self.create_device_buttons()
        dev_layout.addWidget(self.device_search_box); dev_layout.addWidget(self.device_table); dev_layout.addLayout(dev_buttons_layout)
        bottom_row_layout.addWidget(self.devices_group, 1)

        self.verifications_group = QGroupBox("Storico Verifiche")
        verif_layout = QVBoxLayout(self.verifications_group)
        self.verifications_table = QTableWidget(0, 6)
        self.verifications_table.setHorizontalHeaderLabels(["ID", "Data", "Esito Globale", "Profilo", "Tecnico", "Codice Verifica"])
        self.setup_table_style(self.verifications_table, hide_id=False)
        verif_buttons_layout = self.create_verification_buttons()
        verif_layout.addWidget(self.verifications_table); verif_layout.addLayout(verif_buttons_layout)
        bottom_row_layout.addWidget(self.verifications_group, 1)
        
        main_layout.addLayout(top_row_layout)
        main_layout.addLayout(bottom_row_layout)
        self.setLayout(main_layout)

        self.customer_search_box.textChanged.connect(self.load_customers_table)
        self.customer_table.itemSelectionChanged.connect(self.customer_selected)
        self.destination_table.itemSelectionChanged.connect(self.destination_selected)
        self.device_table.itemSelectionChanged.connect(self.device_selected)
        self.device_search_box.textChanged.connect(self.destination_selected)
        
        self.reset_views(level='customer')

    def setup_table_style(self, table, hide_id=True):
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        if hide_id: table.hideColumn(0)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)

    def create_button(self, text, slot, icon=None, enabled=True):
        btn = QPushButton(text)
        if icon: btn.setIcon(QApplication.style().standardIcon(icon))
        btn.clicked.connect(slot)
        btn.setEnabled(enabled)
        return btn

    def create_top_actions(self):
        layout = QHBoxLayout()
        layout.addWidget(self.create_button("Importa Dispositivi...", self.import_from_file, QStyle.SP_ArrowUp))
        layout.addWidget(self.create_button("Importa da Archivio (.stm)...", self.import_from_stm, QStyle.SP_ArrowDown))
        layout.addWidget(self.create_button("Esporta Verifiche per Data...", self.export_daily_verifications, QStyle.SP_DialogSaveButton))
        layout.addStretch()
        layout.addWidget(self.create_button("GGenera Report per Periodo...", self.generate_monthly_reports, QStyle.SP_FileDialogToParent))
        layout.addWidget(self.create_button("Filtra Verifiche per Periodo...", self.open_period_filter_dialog, QStyle.SP_FileDialogDetailedView))
        return layout

    def create_customer_buttons(self):
        layout = QHBoxLayout()
        self.add_cust_btn = self.create_button("Aggiungi", self.add_customer)
        self.edit_cust_btn = self.create_button("Modifica", self.edit_customer, enabled=False)
        self.del_cust_btn = self.create_button("Elimina", self.delete_customer, enabled=False)
        self.show_all_devices_btn = QPushButton("Mostra Tutti i Dispositivi")
        self.show_all_devices_btn.clicked.connect(self.show_all_customer_devices)
        self.show_all_devices_btn.setEnabled(False)
        layout.addStretch() 
        layout.addWidget(self.add_cust_btn)
        layout.addWidget(self.edit_cust_btn) 
        layout.addWidget(self.del_cust_btn)
        layout.addWidget(self.show_all_devices_btn)
        if self.user_role == 'technician': self.edit_cust_btn.setVisible(False)
        if self.user_role == 'technician': self.add_cust_btn.setVisible(False)
        if self.user_role == 'technician': self.del_cust_btn.setVisible(False)
        return layout

    def create_destination_buttons(self):
        layout = QHBoxLayout()
        self.add_dest_btn = self.create_button("Aggiungi", self.add_destination, enabled=False)
        self.edit_dest_btn = self.create_button("Modifica", self.edit_destination, enabled=False)
        self.del_dest_btn = self.create_button("Elimina", self.delete_destination, enabled=False)
        self.export_dest_table_btn = self.create_button("Crea Tabella Excel...", self.export_destination_table, enabled=False)
        layout.addWidget(self.add_dest_btn) 
        layout.addWidget(self.edit_dest_btn) 
        layout.addWidget(self.del_dest_btn)
        layout.addWidget(self.export_dest_table_btn)
        if self.user_role == 'technician': self.edit_dest_btn.setVisible(False)
        return layout

    def export_destination_table(self):
        """Avvia l'esportazione della tabella per la destinazione selezionata."""
        dest_id = self.get_selected_id(self.destination_table)
        if not dest_id:
            return QMessageBox.warning(self, "Selezione Mancante", "Seleziona una destinazione per cui generare la tabella.")
        
        customer_name = self.customer_table.item(self.customer_table.currentRow(), 1).text()
        destination_name = self.destination_table.item(self.destination_table.currentRow(), 1).text()
        
        safe_name = re.sub(r'[\\/*?:"<>|]', '_', f"{destination_name}")
        default_filename = f"Tabella Verifiche_{safe_name}.xlsx"

        output_path, _ = QFileDialog.getSaveFileName(self, "Salva Tabella Excel", default_filename, "File Excel (*.xlsx)")
        if not output_path:
            return

        self.thread = QThread()
        self.worker = TableExportWorker(dest_id, output_path)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_table_export_finished)
        self.worker.error.connect(self.on_table_export_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.setWindowTitle("Manager Anagrafiche (Esportazione Tabella...)")
        self.thread.start()

    def on_table_export_finished(self, message):
        self.setWindowTitle("Manager Anagrafiche")
        QMessageBox.information(self, "Esportazione Completata", message)

    def on_table_export_error(self, error_message):
        self.setWindowTitle("Manager Anagrafiche")
        QMessageBox.critical(self, "Errore Esportazione", error_message)


    def create_device_buttons(self):
        layout = QHBoxLayout()
        self.add_dev_btn = self.create_button("Aggiungi", self.add_device, enabled=False)
        self.edit_dev_btn = self.create_button("Modifica", self.edit_device, enabled=False)
        self.move_dev_btn = self.create_button("Sposta", self.move_device, enabled=False)
        self.decommission_dev_btn = self.create_button("Dismetti", self.decommission_device, enabled=False)
        self.decommission_dev_btn.setVisible(False)
        self.reactivate_dev_btn = self.create_button("Riattiva", self.reactivate_device, enabled=False)
        self.reactivate_dev_btn.setVisible(False)
        self.del_dev_btn = self.create_button("Elimina", self.delete_device, enabled=False)
        
        layout.addStretch()
        layout.addWidget(self.add_dev_btn)
        layout.addWidget(self.edit_dev_btn)
        layout.addWidget(self.move_dev_btn)
        layout.addWidget(self.decommission_dev_btn)
        layout.addWidget(self.reactivate_dev_btn)
        layout.addWidget(self.del_dev_btn)
        return layout
        
    def create_verification_buttons(self):
        layout = QHBoxLayout()
        self.view_verif_btn = self.create_button("Visualizza Dettagli", self.view_verification_details, enabled=False)
        self.gen_report_btn = self.create_button("Genera Report PDF", self.generate_old_report, enabled=False)
        self.print_report_btn = self.create_button("Stampa Report", self.print_old_report, enabled=False)
        self.delete_verif_btn = self.create_button("Elimina Verifica", self.delete_verification, enabled=False)
        layout.addStretch(); layout.addWidget(self.view_verif_btn); layout.addWidget(self.gen_report_btn); layout.addWidget(self.print_report_btn); layout.addWidget(self.delete_verif_btn)
        return layout

    def get_selected_id(self, table: QTableWidget):
        selected_rows = table.selectionModel().selectedRows()
        if not selected_rows: return None
        id_item = table.item(selected_rows[0].row(), 0)
        return int(id_item.text()) if id_item else None

    def reset_views(self, level='customer'):
        if level == 'customer': self.destination_table.setRowCount(0); self.destinations_group.setTitle("Destinazioni / Sedi"); self.set_destination_buttons_enabled(False, False) # <-- MODIFICA QUESTA RIGA
        if level in ['customer', 'destination']: self.device_table.setRowCount(0); self.devices_group.setTitle("Dispositivi"); self.set_device_buttons_enabled(False)
        if level in ['customer', 'destination', 'device']: self.verifications_table.setRowCount(0); self.verifications_group.setTitle("Storico Verifiche"); self.set_verification_buttons_enabled(False)

    def set_customer_buttons_enabled(self, enabled): self.edit_cust_btn.setEnabled(enabled); self.del_cust_btn.setEnabled(enabled)
    def set_destination_buttons_enabled(self, add_enabled, other_enabled):
        self.add_dest_btn.setEnabled(add_enabled)
        self.edit_dest_btn.setEnabled(other_enabled)
        self.del_dest_btn.setEnabled(other_enabled)
        self.export_dest_table_btn.setEnabled(other_enabled)
    def set_device_buttons_enabled(self, enabled): self.add_dev_btn.setEnabled(enabled); self.edit_dev_btn.setEnabled(enabled); self.move_dev_btn.setEnabled(enabled); self.del_dev_btn.setEnabled(enabled)
    def set_verification_buttons_enabled(self, enabled): self.view_verif_btn.setEnabled(enabled); self.gen_report_btn.setEnabled(enabled); self.print_report_btn.setEnabled(enabled); self.delete_verif_btn.setEnabled(enabled)
        
    def load_customers_table(self):
        self.reset_views(level='customer') 
        self.customer_table.setRowCount(0)
        self.customer_table.setSortingEnabled(False) 
        customers = services.get_all_customers(self.customer_search_box.text())
        for cust in customers:
            row = self.customer_table.rowCount(); self.customer_table.insertRow(row)
            self.customer_table.setItem(row, 0, NumericTableWidgetItem(str(cust['id'])))  
            self.customer_table.setItem(row, 1, QTableWidgetItem(cust['name']))
        self.customer_table.setSortingEnabled(True) 
    
    def customer_selected(self):
        self.reset_views(level='destination')
        cust_id = self.get_selected_id(self.customer_table)
        self.set_customer_buttons_enabled(cust_id is not None); self.show_all_devices_btn.setEnabled(cust_id is not None)
        if cust_id:
            customer_name = self.customer_table.item(self.customer_table.currentRow(), 1).text()
            self.destinations_group.setTitle(f"Destinazioni per '{customer_name}'")
            self.load_destinations_table(cust_id); self.set_destination_buttons_enabled(True)

    def load_destinations_table(self, customer_id):
        self.destination_table.setRowCount(0)
        self.destination_table.setSortingEnabled(False)
        destinations = services.database.get_destinations_for_customer(customer_id)
        for dest in destinations:
            row = self.destination_table.rowCount(); self.destination_table.insertRow(row)
            self.destination_table.setItem(row, 0, NumericTableWidgetItem(str(dest['id'])))
            self.destination_table.setItem(row, 1, QTableWidgetItem(dest['name']))
            self.destination_table.setItem(row, 2, QTableWidgetItem(dest['address']))
        self.destination_table.resizeColumnsToContents()
        self.destination_table.setSortingEnabled(True)

    def destination_selected(self):
        self.reset_views(level='device')
        dest_id = self.get_selected_id(self.destination_table)
        is_dest_selected = dest_id is not None
        
        # Abilita il pulsante di esportazione insieme agli altri
        self.set_destination_buttons_enabled(self.get_selected_id(self.customer_table) is not None, is_dest_selected)

        if dest_id:
            dest_name = self.destination_table.item(self.destination_table.currentRow(), 1).text()
            self.devices_group.setTitle(f"Dispositivi in '{dest_name}'")
            self.load_devices_table(dest_id)
            self.set_device_buttons_enabled(True)

    def load_devices_table(self, destination_id):
        self.device_table.setSortingEnabled(False)
        self.device_table.setRowCount(0)
        search_text = self.device_search_box.text()
        
        # Chiama la nuova funzione del database che include i dismessi
        devices = services.database.get_devices_for_destination_manager(destination_id, search_text)
        
        for dev_row in devices:
            dev = dict(dev_row)
            row = self.device_table.rowCount()
            self.device_table.insertRow(row)
            
            status = dev.get('status', 'active')
            status_text = 'attivo' if status == 'active' else 'dismesso'
            
            # Imposta le celle
            self.device_table.setItem(row, 0, NumericTableWidgetItem(str(dev.get('id'))))
            self.device_table.setItem(row, 1, QTableWidgetItem(dev.get('description')))
            self.device_table.setItem(row, 2, QTableWidgetItem(dev.get('department')))
            self.device_table.setItem(row, 3, QTableWidgetItem(dev.get('serial_number')))
            self.device_table.setItem(row, 4, QTableWidgetItem(dev.get('manufacturer')))
            self.device_table.setItem(row, 5, QTableWidgetItem(dev.get('model')))
            self.device_table.setItem(row, 6, QTableWidgetItem(dev.get('customer_inventory')))
            self.device_table.setItem(row, 7, QTableWidgetItem(dev.get('ams_inventory')))
            interval = dev.get('verification_interval')
            interval_text = str(interval) if interval is not None else "N/A"
            self.device_table.setItem(row, 8, NumericTableWidgetItem(interval_text))
            self.device_table.setItem(row, 9, QTableWidgetItem(status_text))

            # Colora la riga se il dispositivo è dismesso
            if status == 'decommissioned':
                for col in range(self.device_table.columnCount()):
                    self.device_table.item(row, col).setForeground(QBrush(QColor("blue")))

        self.device_table.resizeColumnsToContents()
        self.device_table.setSortingEnabled(True)

    def decommission_device(self):
        """Marca il dispositivo selezionato come dismesso."""
        dev_id = self.get_selected_id(self.device_table)
        dest_id = self.get_selected_id(self.destination_table)
        if not dev_id or not dest_id: return
        
        reply = QMessageBox.question(self, 'Conferma Dismissione', 
                                     "Sei sicuro di voler marcare questo dispositivo come dismesso?\nNon apparirà più nelle liste per nuove verifiche.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            services.decommission_device(dev_id)
            self.load_devices_table(dest_id) # Ricarica per aggiornare la vista

    def reactivate_device(self):
        """Riattiva un dispositivo dismesso."""
        dev_id = self.get_selected_id(self.device_table)
        dest_id = self.get_selected_id(self.destination_table)
        if not dev_id or not dest_id: return

        reply = QMessageBox.question(self, 'Conferma Riattivazione', 
                                     "Sei sicuro di voler riattivare questo dispositivo?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            services.reactivate_device(dev_id)
            self.load_devices_table(dest_id)

    def device_selected(self):
        """Gestisce la selezione di un dispositivo, mostrando/nascondendo i pulsanti appropriati."""
        self.reset_views(level='verification')
        dev_id = self.get_selected_id(self.device_table)

        # Stato di default: nessun dispositivo selezionato
        self.edit_dev_btn.setEnabled(False)
        self.del_dev_btn.setEnabled(False)
        self.move_dev_btn.setEnabled(False)
        self.decommission_dev_btn.setEnabled(False)
        self.reactivate_dev_btn.setVisible(False)
        self.decommission_dev_btn.setVisible(True) # Il pulsante Dismetti è visibile di default

        if dev_id:
            # Un dispositivo è stato selezionato
            current_row = self.device_table.currentRow()
            status_item = self.device_table.item(current_row, 9)
            status = status_item.text() if status_item else 'attivo'
            is_active = (status == 'attivo')

            # Abilita i pulsanti comuni
            self.edit_dev_btn.setEnabled(True)
            self.del_dev_btn.setEnabled(True)
            self.move_dev_btn.setEnabled(is_active)

            # Mostra/nascondi i pulsanti di stato in base allo stato del dispositivo
            self.decommission_dev_btn.setVisible(is_active)
            self.decommission_dev_btn.setEnabled(is_active)
            self.reactivate_dev_btn.setVisible(not is_active)
            self.reactivate_dev_btn.setEnabled(not is_active)
            
            # Carica le verifiche
            dev_desc = self.device_table.item(current_row, 1).text()
            self.verifications_group.setTitle(f"Storico Verifiche per '{dev_desc}'")
            self.load_verifications_table(dev_id)
    
    def load_verifications_table(self, device_id):
        self.verifications_table.setRowCount(0)
        self.verifications_table.setSortingEnabled(False) 
        verifications = services.get_verifications_for_device(device_id)
        for verif in verifications:
            row = self.verifications_table.rowCount()
            self.verifications_table.insertRow(row)
            self.verifications_table.setItem(row, 0, NumericTableWidgetItem(str(verif.get('id', 0))))
            self.verifications_table.setItem(row, 1, QTableWidgetItem(verif.get('verification_date')))
            status_item = QTableWidgetItem(verif.get('overall_status'))
            status_item.setBackground(QColor('#A3BE8C') if verif.get('overall_status') == 'PASSATO' else QColor('#BF616A'))
            self.verifications_table.setItem(row, 2, status_item)
            profile_key = verif.get('profile_name', '')
            profile = config.PROFILES.get(profile_key)
            profile_display_name = profile.name if profile else profile_key
            self.verifications_table.setItem(row, 3, QTableWidgetItem(profile_display_name))
            self.verifications_table.setItem(row, 4, QTableWidgetItem(verif.get('technician_name', '')))
            self.verifications_table.setItem(row, 5, QTableWidgetItem(verif.get('verification_code', '')))
        self.verifications_table.resizeColumnsToContents(); 
        self.set_verification_buttons_enabled(self.verifications_table.rowCount() > 0)
        self.verifications_table.setSortingEnabled(True)

    def add_customer(self):
        dialog = CustomerDialog(parent=self)
        if dialog.exec():
            try: services.add_customer(**dialog.get_data()); self.load_customers_table()
            except ValueError as e: QMessageBox.warning(self, "Dati non validi", str(e))

    def edit_customer(self):
        cust_id = self.get_selected_id(self.customer_table);
        if not cust_id: return
        customer_data = dict(services.database.get_customer_by_id(cust_id))
        dialog = CustomerDialog(customer_data, self)
        if dialog.exec():
            try: services.update_customer(cust_id, **dialog.get_data()); self.load_customers_table()
            except ValueError as e: QMessageBox.warning(self, "Dati non validi", str(e))

    def delete_customer(self):
        cust_id = self.get_selected_id(self.customer_table)
        if not cust_id: return
        reply = QMessageBox.question(self, 'Conferma', 'Eliminare il cliente e TUTTE le sue destinazioni e dispositivi?')
        if reply == QMessageBox.Yes:
            success, message = services.delete_customer(cust_id)
            if success: self.load_customers_table()
            else: QMessageBox.critical(self, "Errore", message)

    def add_destination(self):
        cust_id = self.get_selected_id(self.customer_table)
        if not cust_id: return
        dialog = DestinationDetailDialog(parent=self)
        if dialog.exec():
            try: data = dialog.get_data(); services.add_destination(cust_id, data['name'], data['address']); self.load_destinations_table(cust_id)
            except ValueError as e: QMessageBox.warning(self, "Dati non validi", str(e))

    def edit_destination(self):
        dest_id = self.get_selected_id(self.destination_table); cust_id = self.get_selected_id(self.customer_table)
        if not dest_id or not cust_id: return
        dest_data = dict(services.database.get_destination_by_id(dest_id))
        dialog = DestinationDetailDialog(destination_data=dest_data, parent=self)
        if dialog.exec():
            try: data = dialog.get_data(); services.update_destination(dest_id, data['name'], data['address']); self.load_destinations_table(cust_id)
            except ValueError as e: QMessageBox.warning(self, "Dati non validi", str(e))

    def delete_destination(self):
        dest_id = self.get_selected_id(self.destination_table); cust_id = self.get_selected_id(self.customer_table)
        if not dest_id or not cust_id: return
        reply = QMessageBox.question(self, 'Conferma', 'Eliminare questa destinazione? (Verranno eliminati anche tutti i dispositivi al suo interno)')
        if reply == QMessageBox.Yes:
            try: services.delete_destination(dest_id); self.load_destinations_table(cust_id)
            except ValueError as e: QMessageBox.critical(self, "Errore", str(e))

    def add_device(self):
        cust_id = self.get_selected_id(self.customer_table); dest_id = self.get_selected_id(self.destination_table)
        if not dest_id or not cust_id: return QMessageBox.warning(self, "Selezione Mancante", "Seleziona un cliente e una destinazione.")
        dialog = DeviceDialog(customer_id=cust_id, destination_id=dest_id, parent=self)
        if dialog.exec():
            try: services.add_device(**dialog.get_data()); self.load_devices_table(dest_id)
            except ValueError as e:
                QMessageBox.warning(self, "Errore validazione", str(e))
                return
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Impossibile salvare il dispositivo:\n{e}")
                return

    def edit_device(self):
        cust_id = self.get_selected_id(self.customer_table); dev_id = self.get_selected_id(self.device_table); dest_id = self.get_selected_id(self.destination_table)
        if not dev_id or not cust_id or not dest_id: return
        device_data = dict(services.database.get_device_by_id(dev_id))
        dialog = DeviceDialog(customer_id=cust_id, device_data=device_data, parent=self)
        if dialog.exec():
            try: services.update_device(dev_id, **dialog.get_data()); self.load_devices_table(dest_id)
            except ValueError as e:
                QMessageBox.warning(self, "Errore validazione", str(e))
                return
            except Exception as e:
                QMessageBox.critical(self, "Errore", f"Impossibile salvare il dispositivo:\n{e}")
                return

    def delete_device(self):
        dev_id = self.get_selected_id(self.device_table); dest_id = self.get_selected_id(self.destination_table)
        if not dev_id or not dest_id: return
        reply = QMessageBox.question(self, 'Conferma', 'Eliminare questo dispositivo e tutte le sue verifiche?')
        if reply == QMessageBox.Yes: services.delete_device(dev_id); self.load_devices_table(dest_id)

    def move_device(self):
        dev_id = self.get_selected_id(self.device_table); old_dest_id = self.get_selected_id(self.destination_table)
        if not dev_id: return QMessageBox.warning(self, "Selezione Mancante", "Seleziona un dispositivo da spostare.")
        dialog = DestinationSelectionDialog(self)
        if dialog.exec():
            new_dest_id = dialog.selected_destination_id
            if new_dest_id and new_dest_id != old_dest_id:
                try: services.move_device_to_destination(dev_id, new_dest_id); self.load_devices_table(old_dest_id); QMessageBox.information(self, "Successo", "Dispositivo spostato.")
                except Exception as e: QMessageBox.critical(self, "Errore", f"Impossibile spostare il dispositivo: {e}")

    def import_from_file(self):
        dest_id = self.get_selected_id(self.destination_table)
        if not dest_id: return QMessageBox.warning(self, "Selezione Mancante", "Seleziona una destinazione in cui importare.")
        filename, _ = QFileDialog.getOpenFileName(self, "Seleziona File", "", "File Excel/CSV (*.xlsx *.csv)")
        if not filename: return
        try: df_headers = pd.read_csv(filename, sep=';', dtype=str, nrows=0).columns.tolist() if filename.endswith('.csv') else pd.read_excel(filename, dtype=str, nrows=0).columns.tolist()
        except Exception as e: QMessageBox.critical(self, "Errore Lettura File", f"Impossibile leggere le intestazioni:\n{e}"); return
        map_dialog = MappingDialog(df_headers, self)
        if map_dialog.exec() == QDialog.Accepted:
            mapping = map_dialog.get_mapping()
            if mapping is None: return
            self.progress_dialog = QProgressDialog("Importazione...", "Annulla", 0, 100, self); self.progress_dialog.setWindowModality(Qt.WindowModal)
            self.thread = QThread(); self.worker = ImportWorker(filename, mapping, dest_id)
            self.worker.moveToThread(self.thread)
            self.worker.progress_updated.connect(self.progress_dialog.setValue); self.progress_dialog.canceled.connect(self.worker.cancel)
            self.thread.started.connect(self.worker.run); self.worker.finished.connect(self.on_import_finished); self.worker.error.connect(self.on_import_error)
            self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater); self.thread.finished.connect(self.progress_dialog.close)
            self.thread.start(); self.progress_dialog.exec()

    def on_import_finished(self, added_count, skipped_rows_details, status):
        dest_id = self.get_selected_id(self.destination_table)
        if dest_id: self.load_devices_table(dest_id)
        if status == "Annullato": QMessageBox.warning(self, "Importazione Annullata", "Operazione annullata."); return
        summary = f"Importazione terminata.\n- Dispositivi aggiunti: {added_count}\n- Righe ignorate: {len(skipped_rows_details)}"
        msg_box = QMessageBox(self); msg_box.setIcon(QMessageBox.Information); msg_box.setWindowTitle("Importazione Completata"); msg_box.setText(summary)
        if skipped_rows_details:
            details_button = msg_box.addButton("Visualizza Dettagli...", QMessageBox.ActionRole)
        msg_box.addButton("OK", QMessageBox.AcceptRole); msg_box.exec()
        if skipped_rows_details and msg_box.clickedButton() == details_button:
            report_dialog = ImportReportDialog("Dettaglio Righe Ignorate", skipped_rows_details, self); report_dialog.exec()

    def on_import_error(self, error_message):
        if hasattr(self, 'progress_dialog'): self.progress_dialog.close()
        QMessageBox.critical(self, "Errore di Importazione", error_message)

    def import_from_stm(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Seleziona Archivio .stm", "", "File STM (*.stm)")
        if not filepath: return
        self.thread = QThread(); self.worker = StmImportWorker(filepath)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.finished.connect(self.on_stm_import_finished); self.worker.error.connect(self.on_import_error)
        self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater)
        self.setWindowTitle("Manager Anagrafiche (Importazione...)"); self.thread.start()

    def on_stm_import_finished(self, verif_imported, verif_skipped, dev_new, cust_new):
        self.setWindowTitle("Manager Anagrafiche"); self.load_customers_table()
        QMessageBox.information(self, "Importazione Completata", f"Importazione da archivio completata.\n- Verifiche importate: {verif_imported}\n- Verifiche saltate: {verif_skipped}\n- Nuovi dispositivi: {dev_new}")

    def export_daily_verifications(self):
        date_dialog = DateSelectionDialog(self)
        if date_dialog.exec() == QDialog.Accepted:
            target_date = date_dialog.getSelectedDate()
            default_filename = f"Export_Verifiche_{target_date.replace('-', '')}.stm"
            output_path, _ = QFileDialog.getSaveFileName(self, "Salva Esportazione", default_filename, "File STM (*.stm)")
            if not output_path: return
            self.thread = QThread(); self.worker = DailyExportWorker(target_date, output_path)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run); self.worker.finished.connect(self.on_export_finished); self.worker.error.connect(self.on_export_error)
            self.worker.finished.connect(self.thread.quit); self.worker.finished.connect(self.worker.deleteLater); self.thread.finished.connect(self.thread.deleteLater)
            self.setWindowTitle("Manager Anagrafiche (Esportazione...)"); self.thread.start()
    
    def on_export_finished(self, status, message):
        self.setWindowTitle("Manager Anagrafiche")
        if status == "Success": QMessageBox.information(self, "Esportazione Completata", message)
        else: QMessageBox.warning(self, "Esportazione", message)

    def on_export_error(self, error_message):
        self.setWindowTitle("Manager Anagrafiche"); QMessageBox.critical(self, "Errore Esportazione", error_message)

    def generate_monthly_reports(self):
        dest_id = self.get_selected_id(self.destination_table)
        if not dest_id: 
            return QMessageBox.warning(self, "Selezione Mancante", "Seleziona una destinazione.")

        # --> USA LA NUOVA DIALOG <--
        period_dialog = SingleCalendarRangeDialog(self)
        
        if not period_dialog.exec(): 
            return

        start_date, end_date = period_dialog.get_date_range()
        
        # 3. Chiama la NUOVA funzione del database con l'intervallo di date
        verifications = services.database.get_verifications_for_destination_by_date_range(dest_id, start_date, end_date)
        
        if not verifications: 
            return QMessageBox.information(self, "Nessuna Verifica", f"Nessuna verifica trovata nel periodo selezionato.")

        output_folder = QFileDialog.getExistingDirectory(self, "Seleziona Cartella di Destinazione per i Report")
        if not output_folder: 
            return

        # Il resto della logica per avviare il worker rimane identico
        report_settings = {"logo_path": self.main_window.logo_path}
        self.progress_dialog = QProgressDialog("Generazione report...", "Annulla", 0, 100, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        
        self.thread = QThread()
        self.worker = BulkReportWorker(verifications, output_folder, report_settings)
        self.worker.moveToThread(self.thread)
        
        self.progress_dialog.canceled.connect(self.worker.cancel)
        self.worker.progress_updated.connect(self.on_bulk_report_progress)
        self.worker.finished.connect(self.on_bulk_report_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.progress_dialog.close)
        
        self.thread.started.connect(self.worker.run)
        self.progress_dialog.show()
        self.thread.start()

    def on_bulk_report_progress(self, percent, message):
        if hasattr(self, 'progress_dialog'): self.progress_dialog.setValue(percent); self.progress_dialog.setLabelText(message)

    def on_bulk_report_finished(self, success_count, failed_reports):
        summary = f"Generazione completata.\n- Report creati: {success_count}"
        if failed_reports: summary += f"\n- Errori: {len(failed_reports)}"
        msg_box = QMessageBox(QMessageBox.Information, "Operazione Terminata", summary, parent=self)
        if failed_reports: msg_box.setDetailedText("Dettaglio errori:\n" + "\n".join(failed_reports))
        msg_box.exec()

    def open_period_filter_dialog(self):
        dest_id = self.get_selected_id(self.destination_table)
        if not dest_id: return QMessageBox.warning(self, "Selezione Mancante", "Seleziona una destinazione.")
        date_dialog = SingleCalendarRangeDialog(self)
        if not date_dialog.exec(): return
        start_date, end_date = date_dialog.get_date_range()
        try:
            verified, unverified = services.database.get_devices_verification_status_by_period(dest_id, start_date, end_date)
            results_dialog = VerificationStatusDialog(verified, unverified, self); results_dialog.exec()
        except Exception as e: QMessageBox.critical(self, "Errore", f"Impossibile recuperare lo stato: {e}")
        
    def view_verification_details(self):
        verif_id = self.get_selected_id(self.verifications_table)
        dev_id = self.get_selected_id(self.device_table)
        if not verif_id or not dev_id: return
        all_verifs = services.get_verifications_for_device(dev_id)
        verif_data = next((v for v in all_verifs if v.get('id') == verif_id), None)
        if verif_data: dialog = VerificationViewerDialog(verif_data, self); dialog.exec()
        else: QMessageBox.critical(self, "Errore Dati", "Impossibile trovare i dati per la verifica.")

    def generate_old_report(self):
        verif_id = self.get_selected_id(self.verifications_table); dev_id = self.get_selected_id(self.device_table)
        if not verif_id or not dev_id: return
        device_info = services.get_device_by_id(dev_id)
        if not device_info: return QMessageBox.critical(self, "Errore", "Impossibile trovare i dati del dispositivo.")
        ams_inv = device_info.get('ams_inventory', '').strip(); serial_num = device_info.get('serial_number', '').strip()
        base_name = ams_inv if ams_inv else serial_num
        if not base_name: base_name = f"Report_Verifica_{verif_id}"
        safe_base_name = re.sub(r'[\\/*?:"<>|]', '_', base_name)
        default_filename = f"{safe_base_name} VE.pdf"
        filename, _ = QFileDialog.getSaveFileName(self, "Salva Report PDF", default_filename, "PDF Files (*.pdf)")
        if not filename: return
        try:
            report_settings = {"logo_path": self.main_window.logo_path}
            services.generate_pdf_report(filename, verif_id, dev_id, report_settings)
            QMessageBox.information(self, "Successo", f"Report generato con successo: {filename}")
        except Exception as e: QMessageBox.critical(self, "Errore", f"Impossibile generare il report: {e}")

    def print_old_report(self):
        verif_id = self.get_selected_id(self.verifications_table); dev_id = self.get_selected_id(self.device_table)
        if not verif_id or not dev_id: return
        try:
            report_settings = {"logo_path": self.main_window.logo_path}
            services.print_pdf_report(verif_id, dev_id, report_settings)
        except Exception as e: QMessageBox.critical(self, "Errore di Stampa", f"Impossibile stampare il report:\n{e}")

    def delete_verification(self):
        verif_id = self.get_selected_id(self.verifications_table); dev_id = self.get_selected_id(self.device_table)
        if not verif_id or not dev_id: return
        reply = QMessageBox.question(self, 'Conferma', f"Sei sicuro di voler eliminare la verifica ID {verif_id}?")
        if reply == QMessageBox.Yes: services.delete_verification(verif_id); self.load_verifications_table(dev_id)

    def show_all_customer_devices(self):
        cust_id = self.get_selected_id(self.customer_table)
        if not cust_id: return
        self.destination_table.clearSelection()
        customer_name = self.customer_table.item(self.customer_table.currentRow(), 1).text()
        self.devices_group.setTitle(f"Tutti i Dispositivi per '{customer_name}'")
        self.set_device_buttons_enabled(False)
        self.device_table.setSortingEnabled(False)
        self.device_table.setRowCount(0)
        search_text = self.device_search_box.text()
        devices = services.database.get_all_devices_for_customer(cust_id, search_text)
        for dev_row in devices:
            dev = dict(dev_row); row = self.device_table.rowCount(); self.device_table.insertRow(row)
            self.device_table.setItem(row, 0, QTableWidgetItem(str(dev.get('id')))); self.device_table.setItem(row, 1, QTableWidgetItem(dev.get('description'))); self.device_table.setItem(row, 2, QTableWidgetItem(dev.get('department'))); self.device_table.setItem(row, 3, QTableWidgetItem(dev.get('serial_number'))); self.device_table.setItem(row, 4, QTableWidgetItem(dev.get('manufacturer'))); self.device_table.setItem(row, 5, QTableWidgetItem(dev.get('model'))); self.device_table.setItem(row, 6, QTableWidgetItem(dev.get('customer_inventory'))); self.device_table.setItem(row, 7, QTableWidgetItem(dev.get('ams_inventory'))); interval = dev.get('verification_interval'); interval_text = str(interval) if interval is not None else "N/A"; self.device_table.setItem(row, 8, QTableWidgetItem(interval_text))
        self.device_table.resizeColumnsToContents()
        self.device_table.setSortingEnabled(True)

class InstrumentManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestione Anagrafica Strumenti")
        self.setMinimumSize(800, 500)
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Nome Strumento", "Seriale", "Versione FW", "Data Cal."])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader(); header.setSectionResizeMode(0, QHeaderView.ResizeToContents); header.setSectionResizeMode(1, QHeaderView.Stretch); header.setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.table)
        buttons_layout = QHBoxLayout()
        add_btn = QPushButton("Aggiungi"); add_btn.clicked.connect(self.add_instrument)
        edit_btn = QPushButton("Modifica"); edit_btn.clicked.connect(self.edit_instrument)
        delete_btn = QPushButton("Elimina"); delete_btn.clicked.connect(self.delete_instrument)
        default_btn = QPushButton("Imposta come Predefinito"); default_btn.clicked.connect(self.set_default)
        buttons_layout.addWidget(add_btn); buttons_layout.addWidget(edit_btn); buttons_layout.addWidget(delete_btn); buttons_layout.addStretch(); buttons_layout.addWidget(default_btn)
        layout.addLayout(buttons_layout)
        self.load_instruments()

    def get_selected_id(self) -> int | None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows: return None
        try: return int(self.table.item(selected_rows[0].row(), 0).text())
        except (ValueError, AttributeError): return None

    def load_instruments(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        instruments_rows = services.get_all_instruments()
        for inst_row in instruments_rows:
            instrument = dict(inst_row); row = self.table.rowCount(); self.table.insertRow(row)
            id_item = QTableWidgetItem(str(instrument.get('id'))); id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, id_item); self.table.setItem(row, 1, QTableWidgetItem(instrument.get('instrument_name', ''))); self.table.setItem(row, 2, QTableWidgetItem(instrument.get('serial_number', ''))); self.table.setItem(row, 3, QTableWidgetItem(instrument.get('fw_version', ''))); self.table.setItem(row, 4, QTableWidgetItem(instrument.get('calibration_date', '')))
            if instrument.get('is_default'):
                for col in range(5): self.table.item(row, col).setBackground(QColor("#E0F7FA"))
        self.table.setSortingEnabled(True)

    def add_instrument(self):
        dialog = InstrumentDetailDialog(parent=self)
        if dialog.exec():
            try: services.add_instrument(**dialog.get_data()); self.load_instruments()
            except ValueError as e: QMessageBox.warning(self, "Dati non validi", str(e))

    def edit_instrument(self):
        inst_id = self.get_selected_id()
        if not inst_id: return
        all_instruments = services.get_all_instruments()
        inst_row = next((inst for inst in all_instruments if inst['id'] == inst_id), None)
        inst_data_dict = dict(inst_row) if inst_row else None
        dialog = InstrumentDetailDialog(inst_data_dict, self)
        if dialog.exec():
            try: services.update_instrument(inst_id, **dialog.get_data()); self.load_instruments()
            except ValueError as e: QMessageBox.warning(self, "Dati non validi", str(e))

    def delete_instrument(self):
        inst_id = self.get_selected_id()
        if not inst_id: return
        reply = QMessageBox.question(self, "Conferma Eliminazione", "Sei sicuro di voler eliminare lo strumento selezionato?")
        if reply == QMessageBox.Yes: services.delete_instrument(inst_id); self.load_instruments()
            
    def set_default(self):
        inst_id = self.get_selected_id()
        if not inst_id: return
        services.set_default_instrument(inst_id); self.load_instruments()