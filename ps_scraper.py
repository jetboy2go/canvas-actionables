"""
ps_scraper.py  –  Matthew Q4 ungraded assignment tracker
Two-pass PowerSchool scrape + Canvas API merge
Writes data/ps_data.json, data/completed.json
Generates index.html and completed.html
"""

import json, os, re, time
from datetime import datetime, date
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

# ── Config ─────────────────────────────────────────────────────────────────
PS_BASE      = "https://westbloomfield.powerschool.com"
PS_USER      = os.environ.get("PS_USERNAME", "Jetboy")
PS_PASS      = os.environ.get("PS_PASSWORD", "BCVdD7r8")
CANVAS_BASE  = "https://westbloomfieldsd.instructure.com/api/v1"
CANVAS_TOKEN = os.environ.get("CANVAS_TOKEN",
    "16592~UHBmMt4U3Qhn7P8kvufhcatxQCnEHEEFWz69AWr9U4PzFLYMKCmFMTva9VzNcycw")
DATA_DIR = Path("data")
OUT_DIR  = Path(".")
MAX_COMPLETED_PER_COURSE = 8

LATE_PENALTY = {"civics", "earth sci", "earth science", "multicultural lit", "multcult lit"}

CANVAS_COURSES = {
    "29168": "Interior Design",
    "28876": "Algebra 2",
    "30361": "Civics",
    "28927": "Earth Science",
    "29422": "CAD Engineering",
    "29366": "French 1",
    "29304": "Multicultural Lit",
}

Q4_START = date(2026, 3, 30)
Q4_END   = date(2026, 6, 5)

# ── Helpers ────────────────────────────────────────────────────────────────
def parse_date(s):
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None

def fmt_date(d):
    if not d: return ""
    if isinstance(d, str): d = parse_date(d)
    return d.strftime("%m/%d/%Y") if d else ""

def has_penalty(course):
    return any(k in course.lower() for k in LATE_PENALTY)

def canvas_hdr():
    return {"Authorization": f"Bearer {CANVAS_TOKEN}"}

def load_json(p, default):
    return json.loads(p.read_text()) if p.exists() else default

def save_json(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))

def clean_course(name):
    """Strip PS junk from course names (room numbers, times, teacher names)."""
    import unicodedata
    name = unicodedata.normalize("NFKD", name)
    # Take only the first line (before newline or \xa0)
    name = name.split("\n")[0].split("\xa0")[0].strip()
    return name

def course_match(name_a, name_b):
    """Fuzzy course name match."""
    a = clean_course(name_a).lower()
    b = clean_course(name_b).lower()
    return a in b or b in a or a[:6] == b[:6]

# ── Canvas API ─────────────────────────────────────────────────────────────
def get_canvas_assignments():
    """Returns {lower_name: {canvas_url, course_name, due_at}}"""
    result = {}
    for cid, cname in CANVAS_COURSES.items():
        try:
            r = requests.get(f"{CANVAS_BASE}/courses/{cid}/assignments?per_page=100",
                             headers=canvas_hdr(), timeout=15)
            for a in (r.json() if r.ok else []):
                key = a.get("name","").strip().lower()
                result[key] = {
                    "canvas_url": a.get("html_url",""),
                    "course_name": cname,
                    "course_id": cid,
                    "due_at": a.get("due_at",""),
                }
        except Exception as e:
            print(f"  Canvas error {cname}: {e}")
    print(f"  Canvas: {len(result)} assignments indexed")
    return result

def get_canvas_emails():
    """Returns {course_name: email}"""
    emails = {}
    for cid, cname in CANVAS_COURSES.items():
        try:
            r = requests.get(
                f"{CANVAS_BASE}/courses/{cid}/enrollments?type[]=TeacherEnrollment&per_page=5",
                headers=canvas_hdr(), timeout=15)
            for e in (r.json() if r.ok else []):
                em = e.get("user",{}).get("login_id","") or e.get("user",{}).get("email","")
                if em and "@" in em:
                    emails[cname] = em
                    break
        except Exception as e:
            print(f"  Canvas email error {cname}: {e}")
    print(f"  Canvas emails: {emails}")
    return emails

def fetch_canvas_grade(assignment, canvas_map):
    """Try to pull a grade from Canvas for a just-completed assignment."""
    cid = None
    for course_id, cname in CANVAS_COURSES.items():
        if course_match(cname, assignment.get("course","")):
            cid = course_id
            break
    if not cid:
        return "—"
    try:
        r = requests.get(f"{CANVAS_BASE}/courses/{cid}/assignments?per_page=100",
                         headers=canvas_hdr(), timeout=15)
        for a in (r.json() if r.ok else []):
            if a.get("name","").strip().lower() == assignment["assignment_name"].lower():
                r2 = requests.get(
                    f"{CANVAS_BASE}/courses/{cid}/assignments/{a['id']}/submissions?per_page=50",
                    headers=canvas_hdr(), timeout=15)
                for sub in (r2.json() if r2.ok else []):
                    score = sub.get("score")
                    if score is not None:
                        pts = a.get("points_possible", 0)
                        return f"{score}/{pts}"
    except Exception:
        pass
    return "—"

# ── PowerSchool Scraping ───────────────────────────────────────────────────
def scrape_schedule(page):
    """Returns {course_name: ['Mon','Tue',...]}"""
    schedule = {}
    try:
        page.goto(f"{PS_BASE}/guardian/myschedule.html", wait_until="networkidle")
        time.sleep(1)
        html = page.content()

        # Find day column indices from header row
        rows = page.query_selector_all("table tr")
        if not rows:
            return schedule

        day_cols = {}
        header_cells = rows[0].query_selector_all("th, td") if rows else []
        for i, h in enumerate(header_cells):
            txt = h.inner_text().strip().upper()
            for day in ["MON","TUE","WED","THU","FRI"]:
                if day in txt:
                    day_cols[i] = day.capitalize()

        print(f"  Schedule day columns: {day_cols}")

        PS_NAV_JUNK = {"forms", "special education home", "state assessments",
                        "applications description", "course due date assignment",
                        "applications", "description"}

        for row in rows[1:]:
            cells = row.query_selector_all("td")
            if not cells:
                continue
            first = cells[0].inner_text().strip()
            if not first or "advisory" in first.lower():
                continue
            if any(j in first.lower() for j in PS_NAV_JUNK):
                continue

            days = []
            for col_i, day_name in day_cols.items():
                if col_i < len(cells):
                    ct = cells[col_i].inner_text().strip()
                    if ct and ct not in ["-","—",""]:
                        days.append(day_name)

            if days:
                # Try to match to a Canvas course name
                matched = False
                for cname in CANVAS_COURSES.values():
                    if course_match(cname, first):
                        schedule[cname] = days
                        matched = True
                        break
                if not matched:
                    schedule[first] = days

        print(f"  Schedule: {schedule}")
    except Exception as e:
        print(f"  Schedule error: {e}")
    return schedule

def build_assignment(course, name, due_raw, canvas_map, emails, schedule):
    """Build a standard assignment dict."""
    due_date = parse_date(due_raw)
    canvas_info = canvas_map.get(name.lower(), {})
    # Match teacher email by course name
    email = ""
    for cname, em in emails.items():
        if course_match(cname, course):
            email = em
            break
    # Match schedule days
    days = []
    for cname, d in schedule.items():
        if course_match(cname, course):
            days = d
            break

    return {
        "course": course,
        "assignment_name": name,
        "due_date": fmt_date(due_date),
        "canvas_url": canvas_info.get("canvas_url",""),
        "teacher_email": email,
        "late_penalty": has_penalty(course),
        "schedule_days": days,
    }

def is_ungraded(score_raw):
    """Return True if score_raw indicates no real grade."""
    s = score_raw.strip() if score_raw else ""
    if not s or s in ["-","—","--","N/A",""]:
        return True
    m = re.match(r'^([\d.]+)\s*/\s*([\d.]+)$', s)
    if m:
        earned = float(m.group(1))
        return earned == 0.0
    return False

def scrape_ps(canvas_map, emails):
    """Main PS scrape. Returns (ungraded_list, schedule_dict)."""
    ungraded = {}  # (course_lower, name_lower) → dict
    schedule = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        # Login
        print("Logging in to PowerSchool...")
        page.goto(f"{PS_BASE}/public/home.html", wait_until="networkidle")
        time.sleep(2)

        # Dump login form details for debugging
        print("  Page title:", page.title())
        inputs = page.query_selector_all("input")
        for inp in inputs:
            print(f"  Input: id={inp.get_attribute('id')} name={inp.get_attribute('name')} type={inp.get_attribute('type')}")
        buttons = page.query_selector_all("button, input[type=submit], input[type=button]")
        for b in buttons:
            print(f"  Button: id={b.get_attribute('id')} name={b.get_attribute('name')} value={b.get_attribute('value')} text={b.inner_text()[:40] if b.inner_text() else ''}")

        # Fill username
        for sel in ["#fieldAccount", "input[name='account']", "input[name='username']", "input[type='text']"]:
            try:
                page.fill(sel, PS_USER, timeout=3000)
                print(f"  Filled username with: {sel}")
                break
            except Exception:
                continue

        # Fill password
        for sel in ["#fieldPassword", "input[name='pw']", "input[name='password']", "input[type='password']"]:
            try:
                page.fill(sel, PS_PASS, timeout=3000)
                print(f"  Filled password with: {sel}")
                break
            except Exception:
                continue

        # Click login button
        clicked = False
        for sel in ["#btn_enter", "input[type=submit]", "button[type=submit]",
                    "button:has-text('Sign In')", "button:has-text('Log In')",
                    "button:has-text('Submit')", "input[value='Sign In']",
                    "input[value='Log In']", "input[value='Submit']",
                    ".btn-primary", "#loginButton"]:
            try:
                page.click(sel, timeout=3000)
                print(f"  Clicked login with: {sel}")
                clicked = True
                break
            except Exception:
                continue

        if not clicked:
            # Last resort: press Enter on password field
            for sel in ["#fieldPassword", "input[type='password']"]:
                try:
                    page.press(sel, "Enter")
                    print("  Submitted via Enter key")
                    clicked = True
                    break
                except Exception:
                    continue

        try:
            page.wait_for_url("**/guardian/home.html", timeout=20000)
        except Exception:
            page.wait_for_load_state("networkidle", timeout=20000)
        print("  Logged in. Current URL:", page.url)

        # Switch to Matthew via PS JavaScript switchStudent() call
        # Matthew's student ID is 13842 (from link: javascript:switchStudent(13842))
        time.sleep(1.5)
        print("  Switching to Matthew via switchStudent(13842)...")
        page.evaluate("switchStudent(13842)")
        time.sleep(2)
        page.wait_for_load_state("networkidle", timeout=15000)
        print(f"  URL after switch: {page.url}")
        # Confirm we see Matthew's name on the page
        body = page.inner_text("body")[:600]
        print("  Page preview:", body[:400])

        # Teacher emails from PS
        ps_emails = scrape_ps_emails(page)
        # Merge PS emails into Canvas emails (Canvas takes priority)
        for course, em in ps_emails.items():
            if course not in emails:
                emails[course] = em

        # Schedule
        schedule = scrape_schedule(page)

        # Pass 1: /guardian/missingasmts.html?trm=Q4
        print("Pass 1: missing assignments page...")
        page.goto(f"{PS_BASE}/guardian/missingasmts.html?frn=&trm=Q4", wait_until="networkidle")
        time.sleep(1.2)

        current_course = ""
        for row in page.query_selector_all("table tr"):
            # Check for course header rows (often th or a bold td)
            headers = row.query_selector_all("th")
            if headers:
                txt = " ".join(h.inner_text().strip() for h in headers)
                if txt and "advisory" not in txt.lower():
                    current_course = txt.strip()
                continue

            cells = row.query_selector_all("td")
            if len(cells) < 2 or not current_course:
                continue
            if "advisory" in current_course.lower():
                continue

            name = cells[0].inner_text().strip()
            due_raw = cells[1].inner_text().strip() if len(cells) > 1 else ""
            if not name or name.lower() in ["assignment","name"]:
                continue

            due_d = parse_date(due_raw)
            if due_d and (due_d < Q4_START or due_d > Q4_END):
                continue

            key = (current_course.lower(), name.lower())
            if key not in ungraded:
                ungraded[key] = build_assignment(current_course, name, due_raw,
                                                  canvas_map, emails, schedule)
                ungraded[key]["source"] = "missing_page"

        print(f"  Pass 1: {len(ungraded)} assignments")

        # Pass 2: per-course scores pages
        print("Pass 2: per-course scores pages...")
        page.goto(f"{PS_BASE}/guardian/home.html", wait_until="networkidle")
        time.sleep(1)

        PS_NAV_JUNK2 = {"forms", "special education home", "state assessments",
                         "applications", "course due date"}
        course_links = []
        seen_frns = set()
        for link in page.query_selector_all("a[href*='scores.html']"):
            href = link.get_attribute("href") or ""
            cname = clean_course(link.inner_text().strip())
            if not cname or len(cname) < 3:
                continue
            if "advisory" in cname.lower():
                continue
            if any(j in cname.lower() for j in PS_NAV_JUNK2):
                continue
            # Must look like a real course (has letters, not just a grade/number)
            if re.match(r'^[\d\s\.\+\-\[\]iFDABCG]+$', cname):
                continue
            frn_m = re.search(r'frn=([\w]+)', href)
            if frn_m:
                frn = frn_m.group(1)
                if frn in seen_frns:
                    continue
                seen_frns.add(frn)
                url = (f"{PS_BASE}/guardian/scores.html?frn={frn}"
                       f"&begdate=04/06/2026&enddate=06/02/2026&fg=Q4&schoolid=6171")
                course_links.append((cname, url))

        print(f"  {len(course_links)} courses to check")

        for cname, url in course_links:
            if "advisory" in cname.lower():
                continue
            print(f"  → {cname}")
            try:
                page.goto(url, wait_until="networkidle")
                time.sleep(0.8)

                for row in page.query_selector_all("table tr"):
                    cells = row.query_selector_all("td")
                    if len(cells) < 2:
                        continue

                    name = cells[0].inner_text().strip()
                    due_raw = cells[1].inner_text().strip() if len(cells) > 1 else ""
                    score_raw = cells[2].inner_text().strip() if len(cells) > 2 else ""

                    if not name or name.lower() in ["assignment","due date","score",""]:
                        continue

                    due_d = parse_date(due_raw)
                    if due_d and (due_d < Q4_START or due_d > Q4_END):
                        continue

                    if not is_ungraded(score_raw):
                        continue

                    key = (cname.lower(), name.lower())
                    if key not in ungraded:
                        ungraded[key] = build_assignment(cname, name, due_raw,
                                                          canvas_map, emails, schedule)
                        ungraded[key]["source"] = "scores_page"

            except Exception as e:
                print(f"  Error {cname}: {e}")

        browser.close()

    print(f"Total ungraded: {len(ungraded)}")
    return list(ungraded.values()), schedule

def scrape_ps_emails(page):
    """Scrape teacher emails from teachercomments.html."""
    emails = {}
    try:
        page.goto(f"{PS_BASE}/guardian/teachercomments.html", wait_until="networkidle")
        time.sleep(1)
        for link in page.query_selector_all("a[href^='mailto:']"):
            em = link.get_attribute("href","").replace("mailto:","").strip()
            if not em or "@" not in em:
                continue
            # Try to find course name in nearest table row
            row_text = link.evaluate(
                "el => el.closest('tr') ? el.closest('tr').innerText : ''")
            if row_text:
                for cname in CANVAS_COURSES.values():
                    if course_match(cname, row_text):
                        emails[cname] = em
                        break
        print(f"  PS emails: {emails}")
    except Exception as e:
        print(f"  PS email error: {e}")
    return emails

# ── Completed tracking ─────────────────────────────────────────────────────
def update_completed(current, prev_ungraded, prev_completed, canvas_map):
    cur_keys = {(a["course"].lower(), a["assignment_name"].lower()) for a in current}
    completed = list(prev_completed)

    for old in prev_ungraded:
        key = (old["course"].lower(), old["assignment_name"].lower())
        if key not in cur_keys:
            grade = fetch_canvas_grade(old, canvas_map)
            completed.append({**old,
                               "grade": grade,
                               "completed_date": fmt_date(date.today())})

    # Keep max 8 per course (most recent)
    by_course = {}
    for c in completed:
        by_course.setdefault(c["course"], []).append(c)

    result = []
    for items in by_course.values():
        items.sort(key=lambda x: parse_date(x.get("completed_date","")) or date.min,
                   reverse=True)
        result.extend(items[:MAX_COMPLETED_PER_COURSE])
    return result

# ── HTML Generation ────────────────────────────────────────────────────────
CSS_COMMON = """
  :root {
    --bg: #0d0f18;
    --surface: #151825;
    --border: #252838;
    --text: #dde1f0;
    --muted: #636680;
    --accent: #5b8af5;
    --green: #3ecf8e;
    --red: #f55b5b;
    --font: 'JetBrains Mono', 'Fira Mono', 'Cascadia Code', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 13px;
    padding: 28px 24px;
    max-width: 1100px;
    margin: 0 auto;
  }
  h1 {
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--accent);
    margin-bottom: 4px;
  }
  .meta { color: var(--muted); font-size: 11px; margin-bottom: 22px; }
  table {
    width: 100%;
    border-collapse: collapse;
    background: var(--surface);
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid var(--border);
  }
  th {
    background: #1c2030;
    padding: 10px 14px;
    text-align: left;
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }
  td {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
    line-height: 1.6;
  }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: #1a1e2e; }
  .asgn-link { color: var(--accent); text-decoration: none; font-weight: 500; }
  .asgn-link:hover { text-decoration: underline; }
  .email-icon {
    color: var(--muted);
    font-size: 12px;
    text-decoration: none;
    margin-left: 0;
  }
  .email-icon:hover { color: var(--accent); }
  .day {
    display: inline-block;
    font-size: 9px;
    background: #252838;
    color: var(--muted);
    border-radius: 3px;
    padding: 1px 5px;
    margin-left: 3px;
    letter-spacing: 0.03em;
  }
  .penalty {
    display: inline-block;
    animation: siren 0.6s infinite alternate;
    margin-right: 3px;
  }
  @keyframes siren { from { opacity: 1; } to { opacity: 0.15; } }
  .due { white-space: nowrap; }
  .course-tag {
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.04em;
  }
  .empty-row td {
    text-align: center;
    padding: 28px;
    color: var(--muted);
  }
"""

def build_assignment_cell(a):
    name = a["assignment_name"]
    if a.get("canvas_url"):
        name_html = f'<a href="{a["canvas_url"]}" target="_blank" class="asgn-link">{name}</a>'
    else:
        name_html = f'<span>{name}</span>'

    sub = ""
    if a.get("teacher_email"):
        days_html = "".join(f'<span class="day">{d}</span>' for d in (a.get("schedule_days") or []))
        sub = (f'<div style="margin-top:3px">'
               f'<a href="mailto:{a["teacher_email"]}" class="email-icon" title="{a["teacher_email"]}">✉</a>'
               f'{days_html}</div>')
    return name_html + sub

def build_due_cell(a):
    due = a.get("due_date","")
    if a.get("late_penalty"):
        return f'<span class="penalty">🚨</span>{due}'
    return due

def build_index(ungraded):
    def sort_key(a):
        d = parse_date(a.get("due_date",""))
        return d or date(2099,12,31)
    rows = sorted(ungraded, key=sort_key)

    rows_html = ""
    for a in rows:
        rows_html += f"""
    <tr>
      <td class="course-tag">{a.get("course","")}</td>
      <td>{build_assignment_cell(a)}</td>
      <td class="due">{build_due_cell(a)}</td>
    </tr>"""

    if not rows_html:
        rows_html = '<tr class="empty-row"><td colspan="3">All clear ✓</td></tr>'

    count = len(rows)
    updated = datetime.now().strftime("%a %b %d %Y  %I:%M %p")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Matthew – Q4 Open</title>
<style>
{CSS_COMMON}
  .badge {{
    display: inline-block;
    background: var(--accent);
    color: #fff;
    border-radius: 20px;
    padding: 1px 10px;
    font-size: 11px;
    margin-left: 8px;
    vertical-align: middle;
  }}
  .footer {{
    margin-top: 14px;
    text-align: right;
    font-size: 10px;
  }}
  .footer a {{ color: var(--border); text-decoration: none; }}
  .footer a:hover {{ color: var(--muted); }}
</style>
</head>
<body>
<h1>Matthew &mdash; Q4 Open Assignments <span class="badge">{count}</span></h1>
<div class="meta">Updated {updated}</div>
<table>
  <thead><tr>
    <th>Course</th>
    <th>Assignment</th>
    <th>Due</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
<div class="footer"><a href="completed.html">completed &rarr;</a></div>
</body>
</html>"""

def build_completed(completed):
    def sort_key(a):
        d = parse_date(a.get("completed_date",""))
        return d or date.min

    rows = sorted(completed, key=sort_key, reverse=True)

    rows_html = ""
    for a in rows:
        rows_html += f"""
    <tr>
      <td class="course-tag">{a.get("course","")}</td>
      <td>{build_assignment_cell(a)}</td>
      <td class="due">{a.get("due_date","")}</td>
      <td class="grade">{a.get("grade","—")}</td>
      <td class="due">{a.get("completed_date","")}</td>
    </tr>"""

    if not rows_html:
        rows_html = '<tr class="empty-row"><td colspan="5">Nothing completed yet</td></tr>'

    updated = datetime.now().strftime("%a %b %d %Y  %I:%M %p")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Matthew – Completed</title>
<style>
{CSS_COMMON}
  th {{ cursor: pointer; user-select: none; }}
  th:hover {{ color: var(--green); }}
  th.sort-asc::after {{ content: " ↑"; color: var(--green); }}
  th.sort-desc::after {{ content: " ↓"; color: var(--green); }}
  .grade {{ font-weight: 600; color: var(--green); white-space: nowrap; }}
  .back {{ margin-top: 14px; font-size: 10px; }}
  .back a {{ color: var(--muted); text-decoration: none; }}
  .back a:hover {{ color: var(--accent); }}
</style>
</head>
<body>
<h1>Matthew &mdash; Completed Q4</h1>
<div class="meta">Updated {updated}</div>
<table id="ctbl">
  <thead><tr>
    <th onclick="sort(0)">Course</th>
    <th onclick="sort(1)">Assignment</th>
    <th onclick="sort(2)">Due</th>
    <th onclick="sort(3)">Grade</th>
    <th onclick="sort(4)">Graded</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
</table>
<div class="back"><a href="index.html">&larr; back</a></div>
<script>
let dirs = {{}};
function sort(col) {{
  const tbl = document.getElementById('ctbl');
  const tb = tbl.tBodies[0];
  const rows = [...tb.rows];
  const asc = dirs[col] !== true;
  dirs = {{}};
  dirs[col] = asc;
  tbl.tHead.rows[0].querySelectorAll('th').forEach((h,i) => h.className = i===col ? (asc?'sort-asc':'sort-desc') : '');
  rows.sort((a,b) => {{
    let av = a.cells[col]?.innerText.trim() || '';
    let bv = b.cells[col]?.innerText.trim() || '';
    if (col===2||col===4) {{ av = new Date(av)||''; bv = new Date(bv)||''; }}
    return asc ? (av<bv?-1:av>bv?1:0) : (av>bv?-1:av<bv?1:0);
  }});
  rows.forEach(r => tb.appendChild(r));
}}
</script>
</body>
</html>"""

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    DATA_DIR.mkdir(exist_ok=True)
    prev_ungraded  = load_json(DATA_DIR / "ps_data.json", [])
    prev_completed = load_json(DATA_DIR / "completed.json", [])

    print("=== Fetching Canvas data ===")
    canvas_map = get_canvas_assignments()
    emails     = get_canvas_emails()

    print("\n=== Scraping PowerSchool ===")
    current_ungraded, schedule = scrape_ps(canvas_map, emails)

    print("\n=== Updating completed list ===")
    completed = update_completed(current_ungraded, prev_ungraded, prev_completed, canvas_map)

    save_json(DATA_DIR / "ps_data.json", current_ungraded)
    save_json(DATA_DIR / "completed.json", completed)
    save_json(DATA_DIR / "schedule.json", schedule)
    print("Data saved.")

    (OUT_DIR / "index.html").write_text(build_index(current_ungraded), encoding="utf-8")
    (OUT_DIR / "completed.html").write_text(build_completed(completed), encoding="utf-8")
    print("HTML built. Done.")

if __name__ == "__main__":
    main()
