import urllib.request
import json

try:
    url = "http://127.0.0.1:8000/api/banque/rapprochement-breakdown?year=2025"
    req = urllib.request.Request(url, headers={'Accept': 'application/json'})
    with urllib.request.urlopen(req) as response:
        res = json.loads(response.read().decode())
        print("Keys returned:", list(res.keys()))
        if "banques" in res:
            print("banques data:", res["banques"])
        else:
            print("No banques key!")
except Exception as e:
    print("Error:", e)
