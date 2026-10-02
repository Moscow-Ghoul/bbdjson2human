#!/usr/bin/env python3
"""
balance.py - turn your Balanced by Daylight ruleset (hosted on GitHub) into Discord forum posts.

USAGE
    python balance.py                      # fetch the ruleset from GitHub, show what changed, write posts
                                           # (first run asks for your ruleset's GitHub link and remembers it)
    python balance.py --set-url [LINK]     # change the saved ruleset link
    python balance.py --all                # write every post, not only the changed ones
    python balance.py --print              # also show the written posts in the terminal
    python balance.py --no-save            # preview only; never touches the saved "last posted" marker
    python balance.py --no-data-update     # skip downloading the newest perk/addon/map/item lists
    python balance.py --since <commit id>  # compare against a specific older GitHub version
    python balance.py path/to/ruleset.json # use a local file instead of GitHub (no comparison / saving)

HOW IT WORKS
  * Every run downloads the newest ruleset from GitHub (the link is saved in config.json).
  * last_posted.json remembers the GitHub version (commit id) you last posted. The old version is
    downloaded from GitHub again, so nothing else needs to be stored here.
  * The posts built from the old and the new version are compared, and only posts that differ are written
    to output/<date>_<commit>/ - one .txt per post, containing just the post body.
  * The perk/addon/map/item/offering lists are refreshed from the site creator's repo every run (DATA_SOURCES).
  * Perk / addon / map / item / offering IDs the data files don't know are asked about in the terminal and
    remembered in data/custom_names.json.

FOLDER LAYOUT (next to this script)
    data/    CompDBDPerkIDs.json, CompDBDItems.json, CompDBDKillerAddons.json,
             CompDBDOfferings.json, NewMaps.json  (+ custom_names.json, created automatically)
    output/  one folder per run with the post files to paste

PRIVATE REPO? Set an environment variable GITHUB_TOKEN to a personal access token with read access.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent

# ============================================================================
# SETTINGS - edit these
# ============================================================================
CONFIG_FILE = BASE / "config.json"        # remembers your ruleset link (asked on the first run)
STATE_FILE = BASE / "last_posted.json"

# Where the perk / map / item / addon / offering lists come from (maintained by the site's creator).
# Downloaded into data/ on every run; if the download fails, the saved copies in data/ are used.
DATA_REPO = {"owner": "kylestarrtech", "repo": "Balanced-by-Daylight", "branch": "railway-deployment"}
DATA_SOURCES = {   # file name in data/  ->  path inside that repo
    "CompDBDPerkIDs.json":      "public/Perks/dbdperks.json",
    "NewMaps.json":             "public/NewMaps.json",
    "CompDBDItems.json":        "public/Items.json",
    "CompDBDOfferings.json":    "public/Offerings.json",
    "CompDBDKillerAddons.json": "public/NewAddons.json",
}

# --- post style ---
ESC = "\x1b"
WHITE, RED, GREEN = "37", "31", "32"          # ANSI colour codes (written as ESC[2;<code>m)

TIER_POINTER = "{name} Tier bans"             # line in a killer post, e.g. "A Tier bans"
GENERAL_POINTER_KILLER = "General balancing"
GENERAL_POINTER_SURVIVOR = "General Balancing"
TIER_TITLE = "Tier {name}"                    # title/file name of a tier post, e.g. "Tier S"
GENERAL_TITLE = "General"

ADDON_BAN_PREFIX = "-"                        # in front of each banned addon
ALL_ADDONS_OK_PREFIX = "+"
ALL_OTHER_ADDONS = "All other addons are allowed"   # when some addons are banned
ALL_ADDONS = "All addons are allowed"               # when none are banned
NONE_TEXT = "None"
PERK_BAN_PREFIX = "-"                        # in front of each banned perk / tier line (red)
PERK_ALLOW_PREFIX = "+"                       # in front of each allowed perk (green)
ALLOWED_PREFIX = "Allowed: "                  # text before an allowed perk name (set "" to show just the + sign)
COMBO_SUFFIX = " (combo)"                     # added to combo bans in killer posts

# --- section labels, in the order they appear in a killer post ---
L_NOTES, L_MAPS, L_ADDONS = "Notes", "Maps", "Addon bans"
L_KPERKS, L_SPERKS, L_ITEMS = "Killer perks", "Survivor perks", "Items"
L_KOFF, L_SOFF = "Killer offerings", "Survivor offerings"
# tier post sections
L_T_KPERKS, L_T_SPERKS = "Killer perk bans", "Survivor perk bans"
L_T_KCOMBO, L_T_SCOMBO = "Killer combo bans", "Survivor combo bans"
# ============================================================================

# Notes that the script turns into formatting (and then leaves out of the Notes block):
FIRECRACKER_RE = re.compile(r"\b(two|three|four|2|3|4)\s+firecrackers\b", re.I)
DOUBLE_VIGO_RE = re.compile(r"^\s*double\s+vigo'?s\s+shroud\s+must\s+be\s+used\W*$", re.I)
NUMWORDS = {"two": 2, "three": 3, "four": 4, "2": 2, "3": 3, "4": 4}
VIGO_SHROUD = "Vigo's Shroud"

DATA_FILES = {
    "perks": "CompDBDPerkIDs.json",
    "items": "CompDBDItems.json",
    "addons": "CompDBDKillerAddons.json",
    "offerings": "CompDBDOfferings.json",
    "maps": "NewMaps.json",
}


# ----------------------------------------------------------------------------
# Data lookups (+ asking for names of unknown IDs)
# ----------------------------------------------------------------------------
class Data:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.warnings = set()
        self.ctx = ""          # where the ID being resolved is used - shown when asking for a name
        self.silent = False    # True while rendering the OLD version: never ask, never warn
        self.skipped = set()
        self.interactive = sys.stdin.isatty()

        def load(key):
            name = DATA_FILES[key]
            for folder in (self.data_dir, BASE):
                p = Path(folder) / name
                if p.exists():
                    return json.loads(p.read_text(encoding="utf-8-sig"))
            sys.exit(f"Missing data file: {name} (looked in {self.data_dir} and {BASE})")

        self.perks = {str(p["id"]): p["name"] for p in load("perks")}
        self.maps = {str(m["ID"]): m["Name"] for m in load("maps")}
        self.addons = {}
        for killer in load("addons"):
            for a in killer["Addons"]:
                self.addons[a["globalID"]] = a["Name"]
        items = load("items")
        self.items = {i["id"]: {"Name": i["Name"], "Type": i["Type"]} for i in items["Items"]}
        self.item_addons = {t["Name"]: {a["id"]: a["Name"] for a in t["Addons"]}
                            for t in items["ItemTypes"]}
        off = load("offerings")
        self.killer_off = {o["id"]: o["name"] for o in off["Killer"]}
        self.survivor_off = {o["id"]: o["name"] for o in off["Survivor"]}

        # names you typed in earlier runs (only fill gaps - the data files win)
        self.custom_path = self.data_dir / "custom_names.json"
        self.custom = {}
        if self.custom_path.exists():
            self.custom = json.loads(self.custom_path.read_text(encoding="utf-8-sig"))
        c = self.custom
        for k, v in c.get("perk", {}).items():             self.perks.setdefault(k, v)
        for k, v in c.get("map", {}).items():              self.maps.setdefault(k, v)
        for k, v in c.get("addon", {}).items():            self.addons.setdefault(int(k), v)
        for k, v in c.get("killer_offering", {}).items():  self.killer_off.setdefault(int(k), v)
        for k, v in c.get("survivor_offering", {}).items(): self.survivor_off.setdefault(int(k), v)
        for k, v in c.get("item", {}).items():             self.items.setdefault(int(k), v)
        for typ, table in c.get("item_addon", {}).items():
            for k, v in table.items():
                self.item_addons.setdefault(typ, {}).setdefault(int(k), v)

    # -- helpers ----------------------------------------------------------
    def _save_custom(self, kind, key, value, sub=None):
        bucket = self.custom.setdefault(kind, {})
        if sub is not None:
            bucket = bucket.setdefault(sub, {})
        bucket[str(key)] = value
        self.custom_path.parent.mkdir(parents=True, exist_ok=True)
        self.custom_path.write_text(json.dumps(self.custom, indent=1, ensure_ascii=False),
                                    encoding="utf-8")

    def _input(self, prompt):
        try:
            return input(prompt).strip()
        except EOFError:
            return ""

    def _can_ask(self, label, key):
        if self.silent:
            return False
        if (label, str(key)) in self.skipped:
            return False
        if not self.interactive:
            if (label, str(key)) not in self.skipped:   # warn once per ID, not once per killer
                self.skipped.add((label, str(key)))
                self.warnings.add(f"Unknown {label} ID {key} (first seen: {self.ctx}) - run the "
                                  f"script in a terminal so it can ask you for the name")
            return False
        return True

    def _ask_name(self, label, key):
        print(f"\n? Unknown {label} ID {key}  -  used in: {self.ctx}")
        name = self._input("  Name (Enter to skip for now): ")
        if not name:
            self.skipped.add((label, str(key)))
        return name

    def placeholder(self, label, key):
        return f"<unknown {label} {key}>"

    # -- lookups ----------------------------------------------------------
    def _simple(self, table, kind, label, key):
        if key in table:
            return table[key]
        if self._can_ask(label, key):
            name = self._ask_name(label, key)
            if name:
                table[key] = name
                self._save_custom(kind, key, name)
                return name
        return self.placeholder(label, key)

    def perk(self, i):            return self._simple(self.perks, "perk", "perk", str(i))
    def map(self, i):             return self._simple(self.maps, "map", "map", str(i))
    def addon(self, i):           return self._simple(self.addons, "addon", "killer addon", i)
    def killer_offering(self, i): return self._simple(self.killer_off, "killer_offering", "killer offering", i)
    def survivor_offering(self, i): return self._simple(self.survivor_off, "survivor_offering", "survivor offering", i)

    def item(self, i):
        """-> {"Name":..., "Type":...} or None if unknown and skipped."""
        if i in self.items:
            return self.items[i]
        if self._can_ask("item", i):
            name = self._ask_name("item", i)
            if name:
                known = ", ".join(sorted(self.item_addons))
                print(f"  Item types I know: {known}")
                typ = ""
                while not typ:
                    typ = self._input("  Which type is it? (type a known one, or a new name): ")
                self.items[i] = {"Name": name, "Type": typ}
                self._save_custom("item", i, self.items[i])
                return self.items[i]
        return None

    def item_addon(self, typ, aid):
        table = self.item_addons.setdefault(typ, {})
        if aid in table:
            return table[aid]
        label = f"{typ} addon"
        if self._can_ask(label, aid):
            name = self._ask_name(label, aid)
            if name:
                table[aid] = name
                self._save_custom("item_addon", aid, name, sub=typ)
                return name
        return self.placeholder(label, aid)


def join_and(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def sort_names(names):
    return sorted(names, key=lambda s: s.lower())


# ----------------------------------------------------------------------------
# Post model
#   section = (label, segments);  segment = (colour or None, [lines], prefix)
# ----------------------------------------------------------------------------
class Post:
    def __init__(self, title):
        self.title = title
        self.sections = []

    def add(self, label, *segments):
        self.sections.append((label, [s for s in segments if s and (s[1] or s is BOX_BREAK)]))

    def body(self):
        parts = []
        for label, segments in self.sections:
            boxes, current = [], []
            for colour, lines, prefix in segments:
                if colour == "BREAK":
                    boxes.append(current)
                    current = []
                    continue
                text = "\n".join(prefix + ln for ln in lines)
                current.append(f"{ESC}[2;{colour}m{text}{ESC}[0m" if colour else text)
            boxes.append(current)
            blocks = ["```ansi\n" + "\n".join(b) + "\n```" for b in boxes if b]
            parts.append(f"{label}:\n" + "\n".join(blocks))
        return "\n".join(parts)

    def flat(self):
        """[[section, colour, line], ...] - used for the change report."""
        return [[label, colour or "-", line]
                for label, segments in self.sections
                for colour, lines, _ in segments if colour != "BREAK" for line in lines]


def seg(colour, lines, prefix=""):
    return (colour, list(lines), prefix)


BOX_BREAK = ("BREAK", [], "")   # splits a section into two code boxes


# ----------------------------------------------------------------------------
# Building posts
# ----------------------------------------------------------------------------
def tier_name(ruleset, idx):
    return str(ruleset["Tiers"][idx]["Name"]).upper()


def combo_name(d, combo):
    return " + ".join(d.perk(p) for p in combo)


def perk_section(post, label, d, ruleset, indv, combos, tiers, general_label,
                 wl_perks, wl_combos):
    red = sort_names(d.perk(p) for p in indv)
    red += sort_names(combo_name(d, c) + COMBO_SUFFIX for c in combos)
    tier_lines = [TIER_POINTER.format(name=tier_name(ruleset, t)) for t in sorted(tiers) if t != 0]
    if 0 in tiers:
        tier_lines.append(general_label)
    green = [ALLOWED_PREFIX + n for n in sort_names(d.perk(p) for p in wl_perks)]
    green += [ALLOWED_PREFIX + n for n in sort_names(combo_name(d, c) for c in wl_combos)]
    # box 1: tier bans; box 2 (separate code box): individual bans / combos / allowed perks
    if not red and not green and not tier_lines:
        post.add(label, seg(RED, [NONE_TEXT]))
        return
    post.add(label, seg(RED, tier_lines, PERK_BAN_PREFIX), BOX_BREAK,
             seg(RED, red, PERK_BAN_PREFIX), seg(GREEN, green, PERK_ALLOW_PREFIX))


def item_lines(k, d, fc_count):
    """-> (lines, firecracker_line_written)"""
    lines, used_fc = [], False
    for iid in sorted(k["ItemWhitelist"]):
        item = d.item(iid)
        if item is None:
            lines.append(f"<unknown item {iid}>")
            continue
        name, typ = item["Name"], item["Type"]
        addon_ids = k["AddonWhitelist"].get(typ, {}).get("Addons", [])
        if typ == "Firecracker":
            used_fc = True
            if fc_count and fc_count > 1:
                name += f" x{fc_count}"
        elif addon_ids or d.item_addons.get(typ):
            names = [d.item_addon(typ, a) for a in addon_ids]
            name += f" with {join_and(names)}" if names else " with no addons"
        lines.append(name)
    return (lines or ["No items"]), used_fc


def killer_post(k, d, ruleset):
    name = k["Name"]
    post = Post(name)

    # notes: pick out the ones we turn into formatting
    note_lines = [ln.strip() for ln in k["KillerNotes"].splitlines() if ln.strip()]
    fc_count, double_vigo = None, False
    for ln in note_lines:
        m = FIRECRACKER_RE.search(ln)
        if m:
            fc_count = NUMWORDS[m.group(1).lower()]
        if DOUBLE_VIGO_RE.match(ln):
            double_vigo = True

    d.ctx = f"{name} > Maps"
    post.add(L_MAPS, seg(WHITE, [d.map(m) for m in k["Map"]] or [NONE_TEXT]))

    d.ctx = f"{name} > Addon bans"
    banned = [d.addon(a) for a in k["IndividualAddonBans"]]  # keep ruleset order
    post.add(L_ADDONS,
             seg(RED, banned, ADDON_BAN_PREFIX),
             seg(GREEN, [ALL_OTHER_ADDONS if banned else ALL_ADDONS], ALL_ADDONS_OK_PREFIX))

    d.ctx = f"{name} > Killer perks"
    perk_section(post, L_KPERKS, d, ruleset, k["KillerIndvPerkBans"], k["KillerComboPerkBans"],
                 k["BalanceTiers"], GENERAL_POINTER_KILLER,
                 k["KillerWhitelistedPerks"], k["KillerWhitelistedComboPerks"])
    d.ctx = f"{name} > Survivor perks"
    perk_section(post, L_SPERKS, d, ruleset, k["SurvivorIndvPerkBans"], k["SurvivorComboPerkBans"],
                 k["SurvivorBalanceTiers"], GENERAL_POINTER_SURVIVOR,
                 k["SurvivorWhitelistedPerks"], k["SurvivorWhitelistedComboPerks"])

    d.ctx = f"{name} > Items"
    lines, used_fc = item_lines(k, d, fc_count)
    post.add(L_ITEMS, seg(GREEN, lines))

    d.ctx = f"{name} > Killer offerings"
    ko = [d.killer_offering(i) for i in sorted(k["KillerOfferings"])]
    post.add(L_KOFF, seg(WHITE, ko or [NONE_TEXT]))

    d.ctx = f"{name} > Survivor offerings"
    so = [d.survivor_offering(i) for i in sorted(k["SurvivorOfferings"])]
    used_vigo = False
    if double_vigo:
        for n, off in enumerate(so):
            if off == VIGO_SHROUD:
                so[n] = off + " x2"
                used_vigo = True
    post.add(L_SOFF, seg(WHITE, so or [NONE_TEXT]))

    # Notes block (first): everything except the notes that became formatting.
    # If a note could not be applied (e.g. no Firecracker on the item list), it stays as a note.
    leftover = []
    for ln in note_lines:
        if FIRECRACKER_RE.search(ln) and used_fc:
            continue
        if DOUBLE_VIGO_RE.match(ln) and used_vigo:
            continue
        leftover.append(ln)
    if leftover:
        post.sections.insert(0, (L_NOTES, [seg(None, leftover)]))

    if k.get("AddonTiersBanned"):
        d.warnings.add(f"{name}: AddonTiersBanned is set but not supported yet - ignored")
    if k.get("AntiFacecampPermitted"):
        d.warnings.add(f"{name}: AntiFacecampPermitted is true but not shown in posts")
    return post


def tier_post(idx, tier, d, ruleset):
    title = GENERAL_TITLE if idx == 0 else TIER_TITLE.format(name=tier_name(ruleset, idx))
    d.ctx = f"{title} post"
    post = Post(title)
    sections = [
        (L_T_KPERKS, sort_names(d.perk(p) for p in tier["KillerIndvPerkBans"])),
        (L_T_SPERKS, sort_names(d.perk(p) for p in tier["SurvivorIndvPerkBans"])),
        (L_T_KCOMBO, sort_names(combo_name(d, c) for c in tier["KillerComboPerkBans"])),
        (L_T_SCOMBO, sort_names(combo_name(d, c) for c in tier["SurvivorComboPerkBans"])),
    ]
    for label, lines in sections:
        if lines:
            post.add(label, seg(RED, lines, PERK_BAN_PREFIX))
    if not post.sections:
        post.add("Bans", seg(WHITE, [NONE_TEXT]))
    return post


def build_all(ruleset, d):
    posts = {}
    for k in ruleset["KillerOverride"]:
        if k.get("IsDisabled"):
            if not d.silent:
                d.warnings.add(f"{k['Name']} is disabled in the ruleset - no post generated")
            continue
        posts[f"killer:{k['Name']}"] = killer_post(k, d, ruleset)
    for i, t in enumerate(ruleset["Tiers"]):
        posts[f"tier:{t['Name']}"] = tier_post(i, t, d, ruleset)
    return posts


# ----------------------------------------------------------------------------
# GitHub
# ----------------------------------------------------------------------------
class GitHubError(Exception):
    pass


def parse_github_url(url):
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/(?:blob|raw)/([^/]+)/(.+)$", url.strip())
    if not m:
        raise GitHubError("That doesn't look like a link to a file on GitHub. It should look like "
                          "https://github.com/<user>/<repo>/blob/<branch>/<file>.json")
    return {"owner": m[1], "repo": m[2], "branch": m[3], "path": urllib.parse.unquote(m[4])}


def http_get(url, accept=None, auth=True):
    headers = {"User-Agent": "balance-posts-script"}
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and auth:
        headers["Authorization"] = f"token {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
            return r.read().decode("utf-8-sig")
    except urllib.error.HTTPError as e:
        hint = ""
        if e.code == 404:
            hint = " (not found - is the repo private? set the GITHUB_TOKEN environment variable)"
        elif e.code in (403, 429):
            hint = " (GitHub rate limit reached - wait a bit or set GITHUB_TOKEN)"
        raise GitHubError(f"HTTP {e.code} for {url}{hint}")
    except urllib.error.URLError as e:
        raise GitHubError(f"Could not reach GitHub ({e.reason}). Check your internet connection.")


def get_commits(gh):
    """Newest-first list of {"sha","message","date"} for commits that touched the ruleset file."""
    path_q = urllib.parse.quote(gh["path"])
    try:
        url = (f"https://api.github.com/repos/{gh['owner']}/{gh['repo']}/commits"
               f"?sha={urllib.parse.quote(gh['branch'])}&path={path_q}&per_page=100")
        data = json.loads(http_get(url, accept="application/vnd.github+json"))
        return [{"sha": c["sha"], "message": c["commit"]["message"].splitlines()[0],
                 "date": c["commit"]["author"]["date"][:10]} for c in data]
    except (GitHubError, ValueError, KeyError):
        pass  # API limit etc. - fall back to the public commit feed (no rate limit)
    url = (f"https://github.com/{gh['owner']}/{gh['repo']}/commits/"
           f"{urllib.parse.quote(gh['branch'])}/{path_q}.atom")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(http_get(url).encode("utf-8"))
    commits = []
    for e in root.findall("a:entry", ns):
        commits.append({"sha": e.find("a:id", ns).text.rsplit("/", 1)[-1],
                        "message": (e.find("a:title", ns).text or "").strip(),
                        "date": e.find("a:updated", ns).text[:10]})
    if not commits:
        raise GitHubError("No commits found for that file - check your ruleset link (python balance.py --set-url).")
    return commits


def fetch_ruleset(gh, ref):
    url = (f"https://raw.githubusercontent.com/{gh['owner']}/{gh['repo']}/{ref}/"
           f"{urllib.parse.quote(gh['path'])}")
    return json.loads(http_get(url))


def _count(o):
    """Number of records (dicts) anywhere inside a JSON structure."""
    if isinstance(o, dict):
        return 1 + sum(_count(v) for v in o.values())
    if isinstance(o, list):
        return sum(_count(v) for v in o)
    return 0


def sync_data(data_dir):
    """Download the newest data lists from the site creator's repo into data_dir."""
    r = DATA_REPO
    base = f"https://raw.githubusercontent.com/{r['owner']}/{r['repo']}/{r['branch']}/"
    data_dir.mkdir(parents=True, exist_ok=True)
    updated, problems = [], []
    for local, path in DATA_SOURCES.items():
        target = data_dir / local
        try:
            text = http_get(base + urllib.parse.quote(path), auth=False)
            new = json.loads(text)
            if not new:
                raise ValueError("file is empty")
        except (GitHubError, ValueError) as e:
            problems.append(f"{local}: {e}")
            continue
        old = None
        if target.exists():
            try:
                old = json.loads(target.read_text(encoding="utf-8-sig"))
            except ValueError:
                old = None
        if old == new:
            continue
        if old is not None and _count(new) < _count(old):
            problems.append(f"{local}: repo copy has FEWER entries than your saved copy - kept yours")
            continue
        target.write_text(text, encoding="utf-8", newline="")
        updated.append(f"{local} ({_count(new) - _count(old):+d} entries)" if old is not None
                       else f"{local} (new)")
    if updated:
        print("Data lists updated from the Balanced by Daylight repo: " + ", ".join(updated))
    elif not problems:
        print("Data lists are up to date.")
    if problems and len(problems) == len(DATA_SOURCES) and all("Could not reach" in x for x in problems):
        print("Could not reach GitHub to refresh the data lists - using the saved copies in data/.")
    else:
        for pr in problems:
            print(f"Could not update {pr}")
        if problems:
            print("(Using the saved copies in data/ for those.)")


# ----------------------------------------------------------------------------
# Ruleset link (asked once, then remembered in config.json)
# ----------------------------------------------------------------------------
def load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def ask_for_url():
    print("Paste the GitHub link to your ruleset .json file.")
    print("(Open the file on github.com and copy the address bar, e.g.")
    print(" https://github.com/<user>/<repo>/blob/main/Ruleset.json)\n")
    while True:
        try:
            url = input("Ruleset link (Enter to cancel): ").strip()
        except EOFError:
            url = ""
        if not url:
            sys.exit("No link given - nothing to do.")
        try:
            parse_github_url(url)
            return url
        except GitHubError as e:
            print(f"  ! {e}\n")


def get_ruleset_url(set_url_arg):
    """Return the saved ruleset link; ask for it (and save it) if missing or if --set-url was used."""
    cfg = load_config()
    if set_url_arg is None and cfg.get("ruleset_url"):
        return cfg["ruleset_url"]
    if set_url_arg not in (None, "ASK"):
        url = set_url_arg
        parse_github_url(url)                      # validates, raises a clear error if wrong
    elif sys.stdin.isatty():
        url = ask_for_url()
    else:
        sys.exit("No ruleset link saved yet. Run the script in a terminal to enter it, "
                 "or use:  python balance.py --set-url <github link>")
    cfg["ruleset_url"] = url
    CONFIG_FILE.write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    print(f"Saved ruleset link to {CONFIG_FILE.name}.\n")
    return url


# ----------------------------------------------------------------------------
# Comparison + report
# ----------------------------------------------------------------------------
def diff_lines(old_flat, new_flat):
    old = {tuple(x) for x in old_flat}
    new = {tuple(x) for x in new_flat}
    return ([x for x in old_flat if tuple(x) not in new],
            [x for x in new_flat if tuple(x) not in old])


def compare(new, old):
    """-> list of (key, status, removed_lines, added_lines)"""
    out = []
    for key, post in new.items():
        if old is None or key not in old:
            out.append((key, "new", [], []))
        elif old[key].body() != post.body() or old[key].title != post.title:
            rem, add = diff_lines(old[key].flat(), post.flat())
            out.append((key, "changed", rem, add))
    for key in (old or {}):
        if key not in new:
            out.append((key, "removed", [], []))
    return out


def print_report(changes, new, old):
    if not changes:
        print("No post changes.")
        return
    for key, status, rem, add in changes:
        post = new.get(key) or old[key]
        kind = "Tier post" if key.startswith("tier:") else "Killer"
        print(f"[{status.upper():7}] {kind}: {post.title}")
        if status == "changed":
            order = []
            for r in rem + add:
                if r[0] not in order:
                    order.append(r[0])
            for sec in order:
                for r in (r for r in rem if r[0] == sec):
                    print(f"      - {sec}: {r[2]}")
                for a in (a for a in add if a[0] == sec):
                    print(f"      + {sec}: {a[2]}")
    counts = {s: sum(1 for c in changes if c[1] == s) for s in ("new", "changed", "removed")}
    print(f"\nSummary: {counts['new']} new, {counts['changed']} changed, {counts['removed']} removed")
    if counts["removed"]:
        print("(Removed = that killer/tier no longer has a post; delete the old Discord post yourself.)")


def safe_name(s):
    return re.sub(r'[<>:"/\\|?*]', "", s).strip() or "post"


def write_posts(posts, keys, out_root, tag):
    if not keys:
        return None
    folder = Path(out_root) / f"{datetime.now().strftime('%Y-%m-%d_%H%M%S')}_{tag}"
    folder.mkdir(parents=True, exist_ok=True)
    for key in keys:
        p = posts[key]
        (folder / f"{safe_name(p.title)}.txt").write_text(p.body(), encoding="utf-8", newline="\n")
    return folder


# ----------------------------------------------------------------------------
# "Last posted" marker
# ----------------------------------------------------------------------------
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {}


def save_state(commit, url):
    STATE_FILE.write_text(json.dumps({"url": url, "sha": commit["sha"], "date": commit["date"],
                                      "message": commit["message"],
                                      "saved_at": datetime.now().isoformat(timespec="seconds")},
                                     indent=1), encoding="utf-8")


def confirm(prompt):
    try:
        return input(prompt + " [y/N]: ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Generate Discord balancing posts from your GitHub-hosted ruleset")
    ap.add_argument("source", nargs="?", help="optional: a local ruleset .json (default: your GitHub file)")
    ap.add_argument("--data", default=str(BASE / "data"), help="folder with the CompDBD*/NewMaps json files")
    ap.add_argument("--out", default=str(BASE / "output"))
    ap.add_argument("--all", action="store_true", help="write every post, not only changed ones")
    ap.add_argument("--print", dest="show", action="store_true", help="print written posts to the terminal")
    ap.add_argument("--no-save", action="store_true", help="never update the saved 'last posted' version")
    ap.add_argument("--no-data-update", action="store_true",
                    help="do not download the newest perk/addon/map/item/offering lists")
    ap.add_argument("--set-url", nargs="?", const="ASK", default=None, metavar="LINK",
                    help="change the saved ruleset link (give the link, or leave empty to be asked)")
    ap.add_argument("--since", help="compare against this GitHub commit id instead of the saved one")
    args = ap.parse_args()

    if not args.no_data_update:
        sync_data(Path(args.data))
    d = Data(args.data)
    local = bool(args.source)
    latest = None
    old_rs = None

    if local:
        new_rs = json.loads(Path(args.source).read_text(encoding="utf-8-sig"))
        print(f"Using local file {args.source} (no comparison, nothing is saved).")
    else:
        url = get_ruleset_url(args.set_url)
        gh = parse_github_url(url)
        print(f"Checking GitHub: {gh['owner']}/{gh['repo']} ({gh['branch']}) ...")
        commits = get_commits(gh)
        latest = commits[0]
        new_rs = fetch_ruleset(gh, latest["sha"])
        state = load_state()
        if state.get("url") and state["url"] != url:
            print("(Your saved 'last posted' version belongs to a different ruleset link - ignoring it.)")
            state = {}
        last_sha = args.since or state.get("sha")
        print(f"Latest version: {latest['sha'][:7]}  ({latest['date']})")
        if not last_sha:
            print("No previous 'last posted' version saved - this is a first run, every post is new.")
        elif last_sha.startswith(latest["sha"][:len(last_sha)]) or latest["sha"].startswith(last_sha):
            print("You last posted this exact version - comparing shows nothing new.")
            old_rs = new_rs
        else:
            ids = [c["sha"] for c in commits]
            idx = next((i for i, s in enumerate(ids) if s.startswith(last_sha)), None)
            if idx is not None:
                print(f"\nCommits on GitHub since you last posted ({idx}):")
                for c in commits[:idx]:
                    print(f"  {c['date']}  {c['sha'][:7]}  {c['message']}")
            else:
                print("\n(Your last posted version is older than the recent history GitHub lists.)")
            try:
                old_rs = fetch_ruleset(gh, last_sha)
            except (GitHubError, ValueError) as e:
                print(f"Could not load your last posted version ({e}) - treating every post as new.")

    print(f"Ruleset: {new_rs.get('Name')}\n")
    posts = build_all(new_rs, d)

    old_posts = None
    if old_rs is not None:
        d.silent = True
        try:
            old_posts = build_all(old_rs, d)
        except (KeyError, TypeError, IndexError, ValueError) as e:
            print(f"Could not read the old version's format ({e!r}) - treating every post as new.")
        d.silent = False

    changes = compare(posts, old_posts)
    print_report(changes, posts, old_posts)

    if d.warnings:
        print("\nWarnings:")
        for w in sorted(d.warnings):
            print("  !", w)

    to_write = list(posts) if args.all else [c[0] for c in changes if c[0] in posts]
    folder = write_posts(posts, to_write, args.out, "local" if local else latest["sha"][:7])
    if folder:
        print(f"\nWrote {len(to_write)} post file(s) to: {folder}")
        if args.show:
            for key in to_write:
                print("\n" + "=" * 60 + f"\n{posts[key].title}\n" + "=" * 60)
                print(posts[key].body())
    else:
        print("\nNothing to post.")

    if local or args.no_save:
        return
    if changes:
        if sys.stdin.isatty():
            print()
            if confirm("Did you post these? (would you like to update the saved ruleset to the latest version?)"):
                save_state(latest, url)
                print("Saved. Next run will compare against this version.")
            else:
                print("Not saved - these changes will show up again next run.")
        else:
            print("\n(Not running in a terminal, so I did not ask whether to update the saved version.)")
    elif state.get("sha") != latest["sha"]:
        save_state(latest, url)
        print("Saved the latest version as your last posted version (nothing needed posting).")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
    except GitHubError as e:
        sys.exit(f"GitHub problem: {e}")
