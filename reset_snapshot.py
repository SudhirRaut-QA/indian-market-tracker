import json
with open('data/snapshots/last_snapshot.json', 'r') as f:
    snap = json.load(f)

print(f"Before clearing: {len(snap.get('corporate_actions', []))}")
snap['corporate_actions'] = []
    
with open('data/snapshots/last_snapshot.json', 'w') as f:
    json.dump(snap, f, indent=4)
print("Cleared snapshot corporate actions.")
