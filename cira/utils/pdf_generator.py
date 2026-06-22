"""PDF Report Generation utility for CIRA using fpdf2."""

import datetime
from fpdf import FPDF
from pathlib import Path

class CiraReport(FPDF):
    def header(self):
        # Header banner
        self.set_font('Helvetica', 'B', 12)
        self.set_text_color(30, 58, 138)  # Indigo
        self.cell(0, 8, 'CIRA - CYBER INCIDENCE RESPONSE REPORT', border=0, ln=1, align='C')
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(107, 114, 128)  # Gray
        self.cell(0, 4, 'Prepared by CIRA AI Cybercrime Case Officer', border=0, ln=1, align='C')
        
        # Horizontal line
        self.set_draw_color(229, 231, 235)  # Light gray
        self.line(10, 24, 200, 24)
        self.ln(6)

    def footer(self):
        # Position at 1.5 cm from bottom
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(156, 163, 175)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}} | Confidential Incident Report | India Helpline: 1930', border=0, ln=0, align='C')

def sanitize_text(text: str) -> str:
    """Sanitize string for Latin-1 encoding used by default PDF Helvetica font."""
    if not text:
        return ""
    replacements = {
        "₹": "INR ",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u2013": "-",
        "\u2014": "--",
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    # Encode as latin-1, replace unsupported characters with ?
    return text.encode('latin-1', 'replace').decode('latin-1')

def generate_pdf_report(case_data: dict) -> bytes:
    """
    Generate PDF bytes for the case report.
    
    case_data fields:
      - description: str
      - classification: dict (subcategory_name, category_name, match_confidence)
      - summary: str
      - timeline: list of dicts (time, event)
      - evidence: dict (item_id -> bool)
      - followup_answers: dict (qid -> val)
      - evidence_labels: dict (item_id -> label)
      - questions_labels: dict (qid -> text)
    """
    pdf = CiraReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Title & Metadata block
    pdf.set_font('Helvetica', 'B', 14)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 10, 'OFFICIAL COMPLAINT COMPILATION PACKAGE', ln=1, align='L')
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(75, 85, 99)
    now_str = datetime.datetime.now().strftime("%d-%b-%Y %H:%M:%S")
    pdf.cell(0, 5, f'Report Date: {now_str}', ln=1)
    
    # 1. Incident Classification Card
    pdf.ln(4)
    pdf.set_fill_color(243, 244, 246)  # Gray-100 background
    pdf.set_draw_color(209, 213, 219)
    pdf.rect(10, pdf.get_y(), 190, 28, 'DF')
    
    pdf.set_y(pdf.get_y() + 2)
    classification = case_data.get("classification") or {}
    subcat = classification.get("subcategory_name", "Unclassified")
    cat = classification.get("category_name", "General Cybercrime")
    conf = classification.get("match_confidence")
    conf = float(conf) if conf is not None else 0.0
    
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 6, f'  Official Cybercrime Category: {sanitize_text(subcat)}', ln=1)
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(55, 65, 81)
    pdf.cell(0, 5, f'  Parent Section: {sanitize_text(cat)}', ln=1)
    pdf.cell(0, 5, f'  Classification Match Confidence: {int(conf * 100)}%', ln=1)
    pdf.ln(6)
    
    # 2. Case Summary
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 8, '1. Incident Summary', ln=1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(31, 41, 55)
    summary_text = case_data.get("summary") or "No incident summary provided."
    pdf.multi_cell(0, 5, sanitize_text(summary_text))
    pdf.ln(6)
    
    # 3. Incident Timeline
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 8, '2. Incident Timeline', ln=1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    timeline = case_data.get("timeline") or []
    if timeline:
        # Header Row
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_fill_color(229, 231, 235)
        pdf.cell(50, 7, '  Date & Time', border=1, fill=True)
        pdf.cell(140, 7, '  Event Description', border=1, fill=True, ln=1)
        
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(31, 41, 55)
        for item in timeline:
            time_val = item.get("time", "")
            event_val = item.get("event", "")
            if time_val or event_val:
                pdf.cell(50, 7, f' {sanitize_text(time_val)}', border=1)
                pdf.cell(140, 7, f' {sanitize_text(event_val)}', border=1, ln=1)
    else:
        pdf.set_font('Helvetica', 'I', 10)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 5, 'No timeline events generated.', ln=1)
    pdf.ln(6)
    
    # 4. Evidence Checklist Status
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 8, '3. Evidence Checklist Status', ln=1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    evidence_status = case_data.get("evidence") or {}
    evidence_labels = case_data.get("evidence_labels") or {}
    
    if evidence_labels:
        pdf.set_font('Helvetica', '', 9)
        for item_id, label in evidence_labels.items():
            is_collected = evidence_status.get(item_id, False)
            status_box = '[X] COLLECTED' if is_collected else '[ ] MISSING / PENDING'
            
            if is_collected:
                pdf.set_text_color(16, 185, 129)  # Green
                pdf.set_font('Helvetica', 'B', 9)
            else:
                pdf.set_text_color(239, 68, 68)  # Red
                pdf.set_font('Helvetica', '', 9)
                
            pdf.cell(45, 6, status_box, border=0)
            
            pdf.set_text_color(31, 41, 55)
            pdf.set_font('Helvetica', '', 9)
            pdf.cell(145, 6, f'  {sanitize_text(label)}', border=0, ln=1)
    else:
        pdf.set_font('Helvetica', 'I', 10)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 5, 'No evidence checklist items defined for this category.', ln=1)
    pdf.ln(6)
    
    # 5. Case Specific Q&A
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 8, '4. Incident Details & Diagnostics', ln=1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    followup_answers = case_data.get("followup_answers") or {}
    questions_labels = case_data.get("questions_labels") or {}
    
    if followup_answers:
        pdf.set_font('Helvetica', '', 9)
        for qid, ans in followup_answers.items():
            q_label = questions_labels.get(qid, qid)
            pdf.set_font('Helvetica', 'B', 9)
            pdf.set_text_color(75, 85, 99)
            pdf.cell(0, 5, f'Q: {sanitize_text(q_label)}', ln=1)
            pdf.set_font('Helvetica', '', 9)
            pdf.set_text_color(17, 24, 39)
            pdf.cell(0, 5, f'A: {sanitize_text(str(ans))}', ln=1)
            pdf.ln(2)
    else:
        pdf.set_font('Helvetica', 'I', 10)
        pdf.set_text_color(107, 114, 128)
        pdf.cell(0, 5, 'No supplementary questions answered.', ln=1)
    pdf.ln(6)
    
    # 6. National Helplines Box
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(17, 24, 39)
    pdf.cell(0, 8, '5. Official Resources & Next Steps', ln=1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)
    
    # Draw border box
    pdf.set_draw_color(30, 58, 138)
    pdf.set_fill_color(239, 246, 255)  # Light blue background
    pdf.rect(10, pdf.get_y(), 190, 32, 'DF')
    
    pdf.set_y(pdf.get_y() + 2)
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 5, '  CRITICAL STEPS FOR INDIAN CYBERCRIME VICTIMS:', ln=1)
    
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 4, '  - HELPLINE: Call 1930 immediately to report financial fraud (Golden Hour freeze request).', ln=1)
    pdf.cell(0, 4, '  - OFFICIAL REPORT: File this compiled incident summary on https://cybercrime.gov.in.', ln=1)
    pdf.cell(0, 4, '  - BANK DISPUTE: Contact your bank branch and file a written dispute within 3 days (RBI circular).', ln=1)
    pdf.cell(0, 4, '  - LOCAL POLICE: Save a printed copy of this report and submit it at the nearest cyber cell.', ln=1)
    
    # Output PDF bytes
    return pdf.output()
