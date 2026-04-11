import os
import sqlite3
import sys
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(r"d:\Projects\spam-detector\backend")
sys.path.append(str(BASE_DIR))

load_dotenv()

# DB 파일 경로 설정 (.env의 DB_DATA_DIR 우선 적용)
env_db_dir = os.getenv("DB_DATA_DIR")
if env_db_dir:
    DB_DIR = Path(env_db_dir).resolve()
else:
    DB_DIR = BASE_DIR / "data"

DB_PATH = DB_DIR / "signatures.db"

def migrate():
    print(f"Connecting to {DB_PATH} ...")
    if not DB_PATH.exists():
        print("signatures.db not found!")
        return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            
            # Check if columns exist
            cursor.execute("PRAGMA table_info(signatures)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'hit_count' not in columns:
                cursor.execute("ALTER TABLE signatures ADD COLUMN hit_count INTEGER DEFAULT 0")
                print("Added column 'hit_count'.")
            else:
                print("Column 'hit_count' already exists.")
                
            if 'last_hit' not in columns:
                cursor.execute("ALTER TABLE signatures ADD COLUMN last_hit TIMESTAMP")
                print("Added column 'last_hit'.")
            else:
                print("Column 'last_hit' already exists.")
                
            conn.commit()
            print("Migration completed successfully.")
            
    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate()
