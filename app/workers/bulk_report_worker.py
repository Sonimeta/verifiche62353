# app/workers/bulk_report_worker.py
import os
import logging
import re
from PySide6.QtCore import QObject, Signal

from app import services

class BulkReportWorker(QObject):
    """
    Esegue la generazione massiva di report PDF in un thread separato.
    """
    progress_updated = Signal(int, str)
    finished = Signal(int, list)
    
    def __init__(self, verifications_to_process, output_folder, report_settings):
        super().__init__()
        self.verifications = [dict(v) for v in verifications_to_process]
        self.output_folder = output_folder
        self.report_settings = report_settings
        self._is_cancelled = False

    def cancel(self):
        """Richiede l'annullamento dell'operazione."""
        logging.warning("Richiesta di annullamento della generazione massiva di report.")
        self._is_cancelled = True

    def run(self):
        """Esegue il lavoro pesante."""
        total_reports = len(self.verifications)
        success_count = 0
        failed_reports = []

        logging.info(f"Avvio generazione massiva di {total_reports} report in: {self.output_folder}")

        for i, verif in enumerate(self.verifications):
            if self._is_cancelled:
                logging.warning("Generazione massiva interrotta dall'utente.")
                break
            
            verif_id = verif.get('id')
            dev_id = verif.get('device_id')
            
            progress_percent = int(((i + 1) / total_reports) * 100)
            progress_message = f"Generazione report {i + 1} di {total_reports} (Verifica ID: {verif_id})..."
            self.progress_updated.emit(progress_percent, progress_message)

            try:
                if not dev_id or not verif_id:
                    raise ValueError("ID dispositivo o verifica mancante.")

                # --- NUOVA LOGICA PER IL NOME DEL FILE ---
                ams_inv = verif.get('ams_inventory', '').strip()
                serial_num = verif.get('serial_number', '').strip()
                
                base_name = ams_inv if ams_inv else serial_num
                if not base_name:
                    base_name = f"Report_Verifica_{verif_id}" # Nome di fallback
                
                # Pulisce il nome da caratteri non validi per un file
                safe_base_name = re.sub(r'[\\/*?:"<>|]', '_', base_name)
                
                # Aggiunge la data per rendere il nome unico nel mese
                verif_date = verif.get('verification_date', '').replace('-', '')
                
                os.makedirs(self.output_folder, exist_ok=True)
                verif_date = (verif.get('verification_date') or '').replace('-', '')
                suffix = f"_{verif_date}" if verif_date else ""
                filename = os.path.join(self.output_folder, f"{safe_base_name}{suffix} VE.pdf")
                # --- FINE NUOVA LOGICA ---

                services.generate_pdf_report(
                    filename=filename,
                    verification_id=verif_id,
                    device_id=dev_id,
                    report_settings=self.report_settings,
                )
                success_count += 1

            except Exception as e:
                error_message = f"Report per Verifica ID {verif_id}: Fallito ({e})"
                logging.error(f"Errore durante la generazione massiva: {error_message}", exc_info=True)
                failed_reports.append(error_message)
        
        self.finished.emit(success_count, failed_reports)
