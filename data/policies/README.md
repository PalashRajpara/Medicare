# Policy Documents Drop-Zone

> **INPUT DATA ONLY**: These files are source policy documents. When indexed via `make setup` or `medicare-setup --all`, chunks are stored in `var/chroma/` and metadata is recorded in `var/manifest.db`.

Place health insurance policy Markdown files (`*.md`) in this directory.

## Recommended File Structure
Each Markdown file should represent an insurance product or policy guideline.
Use `#` and `##` headings for each section so the chunking indexer can record accurate section metadata:

```markdown
# Star Health Comprehensive Insurance Policy

## Waiting Periods
Pre-existing diseases (PED) are subject to a 24-month waiting period...

## Room Rent Capping
No room rent capping applies for normal rooms. ICU charges are covered up to actuals...

## Cashless Hospitalization Process
Planned hospitalization requires pre-authorization request 48 hours prior...

## Exclusions and Claim Rejections
Cosmetic surgery, non-allopathic treatments without NABH certification are excluded...

## Grievance and Appeal Process
In case of claim repudiation, submit an appeal to the grievance cell within 30 days...
```
