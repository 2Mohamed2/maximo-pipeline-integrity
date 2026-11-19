# Pipeline integrity calculation core, structured after ASME B31.8S (integrity management of gas pipelines)
# and ASME B31G (remaining strength of corroded pipelines, Modified B31G / 0.85dL method).
# Pure functions only: this text is embedded in the PIM.CALC automation script (Jython 2.7)
# and imported by the test harness (CPython 3), so keep it compatible with both.
import math

# ---- Published formulas and limits ------------------------------------------------------------------------
# VERIFY against your licensed copies of ASME B31.8S and B31G before production use; keep under change control.
FLOW_ADD = 69.0            # MPa: Modified B31G flow stress = SMYS + 69 MPa (10 ksi)
DEPTH_IMMEDIATE = 0.80     # B31.8S 7.2.1: metal loss deeper than 80 % of wall -> immediate response
PF_IMMEDIATE = 1.10        # B31.8S 7.2.1: predicted failure pressure below 1.1 x MAOP -> immediate response
DENT_SCHEDULED = 6.0       # B31.8S 7.2.2: plain dent deeper than 6 % of the diameter -> scheduled response
PIR_K = 0.099              # B31.8S 3.2 (SI): potential impact radius r = 0.099 * sqrt(d^2 * p), d mm, p MPa -> m
DESIGN_F = {"1": 0.72, "2": 0.60, "3": 0.50, "4": 0.40}   # ASME B31.8 design factor by class location
# B31.8S Table 3, time-dependent threats, ILI or pressure test: (hoop stress band lower limit in %SMYS,
# [(minimum predicted failure pressure ratio Pf/MAOP, interval in years), ...] longest interval first)
TABLE3 = ((50.0, ((1.39, 10.0), (1.25, 5.0))),
          (30.0, ((1.70, 15.0), (1.40, 10.0))),
          (0.0, ((2.20, 20.0), (2.00, 15.0), (1.65, 10.0))))

# ---- Company-configurable screening values (relative risk model, B31.8S 5.7 index approach) ---------------
SUSC_SCORE = {"HIGH": 4, "MEDIUM": 3, "LOW": 2, "NONE": 0}
COF_FIN = (1e4, 1e5, 1e6, 1e7)          # financial CoF category A..E upper limits (USD), same scale as the RBI module
RISK_LEVEL = ((4, "LOW"), (6, "MEDIUM"), (7, "MEDHIGH"), (10, "HIGH"))   # matrix score = PoF cat + CoF index
THREATS = ("EXTCORR", "INTCORR", "SCC", "MFG", "CONSTR", "EQUIP", "TPD", "INCOPS", "WEATHER")
ILI_THREATS = ("EXTCORR", "INTCORR")    # time-dependent metal-loss threats scored from the ILI results


def b31g_mod(od, wt, smys, depth_mm, length_mm):
    """Modified B31G (0.85dL) predicted failure pressure in MPa for one metal-loss feature."""
    if wt <= 0 or od <= 0:
        return 0.0
    dt = min(max(depth_mm / wt, 0.0), 0.999)
    z = length_mm ** 2 / (od * wt)
    if z <= 50.0:
        m = math.sqrt(1.0 + 0.6275 * z - 0.003375 * z * z)
    else:
        m = 0.032 * z + 3.3
    sflow = smys + FLOW_ADD
    sf = sflow * (1.0 - 0.85 * dt) / (1.0 - 0.85 * dt / m)
    return 2.0 * sf * wt / od


def hoop_pct(maop_mpa, od, wt, smys):
    """Hoop stress at MAOP as a percentage of SMYS (Barlow)."""
    return 100.0 * maop_mpa * od / (2.0 * wt * smys)


def pir(od, maop_mpa):
    """Potential impact radius (m)."""
    return PIR_K * math.sqrt(od * od * maop_mpa)


def feature_eval(f, seg, years_since_ili=0.0):
    """Evaluate one anomaly at a time point years_since_ili after the ILI run.
    f: dict(ftype, depthpct, length, dentpct, growth) ; seg: dict(od, wt, smys, maop (MPa), sf)
    Returns dict(depth, pf, psafe, erf, ratio, response)."""
    depth = f["depthpct"] / 100.0 * seg["wt"] + f.get("growth", 0.0) * years_since_ili
    ftype = f["ftype"]
    if ftype in ("METALLOSS", "DENTML"):
        pf = b31g_mod(seg["od"], seg["wt"], seg["smys"], depth, f["length"])
    else:   # dents and cracks: the pipe body is not thinned; failure pressure of the intact pipe
        pf = 2.0 * (seg["smys"] + FLOW_ADD) * seg["wt"] / seg["od"]
    psafe = pf * seg["sf"]
    erf = seg["maop"] / psafe if psafe > 0 else 99.0
    ratio = pf / seg["maop"] if seg["maop"] > 0 else 99.0
    if ftype in ("DENTML", "CRACK") or depth / seg["wt"] > DEPTH_IMMEDIATE or ratio < PF_IMMEDIATE:
        resp = "IMMEDIATE"
    elif erf >= 1.0 or (ftype == "DENT" and f.get("dentpct", 0.0) > DENT_SCHEDULED):
        resp = "SCHEDULED"
    else:
        resp = "MONITORED"
    return dict(depth=depth, pf=pf, psafe=psafe, erf=erf, ratio=ratio, response=resp)


def remaining_life(f, seg, horizon=30.0):
    """Years from the ILI run until a monitored metal-loss feature needs repair (ERF reaches 1 or it turns
    immediate), with its depth growing at f['growth'] mm/y. 99 when it never does within the horizon."""
    if f["ftype"] != "METALLOSS" or f.get("growth", 0.0) <= 0:
        return 99.0
    t = 0.0
    while t <= horizon:
        if feature_eval(f, seg, t)["response"] != "MONITORED":
            return t
        t += 1.0 / 12.0
    return 99.0


def growth_rate(depthpct, prevdepthpct, wt, years_between, default):
    """Depth growth (mm/y): ILI-to-ILI matched features use their own depth change, others the segment default."""
    if prevdepthpct is not None and prevdepthpct > 0 and years_between > 0 and depthpct >= prevdepthpct:
        return (depthpct - prevdepthpct) / 100.0 * wt / years_between
    return default


def table3_interval(hoop, ratio):
    """B31.8S Table 3 interval (years) for the hoop stress band and the worst remaining predicted failure
    pressure ratio. 0 means the ratio is below every row: the features must be remediated first."""
    for lower, rows in TABLE3:
        if hoop >= lower:
            for r, years in rows:
                if ratio >= r:
                    return years
            return 0.0
    return 0.0


def threat_score(susc, mitigated):
    s = SUSC_SCORE.get(susc, 0)
    if mitigated and s > 1:
        s -= 1
    return s


def ili_score(n_immediate, n_scheduled, min_life):
    """Likelihood (1-5) of the metal-loss threats from the ILI results."""
    if n_immediate:
        return 5
    if n_scheduled or min_life < 2.0:
        return 4
    if min_life < 5.0:
        return 3
    if min_life < 10.0:
        return 2
    return 1


def pof_category(scores):
    """scores: dict threat -> 0..5. PoF category = governing threat, +1 when two or more threats score 3 or
    more (B31.8S 2.2 interacting threats, e.g. external corrosion with third-party damage). Returns (cat, driver, interacting)."""
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], THREATS.index(kv[0]) if kv[0] in THREATS else 99))
    if not ranked or ranked[0][1] <= 0:
        return 1, "", []
    top, driver = ranked[0][1], ranked[0][0]
    inter = [k for k, v in ranked if v >= 3]
    cat = min(5, top + (1 if len(inter) >= 2 else 0))
    return max(cat, 1), driver, inter


def cof_people(buildings, identified_site):
    if identified_site:
        return "E"
    if buildings >= 20:
        return "D"
    if buildings >= 10:
        return "C"
    if buildings >= 1:
        return "B"
    return "A"


def cof_category(value, limits):
    for i, lim in enumerate(limits):
        if value <= lim:
            return "ABCDE"[i]
    return "E"


def risk_level(pofcat, cofcat):
    score = pofcat + "ABCDE".index(cofcat) + 1
    for lim, lvl in RISK_LEVEL:
        if score <= lim:
            return lvl
    return "HIGH"
