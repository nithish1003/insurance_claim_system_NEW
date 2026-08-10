# 🧹 Project Cleanup & Optimization System

A production-grade maintenance utility designed to ensure the insurance system codebase remains clean, lightweight, and deployment-ready.

---

### 🚀 Key Features

#### 1. CLI-Based Execution
* **Argparse Integration**: Standardized command handling for reliable terminal interaction.
* **Explicit Control**: Enforces strict execution modes to prevent accidental data loss.

#### 2. Safety-First Design
* **Safety Interlock**: The script requires an explicit flag to proceed.
* **Mandatory Flags**:
    * `--dry-run` : Preview only (Read-only)
    * `--execute` : Perform cleanup (Write)

#### 3. Dry Run Mode (Preview)
* **Risk-Free Scanning**: Scans the entire project and lists all targeted files/folders.
* **Spatial Analysis**: Displays individual file sizes to help identify storage bottlenecks.
* **No Side Effects**: Guaranteed zero changes to the filesystem.

#### 4. Execute Mode (Cleanup)
* **Intelligent Purging**: Efficiently removes:
    * **Python Cache**: `__pycache__` directories and `*.pyc` files.
    * **Logs & Temp**: `*.log` files and temporary system folders.
    * **IDE/OS Junk**: `.vscode`, `.idea`, `.DS_Store`, and `Thumbs.db`.
* **Whitelist Guard**: Protects mission-critical files:
    * `manage.py`, `requirements.txt`, `risk_model.pkl`, and `claims_dataset.csv`.

#### 5. Audit Logging
* **Persistent Ledger**: Every operation is logged in `cleanup.log`.
* **Dual Output**:
    * **Terminal**: Real-time feedback and status reporting.
    * **Log File**: Permanent, timestamped audit trail for governance compliance.

#### 6. Operational Analytics
* **Success Metrics**: Displays a final summary including:
    * Total unique items processed.
    * **Total disk space reclaimed** (formatted in MB).

---

### 💻 Usage Instructions

**Preview cleanup safely (Recommended first step):**
```bash
python scripts/cleanup_project.py --dry-run
```

**Execute actual cleanup:**
```bash
python scripts/cleanup_project.py --execute
```

---

### 🏁 Final Statement
> "This cleanup system ensures that the insurance system remains lightweight, maintainable, and deployment-ready, while guaranteeing safety through controlled execution and full audit transparency."
