# app/sync_manager.py (Versione Definitiva e Completa)
import requests
import json
import logging
from datetime import datetime, timezone, date
import database
import sqlite3
import base64

from app import auth_manager, config

SYNC_ORDER = ["customers", "mti_instruments", "signatures", "profiles", "profile_tests", "destinations", "devices", "verifications"]

def _jsonify_value(v):
    # datetime/date → ISO 8601
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    # bytes/bytearray/memoryview → base64 string
    if isinstance(v, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(v)).decode("ascii")
    return v

def _jsonify_record(rec: dict) -> dict:
    return {k: _jsonify_value(v) for k, v in rec.items()}

def _get_unsynced_local_changes():
    """Recupera tutte le modifiche locali non sincronizzate in modo più compatto."""
    
    # Definiamo le query e le trasformazioni per ogni tabella in una struttura dati
    TABLE_SYNC_CONFIG = {
        "customers": ("SELECT * FROM {table} WHERE is_synced = 0", []),
        "mti_instruments": ("SELECT * FROM {table} WHERE is_synced = 0", []),
        "signatures": ("SELECT * FROM {table} WHERE is_synced = 0", []),
        "profiles": ("SELECT * FROM {table} WHERE is_synced = 0", []),
        "destinations": (
            "SELECT d.*, c.uuid as customer_uuid FROM destinations d JOIN customers c ON d.customer_id = c.id WHERE d.is_synced = 0",
            ["customer_id"] # Colonne da rimuovere prima dell'invio
        ),
        "devices": (
            "SELECT d.*, dest.uuid as destination_uuid FROM devices d JOIN destinations dest ON d.destination_id = dest.id WHERE d.is_synced = 0",
            ["destination_id"]
        ),
        "verifications": (
            "SELECT v.*, d.uuid as device_uuid FROM verifications v JOIN devices d ON v.device_id = d.id WHERE v.is_synced = 0",
            ["device_id"]
        ),
        "profile_tests": (
            "SELECT pt.*, p.uuid as profile_uuid FROM profile_tests pt JOIN profiles p ON pt.profile_id = p.id WHERE pt.is_synced = 0",
            ["profile_id"]
        )
    }

    changes = {}
    with database.DatabaseConnection() as conn:
        conn.row_factory = sqlite3.Row
        
        for table, (query, cols_to_pop) in TABLE_SYNC_CONFIG.items():
            # Il nome della tabella viene inserito nella query se necessario
            final_query = query.format(table=table)
            
            rows = conn.execute(final_query).fetchall()
            records_list = []
            for row in rows:
                record_dict = dict(row)
                record_dict.pop('id', None) # Rimuoviamo sempre l'ID locale

                # Rimuoviamo le chiavi esterne (FK) numeriche
                for col in cols_to_pop:
                    record_dict.pop(col, None)
                
                records_list.append(record_dict)
            
            changes[table] = records_list
            
    return changes

def _apply_server_changes(conn, changes):
    applied_counts = {table: 0 for table in SYNC_ORDER}
    uuid_to_local_id = {"customers": {}, "devices": {}, "profiles": {}, "destinations": {}}
    cursor = conn.cursor()

    for table in SYNC_ORDER:
        records_from_server = changes.get(table, [])
        if not records_from_server:
            continue

        if table == 'signatures':
            records_to_upsert = []
            for record in records_from_server:
                # decode base64 -> bytes (già lo fai)
                if record.get('signature_data'):
                    try:
                        record['signature_data'] = base64.b64decode(record['signature_data'])
                    except (TypeError, base64.binascii.Error):
                        record['signature_data'] = None

                record['is_synced'] = 1

                # ⬇️ Keep only the columns that really exist in SQLite
                clean = {
                    'username': record.get('username'),
                    'signature_data': record.get('signature_data'),
                    'last_modified': record.get('last_modified'),
                    'is_synced': record.get('is_synced', 1),
                }
                records_to_upsert.append(clean)

            if records_to_upsert:
                cols = ['username', 'signature_data', 'last_modified', 'is_synced']
                placeholders = ", ".join(["?"] * len(cols))
                query = (
                    f"INSERT INTO signatures ({', '.join(cols)}) VALUES ({placeholders}) "
                    "ON CONFLICT(username) DO UPDATE SET "
                    "signature_data=excluded.signature_data, "
                    "last_modified=excluded.last_modified, "
                    "is_synced=excluded.is_synced;"
                )
                params = [tuple(r[c] for c in cols) for r in records_to_upsert]
                cursor.executemany(query, params)
                applied_counts[table] += cursor.rowcount
            continue  # importante: salta il flusso generico

        records_to_insert = []
        records_to_update = []

        for record in records_from_server:
            if 'customer_id' in record and table == 'devices':
                record.pop('customer_id')

            def resolve_fk(parent_table_name, parent_uuid_key):
                parent_uuid = record.pop(parent_uuid_key, None)
                if not parent_uuid: return None
                local_id = uuid_to_local_id.get(parent_table_name, {}).get(parent_uuid)
                if local_id: return local_id
                parent_row = cursor.execute(f"SELECT id FROM {parent_table_name} WHERE uuid = ?", (parent_uuid,)).fetchone()
                if parent_row:
                    return parent_row[0]
                logging.warning(f"Salto record in '{table}' perché il genitore {parent_uuid} in '{parent_table_name}' non è stato trovato.")
                return None

            if table == 'destinations':
                local_customer_id = resolve_fk("customers", "customer_uuid")
                if local_customer_id is None: continue
                record['customer_id'] = local_customer_id
            
            if table == 'devices':
                local_destination_id = resolve_fk("destinations", "destination_uuid")
                if local_destination_id is None: continue
                record['destination_id'] = local_destination_id
            
            if table == 'verifications':
                local_device_id = resolve_fk("devices", "device_uuid")
                if local_device_id is None: continue
                record['device_id'] = local_device_id

            if table == 'profile_tests':
                local_profile_id = resolve_fk("profiles", "profile_uuid")
                if local_profile_id is None: continue
                record['profile_id'] = local_profile_id
            
            record_uuid = record.get('uuid')
            if not record_uuid: continue

            existing = cursor.execute(f"SELECT id FROM {table} WHERE uuid = ?", (record_uuid,)).fetchone()
            
            if existing:
                records_to_update.append(record)
            elif not record.get('is_deleted', False):
                record.pop('id', None)
                records_to_insert.append(record)
        
        if records_to_insert:
            cols = list(records_to_insert[0].keys())
            query = f"INSERT INTO {table} ({', '.join(cols)}, is_synced) VALUES ({', '.join(['?']*len(cols))}, 1)"
            params = [tuple(r.get(c) for c in cols) for r in records_to_insert]
            cursor.executemany(query, params)
            applied_counts[table] += cursor.rowcount
            
            if table in uuid_to_local_id:
                for record in records_to_insert:
                    new_id_row = cursor.execute(f"SELECT id FROM {table} WHERE uuid = ?", (record['uuid'],)).fetchone()
                    if new_id_row:
                        uuid_to_local_id[table][record['uuid']] = new_id_row[0]

        if records_to_update:
            cols = [k for k in records_to_update[0].keys() if k not in ['uuid', 'id']]
            set_clause = ", ".join([f"{col} = ?" for col in cols])
            query = f"UPDATE {table} SET {set_clause}, is_synced = 1 WHERE uuid = ?"
            params = [tuple(r.get(c) for c in cols) + (r['uuid'],) for r in records_to_update]
            cursor.executemany(query, params)
            applied_counts[table] += cursor.rowcount

    logging.info(f"Modifiche batch dal server applicate: {json.dumps(applied_counts)}")
    return applied_counts

def _mark_pushed_changes_as_synced(conn):
    cursor = conn.cursor()
    for table in SYNC_ORDER:
        cursor.execute(f"UPDATE {table} SET is_synced = 1 WHERE is_synced = 0")
    logging.info("Tutti i record locali inviati sono stati marcati come sincronizzati.")

def _handle_uuid_maps(conn, uuid_map: dict):
    if not uuid_map: return
    logging.warning(f"Ricevuta mappa di unione UUID dal server: {uuid_map}")
    cursor = conn.cursor()
    for client_uuid, server_uuid in uuid_map.items():
        try:
            cursor.execute("SELECT id FROM customers WHERE uuid = ?", (server_uuid,))
            correct_customer_row = cursor.fetchone()
            cursor.execute("SELECT id FROM customers WHERE uuid = ?", (client_uuid,))
            duplicate_customer_row = cursor.fetchone()
            if not correct_customer_row or not duplicate_customer_row: continue
            correct_customer_id = correct_customer_row[0]
            duplicate_customer_id = duplicate_customer_row[0]
            cursor.execute("UPDATE destinations SET customer_id = ? WHERE customer_id = ?", (correct_customer_id, duplicate_customer_id))
            logging.info(f"Riassegnate {cursor.rowcount} destinazioni dal cliente duplicato a quello corretto.")
            cursor.execute("DELETE FROM customers WHERE id = ?", (duplicate_customer_id,))
            logging.warning(f"Cliente duplicato con UUID {client_uuid} eliminato.")
        except Exception as e:
            logging.error(f"Errore durante la gestione della mappa UUID {client_uuid} -> {server_uuid}", exc_info=True)
            continue

def run_sync(full_sync=False):
    if full_sync:
        try:
            database.wipe_all_syncable_data()
            auth_manager.update_session_timestamp(None)
        except Exception as e:
            return "error", "Impossibile resettare il database locale. Operazione annullata."
    
    logging.info(f"Avvio processo di sincronizzazione (Full Sync: {full_sync})...")
    last_sync = auth_manager.get_current_user_info().get('last_sync_timestamp')
    local_changes = _get_unsynced_local_changes()
    for table, rows in list(local_changes.items()):
        if not rows:
            continue
    # assicurati che ogni row sia un dict (se è sqlite3.Row convertila prima)
        norm_rows = []
        for r in rows:
            rd = dict(r) if not isinstance(r, dict) else r
            norm_rows.append(_jsonify_record(rd))
        local_changes[table] = norm_rows
    payload = {"last_sync_timestamp": last_sync, "changes": local_changes}

    try:
        headers = auth_manager.get_auth_headers()
        sync_url = f"{config.SERVER_URL}/sync"
        response = requests.post(sync_url, json=payload, timeout=60, headers=headers)
        response.raise_for_status()
        server_response = response.json()
        
        status = server_response.get("status")
        if status == "conflict":
            return "conflict", server_response.get("conflicts")
        if status != "success":
            raise Exception(f"Il server ha risposto con un errore: {server_response.get('message')}")
        
        with database.DatabaseConnection() as conn:
            uuid_map = server_response.get("uuid_map", {})
            if uuid_map: _handle_uuid_maps(conn, uuid_map)
            changes_from_server = server_response.get("changes", {})
            applied_counts = _apply_server_changes(conn, changes_from_server)
            _mark_pushed_changes_as_synced(conn)
        
        auth_manager.update_session_timestamp(server_response.get("new_sync_timestamp"))
        summary = [f"{count} {table}" for table, count in applied_counts.items() if count > 0]
        if not summary:
            return "success", "Sincronizzazione completata. Nessuna nuova modifica ricevuta."
        return "success", "Sincronizzazione completata. Dati aggiornati:\n- " + "\n- ".join(summary)
    
    except requests.RequestException as e:
        if e.response and e.response.status_code == 401:
             return "error", "Errore di autenticazione (401). La sessione potrebbe essere scaduta. Prova a riavviare."
        return "error", str(f"Impossibile connettersi al server.\nControllare la connessione e l'indirizzo nel file config.ini.")
    except Exception as e:
        logging.error(f"Sincronizzazione fallita. Errore: {e}", exc_info=True)
        return "error", str(e)