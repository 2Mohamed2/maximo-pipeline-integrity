"""Checks of pim_core against hand calculations (python test_core.py)."""
import math
import pim_core as c

# Modified B31G, hand calculation: D 610, t 11.9, SMYS 414, d/t 0.62, L 420
D, t, S = 610.0, 11.9, 414.0
z = 420.0 ** 2 / (D * t)
M = math.sqrt(1 + 0.6275 * z - 0.003375 * z * z)
sf = (S + 69) * (1 - 0.85 * 0.62) / (1 - 0.85 * 0.62 / M)
assert abs(c.b31g_mod(D, t, S, 0.62 * t, 420) - 2 * sf * t / D) < 1e-9
# long flaw branch (z > 50) is continuous enough to stay below the short-flaw value at z = 50
assert c.b31g_mod(D, t, S, 0.5 * t, 900) < c.b31g_mod(D, t, S, 0.5 * t, 300)
# Barlow and PIR
assert abs(c.hoop_pct(7.0, D, t, S) - 43.336) < 0.01
assert abs(c.pir(D, 7.0) - 0.099 * D * math.sqrt(7.0)) < 1e-9
# PIR SI constant matches the imperial 0.69*sqrt(p d^2) ft (psi, in) within 1 %
imp = 0.69 * math.sqrt(7.0 * 145.0377 * (D / 25.4) ** 2) * 0.3048
assert abs(c.pir(D, 7.0) / imp - 1) < 0.01
seg = dict(od=D, wt=t, smys=S, maop=7.0, sf=0.5)
assert c.feature_eval(dict(ftype="METALLOSS", depthpct=84, length=60), seg)["response"] == "IMMEDIATE"   # > 80 % wt
assert c.feature_eval(dict(ftype="METALLOSS", depthpct=62, length=420), seg)["response"] == "SCHEDULED"  # ERF > 1
assert c.feature_eval(dict(ftype="DENT", depthpct=0, length=0, dentpct=7.2), seg)["response"] == "SCHEDULED"
assert c.feature_eval(dict(ftype="DENTML", depthpct=12, length=50), seg)["response"] == "IMMEDIATE"
assert c.feature_eval(dict(ftype="METALLOSS", depthpct=35, length=90), seg)["response"] == "MONITORED"
# Table 3 bands
assert c.table3_interval(54, 1.40) == 10 and c.table3_interval(54, 1.30) == 5 and c.table3_interval(54, 1.2) == 0
assert c.table3_interval(43, 2.1) == 15 and c.table3_interval(43, 1.5) == 10
assert c.table3_interval(25, 2.3) == 20 and c.table3_interval(25, 1.7) == 10
# growth from matched features
assert abs(c.growth_rate(41, 27, 11.9, 7.51, 0.2) - 0.14 * 11.9 / 7.51) < 1e-9
assert c.growth_rate(22, None, 11.9, 7.5, 0.2) == 0.2
# interacting threats bump the category
assert c.pof_category({"EXTCORR": 3, "TPD": 3, "WEATHER": 1}) == (4, "EXTCORR", ["EXTCORR", "TPD"])
assert c.cof_people(46, True) == "E" and c.risk_level(5, "E") == "HIGH" and c.risk_level(1, "A") == "LOW"
print("all checks passed")
