"""Offline evidence viewer, machine-readable results, and artifact inventory."""

from collections import Counter
import base64
import hashlib
from html import escape
from pathlib import Path
from urllib.parse import quote
import xml.etree.ElementTree as ET


STYLE = """
:root{color-scheme:dark;font:15px/1.6 system-ui,sans-serif;color:#e1e9f4;background:#0b1220;overflow-wrap:anywhere}
*{box-sizing:border-box}body{margin:0}a{color:#91ccff;text-underline-offset:3px}button,input{font:inherit}
button{cursor:pointer}main{max-width:1380px;margin:auto;padding:36px 28px 80px}
header{padding:38px;background:linear-gradient(125deg,#172d46,#142331 65%,#12332e);border:1px solid #31465a;border-radius:20px}
.eyebrow{font-size:11px;font-weight:750;letter-spacing:.18em;color:#9eccc5}h1{font-size:clamp(2rem,5vw,3.6rem);line-height:1.1;letter-spacing:-.04em;margin:18px 0}
h2{font-size:1.45rem;line-height:1.3}h3{margin:0;font-size:1rem}p{max-width:88ch}.muted,small{color:#a7b7cb}
.badge{display:inline-block;border:1px solid #58657a;padding:2px 9px;border-radius:99px;font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.05em}
.passed{background:#123e33;color:#9bf3c8;border-color:#286a53}.failed,.interrupted{background:#482630;color:#ffb8bf;border-color:#88505e}
.running,.not-run{background:#303348;color:#d4d6ee}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}
.stat,section.panel{border:1px solid #2c3b4f;border-radius:14px;background:#121e2e;padding:22px}.stat strong{display:block;font-size:30px}
nav{display:flex;gap:20px;flex-wrap:wrap;margin-top:24px}.notice{border-left:3px solid #e7b75c;background:#302b25;padding:12px 18px;border-radius:3px}
.filters{display:flex;gap:12px;flex-wrap:wrap;align-items:center;position:sticky;top:0;padding:14px 0;background:#0b1220;z-index:1}
select,input,button.control{background:#17283d;border:1px solid #455973;border-radius:7px;padding:8px 12px;color:#e1e9f4}
article{border:1px solid #34475d;border-radius:15px;margin:20px 0;padding:24px;background:#111d2d;scroll-margin-top:80px}
.case-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,310px),1fr));gap:16px;margin-top:22px}
.step{border:1px solid #314259;border-radius:10px;overflow:hidden;background:#142236}.step-head{padding:14px}.step-head small{display:block}
.step img{display:block;width:100%;height:230px;object-fit:contain;background:#0b1422}.step a.zoom{display:block}.step-foot{padding:12px;font-size:12px}
.step.failed{border-color:#a46170}.step-foot code{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.error{white-space:pre-wrap;color:#ffbec5;background:#34202a;padding:15px;border-radius:8px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #2c3c50;padding:10px;vertical-align:top}.scroll{overflow:auto}
details{margin:12px 0}summary{cursor:pointer;color:#bcd4eb}pre{overflow:auto;white-space:pre-wrap;background:#0b1523;padding:16px;border-radius:8px;font-size:12px}
dl{display:grid;grid-template-columns:180px 1fr;gap:8px 20px}dt{color:#a7b7cb}dd{margin:0;font-family:ui-monospace,monospace;font-size:12px}
.artifact-list{columns:2;list-style:none;padding:0}.artifact-list li{break-inside:avoid;padding:5px 0}footer{color:#9aacc2;margin-top:30px;font-size:12px}
[hidden]{display:none!important}dialog{max-width:96vw;max-height:96vh;padding:16px;background:#0b1523;color:#e1e9f4;border:1px solid #61738c;border-radius:12px}dialog::backdrop{background:#000c}
dialog img{max-width:90vw;max-height:78vh;object-fit:contain;display:block;margin:auto}.dialog-bar{display:flex;gap:12px;align-items:center;justify-content:space-between;margin-bottom:12px}
@media(max-width:700px){main{padding:16px 12px 48px}header,article{padding:20px}.stats{grid-template-columns:repeat(2,1fr)}dl{display:block}dd{margin-bottom:12px}.artifact-list{columns:1}}
@media print{:root{color-scheme:light;color:#111;background:white}header,article,.stat,section.panel{background:white;color:#111}a{color:#164d80}.filters{position:static}article{break-before:page}.step{break-inside:avoid}.muted,small{color:#444}}
"""

SCRIPT = """
const cards=[...document.querySelectorAll('article[data-profile]')];
const profile=document.querySelector('#profile-filter'), status=document.querySelector('#status-filter'), search=document.querySelector('#search');
function filter(){for(const card of cards)card.hidden=(profile.value!=='all'&&card.dataset.profile!==profile.value)||(status.value!=='all'&&card.dataset.status!==status.value)||!card.textContent.toLowerCase().includes(search.value.toLowerCase());}
for(const field of [profile,status,search])field.addEventListener('input',filter);
const dialog=document.querySelector('dialog'),image=dialog.querySelector('img'),caption=dialog.querySelector('span');
const shots=[...document.querySelectorAll('a.zoom')];let current=0;
function show(index){current=(index+shots.length)%shots.length;image.src=shots[current].href;image.alt=shots[current].querySelector('img').alt;caption.textContent=(current+1)+' / '+shots.length+' · '+image.alt;}
shots.forEach((shot,index)=>shot.addEventListener('click',event=>{event.preventDefault();show(index);dialog.showModal();}));
dialog.querySelector('[data-close]').addEventListener('click',()=>dialog.close());
dialog.querySelector('[data-prev]').addEventListener('click',()=>show(current-1));
dialog.querySelector('[data-next]').addEventListener('click',()=>show(current+1));
dialog.addEventListener('keydown',event=>{if(event.key==='ArrowLeft')show(current-1);if(event.key==='ArrowRight')show(current+1);});
"""

TITLES = {"invalid-password": "Incorrect password is rejected",
          "login-session-logout": "Username → password → application → sign-out",
          "tampered-cookie": "Modified session signature is rejected"}


def text(value):
    return escape(str(value), quote=True)


def safe_path(output, name):
    """Evidence may contain hostile filenames; links must stay inside the bundle."""
    name = str(name)
    path = Path(name)
    if (path.is_absolute() or ".." in path.parts or "\\" in name
            or not (output / path).resolve().is_relative_to(output.resolve())
            or not (output / path).is_file()):
        return None
    return "./" + quote(name, safe="/")


def badge(status):
    css = status if status in ("passed", "failed", "interrupted", "running", "not-run") else "not-run"
    return f'<span class="badge {css}">{text(status)}</span>'


def write_junit(output, data):
    cases = data.get("cases", [])
    errors = data.get("errors", [])
    failures = sum(c["status"] in ("failed", "interrupted") for c in cases) + bool(errors)
    skipped = sum(c["status"] not in ("passed", "failed", "interrupted") for c in cases)
    suite = ET.Element("testsuite", name="AuthCrunch browser login", tests=str(len(cases) + bool(errors)),
                       failures=str(failures), skipped=str(skipped), errors="0")
    for case in cases:
        node = ET.SubElement(suite, "testcase", classname="login." + case["profile"], name=case["id"],
                             time=str(case.get("duration_ms", 0) / 1000))
        if case["status"] in ("failed", "interrupted"):
            ET.SubElement(node, "failure", message=case.get("error", case["status"])).text = case.get("error", case["status"])
        elif case["status"] != "passed":
            ET.SubElement(node, "skipped", message="Case did not complete")
    if errors:
        node = ET.SubElement(suite, "testcase", classname="harness", name="execution")
        ET.SubElement(node, "failure", message="Harness did not complete successfully").text = "\n".join(errors)
    ET.ElementTree(suite).write(output / "junit.xml", encoding="utf-8", xml_declaration=True)


def write_report(output, data):
    output = Path(output)
    cases = data.get("cases", [])
    counts = Counter(c["status"] for c in cases)

    def link(name, label=None):
        href = safe_path(output, name)
        return f'<a href="{href}" download>{text(label or name)}</a>' if href else text(label or name) + " (not recorded)"

    status = data.get("status", "interrupted")
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src \'self\' data:; '
             f'style-src \'unsafe-inline\'; script-src \'sha256-{script_hash}\'; base-uri \'none\'; form-action \'none\'">',
             '<title>AuthCrunch · Login test report</title><style>' + STYLE + '</style></head><body><main>',
             '<header><div class="eyebrow">AUTHCRUNCH / END-TO-END BROWSER EVIDENCE</div>',
             '<h1>The complete sign-in journey.</h1>', badge(status),
             '<p>Real forms, a disposable HTTPS instance, and an isolated browser. Follow each interaction from the first username prompt to access after sign-out.</p>',
             f'<p class="muted">{text(data.get("started_at", ""))} · {text(", ".join(data.get("profiles", [])))} · Chromium</p>',
             '<nav aria-label="Report sections"><a href="#journeys">Browser journeys</a><a href="#execution">Execution</a><a href="#debug">Debug data</a><a href="#artifacts">All files</a></nav></header>',
             '<div class="stats">']
    for value, label in ((counts["passed"], "cases passed"), (counts["failed"] + counts["interrupted"], "cases failed / interrupted"),
                         (counts["not-run"], "cases not run"), (sum(len(c.get("steps", [])) for c in cases), "recorded steps")):
        parts.append(f'<div class="stat"><strong>{value}</strong><span class="muted">{label}</span></div>')
    parts.append('</div>')
    for error in data.get("errors", []):
        parts.append('<pre class="error">' + text(error) + '</pre>')
    parts.extend(['<p class="notice">' + text(data.get("tls_note", "No browser run completed.")) + '</p>',
                  '<h2 id="journeys">Browser journeys</h2><p class="muted">Select a screenshot to enlarge it. Use ← and → to browse; Esc closes the viewer. Every assertion and the raw evidence remain available below.</p>',
                  '<div class="filters"><label>Profile <select id="profile-filter"><option value="all">All</option><option>desktop</option><option>mobile</option></select></label>',
                  '<label>Result <select id="status-filter"><option value="all">All</option><option>passed</option><option>failed</option><option>interrupted</option><option>not-run</option></select></label>',
                  '<label>Find <input id="search" type="search" placeholder="Search steps and checks"></label></div>'])
    for case in cases:
        parts.append(f'<article data-profile="{text(case["profile"])}" data-status="{text(case["status"])}"><div class="case-heading"><div>'
                     f'<div class="eyebrow">{text(case["profile"])}</div><h2>{text(TITLES.get(case["id"],case["id"]))}</h2></div>{badge(case["status"])}</div>')
        parts.append(f'<p class="muted">{case.get("duration_ms", 0)/1000:.2f}s · {len(case.get("checks", []))} checks · '
                     + link(case.get("trace", ""), "Replay trace ZIP") + ' · ' + link(case.get("events", ""), "Network and console") + '</p>')
        if case.get("error") or case.get("cleanup_error"):
            parts.append('<pre class="error">' + text(case.get("error", case.get("cleanup_error"))) + '</pre>')
        parts.append('<div class="steps">')
        for number, step in enumerate(case.get("steps", []), 1):
            parts.append(f'<div class="step {"failed" if step["status"] == "failed" else ""}"><div class="step-head">'
                         f'<small>STEP {number:02d} · {step.get("duration_ms", 0)/1000:.2f}s</small><h3>{text(step["label"])}</h3>{badge(step["status"])}</div>')
            href = safe_path(output, step.get("screenshot", ""))
            if href:
                parts.append(f'<a class="zoom" href="{href}"><img loading="lazy" src="{href}" alt="{text(case["profile"] + ": " + step["label"])}"></a>')
            parts.append('<div class="step-foot"><code>' + text(step.get("url", "No page captured")) + '</code>'
                         + link(step.get("source", ""), "Page source") + '</div>')
            if step.get("error"):
                parts.append('<pre class="error">' + text(step["error"]) + '</pre>')
            parts.append('</div>')
        parts.append('</div><details><summary>Every assertion</summary><div class="scroll"><table><thead><tr><th>Result</th><th>Assertion</th><th>Observed</th></tr></thead><tbody>')
        for check in case.get("checks", []):
            parts.append('<tr><td>' + badge("passed" if check["passed"] else "failed") + '</td><td>' + text(check["description"]) + '</td><td>' + text(check.get("observed") or "—") + '</td></tr>')
        parts.append('</tbody></table></div></details></article>')
    parts.append('<section class="panel" id="execution"><h2>Execution and cleanup</h2><div class="scroll"><table><thead><tr><th>Stage</th><th>Result</th><th>Duration</th></tr></thead><tbody>')
    for stage in data.get("stages", []):
        parts.append(f'<tr><td>{text(stage["name"])}<br>{text(stage.get("error", ""))}</td><td>{badge(stage["status"])}</td><td>{stage.get("duration_ms", 0)/1000:.2f}s</td></tr>')
    parts.append('</tbody></table></div></section><section class="panel" id="debug"><h2>Debug data and provenance</h2><dl>')
    for key, value in {**data.get("candidate", {}), **data.get("environment", {}), "origin": data.get("origin", "Not started"),
                       **data.get("fixture", {}), "ask_url": data.get("ask_url", "Not started"),
                       "server_exit_code": data.get("server_exit_code", "Not started")}.items():
        parts.append('<dt>' + text(key.replace("_", " ")) + '</dt><dd>' + text(value) + '</dd>')
    parts.append('</dl><p>' + ' · '.join(link(name) for name in ("summary.json", "junit.xml", "server.log", "build.log", "setup.log", "source-manifest.json", "SHA256SUMS")) + '</p>')
    server_log = output / "server.log"
    if server_log.exists():
        parts.append('<details><summary>Server log · last 60 lines</summary><pre>' + text("\n".join(server_log.read_text(errors="replace").splitlines()[-60:])) + '</pre></details>')
    parts.append('<p>Trace ZIPs include DOM snapshots, network bodies and disposable session credentials. Replay locally with the pinned tool environment:</p><pre>'
                 + text(str(data.get("environment", {}).get("tool_python", "python")) + " -m playwright show-trace path/to/trace.zip") + '</pre>')
    parts.append('<p class="muted">This run checks local username/password authentication and browser logout. It does not test MFA, external identity providers, certificate trust, or revocation of copied JWTs. Mobile coverage uses Chromium with a mobile viewport and touch emulation.</p></section>')
    write_junit(output, data)
    summary_lines = [f"## AuthCrunch login test: {status.upper()}", "", f"Passed: {counts['passed']} · Failed/interrupted: {counts['failed'] + counts['interrupted']} · Not run: {counts['not-run']}",
                     "", "Download the report artifact, extract it, and open `index.html` for screenshots, assertions, traces and server diagnostics.", "",
                     "| Profile | Case | Result |", "| --- | --- | --- |"]
    summary_lines += [f"| {c['profile']} | {c['id']} | {c['status']} |" for c in cases]
    (output / "summary.md").write_text("\n".join(summary_lines) + "\n")
    parts.append('<section class="panel" id="artifacts"><h2>Evidence inventory</h2><p class="muted">Paths are relative to this report. SHA256SUMS covers every file except itself.</p><ul class="artifact-list">')
    paths = sorted(p for p in output.rglob("*") if p.is_file() and not p.is_symlink() and p.name != "SHA256SUMS")
    for path in paths:
        if path.name == "index.html":
            continue
        parts.append('<li>' + link(str(path.relative_to(output))) + f' <small>({path.stat().st_size:,} B)</small></li>')
    parts.append('</ul></section><footer>AuthCrunch · Evidence from the actual run. Incomplete cases never count as passes. All report assets work offline.</footer>')
    parts.append('<dialog aria-label="Screenshot viewer"><div class="dialog-bar"><button class="control" data-prev aria-label="Previous screenshot">←</button><span></span><button class="control" data-next aria-label="Next screenshot">→</button><button class="control" data-close>Close</button></div><img alt=""></dialog>')
    parts.append('<script>' + SCRIPT + '</script></main></body></html>')
    (output / "index.html").write_text("".join(parts))
    paths = sorted(p for p in output.rglob("*") if p.is_file() and not p.is_symlink() and p.name != "SHA256SUMS")
    hashes = []
    for path in paths:
        with path.open("rb") as stream:
            hashes.append(hashlib.file_digest(stream, "sha256").hexdigest() + "  " + str(path.relative_to(output)))
    (output / "SHA256SUMS").write_text("\n".join(hashes) + "\n")
