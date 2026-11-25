# Seed CSV Drop-Zone

> **INPUT DATA ONLY**: These files are seed inputs. When loaded via `make setup` or `medicare-setup --all`, rows are ingested into `var/hospitals.db`.

Place three UTF-8 CSV files with exact headers in this directory:

### 1. `hospitals.csv`
Header:
`hospital_id,name,city,state,rating,bed_count,nabh_accredited,emergency_wait_minutes`

Types & Constraints:
- `hospital_id`: Integer primary key
- `name`: Text
- `city`: Text
- `state`: Text
- `rating`: Real (between 0.0 and 5.0)
- `bed_count`: Integer
- `nabh_accredited`: Integer (0 or 1)
- `emergency_wait_minutes`: Integer

### 2. `hospital_procedures.csv`
Header:
`procedure_id,hospital_id,procedure_name,category,min_cost_inr,max_cost_inr,avg_cost_inr,avg_wait_days,room_rent_per_day_inr`

Types & Constraints:
- `procedure_id`: Integer primary key
- `hospital_id`: Integer references `hospitals(hospital_id)`
- `procedure_name`: Text
- `category`: Text
- `min_cost_inr`: Integer
- `max_cost_inr`: Integer
- `avg_cost_inr`: Integer (must satisfy `min_cost_inr <= avg_cost_inr <= max_cost_inr`)
- `avg_wait_days`: Integer
- `room_rent_per_day_inr`: Integer

### 3. `insurer_acceptance.csv`
Header:
`acceptance_id,hospital_id,insurer_name,cashless_accepted,network_type,avg_claim_settlement_days`

Types & Constraints:
- `acceptance_id`: Integer primary key
- `hospital_id`: Integer references `hospitals(hospital_id)`
- `insurer_name`: Text
- `cashless_accepted`: Integer (0 or 1)
- `network_type`: Text (e.g., Tier-1, Preferred, General)
- `avg_claim_settlement_days`: Integer
