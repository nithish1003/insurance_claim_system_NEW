import os
import shutil
import argparse
import logging
from pathlib import Path

# 🛡️ SAFETY WHITELIST: These patterns or filenames will NEVER be deleted
WHITELIST = [
    "manage.py",
    "requirements.txt",
    "risk_model.pkl",
    "claims_dataset.csv",
    ".gitignore",
    "README.md",
    "db.sqlite3",
    "media",
    "static",
    "cleanup_project.py",
    "cleanup.log"
]

# 🧹 TARGETS: Folders and File extensions to clean
TARGET_FOLDERS = [
    "__pycache__",
    "venv",
    "env",
    ".vscode",
    ".idea",
    "node_modules",
    "tmp",
    "temp",
    ".pytest_cache"
]

TARGET_EXTENSIONS = [
    ".pyc",
    ".pyo",
    ".log",
    ".DS_Store",
    "Thumbs.db",
    ".bak",
    ".swp"
]

def setup_logging():
    """Configures logging to both console and cleanup.log."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler("cleanup.log"),
            logging.StreamHandler()
        ]
    )

def cleanup_project():
    """
    Enhanced Project Cleanup with argparse and dry-run protection.
    """
    parser = argparse.ArgumentParser(description="Insurance System Project Cleanup Utility")
    parser.add_argument("--dry-run", action="store_true", help="Preview cleanup actions without deleting")
    parser.add_argument("--execute", action="store_true", help="Perform actual cleanup of junk files")
    
    args = parser.parse_args()

    # 🔐 SAFETY CHECK: Ensure a mode is specified
    if not (args.dry_run or args.execute):
        print("\n" + "!"*50)
        print("⚠️  SAFETY ALERT: Please specify a cleanup mode.")
        print("💡 Use --dry-run to preview or --execute to perform cleanup.")
        print("!"*50 + "\n")
        parser.print_help()
        return

    setup_logging()
    project_root = Path(__file__).parent.parent.resolve()
    
    mode_label = "DRY RUN MODE" if args.dry_run else "EXECUTION MODE"
    logging.info(f"Starting Project Cleanup in {mode_label} at: {project_root}")

    total_size_cleaned = 0
    deleted_count = 0

    # 1. Recursive Scan
    for path in list(project_root.rglob("*")):
        # Skip whitelisted items
        if any(w in str(path) for w in WHITELIST):
            continue

        # Check Folders
        if path.is_dir() and path.name in TARGET_FOLDERS:
            try:
                size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                total_size_cleaned += size
                rel_path = path.relative_to(project_root)

                if args.execute:
                    shutil.rmtree(path)
                    logging.info(f"[DELETED] Folder: {rel_path} ({size/1024:.1f} KB)")
                else:
                    logging.info(f"[DRY RUN] Would delete Folder: {rel_path} ({size/1024:.1f} KB)")
                
                deleted_count += 1
            except Exception as e:
                logging.error(f"Error processing folder {path}: {e}")

        # Check Files
        elif path.is_file() and (path.suffix in TARGET_EXTENSIONS or path.name in TARGET_EXTENSIONS):
            try:
                size = path.stat().st_size
                total_size_cleaned += size
                rel_path = path.relative_to(project_root)

                if args.execute:
                    path.unlink()
                    logging.info(f"[DELETED] File: {rel_path} ({size/1024:.1f} KB)")
                else:
                    logging.info(f"[DRY RUN] Would remove File: {rel_path} ({size/1024:.1f} KB)")
                
                deleted_count += 1
            except Exception as e:
                logging.error(f"Error processing file {path}: {e}")

    # 2. Results
    print("\n" + "="*50)
    final_status = "PREVIEW COMPLETE" if args.dry_run else "CLEANUP COMPLETE"
    logging.info(f"{final_status}: Found/Processed {deleted_count} items.")
    logging.info(f"Total space optimized: {total_size_cleaned / (1024 * 1024):.4f} MB")
    print("="*50 + "\n")

if __name__ == "__main__":
    cleanup_project()
