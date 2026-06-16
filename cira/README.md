# CIRA — Cyber Incidence Response Assistant

A Streamlit application that helps cybercrime victims in India get immediate guidance and map their incident to the correct category on the [National Cyber Crime Reporting Portal](https://cybercrime.gov.in).

## Quick Start

Using `uv`:

```bash
cd /Users/harshbhatt/Projects/CIRA
cp cira/.env.example .env        # Add your AZURE_OPENAI_API_KEY
cd cira
uv sync
uv run python agent.py      # Investigation Officer loop
```

Run the Streamlit app:

```bash
uv run streamlit run app.py
```

Run the API server:

```bash
uv run uvicorn server:app --reload
```

Traditional `venv` setup:

```bash
cd /Users/harshbhatt/Projects/CIRA
cp cira/.env.example .env        # Add your AZURE_OPENAI_API_KEY
cd cira
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Architecture

End-to-end flow:

1. **Intake** — Free-text or guided wizard
2. **Azure OpenAI** — Summarizes account and proposes subcategory
3. **Classification** — Maps to official taxonomy (`data/categories.json`)
4. **Confirmation** — User confirms or selects from 29 subcategories
5. **Rule Engine** — Dynamic follow-up questions by incident type
6. **Evidence Checklist** — Category-specific items to gather
7. **Playbook** — Markdown guidance per subcategory
8. **Summary & Timeline** — Azure OpenAI-generated, editable case record

## Project Structure

```
cira/
├── app.py                 # Main Streamlit app
├── data/categories.json   # Official taxonomy (source of truth)
├── playbooks/             # One .md playbook per subcategory
├── components/            # UI modules (intake, evidence, playbook)
├── utils/                 # Azure OpenAI, rules, classification, loader
└── scripts/               # Playbook generator
```

## Configuration

- `AZURE_OPENAI_API_KEY` in `/Users/harshbhatt/Projects/CIRA/.env` by default
- Azure endpoint defaults to `https://azure-foundary-a11.cognitiveservices.azure.com/`
- Deployment defaults to `gpt-5.4-mini`
- Override the endpoint, deployment, or API version with `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and `AZURE_OPENAI_API_VERSION` in `/Users/harshbhatt/Projects/CIRA/.env`
- Use a chat/instruction model for the Investigation Officer loop. Content-safety models return labels rather than conversation.
- Smoke test: `uv run python test_azure_openai.py`

## Regenerating Placeholder Playbooks

```bash
python scripts/generate_playbooks.py
```

## License

Internal / operator use — playbook content pending.
