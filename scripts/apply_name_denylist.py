"""Give functions whose recovered name collides with a host C runtime
declaration their sub_XXXXXXXX name back.

    python scripts/apply_name_denylist.py <functions.json> <denylist.txt>
"""
import json
import sys

funcs_path, deny_path = sys.argv[1], sys.argv[2]
deny = {l.strip() for l in open(deny_path) if l.strip() and not l.startswith("#")}
funcs = json.load(open(funcs_path))
n = 0
for f in funcs:
    if f.get("name") in deny:
        f["name"] = "sub_%08X" % int(f["start"], 16)
        n += 1
json.dump(funcs, open(funcs_path, "w"), indent=1)
print(f"name denylist: {n} function(s) renamed back")
