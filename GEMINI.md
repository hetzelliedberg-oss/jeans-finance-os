# 👖 JEANS AROUND FINANCE OS - ANTIGRAVITY WORKSPACE RULES

## 🌐 Central Cloud Hub & Multi-Device Sync Contract (PC & MacBook)

This workspace operates across multiple machines (Windows PC and MacBook) connected through a single Central Cloud Hub:
* **Central Cloud Hub URL:** `https://jeans-finance-os.onrender.com/api`
* **Local Database:** `data/finance_hub.db`
* **Sync Utility:** `hub_sync.py`

### 🤖 Mandatory Agent Behavior for Seamless Multi-Device Continuity:

1. **Auto-Pull on Start:**
   - Whenever the user asks for financial reports, audits, order checks, or P&L figures, **ALWAYS** ensure the latest data is pulled from the Central Cloud Hub:
     `python hub_sync.py pull`
   - This guarantees that any changes, new Telegram orders, or edits made from another machine (e.g. MacBook or PC) are immediately reflected.

2. **Auto-Push on Modification:**
   - Whenever you insert, update, delete, or audit any order or SKU cost in `finance_hub.db`:
     `python hub_sync.py push`
   - This pushes all changes to the Central Cloud Hub so all other devices and the web dashboard are updated in real time.

3. **Git Auto-Commit:**
   - Keep git clean: whenever audit scripts or core files are created or modified, commit them to `origin main`.

4. **Fact Audit Verification:**
   - Always run `python deep_audit_db_issues.py` and `python hub_sync.py status` to ensure **0 issues** and **100% in sync**.
