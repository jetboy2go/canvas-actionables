// build_doc.mjs — Matthew Actionables Complete Doc Builder
// Sections: ALERTS | MISSING | DUE TODAY | DUE THIS WEEK | ASSIGNED TODAY | PENDING | GRADED
// Columns:  Class | Assignment (link) | Assigned | Due | Via | Pts | Grade | Status | Note
// Footer:   Grade bar + attendance totals + teacher email flags + doc shares

import { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
         ExternalHyperlink, AlignmentType, BorderStyle, WidthType, ShadingType,
         VerticalAlign } from 'docx';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const D = JSON.parse(fs.readFileSync(path.join(__dirname, 'actionables_data.json'), 'utf8'));

// ── Palette ───────────────────────────────────────────────────────────────────
const C = {
  navy:     "1F4E79",  white:   "FFFFFF",
  missing:  "C00000",  dueToday:"C55A11",  week:    "7B6000",
  assigned: "375623",  pending: "4B0082",  graded:  "404040",
  locked:   "808080",  alert:   "843C0C",
  altRow:   "F4F8FC",  noteClr: "444444",  border:  "CCCCCC",
};

// Landscape US Letter — 0.5" margins = 14400 DXA content
// Class | Assignment | Assigned | Due | Via | Pts | Grade | Status | Note
const COL = [1400, 2800, 650, 1000, 700, 450, 650, 900, 5850];
const TW  = COL.reduce((a,b)=>a+b,0); // 14400

const bd  = {style:BorderStyle.SINGLE, size:1, color:C.border};
const bds = {top:bd, bottom:bd, left:bd, right:bd};

// ── Cell helpers ──────────────────────────────────────────────────────────────
function run(text, {bold=false,color="000000",size=16,italic=false,underline=false}={}) {
  return new TextRun({text:String(text||''), bold, color, size, italics:italic,
    underline: underline ? {type:"single"} : undefined});
}

function tc(text, opts={}) {
  const {bold=false,color=null,bg=null,size=16,align=AlignmentType.LEFT,
         italic=false,link=null,wrap=true} = opts;

  const child = link
    ? new ExternalHyperlink({link, children:[new TextRun({
        text:String(text||''), size, color:"1155CC",
        underline:{type:"single"}, bold})]})
    : run(text, {bold, color:color||"000000", size, italic});

  return new TableCell({
    borders:bds,
    shading: bg ? {fill:bg, type:ShadingType.CLEAR} : undefined,
    margins: {top:60, bottom:60, left:100, right:100},
    verticalAlign: VerticalAlign.TOP,
    children:[new Paragraph({alignment:align, spacing:{after:0}, children:[child]})]
  });
}

// ── Header row ────────────────────────────────────────────────────────────────
function headerRow() {
  const labels = ["Class","Assignment","Assigned","Due","Via","Pts","Grade","Status","Note"];
  return new TableRow({tableHeader:true, children: labels.map((l,i) =>
    new TableCell({
      borders:bds,
      width:{size:COL[i], type:WidthType.DXA},
      shading:{fill:C.navy, type:ShadingType.CLEAR},
      margins:{top:80, bottom:80, left:100, right:100},
      children:[new Paragraph({spacing:{after:0},
        children:[new TextRun({text:l, bold:true, color:C.white, size:18})]})]
    })
  )});
}

// ── Section divider ───────────────────────────────────────────────────────────
function sectionRow(label, color) {
  return new TableRow({children:[new TableCell({
    columnSpan:COL.length, borders:bds,
    shading:{fill:color, type:ShadingType.CLEAR},
    margins:{top:90, bottom:90, left:140, right:140},
    children:[new Paragraph({spacing:{after:0},
      children:[new TextRun({text:label, bold:true, color:C.white, size:20})]})]
  })]});
}

function emptyRow(msg) {
  return new TableRow({children:[new TableCell({
    columnSpan:COL.length, borders:bds,
    shading:{fill:"F8F8F8", type:ShadingType.CLEAR},
    margins:{top:60, bottom:60, left:140, right:140},
    children:[new Paragraph({spacing:{after:0},
      children:[new TextRun({text:msg, italic:true, color:"888888", size:16})]})]
  })]});
}

// ── Teacher name lookup ───────────────────────────────────────────────────────
const TEACHER_NAMES = {
  "CAD": "Muylaert", "ENGRACAD": "Muylaert",
  "FRENCH": "Bishop",
  "EARTH": "McGuire",
  "LIT": "Sharpe", "MULTCULT": "Sharpe",
  "INTERIOR": "Mattson", "ARCHTEC": "Mattson",
  "CIVICS": "Watson",
  "ALGEBRA": "Pruitt",
  "ADVISORY": "Sepetys",
  "ORCHESTRA": "Kang",
};

function addTeacher(className) {
  const upper = className.toUpperCase();
  for (const [key, teacher] of Object.entries(TEACHER_NAMES)) {
    if (upper.includes(key)) return `${className} / ${teacher}`;
  }
  return className;
}

// ── Data row ──────────────────────────────────────────────────────────────────
function dataRow(e, shade) {
  const bg = shade ? C.altRow : null;

  // Status label
  let statusLabel = e.status || "—";
  let statusColor = "000000";
  if (e.submission_closed) { statusLabel = "🔒 CLOSED — Q3 cutoff"; statusColor = C.missing; }
  else if (e.locked)       { statusLabel = "🔒 Locked";  statusColor = C.locked; }
  else if (statusLabel === "unsubmitted") { statusLabel = "Not submitted"; statusColor = "C00000"; }
  else if (statusLabel === "submitted")   { statusLabel = "Submitted ✓";   statusColor = "375623"; }
  else if (statusLabel === "graded")      { statusLabel = "Graded";         statusColor = "404040"; }
  else if (statusLabel === "pending_review") { statusLabel = "Pending";     statusColor = "4B0082"; }

  // Grade display
  let gradeDisplay = e.grade || "—";
  let gradeColor = "000000";
  if (e.grade && e.grade !== "—" && e.pts && e.pts !== "—") {
    try {
      const parts = e.grade.includes("/") ? e.grade.split("/") : [e.grade, e.pts];
      const pct = (parseFloat(parts[0]) / parseFloat(e.pts)) * 100;
      if (pct < 60) gradeColor = "C00000";
      else if (pct < 70) gradeColor = "C55A11";
      gradeDisplay = e.grade;
    } catch(err) {}
  }

  // Class display with teacher name
  const classDisplay = addTeacher(e.class);

  // If submission closed, shade the whole row differently
  const rowBg = e.submission_closed ? "FFE0E0" : bg;

  return new TableRow({children:[
    tc(classDisplay,  {bg:rowBg, size:14}),
    tc(e.title,       {bg:rowBg, size:15, link:e.url}),
    tc(e.assigned,    {bg:rowBg, size:15, align:AlignmentType.CENTER}),
    tc(e.due,         {bg:rowBg, size:14}),
    tc(e.submit_via,  {bg:rowBg, size:15, align:AlignmentType.CENTER}),
    tc(e.pts,         {bg:rowBg, size:15, align:AlignmentType.CENTER}),
    new TableCell({borders:bds, shading:rowBg?{fill:rowBg,type:ShadingType.CLEAR}:undefined,
      margins:{top:60,bottom:60,left:100,right:100}, verticalAlign:VerticalAlign.TOP,
      children:[new Paragraph({spacing:{after:0}, alignment:AlignmentType.CENTER,
        children:[run(gradeDisplay, {size:15, color:gradeColor, bold:gradeColor!="000000"})]})]}),
    new TableCell({borders:bds, shading:rowBg?{fill:rowBg,type:ShadingType.CLEAR}:undefined,
      margins:{top:60,bottom:60,left:100,right:100}, verticalAlign:VerticalAlign.TOP,
      children:[new Paragraph({spacing:{after:0},
        children:[run(statusLabel, {size:14, color:statusColor, bold:statusColor!="000000"})]})]}),
    tc(e.note,        {bg:rowBg, size:14, italic:true, color:C.noteClr}),
  ]});
}

// ── Build table rows ──────────────────────────────────────────────────────────
const sections = [
  {label:"⚠  MISSING — Past due, not submitted",       items:D.missing,       color:C.missing,  empty:"No missing assignments ✓"},
  {label:"📅  DUE TODAY",                               items:D.due_today,     color:C.dueToday, empty:"Nothing due today"},
  {label:"📆  DUE THIS WEEK",                           items:D.due_this_week, color:C.week,     empty:"Nothing due in the next 7 days"},
  {label:"🆕  ASSIGNED TODAY — New assignments",        items:D.assigned_today,color:C.assigned, empty:"No new assignments today"},
  {label:"⏳  SUBMITTED — Awaiting grade",              items:D.pending,       color:C.pending,  empty:"Nothing pending"},
  {label:"✅  GRADED",                                  items:D.graded,        color:C.graded,   empty:"No graded items"},
];

const rows = [headerRow()];
for (const s of sections) {
  rows.push(sectionRow(s.label, s.color));
  if (!s.items?.length) { rows.push(emptyRow(s.empty)); }
  else { s.items.forEach((e,i) => rows.push(dataRow(e, i%2===1))); }
}

// ── School alerts paragraph ───────────────────────────────────────────────────
const announcements = D.announcements || [];
const alertText = announcements.length
  ? "⚠ SCHOOL ALERTS:  " + announcements.join("   ·   ")
  : null;

// ── Grade + attendance footer ─────────────────────────────────────────────────
const gs = D.grade_summary || {};
const gradeParts = Object.entries(gs).map(([cls,v]) => {
  const abs = v.absences > 0 ? ` (${v.absences}abs${v.tardies>0?`/${v.tardies}late`:''})` : '';
  return `${cls}: ${v.grade}${abs}`;
});
const gradeFooter = gradeParts.length
  ? "Q3 Grades (PS " + D.ps_report_date + "):  " + gradeParts.join("   |   ")
  : "Grade summary not available";

// ── Teacher emails + doc shares footer ───────────────────────────────────────
const teacherEmails = D.teacher_emails || {};
const teacherFooterParts = Object.entries(teacherEmails).map(([t,subjects]) =>
  `${t.charAt(0).toUpperCase()+t.slice(1)}: ${subjects[0]}`);

const docShares = D.doc_shares || [];
const docFooterParts = docShares.map(d => `📄 ${d.date} — ${d.title}`);

// ── Document ──────────────────────────────────────────────────────────────────
const son = (D.son||"Student").split(" ")[0].toUpperCase();
const attTotal = D.attendance_total || {};

const docChildren = [
  // Title
  new Paragraph({spacing:{after:60}, children:[
    run(`${son}  `, {bold:true, size:44, color:C.navy}),
    run("DAILY ACTIONABLES", {bold:true, size:30, color:"505050"}),
    run(`    ${D.generated}`, {size:17, color:"808080"}),
  ]}),

  // Context bar
  new Paragraph({spacing:{after:120}, children:[
    run("Back to school: ", {bold:true, size:16, color:"505050"}),
    run(`${D.back_to_school}   `, {size:16}),
    run("SAT: ", {bold:true, size:16, color:"505050"}),
    run(`${D.sat_date}   `, {size:16}),
    run("PS as of: ", {bold:true, size:16, color:"505050"}),
    run(`${D.ps_report_date}   `, {size:16}),
    run(`YTD Attendance: ${attTotal.absences||0} absences / ${attTotal.tardies||0} tardies   `, {size:16, color:"505050"}),
    run("Ctrl+Click assignments to open Canvas", {size:14, italic:true, color:"888888"}),
  ]}),
];

// Alerts strip (if any)
if (alertText) {
  docChildren.push(new Paragraph({
    spacing:{before:0, after:120},
    shading:{fill:C.alert, type:ShadingType.CLEAR},
    children:[run(alertText, {bold:true, color:C.white, size:17})]
  }));
}

// Main table
docChildren.push(new Table({
  width:{size:TW, type:WidthType.DXA},
  columnWidths:COL,
  rows,
}));

// Grade footer
docChildren.push(new Paragraph({spacing:{before:160, after:40},
  children:[run(gradeFooter, {size:15, italic:true, color:"404040"})]}));

// Teacher email + doc share footnotes
if (teacherFooterParts.length) {
  docChildren.push(new Paragraph({spacing:{before:0, after:40},
    children:[
      run("📧 Teacher emails: ", {bold:true, size:14, color:"505050"}),
      run(teacherFooterParts.join("   ·   "), {size:14, color:"505050"}),
    ]}));
}
if (docFooterParts.length) {
  docChildren.push(new Paragraph({spacing:{before:0, after:40},
    children:[
      run("Student doc shares: ", {bold:true, size:14, color:"505050"}),
      run(docFooterParts.join("   ·   "), {size:14, color:"505050"}),
    ]}));
}

// Canvas Observer tip
docChildren.push(new Paragraph({spacing:{before:40, after:0},
  children:[
    run("💡 ACTION: ", {bold:true, size:14, color:C.missing}),
    run("Enable Canvas Observer on your account to receive Matthew's Canvas notifications (grade alerts, teacher comments, submission confirmations) directly to your Gmail. Matthew generates a pairing code in Canvas Settings → Pair with Observer.", {size:14, italic:true, color:"505050"}),
  ]}));

const doc = new Document({
  styles:{default:{document:{run:{font:"Arial", size:20}}}},
  sections:[{
    properties:{page:{
      size:{width:15840, height:12240},
      margin:{top:720, right:720, bottom:720, left:720}
    }},
    children: docChildren
  }]
});

const sonFirst = (D.son||"Student").split(" ")[0];
const dateStr = new Date().toLocaleDateString("en-US",
  {month:"2-digit",day:"2-digit",year:"numeric"}).replace(/\//g,"-");
const filename = `${sonFirst}_Actionables_${dateStr}.docx`;
const outPath = path.join(__dirname, filename);

// ── HTML sortable version ─────────────────────────────────────────────────────
const allSections = [
  {label:"⚠ MISSING",        items:D.missing||[],        color:"#C00000"},
  {label:"📅 DUE TODAY",      items:D.due_today||[],      color:"#C55A11"},
  {label:"📆 DUE THIS WEEK",  items:D.due_this_week||[],  color:"#7B6000"},
  {label:"🆕 ASSIGNED TODAY", items:D.assigned_today||[], color:"#375623"},
  {label:"⏳ PENDING GRADE",  items:D.pending||[],        color:"#4B0082"},
  {label:"✅ GRADED",         items:D.graded||[],         color:"#404040"},
];

const allRows = [];
for (const s of allSections) {
  for (const e of s.items) allRows.push({...e, section:s.label, sectionColor:s.color});
}

const gradeBar = Object.entries(D.grade_summary||{})
  .map(([cls,v])=>`<span style="margin-right:14px"><b>${cls}:</b> ${v.grade} (${v.absences}abs/${v.tardies}late)</span>`)
  .join("");

const announcementHtml = (D.announcements||[]).map(a=>`<span style="margin-right:12px">⚠ ${a}</span>`).join("");

// Helper: split a due string into date part and time part
// Expects formats like "Apr 10" or "Apr 10 11:59pm" or "Apr 10, 2026 11:59 PM"
function splitDue(due) {
  if (!due || due === '—') return { date: due || '—', time: null };
  // Match a time pattern at the end: digits:digits followed by optional am/pm
  const timeMatch = due.match(/\s+(\d{1,2}:\d{2}\s*[aApP][mM]?)$/);
  if (timeMatch) {
    const time = timeMatch[1].trim();
    const date = due.slice(0, due.length - timeMatch[0].length).trim();
    return { date, time };
  }
  return { date: due, time: null };
}

const htmlRows = allRows.map((e,i)=>{
  const rowBg = e.submission_closed ? 'background:#FFE0E0' : (i%2===0?'':'background:#F4F8FC');
  const statusStyle = e.submission_closed ? 'color:#C00000;font-weight:bold' :
    e.status==='submitted'?'color:#375623;font-weight:bold':
    e.status==='unsubmitted'?'color:#C00000':'color:#4B0082';
  const gradeStyle = (()=>{
    try {
      if(e.grade&&e.grade!=='—'&&e.pts&&e.pts!=='—'){
        const p=e.grade.includes('/')?parseFloat(e.grade.split('/')[0])/parseFloat(e.pts)*100:parseFloat(e.grade)/parseFloat(e.pts)*100;
        return p<60?'color:#C00000;font-weight:bold':p<70?'color:#C55A11':'';
      }
    }catch(err){}
    return '';
  })();
  const statusLabel = e.submission_closed?'🔒 CLOSED':
    e.status==='submitted'?'✓ Submitted':
    e.status==='graded'?'Graded':
    e.status==='pending_review'?'Pending':'Not submitted';

  // Split due into date + hidden time
  const { date: dueDate, time: dueTime } = splitDue(e.due);
  const dueCell = dueTime
    ? `${dueDate}<span class="due-time" title="${dueTime}">${dueTime}</span>`
    : dueDate;

  // Split assigned the same way (keeps consistent sizing)
  const { date: assignedDate, time: assignedTime } = splitDue(e.assigned);
  const assignedCell = assignedTime
    ? `${assignedDate}<span class="due-time" title="${assignedTime}">${assignedTime}</span>`
    : assignedDate;

  return `<tr style="${rowBg}">
    <td style="text-align:center"><span style="background:${e.sectionColor};color:white;padding:1px 5px;border-radius:3px;font-size:11px">${e.section}</span></td>
    <td style="text-align:center">${e.class||'—'}</td>
    <td><a href="${e.url||'#'}" target="_blank">${e.title||'—'}</a></td>
    <td style="text-align:center">${assignedCell}</td>
    <td style="text-align:center">${dueCell}</td>
    <td style="text-align:center">${e.submit_via||'—'}</td>
    <td style="text-align:center">${e.pts||'—'}</td>
    <td style="text-align:center;${gradeStyle}">${e.grade||'—'}</td>
    <td style="text-align:center;${statusStyle}">${statusLabel}</td>
    <td style="font-size:11px;color:#444;font-style:italic;text-align:center">${e.note||'—'}</td>
  </tr>`;
}).join('\n');

const html = `<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<title>${D.son} Actionables</title>
<style>
body{font-family:Arial,sans-serif;font-size:13px;margin:0;padding:12px;background:#f0f4f8}
h1{color:#1F4E79;margin:0 0 4px}
.meta{color:#666;font-size:12px;margin-bottom:8px}
.alerts{background:#843C0C;color:white;padding:6px 12px;border-radius:4px;margin-bottom:8px;font-size:12px}
.grades{background:white;padding:6px 12px;border-radius:4px;margin-bottom:10px;font-size:12px;border-left:4px solid #1F4E79}
table{width:100%;border-collapse:collapse;background:white;border-radius:6px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.1)}
th{background:#1F4E79;color:white;padding:8px 6px;text-align:center;cursor:pointer;user-select:none;font-size:12px;white-space:nowrap}
th:hover{background:#2E6094}
th.asc::after{content:" ▲"}th.desc::after{content:" ▼"}
td{padding:6px;border-bottom:1px solid #E0E0E0;vertical-align:top;font-size:12px;text-align:center}
td:nth-child(3){text-align:left}
tr:hover td{background:#EBF3FB!important}
a{color:#1155CC;text-decoration:none}a:hover{text-decoration:underline}
.filters{margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.filters input,.filters select{padding:5px 8px;border:1px solid #ccc;border-radius:4px;font-size:12px}
#rowCount{color:#666;font-size:12px;margin-left:auto}
/* Due/Assigned column widths */
th:nth-child(4), td:nth-child(4),
th:nth-child(5), td:nth-child(5) { width:90px; min-width:90px; }
/* Hidden time — shown on hover */
.due-time{display:none;font-size:10px;color:#888;margin-left:4px}
td:hover .due-time{display:inline}
</style></head><body>
<h1>${sonFirst.toUpperCase()} &nbsp; DAILY ACTIONABLES</h1>
<div class="meta">Generated: ${D.generated} &nbsp;|&nbsp; PS: ${D.ps_report_date} &nbsp;|&nbsp; Back: ${D.back_to_school} &nbsp;|&nbsp; SAT: ${D.sat_date} &nbsp;|&nbsp; YTD: ${(D.attendance_total||{}).absences||0} abs / ${(D.attendance_total||{}).tardies||0} tardies</div>
${announcementHtml?`<div class="alerts">${announcementHtml}</div>`:''}
<div class="grades"><b>Q3 Grades:</b> ${gradeBar||'Not available — connect Gmail'}</div>
<div class="filters">
  <input id="search" placeholder="🔍 Search..." oninput="filter()" style="width:200px">
  <select id="sec" onchange="filter()"><option value="">All sections</option>${[...new Set(allRows.map(r=>r.section))].map(s=>`<option>${s}</option>`).join('')}</select>
  <select id="cls" onchange="filter()"><option value="">All classes</option>${[...new Set(allRows.map(r=>r.class).filter(Boolean))].sort().map(c=>`<option>${c}</option>`).join('')}</select>
  <select id="sta" onchange="filter()"><option value="">All statuses</option><option>unsubmitted</option><option>submitted</option><option>graded</option><option>closed</option></select>
  <span id="rowCount"></span>
</div>
<table><thead><tr>
  <th onclick="sort(0)">Section</th><th onclick="sort(1)">Class</th><th onclick="sort(2)">Assignment</th>
  <th onclick="sort(3)">Assigned</th><th onclick="sort(4)">Due</th><th onclick="sort(5)">Via</th>
  <th onclick="sort(6)">Pts</th><th onclick="sort(7)">Grade</th><th onclick="sort(8)">Status</th><th onclick="sort(9)">Note</th>
</tr></thead><tbody id="tb">${htmlRows}</tbody></table>
<script>
let sc=-1,sa=true;
function sort(c){
  const tb=document.getElementById('tb');
  const rows=[...tb.querySelectorAll('tr')];
  if(sc===c)sa=!sa;else{sc=c;sa=true;}
  rows.sort((a,b)=>{
    const av=a.cells[c]?.innerText.trim()||'';
    const bv=b.cells[c]?.innerText.trim()||'';
    return sa?av.localeCompare(bv,undefined,{numeric:true}):bv.localeCompare(av,undefined,{numeric:true});
  });
  rows.forEach(r=>tb.appendChild(r));
  document.querySelectorAll('th').forEach((t,i)=>{t.className=i===c?(sa?'asc':'desc'):''});
  count();
}
function filter(){
  const s=document.getElementById('search').value.toLowerCase();
  const sec=document.getElementById('sec').value;
  const cls=document.getElementById('cls').value;
  const sta=document.getElementById('sta').value;
  document.getElementById('tb').querySelectorAll('tr').forEach(r=>{
    const t=r.innerText.toLowerCase();
    const ok=(!s||t.includes(s))&&(!sec||r.cells[0]?.innerText.includes(sec))&&(!cls||r.cells[1]?.innerText===cls)&&(!sta||(sta==='closed'?t.includes('closed'):t.includes(sta)));
    r.style.display=ok?'':'none';
  });
  count();
}
function count(){
  const rows=document.getElementById('tb').querySelectorAll('tr');
  const v=[...rows].filter(r=>r.style.display!=='none').length;
  document.getElementById('rowCount').textContent=v+' of '+rows.length+' assignments';
}
count();
</script></body></html>`;

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(outPath, buf);
  const htmlFilename = `${sonFirst}_Actionables.html`;
  fs.writeFileSync(path.join(__dirname, htmlFilename), html);
  console.log(`✓ Saved: ${filename}`);
  console.log(`✓ Saved: ${htmlFilename}  ← open in browser for sortable view`);
});
