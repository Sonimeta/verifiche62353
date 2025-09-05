# app/config.py
import json
from PySide6.QtWidgets import QMessageBox
from .data_models import Limit, Test, VerificationProfile
import logging
import os
import sys
import configparser

def get_base_dir():
    """Restituisce il percorso della cartella dell'eseguibile."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    
def get_app_data_dir():
    """
    Restituisce il percorso della cartella dati dell'applicazione, creandola se non esiste.
    (es. C:\\Users\\TuoNome\\AppData\\Roaming\\SafetyTestManager)
    """
    # Il nome della tua azienda/applicazione per la cartella dati
    APP_NAME = "SafetyTestManager"
    
    # Trova la cartella AppData
    if sys.platform == "win32":
        app_data_path = os.path.join(os.environ['APPDATA'], APP_NAME)
    else: # Per Mac/Linux
        app_data_path = os.path.join(os.path.expanduser('~'), '.' + APP_NAME)
        
    # Crea la cartella se non esiste
    os.makedirs(app_data_path, exist_ok=True)
    return app_data_path

# --- INIZIO NUOVA DEFINIZIONE DEI PERCORSI ---
BASE_DIR = get_base_dir() # La cartella del programma
APP_DATA_DIR = get_app_data_dir() # La cartella dei dati utente

# I file di dati ora vengono cercati/creati nella cartella AppData
DB_PATH = os.path.join(APP_DATA_DIR, "verifiche.db")
SESSION_FILE = os.path.join(APP_DATA_DIR, "session.json")
BACKUP_DIR = os.path.join(APP_DATA_DIR, "backups")
LOG_DIR = os.path.join(APP_DATA_DIR, "logs")
# Il file di configurazione viene ancora letto dalla cartella del programma
CONFIG_INI_PATH = os.path.join(BASE_DIR, "config.ini")
# --- FINE NUOVA DEFINIZIONE DEI PERCORSI ---

VERSIONE = "7.6.1"
PLACEHOLDER_SERIALS = {
    "N.P.", "NP", "N/A", "NA", "NON PRESENTE", "-", 
    "SENZA SN", "NO SN", "MANCA SN", "N/D", "MANCANTE", "ND"
}

def load_server_url():
    """Legge l'URL del server da config.ini."""
    parser = configparser.ConfigParser()
    if os.path.exists(CONFIG_INI_PATH):
        parser.read(CONFIG_INI_PATH)
        return parser.get('server', 'url', fallback='http://localhost:8000')
    return 'http://localhost:8000'

SERVER_URL = load_server_url()
PROFILES = {}


STYLESHEET = """
    /* Stile Generale */
    QWidget {
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 10pt;
        background-color: #F5F7FA;
        color: #37474F;
    }
    QMainWindow, QDialog {
        background-color: #F5F7FA;
    }

    /* Stile Menu Bar */
    QMenuBar {
        background-color: #37474F;
        color: #FFFFFF;
        font-weight: bold;
        padding: 4px;
    }
    QMenuBar::item {
        padding: 6px 12px;
        background-color: transparent;
        border-radius: 4px;
    }
    QMenuBar::item:selected {
        background-color: #0078d4;
    }
    QMenu {
        background-color: white;
        border: 1px solid #D0D0D0;
        color: #37474F;
    }
    QMenu::item:selected {
        background-color: #0078d4;
        color: white;
    }
    
    /* Stile Checkbox */
    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 4px;
        border: 2px solid #B0BEC5;
        background-color: white;
    }
    QCheckBox::indicator:checked {
        background-color: #0078d4;
        border: 2px solid #005a9e;
        image: url(./icons/check.svg);
    }

    QGroupBox {
        font-weight: bold;
        color: #0060a0;
        border: 1px solid #D0D0D0;
        border-radius: 8px;
        margin-top: 12px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 10px;
        left: 15px;
        background-color: #F5F7FA;
    }

    /* --- INIZIO NUOVE REGOLE PER LE TABELLE --- */
    QTableWidget {
        border: 1px solid #D0D0D0;
        gridline-color: #E0E0E0;
        background-color: white;
    }
    QTableWidget::item {
        padding: 5px;
    }
    QTableWidget::item:selected {
        background-color: #0078d4; /* Blu primario per lo sfondo */
        color: white; /* Testo bianco per un contrasto netto */
    }
    /* --- FINE NUOVE REGOLE PER LE TABELLE --- */

    QHeaderView::section {
        background-color: #FFFFFF;
        padding: 8px;
        border: none;
        border-bottom: 2px solid #0078d4;
        font-weight: bold;
    }
    QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        background-color: white;
        border: 1px solid #B0BEC5;
        border-radius: 4px;
        padding: 8px;
        min-height: 22px;
    }
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus {
        border: 2px solid #0078d4;
    }
    QPushButton {
        background-color: #0078d4;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 10px 20px;
        font-weight: bold;
    }
    QPushButton:hover {
        background-color: #005a9e;
    }
    QPushButton:pressed {
        background-color: #004578;
    }
    QPushButton:disabled {
        background-color: #B0BEC5;
    }
    QPushButton#secondary_button {
        background-color: #607D8B;
    }
    QPushButton#secondary_button:hover {
        background-color: #455A64;
    }
    QStatusBar {
        background-color: #37474F;
        color: white;
    }
    QStatusBar QLabel {
        color: white;
    }
"""

def load_verification_profiles(file_path=None):
    import database
    global PROFILES
    PROFILES = {}
    try:
        # La logica ora chiama la nuova funzione del database
        PROFILES = database.get_all_profiles_from_db()
        if not PROFILES:
            logging.warning("Nessun profilo di verifica trovato nel database locale.")

        return True
    except Exception as e:
        # Rilancia qualsiasi eccezione del database
        logging.error("Errore critico durante il caricamento dei profili dal database.", exc_info=True)
        raise e