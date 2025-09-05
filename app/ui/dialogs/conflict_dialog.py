from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
                               QTableWidgetItem, QAbstractItemView, QHeaderView, 
                               QDialogButtonBox, QGroupBox)
from PySide6.QtGui import QColor, QFont

class ConflictResolutionDialog(QDialog):
    """
    Una finestra di dialogo che mostra un singolo conflitto di sincronizzazione
    e permette all'utente di scegliere come risolverlo.
    """
    def __init__(self, conflict_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Risoluzione Conflitto di Sincronizzazione")
        self.setMinimumSize(800, 400)

        self.resolution = None # Memorizzerà la scelta dell'utente

        # Estrai i dati dal dizionario del conflitto
        client_version = conflict_data.get('client_version', {})
        server_version = conflict_data.get('server_version', {})
        table = conflict_data.get('table', 'N/A')
        
        main_layout = QVBoxLayout(self)

        # Messaggio informativo
        info_label = QLabel(f"È stato rilevato un conflitto per un record nella tabella <b>{table}</b>.")
        info_label.setFont(QFont("Segoe UI", 11))
        main_layout.addWidget(info_label)
        main_layout.addWidget(QLabel("Qualcuno ha salvato una nuova versione sul server prima che le tue modifiche potessero essere sincronizzate."))

        # Layout per i due pannelli di confronto
        panels_layout = QHBoxLayout()
        
        # Pannello versione locale (client)
        client_group = QGroupBox("La Tua Versione (Modifiche Locali)")
        client_layout = QVBoxLayout(client_group)
        self.client_table = self.create_details_table(client_version)
        client_layout.addWidget(self.client_table)
        panels_layout.addWidget(client_group)

        # Pannello versione remota (server)
        server_group = QGroupBox("Versione sul Server (Più Recente)")
        server_layout = QVBoxLayout(server_group)
        self.server_table = self.create_details_table(server_version)
        server_layout.addWidget(self.server_table)
        panels_layout.addWidget(server_group)

        main_layout.addLayout(panels_layout)
        
        self.highlight_differences(client_version, server_version)

        # Pulsanti di scelta
        buttons = QDialogButtonBox()
        self.btn_keep_local = buttons.addButton("Mantieni la Mia Versione", QDialogButtonBox.ActionRole)
        self.btn_use_server = buttons.addButton("Usa la Versione del Server", QDialogButtonBox.ActionRole)
        buttons.addButton(QDialogButtonBox.Cancel)

        buttons.clicked.connect(self.handle_button_click)
        main_layout.addWidget(buttons)

    def create_details_table(self, data_version):
        """Crea e popola una tabella con i dettagli di una versione del record."""
        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Campo", "Valore"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        HIDE = {'uuid','is_synced','last_modified','created_at'}
        for key in sorted(data_version.keys(), key=str.lower):
            if key in HIDE: 
                continue
            val = data_version.get(key, "")
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(str(key)))
            table.setItem(row, 1, QTableWidgetItem(str(val)))
        return table

    def highlight_differences(self, client_data, server_data):
        """Evidenzia in giallo le righe con valori diversi tra le due tabelle."""
        highlight_color = QColor("#EBCB8B") # Un giallo/oro dal tema Nord
        
        for row in range(self.client_table.rowCount()):
            key_item = self.client_table.item(row, 0)
            if not key_item: continue
            
            key = key_item.text()
            client_value = self.client_table.item(row, 1).text()
            server_value = str(server_data.get(key, ''))

            if client_value != server_value:
                self.client_table.item(row, 0).setBackground(highlight_color)
                self.client_table.item(row, 1).setBackground(highlight_color)
                
                # Cerca la riga corrispondente nella tabella del server
                for server_row in range(self.server_table.rowCount()):
                    if self.server_table.item(server_row, 0).text() == key:
                        self.server_table.item(server_row, 0).setBackground(highlight_color)
                        self.server_table.item(server_row, 1).setBackground(highlight_color)
                        break

    def handle_button_click(self, button):
        """Imposta la scelta dell'utente e chiude la finestra."""
        if button == self.btn_keep_local:
            self.resolution = "keep_local"
            self.accept()
        elif button == self.btn_use_server:
            self.resolution = "use_server"
            self.accept()
        else: # Cancel
            self.resolution = "cancel"
            self.reject()