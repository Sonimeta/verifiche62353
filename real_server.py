# real_server.py

from fastapi import FastAPI, HTTPException, Depends, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2 import errors
from psycopg2.extras import RealDictCursor
from datetime import datetime, timezone, date, timedelta
import logging
import base64
import os
import json
from dotenv import load_dotenv
# Sicurezza
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from jose import JWTError, jwt
load_dotenv()
# --- CONFIGURAZIONE DI SICUREZZA ---
SECRET_KEY = os.getenv("SECRET_KEY") # IN PRODUZIONE, QUESTA CHIAVE DOVREBBE ESSERE GESTITA IN MODO SICURO
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 30)) # 30 giorni

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
ph = PasswordHasher()

# --- CONFIGURAZIONE GENERALE ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_PARAMS = {
    "dbname": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT")
}
TABLES_TO_SYNC = ["customers", "mti_instruments", "signatures", "profiles", "profile_tests", "destinations", "devices", "verifications"]

# --- AVVIO APPLICAZIONE API ---
app = FastAPI(title="Safety Test Sync API")

# --- UTILITY DI SICUREZZA ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una password usando Argon2 in modo robusto."""
    try:
        # Il metodo corretto è ph.verify()
        ph.verify(hashed_password, plain_password)
        return True
    except (VerifyMismatchError, InvalidHash):
        # Se la password non corrisponde o l'hash non è valido, l'eccezione viene
        # catturata e la funzione restituisce False, come previsto.
        return False
    except Exception as e:
        logging.error(f"Errore imprevisto durante la verifica della password: {e}")
        return False

def get_password_hash(password: str) -> str:
    return ph.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

BOOL_FIELDS_BY_TABLE = {
    "customers": ["is_deleted", "is_synced"],
    "profiles": ["is_deleted", "is_synced"],
    "destinations": ["is_deleted", "is_synced"],
    "devices": ["is_deleted", "is_synced"],
    "profile_tests": ["is_deleted", "is_synced", "is_applied_part_test"],
    "verifications": ["is_deleted", "is_synced"],
    "mti_instruments": ["is_deleted", "is_synced", "is_default"],
    "signatures": ["is_synced"],
}

def _to_bool(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "t", "yes", "y"): return True
        if s in ("0", "false", "f", "no", "n", ""): return False
    return bool(v)

def _normalize_booleans(table_name: str, rec: dict) -> None:
    for f in BOOL_FIELDS_BY_TABLE.get(table_name, []):
        if f in rec:
            rec[f] = _to_bool(rec[f])

def _normalize_incoming_value(table_name: str, key: str, value):
    from datetime import datetime, date
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if table_name == "signatures" and key == "signature_data" and isinstance(value, str):
        try:
            return base64.b64decode(value)
        except Exception:
            logging.warning("signature_data non è base64 valido; imposto NULL.")
            return None
    return value

def get_valid_columns(cursor, table_name: str) -> set:
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s
    """, (table_name,))
    rows = cursor.fetchall()
    return { (row["column_name"] if isinstance(row, dict) else row[0]) for row in rows }

# --- MODELLI DATI (Pydantic) ---
class User(BaseModel):
    username: str
    role: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserCreate(User):
    password: str

class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class SyncRecord(BaseModel):
    uuid: str
    last_modified: datetime
    is_deleted: Optional[bool] = False # Optional per tabelle come 'signatures'
    is_synced: bool
    class Config:
        extra = 'allow'

class InstrumentRecord(SyncRecord):
    is_default: bool

class SyncChanges(BaseModel):
    customers: List[SyncRecord]
    devices: List[SyncRecord]
    verifications: List[SyncRecord]
    mti_instruments: List[InstrumentRecord]
    signatures: List[SyncRecord]
    profiles: List[SyncRecord]
    profile_tests: List[SyncRecord]
    destinations: List[SyncRecord]

class SyncPayload(BaseModel):
    last_sync_timestamp: Optional[str]
    changes: SyncChanges

# --- DEPENDENCY PER LA SICUREZZA ---
def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        role: Optional[str] = payload.get("role")
        if username is None or role is None:
            raise credentials_exception
        return User(
            username=username, 
            role=role, 
            first_name=payload.get("first_name"), 
            last_name=payload.get("last_name")
        )
    except JWTError:
        raise credentials_exception
    return {"username": username, "role": role, "full_name": payload.get("full_name")}

# --- FUNZIONI DATABASE SERVER ---
def get_db_connection():
    return psycopg2.connect(**DB_PARAMS)

# In real_server.py

def process_client_changes(conn_or_cursor, table_name: str, records: list[dict], user_role: str):
    """
    Mappa UUID→ID per FK, normalizza valori (date/base64/booleans),
    filtra le colonne inesistenti e fa UPSERT.
    """
    try:
        # se è una connessione, ha .cursor(...)
        cursor = conn_or_cursor.cursor(cursor_factory=RealDictCursor)
        conn = conn_or_cursor
    except AttributeError:
        # altrimenti è già un cursore
        cursor = conn_or_cursor
        conn = cursor.connection
    conflicts = []
    uuid_map = {}

    if not records:
        return conflicts, 0, uuid_map

    valid_cols = get_valid_columns(cursor, table_name)
    cleaned_records = []

    for rec in records:
        r = dict(rec)

        # --- FK per UUID ricevuti ---
        if table_name == "destinations":
            cust_uuid = r.pop("customer_uuid", None)
            if cust_uuid:
                cursor.execute("SELECT id FROM customers WHERE uuid=%s AND is_deleted=FALSE", (cust_uuid,))
                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Salto destination: customer {cust_uuid} assente sul server.")
                    continue
                r["customer_id"] = row["id"]

        elif table_name == "devices":
            dest_uuid = r.pop("destination_uuid", None)
            if dest_uuid:
                cursor.execute("SELECT id FROM destinations WHERE uuid=%s AND is_deleted=FALSE", (dest_uuid,))
                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Salto device: destination {dest_uuid} assente sul server.")
                    continue
                r["destination_id"] = row["id"]
            # normalizza seriali placeholder → NULL
            s = (r.get("serial_number") or "").strip()
            if s == "" or s.upper() in {"N.P.", "NP", "N/A", "NA", "NON PRESENTE", "-"}:
                r["serial_number"] = None

        elif table_name == "profile_tests":
            prof_uuid = r.pop("profile_uuid", None)
            if prof_uuid:
                cursor.execute("SELECT id FROM profiles WHERE uuid=%s AND is_deleted=FALSE", (prof_uuid,))
                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Salto profile_test: profile {prof_uuid} assente sul server.")
                    continue
                r["profile_id"] = row["id"]

        elif table_name == "verifications":
            dev_uuid = r.pop("device_uuid", None)
            if dev_uuid:
                cursor.execute("SELECT id FROM devices WHERE uuid=%s AND is_deleted=FALSE", (dev_uuid,))
                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Salto verification: device {dev_uuid} assente sul server.")
                    continue
                r["device_id"] = row["id"]

        # --- normalizza valori (date/base64) ---
        for k, v in list(r.items()):
            r[k] = _normalize_incoming_value(table_name, k, v)

        # --- filtra colonne non presenti nella tabella ---
        r_clean = {k: v for k, v in r.items() if k in valid_cols}
        if not r_clean:
            continue
        cleaned_records.append(r_clean)

    if not cleaned_records:
        return conflicts, 0, uuid_map

    upserted = upsert_records(conn, cursor, table_name, cleaned_records)
    return conflicts, upserted, uuid_map

def upsert_records(conn, cursor, table_name: str, cleaned_records: list[dict]) -> int:
    """
    UPSERT generico su chiave (uuid) o (username) per signatures.
    Converte automaticamente i campi booleani 0/1 → True/False.
    """
    if not cleaned_records:
        return 0

    # booleani normalizzati
    for rec in cleaned_records:
        _normalize_booleans(table_name, rec)

    cols = list(cleaned_records[0].keys())
    columns = ", ".join(cols)
    placeholders = ", ".join([f"%({c})s" for c in cols])

    conflict_key = "username" if table_name == "signatures" else "uuid"
    update_cols = [f"{c}=EXCLUDED.{c}" for c in cols if c != conflict_key]
    update_clause = ", ".join(update_cols) if update_cols else ""

    if update_clause:
        query = f"""
            INSERT INTO {table_name} ({columns})
            VALUES ({placeholders})
            ON CONFLICT ({conflict_key}) DO UPDATE SET {update_clause}
        """
    else:
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"""

    try:
        cursor.executemany(query, cleaned_records)
        conn.commit()
        return len(cleaned_records)
    except Exception:
        conn.rollback()
        logging.error(f"Errore durante UPSERT nella tabella {table_name}", exc_info=True)
        raise

# --- ENDPOINT DI AUTENTICAZIONE ---
@app.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM users WHERE username = %s", (form_data.username,))
    user = cursor.fetchone()
    conn.close()
    if not user or not verify_password(form_data.password, user['hashed_password']):
        raise HTTPException(status_code=401, detail="Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    
    first_name = user.get('first_name') or ''
    last_name = user.get('last_name') or ''
    full_name = f"{first_name} {last_name}".strip()
    if not full_name: full_name = user['username']
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user['username'], "role": user['role'], "full_name": full_name}, expires_delta=access_token_expires)
    return {"access_token": access_token, "token_type": "bearer"}

# --- ENDPOINT PROTETTI ---
@app.post("/sync")
def handle_sync(payload: SyncPayload, current_user: User = Depends(get_current_user)):
    logging.info(f"Sync richiesto dall'utente: {current_user.username}")

    all_conflicts = []
    changes_to_send = {}
    final_uuid_map = {}  # non più usato, ma lasciamo il campo nella risposta per retro-compat
    new_sync_timestamp = datetime.now(timezone.utc)

    try:
        conn = get_db_connection()
        with conn:  # gestisce automaticamente COMMIT/ROLLBACK
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                logging.info("Fase PUSH: Ricezione dati con rilevamento conflitti...")

                changes_dict = payload.changes.model_dump()

                # IMPORTANTE: l’ordine evita FK mancanti (customers -> destinations -> devices -> verifications)
                # Se TABLES_TO_SYNC è già in questo ordine, usa quello. Altrimenti usa questa lista:
                tables_order = ["customers", "mti_instruments", "profiles", "profile_tests",
                                "destinations", "devices", "verifications", "signatures"]

                for table in tables_order:
                    records = changes_dict.get(table, [])
                    if not records:
                        continue
                    logging.info(f"Processando {len(records)} record per la tabella '{table}'...")
                    # process_client_changes deve ACCETTARE un CURSOR e ACCODARE i conflitti in all_conflicts
                    table_conflicts, _, table_uuid_map = process_client_changes(conn, table, records, current_user.role)
                    if table_conflicts:
                        all_conflicts.extend(table_conflicts)
                    if table_uuid_map:
                        final_uuid_map.update(table_uuid_map)

                if all_conflicts:
                    # Il with conn farà rollback uscendo dal blocco
                    logging.warning(f"Rilevati {len(all_conflicts)} conflitti. PUSH annullato.")
                    return {"status": "conflict", "conflicts": all_conflicts}

                logging.info("Fase PUSH completata con successo.")
                logging.info("Fase PULL: Invio aggiornamenti al client...")

                # ------- PULL -------
                simple_tables = ["customers", "mti_instruments", "profiles", "profile_tests", "destinations"]

                # Firma lato client: se è None è prima sync
                is_first_sync = payload.last_sync_timestamp is None

                # Firma: sempre inviate per semplicità
                cursor.execute("SELECT * FROM signatures")
                changes_to_send["signatures"] = cursor.fetchall()

                if is_first_sync:
                    logging.info("Prima sincronizzazione per questo client: invio di tutti i dati.")

                    for table in simple_tables:
                        if table == 'destinations':
                            cursor.execute("""
                                SELECT d.*, c.uuid AS customer_uuid
                                FROM destinations d
                                LEFT JOIN customers c ON d.customer_id = c.id
                                WHERE d.is_deleted = FALSE
                            """)
                            changes_to_send[table] = cursor.fetchall()
                        elif table == 'profile_tests':
                            cursor.execute("""
                                SELECT pt.*, p.uuid AS profile_uuid
                                FROM profile_tests pt
                                LEFT JOIN profiles p ON pt.profile_id = p.id
                                WHERE pt.is_deleted = FALSE
                            """)
                            changes_to_send[table] = cursor.fetchall()
                        else:
                            cursor.execute(f"SELECT * FROM {table} WHERE is_deleted = FALSE")
                            changes_to_send[table] = cursor.fetchall()

                    cursor.execute("""
                        SELECT d.*, dest.uuid as destination_uuid
                        FROM devices d
                        LEFT JOIN destinations dest ON d.destination_id = dest.id
                        WHERE d.is_deleted = FALSE
                    """)
                    changes_to_send["devices"] = cursor.fetchall()

                    cursor.execute("""
                        SELECT v.*, d.uuid as device_uuid
                        FROM verifications v
                        LEFT JOIN devices d ON v.device_id = d.id
                        WHERE v.is_deleted = FALSE
                    """)
                    changes_to_send["verifications"] = cursor.fetchall()

                else:
                    last_sync_ts = payload.last_sync_timestamp
                    if last_sync_ts is None:
                        raise HTTPException(status_code=400, detail="last_sync_timestamp must not be None for incremental sync.")
                    last_sync_dt = datetime.fromisoformat(last_sync_ts)

                    for table in simple_tables:
                        if table == 'destinations':
                            cursor.execute("""
                                SELECT d.*, c.uuid AS customer_uuid
                                FROM destinations d
                                LEFT JOIN customers c ON d.customer_id = c.id
                                WHERE d.last_modified > %s AND d.last_modified <= %s
                            """, (last_sync_dt, new_sync_timestamp))
                            changes_to_send[table] = cursor.fetchall()
                        elif table == 'profile_tests':
                            cursor.execute("""
                                SELECT pt.*, p.uuid AS profile_uuid
                                FROM profile_tests pt
                                LEFT JOIN profiles p ON pt.profile_id = p.id
                                WHERE pt.last_modified > %s AND pt.last_modified <= %s
                            """, (last_sync_dt, new_sync_timestamp))
                            changes_to_send[table] = cursor.fetchall()
                        else:
                            cursor.execute(
                                f"SELECT * FROM {table} WHERE last_modified > %s AND last_modified <= %s",
                                (last_sync_dt, new_sync_timestamp)
                            )
                            changes_to_send[table] = cursor.fetchall()

                    cursor.execute("""
                        SELECT d.*, dest.uuid as destination_uuid
                        FROM devices d
                        LEFT JOIN destinations dest ON d.destination_id = dest.id
                        WHERE d.last_modified > %s AND d.last_modified <= %s
                    """, (last_sync_dt, new_sync_timestamp))
                    changes_to_send["devices"] = cursor.fetchall()

                    cursor.execute("""
                        SELECT v.*, d.uuid as device_uuid
                        FROM verifications v
                        LEFT JOIN devices d ON v.device_id = d.id
                        WHERE v.last_modified > %s AND v.last_modified <= %s
                    """, (last_sync_dt, new_sync_timestamp))
                    changes_to_send["verifications"] = cursor.fetchall()

                # Firma: base64 per i blob
                if "signatures" in changes_to_send:
                    for signature_record in changes_to_send["signatures"]:
                        if signature_record.get("signature_data"):
                            signature_record["signature_data"] = base64.b64encode(signature_record["signature_data"]).decode('utf-8')

                # Serializza date/datetime in ISO
                for _, rows in changes_to_send.items():
                    for row in rows:
                        for key, value in list(row.items()):
                            if isinstance(value, (datetime, date)):
                                row[key] = value.isoformat()

        # Se siamo qui, il with conn ha COMMITTATO
        return {
            "status": "success",
            "new_sync_timestamp": new_sync_timestamp.isoformat(),
            "changes": changes_to_send,
            "uuid_map": final_uuid_map
        }

    except Exception as e:
        logging.error(f"Errore grave durante la sincronizzazione: {e}", exc_info=True)
        # Il with conn avrebbe già fatto rollback; se eccezione prima del with, non c'è transazione aperta
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/users", response_model=List[User])
def read_users(current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Operazione non autorizzata")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT username, role, first_name, last_name FROM users ORDER BY username")
        users = cursor.fetchall()
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail="Errore interno del server.")
    finally:
        if conn: conn.close()

@app.post("/users", response_model=User)
def create_user(user: UserCreate, current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Operazione non autorizzata")
    hashed_password = get_password_hash(user.password)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "INSERT INTO users (username, hashed_password, role, first_name, last_name) VALUES (%s, %s, %s, %s, %s) RETURNING username, role, first_name, last_name",
            (user.username, hashed_password, user.role, user.first_name, user.last_name)
        )
        new_user = cursor.fetchone()
        conn.commit()
        return new_user
    except errors.UniqueViolation:
        raise HTTPException(status_code=400, detail="Un utente con questo nome esiste già.")
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Errore del server: {e}")
    finally:
        if conn: conn.close()

@app.put("/users/{username}", response_model=User)
def update_user(username: str, user_update: UserUpdate, current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Operazione non autorizzata")
    fields_to_update = []
    params = {}
    if user_update.password:
        fields_to_update.append("hashed_password = %(hashed_password)s")
        params["hashed_password"] = get_password_hash(user_update.password)
    if user_update.role:
        fields_to_update.append("role = %(role)s")
        params["role"] = user_update.role
    if user_update.first_name is not None:
        fields_to_update.append("first_name = %(first_name)s")
        params["first_name"] = user_update.first_name
    if user_update.last_name is not None:
        fields_to_update.append("last_name = %(last_name)s")
        params["last_name"] = user_update.last_name
    if not fields_to_update:
        raise HTTPException(status_code=400, detail="Nessun dato da aggiornare fornito.")
    params["username"] = username
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        query = f"UPDATE users SET {', '.join(fields_to_update)} WHERE username = %(username)s RETURNING username, role, first_name, last_name"
        cursor.execute(query, params)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Utente non trovato.")
        updated_user = cursor.fetchone()
        conn.commit()
        return updated_user
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Errore del server: {e}")
    finally:
        if conn: conn.close()

@app.delete("/users/{username}", status_code=204)
def delete_user(username: str, current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin':
        raise HTTPException(status_code=403, detail="Operazione non autorizzata")
    if current_user.username == username:
        raise HTTPException(status_code=400, detail="Un admin non può eliminare se stesso.")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username = %s", (username,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Utente non trovato.")
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Errore del server: {e}")
    finally:
        if conn: conn.close()

@app.post("/signatures/{username}")
def upload_signature(username: str, file: UploadFile = File(...), current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin' and current_user.username != username:
        raise HTTPException(status_code=403, detail="Non autorizzato a modificare la firma di un altro utente.")
    signature_data = file.file.read()
    timestamp = datetime.now(timezone.utc)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO signatures (username, signature_data, last_modified)
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                signature_data = EXCLUDED.signature_data,
                last_modified = EXCLUDED.last_modified;
            """,
            (username, signature_data, timestamp)
        )
        conn.commit()
        return {"status": "success", "username": username}
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail="Errore del server durante il salvataggio della firma.")
    finally:
        if conn: conn.close()

@app.get("/signatures/{username}", responses={200: {"content": {"image/png": {}}}})
def get_signature(username: str, current_user: User = Depends(get_current_user)):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT signature_data FROM signatures WHERE username = %s", (username,))
        record = cursor.fetchone()
        if not record or not record['signature_data']:
            raise HTTPException(status_code=404, detail="Firma non trovata.")
        from fastapi.responses import Response
        return Response(content=record['signature_data'], media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore del server: {e}")
    finally:
        if conn: conn.close()

@app.delete("/signatures/{username}", status_code=204)
def delete_signature(username: str, current_user: User = Depends(get_current_user)):
    if current_user.role != 'admin' and current_user.username != username:
        raise HTTPException(status_code=403, detail="Non autorizzato a eliminare la firma di un altro utente.")
    timestamp = datetime.now(timezone.utc)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE signatures SET signature_data = NULL, last_modified = %s WHERE username = %s",
            (timestamp, username)
        )
        conn.commit()
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=500, detail=f"Errore del server: {e}")
    finally:
        if conn: conn.close()

# --- ENDPOINT ROOT ---
@app.get("/")
def root():
    return {"message": "Safety Test Sync API è in esecuzione."}

# Blocco per l'esecuzione diretta
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)