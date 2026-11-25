# MediCare Input Data

> **IMPORTANT**: This directory contains **INPUTS ONLY**. All generated runtime state (databases, vector stores, uploads) is stored strictly in `var/`.

## Directory Layout

- `seed/`: Immutable seed CSV datasets:
  - `hospitals.csv`: Master hospital records (ID, name, city, state, bed count, rating, accreditation, emergency wait time).
  - `hospital_procedures.csv`: Procedural cost ranges, average costs, wait times, and room rent per day.
  - `insurer_acceptance.csv`: Cashless insurance acceptance matrix and claim settlement durations.
- `policies/`: Immutable curated insurance policy guidelines and clause documentation in Markdown format.

## Runtime State

All runtime state generated from these inputs is placed in `var/`:
- `var/hospitals.db`: SQLite database populated from `seed/`.
- `var/manifest.db`: Document catalog tracking chunk states and metadata.
- `var/platform.db`: Conversation threads and execution history.
- `var/chroma/`: ChromaDB vector index built from `policies/`.
- `var/uploads/`: User-uploaded documents.

To rebuild runtime state from these inputs:
```bash
make setup
# Or directly:
uv run medicare-setup --all
```
