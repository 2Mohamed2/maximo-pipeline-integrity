# Pipeline integrity management (PIM) for IBM Maximo Manage

Code that goes with the IBM Community post *Pipeline integrity management in Maximo Manage: from an in-line inspection
listing to dig work orders and a risk-based reassessment date, built with configuration only* (Maximo group), by
Mohamed Chihaoui.

A pipeline integrity module for Maximo Manage 9, built with configuration only (no Java, nothing a Manage update
overwrites). The calculation follows ASME B31G (Modified B31G, 0.85dL) and the work process follows ASME B31.8S:

| Step | What happens |
|---|---|
| Segment | Hoop stress at MAOP (Barlow) as % SMYS, design factor from the ASME B31.8 class location, potential impact radius 0.099 √(d² p). |
| Features | An ILI vendor listing is loaded over REST. Each feature gets its growth rate (from the matched depth of the previous run, or a default), its Modified B31G failure pressure, safe pressure, ERF and Pf/MAOP. |
| Response | B31.8S section 7: immediate (deeper than 80 % wt, Pf below 1.1 MAOP, dent with metal loss, crack), scheduled within one year (ERF ≥ 1, plain dent deeper than 6 % OD), or monitored with a remaining life and a respond-by date. |
| Risk | The nine B31.8S threats scored 1–5 (ILI results replace assumed susceptibility for corrosion; dents raise third-party damage, cracks SCC; interacting threats +1), consequence A–E from people inside the PIR, environment and cost, and a risk cell. |
| Interval | The earliest of B31.8S Table 3 (hoop stress band, lowest Pf/MAOP of the monitored features), the HCA or company maximum interval, and half the shortest remaining life. |
| Work | *Create Dig Work Orders* raises one DIG work order per immediate or scheduled feature (or links the dig already open for it); *Create Reassessment Work Order* raises the next ILI run, and escalation `PIMDUE` does it by itself 180 days before it is due. Approved assessments are read-only and refuse input changes over REST; a new approval supersedes the old one. |

## What is where

```
dbc/pim_01_schema.dbc       11 domains, work types DIG and INSP, autokey PIMASSESSNUM,
                            objects PIMASSESS, PIMTHREAT and PIMANOM, 6 relationships
dbc/pim_02_app.dbc          application Pipeline Integrity (PIMASSESS), its screen, toolbar, signature options, module PIM
dbc/pim_03_logic.dbc        scripts PIM.CALC, PIM.MARKOWNER, PIM.CHILDINIT, PIM.LOCK, PIM.APPROVE, PIM.DIGWO,
                            PIM.REASSESSWO + launch points, three menu actions, escalation PIMDUE, messages BMXZZ7201E-7206E
dbc/pim_04_api.dbc          object structure MXPIMASSESS (REST / OSLC): assessment + threats + ILI features
dbc/pimassess_presentation.xml   the screen, readable (the DBC carries it base64-encoded)

src/gen_pim.py              generates the four DBC files from one definition of the data model, screen and logic
src/pim_core.py             the calculation core: pure functions, no Maximo calls (first part of PIM.CALC)
src/pim_calc_mbo.py         the Maximo part of PIM.CALC: reads the record, calls the core, writes the results
src/test_core.py            checks the core against hand calculations
src/dbclib.py               guarded multi-database freeform statements (SQL Server, Oracle, Db2)

demo/seed.py                pipeline PL-24, segments PL24-S01..S04 and three assessments with features (REST)
demo/ili_load.py            loads an ILI vendor CSV into an assessment (REST)
demo/ili_PL24-S02_2026.csv  the ILI listing of segment PL24-S02 used in the post
demo/lab6_reassess.py       repairs, post-repair assessment, approval that supersedes the first one (REST)
demo/mx.py                  minimal REST client (MAXIMO_URL + MAXIMO_APIKEY, or MAXIMO_USER + MAXIMO_PASSWORD)
```

## Install

1. Back up the database.
2. Copy `dbc/*.dbc` to `tools/maximo/en/script` in the Manage administration environment (on Maximo Application
   Suite, the Manage maxinst pod) and run them in order from `tools/maximo/internal`:
   ```sh
   ./runscriptfile.sh -cscript -fpim_01_schema
   ./runscriptfile.sh -cscript -fpim_02_app
   ./runscriptfile.sh -cscript -fpim_03_logic
   ./runscriptfile.sh -cscript -fpim_04_api
   ```
3. Restart Manage so the application, menus, scripts, attribute launch points, messages, escalation and object
   structure are loaded.
4. Review security: the application options go to every group that can read Assets, the three actions to MAXADMIN and
   EVERYONE. Remove EVERYONE in production.
5. Set the defaults of `PIMASSESS.HCAMAX` (7 years, from 49 CFR 192.939) and `PIMASSESS.MAXINTERVAL` (10 years) to
   your regulator's and company's values.
6. Check: *Pipeline Integrity* opens, and `GET /maximo/api/os/mxpimassess` answers 200.

## Demo data

```sh
export MAXIMO_URL=https://manage.example.com/maximo MAXIMO_APIKEY=...
python demo/seed.py                                        # pipeline + segment assets
python demo/seed.py --assess                               # plus S01, S03, S04 assessments with features
# create the PL24-S02 assessment in the UI (Lab 2 of the post), then:
python demo/ili_load.py PIM-1008 ili_PL24-S02_2026.csv     # use your assessment number
python demo/lab6_reassess.py PIM-1008                      # after approving it and creating its digs (Lab 5)
```

The demo uses site BEDFORD / organization EAGLENA and person WILSON from the Maximo demo data.

## Change the model

Edit `src/pim_core.py` (and `src/pim_calc_mbo.py` for Maximo fields), run `python src/test_core.py`, then
`python src/gen_pim.py` to regenerate the DBC files. On an installed system, save the new source of automation script
`PIM.CALC` in the Automation Scripts application (saving there also refreshes the script cache).

## Before production use

ASME B31.8S and B31G are copyrighted publications. The formulas and limits are in the first block of
`src/pim_core.py`; the threat scores, interaction rule and consequence categories are screening values marked as
such. Not implemented: B31.8S dent location rules and the time-based response schedule (Figure 4), ILI sizing tolerance
(API 1163), crack assessment. An integrity engineer must check every constant against the editions the operator works
to, add the missing rules the operation needs, set the company risk matrix and intervals, and keep the scripts under
change control. Validate against segments already assessed in your current tool before switching.
