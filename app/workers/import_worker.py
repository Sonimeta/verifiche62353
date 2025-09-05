# app/workers/import_worker.py
import pandas as pd
from PySide6.QtCore import QObject, Signal
from app import services  # Importa i servizi, NON il database
import logging

class ImportWorker(QObject):
    progress_updated = Signal(int)
    finished = Signal(int, list, str) 
    error = Signal(str)

    def __init__(self, filename, mapping, destination_id): # Modificato
        super().__init__()
        self.filename = filename
        self.mapping = mapping
        self.destination_id = destination_id # Modificato
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not self.destination_id:
            self.error.emit("Seleziona una destinazione valida prima di importare.")
            return
        try:
            if self.filename.endswith('.csv'):
               with open(self.filename, 'r', encoding='utf-8', newline='') as f:
                   sample = f.read(2048)
                   f.seek(0)
               df = pd.read_csv(self.filename, dtype=str).fillna('')
            else:
                df = pd.read_excel(self.filename, dtype=str).fillna('')
        except Exception as e:
            self.error.emit(f"Impossibile leggere il file:\n{e}")
            return
            
        added_count, skipped_rows_details, total_rows = 0, [], len(df)

        for index, row in df.iterrows():
            if self._is_cancelled:
                break
            try:
                # Passa il destination_id al servizio
                services.process_device_import_row(row.to_dict(), self.mapping, self.destination_id) # Modificato
                added_count += 1
            except ValueError as e:
                skipped_rows_details.append(f"Riga {index + 2}: {e}")
            except Exception as e:
                logging.error(f"Errore imprevisto importando la riga {index + 2}", exc_info=True)
                skipped_rows_details.append(f"Riga {index + 2}: Errore imprevisto ({e})")
            
            self.progress_updated.emit(int(((index + 1) / total_rows) * 100))
        
        status = "Annullato" if self._is_cancelled else "Completato"
        self.finished.emit(added_count, skipped_rows_details, status)