import sqlite3
import time

DB_FILE = "../db/dev.db"
POLL_INTERVAL = 10  # check every 10 seconds

def fetch_new_incidents(conn, last_seen_id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM incidents WHERE id > ? ORDER BY id ASC", (last_seen_id,))
    rows = cursor.fetchall()
    return rows

def main():
    conn = sqlite3.connect(DB_FILE)
    last_seen_id = 0  # start from the beginning (change if you only want new ones)

    print("🔎 Watching for new incidents... (Ctrl+C to stop)")

    while True:
        new_incidents = fetch_new_incidents(conn, last_seen_id)
        if new_incidents:
            for row in new_incidents:
                print("🚨 New Incident:", row)
                last_seen_id = row[0]  # update last seen ID
                incident = row[5] # payload json
                # Feed incident to agent
                
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
