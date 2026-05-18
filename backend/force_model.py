import sqlite3
import os

b = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "JustHireMe")
db_path = os.path.join(b, "crm.db")

conn = sqlite3.connect(db_path)
# Use a high-end, reliable model
conn.execute("INSERT OR REPLACE INTO settings(key, val) VALUES(?, ?)",
             ("nvidia_model", "nvidia/llama-3.1-nemotron-70b-instruct"))
conn.commit()
conn.close()

print("Successfully forced model to nvidia/llama-3.1-nemotron-70b-instruct")
