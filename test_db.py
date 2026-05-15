import sqlite3
import json

conn = sqlite3.connect('/home/ubuntu/lassi_bot/users.db')
c = conn.cursor()

# Get all users
users = c.execute('SELECT id, username FROM users').fetchall()
print(f"Users: {users}")

# Get all bot_states
states = c.execute('SELECT user_id, last_updated FROM bot_states').fetchall()
print(f"States found for user_ids: {states}")

# Dump bot_state for user 1
row = c.execute('SELECT state_json FROM bot_states WHERE user_id=1').fetchone()
if row and row[0]:
    state = json.loads(row[0])
    print(f"User 1 State cores: {len(state.get('cores', []))}")
    print(f"User 1 State satellites: {len(state.get('satellites', {}))}")
else:
    print("NO STATE for User 1")

conn.close()
