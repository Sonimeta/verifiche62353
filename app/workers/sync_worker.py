# in app/workers/sync_worker.py
from PySide6.QtCore import QObject, Signal
from app import sync_manager
import logging

class SyncWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    conflict = Signal(list)

    def __init__(self, full_sync=False):  # <-- 1. Accept the 'full_sync' argument
        super().__init__()
        self.full_sync = full_sync  # <-- 2. Store the argument

    def run(self):
        try:
            # 3. Pass the argument to the sync_manager function
            status, data = sync_manager.run_sync(full_sync=self.full_sync)
            
            if status == "success":
                self.finished.emit(data)
            elif status == "conflict":
                self.conflict.emit(data)
            elif status == "error":
                self.error.emit(data)
                
        except Exception as e:
            logging.error("Errore imprevisto nel worker di sincronizzazione.", exc_info=True)
            self.error.emit(str(e))