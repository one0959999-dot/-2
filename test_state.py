import json, sqlite3
conn=sqlite3.connect('users.db')
c=conn.cursor()
c.execute('SELECT state_json FROM bot_states WHERE user_id=1')
row=c.fetchone()
if row and row[0]:
    state = json.loads(row[0])
    print(f"cores: {len(state.get('cores', []))}")
    print(f"satellites: {len(state.get('satellites', {}))}")
    print(f"satellite_info: {len(state.get('satellite_info', []))}")
    print(f"last_screen_month: {state.get('last_screen_month')}")
else:
    print("NO STATE")
