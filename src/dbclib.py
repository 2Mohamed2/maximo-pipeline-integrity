"""Small DBC builder shared by the n8n, Home Assistant and RAGFlow packages.

Every statement is a guarded insert (only if the row is missing), so a DBC can be re-run safely.
Targets SQL Server, Oracle and Db2. Automation script source is rebuilt with CHAR(10)/SPACE() because DBC
freeform collapses whitespace inside literals.
"""
import re

DBS = ("sqlserver", "oracle", "db2")
D = {
    "sqlserver": {"cat": " + ", "nl": "CHAR(10)", "sp": "SPACE(%d)", "head": "CAST(%s AS NVARCHAR(MAX))",
                  "seq": "next value for %s", "now": "getdate()", "dual": ""},
    "oracle": {"cat": " || ", "nl": "CHR(10)", "sp": "RPAD(' ', %d)", "head": "TO_CLOB(%s)",
               "seq": "%s.nextval", "now": "sysdate", "dual": " from dual"},
    "db2": {"cat": " || ", "nl": "CHR(10)", "sp": "REPEAT(' ', %d)", "head": "CAST(%s AS CLOB)",
            "seq": "nextval for %s", "now": "current timestamp", "dual": " from sysibm.sysdummy1"},
}


HANDLER_PROPS = {"HTTP": ("CONNECTTIMEOUT", "COOKIES", "HEADERS", "HTTPEXIT", "HTTPMETHOD", "PASSWORD",
                          "READTIMEOUT", "URL", "USERNAME")}


def lit(s):
    return "null" if s is None else "'" + str(s).replace("'", "''") + "'"


def src_expr(src, db):
    d, parts = D[db], []
    for i, line in enumerate(src.replace("\r\n", "\n").split("\n")):
        if i:
            parts.append(d["nl"])
        for tok in re.split(r"( {2,})", line):
            if tok:
                parts.append(d["sp"] % len(tok) if tok.strip() == "" else lit(tok))
    if db == "oracle":
        parts = ["TO_CLOB(%s)" % p if p.startswith("'") else p for p in parts]
    else:
        parts[0] = d["head"] % parts[0]
    return d["cat"].join(parts)


def guarded(db, table, cols, values, where, src_table=None):
    """insert into table (cols) select values [from src_table] where not exists (row matching where)."""
    d = D[db]
    frm = (" from %s" % src_table) if src_table else d["dual"]
    sel = "select %s%s" % (", ".join(values), frm)
    conj = " and " if src_table else " where "
    return ('      <sql target="%s"><![CDATA[insert into %s (%s) %s%snot exists (select 1 from %s where %s)]]></sql>'
            % (db, table, ", ".join(cols), sel, conj, table, where))


class Dbc:
    def __init__(self, name, version, description, header):
        self.name, self.version, self.description, self.header, self.blocks = name, version, description, header, []

    def block(self, desc, fn):
        self.blocks.append('    <freeform description="%s">\n%s\n    </freeform>'
                           % (desc, "\n".join(r for db in DBS for r in fn(db))))

    # ---- security -------------------------------------------------------------------------------------------
    def group(self, group, description, template="DEFLTREG", sites=("BEDFORD",), org="EAGLENA",
              reassign_by=("MAXADMIN",), all_sites=False):
        def rows(db):
            d = D[db]
            cols = ["maxgroupid", "groupname", "description", "passwordduration", "passwordwarning", "independent",
                    "authallsites", "authallgls", "authallstorerooms", "authlaborall", "authlaborcrew",
                    "authlaborself", "authlaborsuper", "langcode", "authpersongroup", "hasld", "nullrepfac",
                    "authallrepfacs", "maxschedreport", "sidenav", "createddate", "createdby", "changedate",
                    "changeby"]
            vals = [d["seq"] % "maxgroupseq", lit(group), lit(description), "passwordduration", "passwordwarning",
                    "0", "0", "0", "0", "0", "0", "0", "0", "langcode", "authpersongroup", "0", "nullrepfac",
                    "0", "maxschedreport", "sidenav", d["now"], "'MAXADMIN'", d["now"], "'MAXADMIN'"]
            out = [guarded(db, "maxgroup", cols, vals, "groupname=%s" % lit(group),
                           "maxgroup t where t.groupname=%s" % lit(template))
                   .replace("not exists (select 1 from maxgroup where", "not exists (select 1 from maxgroup g where g.")]
            if all_sites:   # needed when Maximo checks the group's rights without a site (e.g. REST API scripts)
                out.append('      <sql target="%s"><![CDATA[update maxgroup set authallsites=1 where groupname=%s '
                           'and authallsites=0]]></sql>' % (db, lit(group)))
            for admin in reassign_by:   # lets the administrator add users to the group (Group Reassignment)
                out.append(guarded(db, "grpreassignauth", ["grpreassignauthid", "userid", "groupname"],
                                   [d["seq"] % "grpreassignauthseq", lit(admin), lit(group)],
                                   "userid=%s and groupname=%s" % (lit(admin), lit(group))))
            for s in sites:
                out.append(guarded(db, "siteauth", ["groupname", "siteid", "orgid", "siteauthid"],
                                   [lit(group), lit(s), lit(org), d["seq"] % "siteauthseq"],
                                   "groupname=%s and siteid=%s" % (lit(group), lit(s))))
            return out
        self.block("security group %s" % group, rows)

    def grants(self, group, app, options):
        def rows(db):
            return [guarded(db, "applicationauth", ["groupname", "app", "optionname", "applicationauthid"],
                            [lit(group), lit(app), lit(o), D[db]["seq"] % "applicationauthseq"],
                            "groupname=%s and app=%s and optionname=%s" % (lit(group), lit(app), lit(o)))
                    for o in options]
        self.block("grant %s %s" % (group, app), rows)

    # ---- integration ----------------------------------------------------------------------------------------
    def endpoint(self, name, description, props, handler="HTTP"):
        def rows(db):
            d = D[db]
            out = [guarded(db, "maxendpoint", ["maxendpointid", "endpointname", "handlername", "description",
                                               "changeby", "changedate", "langcode", "hasld"],
                           [d["seq"] % "maxendpointseq", lit(name), lit(handler), lit(description), "'MAXADMIN'",
                            d["now"], "'EN'", "0"], "endpointname=%s" % lit(name))]
            # every property the handler knows, like an end point created in the UI (empty ones as null)
            allp = dict.fromkeys(HANDLER_PROPS.get(handler, ()), None)
            allp.update(props)
            for p, v in allp.items():
                out.append(guarded(db, "maxendpointdtl", ["maxendpointdtlid", "endpointname", "property", "value",
                                                          "changeby", "changedate", "allowoverride"],
                                   [d["seq"] % "maxendpointdtlseq", lit(name), lit(p), lit(v), "'MAXADMIN'",
                                    d["now"], "0"],
                                   "endpointname=%s and property=%s" % (lit(name), lit(p))))
            # PASSWORD is a binary column: it must stay null unless a real encrypted value is set
            out.append('      <sql target="%s"><![CDATA[update maxendpointdtl set password=null where endpointname=%s '
                       'and password is not null and property<>\'PASSWORD\']]></sql>' % (db, lit(name)))
            return out
        self.block("end point %s" % name, rows)

    # ---- scripts --------------------------------------------------------------------------------------------
    def script(self, name, description, source, launchpoints=(), variables=None):
        """launchpoints: dicts with launchpointname, launchpointtype, objectname, objectevent, condition, description."""
        def rows(db):
            d = D[db]
            out = [guarded(db, "autoscript",
                           ["autoscript", "status", "createddate", "statusdate", "changedate", "changeby",
                            "autoscriptid", "hasld", "langcode", "scriptlanguage", "userdefined", "loglevel",
                            "interface", "active", "description", "version", "source"],
                           [lit(name), "'Active'", d["now"], d["now"], d["now"], "'MAXADMIN'",
                            d["seq"] % "autoscriptseq", "0", "'EN'", "'jython'", "1", "'ERROR'", "0", "1",
                            lit(description), lit(self.version), src_expr(source, db)],
                           "autoscript=%s" % lit(name))]
            for vn, vv in (variables or {}).items():   # literal IN variables, e.g. authapp / authsigoption
                out.append(guarded(db, "autoscriptvars",
                                   ["autoscriptvarsid", "autoscript", "varname", "varbindingvalue", "varbindingtype",
                                    "vartype", "allowoverride", "literaldatatype"],
                                   [d["seq"] % "autoscriptvarsseq", lit(name), lit(vn), lit(vv), "'LITERAL'", "'IN'",
                                    "0", "'ALN'"],
                                   "autoscript=%s and varname=%s" % (lit(name), lit(vn))))
            for lp in launchpoints:
                out.append(guarded(db, "scriptlaunchpoint",
                                   ["launchpointname", "autoscript", "description", "launchpointtype", "objectname",
                                    "objectevent", "condition", "active", "scriptlaunchpointid"],
                                   [lit(lp["launchpointname"]), lit(name), lit(lp["description"]),
                                    lit(lp["launchpointtype"]), lit(lp["objectname"]),
                                    str(lp.get("objectevent")) if lp.get("objectevent") is not None else "null",
                                    lit(lp.get("condition")), "1", d["seq"] % "scriptlaunchpointseq"],
                                   "launchpointname=%s" % lit(lp["launchpointname"])))
                if lp["launchpointtype"] == "ACTION":
                    n = lp["launchpointname"]
                    out.append(guarded(db, "action", ["actionid", "action", "description", "objectname", "type",
                                                      "value", "parameter", "langcode", "usewith", "hasld"],
                                       [d["seq"] % "actionseq", lit(n), lit(lp["description"]), lit(lp["objectname"]),
                                        "'CUSTOM'", "'com.ibm.tivoli.maximo.script.ScriptAction'",
                                        lit("%s,%s,%s" % (name, n, n)), "'EN'", "'ALL'", "0"],
                                       "action=%s" % lit(n)))
            return out
        self.block("script %s" % name, rows)

    def cron_instance(self, crontask, instance, schedule, params, description="", runas="MAXADMIN"):
        """A cron task instance (Cron Task Setup), active, with its parameter rows."""
        def rows(db):
            d = D[db]
            out = [guarded(db, "crontaskinstance", ["crontaskname", "instancename", "schedule", "active", "description",
                                                    "crontaskinstanceid", "runasuserid", "langcode", "hasld",
                                                    "autoremoval", "keephistory", "maxhistory"],
                           [lit(crontask), lit(instance), lit(schedule), "1", lit(description),
                            d["seq"] % "crontaskinstanceseq", lit(runas), "'EN'", "0", "0", "1", "100"],
                           "crontaskname=%s and instancename=%s" % (lit(crontask), lit(instance)))]
            for k, v in params.items():
                out.append(guarded(db, "crontaskparam", ["crontaskname", "instancename", "parameter", "value",
                                                         "crontaskparamid"],
                                   [lit(crontask), lit(instance), lit(k), lit(v), d["seq"] % "crontaskparamseq"],
                                   "crontaskname=%s and instancename=%s and parameter=%s"
                                   % (lit(crontask), lit(instance), lit(k))))
            return out
        self.block("cron task %s.%s" % (crontask, instance), rows)

    def menu_action(self, app, option, description, groups, position=950):
        """Select Action entry that runs the ACTION of the same name (option name must equal the action name)."""
        def rows(db):
            s = D[db]["seq"]
            out = [guarded(db, "sigoption", ["app", "optionname", "description", "esigenabled", "visible",
                                             "sigoptionid", "langcode", "hasld"],
                           [lit(app), lit(option), lit(description), "0", "1", s % "sigoptionseq", "'EN'", "0"],
                           "app=%s and optionname=%s" % (lit(app), lit(option))),
                   guarded(db, "sigoptflag", ["sigoptflagid", "app", "optionname", "flagname", "value"],
                           [s % "sigoptflagseq", lit(app), lit(option), "'WFACTION'", lit(option)],
                           "app=%s and optionname=%s and flagname='WFACTION'" % (lit(app), lit(option))),
                   guarded(db, "maxmenu", ["menutype", "moduleapp", "position", "subposition", "elementtype",
                                           "keyvalue", "visible", "tabdisplay", "maxmenuid"],
                           ["'APPMENU'", lit(app), str(position), "0", "'OPTION'", lit(option), "1", "'ALL'",
                            s % "maxmenuseq"],
                           "menutype='APPMENU' and moduleapp=%s and keyvalue=%s" % (lit(app), lit(option)))]
            for g in groups:
                out.append(guarded(db, "applicationauth", ["groupname", "app", "optionname", "applicationauthid"],
                                   [lit(g), lit(app), lit(option), s % "applicationauthseq"],
                                   "groupname=%s and app=%s and optionname=%s" % (lit(g), lit(app), lit(option))))
            return out
        self.block("menu %s / %s" % (app, option), rows)

    def write(self, path):
        txt = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE script SYSTEM "script.dtd">
<!--
%s
  Every row is guarded (inserted only if missing): safe to re-run. Restart Manage after install so
  menus, grants and end points are reloaded.
-->
<script author="Mohamed Chihaoui" scriptname="%s_%s">
  <description>%s</description>
  <statements>
%s
  </statements>
</script>
""" % (self.header.rstrip(), self.name, self.version, self.description, "\n".join(self.blocks))
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(txt)
        return len(txt)
