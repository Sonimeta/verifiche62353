# app/backup_manager.py
import os
import shutil
import logging
from datetime import datetime
from app import config

# ✅ Usa i percorsi centralizzati in AppData
DB_FILE = config.DB_PATH
BACKUP_DIR = config.BACKUP_DIR
BACKUP_RETENTION_COUNT = 10  # Numero di backup da conservare

def create_backup():
    """Crea un backup del file del database con un timestamp."""
    # ✅ Assicurati che la cartella backup esista in AppData
    os.makedirs(BACKUP_DIR, exist_ok=True)

    if not os.path.exists(DB_FILE):
        logging.warning(f"File database '{DB_FILE}' non trovato. Backup saltato.")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.splitext(os.path.basename(DB_FILE))[0]  # 'verifiche'
    backup_name = f"{base}_{timestamp}.db.bak"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    try:
        shutil.copy2(DB_FILE, backup_path)
        logging.info(f"Backup creato: {backup_path}")
        _rotate_old_backups()
    except Exception:
        logging.error("Errore durante la creazione del backup.", exc_info=True)

def _rotate_old_backups():
    """Mantiene solo gli ultimi BACKUP_RETENTION_COUNT backup."""
    try:
        if not os.path.isdir(BACKUP_DIR):
            return
        backups = [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR)
                   if f.lower().endswith(".db")]
        backups.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        if len(backups) > BACKUP_RETENTION_COUNT:
            for f in backups[BACKUP_RETENTION_COUNT:]:
                try:
                    os.remove(f)
                    logging.info(f"Vecchio backup rimosso: {f}")
                except Exception:
                    logging.warning(f"Impossibile rimuovere backup: {f}", exc_info=True)
    except Exception:
        logging.error("Errore durante la rotazione dei vecchi backup.", exc_info=True)

def restore_from_backup(backup_path):
    """Ripristina il database da un file di backup, sovrascrivendo quello corrente."""
    try:
        shutil.copy2(backup_path, DB_FILE)
        logging.warning(f"Database ripristinato con successo dal file: {backup_path}")
        return True
    except Exception:
        logging.critical(f"Errore critico durante il ripristino dal backup: {backup_path}", exc_info=True)
        return False
