

# ---- Maximo glue: read the assessment, run the model above, write the results ----------------------------
# Runs before every save of PIMASSESS (object launch point) and from Select Action > Recalculate Integrity.
from psdi.mbo import MboConstants
from java.util import Date, Calendar

F = MboConstants.NOACCESSCHECK | MboConstants.NOVALIDATION_AND_NOACTION
YEAR_MS = 365.25 * 24 * 3600 * 1000.0
METHOD = {"EXTCORR": "High-resolution MFL in-line inspection (or ECDA where unpiggable)",
          "INTCORR": "MFL in-line inspection plus ICDA at low points and water drop-out sites",
          "SCC": "EMAT crack-detection ILI or SCCDA digs at susceptible sites",
          "MFG": "Hydrostatic test to 1.25 x MAOP (manufacturing defects)",
          "CONSTR": "Geometry/deformation ILI and girth-weld review",
          "EQUIP": "Station equipment inspection (valves, regulators, relief)",
          "TPD": "Increased patrol, depth-of-cover survey, one-call compliance check",
          "INCOPS": "Procedure review, operator qualification and overpressure protection check",
          "WEATHER": "Geohazard survey and IMU/strain ILI at crossings"}
FTYPE_TXT = {"METALLOSS": "metal loss", "DENT": "dent", "DENTML": "dent with metal loss", "CRACK": "crack-like"}


def years(d1, d2):
    return (d2.getTime() - d1.getTime()) / YEAR_MS


def add_years(d, y):
    cal = Calendar.getInstance()
    cal.setTime(d)
    cal.add(Calendar.DAY_OF_YEAR, int(round(y * 365.25)))
    return cal.getTime()


def setv(o, attr, val):
    if val is None:
        o.setValueNull(attr, F)
    else:
        o.setValue(attr, val, F)


# Approved and superseded assessments are frozen records: the approved basis stays as approved.
_st = mbo.getString("STATUS")
_frozen = _st == "SUPERSEDED" or (_st == "APPR" and not mbo.isModified("STATUS"))
if _frozen and launchPoint == "PIMCALC":
    service.error("pim", "frozen")
if _frozen and not mbo.toBeAdded():
    # integrations write without access checks: refuse changed inputs on a frozen record (the PIM scripts only
    # write work order numbers and the status, which stay allowed)
    _bad = [x for x in FROZEN_INPUTS if mbo.isModified(x)]
    for _rel, _attrs in CHILD_INPUTS:
        _set = mbo.getMboSet(_rel)
        _r = _set.moveFirst()
        while _r is not None:
            if _r.toBeAdded() or _r.toBeDeleted() or [x for x in _attrs if _r.isModified(x)]:
                _bad.append(_rel)
            _r = _set.moveNext()
    if _bad:
        service.error("pim", "frozenedit", [mbo.getString("ASSESSNUM")])


def _run():
    a = mbo
    if a.isNull("ASSESSDATE"):
        setv(a, "ASSESSDATE", Date())
    notes = []
    cls = a.getString("CLASSLOC") or "1"
    df = DESIGN_F.get(cls, 0.72)
    setv(a, "DESIGNF", df)
    if a.isNull("SAFETYF"):
        setv(a, "SAFETYF", df)
    seg = dict(od=a.getDouble("OD"), wt=a.getDouble("WT"), smys=a.getDouble("SMYS"),
               maop=a.getDouble("MAOP") / 10.0, sf=a.getDouble("SAFETYF") or df)
    if seg["od"] <= 0 or seg["wt"] <= 0 or seg["smys"] <= 0 or seg["maop"] <= 0:
        setv(a, "CALCNOTE", "Enter diameter, wall thickness, SMYS and MAOP to calculate the segment.")
        return
    ili = a.getDate("ILIDATE")
    rep = a.getDate("ILIREPORTDATE") or ili
    prev = a.getDate("PREVILIDATE")
    between = years(prev, ili) if (prev is not None and ili is not None) else 0.0
    cgr = a.getDouble("DEFAULTCGR")
    hoop = hoop_pct(seg["maop"], seg["od"], seg["wt"], seg["smys"])
    setv(a, "HOOPPCT", round(hoop, 1))
    setv(a, "PIRM", round(pir(seg["od"], seg["maop"]), 1))

    # 1. every open anomaly: growth, Modified B31G failure pressure, ERF, B31.8S response, remaining life
    n = dict(IMMEDIATE=0, SCHEDULED=0, MONITORED=0, REPAIRED=0)
    surf = dict((k, dict(n=0, i=0, s=0, life=99.0)) for k in ("EXT", "INT", "TPD", "SCC"))
    max_erf, min_ratio, min_life, worst = 0.0, 99.0, 99.0, ""
    an = a.getMboSet("ANOMALIES")
    r = an.moveFirst()
    while r is not None:
        if r.toBeDeleted():
            r = an.moveNext()
            continue
        if r.getString("FSTATUS") == "REPAIRED":
            n["REPAIRED"] += 1
            setv(r, "RESPONSE", "REPAIRED")
            for k in ("REMLIFE", "DUEDATE"):
                setv(r, k, None)
            r = an.moveNext()
            continue
        ftype = r.getString("FTYPE") or "METALLOSS"
        g = 0.0 if ftype in ("DENT", "CRACK") else growth_rate(
            r.getDouble("DEPTHPCT"), None if r.isNull("PREVDEPTHPCT") else r.getDouble("PREVDEPTHPCT"),
            seg["wt"], between, cgr)
        f = dict(ftype=ftype, depthpct=r.getDouble("DEPTHPCT"),
                 length=r.getDouble("LENGTH"), dentpct=r.getDouble("DENTPCT"), growth=g)
        e = feature_eval(f, seg, 0.0)
        life = remaining_life(f, seg) if e["response"] == "MONITORED" else 0.0
        resp = e["response"]
        n[resp] += 1
        # metal loss scores the corrosion threat of its surface; dents score mechanical damage, cracks SCC
        ft = f["ftype"]
        key = {"DENT": "TPD", "CRACK": "SCC"}.get(ft) or ("INT" if r.getString("SURFACE") == "INT" else "EXT")
        if ft == "DENTML":
            mech = surf["TPD"]
            mech["n"] += 1
            mech["i"] += resp == "IMMEDIATE"
        sk = surf[key]
        sk["n"] += 1
        if sk is not None:
            sk["i"] += resp == "IMMEDIATE"
            sk["s"] += resp == "SCHEDULED"
            if resp == "MONITORED":
                sk["life"] = min(sk["life"], life)
        if e["erf"] > max_erf:
            max_erf, worst = e["erf"], r.getString("FEATURENUM")
        if resp == "MONITORED":
            min_ratio = min(min_ratio, e["ratio"])
            min_life = min(min_life, life)
        if resp == "IMMEDIATE":
            due = rep
        elif resp == "SCHEDULED":
            due = add_years(rep, 1.0) if rep is not None else None
        else:
            due = add_years(ili, life) if (ili is not None and life < 99.0) else None
        for k, v in (("GROWTH", round(g, 3)), ("PF", round(e["pf"] * 10.0, 1)), ("PSAFE", round(e["psafe"] * 10.0, 1)),
                     ("ERF", round(e["erf"], 3)), ("PFRATIO", round(e["ratio"], 3)), ("RESPONSE", resp),
                     ("REMLIFE", round(life, 1) if life < 99.0 else None), ("DUEDATE", due)):
            setv(r, k, v)
        r = an.moveNext()
    tot = n["IMMEDIATE"] + n["SCHEDULED"] + n["MONITORED"]
    for k, v in (("NUMANOM", tot + n["REPAIRED"]), ("NUMIMMED", n["IMMEDIATE"]), ("NUMSCHED", n["SCHEDULED"]),
                 ("NUMMON", n["MONITORED"]), ("NUMREPAIRED", n["REPAIRED"]), ("MAXERF", round(max_erf, 3)),
                 ("MINPFRATIO", round(min_ratio, 3) if min_ratio < 99 else None),
                 ("MINLIFE", round(min_life, 1) if min_life < 99.0 else None)):
        setv(a, k, v)
    if ili is None or not (tot + n["REPAIRED"]):
        notes.append("No ILI feature listing yet: corrosion threats scored from susceptibility only.")

    # 2. threats: ILI metal loss scores the corrosion threats (measured condition replaces assumed susceptibility,
    #    at least 2 while open features are growing); ILI dents and cracks raise mechanical damage and SCC
    ILI_KEY = {"EXTCORR": "EXT", "INTCORR": "INT", "TPD": "TPD", "SCC": "SCC"}

    listed = ili is not None and (tot + n["REPAIRED"]) > 0   # an ILI listing has been loaded

    def measured(k):
        sv = surf[ILI_KEY[k]]
        if not listed or not sv["n"]:
            return None
        return max(ili_score(sv["i"], sv["s"], sv["life"]), 2)

    scores, rows = {}, []
    th = a.getMboSet("THREATS")
    t = th.moveFirst()
    while t is not None:
        if not t.toBeDeleted():
            k = t.getString("THREAT")
            s = threat_score(t.getString("SUSCEPT"), t.getBoolean("MITIGATED"))
            m = measured(k) if k in ILI_KEY else None
            if m is not None:
                s = m if k in ILI_THREATS else max(s, m)
            elif k in ILI_THREATS and listed:
                s = 1   # ILI ran and found no metal loss on that surface
            scores[k] = max(scores.get(k, 0), s)
            setv(t, "SCORE", s)
            setv(t, "RECMETHOD", METHOD.get(k, "")[:100])
            rows.append(t)
        t = th.moveNext()
    for k in ILI_KEY:   # ILI findings count even when nobody listed that threat
        m = measured(k)
        if k not in scores and m is not None:
            scores[k] = m
            notes.append("ILI findings scored %s %d (no threat row)." % (k, m))
    pofcat, driver, inter = pof_category(scores)
    setv(a, "POFCAT", pofcat)
    setv(a, "DRIVER", driver or None)
    setv(a, "INTERACT", ", ".join(inter) if len(inter) >= 2 else None)

    # 3. consequence: people inside the potential impact radius, environment, cost
    cp = cof_people(a.getInt("BUILDINGS"), a.getBoolean("IDSITE"))
    ce = {"HIGH": "D", "MEDIUM": "C"}.get(a.getString("ENVSENS"), "A")
    fin = a.getDouble("REPAIRCOST") + a.getDouble("OUTAGEDAYS") * a.getDouble("LOSSPERDAY") + a.getDouble("ENVCOST")
    cf = cof_category(fin, COF_FIN)
    cof = max(cp, ce, cf)
    for k, v in (("COFPEOPLE", cp), ("COFENV", ce), ("FINCOST", round(fin, 2)), ("COFFIN", cf), ("COFCAT", cof),
                 ("RISKCELL", "%d%s" % (pofcat, cof)), ("RISK", risk_level(pofcat, cof))):
        setv(a, k, v)

    # 4. reassessment interval: B31.8S Table 3, the maximum interval (HCA or not), half the shortest remaining life
    tab = table3_interval(hoop, min_ratio) if min_ratio < 99 else (20.0 if hoop < 30 else (15.0 if hoop < 50 else 10.0))
    setv(a, "TABLEINT", tab)
    hca = a.getBoolean("HCA")
    cap = a.getDouble("HCAMAX") if hca else a.getDouble("MAXINTERVAL")
    cands = [(cap, "%s maximum interval %.0f y" % ("HCA" if hca else "company", cap))]
    if tab > 0:
        cands.append((tab, "B31.8S Table 3 (%.0f %% SMYS, Pf/MAOP %.2f)" % (hoop, min_ratio)))
    else:
        notes.append("Remaining features are below every B31.8S Table 3 row: remediate before setting an interval.")
    if min_life < 99:
        cands.append((min_life / 2.0, "half the shortest remaining life (%.1f y)" % min_life))
    yrs, why = sorted(cands, key=lambda c: c[0])[0]
    base = ili or a.getDate("ASSESSDATE")
    setv(a, "INTERVALBASIS", why[:100])
    setv(a, "NEXTASSESSDATE", add_years(base, max(yrs, 0.0)))
    setv(a, "ASSESSMETHOD", METHOD.get(driver, METHOD["EXTCORR"])[:100])

    note = ("Segment: OD %.0f mm, wt %.1f mm, SMYS %.0f MPa, MAOP %.1f bar -> hoop %.1f %% SMYS, class %s (F %.2f), "
            "PIR %.0f m. ILI: %d open features (%d immediate, %d scheduled, %d monitored), %d repaired; worst ERF %.3f (%s); "
            "monitored: min Pf/MAOP %s, shortest remaining life %s. Threat scores: %s -> PoF %d (driver %s%s). "
            "CoF people %s, environment %s, cost %.0f USD (%s) -> %s. Risk %d%s %s. Interval %.1f y (%s). %s"
            % (seg["od"], seg["wt"], seg["smys"], seg["maop"] * 10, hoop, cls, df, pir(seg["od"], seg["maop"]), tot,
               n["IMMEDIATE"], n["SCHEDULED"], n["MONITORED"], n["REPAIRED"], max_erf, worst or "-",
               ("%.2f" % min_ratio) if min_ratio < 99 else "-",
               ("%.1f y" % min_life) if min_life < 99 else "none within 30 y",
               ", ".join("%s %d" % (k, v) for k, v in sorted(scores.items(), key=lambda kv: -kv[1])), pofcat,
               driver or "-", (", interacting " + "+".join(inter)) if len(inter) >= 2 else "", cp, ce, fin, cf, cof,
               pofcat, cof, risk_level(pofcat, cof), yrs, why, " ".join(notes)))
    setv(a, "CALCNOTE", note[:1000])


if not _frozen:
    _run()
