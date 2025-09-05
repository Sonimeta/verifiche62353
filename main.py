# main.py
import logging
import sys
import os
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from jose import jwt, JWTError
import app.auth_manager as auth_manager
from app import auth_manager
from dotenv import load_dotenv
from app.config import STYLESHEET, load_verification_profiles
from app.ui.main_window import MainWindow
from app.logging_config import setup_logging
from app.backup_manager import create_backup
from app.ui.dialogs.login_dialog import LoginDialog
from app import config

load_dotenv()
# La SECRET_KEY qui deve essere IDENTICA a quella in real_server.py
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

if __name__ == '__main__':
    # 1. Crea l'oggetto applicazione UNA SOLA VOLTA
    app = QApplication(sys.argv)
    
    setup_logging()
    logging.info("=====================================")
    logging.info("||   Avvio Safety Test Manager     ||")
    logging.info("=====================================")
    logging.info(f"BASE_DIR: {config.BASE_DIR}")
    logging.info(f"APP_DATA_DIR: {config.APP_DATA_DIR}")
    logging.info(f"DB_PATH: {config.DB_PATH}")
    logging.info(f"BACKUP_DIR: {config.BACKUP_DIR}")
    
    create_backup()
    
    # 2. Avvia un ciclo che permette il login e il riavvio
    while True:
        logged_in_successfully = False
        
        # Gestisce il caricamento della sessione o il login
        if auth_manager.load_session_from_disk():
            logged_in_successfully = True
        else:
            login_dialog = LoginDialog()
            if login_dialog.exec() == QDialog.Accepted:
                try:
                    token = login_dialog.token_data['access_token']
                    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                    username, role, full_name = payload.get("sub"), payload.get("role"), payload.get("full_name", "N/D")
                    
                    auth_manager.set_current_user(username, role, token, full_name)
                    auth_manager.save_session_to_disk()
                    logged_in_successfully = True
                except (JWTError, KeyError) as e:
                    QMessageBox.critical(None, "Errore Critico", "Il token di autenticazione non è valido.")
        
        # Se il login ha avuto successo, avvia l'applicazione
        if logged_in_successfully:
            try:
                config.load_verification_profiles()
            except Exception as e:
                QMessageBox.critical(None, "Errore Caricamento Profili", f"Impossibile caricare i profili:\n{e}")
                sys.exit(1)

            app.setStyleSheet(config.STYLESHEET)
            window = MainWindow()
            window.show()
            
            app.exec() # Avvia il ciclo degli eventi, che si blocca finché la finestra non si chiude
    
            if window.relogin_requested or window.restart_after_sync:
                logging.info("Riavvio richiesto (logout o post-sync)...")
                continue 
            else:
                break 
        else:
            break 

    logging.info("Applicazione chiusa.")
    sys.exit(0)