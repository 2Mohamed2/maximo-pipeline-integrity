"""Lab 5: the immediate digs are done, F-0503 is repaired in the same campaign (opportunistic: it alone sets the
2.2-year interval), a new assessment records the repairs, its approval supersedes the first one, and the old
reassessment work order is cancelled. Every REST call is recorded in api_samples.json for the guide.

    python lab6_reassess.py PIM-1008
"""
import json, os, sys
import mx  # noqa: E402
from ili_load import rec, LOG, LOG_PATH  # noqa: E402

OLD = sys.argv[1]
SITE, ORG = "BEDFORD", "EAGLENA"
REPAIRS = {"F-0519": ("2026-11-06T00:00:00", "Type B pressure-containing sleeve"),
           "F-0634": ("2026-11-12T00:00:00", "Type B sleeve, epoxy-filled (dent)"),
           "F-0503": ("2026-11-13T00:00:00", "Composite wrap (opportunistic)")}
KEEP = ("pipeline", "kpstart", "kpend", "installdate", "coating", "classloc", "hca", "od", "wt", "grade", "smys", "maop",
        "ilidate", "ilireportdate", "ilitool", "previlidate", "defaultcgr", "buildings", "idsite", "envsens",
        "repaircost", "outagedays", "lossperday", "envcost", "maxinterval", "hcamax")


def wo_href(wonum):
    st, r = mx.get(f'/os/mxapiwodetail?lean=1&oslc.where=wonum="{wonum}" and siteid="{SITE}"&oslc.select=wonum')
    return r["member"][0]["href"]


def status(wonum, new, memo):
    href = wo_href(wonum)
    path = "/os/" + href.split("/os/")[1] + "?lean=1&action=wsmethod:changeStatus"
    body = {"status": new, "memo": memo}
    st, resp = mx.call("POST", path, body, {"x-method-override": "PATCH"})
    return st, resp, "/maximo/api/os/mxapiwodetail/" + href.split("/")[-1] + "?lean=1&action=wsmethod:changeStatus", body


# 1. the opportunistic dig for F-0503
body = {"siteid": SITE, "orgid": ORG, "assetnum": "PL24-S02", "worktype": "DIG", "wopriority": 2,
        "description": "Dig F-0503 KP 23.118: metal loss 41% wt, opportunistic repair",
        "description_longdescription": "Monitored feature with the shortest remaining life (4.4 y, growth 0.222 mm/y). "
        "Repaired in the November 2026 campaign so the next ILI is not set at 2.2 years."}
st, r = mx.call("GET", "/os/mxapiwodetail?lean=1&oslc.where=" + mx.urllib.parse.quote('description="%s"' % body["description"])
                + "&oslc.select=wonum")
if r.get("member"):
    opp = r["member"][0]["wonum"]
else:
    st, r = mx.create("mxapiwodetail", body, "wonum,description,worktype,status")
    rec("Create the opportunistic dig work order", "POST", "/maximo/api/os/mxapiwodetail?lean=1", body,
        {"properties": "wonum,description,worktype,status"}, st, r)
    opp = r["wonum"]

# 2. the immediate digs and the opportunistic one are complete
st, r = mx.get(f'/os/mxpimassess?lean=1&oslc.where=assessnum="{OLD}"&oslc.select=*,pimthreat{{*}},pimanom{{*}}')
old = r["member"][0]
digs = {f["featurenum"]: f.get("wonum") for f in old["pimanom"]}
digs["F-0503"] = opp
for feat in REPAIRS:
    st, w = mx.get(f'/os/mxapiwodetail?lean=1&oslc.where=wonum="{digs[feat]}"&oslc.select=status')
    if w["member"][0]["status"] == "COMP":
        continue
    st, resp, path, b = status(digs[feat], "COMP", ("Repaired: " + REPAIRS[feat][1])[:50])
    if feat == "F-0519":
        rec("Complete a dig work order", "POST", path, b, {"x-method-override": "PATCH"}, st, resp)
    print("complete", digs[feat], st, "" if st < 300 else resp)

# 3. the new assessment: same segment and ILI, with the three repairs recorded on their features
new = {k: old[k] for k in KEEP if k in old}
new.update(assetnum="PL24-S02", siteid=SITE, orgid=ORG, assessor="WILSON", assessdate="2026-11-19T00:00:00",
           description="PL24-S02 village section - after Nov 2026 repairs")
new["pimthreat"] = [dict(threat=t["threat"], suscept=t["suscept"], mitigated=t.get("mitigated", False),
                         notes=t.get("notes", ""), siteid=SITE, orgid=ORG) for t in old["pimthreat"]]
feats = []
for f in old["pimanom"]:
    g = {k: f[k] for k in ("featurenum", "kp", "clock", "ftype", "surface", "depthpct", "length", "width", "dentpct",
                           "prevdepthpct") if k in f}
    g.update(siteid=SITE, orgid=ORG)
    if f["featurenum"] in REPAIRS:
        g.update(fstatus="REPAIRED", repairdate=REPAIRS[f["featurenum"]][0], repairtype=REPAIRS[f["featurenum"]][1],
                 wonum=digs[f["featurenum"]])   # the dig that repaired it
    feats.append(g)
new["pimanom"] = feats
sel = ("assessnum,status,numanom,numimmed,numsched,nummon,numrepaired,maxerf,minlife,pofcat,driver,interact,riskcell,"
       "risk,tableint,intervalbasis,nextassessdate")
st, r = mx.get('/os/mxpimassess?lean=1&oslc.where=description="%s"&oslc.select=assessnum' % new["description"])
if r.get("member"):
    num, href = r["member"][0]["assessnum"], r["member"][0]["href"]
else:
    st, resp = mx.create("mxpimassess", new, sel)
    shown = dict(new, pimanom=[x for x in feats if x["featurenum"] in REPAIRS][:1] + ["... 11 more features"],
                 pimthreat=new["pimthreat"][:1] + ["... 4 more threats"])
    rec("Create the post-repair assessment", "POST", "/maximo/api/os/mxpimassess?lean=1", shown, {"properties": sel}, st, resp)
    if st >= 300: print(resp); sys.exit(1)
    num, href = resp["assessnum"], resp["href"]
    print("new", st, resp)

# 4. approve it: PIM.APPROVE supersedes PIM-1008; then cancel PIM-1008's reassessment work order
st, resp = mx.update(href, {"status": "APPR"}, "assessnum,status")
rec("Approve the post-repair assessment", "POST", "/maximo/api/os/mxpimassess/" + href.split("/")[-1] + "?lean=1",
    {"status": "APPR"}, {"x-method-override": "PATCH", "patchtype": "MERGE", "properties": "assessnum,status"}, st, resp)
if old.get("wonum"):
    st, resp, path, b = status(old["wonum"], "CAN", ("Superseded by %s" % num))
    print("cancel", old["wonum"], st, "" if st < 300 else resp)

# 5. read the pipeline: every assessment of PL-24, newest first
path = ('/os/mxpimassess?lean=1&oslc.select=assessnum,assetnum,status,numimmed,numsched,riskcell,risk,nextassessdate,'
        'intervalbasis,wonum&oslc.orderBy=-assessnum&oslc.pageSize=10')
st, resp = mx.get(path)
rec("Read the pipeline's assessments", "GET", "/maximo/api" + path, None, {}, st, resp)
json.dump(LOG, open(LOG_PATH, "w"), indent=1)
for m in resp["member"]:
    print({k: v for k, v in m.items() if not k.endswith(("href", "_rowstamp", "_description"))})
