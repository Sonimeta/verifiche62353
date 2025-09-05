# app/services.py (Versione completa per la sincronizzazione)
import logging
import json
from datetime import datetime, timezone
import uuid

import serial

import database
from .data_models import AppliedPart
import report_generator
import tempfile
import os
import sys
import subprocess
from PySide6.QtCore import QTimer, QSettings
from app import auth_manager
from app import config



# ==============================================================================
# SERVIZI PER CLIENTI
# ==============================================================================

def add_destination(customer_id, name, address):
    if not name: raise ValueError("Il nome della destinazione non può essere vuoto.")
    timestamp = datetime.now(timezone.utc).isoformat()
    new_uuid = str(uuid.uuid4())
    database.add_destination(new_uuid, customer_id, name, address, timestamp)

def delete_destination(dest_id):
    """
    Wrapper di servizio per eliminare una destinazione, solo se non contiene dispositivi.
    """
    # Controlla se ci sono dispositivi associati a questa destinazione
    device_count = database.get_device_count_for_destination(dest_id)
    if device_count > 0:
        # Solleva un errore specifico che l'interfaccia può mostrare all'utente
        raise ValueError(f"Impossibile eliminare: la destinazione contiene {device_count} dispositivi. Spostarli o eliminarli prima.")
    
    # Se non ci sono dispositivi, procedi con l'eliminazione
    timestamp = datetime.now(timezone.utc).isoformat()
    database.delete_destination(dest_id, timestamp)

def update_destination(dest_id, name, address):
    """
    Wrapper di servizio per aggiornare i dati di una destinazione.
    """
    if not name:
        raise ValueError("Il nome della destinazione non può essere vuoto.")
    
    timestamp = datetime.now(timezone.utc).isoformat()
    database.update_destination(dest_id, name, address, timestamp)

def add_customer(name: str, address: str, phone: str, email: str):
    """Crea i dati di sync e aggiunge un cliente."""
    if not name:
        raise ValueError("Il nome del cliente non può essere vuoto.")
    new_uuid = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    database.add_customer(new_uuid, name, address, phone, email, timestamp)

def update_customer(cust_id: int, name: str, address: str, phone: str, email: str):
    """Crea il timestamp e aggiorna un cliente."""
    if not name:
        raise ValueError("Il nome del cliente non può essere vuoto.")
    timestamp = datetime.now(timezone.utc)
    database.update_customer(cust_id, name, address, phone, email, timestamp)

def delete_customer(cust_id: int) -> tuple[bool, str]:
    """Crea il timestamp ed esegue un soft delete."""
    timestamp = datetime.now(timezone.utc)
    return database.soft_delete_customer(cust_id, timestamp)

# --- Wrapper di lettura per coerenza architetturale ---
def get_all_customers(search_query=None):
    return database.get_all_customers(search_query)

def get_customer_by_id(customer_id):
    return database.get_customer_by_id(customer_id)

def get_device_count_for_customer(customer_id):
    return database.get_device_count_for_customer(customer_id)

# ==============================================================================
# SERVIZI PER DISPOSITIVI
# ==============================================================================

def normalize_serial(serial):
    if not serial:
        return None
    s = str(serial).strip().upper()
    return None if s in config.PLACEHOLDER_SERIALS or s == "" else s

def add_device(destination_id, serial, desc, mfg, model, department, applied_parts, customer_inv, ams_inv, verification_interval, default_profile_key):
    serial = normalize_serial(serial)
    if serial:
        if database.device_exists(serial):
            raise ValueError(f"Il numero di serie '{serial}' è già utilizzato da un altro dispositivo attivo.")
    
    # Cerca se esiste un dispositivo con questo seriale, inclusi quelli eliminati
    if serial:
        existing_device = database.find_device_by_serial(serial, include_deleted=True)
        if existing_device and existing_device['is_deleted']:
            logging.warning(f"Dispositivo S/N {serial} trovato come eliminato localmente. Riattivazione in corso.")
            update_device(
                dev_id=existing_device['id'], destination_id=destination_id, serial=serial, 
                desc=desc, mfg=mfg, model=model, department=department, 
                applied_parts=applied_parts, customer_inv=customer_inv, 
                ams_inv=ams_inv, default_profile_key=default_profile_key,
                verification_interval=verification_interval, reactivate=True
            )
            return

    timestamp = datetime.now(timezone.utc).isoformat()
    new_uuid = str(uuid.uuid4())
    database.add_device(
        new_uuid, destination_id, serial, desc, mfg, model, department,
        applied_parts, customer_inv, ams_inv, verification_interval,
        default_profile_key, timestamp
    )

def update_device(
    dev_id, destination_id, serial, desc, mfg, model, department,
    applied_parts, customer_inv, ams_inv, verification_interval, 
    default_profile_key, reactivate=False, new_destination_id=None
):
    norm_serial = normalize_serial(serial)
    if norm_serial:
        existing_device = database.find_device_by_serial(norm_serial, include_deleted=True)
        if existing_device and existing_device['id'] != dev_id and not existing_device['is_deleted']:
            raise ValueError(f"Il numero di serie '{norm_serial}' è già utilizzato da un altro dispositivo attivo.")
    
    ts = datetime.now(timezone.utc).isoformat()
    database.update_device(
        dev_id, destination_id, norm_serial, desc, mfg, model, department,
        applied_parts, customer_inv, ams_inv, verification_interval,
        default_profile_key, ts, reactivate, new_destination_id
    )

def decommission_device(dev_id: int):
    """Imposta lo stato di un dispositivo a 'dismesso'."""
    timestamp = datetime.now(timezone.utc).isoformat()
    database.set_device_status(dev_id, 'decommissioned', timestamp)
    logging.info(f"Dispositivo ID {dev_id} marcato come dismesso.")

def reactivate_device(dev_id: int):
    """Riporta lo stato di un dispositivo a 'attivo'."""
    timestamp = datetime.now(timezone.utc).isoformat()
    database.set_device_status(dev_id, 'active', timestamp)
    logging.info(f"Dispositivo ID {dev_id} riattivato.")

def move_device_to_destination(device_id: int, new_destination_id: int):
    """Servizio per spostare un dispositivo."""
    timestamp = datetime.now(timezone.utc).isoformat()
    database.move_device_to_destination(device_id, new_destination_id, timestamp)

def delete_device(dev_id: int):
    """Crea il timestamp ed esegue un soft delete del dispositivo."""
    timestamp = datetime.now(timezone.utc)
    database.soft_delete_device(dev_id, timestamp)

def delete_all_devices_for_customer(customer_id: int) -> bool:
    """Esegue un soft delete massivo dei dispositivi di un cliente."""
    timestamp = datetime.now(timezone.utc)
    return database.soft_delete_all_devices_for_customer(customer_id, timestamp)

def get_destination_devices_for_export(destination_id: int):
    """
    Prepara i dati dei dispositivi di una destinazione per l'esportazione in tabella.
    Se una verifica manca, imposta l'esito come 'Verifica non eseguita'.
    """
    devices_data = database.get_devices_with_last_verification_for_destination(destination_id)
    
    export_data = []
    for row in devices_data:
        row_dict = dict(row)
        if not row_dict.get("ESITO"):
            row_dict["ESITO"] = "VERIFICA NON ESEGUITA"
        export_data.append(row_dict)
        
    return export_data

# --- Wrapper di lettura ---
def get_devices_for_customer(customer_id, search_query=None):
    return database.get_devices_for_customer(customer_id, search_query)

def get_device_by_id(device_id):
    return database.get_device_by_id(device_id)
    
def search_device_globally(search_term):
    return database.search_device_globally(search_term)

def get_devices_needing_verification(days_in_future=30):
    """Wrapper di servizio per recuperare i dispositivi in scadenza."""
    return database.get_devices_needing_verification(days_in_future)

# ==============================================================================
# SERVIZI PER VERIFICHE E REPORT
# ==============================================================================

def finalizza_e_salva_verifica(device_id, profile_name, results,
                               visual_inspection_data, mti_info,
                               technician_name, technician_username) -> tuple[str, int]:
    overall_status = "PASSATO" if all(r.get('passed', False) for r in results) else "FALLITO"
    new_uuid = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)

    # Salva nel DB locale (save_verification genererà il codice se non passato)
    verification_code, new_id = database.save_verification(
        uuid=new_uuid,
        device_id=device_id,
        profile_name=profile_name,
        results=results,
        overall_status=overall_status,
        visual_inspection_data=visual_inspection_data,
        mti_info=mti_info,
        technician_name=technician_name,
        technician_username=technician_username,
        timestamp=timestamp.isoformat(),
        verification_code=None  # None => lo genera database.save_verification
    )

    logging.info(f"Verifica creata: id={new_id}, code={verification_code}")
    return verification_code, new_id

def delete_verification(verification_id: int):
    """Crea il timestamp ed esegue un soft delete della verifica."""
    timestamp = datetime.now(timezone.utc)
    return database.soft_delete_verification(verification_id, timestamp)

def generate_pdf_report(filename, verification_id, device_id, report_settings):
    """
    Prepara i dati e genera il report PDF, usando la nuova struttura a destinazioni.
    """
    logging.info(f"Servizio di generazione report per verifica ID {verification_id}")
    
    # 1. Recupera i dati del dispositivo
    device_info_row = database.get_device_by_id(device_id)
    if not device_info_row:
        raise ValueError(f"Dispositivo con ID {device_id} non trovato.")
    device_info = dict(device_info_row)
    
    # 2. Dalle info del dispositivo, trova la destinazione
    destination_id = device_info.get('destination_id')
    if not destination_id:
        raise ValueError(f"Il dispositivo ID {device_id} non è associato a nessuna destinazione.")
    
    destination_info_row = database.get_destination_by_id(destination_id)
    if not destination_info_row:
        raise ValueError(f"Destinazione ID {destination_id} non trovata.")
    destination_info = dict(destination_info_row)
    
    # 3. Dalle info della destinazione, trova il cliente
    customer_id = destination_info.get('customer_id')
    customer_info_row = database.get_customer_by_id(customer_id)
    if not customer_info_row:
        raise ValueError(f"Cliente ID {customer_id} non trovato.")
    customer_info = dict(customer_info_row)

    # 4. Recupera i dati specifici della verifica
    verifications = database.get_verifications_for_device(device_id)
    verification = next((v for v in verifications if v.get('id') == verification_id), None)
    
    if not verification:
        raise ValueError(f"Dati di verifica mancanti per la verifica ID {verification_id}")

    # 5. Prepara le informazioni rimanenti per il report
    technician_name = verification['technician_name'] or "N/D"
    technician_username = verification.get('technician_username')
    
    print(f"--- DEBUG (Generazione Report): Username recuperato dalla verifica: '{technician_username}'")
    signature_data = database.get_signature_by_username(technician_username)
    print(f"--- DEBUG (Generazione Report): Dati firma trovati nel DB locale? {'Sì, ' + str(len(signature_data)) + ' bytes' if signature_data else 'No'}")
    # --- FINE BLOCCO DI DEBUG ---
    
    mti_info = {
        "instrument": verification.get('mti_instrument', ''),
        "serial": verification.get('mti_serial', ''),
        "version": verification.get('mti_version', ''),
        "cal_date": verification.get('mti_cal_date', '')
    }
    
    # --> INSERISCI QUESTE RIGHE DI DEBUG QUI <--
    print("--- DEBUG REPORT ---")
    print(f"Dati letti dal DB (verification): {verification}")
    print(f"Dati preparati per il report (mti_info): {mti_info}")
    print("--------------------")
    
    results_data = verification.get('results') or []
    visual_data = verification.get('visual_inspection') or {}
    
    verification_data_for_report = {
        'date': verification['verification_date'], 'profile_name': verification['profile_name'],
        'overall_status': verification['overall_status'], 'results': results_data,
        'visual_inspection_data': visual_data, 'verification_code': verification.get('verification_code', 'N/A')
    }
    
    report_generator.create_report(
        filename, 
        device_info, 
        customer_info, 
        destination_info,
        mti_info, 
        report_settings, 
        verification_data_for_report, 
        technician_name,
        signature_data
    )

def print_pdf_report(verification_id, device_id, report_settings):
    """
    Genera un report PDF in un file temporaneo e lo invia alla stampante predefinita.
    """
    temp_fd, temp_filename = tempfile.mkstemp(suffix=".pdf")
    os.close(temp_fd) # C

    try:
        
        generate_pdf_report(temp_filename, verification_id, device_id, report_settings)
        os.startfile(temp_filename, "print")
        
        logging.info(f"Report per verifica ID {verification_id} inviato alla stampante.")
    except FileNotFoundError:
        raise Exception("Nessun programma predefinito per i PDF trovato per la stampa.")
    except Exception as e:
        raise e

def get_data_for_daily_export(target_date: str) -> dict:
    """Wrapper di servizio per l'esportazione giornaliera."""
    return database.get_full_verification_data_for_date(target_date)

def get_verifications_for_customer_by_month(customer_id: int, year: int, month: int) -> list:
    """Wrapper di servizio per ottenere le verifiche di un cliente per mese."""
    return database.get_verifications_for_customer_by_month(customer_id, year, month)

def get_verifications_for_device(device_id: int):
    """Wrapper di servizio per ottenere le verifiche di un dispositivo."""
    return database.get_verifications_for_device(device_id)

# ==============================================================================
# SERVIZI PER IMPORT / EXPORT
# ==============================================================================

def process_device_import_row(row_data: dict, mapping: dict, destination_id: int):
    """
    Logica di business per importare una singola riga da un file
    all'interno di una specifica destinazione.
    """
    serial_number = row_data.get(mapping.get('matricola'))
    
    description = row_data.get(mapping.get('descrizione'))
    if not description:
        raise ValueError("Descrizione mancante.")
    profile_key = (row_data.get(mapping.get('profilo')) or "IEC 62353 Metodo Diretto - Classe 1") if mapping.get('profilo') else None
    add_device(
        destination_id=destination_id,
        serial=serial_number,
        desc=description,
        mfg=row_data.get(mapping.get('costruttore'), ''),
        model=row_data.get(mapping.get('modello'), ''),
        department=row_data.get(mapping.get('reparto'), ''),
        customer_inv=row_data.get(mapping.get('inv_cliente'), ''),
        ams_inv=row_data.get(mapping.get('inv_ams'), ''),
        verification_interval=row_data.get(mapping.get('verification_interval'), None),
        applied_parts=[],
        default_profile_key=profile_key
    )

def get_data_for_daily_export(target_date: str) -> dict:
    """Prepara i dati per l'esportazione giornaliera in formato .stm."""
    return database.get_full_verification_data_for_date(target_date)


# ==============================================================================
# SERVIZI PER STRUMENTI E IMPOSTAZIONI
# ==============================================================================

def get_all_instruments():
    return database.get_all_instruments()

def add_instrument(instrument_name, serial_number, fw_version, calibration_date):
    if not instrument_name or not serial_number:
        raise ValueError("Nome e Seriale dello strumento sono obbligatori.")
    new_uuid = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc)
    database.add_instrument(new_uuid, instrument_name, serial_number, fw_version, calibration_date, com_port=None, timestamp=timestamp)

def update_instrument(inst_id, instrument_name, serial_number, fw_version, calibration_date, timestamp=None):
    if not instrument_name or not serial_number:
        raise ValueError("Nome e Seriale dello strumento sono obbligatori.")
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    database.update_instrument(inst_id, instrument_name, serial_number, fw_version, calibration_date, com_port=None, timestamp=timestamp)

def delete_instrument(inst_id: int):
    timestamp = datetime.now(timezone.utc)
    database.soft_delete_instrument(inst_id, timestamp)

def set_default_instrument(inst_id: int):
    timestamp = datetime.now(timezone.utc)
    database.set_default_instrument(inst_id, timestamp)

def get_stats():
    return database.get_stats()

def resolve_conflict_keep_local(table_name: str, uuid: str):
    """
    Forza la versione locale ad essere più recente per vincere il prossimo sync.
    """
    logging.warning(f"Risoluzione conflitto per {table_name} UUID {uuid}: forzatura versione locale.")
    timestamp = datetime.now(timezone.utc)
    database.force_update_timestamp(table_name, uuid, timestamp)

def resolve_conflict_use_server(table_name: str, server_version: dict):
    """
    Sovrascrive il record locale con la versione fornita dal server.
    """
    uuid = server_version.get('uuid')
    logging.warning(f"Risoluzione conflitto per {table_name} UUID {uuid}: accettazione versione server.")
    database.overwrite_local_record(table_name, server_version)

def force_full_push():
    import database
    with database.DatabaseConnection() as conn:
        return database.mark_everything_for_full_push(conn)
    
# ==============================================================================
# SERVIZI PER PROFILI DI VERIFICA
# ==============================================================================

def add_profile_with_tests(profile_key, profile_name, tests_list):
    """Wrapper di servizio per aggiungere un nuovo profilo."""
    timestamp = datetime.now(timezone.utc).isoformat()
    return database.add_profile_with_tests(profile_key, profile_name, tests_list, timestamp)

def update_profile_with_tests(profile_id, profile_name, tests_list):
    """Wrapper di servizio per aggiornare un profilo."""
    timestamp = datetime.now(timezone.utc).isoformat()
    database.update_profile_with_tests(profile_id, profile_name, tests_list, timestamp)

def delete_profile(profile_id):
    """Wrapper di servizio per eliminare un profilo."""
    timestamp = datetime.now(timezone.utc).isoformat()
    database.delete_profile(profile_id, timestamp)