"""Tiny Maximo REST client used by the demo scripts.

Set MAXIMO_URL (for example https://manage.example.com/maximo) and either MAXIMO_APIKEY or MAXIMO_USER + MAXIMO_PASSWORD.
"""
import base64, json, os, ssl, urllib.error, urllib.parse, urllib.request

BASE = os.environ.get("MAXIMO_URL", "http://localhost:9080/maximo").rstrip("/") + "/api"
HEAD = {"Accept": "application/json", "Content-Type": "application/json"}
if os.environ.get("MAXIMO_APIKEY"):
    HEAD["apikey"] = os.environ["MAXIMO_APIKEY"]
else:
    cred = "%s:%s" % (os.environ.get("MAXIMO_USER", "maxadmin"), os.environ.get("MAXIMO_PASSWORD", ""))
    HEAD["Authorization"] = "Basic " + base64.b64encode(cred.encode()).decode()
CTX = ssl.create_default_context()
if os.environ.get("MAXIMO_INSECURE") == "1":   # self-signed lab certificates only
    CTX = ssl._create_unverified_context()


def call(method, path, body=None, headers=None):
    h = dict(HEAD, **(headers or {}))
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        t = e.read().decode()
        try:
            return e.code, json.loads(t)
        except ValueError:
            return e.code, {"raw": t[:400]}


def get(path):
    return call("GET", urllib.parse.quote(path, safe="/?&=,.:*{}%_-"))


def create(os_name, body, select="*"):
    return call("POST", f"/os/{os_name}?lean=1", body, {"properties": select})


def update(href, body, select="*"):
    path = "/os/" + href.split("/os/", 1)[-1]
    return call("POST", path + ("&" if "?" in path else "?") + "lean=1", body,
                {"x-method-override": "PATCH", "patchtype": "MERGE", "properties": select})
