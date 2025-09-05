# app/workers/stm_import_worker.py
import json
import logging
from PySide6.QtCore import QObject, Signal
import database

class StmImportWorker(QObject):
    """Esegue l'importazione di un file archivio .stm in background."""
    finished = Signal(int, int, int, int) # verif_imp, verif_skip, dev_new, cust_new
    error = Signal(str)

    def __init__(self, filepath):
        super().__init__()
        self.filepath = filepath

    def run(self):
        logging.info(f"Avvio importazione dall'archivio: {self.filepath}")
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.error.emit(f"Impossibile leggere o parsare il file .stm: {e}")
            return

        verif_imported = 0
        verif_skipped = 0
        devices_created = 0
        customers_created = 0
        
        # Itera su ogni pacchetto di verifica presente nel file
        for verification_package in data.get("verifications", []):
            try:
                # --- 1. Gestione Cliente ---
                customer_data = verification_package['customer']
                customer_id = database.add_or_get_customer(customer_data['name'], customer_data['address'])
                
                # --- 2. Gestione Dispositivo ---
                device_data = verification_package['device']
                device_serial = device_data['serial_number']
                
                existing_device = database.get_device_by_serial(device_serial)
                if existing_device:
                    device_id = existing_device['id']
                else:
                    # Crea il nuovo dispositivo se non esiste
                    database.add_device(
                        customer_id, device_serial, device_data['description'], device_data['manufacturer'],
                        device_data['model'], json.loads(device_data['applied_parts_json']), 
                        device_data['customer_inventory'], device_data['ams_inventory']
                    )
                    new_device = database.get_device_by_serial(device_serial)
                    device_id = new_device['id']
                    devices_created += 1
                    logging.info(f"Nuovo dispositivo creato: {device_serial}")
                
                # --- 3. Gestione Verifica ---
                verif_details = verification_package['verification_details']
                verif_date = verif_details['verification_date']
                verif_profile = verif_details['profile_name']

                if database.verification_exists(device_id, verif_date, verif_profile):
                    verif_skipped += 1
                    logging.warning(f"Verifica del {verif_date} per S/N {device_serial} già esistente. Saltata.")
                else:
                    # Salva la nuova verifica
                    database.save_verification(
                        device_id=device_id,
                        verification_date=verif_date,
                        profile_name=verif_profile,
                        results=json.loads(verif_details['results_json']),
                        overall_status=verif_details['overall_status'],
                        visual_inspection_data=json.loads(verif_details['visual_inspection_json']),
                        mti_info=verif_details['mti_info']
                    )
                    verif_imported += 1
            
            except Exception as e:
                logging.error(f"Errore durante l'importazione di un record di verifica.", exc_info=True)
                verif_skipped += 1 # Salta il record problematico

        self.finished.emit(verif_imported, verif_skipped, devices_created, customers_created)