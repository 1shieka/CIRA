# CIRA — Cyber Incidence Response Assistant

A Streamlit application that helps cybercrime victims in India get immediate guidance and map their incident to the correct category on the [National Cyber Crime Reporting Portal](https://cybercrime.gov.in).

## Quick Start (with `uv`)

### 1. Start the Backend (FastAPI)
From the project root directory:
```bash
# Setup uv virtual environment (done)
uv venv
uv pip install -r requirements.txt

# Run the FastAPI server via uv
uv run python server.py
```
*The backend API will run on `http://localhost:8000`.*

### 2. Start the Frontend (Vite React Client)
From the `client` directory:
```bash
cd client
npm install
npm run dev -- --port 8501 --host
```
*The React user interface will run on `http://localhost:8501`.*

## Architecture

End-to-end flow:

1. **Intake** — Free-text or guided wizard
2. **Groq AI** — Summarizes account and proposes subcategory
3. **Classification** — Maps to official taxonomy (`data/categories.json`)
4. **Confirmation** — User confirms or selects from 29 subcategories
5. **Rule Engine** — Dynamic follow-up questions by incident type
6. **Evidence Checklist** — Category-specific items to gather
7. **Playbook** — Markdown guidance per subcategory
8. **Summary & Timeline** — Groq-generated, editable case record

## Project Structure

```
cira/
├── app.py                 # Main Streamlit app
├── data/categories.json   # Official taxonomy (source of truth)
├── playbooks/             # One .md playbook per subcategory
├── components/            # UI modules (intake, evidence, playbook)
├── utils/                 # Groq, rules, classification, loader
└── scripts/               # Playbook generator
```

## Configuration

- `GROQ_API_KEY` in `.env` (see `.env.example`)
- Model name in `utils/groq_client.py` (`GROQ_MODEL` constant)

## Regenerating Placeholder Playbooks

```bash
python scripts/generate_playbooks.py
```

## License

Internal / operator use — playbook content pending.
