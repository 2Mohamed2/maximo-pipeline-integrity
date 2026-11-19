"""Demo data for the pipeline integrity guide: the PL-24 gas trunkline (parent asset) and its four segments,
plus (with --assess) three API-made assessments with their ILI features. PL24-S02's assessment is made in the UI.

    python seed.py            assets
    python seed.py --assess   also the three API-made assessments (S01, S03, S04)
"""
import os, sys
import mx  # noqa: E402

SITE, ORG = "BEDFORD", "EAGLENA"
ASSETS = [("PL-24", None, "PL-24 gas trunkline, 24 in, Station North to Station South (60.4 km)"),
          ("PL24-S01", "PL-24", "PL-24 segment 1, KP 0.0-18.5, desert, class 1"),
          ("PL24-S02", "PL-24", "PL-24 segment 2, KP 18.5-31.2, village and school, class 3 HCA"),
          ("PL24-S03", "PL-24", "PL-24 segment 3, KP 31.2-52.0, wadi crossing, class 1"),
          ("PL24-S04", "PL-24", "PL-24 segment 4, KP 52.0-60.4, approach to Station South, class 2")]

COMMON = dict(pipeline="PL-24 gas trunkline", installdate="1998-06-01T00:00:00", coating="Coal-tar enamel",
              od=610, grade="API 5L X60", smys=414, maop=70, assessdate="2026-11-19T00:00:00",
              ilidate="2026-09-14T00:00:00", ilireportdate="2026-10-26T00:00:00",
              ilitool="High-resolution MFL + caliper", previlidate="2019-03-11T00:00:00", defaultcgr=0.2,
              assessor="WILSON", maxinterval=10, hcamax=7)


def T(threat, susc, mit=False, notes=""):
    return dict(threat=threat, suscept=susc, mitigated=mit, notes=notes)


def ML(num, kp, clock, depth, length, prev=None, surf="EXT", ftype="METALLOSS", dent=None, width=None):
    f = dict(featurenum=num, kp=kp, clock=clock, ftype=ftype, surface=surf, depthpct=depth, length=length)
    if prev is not None:
        f["prevdepthpct"] = prev
    if dent is not None:
        f["dentpct"] = dent
    if width is not None:
        f["width"] = width
    return f


ASSESS = [
    dict(assetnum="PL24-S01", description="PL24-S01 desert section - 2026 ILI", kpstart=0, kpend=18.5, classloc="1",
         hca=False, wt=9.5, buildings=2, envsens="LOW", repaircost=250000, outagedays=0, lossperday=0, envcost=0,
         pimthreat=[T("EXTCORR", "MEDIUM", True, "Coal-tar enamel, CP surveys annual; 3 low readings 2025"),
                    T("INTCORR", "LOW", True, "Dry sales gas, dew point controlled"),
                    T("TPD", "LOW", False, "Remote, patrol monthly"), T("WEATHER", "LOW")],
         pimanom=[ML("F-0107", 3.412, "06:00", 31, 120, 26), ML("F-0158", 9.877, "05:15", 24, 80, 20),
                  ML("F-0203", 14.205, "07:30", 38, 95, 30), ML("F-0244", 17.660, "04:00", 19, 210)]),
    dict(assetnum="PL24-S03", description="PL24-S03 wadi crossing - 2026 ILI", kpstart=31.2, kpend=52.0,
         classloc="1", hca=False, wt=9.5, buildings=4, envsens="HIGH", repaircost=900000, outagedays=6,
         lossperday=120000, envcost=200000,
         pimthreat=[T("EXTCORR", "MEDIUM", True, "Coating disbondment at wadi banks"),
                    T("WEATHER", "HIGH", False, "Flash floods 2024; 40 m of exposed pipe at KP 38.6"),
                    T("TPD", "MEDIUM", False, "Quarry trucks cross at KP 44; no slabbing"),
                    T("INTCORR", "LOW", True)],
         pimanom=[ML("F-0702", 33.050, "06:30", 27, 140, 22), ML("F-0745", 38.604, "12:00", None, None, ftype="DENT", dent=6.8),
                  ML("F-0781", 44.118, "01:30", None, None, ftype="DENT", dent=3.0), ML("F-0815", 49.930, "05:45", 33, 70, 25)]),
    dict(assetnum="PL24-S04", description="PL24-S04 station approach - 2026 ILI", kpstart=52.0, kpend=60.4,
         classloc="2", hca=False, wt=10.3, buildings=14, envsens="MEDIUM", repaircost=400000, outagedays=2,
         lossperday=150000, envcost=50000,
         pimthreat=[T("INTCORR", "MEDIUM", False, "Liquid drop-out at the low point KP 57.2 before the slug catcher"),
                    T("EXTCORR", "LOW", True), T("EQUIP", "MEDIUM", False, "Pig trap door seal replaced twice"),
                    T("INCOPS", "LOW", True)],
         pimanom=[ML("F-0903", 57.190, "06:00", 39, 110, 25, surf="INT"), ML("F-0911", 57.240, "05:30", 31, 85, 20, surf="INT"),
                  ML("F-0940", 58.870, "07:15", 21, 60)]),
]


def assets():
    for num, parent, desc in ASSETS:
        st, r = mx.get(f'/os/mxapiasset?lean=1&oslc.where=assetnum="{num}" and siteid="{SITE}"&oslc.select=assetnum')
        if r.get("member"):
            print("asset exists", num); continue
        body = {"assetnum": num, "siteid": SITE, "orgid": ORG, "description": desc}
        if parent:
            body["parent"] = parent
        st, r = mx.create("mxapiasset", body, "assetnum")
        print("asset", num, st, "" if st < 300 else r)


def assessments():
    for a in ASSESS:
        st, r = mx.get(f'/os/mxpimassess?lean=1&oslc.where=assetnum="{a["assetnum"]}"&oslc.select=assessnum')
        if r.get("member"):
            print("assessment exists", a["assetnum"], r["member"][0]["assessnum"]); continue
        body = dict(COMMON, **a)
        body.update(siteid=SITE, orgid=ORG)
        for k in ("pimthreat", "pimanom"):
            body[k] = [dict({kk: vv for kk, vv in x.items() if vv is not None}, siteid=SITE, orgid=ORG) for x in body[k]]
        st, r = mx.create("mxpimassess", body, "assessnum,hooppct,pirm,numimmed,numsched,nummon,maxerf,minlife,"
                          "pofcat,driver,interact,cofcat,riskcell,risk,tableint,intervalbasis,nextassessdate")
        print("assessment", a["assetnum"], st, r)


if __name__ == "__main__":
    assets()
    if "--assess" in sys.argv:
        assessments()
