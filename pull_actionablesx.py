#!/usr/bin/env python3
"""
Matthew Actionables — Canvas + Gmail Complete Intelligence Pull
Usage: python3 pull_actionables.py matthew
       python3 pull_actionables.py edward

Gathers:
  Canvas  — assignments, submission status, grades, descriptions,
             lock status, late work availability, submission types
  Gmail   — PowerSchool attendance (absences/tardies per class)
  Gmail   — Detailed attendance (per-period dates, excused vs unexcused)
  Gmail   — School daily announcements (late starts, events)
  Gmail   — Teacher direct emails (flagged per class)
  Gmail   — Any Canvas/school notification emails
  Gmail   — Google Doc shares from student (assignment work evidence)
"""

import requests, json, subprocess, sys, os, re, base64
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

CANVAS_BASE = "https://westbloomfieldsd.instructure.com/api/v1"
TOKENS = {
    "matthew": "16592~UHBmMt4U3Qhn7P8kvufhcatxQCnEHEEFWz69AWr9U4PzFLYMKCmFMTva9VzNcycw",
    "edward":  "16592~3KAZxcucZtAvKRGXhB6U8hecXueRAtXG4yy8kQQBtMZ7WTeHTT32DZa394P4zUNR"
}
SONS = {"matthew": "Matthew Nichols", "edward": "Edward Nichols"}
STUDENT_EMAILS = {"matthew": "wbfnicholsm07@student.wbsd.org", "edward": "wbfnicholse"}

ET = timezone(timedelta(hours=-4))
CUTOFF = datetime(2026, 1, 15, tzinfo=timezone.utc)
SKIP = ["advisory","counseling","college and career","7th grade","8th grade",
        "science 7","summer school"]

GMAIL_TOKEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gmail_token.json")


# ── HTML stripper ─────────────────────────────────────────────────────────────
class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)
    def get_text(self):
        return re.sub(r'\s+', ' ', ' '.join(self.parts)).strip()

def strip_html(html):
    if not html: return ""
    s = HTMLStripper()
    try:
        s.feed(html)
        return s.get_text()
    except:
        return re.sub(r'<[^>]+>', ' ', html)


# ── Gmail ─────────────────────────────────────────────────────────────────────
def gmail_svc():
    if not os.path.exists(GMAIL_TOKEN):
        return None
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_file(
            GMAIL_TOKEN, ["https://www.googleapis.com/auth/gmail.readonly"])
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        print(f"  ⚠ Gmail auth: {e}")
        return None

def g_search(svc, q, n=10):
    if not svc: return []
    try:
        r = svc.users().messages().list(userId="me", q=q, maxResults=n).execute()
        return r.get("messages", [])
    except: return []

def g_body(svc, mid):
    if not svc: return ""
    try:
        msg = svc.users().messages().get(userId="me", id=mid, format="full").execute()
        payload = msg.get("payload", {})
        def extract(p):
            if p.get("mimeType") == "text/plain":
                d = p.get("body", {}).get("data", "")
                if d: return base64.urlsafe_b64decode(d + "==").decode("utf-8", "ignore")
            for part in p.get("parts", []):
                r = extract(part)
                if r: return r
            return ""
        return extract(payload)
    except: return ""

def g_subject(svc, mid):
    try:
        msg = svc.users().messages().get(userId="me", id=mid, format="metadata",
            metadataHeaders=["Subject","From","Date"]).execute()
        headers = {h["name"]: h["value"] for h in msg.get("payload",{}).get("headers",[])}
        return headers
    except: return {}


# ── Gmail intelligence layer ──────────────────────────────────────────────────
def load_gmail(svc, son_key):
    out = {
        "attendance_by_class": {},   # {period_course: {grade, absences, tardies}}
        "attendance_detail": {},     # {period: [(date, code)]}
        "attendance_total": {},      # {absences: N, tardies: N}
        "announcements": [],         # ["April 15 Late Start", ...]
        "teacher_emails": {},        # {teacher_name: [subject_lines]}
        "doc_shares": [],            # [{title, url, from, date}]
        "ps_report_date": "—",
    }
    if not svc:
        print("  Gmail not connected — Canvas-only mode")
        return out

    # ── 1. Daily summary (grades + absences per class) ────────────────────────
    msgs = g_search(svc, 'subject:"Progress Report From West Bloomfield"', 1)
    if msgs:
        body = g_body(svc, msgs[0]["id"])
        m = re.search(r'as of (\d+/\d+/\d+)', body)
        if m: out["ps_report_date"] = m.group(1)
        for match in re.finditer(
            r'PERIOD\s+\d+\([AB]\):\s+(.+?)\s*\(Teachers:.*?\)\s*\n\s*'
            r'Current Grade:\s*(\S+)\s+Absences:\s*(\d+)\s+Tardies:\s*(\d+)',
            body, re.IGNORECASE):
            course = match.group(1).strip().upper()
            out["attendance_by_class"][course] = {
                "grade_ps": match.group(2),
                "absences": int(match.group(3)),
                "tardies":  int(match.group(4))
            }
        print(f"  PS summary: {len(out['attendance_by_class'])} classes, as of {out['ps_report_date']}")

    # ── 2. Detailed attendance (per-date breakdown) ───────────────────────────
    name_upper = SONS[son_key].split()[0].upper()
    msgs = g_search(svc, f'subject:"Detailed attendance report for {name_upper}"', 1)
    if msgs:
        body = g_body(svc, msgs[0]["id"])
        # Parse totals
        tot_abs = re.search(r'(\d+)\s+Absences', body)
        tot_tar = re.search(r'(\d+)\s+Tardies', body)
        out["attendance_total"] = {
            "absences": int(tot_abs.group(1)) if tot_abs else 0,
            "tardies":  int(tot_tar.group(1)) if tot_tar else 0
        }
        # Parse per-period S2 entries (2026 dates only)
        for period_match in re.finditer(r'Expression (\d+\([AB]\)):\s*\n((?:.*\n?)*?)(?=Expression|\Z)', body):
            period = period_match.group(1)
            entries_text = period_match.group(2)
            s2_entries = []
            for entry in re.finditer(r'(\d+\([AB]\))\s*-\s*(0[1-9]|1[0-2])/(\d+)/2026\s+(\w+)', entries_text):
                date_str = f"{entry.group(2)}/{entry.group(3)}/2026"
                code = entry.group(4)
                s2_entries.append({"date": date_str, "code": code})
            if s2_entries:
                out["attendance_detail"][period] = s2_entries
        print(f"  Detailed attendance: {out['attendance_total']} total, {len(out['attendance_detail'])} periods with S2 data")

    # ── 3. School announcements (daily bulletin) ──────────────────────────────
    msgs = g_search(svc, 'subject:"West Bloomfield High School Announcements"', 3)
    seen = set()
    for m in msgs:
        body = g_body(svc, m["id"])
        lines = [l.strip() for l in body.splitlines()
                 if l.strip() and "Sent on behalf" not in l
                 and "West Bloomfield" not in l and len(l.strip()) > 5]
        for l in lines:
            if l not in seen:
                seen.add(l)
                out["announcements"].append(l)
    print(f"  Announcements: {len(out['announcements'])} items")

    # ── 4. Teacher direct emails ──────────────────────────────────────────────
    teachers = ["pruitt","bishop","sharpe","mcguire","muylaert","watson",
                "mattson","chase","sepetys","kang"]
    for t in teachers:
        msgs = g_search(svc, f'from:{t}@wbsd.org after:2026/01/15', 5)
        if msgs:
            subjects = []
            for m in msgs:
                hdrs = g_subject(svc, m["id"])
                subj = hdrs.get("Subject","")
                date = hdrs.get("Date","")[:16]
                if subj:
                    subjects.append(f"{date}: {subj}")
            if subjects:
                out["teacher_emails"][t] = subjects
    if out["teacher_emails"]:
        print(f"  Teacher emails: {list(out['teacher_emails'].keys())}")

    # ── 5. Google Doc shares from student ────────────────────────────────────
    student_email = STUDENT_EMAILS.get(son_key, "")
    if student_email:
        msgs = g_search(svc, f'from:{student_email} after:2026/01/15', 10)
        for m in msgs:
            body = g_body(svc, m["id"])
            hdrs = g_subject(svc, m["id"])
            # Extract doc title and URL
            title_match = re.search(r'shared a link to the following document:\s*(.+?)(?:\n|Copy of)', body)
            url_match = re.search(r'(https://docs\.google\.com/\S+)', body)
            if title_match or url_match:
                out["doc_shares"].append({
                    "subject": hdrs.get("Subject",""),
                    "date": hdrs.get("Date","")[:16],
                    "title": title_match.group(1).strip() if title_match else hdrs.get("Subject",""),
                    "url": url_match.group(1) if url_match else ""
                })
    if out["doc_shares"]:
        print(f"  Doc shares from student: {len(out['doc_shares'])}")

    # ── 6. Canvas email notifications (grade alerts, etc.) ───────────────────
    msgs = g_search(svc, 'from:instructure.com OR from:canvas after:2026/01/15', 10)
    canvas_notifs = []
    for m in msgs:
        hdrs = g_subject(svc, m["id"])
        subj = hdrs.get("Subject","")
        if subj and subj not in canvas_notifs:
            canvas_notifs.append(subj)
    if canvas_notifs:
        out["canvas_notifications"] = canvas_notifs
        print(f"  Canvas email notifications: {len(canvas_notifs)}")

    return out


# ── Canvas pull ───────────────────────────────────────────────────────────────
def is_current(name):
    n = name.lower()
    # Skip year-stamped old courses
    if re.search(r'202[234]', n): return False
    return not any(t in n for t in SKIP)

def parse_dt(s):
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except: return None

def fmt_dt(dt, fmt="%m/%d %I:%M %p"):
    if not dt: return "No due date"
    s = dt.astimezone(ET).strftime(fmt)
    # Strip leading zeros on Windows-safe way
    return re.sub(r'\b0(\d)', r'\1', s)

def submission_label(types):
    if not types: return "Unknown"
    if any(t in types for t in ["online_upload","online_text_entry","online_quiz","media_recording"]):
        return "Canvas"
    if "on_paper" in types: return "Paper"
    if "none" in types: return "None/In-class"
    return types[0]

def distill_description(raw_desc, title):
    """Extract actionable intelligence from assignment description."""
    if not raw_desc: return ""
    text = strip_html(raw_desc)
    if len(text) < 20: return ""

    notes = []

    # Late work / cutoff language
    late_patterns = [
        r'(no late work[^.]*\.)',
        r'(late work[^.]*accepted[^.]*\.)',
        r'(submissions? (will )?not be accepted after[^.]*\.)',
        r'(quarter (ends?|closes?|cutoff)[^.]*\.)',
        r'(last day to submit[^.]*\.)',
        r'(deadline[^.]*no credit[^.]*\.)',
    ]
    for pat in late_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m: notes.append(f"⚠ POLICY: {m.group(1).strip()}")

    # Group work
    if re.search(r'group|partner|team|collaborat', text, re.IGNORECASE):
        notes.append("Group/partner work")

    # Minimum requirements
    reqs = re.findall(r'(minimum \d+[^.]*\.|at least \d+[^.]*\.|\d+ (respondents?|sentences?|paragraphs?|pages?)[^.]*\.)', text, re.IGNORECASE)
    for r_match in reqs[:2]:
        req_text = r_match[0].strip()
        if req_text: notes.append(f"Requires: {req_text}")

    # Specific deliverables
    deliverables = re.findall(r'(submit[^.]{5,50}\.)', text, re.IGNORECASE)
    for d in deliverables[:1]:
        notes.append(f"Submit: {d[0][:80].strip()}")

    # Paper/physical submission
    if re.search(r'print|physical copy|hand.?in|turn.?in', text, re.IGNORECASE):
        notes.append("Print/physical copy required")

    # First 150 chars if nothing else extracted
    if not notes:
        snippet = text[:150].strip()
        if snippet: notes.append(snippet)

    return " · ".join(notes[:3])

def build_note(entry, gmail_data):
    """Synthesize a comprehensive Note from all data sources."""
    notes = []
    cls_upper = entry.get("canvas_course","").upper()
    cls_lower = entry.get("class","").lower()

    # ── Attendance for this class ─────────────────────────────────────────────
    att = None
    for ps_course, data in gmail_data["attendance_by_class"].items():
        ps_short = re.sub(r'\s+S[12]\s*$', '', ps_course).strip()
        if ps_short in cls_upper or any(k in cls_upper for k in ps_short.split()):
            att = data
            break

    if att:
        abs_n, tar_n = att["absences"], att["tardies"]
        att_parts = []
        if abs_n > 0: att_parts.append(f"{abs_n} abs")
        if tar_n > 0: att_parts.append(f"{tar_n} late")
        if att_parts:
            flag = "⚠ " if (abs_n >= 3 or tar_n >= 3) else ""
            notes.append(f"{flag}Attendance: {', '.join(att_parts)}")

    # ── S2 per-period attendance detail ──────────────────────────────────────
    period_map = {
        "ENGRACAD": "1(A)", "FRENCH": "2(A)", "EARTH SCI": "3(A)",
        "MULTCULT": "4(A)", "ARCHTEC": "5(A)", "ECON": "6(A)",
        "ALGEBRA": "7(A)", "INTERIOR": "5(A)", "CIVICS": "6(A)"
    }
    for keyword, period in period_map.items():
        if keyword in cls_upper:
            detail = gmail_data["attendance_detail"].get(period, [])
            s2_detail = [e for e in detail if "2026" in e.get("date","")]
            if s2_detail:
                codes = [e["code"] for e in s2_detail]
                code_summary = ", ".join(f"{e['date']} {e['code']}" for e in s2_detail[-3:])
                notes.append(f"S2 attendance: {code_summary}")
            break

    # ── Assignment description intelligence ───────────────────────────────────
    desc_note = entry.get("desc_note","")
    if desc_note:
        notes.append(desc_note)

    # ── Lock / availability status ────────────────────────────────────────────
    if entry.get("locked"):
        notes.append(f"🔒 LOCKED: {entry.get('lock_explanation','')[:80]}")

    # ── Submission type ───────────────────────────────────────────────────────
    via = entry.get("submit_via","")
    if via == "Paper":
        notes.append("Paper — hand to teacher")
    elif via == "None/In-class":
        notes.append("In-class activity")

    # ── Google Doc shares matching this assignment ────────────────────────────
    title_lower = entry.get("title","").lower()
    for share in gmail_data.get("doc_shares",[]):
        share_title = share.get("title","").lower()
        # Fuzzy match: significant word overlap
        title_words = set(w for w in title_lower.split() if len(w) > 4)
        share_words = set(w for w in share_title.split() if len(w) > 4)
        if title_words & share_words:
            notes.append(f"📄 Student shared doc {share['date']}: {share['title'][:60]}")
            break
        # Also check by class keyword
        if any(k in share_title for k in ["civics","algebra","french","earth","lit","interior","cad"]):
            if any(k in cls_lower for k in ["civics","algebra","french","earth","lit","interior","cad"]):
                notes.append(f"📄 Student shared doc {share['date']}: {share['title'][:60]}")
                break

    # ── Teacher email for this class ──────────────────────────────────────────
    teacher_map = {
        "algebra": "pruitt", "french": "bishop", "lit": "sharpe",
        "earth": "mcguire", "cad": "muylaert", "engracad": "muylaert",
        "civics": "watson", "interior": "mattson", "archtec": "mattson"
    }
    for keyword, teacher in teacher_map.items():
        if keyword in cls_lower and teacher in gmail_data.get("teacher_emails",{}):
            emails = gmail_data["teacher_emails"][teacher]
            notes.append(f"📧 {teacher.title()} email: {emails[0][:60]}")
            break

    return " · ".join(notes) if notes else "—"

def fetch_canvas(son_key, gmail_data):
    token = TOKENS[son_key]
    son_name = SONS[son_key]
    headers = {"Authorization": f"Bearer {token}"}

    print(f"  Pulling courses...")
    r = requests.get(f"{CANVAS_BASE}/courses", headers=headers,
        params={"enrollment_type":"student","enrollment_state":"active","per_page":100},
        timeout=15)
    r.raise_for_status()
    courses = [c for c in r.json() if is_current(c.get("name",""))]
    print(f"  {len(courses)} current courses")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    week_out = now + timedelta(days=7)

    buckets = {
        "missing":        [],
        "due_today":      [],
        "due_this_week":  [],
        "assigned_today": [],
        "pending":        [],
        "graded":         [],
    }

    for course in courses:
        cid = course["id"]
        cname = course.get("name","")
        # Clean display name
        short = re.sub(r'\s+S[12]\s*$','', cname.split(" - ")[0].strip(), flags=re.IGNORECASE)
        short = re.sub(r'\s+(PRUITT|BISHOP|SHARPE|MCGUIRE|MUYLAERT|WATSON|MATTSON).*$',
                       '', short, flags=re.IGNORECASE).strip()

        try:
            ar = requests.get(f"{CANVAS_BASE}/courses/{cid}/assignments", headers=headers,
                params={"per_page":100, "include[]":["submission","score_statistics"]},
                timeout=10)
            ar.raise_for_status()
            assigns = ar.json()
        except: continue

        for a in assigns:
            title = (a.get("name") or "").strip()
            if not title or "[Title" in title: continue

            due_dt  = parse_dt(a.get("due_at"))
            cre_dt  = parse_dt(a.get("created_at"))
            lock_dt = parse_dt(a.get("lock_at"))
            avail_dt= parse_dt(a.get("unlock_at"))

            if due_dt and due_dt < CUTOFF: continue
            if not due_dt and cre_dt and cre_dt < CUTOFF: continue

            sub    = a.get("submission") or {}
            state  = sub.get("workflow_state","unsubmitted")
            grade  = sub.get("grade") or "—"
            score  = sub.get("score")
            pts    = a.get("points_possible")
            types  = a.get("submission_types",[])
            locked = a.get("locked_for_user", False)
            lock_exp = (a.get("lock_explanation") or "")[:120]

            # Check if submission window is closed
            submission_closed = False
            if lock_dt and lock_dt < now:
                submission_closed = True

            # Description intelligence
            raw_desc = a.get("description","")
            desc_note = distill_description(raw_desc, title)

            via = submission_label(types)
            url = f"https://westbloomfieldsd.instructure.com/courses/{cid}/assignments/{a['id']}"

            entry = {
                "class":          short,
                "canvas_course":  cname.upper(),
                "title":          title,
                "url":            url,
                "due":            fmt_dt(due_dt) if due_dt else "No due date",
                "due_raw":        a.get("due_at",""),
                "assigned":       fmt_dt(cre_dt, "%m/%d") if cre_dt else "—",
                "pts":            str(int(pts)) if pts is not None else "—",
                "submit_via":     via,
                "grade":          grade,
                "score":          score,
                "status":         state,
                "locked":         locked,
                "lock_explanation": lock_exp,
                "submission_closed": submission_closed,
                "desc_note":      desc_note,
            }
            entry["note"] = build_note(entry, gmail_data)

            # Bucket
            if cre_dt and today_start <= cre_dt < today_end:
                buckets["assigned_today"].append(entry)

            if due_dt and today_start <= due_dt < today_end:
                buckets["due_today"].append(entry)
            elif due_dt and now < due_dt <= week_out and state == "unsubmitted":
                buckets["due_this_week"].append(entry)
            elif state == "graded":
                buckets["graded"].append(entry)
            elif state in ("submitted","pending_review"):
                buckets["pending"].append(entry)
            elif state == "unsubmitted" and (not due_dt or due_dt < now):
                buckets["missing"].append(entry)

    for k in buckets:
        buckets[k].sort(key=lambda x: x.get("due_raw","") or "9999")

    totals = {k: len(v) for k,v in buckets.items()}
    print(f"  {totals}")
    return buckets


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2 or sys.argv[1].lower() not in TOKENS:
        print("Usage: python3 pull_actionables.py [matthew|edward]")
        sys.exit(1)

    son_key  = sys.argv[1].lower()
    son_name = SONS[son_key]
    now_et   = datetime.now(ET)

    print(f"\n{'='*60}")
    print(f"  {son_name.upper()} — ACTIONABLES")
    print(f"  {now_et.strftime('%A %B %d, %Y  %I:%M %p ET').replace(' 0',' ')}")
    print(f"{'='*60}")

    print("\n[1/2] Gmail...")
    svc = gmail_svc()
    gmail_data = load_gmail(svc, son_key)

    print("\n[2/2] Canvas...")
    buckets = fetch_canvas(son_key, gmail_data)

    # Grade summary from PS daily report
    grade_summary = {}
    for course, att in gmail_data["attendance_by_class"].items():
        short = re.sub(r'\s+S[12]\s*$','', course).strip()
        grade_summary[short] = {
            "grade": att["grade_ps"],
            "absences": att["absences"],
            "tardies": att["tardies"]
        }

    script_dir = os.path.dirname(os.path.abspath(__file__))
    out = {
        "son":              son_name,
        "generated":        now_et.strftime("%m/%d/%Y %I:%M %p ET"),
        "ps_report_date":   gmail_data["ps_report_date"],
        "back_to_school":   "4/7/2026",
        "sat_date":         "4/21/2026",
        "announcements":    gmail_data["announcements"],
        "grade_summary":    grade_summary,
        "attendance_total": gmail_data.get("attendance_total",{}),
        "teacher_emails":   gmail_data.get("teacher_emails",{}),
        "doc_shares":       gmail_data.get("doc_shares",[]),
        **buckets
    }

    json_path = os.path.join(script_dir, "actionables_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    result = subprocess.run(["node", os.path.join(script_dir, "build_doc.mjs")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=script_dir)
    if result.returncode != 0:
        print("DOC ERROR:\n", result.stderr or "")
        sys.exit(1)
    output = result.stdout or ""
    print("\n" + output.strip())

if __name__ == "__main__":
    main()
