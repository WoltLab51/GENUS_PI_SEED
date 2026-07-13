"""Render the deterministic GENUS map as JSON, Markdown and standalone HTML."""
from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from genus import kartografie


ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "docs" / "generated" / "GENUS_KARTOGRAFIE.json"
MARKDOWN_PATH = ROOT / "docs" / "generated" / "GENUS_KARTOGRAFIE.md"
HTML_PATH = ROOT / "docs" / "visual" / "GENUS_KARTOGRAFIE.html"


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _impact_label(value: str) -> str:
    return {
        "direct": "direkt",
        "direct_limited": "direkt, begrenzt",
        "indirect": "indirekt",
        "none": "keine",
        "potential": "potenziell",
    }.get(value, value)


def _source_link(ref: dict[str, Any], *, from_generated: bool = True) -> str:
    prefix = "../../" if from_generated else "../../"
    label = f"{ref['file']}:{ref['line']}"
    # Local Markdown anchor checks treat ``#L42`` as a document heading, not as a
    # repository line link. Keep the exact line in the label and link the real file.
    return f"[{label}]({prefix}{ref['file']})"


def _event_rows(data: dict[str, Any]) -> list[tuple[str, str, str]]:
    node_by_id = {node["id"]: node for node in data["nodes"]}
    projector_by_event = {
        edge["from"]: edge["to"]
        for edge in data["edges"]
        if edge["type"] == "routes_on_replay"
    }
    targets: dict[str, list[str]] = defaultdict(list)
    for edge in data["edges"]:
        if edge["type"] == "writes_projection":
            targets[edge["from"]].append(node_by_id[edge["to"]]["label"])
    rows: list[tuple[str, str, str]] = []
    for node in data["nodes"]:
        if node["type"] != "event" or node["status"] != "projected":
            continue
        projector_id = projector_by_event[node["id"]]
        rows.append(
            (
                node["label"],
                node_by_id[projector_id]["label"],
                ", ".join(sorted(targets[projector_id])),
            )
        )
    return sorted(rows, key=lambda row: (row[2], row[0]))


def _ring_counts(data: dict[str, Any]) -> list[tuple[str, int]]:
    counts = Counter(
        node.get("ring", "-") for node in data["nodes"] if node["type"] == "module"
    )
    return sorted(counts.items())


def render_markdown(data: dict[str, Any] | None = None) -> str:
    data = data or kartografie.build_map()
    summary = data["summary"]
    runtime_report = data["runtime_snapshot"]["sources"][0]["file"].removeprefix("docs/")
    lines = [
        "# GENUS-Kartografie",
        "",
        "> **Status:** generated · aktueller Quellbaumvertrag",
        "> **Quelle:** `genus.kartografie` · nicht von Hand editieren",
        f"> **Inhalt:** `{data['content_sha256'][:16]}` · Regeneration: `genus kartografie build`",
        "",
        "Diese Karte beantwortet nicht nur *wer importiert wen?*, sondern die wichtigere",
        "Frage: **Was kann über welche Kante tatsächlich Wissen, Antwort oder Betrieb",
        "verändern?** Die interaktive Ansicht liegt in",
        "[GENUS_KARTOGRAFIE.html](../visual/GENUS_KARTOGRAFIE.html); die vollständigen",
        "Daten in [GENUS_KARTOGRAFIE.json](GENUS_KARTOGRAFIE.json).",
        "",
        "## Inventar",
        "",
        "| Knoten | Kanten | Python-Module | Events | projiziert / roh | Projektionstabellen | H1-Lücken | Pi-Knoten |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {summary['nodes']} | {summary['edges']} | {summary['modules']} | "
            f"{summary['event_types']} | {summary['projected_events']} / "
            f"{summary['raw_events']} | {summary['projection_tables']} | "
            f"{summary['missing_h1_contracts']} | {summary['runtime_nodes']} |"
        ),
        "",
        "## Kausales Urteil",
        "",
        "GENUS lernt bereits symbolisch: Fakten, Relationen, Episoden, Einstellungen und",
        "enge Intent-Korrekturen werden dauerhaft wirksam. Der Engpass liegt danach:",
        "Deuter klassifiziert, Handler erzeugen fertige Einzelsätze, `_komponiere` verbindet",
        "sie nur und ein Antwort-Outcome mit Feedbackbezug fehlt. Deshalb wächst Wissen",
        "heute deutlich schneller als Gesprächsqualität.",
        "",
        "```text",
        "Wissensquelle → Event → Projektion → Handler → terminale Strings → Ausgabe",
        "                                   ↘ kein AnswerDraft / DialogFrame / Outcome-Kreis",
        "```",
        "",
        "## Event → Projektor → Tabelle",
        "",
        "Der Live-Pfad wendet den Projektor direkt beim Schreiben an; der Router rekonstruiert",
        "denselben Effekt beim Replay. Diese Kanten sind in JSON getrennt.",
        "",
        "| Event | Replay-Projektor | persistiertes Ziel |",
        "|---|---|---|",
    ]
    for event, projector, target in _event_rows(data):
        lines.append(f"| `{_md(event)}` | `{_md(projector)}` | `{_md(target)}` |")

    raw_nodes = sorted(
        node["label"]
        for node in data["nodes"]
        if node["type"] == "event" and node.get("status") == "raw"
    )
    lines.extend(
        [
            "",
            "Die 16 bewusst rohen Events sind kein gemeinsamer Mülleimer: Die JSON-Karte",
            "zeichnet `raw_fold`, `audit_trigger`, `audit_trace` und `audit_only` getrennt.",
            "",
            ", ".join(f"`{event}`" for event in raw_nodes) + ".",
            "",
            "## Lernwirkung auf Antworten",
            "",
            "| Signal | Speicher | Verbraucher | Wirkung | tatsächlicher Effekt | Quelle |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in data["learning_impact"]:
        lines.append(
            "| "
            + " | ".join(_md(item[key]) for key in ("signal", "store", "consumer"))
            + " | "
            + _impact_label(item["impact"])
            + " | "
            + _md(item["effect"])
            + " | "
            + " · ".join(_source_link(ref) for ref in item["sources"])
            + " |"
        )

    lines.extend(
        [
            "",
            "## Fehlende H1-Kanten in sinnvoller Reihenfolge",
            "",
            "1. `ResponseOutcome` samt Response-ID direkt nach dem Dispatch erfassen.",
            "2. Handler auf `AnswerDraft` mit Claims, Provenienz und Unsicherheit umstellen.",
            "3. Aus Session und relevantem Kontext einen `DialogueFrame` bilden.",
            "4. persönliche Episoden in einen physisch löschbaren `MemoryVault` migrieren.",
            "5. `AnswerDraft + DialogueFrame` über einen treuen Diskursrenderer formulieren.",
            "6. explizites Feedback gegatet in eine kuratierte Wirkungsbewertung führen.",
            "",
            "## Modulringe",
            "",
            "Module dürfen mehrere Rollen tragen; der Ring beschreibt nur ihre primäre Lage.",
            "Lazy Imports bleiben als eigene Kanten sichtbar und werden nicht als saubere",
            "Schichtgrenze missverstanden.",
            "Python-Imports sind rekursiv abgeleitet. Dynamische SQL-Stellen werden im JSON",
            "explizit als Grenze geführt; Shell-/systemd-/Cronkanten sind einzeln belegte",
            "Runtime-Verträge und keine behauptete vollständige Shell-Sprachanalyse.",
            "",
            "| Ring | Module |",
            "|---|---:|",
        ]
    )
    for ring, count in _ring_counts(data):
        lines.append(f"| `{ring}` | {count} |")

    lines.extend(
        [
            "",
            "### Sichtbare Importzyklen",
            "",
            "| Mitglieder | Kantenart | Bewertung |",
            "|---|---|---|",
        ]
    )
    for cycle in data["import_cycles"]:
        lines.append(
            f"| {_md(', '.join(cycle['members']))} | "
            f"`{_md(', '.join(cycle['edge_types']))}` | `{cycle['assessment']}` |"
        )

    externals = sorted(
        node["label"] for node in data["nodes"] if node["type"] == "external"
    )
    lines.extend(
        [
            "",
            "Direkt erkannte Nicht-Stdlib-Abhängigkeiten: "
            + ", ".join(f"`{name}`" for name in externals)
            + ".",
            "",
            f"## Pi-Soll-/Ist-Overlay vom {data['runtime_snapshot']['captured_at']}",
            "",
            "Der produktive Pfad war read-only verifiziert: Checkout sauber, Ledger einzeln und",
            "gesund, Cron/Watchdog/Learner/Telegram aktiv, H0.1 laufend, kein GENUS-Listener.",
            "Die Karte exportiert keine Token, IDs, Chat- oder Ledgerinhalte.",
            "`genus kartografie check` prüft diesen datierten Snapshot als Repo-Artefakt,",
            "verbindet sich aber nicht live mit dem Pi. Der vollständige Befund steht im",
            f"[Runtime-Audit](../{runtime_report}).",
            "",
            "| Schärfungspunkt | Schwere | Quelle |",
            "|---|---|---|",
        ]
    )
    for finding in data["findings"]:
        if not finding["id"].startswith("pi-"):
            continue
        links = " · ".join(_source_link(ref) for ref in finding["sources"])
        lines.append(
            f"| {_md(finding['statement'])} | `{finding['severity']}` | {links} |"
        )
    lines.extend(
        [
            "",
            "## Pflegevertrag",
            "",
            "- `genus kartografie build` erzeugt JSON, Markdown und die interaktive Ansicht.",
            "- `genus kartografie check` bricht bei Drift oder ungültigen Quellenkanten ab.",
            "- CI prüft Vollständigkeit von Event-Produzenten, Projektionszielen, Replay-Tabellen,",
            "  Quellenreferenzen und generierten Dateien.",
            "- Live-Zahlen gehören nicht in diesen deterministischen Kern. Ein Pi-Befund bleibt",
            "  ein datierter Report; die Betriebsansicht zeigt den deploybaren Sollpfad.",
            f"- {data['summary']['dynamic_sql_calls']} dynamische SQL-Aufrufe bleiben explizit",
            "  als Analysegrenze im JSON sichtbar; Tabellenziele werden dort nicht geraten.",
            "",
        ]
    )
    return "\n".join(lines)


def _safe_script_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace(
        "</", "<\\/"
    )


def render_html(data: dict[str, Any] | None = None) -> str:
    data = data or kartografie.build_map()
    payload = _safe_script_json(data)
    digest = html.escape(data["content_sha256"][:16])
    return f'''<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GENUS-Kartografie</title>
<style>
:root {{ color-scheme: light dark; --font-size-base: 16px; --background: Canvas; --foreground: CanvasText; --card: ButtonFace; --card-foreground: ButtonText; --muted: color-mix(in srgb, CanvasText 8%, Canvas); --muted-foreground: color-mix(in srgb, CanvasText 70%, Canvas); --border: color-mix(in srgb, CanvasText 24%, Canvas); --primary: AccentColor; --primary-foreground: AccentColorText; --accent: color-mix(in srgb, AccentColor 14%, Canvas); --destructive: Mark; --series-1: AccentColor; --series-2: LinkText; --series-3: VisitedText; --series-4: GrayText; font: 400 var(--font-size-base) system-ui, sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--background); color: var(--foreground); }}
main {{ width: min(1180px, 100%); margin: 0 auto; padding: clamp(16px, 3vw, 36px); }}
h1, h2 {{ font-weight: 500; }}
h1 {{ margin: 0 0 6px; }}
h2 {{ margin: 28px 0 12px; }}
p {{ max-width: 78ch; }}
code {{ font-family: ui-monospace, monospace; }}
.muted {{ color: var(--muted-foreground); }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(140px,1fr)); gap: 10px; margin: 20px 0; }}
.stat, .detail {{ background: var(--card); color: var(--card-foreground); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }}
.stat strong {{ display: block; font-weight: 500; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 20px 0 14px; }}
button {{ font: inherit; color: inherit; background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; cursor: pointer; }}
button[aria-pressed="true"], button.selected {{ background: var(--primary); color: var(--primary-foreground); border-color: transparent; }}
.canvas {{ min-height: 320px; }}
.lanes {{ display: grid; grid-template-columns: repeat(var(--lane-count, 4), minmax(130px,1fr)); gap: 22px; align-items: start; }}
.lane {{ min-width: 0; }}
.lane h3 {{ margin: 0 0 8px; font-weight: 500; color: var(--muted-foreground); }}
.node {{ width: 100%; text-align: left; margin: 0 0 8px; padding: 9px; position: relative; overflow-wrap: anywhere; }}
.node[data-status="missing_h1"] {{ border-style: dashed; }}
.node.neighbor, .tile.neighbor {{ background: var(--accent); }}
.node[data-type="event"] {{ background: color-mix(in srgb, var(--series-1) 10%, var(--card)); }}
.node[data-type="projector"] {{ background: color-mix(in srgb, var(--series-2) 10%, var(--card)); }}
.node[data-type="table"] {{ background: color-mix(in srgb, var(--series-3) 10%, var(--card)); }}
.edge-list {{ margin: 18px 0 0; padding: 0; list-style: none; columns: 2; column-gap: 24px; }}
.edge-list li {{ break-inside: avoid; padding: 4px 0; color: var(--muted-foreground); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(130px,1fr)); gap: 7px; }}
.tile {{ min-height: 48px; overflow-wrap: anywhere; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 14px; margin: 14px 0; color: var(--muted-foreground); }}
.swatch {{ display: inline-block; width: 12px; height: 12px; margin-right: 5px; border-radius: 3px; vertical-align: -1px; background: var(--muted); }}
.swatch.event {{ background: color-mix(in srgb, var(--series-1) 35%, var(--card)); }}
.swatch.projector {{ background: color-mix(in srgb, var(--series-2) 35%, var(--card)); }}
.swatch.table {{ background: color-mix(in srgb, var(--series-3) 35%, var(--card)); }}
.detail {{ margin-top: 18px; min-height: 62px; }}
.detail a {{ color: LinkText; }}
.impact-list {{ display: grid; gap: 10px; }}
.impact-row {{ border-left: 4px solid var(--series-4); padding: 8px 10px; }}
.impact-row.direct {{ border-left-color: var(--series-1); }}
.impact-row.indirect, .impact-row.potential {{ border-left-color: var(--series-2); }}
.impact-row h3 {{ margin: 0 0 6px; font-weight: 500; }}
.impact-row dl {{ display: grid; grid-template-columns: max-content minmax(0,1fr); gap: 4px 10px; margin: 0; }}
.impact-row dt {{ color: var(--muted-foreground); }}
.impact-row dd {{ margin: 0; }}
.impact-row a {{ color: LinkText; }}
.sr-only {{ position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }}
@media (max-width: 900px) {{ .lanes {{ grid-template-columns: repeat(3,minmax(0,1fr)); }} }}
@media (max-width: 700px) {{ .lanes {{ grid-template-columns: 1fr; }} .edge-list {{ columns: 1; }} .impact-row dl {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
  <h1>GENUS-Kartografie</h1>
  <p class="muted">Quellengebundener Ist-Stand · Inhalt <code>{digest}</code></p>
  <div class="stats" id="stats" aria-label="Inventar"></div>
  <nav class="controls" id="views" aria-label="Kartenansicht"></nav>
  <p id="view-description" class="muted"></p>
  <section id="detail" class="detail" aria-live="polite">Knoten auswählen, um Wirkung und Quelle zu sehen.</section>
  <section id="canvas" class="canvas" aria-label="Aktuelle Kartenansicht"></section>
</main>
<script id="map-data" type="application/json">{payload}</script>
<script>
(() => {{
  'use strict';
  const data = JSON.parse(document.getElementById('map-data').textContent);
  const byId = new Map(data.nodes.map(n => [n.id, n]));
  const stats = document.getElementById('stats');
  const controls = document.getElementById('views');
  const canvas = document.getElementById('canvas');
  const detail = document.getElementById('detail');
  const description = document.getElementById('view-description');
  const labels = [['Module', data.summary.modules], ['Events', data.summary.event_types], ['Kanten', data.summary.edges]];
  labels.forEach(([label, value]) => {{ const el=document.createElement('div'); el.className='stat'; const strong=document.createElement('strong'); strong.textContent=String(value); const span=document.createElement('span'); span.textContent=label; el.append(strong,span); stats.appendChild(el); }});
  let activeView=null;
  const statusLabels={{missing_h1:'fehlt in H1',active_voice_off:'aktiv, Stimme aus',no_weight_learning:'kein Gewichtstraining',known_bottleneck:'bekannter Engpass',terminal_strings:'terminale Strings',direct:'direkt',direct_limited:'direkt, begrenzt',indirect:'indirekt',none:'keine',potential:'potenziell'}};
  const pretty = value => statusLabels[value] || String(value||'').replaceAll('_',' ');
  function appendSources(parent, refs) {{
    (refs||[]).forEach((s,index)=>{{ if(index) parent.append(' · '); const a=document.createElement('a'); a.href='../../'+s.file+'#L'+s.line; a.textContent=s.file+':'+s.line; parent.appendChild(a); }});
  }}
  function selectNode(id, button) {{
    document.querySelectorAll('.node.selected,.tile.selected,.node.neighbor,.tile.neighbor').forEach(el => {{ el.classList.remove('selected','neighbor'); el.setAttribute('aria-pressed','false'); }});
    if (button) {{ button.classList.add('selected'); button.setAttribute('aria-pressed','true'); }}
    const n=byId.get(id); if(!n) return;
    const title=document.createElement('strong'); title.textContent=n.label;
    const meta=document.createElement('span'); meta.className='muted'; const roles=n.roles?.length?' · Rollen: '+n.roles.map(pretty).join(', '):''; const ring=n.ring?' · Ring: '+pretty(n.ring):''; meta.textContent=' · '+pretty(n.type)+(n.status?' · '+pretty(n.status):'')+ring+roles;
    const refs=document.createElement('div'); appendSources(refs,n.sources);
    detail.replaceChildren(title,meta,refs);
    const wanted=new Set(activeView?.nodes||[]); const edgeTypes=new Set(activeView?.edge_types||[]);
    const related=data.edges.filter(e=>wanted.has(e.from)&&wanted.has(e.to)&&edgeTypes.has(e.type)&&(e.from===id||e.to===id));
    if(related.length) {{
      const list=document.createElement('ul'); list.setAttribute('aria-label','Direkte Abhängigkeiten');
      related.slice(0,20).forEach(e=>{{ const neighbor=e.from===id?e.to:e.from; const li=document.createElement('li'); li.append((e.from===id?'→ ':'← ')+byId.get(neighbor).label+' · '+pretty(e.type)+' · '); appendSources(li,e.sources); list.appendChild(li); document.querySelectorAll('[data-node-id]').forEach(el=>{{if(el.dataset.nodeId===neighbor)el.classList.add('neighbor');}}); }});
      if(related.length>20) {{ const more=document.createElement('li'); more.textContent=(related.length-20)+' weitere Kanten stehen vollständig in JSON.'; list.appendChild(more); }}
      detail.appendChild(list);
    }}
    detail.scrollIntoView({{block:'nearest'}});
  }}
  function buttonFor(n, cls='node') {{
    const b=document.createElement('button'); b.type='button'; b.className=cls; b.textContent=n.label; b.dataset.nodeId=n.id; b.dataset.type=n.type; b.dataset.status=n.status||''; b.setAttribute('aria-pressed','false'); b.setAttribute('aria-label', n.label+', '+pretty(n.type)+(n.status?', '+pretty(n.status):'')); b.addEventListener('click',()=>selectNode(n.id,b)); return b;
  }}
  function renderFlow(view) {{
    const wanted=new Set(view.nodes); const nodes=data.nodes.filter(n=>wanted.has(n.id));
    const eventStages={{event_producer:0,event:1,projector:2,module:2,table:3}};
    const groups=new Map(); nodes.forEach(n=>{{ const stage=view.id==='ereignisse'?(eventStages[n.type]??2):(Number.isInteger(n.stage)?n.stage:0); if(!groups.has(stage))groups.set(stage,[]); groups.get(stage).push(n); }});
    const wrap=document.createElement('div'); wrap.className='lanes'; wrap.style.setProperty('--lane-count',Math.min(5,groups.size));
    [...groups].sort((a,b)=>a[0]-b[0]).forEach(([stage,items])=>{{ const lane=document.createElement('section'); lane.className='lane'; const h=document.createElement('h3'); h.textContent='Stufe '+stage; lane.appendChild(h); items.sort((a,b)=>a.label.localeCompare(b.label,'de')).forEach(n=>lane.appendChild(buttonFor(n))); wrap.appendChild(lane); }});
    canvas.appendChild(wrap);
    const edges=data.edges.filter(e=>wanted.has(e.from)&&wanted.has(e.to)&&(view.edge_types||[]).includes(e.type));
    if(edges.length<=40) {{ const list=document.createElement('ul'); list.className='edge-list'; list.setAttribute('aria-label','Wirkungskanten'); edges.forEach(e=>{{ const li=document.createElement('li'); li.textContent=byId.get(e.from).label+' → '+byId.get(e.to).label+' · '+pretty(e.type); list.appendChild(li); }}); canvas.appendChild(list); }} else {{ const note=document.createElement('p'); note.className='muted'; note.textContent=edges.length+' Kanten: Knoten auswählen, um seine direkten Abhängigkeiten samt Quellen zu sehen.'; canvas.appendChild(note); }}
  }}
  function renderModules(view) {{
    const wanted=new Set(view.nodes); const modules=data.nodes.filter(n=>wanted.has(n.id)).sort((a,b)=>a.label.localeCompare(b.label,'de'));
    const grid=document.createElement('div'); grid.className='grid'; modules.forEach(n=>{{ const short=n.label.startsWith('genus.')?n.label.slice(6):n.label.startsWith('deploy.')?'deploy/'+n.label.slice(7):n.label; const b=buttonFor({{...n,label:short}},'tile'); b.dataset.type=n.type; grid.appendChild(b); }}); canvas.appendChild(grid);
    const legend=document.createElement('div'); legend.className='legend'; legend.textContent='Eine Zelle pro Modul oder externer Direktabhängigkeit; Auswahl zeigt Ring und Quellfundstelle.'; canvas.appendChild(legend);
  }}
  function renderLearning() {{
    const list=document.createElement('div'); list.className='impact-list';
    data.learning_impact.forEach(i=>{{ const impact=i.impact.startsWith('direct')?'direct':i.impact; const article=document.createElement('article'); article.className='impact-row '+impact; const h=document.createElement('h3'); h.textContent=i.signal; const dl=document.createElement('dl'); [['Wirkung',pretty(i.impact)],['Speicher',i.store],['Verbraucher',i.consumer],['Effekt',i.effect]].forEach(([term,value])=>{{const dt=document.createElement('dt');dt.textContent=term;const dd=document.createElement('dd');dd.textContent=value;dl.append(dt,dd);}}); const dt=document.createElement('dt');dt.textContent='Quelle';const dd=document.createElement('dd');appendSources(dd,i.sources);dl.append(dt,dd);article.append(h,dl);list.appendChild(article); }}); canvas.appendChild(list);
  }}
  function activate(view) {{
    activeView=view;
    controls.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view.id)));
    description.textContent=view.description; canvas.replaceChildren(); detail.textContent=view.id==='lernen'?'Alle Lernwirkungen sind mit Speicher, Verbraucher und Quelle aufgeführt.':'Knoten auswählen, um direkte Abhängigkeiten, Wirkung und Quellen zu sehen.';
    if(view.id==='module') renderModules(view); else if(view.id==='lernen') renderLearning(); else renderFlow(view);
  }}
  data.views.forEach(view=>{{ const b=document.createElement('button'); b.type='button'; b.dataset.view=view.id; b.textContent=view.label; b.setAttribute('aria-pressed','false'); b.addEventListener('click',()=>activate(view)); controls.appendChild(b); }});
  activate(data.views[0]);
}})();
</script>
</body>
</html>
'''


def expected_artifacts(data: dict[str, Any] | None = None) -> dict[Path, str]:
    data = data or kartografie.build_map()
    return {
        JSON_PATH: kartografie.render_json(data),
        MARKDOWN_PATH: render_markdown(data),
        HTML_PATH: render_html(data),
    }


def write_artifacts(data: dict[str, Any] | None = None) -> list[Path]:
    written: list[Path] = []
    for path, content in expected_artifacts(data).items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def stale_artifacts(data: dict[str, Any] | None = None) -> list[Path]:
    stale: list[Path] = []
    for path, expected in expected_artifacts(data).items():
        if not path.is_file() or path.read_text(encoding="utf-8") != expected:
            stale.append(path)
    return stale
