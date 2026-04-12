# Canvas Project — Session Summary
**Last updated: April 11, 2026**

---

## What This Project Is
An automated academic tracking system for two sons — Matthew (11th grade, WBHS) and Edward (8th grade, WBMS) — in the West Bloomfield School District. The system pulls assignment data from Canvas and PowerSchool via Gmail, generates a polished Word doc and sortable HTML "actionables" report, and is designed to catch missing assignments, zeros, and grade changes in real time.

---

## Project Location
`C:\Users\Jetbo\Desktop\Canvas Project`

**Key files:**
- `pull_actionables.py` — main script, run with `python pull_actionables.py matthew` or `edward`
- `build_doc.mjs` — generates the Word doc and HTML from JSON
- `actionables_data.json` — output data file
- `gmail_token.json` — Gmail OAuth token (expires ~July 2026)
- `gmail_credentials.json` — Google Cloud OAuth credentials
- `Run_Matthew_Actionables.bat` — desktop shortcut batch file

---

## Canvas API Details
- **Base URL:** `https://westbloomfieldsd.instructure.com/api/v1`
- **Matthew token:** `16592~UHBmMt4U3Qhn7P8kvufhcatxQCnEHEEFWz69AWr9U4PzFLYMKCmFMTva9VzNcycw`
- **Edward token:** `16592~3KAZxcucZtAvKRGXhB6U8hecXueRAtXG4yy8kQQBtMZ7WTeHTT32DZa394P4zUNR`
- Both tokens expire ~July 2026

**Matthew's S2 Canvas courses (confirmed working):**
| Course ID | Name |
|---|---|
| 29168 | 5th Hour Interior Design (2nd Semester) |
| 28876 | ALGEBRA 2 S2 - PRUITT - 5(A) |
| 30361 | CIVICS - WATSON - 6(A) |
| 28927 | EARTH SCI S2 - MCGUIRE - 3(A) |
| 29422 | ENGRACAD3 S2 - MUYLAERT - 1(A) |
| 29366 | FRENCH 1 S2 - BISHOP - 2(A) |
| 29304 | MULTCULT LIT 11 S2 - SHARPE - 4(A) |

---

## What's Working
- ✅ Canvas API pulling all 8 Matthew courses including French S2 and CAD S2
- ✅ Gmail OAuth connected — reads PowerSchool emails automatically
- ✅ Ghost assignment filter — skips any assignment due before 2026 (killed 40 McGuire 2022/2023 junk assignments)
- ✅ Word doc (.docx) and sortable HTML both generating correctly
- ✅ Desktop shortcut working (`Run_Matthew_Actionables.bat`)
- ✅ Tasker + AutoNotification set up on Android phone to forward PowerSchool push notifications to jetboy2go@gmail.com (awaiting first real push to confirm working)

## Known Issues / To Verify
- Grade summary bar in the doc shows blank — PS email regex pulls grades labeled S1 but matching against S2 canvas names may be off. Needs further testing.
- French (Bishop) shows in Canvas course list but zero assignments visible — she may not have entered any yet
- Tasker forwarding not yet confirmed — waiting for next PowerSchool push notification to test

---

## PowerSchool Email Behavior
- Matthew's PS emails say "Grading period: S1" — this is correct. WBHS runs the full year as one S1 grading period. Not a bug.
- Edward's PS emails correctly show S2
- PS email assignment detail for Matthew stops at Jan 14 midterms — only overall grades update after that
- **Push notifications on the PowerSchool app ARE showing real-time S2 grade changes** — that's the most current data source

## Current Grades (as of April 10, 2026)
**Matthew:**
- CAD Engineering (Muylaert): B
- French (Bishop): D
- Earth Science (McGuire): B
- Multicultural Lit (Sharpe): D
- Architecture/Interior Design (Mattson): D
- Econ/Personal Finance (Chase): C
- Algebra 2 (Pruitt): D

**Edward:**
- History: F
- English: F
- Orchestra: C-
- Design: A
- Science: B+/A-
- Math: C+

---

## Tasker Setup (in progress)
**Goal:** Forward PowerSchool push notifications to jetboy2go@gmail.com automatically
**Status:** Profile created, awaiting test
- App: Tasker by joaomgcd ($4.49)
- Plugin: AutoNotification (same developer)
- Profile trigger: AutoNotification Intercept → PowerSchool app only
- Task: Compose Email → jetboy2go@gmail.com, Subject: %antitle, Message: %antext
- AutoNotification has Notification Access enabled ✅

---

## TO DO LIST (prioritized)
1. **Confirm Tasker working** — check Gmail after next PowerSchool push fires
2. **Google Drive auto-upload** — add to batch file so HTML uploads automatically after script runs; optionally share to Matthew's Google Drive too
3. **Quarter filter toggle** — add Q1/Q2/Q3/Q4 toggle to the HTML browser view; ghost old Q3 assignments but keep accessible. Q3 cutoff is approximately April 11, 2026.
4. **Mobile web app** — phone-friendly Canvas dashboard accessible anywhere, no laptop needed. React/Node.js recommended. Canvas OAuth needed for broader use.
5. **Grade summary bar fix** — PS email regex needs adjustment to populate grade bar in the doc

---

## Key Contact Info
- WBHS Attendance Office: 248-865-6722 (press 1 to excuse absence, press 2 for tardy)
- Canvas observer login: westbloomfieldsd.instructure.com
- PowerSchool parent portal: westbloomfield.powerschool.com
- Gmail account: jetboy2go@gmail.com

---

## Notes
- Parent describes himself as "the concept man" — prefers clean execution, minimal explanation
- Matthew and Edward both share same pattern: pass tests, don't submit assignments
- Matthew's mother is skeptical of AI — keep any docs for her looking natural
- Attendance report built for Matthew's mom: 9 unique absence days (not 31 — PS counts per period), 3 unexcused, 9 tardies (6 in French)
- Business idea noted: this system could be licensed to school districts as a unified parent dashboard
