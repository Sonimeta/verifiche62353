import pandas as pd
from PySide6.QtCore import QObject, Signal
from app import services
import logging

class TableExportWorker(QObject):
    """
    Esegue l'esportazione della tabella dei dispositivi di una destinazione
    in un file Excel formattato, con filtri, colori condizionali e testo a capo.
    """
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, destination_id, output_path):
        super().__init__()
        self.destination_id = destination_id
        self.output_path = output_path

    def run(self):
        try:
            logging.info(f"Avvio esportazione tabella formattata per destinazione ID: {self.destination_id}")
            export_data = services.get_destination_devices_for_export(self.destination_id)
            
            if not export_data:
                self.finished.emit("Nessun dispositivo trovato per la destinazione selezionata.")
                return

            df = pd.DataFrame(export_data)
            
            final_columns_order = [
                "INVENTARIO AMS", "INVENTARIO CLIENTE", "DENOMINAZIONE", "MARCA", "MODELLO", "MATRICOLA",
                "REPARTO", "DATA", "DESTINAZIONE", "TECNICO", "ESITO"
            ]
            
            for col in final_columns_order:
                if col not in df.columns:
                    df[col] = None
            df = df[final_columns_order]

            # Inizializza il writer di Excel con il motore xlsxwriter
            writer = pd.ExcelWriter(self.output_path, engine='xlsxwriter')
            # Scrivi i dati partendo dalla seconda riga (startrow=1) per lasciare spazio all'intestazione
            df.to_excel(writer, sheet_name='Verifiche', index=False, header=False, startrow=1)
            
            workbook = writer.book
            worksheet = writer.sheets['Verifiche']

            # Definisci un formato per l'intestazione (grassetto, sfondo, testo a capo)
            header_format = workbook.add_format({
                'bold': True,
                'text_wrap': True,
                'valign': 'vcenter',
                'fg_color': '#D7E4BC',
                'border': 1
            })

            # Definisci i formati per la formattazione condizionale CON text_wrap incluso
            green_format = workbook.add_format({
                'bg_color': "#47BD43", 
                'font_color': "#000000", 
                'text_wrap': True, 
                'valign': 'top'
            })
            red_format = workbook.add_format({
                'bg_color': '#FFC7CE', 
                'font_color': "#000000", 
                'text_wrap': True, 
                'valign': 'top'
            })

            blue_format = workbook.add_format({
                'bg_color': '#BDD7EE',
                'font_color': "#000000",
                'text_wrap': True,
                'valign': 'top'
            })

            # Definisci un formato base per le celle di dati con testo a capo
            cell_format = workbook.add_format({
                'text_wrap': True, 
                'valign': 'top'
            })

            num_rows, num_cols = df.shape

            # Applica il formato di base a tutte le colonne PRIMA della formattazione condizionale
            for col in range(num_cols):
                worksheet.set_column(col, col, None, cell_format)

            # Applica la formattazione condizionale (questo sovrascriverà il formato base dove applicabile)
            worksheet.conditional_format(f'A2:K{num_rows + 1}', {
                'type': 'formula',
                'criteria': '=SEARCH("CONFORME",$K2)',
                'format': green_format
            })

            worksheet.conditional_format(f'A2:K{num_rows + 1}', {
                'type': 'formula',
                'criteria': '=SEARCH("NON CONFORME",$K2)',
                'format': red_format
            })

            # Crea la tabella
            columns_for_table = [{'header': col} for col in df.columns]
            worksheet.add_table(0, 0, num_rows, num_cols - 1, {
                'columns': columns_for_table,
                'header_row': True,
                'style': 'Table Style Light 15'
            })
            
            # Scrivi l'intestazione manualmente per applicare il formato corretto
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

            # Imposta la larghezza delle colonne
            worksheet.set_column('A:B', 18)
            worksheet.set_column('C:C', 45)
            worksheet.set_column('D:F', 22)
            worksheet.set_column('G:G', 25)
            worksheet.set_column('H:H', 12)
            worksheet.set_column('I:I', 30)
            worksheet.set_column('J:J', 20)
            worksheet.set_column('K:K', 25)

            # IMPORTANTE: Imposta l'altezza delle righe per permettere il testo a capo
            for row in range(1, num_rows + 2):  # +2 perché includiamo l'header
                worksheet.set_row(row, None, None, {'level': 0})

            writer.close()
            
            logging.info(f"Esportazione formattata completata con successo: {self.output_path}")
            self.finished.emit(f"Tabella esportata con successo in:\n{self.output_path}")

        except Exception as e:
            logging.error("Errore durante l'esportazione della tabella.", exc_info=True)
            self.error.emit(f"Si è verificato un errore imprevisto durante l'esportazione:\n{e}")