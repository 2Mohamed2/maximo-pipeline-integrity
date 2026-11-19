# -*- coding: utf-8 -*-
"""Generate the Pipeline Integrity Management (PIM) package for Maximo Manage.

Writes four DBC files into blog/pipeline-integrity/dbc:
  pim_01_schema.dbc   domains, DIG/INSP work types, autokey, objects PIMASSESS + PIMTHREAT + PIMANOM, relationships
  pim_02_app.dbc      the PIMASSESS application, its screen, toolbar, sigoptions and the PIM module
  pim_03_logic.dbc    automation scripts (integrity calculation, approval, dig + reassessment work orders), escalation
  pim_04_api.dbc      MXPIMASSESS object structure, used to load ILI feature listings over REST

Native DBC statements are database-neutral. Freeform rows come from dbclib, which writes one guarded
statement per database (SQL Server, Oracle, Db2), so every file can be re-run safely.
"""
import base64, html, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
from dbclib import Dbc, D, guarded, lit  # noqa: E402

OUT = os.path.join(HERE, "..", "dbc")
VER = "1.0.0"


def esc(s):
    return html.escape(str(s), quote=True)


# --------------------------------------------------------------------------------------------- domains
DOMAINS = [
    ("PIMCLASS", "ASME B31.8 class location", "UPPER", 1, [
        ("1", "Class 1 - 10 or fewer buildings (F 0.72)"), ("2", "Class 2 - 11 to 45 buildings (F 0.60)"),
        ("3", "Class 3 - 46 or more buildings (F 0.50)"), ("4", "Class 4 - multi-storey buildings prevalent (F 0.40)")]),
    ("PIMTHREAT", "ASME B31.8S threat category", "UPPER", 8, [
        ("EXTCORR", "External corrosion (time-dependent)"), ("INTCORR", "Internal corrosion (time-dependent)"),
        ("SCC", "Stress corrosion cracking (time-dependent)"), ("MFG", "Manufacturing defects (stable)"),
        ("CONSTR", "Welding / fabrication / construction (stable)"), ("EQUIP", "Equipment (stable)"),
        ("TPD", "Third-party / mechanical damage (time-independent)"),
        ("INCOPS", "Incorrect operations (time-independent)"),
        ("WEATHER", "Weather and outside force (time-independent)")]),
    ("PIMSUSC", "Susceptibility of a pipeline segment to a threat", "UPPER", 6, [
        ("HIGH", "High"), ("MEDIUM", "Medium"), ("LOW", "Low"), ("NONE", "None / not applicable")]),
    ("PIMFTYPE", "ILI feature type", "UPPER", 10, [
        ("METALLOSS", "Metal loss (corrosion)"), ("DENT", "Plain dent"), ("DENTML", "Dent with metal loss"),
        ("CRACK", "Crack-like feature")]),
    ("PIMSURF", "Feature surface", "UPPER", 3, [("EXT", "External"), ("INT", "Internal")]),
    ("PIMRESP", "ASME B31.8S response category", "UPPER", 10, [
        ("IMMEDIATE", "Immediate - reduce pressure and repair on discovery"),
        ("SCHEDULED", "Scheduled - repair within one year"), ("MONITORED", "Monitored - reassess at the next interval"),
        ("REPAIRED", "Repaired")]),
    ("PIMFSTAT", "ILI feature status", "UPPER", 8, [("OPEN", "Open"), ("REPAIRED", "Repaired")]),
    ("PIMENV", "Environmental sensitivity along the segment", "UPPER", 6, [
        ("LOW", "Low (category A)"), ("MEDIUM", "Medium (category C)"), ("HIGH", "High (category D)")]),
    ("PIMCOF", "Consequence of failure category", "UPPER", 1, [
        ("A", "A"), ("B", "B"), ("C", "C"), ("D", "D"), ("E", "E")]),
    ("PIMRISK", "Pipeline segment risk level", "UPPER", 8, [
        ("LOW", "Low"), ("MEDIUM", "Medium"), ("MEDHIGH", "Medium-high"), ("HIGH", "High")]),
    ("PIMSTATUS", "Pipeline integrity assessment status", "UPPER", 10, [
        ("DRAFT", "Draft - being prepared"), ("APPR", "Approved - drives digs and the reassessment"),
        ("SUPERSEDED", "Superseded by a newer approved assessment")]),
]


def A(attr, mt, ln=None, sc=None, req=False, title="", rem="", sao=None, saa=None, dom=None, dflt=None):
    return dict(attr=attr, mt=mt, ln=ln, sc=sc, req=req, title=title, rem=rem or title, sao=sao, saa=saa,
                dom=dom, dflt=dflt)


SITEORG = [A("SITEID", "UPPER", 8, req=True, title="Site", sao="SITE", saa="SITEID"),
           A("ORGID", "UPPER", 8, req=True, title="Organization", sao="ORGANIZATION", saa="ORGID")]

PIMASSESS = [
    A("ASSESSNUM", "UPPER", 12, req=True, title="Assessment", rem="Pipeline integrity assessment number"),
    A("DESCRIPTION", "ALN", 100, title="Description"),
    A("ASSETNUM", "UPPER", 25, req=True, title="Segment", rem="Pipeline segment asset", sao="ASSET", saa="ASSETNUM"),
    A("PIPELINE", "ALN", 40, title="Pipeline"),
    A("KPSTART", "DECIMAL", 10, 3, title="Start KP (km)"),
    A("KPEND", "DECIMAL", 10, 3, title="End KP (km)"),
    A("INSTALLDATE", "DATE", title="In service since"),
    A("COATING", "ALN", 40, title="Coating", rem="External coating system, e.g. 3-layer PE"),
    A("STATUS", "UPPER", 10, req=True, title="Status", dom="PIMSTATUS", dflt="DRAFT"),
    A("ASSESSDATE", "DATE", title="Assessment date"),
    A("ASSESSOR", "UPPER", 30, title="Assessed by", rem="Integrity engineer", sao="PERSON", saa="PERSONID"),
    A("CLASSLOC", "UPPER", 1, title="Class location", dom="PIMCLASS", dflt="1"),
    A("HCA", "YORN", title="High consequence area", dflt="0"),
    A("OD", "DECIMAL", 8, 1, title="Outside diameter (mm)"),
    A("WT", "DECIMAL", 6, 2, title="Wall thickness (mm)"),
    A("GRADE", "ALN", 20, title="Line pipe grade", rem="e.g. API 5L X60"),
    A("SMYS", "DECIMAL", 8, 1, title="SMYS (MPa)", rem="Specified minimum yield strength"),
    A("MAOP", "DECIMAL", 8, 1, title="MAOP (bar)", rem="Maximum allowable operating pressure"),
    A("DESIGNF", "DECIMAL", 4, 2, title="Design factor F", rem="From the class location (ASME B31.8)"),
    A("ILIDATE", "DATE", title="ILI run date"),
    A("ILIREPORTDATE", "DATE", title="ILI report received", rem="Discovery date: response times start here"),
    A("ILITOOL", "ALN", 40, title="ILI tool", rem="e.g. high-resolution MFL + caliper"),
    A("PREVILIDATE", "DATE", title="Previous ILI run", rem="Used for feature-matched corrosion growth"),
    A("DEFAULTCGR", "DECIMAL", 6, 3, title="Default growth (mm/y)", rem="Depth growth for features without a match",
      dflt="0.200"),
    A("SAFETYF", "DECIMAL", 4, 2, title="Safety factor on Pf", rem="Safe pressure = Pf x factor (defaults to F)"),
    A("NUMANOM", "INTEGER", title="Features listed"),
    A("NUMIMMED", "INTEGER", title="Immediate"),
    A("NUMSCHED", "INTEGER", title="Scheduled"),
    A("NUMMON", "INTEGER", title="Monitored"),
    A("NUMREPAIRED", "INTEGER", title="Repaired"),
    A("HOOPPCT", "DECIMAL", 6, 1, title="Hoop stress at MAOP (% SMYS)"),
    A("MAXERF", "DECIMAL", 6, 3, title="Worst ERF"),
    A("MINPFRATIO", "DECIMAL", 6, 3, title="Lowest Pf/MAOP (monitored)"),
    A("MINLIFE", "DECIMAL", 6, 1, title="Shortest remaining life (y)"),
    A("POFCAT", "INTEGER", title="Likelihood category (1-5)"),
    A("DRIVER", "UPPER", 8, title="Governing threat", dom="PIMTHREAT"),
    A("INTERACT", "ALN", 60, title="Interacting threats"),
    A("PIRM", "DECIMAL", 8, 1, title="Potential impact radius (m)"),
    A("BUILDINGS", "INTEGER", title="Buildings inside PIR", dflt="0"),
    A("IDSITE", "YORN", title="Identified site inside PIR", rem="School, hospital, assembly area", dflt="0"),
    A("COFPEOPLE", "UPPER", 1, title="People CoF", dom="PIMCOF"),
    A("ENVSENS", "UPPER", 6, title="Environmental sensitivity", dom="PIMENV", dflt="LOW"),
    A("COFENV", "UPPER", 1, title="Environment CoF", dom="PIMCOF"),
    A("REPAIRCOST", "DECIMAL", 14, 2, title="Repair cost (USD)"),
    A("OUTAGEDAYS", "DECIMAL", 8, 1, title="Supply outage (days)"),
    A("LOSSPERDAY", "DECIMAL", 14, 2, title="Lost throughput per day (USD)"),
    A("ENVCOST", "DECIMAL", 14, 2, title="Environmental cost (USD)"),
    A("FINCOST", "DECIMAL", 14, 2, title="Financial consequence (USD)"),
    A("COFFIN", "UPPER", 1, title="Financial CoF", dom="PIMCOF"),
    A("COFCAT", "UPPER", 1, title="CoF category", dom="PIMCOF"),
    A("RISKCELL", "UPPER", 2, title="Risk cell"),
    A("RISK", "UPPER", 8, title="Risk", dom="PIMRISK"),
    A("TABLEINT", "DECIMAL", 6, 1, title="B31.8S Table 3 interval (y)"),
    A("MAXINTERVAL", "DECIMAL", 6, 1, title="Maximum interval (y)", dflt="10"),
    A("HCAMAX", "DECIMAL", 6, 1, title="HCA maximum interval (y)",
      rem="Regulatory cap for HCA segments (49 CFR 192.939: 7 years); set your regulator's value", dflt="7"),
    A("INTERVALBASIS", "ALN", 100, title="Interval set by"),
    A("NEXTASSESSDATE", "DATE", title="Next assessment due"),
    A("ASSESSMETHOD", "ALN", 100, title="Assessment method"),
    A("WONUM", "UPPER", 25, title="Reassessment work order", sao="WORKORDER", saa="WONUM"),
    A("CALCNOTE", "ALN", 1000, title="Calculation trace"),
]

PIMTHREAT = [
    A("ASSESSNUM", "UPPER", 12, req=True, title="Assessment", sao="PIMASSESS", saa="ASSESSNUM"),
    A("THREAT", "UPPER", 8, req=True, title="Threat", dom="PIMTHREAT"),
    A("SUSCEPT", "UPPER", 6, req=True, title="Susceptibility", dom="PIMSUSC", dflt="LOW"),
    A("MITIGATED", "YORN", title="Mitigated", rem="A preventive measure is in place and verified", dflt="0"),
    A("SCORE", "INTEGER", title="Likelihood score"),
    A("RECMETHOD", "ALN", 100, title="Assessment / prevention"),
    A("NOTES", "ALN", 250, title="Basis / notes"),
]

PIMANOM = [
    A("ASSESSNUM", "UPPER", 12, req=True, title="Assessment", sao="PIMASSESS", saa="ASSESSNUM"),
    A("FEATURENUM", "UPPER", 12, req=True, title="Feature", rem="ILI feature number"),
    A("KP", "DECIMAL", 10, 3, title="KP (km)"),
    A("CLOCK", "ALN", 5, title="Clock"),
    A("FTYPE", "UPPER", 10, req=True, title="Type", dom="PIMFTYPE", dflt="METALLOSS"),
    A("SURFACE", "UPPER", 3, title="Surface", dom="PIMSURF", dflt="EXT"),
    A("DEPTHPCT", "DECIMAL", 5, 1, title="Depth (% wt)"),
    A("LENGTH", "DECIMAL", 8, 1, title="Length (mm)"),
    A("WIDTH", "DECIMAL", 8, 1, title="Width (mm)"),
    A("DENTPCT", "DECIMAL", 5, 1, title="Dent depth (% OD)"),
    A("PREVDEPTHPCT", "DECIMAL", 5, 1, title="Previous ILI depth (% wt)"),
    A("GROWTH", "DECIMAL", 6, 3, title="Growth (mm/y)"),
    A("PF", "DECIMAL", 8, 1, title="Failure pressure Pf (bar)"),
    A("PSAFE", "DECIMAL", 8, 1, title="Safe pressure (bar)"),
    A("ERF", "DECIMAL", 6, 3, title="ERF"),
    A("PFRATIO", "DECIMAL", 6, 3, title="Pf/MAOP"),
    A("RESPONSE", "UPPER", 10, title="Response", dom="PIMRESP"),
    A("REMLIFE", "DECIMAL", 6, 1, title="Remaining life (y)"),
    A("DUEDATE", "DATE", title="Respond by"),
    A("WONUM", "UPPER", 25, title="Dig work order", sao="WORKORDER", saa="WONUM"),
    A("FSTATUS", "UPPER", 8, title="Feature status", dom="PIMFSTAT", dflt="OPEN"),
    A("REPAIRDATE", "DATE", title="Repair date"),
    A("REPAIRTYPE", "ALN", 40, title="Repair", rem="e.g. Type B sleeve, composite wrap, cut-out"),
]

OBJECTS = [
    ("PIMASSESS", "Integrity assessment of one pipeline segment", "ASSESSNUM,SITEID", "PIMASSESSID", PIMASSESS),
    ("PIMTHREAT", "B31.8S threat scored in a pipeline integrity assessment", "ASSESSNUM,THREAT,SITEID", "PIMTHREATID",
     PIMTHREAT),
    ("PIMANOM", "ILI feature evaluated in a pipeline integrity assessment", "ASSESSNUM,FEATURENUM,SITEID", "PIMANOMID",
     PIMANOM),
]

RELS = [
    ("PIMASSESS", "ASSET", "ASSET", "assetnum=:assetnum and siteid=:siteid", "The assessed segment"),
    ("PIMASSESS", "THREATS", "PIMTHREAT", "assessnum=:assessnum and siteid=:siteid", "Threats of the assessment"),
    ("PIMASSESS", "ANOMALIES", "PIMANOM", "assessnum=:assessnum and siteid=:siteid", "ILI features of the assessment"),
    ("PIMASSESS", "PIMWO", "WORKORDER", "assetnum=:assetnum and siteid=:siteid and worktype in ('DIG','INSP')",
     "Dig and reassessment work orders of the segment"),
    ("PIMASSESS", "HISTORY", "PIMASSESS", "assetnum=:assetnum and siteid=:siteid and assessnum<>:assessnum",
     "Other assessments of the same segment"),
    ("ASSET", "PIMASSESS", "PIMASSESS", "assetnum=:assetnum and siteid=:siteid", "Integrity assessments of the segment"),
]


def attrdef(a):
    s = '      <attrdef attribute="%s" maxtype="%s"' % (a["attr"], a["mt"])
    if a["mt"] == "DECIMAL":
        s += ' length="%d" scale="%d"' % (a["ln"], a["sc"])
    elif a["ln"]:
        s += ' length="%d"' % a["ln"]
    s += ' required="%s" title="%s" remarks="%s"' % ("true" if a["req"] else "false", esc(a["title"]), esc(a["rem"]))
    if a["sao"]:
        s += ' sameasobject="%s" sameasattribute="%s"' % (a["sao"], a["saa"])
    if a["dom"]:
        s += ' domain="%s"' % a["dom"]
    if a["dflt"] is not None:
        s += ' defaultvalue="%s"' % esc(a["dflt"])
    return s + "/>"


def worktype_row(db, wt, desc, cuid):
    q = D[db]
    return (guarded(db, "worktype", ["worktype", "wtypedesc", "promptfail", "promptdown", "orgid", "woclass",
                                     "worktypeid", "type", "keeptaskstatushist", "contentuid", "ahcondassess"],
                    [lit(wt), lit(desc), "0", "0", "o.orgid", "'WORKORDER'", q["seq"] % "worktypeseq", "'NONE'", "1",
                     lit(cuid) + q["cat"] + "o.orgid", "0"],
                    "worktype=%s and orgid=o.orgid" % lit(wt), "organization o where 1=1")
            .replace("not exists (select 1 from worktype where", "not exists (select 1 from worktype w where w.")
            .replace("and orgid=o.orgid)", "and w.orgid=o.orgid)"))


def schema_dbc():
    d = Dbc("pim_01_schema", VER, "PIM: domains, DIG and INSP work types, objects and relationships",
            "  Pipeline Integrity Management for Maximo Manage - part 1 of 3: data model.")
    stm = []
    for did, desc, mt, ln, vals in DOMAINS:
        stm.append('    <specify_synonym_domain domainid="%s" description="%s" maxtype="%s" length="%d" '
                   'overwrite="true" internal="false">' % (did, esc(desc), mt, ln))
        for v, vd in vals:
            stm.append('      <synonymvalueinfo value="%s" maxvalue="%s" defaults="true" description="%s"/>'
                       % (v, v, esc(vd)))
        stm.append('    </specify_synonym_domain>')
    for obj, desc, pk, uid, attrs in OBJECTS:
        stm.append('    <define_table object="%s" description="%s" service="CUSTAPP" '
                   'classname="psdi.mbo.custapp.CustomMboSet" type="site" persistent="true" primarykey="%s" '
                   'unique_column="%s" mainobject="%s">'
                   % (obj, esc(desc), pk, uid, "true" if obj == "PIMASSESS" else "false"))
        stm.append(attrdef(A(uid, "BIGINT", req=True, title="Unique id")))
        for a in attrs[:1] + SITEORG + attrs[1:]:
            stm.append(attrdef(a))
        stm.append('    </define_table>')
    for parent, name, child, wc, rem in RELS:
        stm.append('    <create_relationship parent="%s" name="%s" child="%s" whereclause="%s" remarks="%s"/>'
                   % (parent, name, child, esc(wc), esc(rem)))
    d.blocks.extend(stm)

    def master_rows(db):
        q = D[db]
        out = [worktype_row(db, "DIG", "Integrity dig and repair", "PIMDIG"),
               worktype_row(db, "INSP", "Inspection", "PIMINSP")]
        out.append(guarded(db, "autokey", ["prefix", "seed", "orgid", "siteid", "autokeyname", "setid", "langcode",
                                           "autokeyid"],
                           ["'PIM-'", "1001", "o.orgid", "null", "'PIMASSESSNUM'", "null", "'EN'",
                            q["seq"] % "autokeyseq"],
                           "autokeyname='PIMASSESSNUM' and orgid=o.orgid", "organization o where 1=1")
                   .replace("not exists (select 1 from autokey where", "not exists (select 1 from autokey k where k.")
                   .replace("and orgid=o.orgid)", "and k.orgid=o.orgid)"))
        for t in ("maxattribute", "maxattributecfg"):
            out.append('      <sql target="%s"><![CDATA[update %s set autokeyname=\'PIMASSESSNUM\', '
                       'defaultvalue=\'&AUTOKEY&\' where objectname=\'PIMASSESS\' and attributename=\'ASSESSNUM\']]></sql>'
                       % (db, t))
        return out
    d.block("DIG and INSP work types, PIMASSESSNUM autokey", master_rows)
    return d


# --------------------------------------------------------------------------------------------- screen
ALL_ATTRS = PIMASSESS + PIMTHREAT + PIMANOM
DATE = {a["attr"] for a in ALL_ATTRS if a["mt"] == "DATE"}
DOM = {a["attr"] for a in ALL_ATTRS if a["dom"]}
YORN = {a["attr"] for a in ALL_ATTRS if a["mt"] == "YORN"}
CALC = {"DESIGNF", "NUMANOM", "NUMIMMED", "NUMSCHED", "NUMMON", "NUMREPAIRED", "HOOPPCT", "MAXERF", "MINPFRATIO",
        "MINLIFE", "POFCAT", "DRIVER", "INTERACT", "PIRM", "COFPEOPLE", "COFENV", "FINCOST", "COFFIN", "COFCAT",
        "RISKCELL", "RISK", "TABLEINT", "INTERVALBASIS", "NEXTASSESSDATE", "ASSESSMETHOD", "WONUM", "CALCNOTE"}
THRCALC = {"SCORE", "RECMETHOD"}
ANOCALC = {"GROWTH", "PF", "PSAFE", "ERF", "PFRATIO", "RESPONSE", "REMLIFE", "DUEDATE", "WONUM"}


def field(attr, pfx, calc=CALC):
    i = "%s_%s" % (pfx, attr.lower())
    ro = ' inputmode="readonly"' if attr in calc else ""
    if attr == "ASSETNUM":
        return ('<multiparttextbox applink="asset" dataattribute="ASSETNUM" descdataattribute="ASSET.DESCRIPTION" '
                'id="%s" lookup="asset" menutype="asset"/>' % i)
    if attr == "ASSESSOR":
        return '<textbox dataattribute="ASSESSOR" id="%s" lookup="person"/>' % i
    if attr == "WONUM":
        return '<textbox applink="wotrack" dataattribute="WONUM" id="%s" inputmode="readonly" menutype="workorder"/>' % i
    if attr in ("ASSESSMETHOD", "INTERVALBASIS"):
        return '<multilinetextbox columns="40" dataattribute="%s" id="%s" inputmode="readonly" rows="3"/>' % (attr, i)
    if attr == "CALCNOTE":
        return '<multilinetextbox columns="90" dataattribute="CALCNOTE" id="%s" inputmode="readonly" rows="5"/>' % i
    if attr in YORN:
        return '<checkbox dataattribute="%s" id="%s"%s/>' % (attr, i, ro)
    lk = (' lookup="valuelist"' if attr in DOM and attr not in calc
          else (' lookup="datelookup"' if attr in DATE and attr not in calc else ""))
    return '<textbox dataattribute="%s" id="%s"%s%s/>' % (attr, i, lk, ro)


SECTIONS = [  # (id, label, column 1, column 2, column 3)
    ("seg", "Pipeline segment", ["ASSESSNUM", "ASSETNUM", "PIPELINE", "KPSTART", "KPEND", "INSTALLDATE", "COATING"],
     ["STATUS", "ASSESSDATE", "ASSESSOR", "CLASSLOC", "DESIGNF", "HCA"], ["OD", "WT", "GRADE", "SMYS", "MAOP", "HOOPPCT"]),
    ("ili", "In-line inspection", ["ILIDATE", "ILIREPORTDATE", "ILITOOL", "PREVILIDATE", "DEFAULTCGR", "SAFETYF"],
     ["NUMANOM", "NUMIMMED", "NUMSCHED", "NUMMON", "NUMREPAIRED"], ["MAXERF", "MINPFRATIO", "MINLIFE"]),
    ("cof", "Consequence of failure", ["PIRM", "BUILDINGS", "IDSITE", "COFPEOPLE"],
     ["ENVSENS", "COFENV", "REPAIRCOST", "OUTAGEDAYS"], ["LOSSPERDAY", "ENVCOST", "FINCOST", "COFFIN"]),
    ("plan", "Risk and reassessment plan", ["POFCAT", "DRIVER", "INTERACT", "COFCAT", "RISKCELL", "RISK"],
     ["TABLEINT", "MAXINTERVAL", "HCAMAX", "INTERVALBASIS"], ["NEXTASSESSDATE", "ASSESSMETHOD", "WONUM"]),
]

CHILD_TABS = [  # (id, label, relationship, columns, editable, calc set, detail column 1, detail column 2)
    ("thr", "Threats", "THREATS", ["THREAT", "SUSCEPT", "MITIGATED", "SCORE", "RECMETHOD", "NOTES"], True, THRCALC,
     ["THREAT", "SUSCEPT", "MITIGATED", "NOTES"], ["SCORE", "RECMETHOD"]),
    ("ano", "ILI Features", "ANOMALIES", ["FEATURENUM", "KP", "CLOCK", "FTYPE", "SURFACE", "DEPTHPCT", "LENGTH",
                                          "GROWTH", "PF", "ERF", "PFRATIO", "RESPONSE", "REMLIFE", "DUEDATE", "WONUM",
                                          "FSTATUS"], True, ANOCALC,
     ["FEATURENUM", "KP", "CLOCK", "FTYPE", "SURFACE", "DEPTHPCT", "LENGTH", "WIDTH", "DENTPCT", "PREVDEPTHPCT",
      "FSTATUS", "REPAIRDATE", "REPAIRTYPE"],
     ["GROWTH", "PF", "PSAFE", "ERF", "PFRATIO", "RESPONSE", "REMLIFE", "DUEDATE", "WONUM"]),
    ("wo", "Work Orders", "PIMWO", ["WONUM", "DESCRIPTION", "WORKTYPE", "STATUS", "TARGSTARTDATE", "WOPRIORITY"], False,
     set(), [], []),
    ("hist", "Assessment History", "HISTORY", ["ASSESSNUM", "ASSESSDATE", "ILIDATE", "STATUS", "NUMIMMED", "NUMSCHED",
                                               "RISKCELL", "RISK", "NEXTASSESSDATE"], False, set(), [], []),
]


def presentation():
    p = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<presentation id="pimassess" mboname="PIMASSESS" orderby="assessnum desc" resultstableid="results_showlist" '
         'version="7.6.1.2" apphelp="">',
         '<page id="mainrec" scroll="false"><include controltoclone="pageHeader" id="INCLUDE-pageHeader"/>',
         '<clientarea id="clientarea"><tabgroup id="maintabs" style="form">',
         '<tab default="true" id="results" label="List" type="list">',
         '<menubar event="search" id="actiontoolbar" sourcemethod="getAppSearchOptions"/>',
         '<table datasrc="results_showlist" id="results_showlist" inputmode="readonly" label="Pipeline Integrity Assessments" '
         'mboname="PIMASSESS" selectmode="multiple">',
         '<tablebody displayrowsperpage="20" filterable="true" filterexpanded="true" id="results_showlist_tb">',
         '<tablecol dataattribute="ASSESSNUM" filterable="false" id="r_sel" mxevent="toggleselectrow" '
         'mxevent_desc="Select Row {0}" sortable="false" type="event"/>',
         '<tablecol dataattribute="ASSESSNUM" id="r_num" mxevent="selectrecord" mxevent_desc="Go To %1" type="link"/>']
    for c in ["ASSETNUM", "DESCRIPTION", "KPSTART", "KPEND", "CLASSLOC", "HCA", "NUMIMMED", "NUMSCHED", "RISKCELL",
              "RISK", "NEXTASSESSDATE", "STATUS"]:
        lk = ' filterable="true" lookup="valuelist"' if c in DOM else ""
        p.append('<tablecol dataattribute="%s" id="r_%s"%s/>' % (c, c.lower(), lk))
    p.append('</tablebody></table></tab>')
    p.append('<tab id="main" label="Assessment" type="insert">')
    p.append('<section id="hdr"><sectionrow id="hdr_r"><sectioncol id="hdr_c"><section id="hdr_s">'
             '<multiparttextbox dataattribute="ASSESSNUM" descdataattribute="DESCRIPTION" id="hdr_num"/>'
             '</section></sectioncol></sectionrow></section>')
    for sid, label, c1, c2, c3 in SECTIONS:
        p.append('<section collapsed="false" id="%s" label="%s"><sectionrow id="%s_r">' % (sid, esc(label), sid))
        for n, cols in enumerate((c1, c2, c3), 1):
            p.append('<sectioncol id="%s_c%d"><section id="%s_s%d">' % (sid, n, sid, n))
            p.extend(field(a, sid) for a in cols if a != "ASSESSNUM")
            p.append('</section></sectioncol>')
        p.append('</sectionrow></section>')
    p.append('<section id="note" label="Calculation trace"><sectionrow id="note_r"><sectioncol id="note_c">'
             '<section id="note_s">%s</section></sectioncol></sectionrow></section>' % field("CALCNOTE", "note"))
    p.append('<tabgroup id="childtabs" style="form">')
    for tid, label, rel, cols, edit, calc, d1, d2 in CHILD_TABS:
        ro = "" if edit else ' inputmode="readonly"'
        p.append('<tab id="%s" label="%s"><table id="%s_t" label="%s" relationship="%s"%s>'
                 % (tid, esc(label), tid, esc(label), rel, ro))
        p.append('<tablebody displayrowsperpage="%d" filterable="true" id="%s_tb">' % (15 if tid == "ano" else 10, tid))
        if edit:
            p.append('<tablecol filterable="false" id="%s_det" mxevent="toggledetailstate" mxevent_desc="View Details" '
                     'sortable="false" type="event"/>' % tid)
        for c in cols:
            if c == "WONUM":
                p.append('<tablecol applink="wotrack" dataattribute="WONUM" id="%s_wonum" inputmode="readonly" '
                         'menutype="workorder"/>' % tid)
                continue
            ro_c = ' inputmode="readonly"' if c in calc else ""
            lk = ' lookup="valuelist"' if edit and c in DOM and c not in calc else ""
            ty = ' type="checkbox"' if c in YORN else ""
            p.append('<tablecol dataattribute="%s" id="%s_%s"%s%s%s/>' % (c, tid, c.lower(), lk, ro_c, ty))
        if edit:
            p.append('<tablecol filterable="false" id="%s_del" mxevent="toggledeleterow" mxevent_icon="btn_garbage.gif" '
                     'mxevent_desc="Mark Row for Delete" sortable="false" type="event"/>' % tid)
        p.append('</tablebody>')
        if edit:
            p.append('<tabledetails id="%s_td"><section id="%s_tds" label="Details"><sectionrow id="%s_tdr">'
                     '<sectioncol id="%s_tdc1"><section id="%s_tdcs1">%s</section></sectioncol>'
                     '<sectioncol id="%s_tdc2"><section id="%s_tdcs2">%s</section></sectioncol>'
                     '</sectionrow></section></tabledetails>'
                     % (tid, tid, tid, tid, tid, "".join(field(a, tid + "d", calc) for a in d1),
                        tid, tid, "".join(field(a, tid + "d", calc) for a in d2)))
            p.append('<buttongroup id="%s_bg"><pushbutton default="true" id="%s_new" label="New Row" mxevent="addrow"/>'
                     '</buttongroup>' % (tid, tid))
        p.append('</table></tab>')
    p.append('</tabgroup></tab></tabgroup></clientarea></page></presentation>')
    return "".join(p)


def app_dbc():
    d = Dbc("pim_02_app", VER, "PIM: Pipeline Integrity application, toolbar, security options and PIM module",
            "  Pipeline Integrity Management for Maximo Manage - part 2 of 3: application.")
    app = "PIMASSESS"
    s = ['    <create_app app="%s" description="Pipeline Integrity" skipnavigation="false" orderby="assessnum desc" '
         'maintbname="PIMASSESS"/>' % app]
    for opt, od in [("READ", "Access Pipeline Integrity"), ("INSERT", "New assessment"), ("SAVE", "Save assessment"),
                    ("DELETE", "Delete assessment"), ("CLEAR", "Clear changes"), ("PREVIOUS", "Previous record"),
                    ("NEXT", "Next record"), ("BOOKMARK", "Add to bookmarks"), ("ASSETDETAILS", "View asset")]:
        s.append('    <add_sigoption app="%s" optionname="%s" description="%s" esigenabled="false" visible="true" '
                 'grantapp="ASSET" grantoption="READ"/>' % (app, opt, od))
    b64 = base64.b64encode(presentation().encode("utf-8")).decode("ascii")
    s.append('    <insert table="MAXPRESENTATION"><insertrow>')
    s.append('      <columnvalue column="APP" string="%s"/>' % app)
    s.append('      <columnvalue column="PRESENTATION" clob="%s"/>' % b64)
    s.append('    </insertrow></insert>')
    s.append('    <create_app_menu app="%s" type="tool">' % app)
    for opt, img, tab in [("INSERT", "nav_icon_insert.gif", "ALL"), ("SAVE", "nav_icon_save.gif", "MAIN"),
                          ("CLEAR", "nav_icon_clear.gif", "MAIN")]:
        s.append('      <app_menu_option option="%s" image="%s" tabdisplay="%s"/>' % (opt, img, tab))
    s.append('      <menu_separator tabdisplay="MAIN"/>')
    for opt, img in [("PREVIOUS", "nav_icon_previous.gif"), ("NEXT", "nav_icon_next.gif")]:
        s.append('      <app_menu_option option="%s" image="%s" tabdisplay="MAIN"/>' % (opt, img))
    s.append('    </create_app_menu>')
    s.append('    <create_app_menu app="%s" type="search">' % app)
    s.append('      <app_menu_option option="BOOKMARK" tabdisplay="ALL"/>')
    s.append('    </create_app_menu>')
    s.append('    <create_module module="PIM" description="Pipeline Integrity" menu_position="last" '
             'skipnavigation="false" skipentitlement="false">')
    s.append('      <module_menu_app app="%s" pinned="Y"/>' % app)
    s.append('    </create_module>')
    d.blocks.extend(s)

    def fix(db):   # create_app leaves ORIGINALAPP empty: the app then stays hidden from Go To and App Designer
        return ['      <sql target="%s"><![CDATA[update maxapps set originalapp=app, ismobile=0 where app=\'PIMASSESS\' '
                'and originalapp is null]]></sql>' % db]
    d.block("set MAXAPPS.ORIGINALAPP", fix)
    return d


# --------------------------------------------------------------------------------------------- logic
FIXED = {"ASSESSNUM", "SITEID", "ORGID", "STATUS", "DESCRIPTION"}
FROZEN_INPUTS = tuple(a["attr"] for a in PIMASSESS if a["attr"] not in CALC | FIXED)
CHILD_INPUTS = (("THREATS", tuple(a["attr"] for a in PIMTHREAT if a["attr"] not in THRCALC | FIXED)),
                ("ANOMALIES", tuple(a["attr"] for a in PIMANOM if a["attr"] not in ANOCALC | FIXED)))
CALC_SRC = ("# PIM.CALC - pipeline integrity calculation structured after ASME B31.8S and Modified B31G.\n"
            + open(os.path.join(HERE, "pim_core.py"), encoding="utf-8").read()
            + "\n# inputs an approved or superseded assessment no longer accepts (generated by gen_pim.py)\n"
            + "FROZEN_INPUTS = %r\nCHILD_INPUTS = %r\n" % (FROZEN_INPUTS, CHILD_INPUTS)
            + open(os.path.join(HERE, "pim_calc_mbo.py"), encoding="utf-8").read())

APPROVE_SRC = r'''# PIM.APPROVE - an approved assessment supersedes older approved assessments of the same segment.
from psdi.mbo import MboConstants
F = MboConstants.NOACCESSCHECK | MboConstants.NOVALIDATION_AND_NOACTION
if mbo.getString("STATUS") == "APPR":
    if mbo.isNull("ILIDATE") or mbo.getDouble("MAOP") <= 0 or mbo.getDouble("WT") <= 0:
        service.error("pim", "needili")
    old = mbo.getMboSet("$pimold", "PIMASSESS",
                        "assetnum=:assetnum and siteid=:siteid and status='APPR' and assessnum<>:assessnum")
    o = old.moveFirst()
    while o is not None:
        o.setValue("STATUS", "SUPERSEDED", F)
        o = old.moveNext()
'''

DIGWO_SRC = r'''# PIM.DIGWO - one dig work order per open immediate or scheduled ILI feature without a work order.
from psdi.mbo import MboConstants
F = MboConstants.NOACCESSCHECK | MboConstants.NOVALIDATION_AND_NOACTION
a = mbo
# PIM.LOCK opens approved records read-only, and related sets inherit that flag: lift it on this record so
# the work order set accepts the new row (the save-time guard in PIM.CALC still refuses changed inputs)
a.setFlag(MboConstants.READONLY, False)
if a.getString("STATUS") != "APPR":
    service.error("pim", "notapproved")
TXT = {"METALLOSS": "metal loss", "DENT": "dent", "DENTML": "dent with metal loss", "CRACK": "crack-like feature"}
made, linked = [], []
wos = a.getMboSet("$pimdigwo", "WORKORDER", "1=0")
an = a.getMboSet("ANOMALIES")
r = an.moveFirst()
while r is not None:
    resp = r.getString("RESPONSE")
    if resp in ("IMMEDIATE", "SCHEDULED") and r.isNull("WONUM") and r.getString("FSTATUS") != "REPAIRED":
        # a newer assessment of the same segment re-lists features whose dig is already open: link, never duplicate
        ex = a.getMboSet("$pimdig" + "".join(c for c in r.getString("FEATURENUM") if c.isalnum()), "WORKORDER", "siteid=:siteid and assetnum=:assetnum and worktype='DIG' and "
                         "description like 'Dig %s %%' and status not in (select value from synonymdomain where "
                         "domainid='WOSTATUS' and maxvalue in ('CAN','CLOSE','COMP'))" % r.getString("FEATURENUM"))
        ex.reset()
        if not ex.isEmpty():
            r.setValue("WONUM", ex.getMbo(0).getString("WONUM"), F)
            linked.append(ex.getMbo(0).getString("WONUM"))
            r = an.moveNext()
            continue
        wo = wos.add()
        wo.setValue("SITEID", a.getString("SITEID"), F)
        wo.setValue("ASSETNUM", a.getString("ASSETNUM"))
        wo.setValue("WORKTYPE", "DIG")
        size = ("%.1f%% OD" % r.getDouble("DENTPCT")) if r.getString("FTYPE") == "DENT" else ("%.0f%% wt" % r.getDouble("DEPTHPCT"))
        wo.setValue("DESCRIPTION", ("Dig %s KP %.3f: %s %s, %s" % (r.getString("FEATURENUM"), r.getDouble("KP"),
                    TXT.get(r.getString("FTYPE"), r.getString("FTYPE")), size, resp.lower()))[:100])
        wo.setValue("WOPRIORITY", 1 if resp == "IMMEDIATE" else 2)
        if not r.isNull("DUEDATE"):
            wo.setValue("TARGCOMPDATE", r.getDate("DUEDATE"))
            wo.setValue("TARGSTARTDATE", r.getDate("DUEDATE"))
        wo.setValue("DESCRIPTION_LONGDESCRIPTION",
                    "Raised by pipeline integrity assessment %s.\nFeature %s at KP %.3f, %s o'clock, %s surface.\n"
                    "Depth %.1f %% wt, dent %.1f %% OD, length %.0f mm, growth %.3f mm/y.\n%s: Pf %.1f bar, safe pressure "
                    "%.1f bar, ERF %.3f, Pf/MAOP %.3f -> B31.8S response %s.%s\n\nExcavate, measure (NDE), "
                    "assess and repair; record the repair on the feature (status REPAIRED, repair date, repair type)."
                    % (a.getString("ASSESSNUM"), r.getString("FEATURENUM"), r.getDouble("KP"), r.getString("CLOCK"),
                       r.getString("SURFACE"), r.getDouble("DEPTHPCT"), r.getDouble("DENTPCT"), r.getDouble("LENGTH"), r.getDouble("GROWTH"),
                       "Modified B31G" if r.getString("FTYPE") in ("METALLOSS", "DENTML") else
                       "Intact pipe (response set by the feature type and dent depth)", r.getDouble("PF"), r.getDouble("PSAFE"), r.getDouble("ERF"), r.getDouble("PFRATIO"), resp,
                       "\nIMMEDIATE: reduce operating pressure until the repair is complete." if resp == "IMMEDIATE" else ""))
        r.setValue("WONUM", wo.getString("WONUM"), F)
        made.append(wo.getString("WONUM"))
    r = an.moveNext()
if not made and not linked:
    service.error("pim", "nodigs")
'''

REWO_SRC = r'''# PIM.REASSESSWO - the reassessment work order (next ILI run) of an approved assessment.
# Runs from Select Action > Create Reassessment Work Order and from the PIMDUE escalation.
from psdi.mbo import MboConstants
F = MboConstants.NOACCESSCHECK | MboConstants.NOVALIDATION_AND_NOACTION
a = mbo
# PIM.LOCK opens approved records read-only, and related sets inherit that flag: lift it on this record so
# the work order set accepts the new row (the save-time guard in PIM.CALC still refuses changed inputs)
a.setFlag(MboConstants.READONLY, False)
if a.getString("STATUS") != "APPR":
    service.error("pim", "notapproved")
if not a.isNull("WONUM"):
    service.error("pim", "woexists", [a.getString("WONUM")])
prio = {"HIGH": 1, "MEDHIGH": 2, "MEDIUM": 3, "LOW": 4}.get(a.getString("RISK"), 3)
wos = a.getMboSet("$pimrewo", "WORKORDER", "1=0")
wo = wos.add()
wo.setValue("SITEID", a.getString("SITEID"), F)
wo.setValue("ASSETNUM", a.getString("ASSETNUM"))
wo.setValue("WORKTYPE", "INSP")
wo.setValue("DESCRIPTION", ("Reassess %s KP %.1f-%.1f: %s" % (a.getString("ASSETNUM"), a.getDouble("KPSTART"),
            a.getDouble("KPEND"), a.getString("ASSESSMETHOD")))[:100])
wo.setValue("WOPRIORITY", prio)
wo.setValue("TARGSTARTDATE", a.getDate("NEXTASSESSDATE"))
wo.setValue("DESCRIPTION_LONGDESCRIPTION",
            "Raised by pipeline integrity assessment %s (risk %s %s, governing threat %s).\nInterval set by: %s.\n\n%s"
            % (a.getString("ASSESSNUM"), a.getString("RISKCELL"), a.getString("RISK"), a.getString("DRIVER"),
               a.getString("INTERVALBASIS"), a.getString("CALCNOTE")))
a.setValue("WONUM", wo.getString("WONUM"), F)
'''

CHILDINIT_SRC = r'''# PIM.CHILDINIT - threat and ILI feature rows added on the screen take their keys from the assessment.
from psdi.mbo import MboConstants
F = MboConstants.NOACCESSCHECK | MboConstants.NOVALIDATION_AND_NOACTION
o = mbo.getOwner()
if mbo.toBeAdded() and o is not None and o.getName() == "PIMASSESS":
    for k in ("ASSESSNUM", "SITEID", "ORGID"):
        mbo.setValue(k, o.getString(k), F)
'''


MARK_SRC = r'''# PIM.MARKOWNER - a feature or threat value set on the screen or over REST marks its draft assessment as changed,
# so PIM.CALC (before save) runs even when only child rows were added or edited.
from psdi.mbo import MboConstants
o = mbo.getOwner()
if o is not None and o.getName() == "PIMASSESS" and o.getString("STATUS") == "DRAFT" and not o.isModified("CALCNOTE"):
    o.setValue("CALCNOTE", "Recalculating after a feature or threat change.", MboConstants.NOACCESSCHECK | MboConstants.NOVALIDATION_AND_NOACTION)
'''
LOCK_SRC = r'''# PIM.LOCK - approved and superseded assessments are frozen records: the assessment, its threats and its
# ILI features open read-only. The PIM scripts still write their own fields (they bypass access checks).
from psdi.mbo import MboConstants
a = mbo if mbo.getName() == "PIMASSESS" else mbo.getOwner()
if a is not None and a.getName() == "PIMASSESS" and not a.toBeAdded() and         a.getMboValue("STATUS").getPreviousValue().asString() in ("APPR", "SUPERSEDED"):
    mbo.setFlag(MboConstants.READONLY, True)
'''
MARK_ATTRS = [("PIMANOM", a) for a in ("FEATURENUM", "FTYPE", "SURFACE", "DEPTHPCT", "LENGTH", "DENTPCT", "PREVDEPTHPCT",
                                       "FSTATUS")] + [("PIMTHREAT", a) for a in ("THREAT", "SUSCEPT", "MITIGATED")]


def logic_dbc():
    d = Dbc("pim_03_logic", VER, "PIM: calculation, approval, dig and reassessment work orders, due-date escalation",
            "  Pipeline Integrity Management for Maximo Manage - part 3 of 3: logic.")
    d.script("PIM.CALC", "PIM: B31G failure pressure, B31.8S response, threats, consequence, risk and interval",
             CALC_SRC,
             [dict(launchpointname="PIMCALCSAVE", launchpointtype="OBJECT", objectname="PIMASSESS", objectevent=6,
                   description="Recalculate the integrity assessment before every save"),
              dict(launchpointname="PIMCALC", launchpointtype="ACTION", objectname="PIMASSESS",
                   description="Recalculate Integrity")])
    d.script("PIM.CHILDINIT", "PIM: new threat and feature rows take the assessment keys", CHILDINIT_SRC,
             [dict(launchpointname="PIMTHRINIT", launchpointtype="OBJECT", objectname="PIMTHREAT", objectevent=1,
                   description="Copy assessment keys to a new threat row"),
              dict(launchpointname="PIMANOINIT", launchpointtype="OBJECT", objectname="PIMANOM", objectevent=1,
                   description="Copy assessment keys to a new ILI feature row")])
    d.script("PIM.MARKOWNER", "PIM: a changed feature or threat row marks its draft assessment for recalculation",
             MARK_SRC, [])

    def mark_lps(db):   # attribute launch points (dbclib.script writes object/action ones only)
        q = D[db]
        return [guarded(db, "scriptlaunchpoint", ["launchpointname", "autoscript", "description", "launchpointtype",
                                                  "objectname", "attributename", "objectevent", "active",
                                                  "scriptlaunchpointid"],
                        [lit(("PIMM" + obj[3:6] + attr)[:18]), "'PIM.MARKOWNER'",
                         lit("Mark the assessment when %s.%s changes" % (obj, attr)), "'ATTRIBUTE'", lit(obj), lit(attr),
                         "1", "1", q["seq"] % "scriptlaunchpointseq"],
                        "launchpointname=%s" % lit(("PIMM" + obj[3:6] + attr)[:18])) for obj, attr in MARK_ATTRS] + [
            '      <sql target="%s"><![CDATA[update scriptlaunchpoint set objectevent=1 where autoscript=\'PIM.MARKOWNER\' '
            'and objectevent<>1]]></sql>' % db]   # attribute launch point: 1 = run action (0 would be validate)
    d.block("attribute launch points of PIM.MARKOWNER", mark_lps)
    d.script("PIM.LOCK", "PIM: approved and superseded assessments open read-only", LOCK_SRC,
             [dict(launchpointname="PIMLOCK" + o[3:6], launchpointtype="OBJECT", objectname=o, objectevent=1,
                   description="Open %s read-only when the assessment is approved or superseded" % o)
              for o in ("PIMASSESS", "PIMTHREAT", "PIMANOM")])
    d.script("PIM.APPROVE", "PIM: supersede older approved assessments of the same segment", APPROVE_SRC,
             [dict(launchpointname="PIMAPPROVE", launchpointtype="OBJECT", objectname="PIMASSESS", objectevent=6,
                   condition=":status='APPR'", description="Supersede older approved assessments")])
    d.script("PIM.DIGWO", "PIM: dig work orders for immediate and scheduled features", DIGWO_SRC,
             [dict(launchpointname="PIMDIGWO", launchpointtype="ACTION", objectname="PIMASSESS",
                   description="Create Dig Work Orders")])
    d.script("PIM.REASSESSWO", "PIM: reassessment work order of an approved assessment", REWO_SRC,
             [dict(launchpointname="PIMREWO", launchpointtype="ACTION", objectname="PIMASSESS",
                   description="Create Reassessment Work Order")])
    d.menu_action("PIMASSESS", "PIMCALC", "Recalculate Integrity", ["MAXADMIN", "EVERYONE"], position=910)
    d.menu_action("PIMASSESS", "PIMDIGWO", "Create Dig Work Orders", ["MAXADMIN", "EVERYONE"], position=920)
    d.menu_action("PIMASSESS", "PIMREWO", "Create Reassessment Work Order", ["MAXADMIN", "EVERYONE"], position=930)

    def escalation(db):
        q = D[db]
        return [guarded(db, "escalation", ["escalationid", "description", "active", "objectname", "condition",
                                           "changeby", "changedate", "crontaskname", "instancename", "escalation",
                                           "schedule", "langcode", "hasld", "escstatusflag", "pluspondemand",
                                           "pluspsourceapp"],
                        ["(select coalesce(max(escalationid),0)+1 from escalation)",
                         "'PIM: raise the reassessment work order 180 days before it is due'",
                         "1", "'PIMASSESS'", "'status=''APPR'' and wonum is null'", "'MAXADMIN'", q["now"],
                         "'ESCALATION'", "'PIMDUE'", "'PIMDUE'", "'1d,0,30,2,*,*,*,*,*,*'", "'EN'", "0", "1", "0", "0"],
                        "escalation='PIMDUE'"),
                guarded(db, "escrefpoint", ["escalation", "refpointnum", "eventcondition", "elapsedinterval",
                                            "intervaluom", "repeat", "refpointid", "eventattribute", "action"],
                        ["'PIMDUE'", "1", "null", "-180", "'DAYS'", "0",
                         "(select coalesce(max(refpointid),0)+1 from escrefpoint)", "'NEXTASSESSDATE'", "'PIMREWO'"],
                        "escalation='PIMDUE' and refpointnum=1"),
                guarded(db, "crontaskinstance", ["crontaskname", "instancename", "schedule", "active", "description",
                                                 "crontaskinstanceid", "runasuserid", "langcode", "hasld", "autoremoval",
                                                 "keephistory", "maxhistory"],
                        ["'ESCALATION'", "'PIMDUE'", "'1d,0,30,2,*,*,*,*,*,*'", "1", "'Pipeline reassessment due escalation'",
                         q["seq"] % "crontaskinstanceseq", "'MAXADMIN'", "'EN'", "0", "0", "1", "100"],
                        "crontaskname='ESCALATION' and instancename='PIMDUE'"),
                guarded(db, "crontaskparam", ["crontaskname", "instancename", "parameter", "value", "crontaskparamid"],
                        ["'ESCALATION'", "'PIMDUE'", "'ESCALATION'", "'PIMDUE'", q["seq"] % "crontaskparamseq"],
                        "crontaskname='ESCALATION' and instancename='PIMDUE' and parameter='ESCALATION'")]
    d.block("escalation PIMDUE", escalation)

    def messages(db):
        q = D[db]
        msgs = [("needili", "BMXZZ7201E", "Enter the ILI run date, the MAOP and the wall thickness before you approve "
                 "the pipeline integrity assessment."),
                ("notapproved", "BMXZZ7202E", "Approve the pipeline integrity assessment before you create its work orders."),
                ("woexists", "BMXZZ7203E", "Reassessment work order {0} already exists for this assessment."),
                ("nodigs", "BMXZZ7204E", "No open immediate or scheduled ILI feature is waiting for a dig work order."),
                ("frozenedit", "BMXZZ7206E", "Assessment {0} is approved or superseded: its segment data, threats and "
                 "ILI features cannot change. Create a new assessment to record repairs or new data."),
                ("frozen", "BMXZZ7205E", "This pipeline integrity assessment is approved or superseded and is not "
                 "recalculated. Create a new assessment to reassess the segment.")]
        return [guarded(db, "maxmessages", ["msgkey", "msggroup", "value", "displaymethod", "options", "maxmessagesid",
                                            "msgid", "prefix"],
                        [lit(k), "'pim'", lit(v), "'MSGBOX'", "2", q["seq"] % "maxmessagesseq", lit(i), "1"],
                        "msggroup='pim' and msgkey=%s" % lit(k)) for k, i, v in msgs]
    d.block("messages pim/*", messages)
    return d


def api_dbc():
    d = Dbc("pim_04_api", VER, "PIM: MXPIMASSESS object structure (REST API) for assessments, threats and ILI features",
            "  Pipeline Integrity Management for Maximo Manage - optional part 4: REST/OSLC object structure.\n"
            "  Restart Manage (or reload the object structure cache) after install.")

    def rows(db):
        q = D[db]
        out = [guarded(db, "maxintobject",
                       ["intobjectname", "description", "selfreferencing", "userdefined", "changeby", "changedate",
                        "maxintobjectid", "langcode", "hasld", "queryonly", "configurable", "flatsupported", "usewith",
                        "aliasconflict", "authapp", "loadqueryfromapp", "primaryapi", "completehierarchy", "graphtype",
                        "useforassistant", "trackrequests", "usewithproduct", "intendedfordataloading", "module"],
                       ["'MXPIMASSESS'", "'Pipeline integrity assessments with threats and ILI features'", "0", "1",
                        "'MAXADMIN'", q["now"], q["seq"] % "maxintobjectseq", "'EN'", "0", "0", "1", "0",
                        "'INTEGRATION'", "0", "'PIMASSESS'", "0", "0", "0", "0", "0", "0", "3", "0", "'PIM'"],
                       "intobjectname='MXPIMASSESS'")]
        for obj, rel, order, oid, parent, path in (("PIMASSESS", None, 1, 1, None, "PIMASSESS"),
                                                   ("PIMTHREAT", "THREATS", 2, 2, 1, "PIMASSESS/PIMTHREAT"),
                                                   ("PIMANOM", "ANOMALIES", 3, 3, 1, "PIMASSESS/PIMANOM")):
            out.append(guarded(db, "maxintobjdetail",
                               ["intobjectname", "objectname", "relation", "objectorder", "processorder", "userdefined",
                                "changeby", "changedate", "maxintobjdetailid", "objectid", "parentobjid",
                                "hierarchypath", "excludeparentkey", "deleteoncreate", "propagateevent",
                                "invokeexecute", "skipkeyupdate", "excludebydefault", "skipdeleteonreplace"],
                               ["'MXPIMASSESS'", lit(obj), lit(rel), str(order), str(order), "1", "'MAXADMIN'",
                                q["now"], q["seq"] % "maxintobjdetailseq", str(oid),
                                str(parent) if parent else "null", lit(path), "0", "0", "0", "0", "0", "0", "0"],
                               "intobjectname='MXPIMASSESS' and objectname=%s" % lit(obj)))
        return out
    d.block("object structure MXPIMASSESS", rows)
    return d


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for d in (schema_dbc(), app_dbc(), logic_dbc(), api_dbc()):
        p = os.path.join(OUT, d.name + ".dbc")
        print(p, d.write(p))
    with open(os.path.join(OUT, "pimassess_presentation.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write(presentation())
