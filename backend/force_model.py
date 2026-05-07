import sqlite3
import os
import sys

def _data_dir():
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        return os.path.join(base, "JustHireMe")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"), "Library", "Application Support", "JustHireMe")
    base = os.environ.get("XDG_DATA_HOME", os.path.join(os.path.expanduser("~"), ".local", "share"))
    return os.path.join(base, "justhireme")

b = _data_dir()
db_path = os.path.join(b, "crm.db")

conn = sqlite3.connect(db_path)
# Use a high-end, reliable model
conn.execute("INSERT OR REPLACE INTO settings(key, val) VALUES(?, ?)", 
             ("nvidia_model", "nvidia/llama-3.1-nemotron-70b-instruct"))
conn.commit()
conn.close()

print("Successfully forced model to nvidia/llama-3.1-nemotron-70b-instruct")
