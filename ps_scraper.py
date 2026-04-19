"""
ps_scraper.py  —  Matthew Q4 Assignment Tracker
Sources: PowerSchool (2-pass) + Canvas (Playwright browser) + Gmail notifications
Outputs: data/assignments.json, data/completed.json, index.html, completed.html
"""

import json, os, re, time
from datetime import datetime, date
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

# ── Config ─────────────────────────────────────────────────────────────────
PS_BASE      = "https://westbloomfield.powerschool.com"
PS_USER      = os.environ.get("PS_USERNAME", "")
PS_PASS      = os.environ.get("PS_PASSWORD", "")
CANVAS_BASE  = "https://westbloomfieldsd.instructure.com"
CANVAS_TOKEN = os.environ.get("CANVAS_TOKEN",
    "16592~UHBmMt4U3Qhn7P8kvufhcatxQCnEHEEFWz69AWr9U4PzFLYMKCmFMTva9VzNcycw")
CANVAS_EMAIL    = "wbfnicholsm07@student.wbsd.org"
CANVAS_PASSWORD = os.environ.get("CANVAS_STUDENT_PASSWORD", "")
GMAIL_TOKEN_FILE = Path(os.environ.get("GMAIL_TOKEN", "gmail_token.json"))
DATA_DIR = Path("data")
MAX_COMPLETED_PER_COURSE = 8
Q4_START = date(2026, 3, 30)
Q4_END   = date(2026, 6, 5)

LATE_PENALTY_COURSES = {"civics", "earth sci", "earth science",
                        "multicultural lit", "multcult lit", "multcult lit 11 s2"}

CANVAS_COURSES = {
    "29168": "Interior Design",
    "28876": "Algebra 2",
    "30361": "Civics",
    "28927": "Earth Science",
    "29422": "CAD Engineering",
    "29366": "French 1",
    "29304": "Multicultural Lit",
}

MATTHEW_COURSE_FRNS = [
    ("Earth Science",     "0042287836"),
    ("Multicultural Lit", "0042291490"),
    ("Algebra 2",         "0042291559"),
    ("Civics",            "0042291530"),
    ("French 1",          "0042291537"),
    ("Interior Design",   "0042287823"),
    ("CAD Engineering",   "0042291544"),
]

PS_NAV_JUNK = {
    "forms", "special education home", "state assessments",
    "applications description", "course due date assignment category teacher",
    "applications", "description", "course due date"
}

TEACHER_EMAILS = {
    "Civics":           "lwatson@wbsd.org",
    "Earth Science":    "bmcguire@wbsd.org",
    "Multicultural Lit":"jsharpe@wbsd.org",
    "Interior Design":  "mmattson@wbsd.org",
    "CAD Engineering":  "cmuylaert@wbsd.org",
    "Algebra 2":        "jpruitt@wbsd.org",
    "French 1":         "mbishop@wbsd.org",
}

# ── Helpers ────────────────────────────────────────────────────────────────
def parse_date(s):
    if not s: return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y"):
        try: return datetime.strptime(s.strip(), fmt).date()
        except ValueError: pass
    return None

def fmt_date(d):
    if not d: return ""
    if isinstance(d, str): d = parse_date(d)
    return d.strftime("%m/%d/%Y") if d else ""

def has_penalty(course):
    return any(k in course.lower() for k in LATE_PENALTY_COURSES)

def canvas_hdr():
    return {"Authorization": f"Bearer {CANVAS_TOKEN}"}

def load_json(p, default):
    try: return json.loads(Path(p).read_text())
    except: return default

def save_json(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(data, indent=2))

def normalize(s):
    return re.sub(r'\s+', ' ', s.lower().strip())

def clean_course(name):
    import unicodedata
    name = unicodedata.normalize("NFKD", name)
    name = name.split("\n")[0].split("\xa0")[0].strip()
    name = re.sub(r'\s+S2.*$', '', name, flags=re.IGNORECASE).strip()
    return name

def course_match(a, b):
    a, b = clean_course(str(a)).lower(), clean_course(str(b)).lower()
    return a in b or b in a or (len(a) > 4 and len(b) > 4 and a[:5] == b[:5])

def match_course_name(raw):
    raw_c = clean_course(raw).lower()
    for cname in list(CANVAS_COURSES.values()):
        if course_match(cname, raw_c): return cname
    if "earth" in raw_c: return "Earth Science"
    if "civ" in raw_c: return "Civics"
    if "mult" in raw_c or "sharpe" in raw_c: return "Multicultural Lit"
    if "algebra" in raw_c or "pruitt" in raw_c: return "Algebra 2"
    if "french" in raw_c or "bishop" in raw_c: return "French 1"
    if "interior" in raw_c or "mattson" in raw_c: return "Interior Design"
    if "cad" in raw_c or "engr" in raw_c or "muylaert" in raw_c: return "CAD Engineering"
    return clean_course(raw)

def make_assignment(course, name, due_raw, canvas_url="", source=""):
    due_d = parse_date(due_raw)
    return {
        "course": course,
        "assignment_name": name,
        "due_date": fmt_date(due_d),
        "canvas_url": canvas_url,
        "teacher_email": TEACHER_EMAILS.get(course, ""),
        "late_penalty": has_penalty(course),
        "submitted": False,
        "graded": False,
        "sources": [source] if source else [],
        "schedule_days": [],
    }

def is_ungraded_score(score_raw):
    s = (score_raw or "").strip()
    if not s or s in ["-", "—", "--", "N/A"]: return True
    m = re.match(r'^([\d.]+)\s*/\s*([\d.]+)$', s)
    if m: return float(m.group(1)) == 0.0
    return False

# ── Canvas (Playwright browser login) ──────────────────────────────────────
def scrape_canvas_playwright(page):
    result = {}

    print("  Logging into Canvas...")
    page.goto(f"{CANVAS_BASE}/login/canvas", wait_until="networkidle")
    time.sleep(1)

    try:
        page.fill('#pseudonym_session_unique_id', CANVAS_EMAIL, timeout=5000)
        page.fill('#pseudonym_session_password', CANVAS_PASSWORD, timeout=5000)
        time.sleep(1)
        page.keyboard.press("Enter")
        page.wait_for_load_state("networkidle", timeout=20000)
        print(f"  Canvas logged in: {page.url}")
    except Exception as e:
        print(f"  Canvas login failed: {e}")
        return result

    if "login" in page.url.lower():
        print("  Canvas login redirect failed — check CANVAS_STUDENT_PASSWORD secret")
        return result

    for cid, cname in CANVAS_COURSES.items():
        try:
            url = f"{CANVAS_BASE}/courses/{cid}/assignments?bucket=missing"
            page.goto(url, wait_until="networkidle", timeout=20000)
            time.sleep(1)

            items = page.query_selector_all("li.assignment")
            print(f"  {cname}: {len(items)} missing")

            for item in items:
                try:
                    title_el = item.query_selector(".ig-title")
                    due_el   = item.query_selector(".assignment-date-due")

                    title = title_el.inner_text().strip() if title_el else ""
                    if not title:
                        continue

                    due_raw = ""
                    if due_el:
                        due_text = due_el.inner_text().strip()
                        due_text = re.sub(r'^Due:\s*', '', due_text, flags=re.IGNORECASE).strip()
                        due_text = re.sub(r'\s+at\s+\d+:\d+\w+.*$', '', due_text, flags=re.IGNORECASE).strip()
                        due_raw = due_text

                    due_d = parse_date(due_raw)
                    if due_d and (due_d < Q4_START or due_d > Q4_END):
                        continue

                    link_el = item.query_selector(".ig-title a")
                    canvas_url = ""
                    if link_el:
                        href = link_el.get_attribute("href") or ""
                        canvas_url = href if href.startswith("http") else f"{CANVAS_BASE}{href}"

                    key = (cname.lower(), normalize(title))
                    if key not in result:
                        a = make_assignment(cname, title, due_raw, canvas_url, "canvas_pw")
                        result[key] = a
                        print(f"    + {title[:60]}")

                except Exception as e:
                    print(f"    Item error in {cname}: {e}")
                    continue

        except Exception as e:
            print(f"  Canvas scrape error {cname}: {e}")
            continue

    print(f"  Canvas Playwright: {len(result)} missing assignments")
    return result

# ── Gmail ──────────────────────────────────────────────────────────────────
def parse_gmail_assignments():
    assignments = {}
    graded_signals = set()
    submitted_signals = set()
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        if not GMAIL_TOKEN_FILE.exists():
            print("  Gmail token not found, skipping")
            return assignments, graded_signals, submitted_signals
        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN_FILE))
        svc = build("gmail", "v1", credentials=creds)

        # ── Forwarded emails from Matthew ──────────────────────────────────
        result = svc.users().messages().list(
            userId="me",
            q="from:wbfnicholsm07@student.wbsd.org after:2026/03/29",
            maxResults=500).execute()
        msgs = result.get("messages", [])
        print(f"  Gmail: {len(msgs)} messages")

        for ref in msgs:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=ref["id"], format="metadata",
                    metadataHeaders=["Subject"]).execute()
                subj = next((h["value"] for h in msg.get("payload",{}).get("headers",[])
                             if h["name"] == "Subject"), "")
                subj = subj.replace("Fwd: ", "").strip()

                course = None
                for marker, cname in [
                    ("CIVICS","Civics"),("WATSON","Civics"),
                    ("EARTH SCI","Earth Science"),("MCGUIRE","Earth Science"),
                    ("MULTCULT","Multicultural Lit"),("SHARPE","Multicultural Lit"),
                    ("ALGEBRA","Algebra 2"),("PRUITT","Algebra 2"),
                    ("FRENCH","French 1"),("BISHOP","French 1"),
                    ("INTERIOR DESIGN","Interior Design"),("5TH HOUR","Interior Design"),
                    ("MATTSON","Interior Design"),
                    ("ENGRACAD","CAD Engineering"),("MUYLAERT","CAD Engineering"),
                ]:
                    if marker in subj.upper(): course = cname; break
                if not course: continue

                asgn = None
                ntype = None
                if subj.startswith("Assignment Graded: "):
                    ntype = "graded"; asgn = subj[19:]
                elif subj.startswith("Assignment Due Date Changed: "):
                    ntype = "due_changed"; asgn = subj[29:]
                elif subj.startswith("New Assignment: "):
                    ntype = "new"; asgn = subj[16:]
                elif subj.startswith("Submission Comment: MATTHEW NICHOLS, "):
                    ntype = "comment"; asgn = subj[37:]
                if not asgn: continue

                for sep in [", CIVICS",", EARTH",", MULTCULT",", ALGEBRA",
                            ", FRENCH",", 5th Hour",", ENGRACAD",", Interior",", ALGEBRA 2"]:
                    if sep.upper() in asgn.upper():
                        asgn = asgn[:asgn.upper().index(sep.upper())]
                asgn = asgn.strip()
                key = (course.lower(), normalize(asgn))

                if ntype == "graded":
                    graded_signals.add(key)
                    submitted_signals.add(key)
                    continue
                if ntype == "comment":
                    submitted_signals.add(key)
                if ntype in ("new","due_changed","comment"):
                    if key not in assignments:
                        assignments[key] = make_assignment(course, asgn, "", source="gmail")
            except: pass

        # ── Weekly digest parser ───────────────────────────────────────────
        digest_result = svc.users().messages().list(
            userId="me",
            q="subject:\"Recent Canvas Notifications\" after:2026/03/29",
            maxResults=20).execute()
        digest_msgs = digest_result.get("messages", [])
        print(f"  Gmail digest: {len(digest_msgs)} weekly digests")

        for ref in digest_msgs:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=ref["id"], format="full").execute()
                body = ""
                parts = msg.get("payload", {}).get("parts", [])
                if parts:
                    for part in parts:
                        if part.get("mimeType") == "text/plain":
                            import base64
                            data = part.get("body", {}).get("data", "")
                            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")
                            break
                else:
                    import base64
                    data = msg.get("payload", {}).get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="ignore")

                if not body:
                    continue

                blocks = re.split(r'-{10,}', body)
                for block in blocks:
                    block = block.strip()
                    if not block:
                        continue

                    m = re.match(r'Assignment Created\s*-\s*(.+?),\s*([A-Z].+?)(?:\n|$)', block)
                    if not m:
                        continue

                    asgn_name = m.group(1).strip()
                    course_raw = m.group(2).strip()
                    course = match_course_name(course_raw)

                    due_raw = ""
                    due_m = re.search(r'due:\s*(.+?)(?:\n|$)', block, re.IGNORECASE)
                    if due_m:
                        due_raw = due_m.group(1).strip()
                        if "no due" in due_raw.lower():
                            due_raw = ""

                    url_m = re.search(r'(https://westbloomfieldsd\.instructure\.com/courses/\S+)', block)
                    canvas_url = url_m.group(1).strip() if url_m else ""

                    due_d = parse_date(due_raw)
                    if due_d and (due_d < Q4_START or due_d > Q4_END):
                        continue

                    key = (course.lower(), normalize(asgn_name))
                    if key not in assignments:
                        a = make_assignment(course, asgn_name, due_raw, canvas_url, "gmail_digest")
                        assignments[key] = a
                        print(f"  [digest] {course}: {asgn_name[:50]}")

            except Exception as e:
                print(f"  Digest parse error: {e}")
                continue

        # ── Direct Canvas notifications to jetboy2go@gmail.com ────────────
        direct_result = svc.users().messages().list(
            userId="me",
            q="from:notifications@instructure.com to:jetboy2go@gmail.com subject:\"Assignment Created\" after:2026/03/29",
            maxResults=100).execute()
        direct_msgs = direct_result.get("messages", [])
        print(f"  Gmail direct: {len(direct_msgs)} assignment created emails")

        for ref in direct_msgs:
            try:
                msg = svc.users().messages().get(
                    userId="me", id=ref["id"], format="metadata",
                    metadataHeaders=["Subject"]).execute()
                subj = next((h["value"] for h in msg.get("payload", {}).get("headers", [])
                             if h["name"] == "Subject"), "")

                m = re.match(r'Assignment Created\s*-\s*(.+?),\s*(.+)$', subj)
                if not m:
                    continue

                asgn_name = m.group(1).strip()
                course_raw = m.group(2).strip()
                course = match_course_name(course_raw)

                key = (course.lower(), normalize(asgn_name))
                if key not in assignments:
                    a = make_assignment(course, asgn_name, "", "", "gmail_direct")
                    assignments[key] = a
                    print(f"  [direct] {course}: {asgn_name[:50]}")

            except Exception as e:
                print(f"  Direct parse error: {e}")
                continue

    except Exception as e:
        print(f"  Gmail error: {e}")

    print(f"  Gmail: {len(assignments)} new asgn, {len(graded_signals)} graded, {len(submitted_signals)} submitted")
    return assignments, graded_signals, submitted_signals

# ── PowerSchool ────────────────────────────────────────────────────────────
def scrape_ps(canvas_map):
    ungraded = {}
    schedule = {}
    canvas_pw_asgn = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # ── Canvas Playwright scrape (student login) ───────────────────────
        print("\n=== Canvas (Playwright) ===")
        if CANVAS_PASSWORD:
            canvas_pw_asgn = scrape_canvas_playwright(page)
        else:
            print("  CANVAS_STUDENT_PASSWORD not set, skipping Canvas browser scrape")

        # ── PowerSchool Login ──────────────────────────────────────────────
        print("\n=== PowerSchool ===")
        print("  Logging in...")
        page.goto(f"{PS_BASE}/public/home.html", wait_until="networkidle")
        time.sleep(1)
        for sel in ["#fieldAccount","input[name='account']"]:
            try: page.fill(sel, PS_USER, timeout=3000); break
            except: pass
        for sel in ["#fieldPassword","input[name='pw']","input[type='password']"]:
            try: page.fill(sel, PS_PASS, timeout=3000); break
            except: pass
        clicked = False
        for sel in ["#btn-enter-sign-in","button[type=submit]","input[type=submit]"]:
            try: page.click(sel, timeout=3000); clicked = True; break
            except: pass
        if not clicked:
            try: page.press("input[type='password']","Enter")
            except: pass
        try: page.wait_for_url("**/guardian/home.html", timeout=20000)
        except: page.wait_for_load_state("networkidle", timeout=20000)

        # Handle PS interstitial message page
        if "message.powerschool.com" in page.url or "message.html" in page.url:
            print("  PS message page detected, clicking through...")
            try:
                page.click("a, button", timeout=5000)
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                page.goto(f"{PS_BASE}/guardian/home.html", wait_until="networkidle")
                time.sleep(1)

        print(f"  Logged in: {page.url}")

        # Switch to Matthew
        time.sleep(1)
        try:
            page.evaluate("switchStudent(13842)")
            time.sleep(2)
            page.wait_for_load_state("networkidle", timeout=15000)
            print(f"  Switched to Matthew: {page.url}")
        except Exception as e:
            print(f"  Student switch error: {e}")

        # Schedule
        try:
            page.goto(f"{PS_BASE}/guardian/myschedule.html", wait_until="networkidle")
            time.sleep(1)
            rows = page.query_selector_all("table tr")
            day_cols = {}
            if rows:
                for i, h in enumerate(rows[0].query_selector_all("th,td")):
                    txt = h.inner_text().strip().upper()
                    for day in ["MON","TUE","WED","THU","FRI"]:
                        if day in txt: day_cols[i] = day.capitalize()
            for row in rows[1:]:
                cells = row.query_selector_all("td")
                if not cells: continue
                first = cells[0].inner_text().strip()
                if not first or "advisory" in first.lower(): continue
                if any(j in first.lower() for j in PS_NAV_JUNK): continue
                if re.match(r'^\d+:\d+', first): continue
                days = [day_cols[i] for i in day_cols if i < len(cells)
                        and cells[i].inner_text().strip() not in ["-","—",""]]
                if days:
                    cname = match_course_name(first)
                    schedule[cname] = days
            print(f"  Schedule: {schedule}")
        except Exception as e:
            print(f"  Schedule error: {e}")

        # Pass 1: missing assignments page
        print("  Pass 1: missing page...")
        page.goto(f"{PS_BASE}/guardian/missingasmts.html?frn=&trm=Q4", wait_until="networkidle")
        time.sleep(1.5)

        tables = page.query_selector_all("table")
        for ti, tbl in enumerate(tables[:2]):
            rows = tbl.query_selector_all("tr")
            print(f"  Table {ti}: {len(rows)} rows")
            for ri, row in enumerate(rows[:5]):
                cells = row.query_selector_all("td,th")
                texts = [c.inner_text().strip()[:45] for c in cells]
                if any(t for t in texts): print(f"    R{ri}: {texts}")

        for tbl in page.query_selector_all("table"):
            rows = tbl.query_selector_all("tr")
            if not rows: continue
            header_cells = rows[0].query_selector_all("td,th")
            header_texts = [c.inner_text().strip().lower() for c in header_cells]
            if not any("assignment" in h or "due" in h for h in header_texts):
                continue
            col_course = col_due = col_asgn = -1
            for i, h in enumerate(header_texts):
                if "course" in h: col_course = i
                elif "due" in h: col_due = i
                elif "assignment" in h: col_asgn = i

            print(f"  Cols: course={col_course} due={col_due} asgn={col_asgn}")
            if col_asgn == -1: continue

            for row in rows[1:]:
                cells = row.query_selector_all("td,th")
                if not cells: continue
                texts = [c.inner_text().strip() for c in cells]

                course_raw = texts[col_course] if col_course >= 0 and col_course < len(texts) else ""
                due_raw    = texts[col_due]    if col_due    >= 0 and col_due    < len(texts) else ""
                name       = texts[col_asgn]   if col_asgn   >= 0 and col_asgn   < len(texts) else ""

                if not name or not course_raw: continue
                if any(j in course_raw.lower() for j in PS_NAV_JUNK): continue
                if "advisory" in course_raw.lower(): continue

                course = match_course_name(course_raw)
                due_d = parse_date(due_raw)
                if due_d and (due_d < Q4_START or due_d > Q4_END): continue

                key = (course.lower(), normalize(name))
                if key not in ungraded:
                    ci = canvas_map.get(normalize(name), {})
                    a = make_assignment(course, name, due_raw, ci.get("canvas_url",""), "ps_missing")
                    a["schedule_days"] = schedule.get(course, [])
                    ungraded[key] = a
                    print(f"  + [{course}] {name[:50]}")

        # Pass 2: per-course scores
        print(f"  Pass 2: {len(MATTHEW_COURSE_FRNS)} courses...")
        for cname, frn in MATTHEW_COURSE_FRNS:
            url = (f"{PS_BASE}/guardian/scores.html?frn={frn}"
                   f"&begdate=04/06/2026&enddate=06/02/2026&fg=Q4&schoolid=6171")
            try:
                page.goto(url, wait_until="networkidle")
                time.sleep(0.8)
                for row in page.query_selector_all("table tr"):
                    cells = row.query_selector_all("td")
                    if len(cells) < 2: continue
                    name = cells[0].inner_text().strip()
                    due_raw = cells[1].inner_text().strip() if len(cells) > 1 else ""
                    score_raw = cells[2].inner_text().strip() if len(cells) > 2 else ""
                    if not name or name.lower() in ["assignment","due date","score",""]: continue
                    due_d = parse_date(due_raw)
                    if due_d and (due_d < Q4_START or due_d > Q4_END): continue
                    if not is_ungraded_score(score_raw): continue
                    key = (cname.lower(), normalize(name))
                    if key not in ungraded:
                        ci = canvas_map.get(normalize(name), {})
                        a = make_assignment(cname, name, due_raw, ci.get("canvas_url",""), "ps_scores")
                        a["schedule_days"] = schedule.get(cname, [])
                        ungraded[key] = a
                        print(f"  + [{cname}] {name[:50]} [{score_raw}]")
                    elif not ungraded[key].get("canvas_url"):
                        ci = canvas_map.get(normalize(name), {})
                        ungraded[key]["canvas_url"] = ci.get("canvas_url","")
            except Exception as e:
                print(f"  Scores error {cname}: {e}")

        browser.close()

    print(f"  PS total: {len(ungraded)}")
    return ungraded, schedule, canvas_pw_asgn

# ── Merge ──────────────────────────────────────────────────────────────────
def merge_sources(ps_asgn, canvas_map, canvas_pw_asgn, gmail_asgn, graded_sigs, submitted_sigs, schedule):
    merged = dict(ps_asgn)

    for norm_name, info in canvas_map.items():
        cname = info["course_name"]
        key = (cname.lower(), norm_name)
        if key in merged:
            if not merged[key].get("canvas_url"): merged[key]["canvas_url"] = info.get("canvas_url","")
            if not merged[key].get("due_date"): merged[key]["due_date"] = fmt_date(parse_date(info.get("due_at","")))
            if "canvas" not in merged[key].get("sources",[]): merged[key].setdefault("sources",[]).append("canvas")

    for key, a in canvas_pw_asgn.items():
        if key not in merged:
            a["schedule_days"] = schedule.get(a["course"], [])
            merged[key] = a
            print(f"  [canvas_pw new] {a['course']}: {a['assignment_name'][:50]}")
        else:
            if not merged[key].get("canvas_url") and a.get("canvas_url"):
                merged[key]["canvas_url"] = a["canvas_url"]
            if "canvas_pw" not in merged[key].get("sources",[]):
                merged[key].setdefault("sources",[]).append("canvas_pw")

    for key, a in gmail_asgn.items():
        if key not in merged:
            a["schedule_days"] = schedule.get(a["course"], [])
            merged[key] = a
        else:
            if "gmail" not in merged[key].get("sources",[]): merged[key].setdefault("sources",[]).append("gmail")

    for key in merged:
        if key in submitted_sigs: merged[key]["submitted"] = True
        if key in graded_sigs: merged[key]["graded"] = True

    for key, a in merged.items():
        if not a.get("teacher_email"): a["teacher_email"] = TEACHER_EMAILS.get(a["course"],"")
        if not a.get("schedule_days"): a["schedule_days"] = schedule.get(a["course"],[])

    return merged

# ── Completed ──────────────────────────────────────────────────────────────
def try_get_grade_canvas(assignment):
    cid = None
    for course_id, cname in CANVAS_COURSES.items():
        if course_match(cname, assignment.get("course", "")): cid = course_id; break
    if not cid: return "—"
    try:
        r = requests.get(f"{CANVAS_BASE}/api/v1/courses/{cid}/assignments?per_page=100",
                         headers=canvas_hdr(), timeout=10)
        for a in (r.json() if r.ok else []):
            if normalize(a.get("name","")) == normalize(assignment.get("assignment_name","")):
                r2 = requests.get(
                    f"{CANVAS_BASE}/api/v1/courses/{cid}/assignments/{a['id']}/submissions?per_page=50",
                    headers=canvas_hdr(), timeout=10)
                for sub in (r2.json() if r2.ok else []):
                    score = sub.get("score")
                    if score is not None:
                        return f"{score}/{a.get('points_possible',0)}"
    except: pass
    return "—"

def update_completed(merged, prev_open, prev_completed):
    cur_keys = set(merged.keys())
    completed = list(prev_completed)
    for key, old in prev_open.items():
        gone = key not in cur_keys
        now_graded = key in cur_keys and merged[key].get("graded")
        if gone or now_graded:
            grade = old.get("grade","—")
            if not grade or grade == "—": grade = try_get_grade_canvas(old)
            completed.append({**old, "grade": grade, "completed_date": fmt_date(date.today())})
            if key in cur_keys: del merged[key]
    by_course = {}
    for c in completed: by_course.setdefault(c["course"],[]).append(c)
    result = []
    for items in by_course.values():
        items.sort(key=lambda x: parse_date(x.get("completed_date","")) or date.min, reverse=True)
        result.extend(items[:MAX_COMPLETED_PER_COURSE])
    return result

# ── HTML ───────────────────────────────────────────────────────────────────
CSS = """<style>
:root{--bg:#0d1117;--nav:#0f172a;--surface:#111827;--surface2:#1c2540;--border:#1e293b;
--text:#e2e8f0;--muted:#64748b;--accent:#3b82f6;--accent2:#60a5fa;--green:#10b981;
--red:#ef4444;--yellow:#f59e0b;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:14px;}
.header{background:var(--nav);border-bottom:1px solid var(--border);padding:14px 16px;
position:sticky;top:0;z-index:10;}
.header h1{font-size:16px;font-weight:700;color:var(--accent2);}
.header .meta{font-size:11px;color:var(--muted);margin-top:2px;}
.badge{background:var(--accent);color:#fff;border-radius:20px;padding:2px 9px;font-size:12px;font-weight:600;margin-left:6px;}
.badge.green{background:var(--green);}
.content{padding:12px 14px;max-width:1000px;margin:0 auto;}
.course-group{margin-bottom:18px;}
.course-label{font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
color:var(--muted);padding:8px 0 5px;border-bottom:1px solid var(--border);margin-bottom:7px;display:flex;align-items:center;gap:8px;}
.penalty-tag{font-size:9px;background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3);border-radius:4px;padding:1px 6px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:12px 14px;margin-bottom:8px;display:grid;grid-template-columns:1fr auto;gap:8px;align-items:start;}
.asgn-name{font-size:14px;font-weight:600;line-height:1.4;}
.asgn-name a{color:var(--accent2);text-decoration:none;}
.asgn-name a:hover{text-decoration:underline;}
.card-sub{font-size:11px;color:var(--muted);margin-top:4px;display:flex;align-items:center;gap:6px;flex-wrap:wrap;}
.email-btn{color:var(--muted);text-decoration:none;font-size:13px;}
.email-btn:hover{color:var(--accent2);}
.day-pill{background:var(--surface2);color:var(--muted);border-radius:4px;padding:1px 5px;font-size:10px;}
.src-tag{font-size:9px;border-radius:3px;padding:1px 5px;font-weight:700;}
.src-ps{background:rgba(59,130,246,.15);color:#93c5fd;}
.src-canvas{background:rgba(16,185,129,.15);color:#6ee7b7;}
.src-canvas-pw{background:rgba(16,185,129,.15);color:#6ee7b7;}
.src-gmail{background:rgba(245,158,11,.15);color:#fcd34d;}
.due-block{text-align:right;white-space:nowrap;}
.due-date{font-size:13px;font-weight:600;}
.due-date.overdue{color:var(--red);}
.due-date.soon{color:var(--yellow);}
.penalty-flash{font-size:16px;display:block;animation:flash .7s infinite alternate;}
@keyframes flash{from{opacity:1}to{opacity:.1}}
.status-row{display:flex;gap:4px;margin-top:5px;justify-content:flex-end;}
.status-pill{font-size:9px;border-radius:4px;padding:2px 6px;font-weight:700;}
.status-sub{background:rgba(16,185,129,.2);color:var(--green);}
.status-unsub{background:rgba(239,68,68,.15);color:var(--red);}
.sources{display:flex;gap:3px;flex-wrap:wrap;}
.empty{text-align:center;padding:40px 20px;color:var(--muted);}
.empty .icon{font-size:36px;margin-bottom:8px;}
.footer{text-align:center;padding:20px;font-size:11px;}
.footer a{color:var(--muted);text-decoration:none;}
.footer a:hover{color:var(--accent2);}
.grade{font-weight:700;color:var(--green);white-space:nowrap;}
@media(min-width:640px){
  .content{padding:20px 24px;}
  .card{display:none;}
  .course-group{display:none;}
  .tbl-wrap{display:block;}
  .header h1{font-size:18px;}
  table{width:100%;border-collapse:collapse;background:var(--surface);border-radius:10px;overflow:hidden;border:1px solid var(--border);}
  th{background:#0f172a;padding:10px 14px;text-align:left;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border);cursor:pointer;user-select:none;white-space:nowrap;}
  th:hover{color:var(--accent2);}
  th.sort-asc::after{content:" ↑";color:var(--green);}
  th.sort-desc::after{content:" ↓";color:var(--green);}
  td{padding:10px 14px;border-bottom:1px solid var(--border);vertical-align:top;line-height:1.5;}
  tr:last-child td{border-bottom:none;}
  tr:hover td{background:var(--surface2);}
}
@media(max-width:639px){.tbl-wrap{display:none;}}
</style>"""

SORT_JS = """<script>
let sd={};
function sortTbl(col,id){
  const t=document.getElementById(id);if(!t)return;
  const tb=t.tBodies[0],rows=[...tb.rows];
  const asc=sd[col]!==true;sd={};sd[col]=asc;
  t.tHead.rows[0].querySelectorAll('th').forEach((h,i)=>h.className=i===col?(asc?'sort-asc':'sort-desc'):'');
  rows.sort((a,b)=>{
    let av=a.cells[col]?.innerText.trim()||'',bv=b.cells[col]?.innerText.trim()||'';
    if([2,4].includes(col)){av=new Date(av)||'';bv=new Date(bv)||'';}
    return asc?(av<bv?-1:av>bv?1:0):(av>bv?-1:av<bv?1:0);
  });
  rows.forEach(r=>tb.appendChild(r));
}
</script>"""

def src_tags(sources):
    h = '<div class="sources">'
    for s in (sources or []):
        if "ps" in s: h += '<span class="src-tag src-ps">PS</span>'
        elif "canvas_pw" in s: h += '<span class="src-tag src-canvas-pw">CV</span>'
        elif "canvas" in s: h += '<span class="src-tag src-canvas">CV</span>'
        elif "gmail" in s: h += '<span class="src-tag src-gmail">GM</span>'
    return h + '</div>'

def due_cls(ds):
    d = parse_date(ds)
    if not d: return ""
    n = (d - date.today()).days
    if n < 0: return "overdue"
    if n <= 3: return "soon"
    return ""

def build_index(open_asgn):
    by_course = {}
    for a in open_asgn.values():
        by_course.setdefault(a["course"],[]).append(a)

    def sk(a):
        d = parse_date(a.get("due_date",""))
        return d or date(2099,12,31)

    # Mobile
    mob = ""
    for course in sorted(by_course):
        items = sorted(by_course[course], key=sk)
        pen = has_penalty(course)
        pen_html = '<span class="penalty-tag">LATE PENALTY</span>' if pen else ''
        mob += f'<div class="course-group"><div class="course-label">{course}{pen_html}</div>'
        for a in items:
            nm = (f'<a href="{a["canvas_url"]}" target="_blank">{a["assignment_name"]}</a>'
                  if a.get("canvas_url") else a["assignment_name"])
            days = "".join(f'<span class="day-pill">{d}</span>' for d in (a.get("schedule_days") or []))
            em = (f'<a href="mailto:{a["teacher_email"]}" class="email-btn" title="{a["teacher_email"]}">✉</a>'
                  if a.get("teacher_email") else "")
            dc = due_cls(a.get("due_date",""))
            pf = '<span class="penalty-flash">🚨</span>' if pen else ""
            sp = ('<span class="status-pill status-sub">submitted</span>' if a.get("submitted")
                  else '<span class="status-pill status-unsub">not submitted</span>')
            mob += f'''<div class="card">
<div><div class="asgn-name">{nm}</div>
<div class="card-sub">{em}{days}{src_tags(a.get("sources",[]))}</div></div>
<div class="due-block">{pf}<div class="due-date {dc}">{a.get("due_date","—")}</div>
<div class="status-row">{sp}</div></div></div>'''
        mob += '</div>'

    # Desktop
    all_s = sorted(open_asgn.values(), key=sk)
    rows = ""
    for a in all_s:
        nm = (f'<a href="{a["canvas_url"]}" target="_blank">{a["assignment_name"]}</a>'
              if a.get("canvas_url") else a["assignment_name"])
        em = (f'<a href="mailto:{a["teacher_email"]}" class="email-btn" title="{a["teacher_email"]}">✉</a> '
              if a.get("teacher_email") else "")
        days = "".join(f'<span class="day-pill">{d}</span>' for d in (a.get("schedule_days") or []))
        dc = due_cls(a.get("due_date",""))
        pf = "🚨 " if has_penalty(a["course"]) else ""
        sb = ('<span style="color:var(--green)">✓</span>' if a.get("submitted")
              else '<span style="color:var(--red)">✗</span>')
        rows += f"""<tr>
<td style="color:var(--muted);font-size:12px">{a["course"]}</td>
<td>{nm}<br><small style="color:var(--muted)">{em}{days}</small></td>
<td class="due-date {dc}" style="text-align:center">{pf}{a.get("due_date","—")}</td>
<td style="text-align:center">{sb}</td>
<td>{src_tags(a.get("sources",[]))}</td>
</tr>"""

    count = len(open_asgn)
    upd = datetime.now().strftime("%b %d %Y  %I:%M %p")
    empty = '<div class="empty"><div class="icon">✅</div>All clear</div>'

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Matthew – Open</title>{CSS}</head><body>
<div class="header"><div>
<h1>Matthew <span style="color:var(--muted);font-weight:400">Q4 Open</span><span class="badge">{count}</span></h1>
<div class="meta">Updated {upd}</div></div></div>
<div class="content">
{mob if open_asgn else empty}
<div class="tbl-wrap">{"" if not open_asgn else f'''<table id="mt">
<thead><tr>
<th onclick="sortTbl(0,'mt')">Course</th>
<th onclick="sortTbl(1,'mt')">Assignment</th>
<th onclick="sortTbl(2,'mt')">Due</th>
<th onclick="sortTbl(3,'mt')">Sub</th>
<th>Src</th>
</tr></thead><tbody>{rows}</tbody></table>'''}</div>
</div>
<div class="footer"><a href="completed.html">completed →</a></div>
{SORT_JS}</body></html>"""

def build_completed(completed):
    def sk(a):
        d = parse_date(a.get("completed_date",""))
        return d or date.min
    rows_data = sorted(completed, key=sk, reverse=True)

    mob = ""
    for a in rows_data:
        nm = (f'<a href="{a["canvas_url"]}" target="_blank">{a["assignment_name"]}</a>'
              if a.get("canvas_url") else a["assignment_name"])
        mob += f'''<div class="card">
<div><div style="font-size:11px;color:var(--muted);margin-bottom:2px">{a["course"]}</div>
<div class="asgn-name">{nm}</div>
<div class="card-sub">due {a.get("due_date","—")} · {a.get("completed_date","")}</div></div>
<div class="due-block"><div class="grade">{a.get("grade","—")}</div></div></div>'''

    tbl_rows = ""
    for a in rows_data:
        nm = (f'<a href="{a["canvas_url"]}" target="_blank">{a["assignment_name"]}</a>'
              if a.get("canvas_url") else a["assignment_name"])
        tbl_rows += f"""<tr>
<td style="color:var(--muted);font-size:12px">{a["course"]}</td>
<td>{nm}</td><td>{a.get("due_date","—")}</td>
<td class="grade">{a.get("grade","—")}</td>
<td>{a.get("completed_date","")}</td></tr>"""

    count = len(completed)
    upd = datetime.now().strftime("%b %d %Y  %I:%M %p")

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Matthew – Completed</title>{CSS}</head><body>
<div class="header"><div>
<h1>Matthew <span style="color:var(--muted);font-weight:400">Completed</span><span class="badge green">{count}</span></h1>
<div class="meta">Updated {upd}</div></div></div>
<div class="content">
{mob if completed else '<div class="empty"><div class="icon">📭</div>Nothing yet</div>'}
<div class="tbl-wrap">{"" if not completed else f'''<table id="ct">
<thead><tr>
<th onclick="sortTbl(0,'ct')">Course</th>
<th onclick="sortTbl(1,'ct')">Assignment</th>
<th onclick="sortTbl(2,'ct')">Due</th>
<th onclick="sortTbl(3,'ct')">Grade</th>
<th onclick="sortTbl(4,'ct')">Graded</th>
</tr></thead><tbody>{tbl_rows}</tbody></table>'''}</div>
</div>
<div class="footer"><a href="index.html">← open assignments</a></div>
{SORT_JS}</body></html>"""

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(exist_ok=True)
    prev_open_list = load_json(DATA_DIR / "assignments.json", [])
    prev_open = {(a["course"].lower(), normalize(a["assignment_name"])): a
                 for a in prev_open_list}
    prev_completed = load_json(DATA_DIR / "completed.json", [])

    print("=== Gmail ===")
    gmail_asgn, graded_sigs, submitted_sigs = parse_gmail_assignments()

    canvas_api_map = {}
    ps_asgn, schedule, canvas_pw_asgn = scrape_ps(canvas_api_map)

    print("\n=== Merge ===")
    merged = merge_sources(ps_asgn, canvas_api_map, canvas_pw_asgn, gmail_asgn, graded_sigs, submitted_sigs, schedule)
    print(f"  Total open: {len(merged)}")

    print("\n=== Completed ===")
    completed = update_completed(merged, prev_open, prev_completed)

    save_json(DATA_DIR / "assignments.json", list(merged.values()))
    save_json(DATA_DIR / "completed.json", completed)
    save_json(DATA_DIR / "schedule.json", schedule)
    print("Saved.")

    Path("index.html").write_text(build_index(merged), encoding="utf-8")
    Path("completed.html").write_text(build_completed(completed), encoding="utf-8")
    print("Done.")

if __name__ == "__main__":
    main()
