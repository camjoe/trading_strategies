from __future__ import annotations

import html
import json
from typing import Any

DEFAULT_VIEWER_TITLE = "Database Diagram Viewer"


def render_html(payload: dict[str, Any]) -> str:
    payload_json = json.dumps(payload, indent=2, sort_keys=True)
    escaped_payload = html.escape(payload_json, quote=False)
    table_count = len(payload["tables"])
    generated_at = html.escape(str(payload.get("generatedAt", "unknown")))
    viewer_title = html.escape(str(payload.get("title") or DEFAULT_VIEWER_TITLE))
    source_text = html.escape(str(payload.get("source", "schema payload")))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{viewer_title}</title>
  <style>
    :root {{
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d0d5dd;
      --cascade: #0f8b5f;
      --no-action: #667085;
      --restrict: #b54708;
      --accent: #1d4ed8;
      --shadow: 0 12px 28px rgba(16, 24, 40, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background: var(--bg);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 24px;
      padding: 20px 24px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 10;
    }}
    h1 {{ margin: 0 0 6px; font-size: 22px; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .toolbar {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    button, input {{
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 6px;
      font: inherit;
      height: 34px;
    }}
    button {{ padding: 0 10px; cursor: pointer; }}
    button[aria-pressed="true"] {{
      border-color: var(--accent);
      color: var(--accent);
      background: #eef4ff;
    }}
    input {{ min-width: 220px; padding: 0 10px; }}
    .tabs {{
      display: flex;
      gap: 6px;
      padding: 12px 24px;
      overflow-x: auto;
      background: #eef1f5;
      border-bottom: 1px solid var(--line);
    }}
    .tab {{
      white-space: nowrap;
      min-width: max-content;
    }}
    main {{
      height: calc(100vh - 118px);
      overflow: hidden;
      position: relative;
    }}
    .info-panel {{
      position: absolute;
      top: 14px;
      right: 18px;
      width: 340px;
      max-height: calc(100% - 32px);
      overflow: auto;
      padding: 0;
      background: rgba(255, 255, 255, 0.92);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      z-index: 5;
      font-size: 12px;
    }}
    .info-panel > summary {{
      padding: 10px 12px;
      color: var(--ink);
      font-weight: 760;
      border-bottom: 1px solid var(--line);
    }}
    .info-panel-body {{
      display: grid;
      gap: 12px;
      padding: 12px;
    }}
    .panel-section {{
      display: grid;
      gap: 7px;
    }}
    .panel-section h2,
    .panel-section h3 {{
      margin: 0;
      font-size: 14px;
      color: var(--ink);
    }}
    .panel-section p {{ margin: 0; color: var(--muted); line-height: 1.35; }}
    .canvas {{
      position: absolute;
      inset: 0;
      overflow: hidden;
      cursor: grab;
      background-image:
        linear-gradient(#e4e7ec 1px, transparent 1px),
        linear-gradient(90deg, #e4e7ec 1px, transparent 1px);
      background-size: 24px 24px;
    }}
    .canvas.dragging {{ cursor: grabbing; }}
    .stage {{
      position: absolute;
      width: 5200px;
      min-height: 9000px;
      transform-origin: 0 0;
    }}
    .lines {{
      position: absolute;
      inset: 0;
      width: 5200px;
      height: 9000px;
      pointer-events: none;
      overflow: visible;
    }}
    .section-label {{
      position: absolute;
      min-width: 260px;
      height: 34px;
      padding: 7px 12px 6px;
      border-left: 6px solid var(--section-color);
      border-radius: 7px;
      background: rgba(255, 255, 255, 0.86);
      color: var(--section-color);
      box-shadow: var(--shadow);
      font-size: 15px;
      font-weight: 760;
      letter-spacing: 0;
      cursor: grab;
      user-select: none;
    }}
    .section-label.moving {{ cursor: grabbing; z-index: 3; }}
    .table-card {{
      position: absolute;
      width: 300px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      overflow: hidden;
      cursor: grab;
      user-select: none;
    }}
    .table-card.moving {{ cursor: grabbing; z-index: 3; }}
    .table-card.hidden {{ opacity: 0.12; }}
    .table-card header {{
      position: static;
      padding: 10px 12px;
      display: block;
      border-bottom: 1px solid var(--line);
      background: #f9fafb;
    }}
    .table-card h3 {{ margin: 0; font-size: 15px; }}
    .column-list {{
      margin: 0;
      padding: 8px 0;
      list-style: none;
    }}
    .column {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      padding: 4px 10px;
      border-bottom: 1px solid #f2f4f7;
      font-size: 12px;
    }}
    .column:last-child {{ border-bottom: 0; }}
    .column-name {{ font-weight: 650; overflow-wrap: anywhere; }}
    .column.sectioned {{
      border-left: 3px solid var(--column-section-color);
      padding-left: 7px;
    }}
    .column.sectioned .column-name {{ color: var(--column-section-color); }}
    .column-type {{ color: var(--muted); text-align: right; }}
    .badges {{
      grid-column: 1 / -1;
      display: flex;
      gap: 4px;
      flex-wrap: wrap;
    }}
    .badge {{
      border-radius: 999px;
      padding: 1px 6px;
      background: #eef2f6;
      color: #344054;
      font-size: 10px;
      line-height: 16px;
    }}
    .badge.pk {{ background: #dbeafe; color: #1e40af; }}
    .badge.fk {{ background: #dcfce7; color: #166534; }}
    details {{
      border-top: 1px solid var(--line);
      padding: 8px 10px 10px;
      font-size: 12px;
    }}
    summary {{ cursor: pointer; color: var(--muted); }}
    .index-list {{ margin: 8px 0 0; padding-left: 18px; color: var(--muted); }}
    .rel-line {{ fill: none; stroke-width: 2.3; stroke: #475467; }}
    .rel-line.CASCADE {{ stroke: var(--cascade); }}
    .rel-line.NO_ACTION {{ stroke: var(--no-action); stroke-dasharray: 5 5; }}
    .rel-line.RESTRICT {{ stroke: var(--restrict); stroke-dasharray: 2 4; }}
    .rel-label-bg {{ fill: rgba(255, 255, 255, 0.96); stroke: var(--line); }}
    .rel-label {{
      font-size: 12px;
      font-weight: 650;
      fill: var(--ink);
      paint-order: stroke;
      stroke: white;
      stroke-width: 5px;
      stroke-linejoin: round;
    }}
    .legend-row {{ display: flex; gap: 7px; align-items: center; }}
    .color-key {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 6px;
    }}
    .color-key-item {{
      display: flex;
      align-items: center;
      gap: 7px;
      color: var(--muted);
    }}
    .color-dot {{
      width: 12px;
      height: 12px;
      border-radius: 999px;
      background: var(--section-color);
      flex: 0 0 auto;
    }}
    .swatch {{ width: 24px; height: 3px; display: inline-block; vertical-align: middle; margin-right: 4px; }}
    .swatch.fk {{ background: #475467; }}
    .swatch.cascade {{ background: var(--cascade); }}
    .swatch.no-action {{ background: repeating-linear-gradient(90deg, var(--no-action) 0 5px, transparent 5px 9px); }}
    .swatch.restrict {{ background: repeating-linear-gradient(90deg, var(--restrict) 0 2px, transparent 2px 6px); }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>{viewer_title}</h1>
      <div class="meta">Source: {source_text}. Generated: {generated_at}. Tables: {table_count}.</div>
    </div>
    <div class="toolbar" aria-label="Diagram controls">
      <input id="search" type="search" placeholder="Search tables or columns" aria-label="Search tables or columns">
      <button id="zoomOut" type="button">-</button>
      <button id="zoomReset" type="button">Reset</button>
      <button id="zoomIn" type="button">+</button>
      <button id="toggleIndexes" type="button" aria-pressed="false">Indexes</button>
      <button id="toggleLabels" type="button" aria-pressed="false">Labels</button>
      <button id="toggleConstraints" type="button" aria-pressed="false">Constraints</button>
      <button id="toggleDeleteActions" type="button" aria-pressed="false">Delete actions</button>
      <button id="resetLayout" type="button">Reset layout</button>
    </div>
  </header>
  <nav id="tabs" class="tabs" aria-label="Diagram views"></nav>
  <main>
    <details class="info-panel" open>
      <summary>Diagram info</summary>
      <div class="info-panel-body">
        <section class="panel-section" aria-live="polite">
          <h2 id="viewTitle"></h2>
          <p id="viewDescription"></p>
        </section>
        <section class="panel-section" aria-label="Relationship legend">
          <h3>Relationship key</h3>
          <span class="legend-row">
            <i class="swatch fk"></i>Arrow: child/FK table points to referenced parent table.
          </span>
          <span class="legend-row">
            <i class="swatch cascade"></i>Delete action on: CASCADE deletes child rows automatically.
          </span>
          <span class="legend-row">
            <i class="swatch no-action"></i>Delete action on: NO ACTION blocks parent deletion until children are
            handled.
          </span>
          <span class="legend-row">
            <i class="swatch restrict"></i>Delete action on: RESTRICT intentionally blocks deletion.
          </span>
          <span class="legend-row">Drag table cards or section headers to rearrange a view.</span>
        </section>
        <section class="panel-section">
          <h3>Color key</h3>
          <div id="colorKey" class="color-key"></div>
        </section>
      </div>
    </details>
    <section id="canvas" class="canvas" aria-label="Database diagram canvas">
      <div id="stage" class="stage">
        <svg id="lines" class="lines" aria-hidden="true"></svg>
        <div id="sections"></div>
        <div id="cards"></div>
      </div>
    </section>
  </main>
  <script id="schema-payload" type="application/json">{escaped_payload}</script>
  <script>
    const payload = JSON.parse(document.getElementById("schema-payload").textContent);
    const tablesByName = new Map(payload.tables.map((table) => [table.name, table]));
    const sectionsById = new Map(payload.sections.map((section) => [section.id, section]));
    const tabsEl = document.getElementById("tabs");
    const cardsEl = document.getElementById("cards");
    const sectionsEl = document.getElementById("sections");
    const colorKeyEl = document.getElementById("colorKey");
    const linesEl = document.getElementById("lines");
    const canvasEl = document.getElementById("canvas");
    const stageEl = document.getElementById("stage");
    const searchEl = document.getElementById("search");
    const viewTitleEl = document.getElementById("viewTitle");
    const viewDescriptionEl = document.getElementById("viewDescription");
    const toggleIndexesEl = document.getElementById("toggleIndexes");
    const toggleLabelsEl = document.getElementById("toggleLabels");
    const toggleConstraintsEl = document.getElementById("toggleConstraints");
    const toggleDeleteActionsEl = document.getElementById("toggleDeleteActions");
    let activeView = payload.views[0];
    let scale = 0.78;
    let offsetX = 40;
    let offsetY = 72;
    let showIndexes = false;
    let showLabels = false;
    let showConstraints = false;
    let showDeleteActions = false;
    let dragState = null;
    let cardDragState = null;
    let sectionDragState = null;
    let currentPositions = new Map();
    let currentSectionRegions = [];

    function storageKey() {{
      return `database-diagram-layout:${{activeView.id}}`;
    }}

    function fkColumns(table) {{
      return new Set(table.foreignKeys.map((fk) => fk.column));
    }}

    function tableMarkup(table) {{
      const foreignColumns = fkColumns(table);
      const columns = table.columns.map((column) => {{
        const badges = [];
        const columnSectionStyle = column.section ? ` style="--column-section-color: ${{column.section.color}}"` : "";
        const columnSectionClass = column.section ? " sectioned" : "";
        if (column.primaryKeyPosition) badges.push('<span class="badge pk">PK</span>');
        if (foreignColumns.has(column.name)) badges.push('<span class="badge fk">FK</span>');
        if (showConstraints) {{
          if (column.notNull) badges.push('<span class="badge">NOT NULL</span>');
          if (column.default !== null) {{
            badges.push(`<span class="badge">DEFAULT ${{escapeHtml(String(column.default))}}</span>`);
          }}
        }}
        return `
          <li class="column${{columnSectionClass}}"${{columnSectionStyle}}>
            <span class="column-name">${{escapeHtml(column.name)}}</span>
            <span class="column-type">${{escapeHtml(column.type || "ANY")}}</span>
            <span class="badges">${{badges.join("")}}</span>
          </li>`;
      }}).join("");
      const indexes = table.indexes.length
        ? table.indexes
            .map((index) => `
              <li>
                ${{index.unique ? "UNIQUE " : ""}}${{escapeHtml(index.name)}}
                (${{index.columns.map(escapeHtml).join(", ")}})
              </li>`)
            .join("")
        : "<li>No indexes</li>";
      return `
        <article class="table-card" id="table-${{table.name}}" data-table="${{table.name}}">
          <header><h3>${{escapeHtml(table.name)}}</h3></header>
          <ul class="column-list">${{columns}}</ul>
          <details class="indexes" ${{showIndexes ? "open" : ""}}>
            <summary>Indexes (${{table.indexes.length}})</summary>
            <ul class="index-list">${{indexes}}</ul>
          </details>
        </article>`;
    }}

    function escapeHtml(value) {{
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }}

    function layoutTables(tables) {{
      const cardWidth = 410;
      const cardHeight = 760;
      const titleHeight = 54;
      const sectionGap = 150;
      const defaults = new Map();
      const sectionRegions = [];
      let cursorY = 0;

      for (const group of groupedTables(tables)) {{
        const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(group.tables.length * 1.4))));
        const rows = Math.ceil(group.tables.length / columns);
        const sectionTop = cursorY;
        const tableTop = cursorY + titleHeight;
        group.tables.forEach((table, index) => {{
          defaults.set(table.name, {{
            x: (index % columns) * cardWidth,
            y: tableTop + Math.floor(index / columns) * cardHeight,
          }});
        }});
        sectionRegions.push({{
          id: group.section.id,
          label: group.section.label,
          color: group.section.color,
          tables: group.tables.map((table) => table.name),
          x: 0,
          y: sectionTop,
          width: columns * cardWidth - 40,
          height: titleHeight + rows * cardHeight - 80,
          count: group.tables.length,
          showTitle: group.tables.length > 2,
        }});
        cursorY += titleHeight + rows * cardHeight + sectionGap;
      }}
      const saved = loadSavedPositions();
      for (const [tableName, position] of Object.entries(saved)) {{
        if (defaults.has(tableName) && Number.isFinite(position.x) && Number.isFinite(position.y)) {{
          defaults.set(tableName, {{ x: position.x, y: position.y }});
        }}
      }}
      return {{ positions: defaults, sections: sectionRegions }};
    }}

    function groupedTables(tables) {{
      const remaining = new Set(tables.map((table) => table.name));
      const groups = [];
      for (const section of payload.sections) {{
        const sectionTables = tables.filter((table) => table.section?.id === section.id);
        if (!sectionTables.length) continue;
        sectionTables.forEach((table) => remaining.delete(table.name));
        groups.push({{ section, tables: sectionTables }});
      }}
      const otherTables = tables.filter((table) => remaining.has(table.name));
      if (otherTables.length) {{
        groups.push({{
          section: {{ id: "other", label: "Other", color: "#475467" }},
          tables: otherTables,
        }});
      }}
      return groups;
    }}

    function loadSavedPositions() {{
      try {{
        return JSON.parse(localStorage.getItem(storageKey()) || "{{}}");
      }} catch {{
        return {{}};
      }}
    }}

    function saveCurrentPositions() {{
      const value = Object.fromEntries(currentPositions.entries());
      localStorage.setItem(storageKey(), JSON.stringify(value));
    }}

    function relationshipsFor(viewTables) {{
      const tableSet = new Set(viewTables.map((table) => table.name));
      const relationships = [];
      for (const table of viewTables) {{
        for (const fk of table.foreignKeys) {{
          if (tableSet.has(fk.referencesTable)) {{
            relationships.push({{
              from: table.name,
              to: fk.referencesTable,
              column: fk.column,
              referencesColumn: fk.referencesColumn,
              onDelete: fk.onDelete,
              sectionId: table.section?.id || "other",
              sectionColor: table.section?.color || "#475467",
            }});
          }}
        }}
      }}
      return relationships;
    }}

    function activeViewTables() {{
      return activeView.tables.map((name) => tablesByName.get(name)).filter(Boolean);
    }}

    function renderTabs() {{
      tabsEl.innerHTML = payload.views.map((view) => `
        <button class="tab" type="button" aria-pressed="${{view.id === activeView.id}}" data-view="${{view.id}}">
          ${{escapeHtml(view.label)}}
        </button>`).join("");
      tabsEl.querySelectorAll("button").forEach((button) => {{
        button.addEventListener("click", () => {{
          activeView = payload.views.find((view) => view.id === button.dataset.view);
          render();
        }});
      }});
    }}

    function render() {{
      const query = searchEl.value.trim().toLowerCase();
      const viewTables = activeViewTables();
      const layout = layoutTables(viewTables);
      currentPositions = layout.positions;
      viewTitleEl.textContent = activeView.label;
      viewDescriptionEl.textContent = activeView.description;
      renderSections(layout.sections);
      cardsEl.innerHTML = viewTables.map(tableMarkup).join("");
      for (const table of viewTables) {{
        const card = document.getElementById(`table-${{table.name}}`);
        const pos = currentPositions.get(table.name);
        card.style.left = `${{pos.x}}px`;
        card.style.top = `${{pos.y}}px`;
        const matches = !query
          || table.name.toLowerCase().includes(query)
          || table.columns.some((column) => column.name.toLowerCase().includes(query));
        card.classList.toggle("hidden", !matches);
      }}
      attachCardDragHandlers();
      attachSectionDragHandlers();
      drawRelationships(relationshipsFor(viewTables), currentPositions);
      renderTabs();
      applyTransform();
    }}

    function renderSections(sections) {{
      currentSectionRegions = sectionDisplayRegions(sections);
      sectionsEl.innerHTML = currentSectionRegions
        .filter((section) => section.showTitle)
        .map((section) => `
          <div
            class="section-label"
            data-section="${{section.id}}"
            style="left: ${{section.x}}px; top: ${{section.y}}px; --section-color: ${{section.color}}"
          >
            ${{escapeHtml(section.label)}}
          </div>`)
        .join("");
      renderColorKey(currentSectionRegions);
    }}

    function sectionDisplayRegions(sections) {{
      return sections.map((section) => {{
        const positions = section.tables.map((tableName) => currentPositions.get(tableName)).filter(Boolean);
        if (!positions.length) return section;
        const minX = Math.min(...positions.map((position) => position.x));
        const minY = Math.min(...positions.map((position) => position.y));
        const maxX = Math.max(...positions.map((position) => position.x + 300));
        return {{
          ...section,
          x: minX,
          y: Math.max(0, minY - 48),
          width: maxX - minX,
        }};
      }});
    }}

    function renderColorKey(sections) {{
      const visible = sections.filter((section) => section.showTitle);
      colorKeyEl.innerHTML = visible.map((section) => `
        <span class="color-key-item">
          <i class="color-dot" style="--section-color: ${{section.color}}"></i>
          ${{escapeHtml(section.label)}}
        </span>`).join("");
    }}

    function attachCardDragHandlers() {{
      cardsEl.querySelectorAll(".table-card").forEach((card) => {{
        card.addEventListener("pointerdown", (event) => {{
          if (event.target.closest("summary") || event.target.closest(".column-list")) return;
          const tableName = card.dataset.table;
          const position = currentPositions.get(tableName);
          cardDragState = {{
            tableName,
            card,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            originX: position.x,
            originY: position.y,
          }};
          card.classList.add("moving");
          card.setPointerCapture(event.pointerId);
          event.stopPropagation();
        }});
        card.addEventListener("pointermove", (event) => {{
          if (!cardDragState || cardDragState.pointerId !== event.pointerId) return;
          const next = {{
            x: cardDragState.originX + (event.clientX - cardDragState.startX) / scale,
            y: cardDragState.originY + (event.clientY - cardDragState.startY) / scale,
          }};
          currentPositions.set(cardDragState.tableName, next);
          card.style.left = `${{next.x}}px`;
          card.style.top = `${{next.y}}px`;
          drawRelationships(relationshipsFor(activeViewTables()), currentPositions);
          event.stopPropagation();
        }});
        card.addEventListener("pointerup", (event) => {{
          if (!cardDragState || cardDragState.pointerId !== event.pointerId) return;
          cardDragState.card.classList.remove("moving");
          saveCurrentPositions();
          cardDragState = null;
          event.stopPropagation();
        }});
      }});
    }}

    function attachSectionDragHandlers() {{
      sectionsEl.querySelectorAll(".section-label").forEach((label) => {{
        label.addEventListener("pointerdown", (event) => {{
          const section = currentSectionRegions.find((item) => item.id === label.dataset.section);
          if (!section) return;
          sectionDragState = {{
            section,
            label,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            originX: section.x,
            originY: section.y,
            origins: new Map(section.tables.map((tableName) => [tableName, currentPositions.get(tableName)])),
          }};
          label.classList.add("moving");
          label.setPointerCapture(event.pointerId);
          event.stopPropagation();
        }});
        label.addEventListener("pointermove", (event) => {{
          if (!sectionDragState || sectionDragState.pointerId !== event.pointerId) return;
          const deltaX = (event.clientX - sectionDragState.startX) / scale;
          const deltaY = (event.clientY - sectionDragState.startY) / scale;
          sectionDragState.section.x = sectionDragState.originX + deltaX;
          sectionDragState.section.y = sectionDragState.originY + deltaY;
          sectionDragState.label.style.left = `${{sectionDragState.section.x}}px`;
          sectionDragState.label.style.top = `${{sectionDragState.section.y}}px`;
          for (const [tableName, origin] of sectionDragState.origins.entries()) {{
            if (!origin) continue;
            const next = {{ x: origin.x + deltaX, y: origin.y + deltaY }};
            currentPositions.set(tableName, next);
            const card = document.getElementById(`table-${{tableName}}`);
            if (card) {{
              card.style.left = `${{next.x}}px`;
              card.style.top = `${{next.y}}px`;
            }}
          }}
          drawRelationships(relationshipsFor(activeViewTables()), currentPositions);
          event.stopPropagation();
        }});
        label.addEventListener("pointerup", (event) => {{
          if (!sectionDragState || sectionDragState.pointerId !== event.pointerId) return;
          sectionDragState.label.classList.remove("moving");
          saveCurrentPositions();
          sectionDragState = null;
          event.stopPropagation();
        }});
      }});
    }}

    function drawRelationships(relationships, positions) {{
      linesEl.innerHTML = "";
      const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
      const markerMap = new Map();
      for (const relationship of relationships) {{
        markerMap.set(relationship.sectionId, relationship.sectionColor);
      }}
      defs.innerHTML = Array.from(markerMap.entries()).map(([sectionId, color]) => `
        <marker
          id="fk-arrow-${{sectionId}}"
          markerWidth="16"
          markerHeight="12"
          refX="14"
          refY="6"
          orient="auto"
        >
          <path d="M 0 0 L 16 6 L 0 12 z" fill="${{color}}"></path>
        </marker>`).join("");
      linesEl.appendChild(defs);
      for (const relationship of relationships) {{
        const from = positions.get(relationship.from);
        const to = positions.get(relationship.to);
        if (!from || !to) continue;
        const source = edgePoint(cardBounds(relationship.from, from), cardBounds(relationship.to, to), 4);
        const target = edgePoint(cardBounds(relationship.to, to), cardBounds(relationship.from, from), 22);
        const fromX = source.x;
        const fromY = source.y;
        const toX = target.x;
        const toY = target.y;
        const midX = (fromX + toX) / 2;
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", `M ${{fromX}} ${{fromY}} C ${{midX}} ${{fromY}}, ${{midX}} ${{toY}}, ${{toX}} ${{toY}}`);
        const actionClass = showDeleteActions ? relationship.onDelete.replace(" ", "_") : "";
        path.setAttribute("class", `rel-line ${{actionClass}}`);
        path.setAttribute("style", `stroke: ${{relationship.sectionColor}}`);
        path.setAttribute("marker-end", `url(#fk-arrow-${{relationship.sectionId}})`);
        linesEl.appendChild(path);
        if (showLabels) {{
          const labelGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
          const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
          label.setAttribute("x", String(midX));
          label.setAttribute("y", String((fromY + toY) / 2 - 6));
          label.setAttribute("text-anchor", "middle");
          label.setAttribute("class", "rel-label");
          label.textContent = showDeleteActions
            ? `${{relationship.column}} -> ${{relationship.referencesColumn}} / ${{relationship.onDelete}}`
            : `${{relationship.column}} -> ${{relationship.referencesColumn}}`;
          labelGroup.appendChild(label);
          linesEl.appendChild(labelGroup);
          const box = label.getBBox();
          const background = document.createElementNS("http://www.w3.org/2000/svg", "rect");
          background.setAttribute("x", String(box.x - 6));
          background.setAttribute("y", String(box.y - 3));
          background.setAttribute("width", String(box.width + 12));
          background.setAttribute("height", String(box.height + 6));
          background.setAttribute("rx", "5");
          background.setAttribute("class", "rel-label-bg");
          labelGroup.insertBefore(background, label);
        }}
      }}
    }}

    function cardBounds(tableName, position) {{
      const card = document.getElementById(`table-${{tableName}}`);
      const width = card ? card.offsetWidth : 300;
      const height = card ? card.offsetHeight : 420;
      return {{
        left: position.x,
        top: position.y,
        width,
        height,
        centerX: position.x + width / 2,
        centerY: position.y + height / 2,
      }};
    }}

    function edgePoint(bounds, otherBounds, outwardPadding) {{
      const dx = otherBounds.centerX - bounds.centerX;
      const dy = otherBounds.centerY - bounds.centerY;
      const halfWidth = bounds.width / 2;
      const halfHeight = bounds.height / 2;
      if (dx === 0 && dy === 0) {{
        return {{ x: bounds.centerX, y: bounds.top - outwardPadding }};
      }}
      const scaleToEdge = Math.min(
        Math.abs(halfWidth / (dx || 0.0001)),
        Math.abs(halfHeight / (dy || 0.0001)),
      );
      const edgeX = bounds.centerX + dx * scaleToEdge;
      const edgeY = bounds.centerY + dy * scaleToEdge;
      const length = Math.hypot(dx, dy);
      return {{
        x: edgeX + (dx / length) * outwardPadding,
        y: edgeY + (dy / length) * outwardPadding,
      }};
    }}

    function applyTransform() {{
      stageEl.style.transform = `translate(${{offsetX}}px, ${{offsetY}}px) scale(${{scale}})`;
    }}

    function setScale(nextScale) {{
      scale = Math.max(0.35, Math.min(1.6, nextScale));
      applyTransform();
    }}

    document.getElementById("zoomOut").addEventListener("click", () => setScale(scale - 0.1));
    document.getElementById("zoomIn").addEventListener("click", () => setScale(scale + 0.1));
    document.getElementById("zoomReset").addEventListener("click", () => {{
      scale = 0.78;
      offsetX = 40;
      offsetY = 72;
      applyTransform();
    }});
    document.getElementById("resetLayout").addEventListener("click", () => {{
      localStorage.removeItem(storageKey());
      render();
    }});
    toggleIndexesEl.addEventListener("click", () => {{
      showIndexes = !showIndexes;
      toggleIndexesEl.setAttribute("aria-pressed", String(showIndexes));
      render();
    }});
    toggleLabelsEl.addEventListener("click", () => {{
      showLabels = !showLabels;
      toggleLabelsEl.setAttribute("aria-pressed", String(showLabels));
      render();
    }});
    toggleConstraintsEl.addEventListener("click", () => {{
      showConstraints = !showConstraints;
      toggleConstraintsEl.setAttribute("aria-pressed", String(showConstraints));
      render();
    }});
    toggleDeleteActionsEl.addEventListener("click", () => {{
      showDeleteActions = !showDeleteActions;
      toggleDeleteActionsEl.setAttribute("aria-pressed", String(showDeleteActions));
      drawRelationships(relationshipsFor(activeViewTables()), currentPositions);
    }});
    searchEl.addEventListener("input", render);
    canvasEl.addEventListener("wheel", (event) => {{
      event.preventDefault();
      setScale(scale + (event.deltaY < 0 ? 0.06 : -0.06));
    }}, {{ passive: false }});
    canvasEl.addEventListener("pointerdown", (event) => {{
      if (event.target.closest(".table-card")) return;
      dragState = {{ x: event.clientX, y: event.clientY, offsetX, offsetY }};
      canvasEl.classList.add("dragging");
      canvasEl.setPointerCapture(event.pointerId);
    }});
    canvasEl.addEventListener("pointermove", (event) => {{
      if (!dragState) return;
      offsetX = dragState.offsetX + event.clientX - dragState.x;
      offsetY = dragState.offsetY + event.clientY - dragState.y;
      applyTransform();
    }});
    canvasEl.addEventListener("pointerup", () => {{
      dragState = null;
      canvasEl.classList.remove("dragging");
    }});

    render();
  </script>
</body>
</html>
"""



