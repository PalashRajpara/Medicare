# Adding Documents & Seed Data

This guide describes how to ingest healthcare policies, seed CSVs, and user uploads.

## Input Directories

All immutable input files reside strictly under `data/`:
- `data/seed/`: Structured CSV files:
  - `hospitals.csv`: Hospital directory records.
  - `hospital_procedures.csv`: Procedure pricing, room rents, and wait times.
  - `insurer_acceptance.csv`: Cashless insurance network mapping.
- `data/policies/`: Markdown policy files containing policy clauses, exclusions, waiting periods, and terms.

## Indexing Seed Data

To ingest newly added CSVs or policies:

```bash
# Ingest all new CSVs and index policies
uv run medicare-setup --all

# Sync index (pruning removed files from index)
uv run medicare-setup --sync

# Force complete reindex
uv run medicare-setup --reindex-all
```

## User Document Uploads

Users can upload documents via:
- UI sidebar upload drawer (supports `.pdf`, `.docx`, `.md`, `.txt`, `.html`, `.csv`)
- API endpoint `POST /documents/upload`

Uploaded documents are saved under `var/uploads/` and indexed in `var/chroma/` under the `user` scope.
