import os
import re
import logging
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from PySide6.QtCore import QSettings
from app import config
import io

# --- Costanti di Stile e Layout ---
COLOR_GRID = colors.HexColor('#CCCCCC')
COLOR_HEADER_BG = colors.HexColor('#F2F2F2')
COLOR_MAIN_BLUE = colors.HexColor('#005a9c')
COLOR_FAIL_TEXT = colors.HexColor('#721c24')
COLOR_PASS_TEXT = colors.HexColor('#0f5132')
FONT_BOLD = 'Helvetica-Bold'
FONT_NORMAL = 'Helvetica'
PAGE_MARGIN = 2*cm
SPACER_LARGE = 0.7*cm
SPACER_MEDIUM = 0.5*cm
SPACER_EXTRA_LARGE = 3*cm

def _create_styles():
    """Crea e restituisce un dizionario di stili di paragrafo personalizzati."""
    styles = getSampleStyleSheet()
    styles['Normal'].fontName = FONT_NORMAL
    styles['Normal'].fontSize = 9
    styles['Normal'].leading = 12
    styles.add(ParagraphStyle(name='Nometec', parent=styles['Normal'], fontName=FONT_NORMAL, fontSize=11))
    styles.add(ParagraphStyle(name='NormalBold', parent=styles['Normal'], fontName=FONT_BOLD))
    styles.add(ParagraphStyle(name='ReportTitle', fontName=FONT_BOLD, fontSize=16, textColor=COLOR_MAIN_BLUE, alignment=TA_CENTER, spaceAfter=4))
    styles.add(ParagraphStyle(name='ReportSubTitle', fontName=FONT_NORMAL, fontSize=10, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=12))
    styles.add(ParagraphStyle(name='SectionHeader', fontName=FONT_BOLD, fontSize=11, textColor=COLOR_MAIN_BLUE, spaceAfter=8))
    styles.add(ParagraphStyle(name='Conforme', fontName=FONT_BOLD, textColor=COLOR_PASS_TEXT))
    styles.add(ParagraphStyle(name='NonConforme', fontName=FONT_BOLD, textColor=COLOR_FAIL_TEXT))
    styles.add(ParagraphStyle(name='FinaleBase', fontName=FONT_BOLD, fontSize=12, alignment=TA_CENTER, borderPadding=10, borderWidth=1))
    return styles

def _create_styled_paragraph(text, style):
    """Crea un paragrafo con uno stile specifico, gestendo i 'None' e i ritorni a capo."""
    text_str = str(text) if text is not None else ''
    return Paragraph(text_str.replace('\n', '<br/>'), style)

# --- Funzioni per la Creazione delle Sezioni del Report ---

def _add_logo(story, report_settings):
    """Aggiunge il logo al report se presente."""
    logo_path = report_settings.get('logo_path')
    if logo_path and os.path.exists(logo_path):
        try:
            img = Image(logo_path, width=18*cm, height=3*cm, kind='proportional')
            img.hAlign = 'CENTER'
            story.append(img)
            story.append(Spacer(1, 0.8*cm))
        except Exception as e:
            logging.error(f"Impossibile caricare il file del logo: {e}")

def _add_header(story, styles, verification_data):
    """Aggiunge l'intestazione del report."""
    story.append(_create_styled_paragraph("Report di Verifica di Sicurezza Elettrica", styles['ReportTitle']))
    story.append(_create_styled_paragraph("(Conforme a CEI EN 62353)", styles['ReportSubTitle']))

    # --- INIZIO MODIFICA ---
    # Crea uno stile di paragrafo con allineamento a destra
    right_aligned_style = ParagraphStyle(name='NormalRight', parent=styles['Normal'], alignment=2) # 2 = TA_RIGHT

    date_text = f"<b>Data Verifica:</b> {verification_data.get('date', 'N/A')}"
    code_text = f"<b>Codice Verifica:</b> {verification_data.get('verification_code', 'N/A')}"

    # Usa una tabella per allineare i due elementi sulla stessa riga
    header_data = [
        [
            _create_styled_paragraph(date_text, styles['Normal']),
            _create_styled_paragraph(code_text, right_aligned_style)
        ]
    ]

    # La tabella ha due colonne di larghezza uguale
    header_table = Table(header_data, colWidths=[9*cm, 9*cm])
    # Applica uno stile per rimuovere eventuali bordi o padding
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    story.append(header_table)
    # --- FINE MODIFICA ---
    
    story.append(Spacer(1, SPACER_MEDIUM))

def _add_customer_info(story, styles, customer_info, destination_info):
    """Aggiunge la tabella con le informazioni sul cliente e sulla destinazione."""
    story.append(_create_styled_paragraph("Dati Cliente e Destinazione", styles['SectionHeader']))

    cliente = customer_info.get('name', 'N/D')
    indirizzo_cliente = customer_info.get('address', 'N/D')
    telefono_cliente = customer_info.get('phone', 'N/D')
    email_cliente = customer_info.get('email', 'N/D')

    destinazione = destination_info.get('name', 'N/D')
    indirizzo_destinazione = destination_info.get('address', 'N/D')

    customer_data = [
        [_create_styled_paragraph("Cliente", styles['NormalBold']), _create_styled_paragraph(cliente, styles['Normal']),
         _create_styled_paragraph("Destinazione", styles['NormalBold']), _create_styled_paragraph(destinazione, styles['Normal'])],
    ]

    table = Table(customer_data, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm])
    table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, COLOR_GRID), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 6)]))
    story.append(table)
    story.append(Spacer(1, SPACER_LARGE))

def _add_device_info(story, styles, device_info, verification_data):
    """Aggiunge la tabella con le informazioni sul dispositivo."""
    story.append(_create_styled_paragraph("Dati Apparecchio", styles['SectionHeader']))

    descrizione = device_info.get('description', 'N/D')
    reparto = device_info.get('department', 'N/D') 
    inventario_ams = device_info.get('ams_inventory', 'N/D') 
    marca = device_info.get('manufacturer', 'N/D')
    modello = device_info.get('model', 'N/D')
    inventario_cliente = device_info.get('customer_inventory', 'N/D')
    profile_key = verification_data.get('profile_name', '')
    profile = config.PROFILES.get(profile_key)
    profile_display_name = profile.name if profile else profile_key

    device_data = [
        
        [_create_styled_paragraph("Tipo Apparecchio", styles['NormalBold']), _create_styled_paragraph(descrizione, styles['Normal']),
         _create_styled_paragraph("Marca", styles['NormalBold']), _create_styled_paragraph(marca, styles['Normal'])],

        [_create_styled_paragraph("Modello", styles['NormalBold']), _create_styled_paragraph(modello, styles['Normal']),
         _create_styled_paragraph("Classe Isolamento", styles['NormalBold']), _create_styled_paragraph(profile_display_name, styles['Normal'])],

        [_create_styled_paragraph("Numero di Serie", styles['NormalBold']), _create_styled_paragraph(device_info.get('serial_number', ''), styles['Normal']),
         _create_styled_paragraph("Reparto", styles['NormalBold']), _create_styled_paragraph(reparto, styles['Normal'])],

        [_create_styled_paragraph("Inventario Cliente", styles['NormalBold']), _create_styled_paragraph(inventario_cliente, styles['Normal']),
         _create_styled_paragraph("Inventario AMS", styles['NormalBold']), _create_styled_paragraph(inventario_ams, styles['Normal'])],
    ]
    table = Table(device_data, colWidths=[3.5*cm, 5.5*cm, 3.5*cm, 5.5*cm])
    table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, COLOR_GRID), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 6)]))
    story.append(table)
    story.append(Spacer(1, SPACER_LARGE))

def _add_instrument_info(story, styles, mti_info):
    """Aggiunge la tabella con le informazioni sullo strumento di misura."""
    story.append(_create_styled_paragraph("Dati Strumento", styles['SectionHeader']))
    nome_strumento = mti_info.get('instrument', 'N/A')
    mti_data = [
        [_create_styled_paragraph("<b>Strumento:</b>", styles['NormalBold']), _create_styled_paragraph(nome_strumento, styles['Normal'])],
        [_create_styled_paragraph("<b>Matricola:</b>", styles['NormalBold']), _create_styled_paragraph(mti_info.get('serial', 'N/A'), styles['Normal'])],
        [_create_styled_paragraph("<b>Data Cal.:</b>", styles['NormalBold']), _create_styled_paragraph(mti_info.get('cal_date', 'N/A'), styles['Normal'])],
    ]
    table = Table(mti_data, colWidths=[9*cm, 9*cm])
    table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, COLOR_GRID), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 6)]))
    story.append(table)
    story.append(Spacer(1, SPACER_LARGE))

def _add_final_evaluation(story, styles, verification_data):
    """Aggiunge il riquadro con la valutazione finale."""
    story.append(_create_styled_paragraph("Esito Verifica Sicurezza Elettrica", styles['SectionHeader']))
    story.append(Spacer(1, SPACER_MEDIUM))
    
    is_pass = verification_data.get('overall_status') == 'PASSATO'
    finale_text = "Apparecchio Conforme" if is_pass else "Apparecchio NON Conforme"
    
    finale_style = ParagraphStyle(name='FinaleDynamic', parent=styles['FinaleBase'])
    finale_style.borderColor = colors.darkgreen if is_pass else colors.red
    finale_style.textColor = finale_style.borderColor
    
    story.append(_create_styled_paragraph(finale_text, finale_style))
    story.append(Spacer(1, SPACER_EXTRA_LARGE))

def _add_signature(story, styles, technician_name, signature_data): # <-- 2. Usa signature_data
    """Aggiunge la sezione per la firma leggendo i dati binari."""
    technician_paragraph = _create_styled_paragraph(f"<b>Tecnico Verificatore:</b> {technician_name or 'N/D'}", styles['Normal'])
    
    signature_content = Paragraph("<b>Firma:</b>________________________", styles['Normal'])
    
    # --- 3. MODIFICA CHIAVE: Crea l'immagine dai dati binari ---
    if signature_data:
        try:
            # Usa io.BytesIO per trattare i dati binari come un file in memoria
            image_file = io.BytesIO(signature_data)
            signature_image = Image(image_file, width=4*cm, height=2*cm, kind='proportional')
            signature_image.hAlign = 'LEFT'
            signature_content = signature_image
        except Exception as e:
            logging.warning(f"Impossibile caricare l'immagine della firma dai dati del DB: {e}")

    table = Table([[technician_paragraph, signature_content]], colWidths=[9*cm, 9*cm])
    table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'BOTTOM'), ('LEFTPADDING', (0,0), (-1,-1), 0)]))
    story.append(table)

def _add_visual_inspection(story, styles, verification_data):
    """Aggiunge la tabella con i risultati dell'ispezione visiva."""
    visual_data = verification_data.get('visual_inspection_data', {})
    if not visual_data or not visual_data.get('checklist'):
        return # Non aggiunge la sezione se non ci sono dati
        
    story.append(_create_styled_paragraph("Ispezione Visiva", styles['SectionHeader']))
    header = [_create_styled_paragraph("Controllo", styles['NormalBold']), _create_styled_paragraph("Esito", styles['NormalBold'])]
    table_data = [header]
    
    # --- MODIFICA CHIAVE: Leggiamo il nuovo campo 'result' ---
    for item in visual_data.get('checklist', []):
        esito_text = item.get('result', 'N/D') # Prende il testo salvato: OK, KO, N/A
        
        # Opzionale: Applica uno stile diverso in base al risultato
        if esito_text == "KO":
            esito_paragraph = _create_styled_paragraph(esito_text, styles['NonConforme'])
        elif esito_text == "OK":
            esito_paragraph = _create_styled_paragraph(esito_text, styles['Conforme'])
        else: # Per N/A o altro
            esito_paragraph = _create_styled_paragraph(esito_text, styles['Normal'])

        table_data.append([
            _create_styled_paragraph(item.get('item', ''), styles['Normal']), 
            esito_paragraph
        ])
                           
    table = Table(table_data, colWidths=[14.5*cm, 3.5*cm], repeatRows=1)
    table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, COLOR_GRID), ('BACKGROUND', (0,0), (-1,0), COLOR_HEADER_BG), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 6)]))
    story.append(table)
    story.append(Spacer(1, SPACER_LARGE))

def _add_electrical_measurements(story, styles, verification_data):
    """Aggiunge la tabella con le misure elettriche usando la nuova struttura dati."""
    story.append(_create_styled_paragraph("Misure Elettriche", styles['SectionHeader']))
    
    header = [_create_styled_paragraph(h, styles['NormalBold']) for h in ["Misura", "Valore Misurato", "Limite Norma", "Esito"]]
    table_data = [header]
    
    for res in verification_data.get('results', []):
        esito_style = styles['Conforme'] if res.get('passed') else styles['NonConforme']
        esito_text = "CONFORME" if res.get('passed') else "NON CONFORME"
        
        valore = res.get('value', 'N/A')
        limite = res.get('limit_value')
        unita = res.get('unit', '')

        valore_misurato = f"{valore} {unita}".strip() if valore != 'N/A' else 'N/A'
        limite_norma = f"≤ {limite} {unita}".strip() if limite is not None else 'N/A'
        
        table_data.append([
            _create_styled_paragraph(res.get('name', ''), styles['Normal']),
            _create_styled_paragraph(valore_misurato, styles['Normal']),
            _create_styled_paragraph(limite_norma, styles['Normal']),
            _create_styled_paragraph(esito_text, esito_style)
        ])
        
    table = Table(table_data, colWidths=[7*cm, 3.5*cm, 4.5*cm, 3*cm], repeatRows=1)
    table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, COLOR_GRID), ('BACKGROUND', (0,0), (-1,0), COLOR_HEADER_BG), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('LEFTPADDING', (0,0), (-1,-1), 6)]))
    story.append(table)
    story.append(Spacer(1, SPACER_LARGE))



def _add_footer(canvas, doc, device_info, verification_data):
    """Disegna il piè di pagina su ogni pagina."""
    canvas.saveState()
    canvas.setFont(FONT_NORMAL, 9)
    canvas.setStrokeColor(COLOR_GRID)
    canvas.line(doc.leftMargin, 1.4*cm, doc.width + doc.leftMargin, 1.4*cm)
    footer_text = f"Dispositivo S/N: {device_info.get('serial_number', 'N/A')}   |   Verifica del: {verification_data.get('date', 'N/A')}   |   Email: assistenza@amstrento.it"
    canvas.drawString(doc.leftMargin, 1*cm, footer_text)
    canvas.drawRightString(doc.width + doc.leftMargin, 1*cm, f"Pagina {doc.page}")
    canvas.restoreState()

# --- Funzione Principale per Creare il Report ---

def create_report(filename, device_info, customer_info, destination_info, mti_info, report_settings, verification_data, technician_name, signature_data):
    """
    Genera il report PDF assemblando le varie sezioni con la nuova struttura a due pagine.
    """
    doc = SimpleDocTemplate(filename, rightMargin=PAGE_MARGIN, leftMargin=PAGE_MARGIN, 
                            topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN, 
                            title="Rapporto di Verifica")

    styles = _create_styles()
    story = []

    # --- ASSEMBLAGGIO PAGINA 1: DATI, ESITO E FIRMA ---
    _add_logo(story, report_settings)
    _add_header(story, styles, verification_data)
    _add_customer_info(story, styles, customer_info, destination_info)
    _add_device_info(story, styles, device_info, verification_data)
    _add_instrument_info(story, styles, mti_info)
    _add_final_evaluation(story, styles, verification_data)
    _add_signature(story, styles, technician_name, signature_data)

    # --- INSERIMENTO INTERRUZIONE DI PAGINA ---
    story.append(PageBreak())

    # --- ASSEMBLAGGIO PAGINA 2: DETTAGLI TECNICI ---
    _add_visual_inspection(story, styles, verification_data)
    _add_electrical_measurements(story, styles, verification_data)


    # Il resto della funzione per costruire il documento rimane invariato
    footer_callback = lambda canvas, doc: _add_footer(canvas, doc, device_info, verification_data)
    try:
        doc.build(story, onFirstPage=footer_callback, onLaterPages=footer_callback)
        logging.info(f"Report PDF generato con successo: {filename}")
    except Exception as e:
        logging.error(f"Errore durante la creazione del PDF: {e}", exc_info=True)
        raise
