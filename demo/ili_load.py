"""Lab 3: load an ILI vendor feature listing (CSV) into an assessment over REST, then read the result.
Every REST call is recorded in api_samples.json for the guide.

    python ili_load.py PIM-1004 ili_PL24-S02_2026.csv
"""
import csv, json, os, sys
import mx  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "api_samples.json")
LOG = json.load(open(LOG_PATH)) if os.path.exists(LOG_PATH) else []


def rec(title, method, path, body, headers, st, resp):
    LOG[:] = [x for x in LOG if x["title"] != title]
    LOG.append(dict(title=title, method=method, path=path, headers=headers, body=body, status=st, response=resp))
    print(title, st)


def num(v):
    return float(v) if v not in ("", None) else None


def rows(path):
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8")):
        f = {"featurenum": r["feature"], "kp": num(r["kp_km"]), "clock": r["clock"], "ftype": r["type"],
             "surface": r["surface"], "depthpct": num(r["depth_pct_wt"]), "length": num(r["length_mm"]),
             "width": num(r["width_mm"]), "dentpct": num(r["dent_pct_od"]), "prevdepthpct": num(r["prev_depth_pct_wt"]),
             "siteid": "BEDFORD", "orgid": "EAGLENA"}
        out.append({k: v for k, v in f.items() if v is not None})
    return out


if __name__ == "__main__":
    assess, csvfile = sys.argv[1], sys.argv[2]
    st, r = mx.get(f'/os/mxpimassess?lean=1&oslc.where=assessnum="{assess}"&oslc.select=assessnum')
    href = r["member"][0]["href"]
    feats = rows(os.path.join(HERE, csvfile))
    body = {"pimanom": feats}
    sel = ("assessnum,numanom,numimmed,numsched,nummon,maxerf,minpfratio,minlife,pofcat,driver,interact,riskcell,risk,"
           "tableint,intervalbasis,nextassessdate")
    st, resp = mx.update(href, body, sel)
    rec("Load the ILI feature listing", "POST", "/maximo/api/os/mxpimassess/" + href.split("/")[-1] + "?lean=1",
        {"pimanom": feats[:2] + ["... %d more features" % (len(feats) - 2)]},
        {"x-method-override": "PATCH", "patchtype": "MERGE", "properties": sel}, st, resp)
    path = ('/os/mxpimassess/' + href.split("/")[-1] + '?lean=1&oslc.select=assessnum,pimanom{featurenum,kp,ftype,'
            'depthpct,length,growth,pf,erf,pfratio,response,remlife,duedate}')
    st, resp = mx.get(path)
    feats_out = sorted(resp.get("pimanom", []), key=lambda x: -x.get("erf", 0))
    rec("Read the evaluated features", "GET", "/maximo/api" + path.split("?")[0] + "?lean=1&oslc.select=...", None, {},
        st, dict(assessnum=resp.get("assessnum"), pimanom=feats_out[:3]))
    json.dump(LOG, open(LOG_PATH, "w"), indent=1)
    for f in feats_out:
        print(f)
