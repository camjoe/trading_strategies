    const payload = JSON.parse(document.getElementById("schema-payload").textContent);
    const tablesByName = new Map(payload.tables.map((table) => [table.name, table]));
    const tabsEl = document.getElementById("tabs");
    const categoryTabsEl = document.getElementById("categoryTabs");
    const categoryViews = payload.categoryViews || [];
    const allViews = [...payload.views, ...categoryViews];
    const cardsEl = document.getElementById("cards");
    const sectionsEl = document.getElementById("sections");
    const colorKeyEl = document.getElementById("colorKey");
    const linesEl = document.getElementById("lines");
    const canvasEl = document.getElementById("canvas");
    const stageEl = document.getElementById("stage");
    const viewTitleEl = document.getElementById("viewTitle");
    const viewDescriptionEl = document.getElementById("viewDescription");
    const toggleIndexesEl = document.getElementById("toggleIndexes");
    const toggleLabelsEl = document.getElementById("toggleLabels");
    const toggleConstraintsEl = document.getElementById("toggleConstraints");
    const toggleDeleteActionsEl = document.getElementById("toggleDeleteActions");
    // Delete-actions mode recolors lines by FK ON DELETE action instead of by
    // section, so the actions read on their own. Colors mirror the CSS legend.
    const DELETE_ACTION_COLORS = new Map([
      ["CASCADE", "#0f8b5f"],
      ["SET NULL", "#1d4ed8"],
      ["NO ACTION", "#667085"],
      ["RESTRICT", "#b54708"],
    ]);
    const DELETE_ACTION_FALLBACK_COLOR = "#db2777";
    // Near-aligned endpoints snap onto the source row so the connector renders
    // as one straight line; exact alignment by hand needs too much precision.
    const STRAIGHT_SNAP_TOLERANCE = 24;
    const ROUTE_TABLE_COLLISION_PENALTY = 10000;
    const ROUTE_OVERLAP_BASE_PENALTY = 6500;
    const ROUTE_OVERLAP_LENGTH_PENALTY = 30;
    const ROUTE_BEND_PENALTY = 220;
    const ROUTE_LENGTH_DIVISOR = 100;
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
    let arrowDragState = null;
    let currentPositions = new Map();
    let currentSectionRegions = [];

    function storageKey() {
      return `database-diagram-layout:${activeView.id}`;
    }

    function arrowStorageKey() {
      return `database-diagram-arrow-targets:${activeView.id}`;
    }

    function arrowSourceStorageKey() {
      return `database-diagram-arrow-sources:${activeView.id}`;
    }

    function loadJson(key) {
      try {
        return JSON.parse(localStorage.getItem(key) || "{}");
      } catch {
        return {};
      }
    }

    function saveJson(key, value) {
      localStorage.setItem(key, JSON.stringify(value));
    }

    function fkColumns(table) {
      return new Set(table.foreignKeys.map((fk) => fk.column));
    }

    function tableMarkup(table) {
      const foreignColumns = fkColumns(table);
      const columns = table.columns.map((column) => {
        const badges = [];
        const columnSectionStyle = column.section ? ` style="--column-section-color: ${column.section.color}"` : "";
        const columnSectionClass = column.section ? " sectioned" : "";
        if (column.primaryKeyPosition) badges.push('<span class="badge pk">PK</span>');
        if (foreignColumns.has(column.name)) badges.push('<span class="badge fk">FK</span>');
        if (showConstraints) {
          if (column.notNull) badges.push('<span class="badge">NOT NULL</span>');
          if (column.default !== null) {
            badges.push(`<span class="badge">DEFAULT ${escapeHtml(String(column.default))}</span>`);
          }
        }
        return `
          <li class="column${columnSectionClass}" data-column="${escapeHtml(column.name)}"${columnSectionStyle}>
            <span class="column-name">${escapeHtml(column.name)}</span>
            <span class="column-type">${escapeHtml(column.type || "ANY")}</span>
            <span class="badges">${badges.join("")}</span>
          </li>`;
      }).join("");
      const indexes = table.indexes.length
        ? table.indexes
            .map((index) => `
              <li>
                ${index.unique ? "UNIQUE " : ""}${escapeHtml(index.name)}
                (${index.columns.map(escapeHtml).join(", ")})
              </li>`)
            .join("")
        : "<li>No indexes</li>";
      return `
        <article class="table-card" id="table-${table.name}" data-table="${table.name}">
          <header><h3>${escapeHtml(table.name)}</h3></header>
          <ul class="column-list">${columns}</ul>
          <details class="indexes" ${showIndexes ? "open" : ""}>
            <summary>Indexes (${table.indexes.length})</summary>
            <ul class="index-list">${indexes}</ul>
          </details>
        </article>`;
    }

    function escapeHtml(value) {
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    }

    function layoutTables(tables) {
      const cardWidth = 410;
      const cardHeight = 760;
      const titleHeight = 54;
      const sectionGap = 150;
      // Keep the leftmost/topmost route corridor inside the visible stage:
      // left-approaching connectors swing up to ~154px left of a card
      // (26 connection offset + 92 lane gap + 36 max lane offset) and get
      // clipped by the canvas if the layout starts at 0.
      const layoutMarginX = 180;
      const layoutMarginY = 80;
      const defaults = new Map();
      const sectionRegions = [];
      let cursorY = layoutMarginY;

      for (const group of groupedTables(tables)) {
        const columns = groupColumnCount(group.tables.length);
        const rows = Math.ceil(group.tables.length / columns);
        const sectionTop = cursorY;
        const tableTop = cursorY + titleHeight;
        group.tables.forEach((table, index) => {
          defaults.set(table.name, {
            x: layoutMarginX + (index % columns) * cardWidth,
            y: tableTop + Math.floor(index / columns) * cardHeight,
          });
        });
        sectionRegions.push({
          id: group.section.id,
          label: group.section.label,
          color: group.section.color,
          tables: group.tables.map((table) => table.name),
          x: layoutMarginX,
          y: sectionTop,
          width: columns * cardWidth - 40,
          height: titleHeight + rows * cardHeight - 80,
          count: group.tables.length,
          showTitle: group.tables.length > 2,
        });
        cursorY += titleHeight + rows * cardHeight + sectionGap;
      }
      const saved = loadSavedPositions();
      for (const [tableName, position] of Object.entries(saved)) {
        if (defaults.has(tableName) && Number.isFinite(position.x) && Number.isFinite(position.y)) {
          defaults.set(tableName, { x: position.x, y: position.y });
        }
      }
      return { positions: defaults, sections: sectionRegions };
    }

    function groupColumnCount(tableCount) {
      return Math.min(4, Math.max(1, Math.ceil(Math.sqrt(tableCount * 1.4))));
    }

    function restackDefaultLayout(viewTables) {
      // The initial layout assumes a fixed card height, but rendered cards vary
      // (accounts has 3x the columns of order_fills). Once cards are in the DOM,
      // re-stack each section row using measured heights so cards never overlap.
      // Skipped when the user has dragged cards: their arrangement wins.
      if (Object.keys(loadSavedPositions()).length) return;
      const titleHeight = 54;
      const sectionGap = 150;
      const rowGap = 90;
      const layoutMarginY = 80;
      let cursorY = layoutMarginY;
      for (const group of groupedTables(viewTables)) {
        const columns = groupColumnCount(group.tables.length);
        let rowTop = cursorY + titleHeight;
        for (let rowStart = 0; rowStart < group.tables.length; rowStart += columns) {
          const rowTables = group.tables.slice(rowStart, rowStart + columns);
          let rowHeight = 0;
          for (const table of rowTables) {
            const card = document.getElementById(`table-${table.name}`);
            const position = currentPositions.get(table.name);
            currentPositions.set(table.name, { x: position.x, y: rowTop });
            card.style.top = `${rowTop}px`;
            rowHeight = Math.max(rowHeight, card.offsetHeight);
          }
          rowTop += rowHeight + rowGap;
        }
        cursorY = rowTop - rowGap + sectionGap;
      }
    }

    function groupedTables(tables) {
      const remaining = new Set(tables.map((table) => table.name));
      const groups = [];
      for (const section of payload.sections) {
        const sectionTables = tables.filter((table) => table.section?.id === section.id);
        if (!sectionTables.length) continue;
        sectionTables.forEach((table) => remaining.delete(table.name));
        groups.push({ section, tables: sectionTables });
      }
      const otherTables = tables.filter((table) => remaining.has(table.name));
      if (otherTables.length) {
        groups.push({
          section: { id: "other", label: "Other", color: "#475467" },
          tables: otherTables,
        });
      }
      return groups;
    }

    function loadSavedPositions() {
      return loadJson(storageKey());
    }

    function saveCurrentPositions() {
      const value = Object.fromEntries(currentPositions.entries());
      saveJson(storageKey(), value);
    }

    function relationshipsFor(viewTables) {
      const tableSet = new Set(viewTables.map((table) => table.name));
      const relationships = [];
      for (const table of viewTables) {
        for (const fk of table.foreignKeys) {
          if (tableSet.has(fk.referencesTable)) {
            relationships.push({
              from: table.name,
              to: fk.referencesTable,
              column: fk.column,
              referencesColumn: fk.referencesColumn,
              fields: [{ column: fk.column, referencesColumn: fk.referencesColumn }],
              onDelete: fk.onDelete,
              sectionId: table.section?.id || "other",
              sectionColor: table.section?.color || "#475467",
            });
          }
        }
      }
      return combineRelationships(relationships);
    }

    function combineRelationships(relationships) {
      const grouped = new Map();
      for (const relationship of relationships) {
        const key = `${relationship.from}->${relationship.to}`;
        const existing = grouped.get(key);
        if (!existing) {
          grouped.set(key, { ...relationship, fields: [...relationship.fields] });
          continue;
        }
        existing.fields.push(...relationship.fields);
        existing.column = existing.fields.map((field) => field.column).join(", ");
        existing.referencesColumn = existing.fields.map((field) => field.referencesColumn).join(", ");
        if (existing.onDelete !== relationship.onDelete) existing.onDelete = "MIXED";
      }
      return Array.from(grouped.values());
    }

    function activeViewTables() {
      return activeView.tables.map((name) => tablesByName.get(name)).filter(Boolean);
    }

    function renderTabs() {
      function renderViewButtons(container, views) {
        container.innerHTML = views.map((view) => `
        <button class="tab" type="button" aria-pressed="${view.id === activeView.id}" data-view="${view.id}">
          ${escapeHtml(view.label)}
        </button>`).join("");
        container.querySelectorAll("button").forEach((button) => {
          button.addEventListener("click", () => {
            activeView = allViews.find((view) => view.id === button.dataset.view);
            render();
          });
        });
      }

      renderViewButtons(tabsEl, payload.views);
      categoryTabsEl.hidden = categoryViews.length === 0;
      renderViewButtons(categoryTabsEl, categoryViews);
    }

    function render() {
      const viewTables = activeViewTables();
      const layout = layoutTables(viewTables);
      currentPositions = layout.positions;
      viewTitleEl.textContent = activeView.label;
      viewDescriptionEl.textContent = activeView.description;
      cardsEl.innerHTML = viewTables.map(tableMarkup).join("");
      for (const table of viewTables) {
        const card = document.getElementById(`table-${table.name}`);
        const pos = currentPositions.get(table.name);
        card.style.left = `${pos.x}px`;
        card.style.top = `${pos.y}px`;
      }
      restackDefaultLayout(viewTables);
      renderSections(layout.sections);
      attachCardDragHandlers();
      attachSectionDragHandlers();
      drawRelationships(relationshipsFor(viewTables), currentPositions);
      renderTabs();
      applyTransform();
    }

    function renderSections(sections) {
      currentSectionRegions = sectionDisplayRegions(sections);
      sectionsEl.innerHTML = currentSectionRegions
        .filter((section) => section.showTitle)
        .map((section) => `
          <div
            class="section-label"
            data-section="${section.id}"
            style="left: ${section.x}px; top: ${section.y}px; --section-color: ${section.color}"
          >
            ${escapeHtml(section.label)}
          </div>`)
        .join("");
      renderColorKey(currentSectionRegions);
    }

    function sectionDisplayRegions(sections) {
      return sections.map((section) => {
        const positions = section.tables.map((tableName) => currentPositions.get(tableName)).filter(Boolean);
        if (!positions.length) return section;
        const minX = Math.min(...positions.map((position) => position.x));
        const minY = Math.min(...positions.map((position) => position.y));
        const maxX = Math.max(...positions.map((position) => position.x + 300));
        return {
          ...section,
          x: minX,
          y: Math.max(0, minY - 48),
          width: maxX - minX,
        };
      });
    }

    function renderColorKey(sections) {
      const visible = sections.filter((section) => section.showTitle);
      colorKeyEl.innerHTML = visible.map((section) => `
        <span class="color-key-item">
          <i class="color-dot" style="--section-color: ${section.color}"></i>
          ${escapeHtml(section.label)}
        </span>`).join("");
    }

    function attachCardDragHandlers() {
      cardsEl.querySelectorAll(".table-card").forEach((card) => {
        card.addEventListener("pointerdown", (event) => {
          if (event.target.closest("summary") || event.target.closest(".column-list")) return;
          const tableName = card.dataset.table;
          const position = currentPositions.get(tableName);
          cardDragState = {
            tableName,
            card,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            originX: position.x,
            originY: position.y,
          };
          card.classList.add("moving");
          card.setPointerCapture(event.pointerId);
          event.stopPropagation();
        });
        card.addEventListener("pointermove", (event) => {
          if (!cardDragState || cardDragState.pointerId !== event.pointerId) return;
          const next = {
            x: cardDragState.originX + (event.clientX - cardDragState.startX) / scale,
            y: cardDragState.originY + (event.clientY - cardDragState.startY) / scale,
          };
          currentPositions.set(cardDragState.tableName, next);
          card.style.left = `${next.x}px`;
          card.style.top = `${next.y}px`;
          drawRelationships(relationshipsFor(activeViewTables()), currentPositions);
          event.stopPropagation();
        });
        card.addEventListener("pointerup", (event) => {
          if (!cardDragState || cardDragState.pointerId !== event.pointerId) return;
          cardDragState.card.classList.remove("moving");
          saveCurrentPositions();
          cardDragState = null;
          event.stopPropagation();
        });
      });
    }

    function attachSectionDragHandlers() {
      sectionsEl.querySelectorAll(".section-label").forEach((label) => {
        label.addEventListener("pointerdown", (event) => {
          const section = currentSectionRegions.find((item) => item.id === label.dataset.section);
          if (!section) return;
          sectionDragState = {
            section,
            label,
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            originX: section.x,
            originY: section.y,
            origins: new Map(section.tables.map((tableName) => [tableName, currentPositions.get(tableName)])),
          };
          label.classList.add("moving");
          label.setPointerCapture(event.pointerId);
          event.stopPropagation();
        });
        label.addEventListener("pointermove", (event) => {
          if (!sectionDragState || sectionDragState.pointerId !== event.pointerId) return;
          const deltaX = (event.clientX - sectionDragState.startX) / scale;
          const deltaY = (event.clientY - sectionDragState.startY) / scale;
          sectionDragState.section.x = sectionDragState.originX + deltaX;
          sectionDragState.section.y = sectionDragState.originY + deltaY;
          sectionDragState.label.style.left = `${sectionDragState.section.x}px`;
          sectionDragState.label.style.top = `${sectionDragState.section.y}px`;
          for (const [tableName, origin] of sectionDragState.origins.entries()) {
            if (!origin) continue;
            const next = { x: origin.x + deltaX, y: origin.y + deltaY };
            currentPositions.set(tableName, next);
            const card = document.getElementById(`table-${tableName}`);
            if (card) {
              card.style.left = `${next.x}px`;
              card.style.top = `${next.y}px`;
            }
          }
          drawRelationships(relationshipsFor(activeViewTables()), currentPositions);
          event.stopPropagation();
        });
        label.addEventListener("pointerup", (event) => {
          if (!sectionDragState || sectionDragState.pointerId !== event.pointerId) return;
          sectionDragState.label.classList.remove("moving");
          saveCurrentPositions();
          sectionDragState = null;
          event.stopPropagation();
        });
      });
    }

    function deleteActionColor(onDelete) {
      return DELETE_ACTION_COLORS.get(onDelete) || DELETE_ACTION_FALLBACK_COLOR;
    }

    function relationshipStroke(relationship) {
      return showDeleteActions ? deleteActionColor(relationship.onDelete) : relationship.sectionColor;
    }

    function relationshipMarkerId(relationship) {
      if (!showDeleteActions) return relationship.sectionId;
      return `action-${relationship.onDelete.replaceAll(" ", "_")}`;
    }

    function drawRelationships(relationships, positions) {
      linesEl.innerHTML = "";
      const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
      const markerMap = new Map();
      for (const relationship of relationships) {
        markerMap.set(relationshipMarkerId(relationship), relationshipStroke(relationship));
      }
      // Reference mode points at the referenced parent (marker-end). Delete-
      // actions mode flips the arrow onto the child end (marker-start with
      // auto-start-reverse) so it points at the table whose rows the parent's
      // deletion removes (CASCADE), clears (SET NULL), or that blocks it.
      const markerOrient = showDeleteActions ? "auto-start-reverse" : "auto";
      defs.innerHTML = Array.from(markerMap.entries()).map(([markerId, color]) => `
        <marker
          id="fk-arrow-${markerId}"
          markerWidth="11"
          markerHeight="8"
          refX="9.5"
          refY="4"
          orient="${markerOrient}"
        >
          <path d="M 0 0 L 11 4 L 0 8 z" fill="${color}"></path>
        </marker>`).join("");
      linesEl.appendChild(defs);
      const tableBounds = activeViewTables().map((table) => {
        const position = positions.get(table.name);
        return position ? { tableName: table.name, ...cardBounds(table.name, position) } : null;
      }).filter(Boolean);
      const drawnSegments = [];
      const bridgedCrossings = new Set();
      const targetSlots = targetSlotAssignments(relationships);
      const arrowTargets = loadArrowTargets();
      const arrowSources = loadArrowSources();
      relationships.forEach((relationship, relationshipIndex) => {
        const from = positions.get(relationship.from);
        const to = positions.get(relationship.to);
        if (!from || !to) return;
        const fromBounds = { tableName: relationship.from, ...sourceAnchorBounds(relationship, from, arrowSources) };
        const toSlot = targetSlots.get(relationshipKey(relationship));
        const toBounds = {
          tableName: relationship.to,
          ...targetAnchorBounds(relationship, to, toSlot.index, toSlot.total, arrowTargets),
        };
        const route = routeRelationship(fromBounds, toBounds, tableBounds, relationshipIndex, drawnSegments);
        const labelPoint = routeLabelPoint(route.points);
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", routedPathData(route.points, drawnSegments, bridgedCrossings));
        const actionClass = showDeleteActions ? relationship.onDelete.replaceAll(" ", "_") : "";
        path.setAttribute("class", `rel-line ${actionClass}`);
        path.setAttribute("style", `stroke: ${relationshipStroke(relationship)}`);
        const markerSide = showDeleteActions ? "marker-start" : "marker-end";
        path.setAttribute(markerSide, `url(#fk-arrow-${relationshipMarkerId(relationship)})`);
        linesEl.appendChild(path);
        attachArrowDragHandle(relationship, route.points[route.points.length - 1], relationshipStroke(relationship), "target");
        attachArrowDragHandle(relationship, route.points[0], relationshipStroke(relationship), "source");
        drawnSegments.push(...route.segments);
        if (showLabels) {
          const labelGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
          const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
          label.setAttribute("x", String(labelPoint.x));
          label.setAttribute("y", String(labelPoint.y - 6));
          label.setAttribute("text-anchor", "middle");
          label.setAttribute("class", "rel-label");
          const fieldLabel = relationship.fields
            .map((field) => `${field.column} -> ${field.referencesColumn}`)
            .join(", ");
          label.textContent = showDeleteActions
            ? `${fieldLabel} / ${relationship.onDelete}`
            : fieldLabel;
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
        }
      });
    }

    function loadArrowTargets() {
      return loadJson(arrowStorageKey());
    }

    function saveArrowTarget(relationship, y) {
      const targets = loadArrowTargets();
      targets[relationshipKey(relationship)] = y;
      saveJson(arrowStorageKey(), targets);
    }

    function loadArrowSources() {
      return loadJson(arrowSourceStorageKey());
    }

    function saveArrowSource(relationship, y) {
      const sources = loadArrowSources();
      sources[relationshipKey(relationship)] = y;
      saveJson(arrowSourceStorageKey(), sources);
    }

    function attachArrowDragHandle(relationship, endpointPoint, color, end) {
      const handle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      handle.setAttribute("cx", String(endpointPoint.x));
      handle.setAttribute("cy", String(endpointPoint.y));
      handle.setAttribute("r", "14");
      handle.setAttribute("fill", color);
      handle.setAttribute("opacity", "0");
      handle.setAttribute("style", "cursor: ns-resize; pointer-events: all;");
      handle.addEventListener("pointerdown", (event) => {
        arrowDragState = {
          relationship,
          end,
          pointerId: event.pointerId,
          startY: event.clientY,
          originY: endpointPoint.y,
        };
        event.stopPropagation();
      });
      linesEl.appendChild(handle);
    }

    function handleArrowPointerMove(event) {
      if (!arrowDragState || arrowDragState.pointerId !== event.pointerId) return;
      const nextY = arrowDragState.originY + (event.clientY - arrowDragState.startY) / scale;
      if (arrowDragState.end === "source") {
        saveArrowSource(arrowDragState.relationship, nextY);
      } else {
        saveArrowTarget(arrowDragState.relationship, nextY);
      }
      drawRelationships(relationshipsFor(activeViewTables()), currentPositions);
      event.preventDefault();
    }

    function handleArrowPointerUp(event) {
      if (!arrowDragState || arrowDragState.pointerId !== event.pointerId) return;
      arrowDragState = null;
      event.preventDefault();
    }

    function relationshipKey(relationship) {
      return `${relationship.from}.${relationship.column}->${relationship.to}.${relationship.referencesColumn}`;
    }

    function targetSlotAssignments(relationships) {
      const grouped = new Map();
      for (const relationship of relationships) {
        const entries = grouped.get(relationship.to) || [];
        entries.push(relationship);
        grouped.set(relationship.to, entries);
      }
      const assignments = new Map();
      for (const entries of grouped.values()) {
        entries.forEach((relationship, index) => {
          assignments.set(relationshipKey(relationship), { index, total: entries.length });
        });
      }
      return assignments;
    }

    function snapAlignedTarget(fromBounds, toBounds) {
      // The source anchor is the FK column row (fixed); the target anchor is a
      // slot or drag position (arbitrary), so it is the side that moves.
      const deltaY = toBounds.centerY - fromBounds.centerY;
      if (deltaY === 0 || Math.abs(deltaY) > STRAIGHT_SNAP_TOLERANCE) return toBounds;
      return { ...toBounds, top: fromBounds.centerY - 1, centerY: fromBounds.centerY };
    }

    function routeRelationship(fromBounds, rawToBounds, allBounds, relationshipIndex, previousSegments) {
      const toBounds = snapAlignedTarget(fromBounds, rawToBounds);
      const laneOffset = relationshipLaneOffset(relationshipIndex);
      const fromSides = connectorSides(fromBounds, toBounds);
      const toSides = connectorSides(toBounds, fromBounds);
      const obstacles = allBounds.map((bounds) => expandBounds(bounds, 22));
      const candidates = [];
      for (const fromSide of fromSides) {
        for (const toSide of toSides) {
          const sourcePort = connectionPoint(fromBounds, fromSide, laneOffset);
          const targetPort = connectionPoint(toBounds, toSide, laneOffset);
          const sourceExit = sideOffsetPoint(sourcePort, fromSide, 34);
          const targetApproach = sideOffsetPoint(targetPort, toSide, 34);
          candidates.push(
            ...routeCandidates(
              sourceExit,
              targetApproach,
              laneOffset,
            ).concat(obstacleAvoidanceCandidates(sourceExit, targetApproach, obstacles, laneOffset))
              .map((middle) => [sourcePort, ...middle, targetPort])
              .filter((points) => routeRespectsEndpointDirection(points, fromSide, toSide)),
          );
        }
      }
      const scored = candidates
        .map((points) => simplifyRoute(points, 2))
        .map((points) => ({ points, segments: routeSegments(points) }))
        .map((route) => ({
          ...route,
          tableCrossings: routeTableCrossingCount(route.segments, obstacles, fromBounds.tableName, toBounds.tableName),
          overlappingSegments: routeOverlapCount(route.segments, previousSegments),
          score: scoreRoute(route, obstacles, fromBounds.tableName, toBounds.tableName, previousSegments),
        }))
        .sort(
          (left, right) =>
            left.tableCrossings - right.tableCrossings
            || left.overlappingSegments - right.overlappingSegments
            || left.score - right.score,
        );
      return scored[0];
    }

    function relationshipLaneOffset(index) {
      const offsets = [0, -12, 12, -24, 24, -36, 36];
      return offsets[index % offsets.length];
    }

    function connectorSides(bounds, otherBounds) {
      const dx = otherBounds.centerX - bounds.centerX;
      const primary = dx >= 0 ? "right" : "left";
      return [primary, primary === "right" ? "left" : "right"];
    }

    function connectionPoint(bounds, side, laneOffset) {
      const offset = 26;
      const y = bounds.centerY + laneOffset;
      if (side === "left") return { x: bounds.left - offset, y };
      return { x: bounds.left + bounds.width + offset, y };
    }

    function sideOffsetPoint(point, side, distance) {
      if (side === "left") return { x: point.x - distance, y: point.y };
      return { x: point.x + distance, y: point.y };
    }

    function routeRespectsEndpointDirection(points, fromSide, toSide) {
      return !sourceTurnsBack(points, fromSide) && !targetTurnsBack(points, toSide);
    }

    function sourceTurnsBack(points, fromSide) {
      const sourceExit = points[1];
      const next = nextDifferentPoint(points, 1, 1);
      if (!next || next.y !== sourceExit.y) return false;
      if (fromSide === "left") return next.x > sourceExit.x;
      return next.x < sourceExit.x;
    }

    function targetTurnsBack(points, toSide) {
      const targetApproach = points[points.length - 2];
      const previous = nextDifferentPoint(points, points.length - 2, -1);
      if (!previous || previous.y !== targetApproach.y) return false;
      if (toSide === "left") return previous.x > targetApproach.x;
      return previous.x < targetApproach.x;
    }

    function nextDifferentPoint(points, startIndex, direction) {
      const start = points[startIndex];
      for (let index = startIndex + direction; index >= 0 && index < points.length; index += direction) {
        const point = points[index];
        if (point.x !== start.x || point.y !== start.y) return point;
      }
      return null;
    }

    function routeCandidates(start, end, laneOffset) {
      const midX = (start.x + end.x) / 2 + laneOffset;
      const midY = (start.y + end.y) / 2 + laneOffset;
      const gap = 92 + Math.abs(laneOffset);
      const leftLane = Math.min(start.x, end.x) - gap;
      const rightLane = Math.max(start.x, end.x) + gap;
      const topLane = Math.min(start.y, end.y) - gap;
      const bottomLane = Math.max(start.y, end.y) + gap;
      const candidates = [];
      if (start.x === end.x || start.y === end.y) {
        candidates.push([start, end]);
      }
      candidates.push(
        [start, { x: midX, y: start.y }, { x: midX, y: end.y }, end],
        [start, { x: start.x, y: midY }, { x: end.x, y: midY }, end],
        [start, { x: leftLane, y: start.y }, { x: leftLane, y: end.y }, end],
        [start, { x: rightLane, y: start.y }, { x: rightLane, y: end.y }, end],
        [start, { x: start.x, y: topLane }, { x: end.x, y: topLane }, end],
        [start, { x: start.x, y: bottomLane }, { x: end.x, y: bottomLane }, end],
      );
      return candidates;
    }

    function obstacleAvoidanceCandidates(start, end, obstacles, laneOffset) {
      const candidates = [];
      const minX = Math.min(start.x, end.x);
      const maxX = Math.max(start.x, end.x);
      const minY = Math.min(start.y, end.y);
      const maxY = Math.max(start.y, end.y);
      for (const obstacle of obstacles) {
        const overlapsHorizontalSpan = maxX >= obstacle.left && minX <= obstacle.left + obstacle.width;
        const overlapsVerticalSpan = maxY >= obstacle.top && minY <= obstacle.top + obstacle.height;
        const laneGap = 34 + Math.abs(laneOffset);
        if (overlapsHorizontalSpan) {
          const above = obstacle.top - laneGap;
          const below = obstacle.top + obstacle.height + laneGap;
          candidates.push(
            [start, { x: start.x, y: above }, { x: end.x, y: above }, end],
            [start, { x: start.x, y: below }, { x: end.x, y: below }, end],
          );
        }
        if (overlapsVerticalSpan) {
          const left = obstacle.left - laneGap;
          const right = obstacle.left + obstacle.width + laneGap;
          candidates.push(
            [start, { x: left, y: start.y }, { x: left, y: end.y }, end],
            [start, { x: right, y: start.y }, { x: right, y: end.y }, end],
          );
        }
      }
      return candidates;
    }

    function simplifyRoute(points, protectedEndpointCount = 0) {
      const simplified = [];
      for (const point of points) {
        const previous = simplified[simplified.length - 1];
        if (!previous || previous.x !== point.x || previous.y !== point.y) simplified.push(point);
      }
      return simplified.filter((point, index, all) => {
        if (index === 0 || index === all.length - 1) return true;
        if (index < protectedEndpointCount || index >= all.length - protectedEndpointCount) return true;
        const previous = all[index - 1];
        const next = all[index + 1];
        return !((previous.x === point.x && point.x === next.x) || (previous.y === point.y && point.y === next.y));
      });
    }

    function routeSegments(points) {
      const segments = [];
      for (let index = 0; index < points.length - 1; index += 1) {
        const start = points[index];
        const end = points[index + 1];
        segments.push({
          id: `${start.x},${start.y}|${end.x},${end.y}`,
          x1: start.x,
          y1: start.y,
          x2: end.x,
          y2: end.y,
          horizontal: start.y === end.y,
          vertical: start.x === end.x,
        });
      }
      return segments;
    }

    function scoreRoute(route, obstacles, sourceTableName, targetTableName, previousSegments) {
      return (
        routeScore(route.segments, obstacles, sourceTableName, targetTableName)
        + routeOverlapScore(route.segments, previousSegments)
        + routeBendCount(route.points) * ROUTE_BEND_PENALTY
        + routeLength(route.segments) / ROUTE_LENGTH_DIVISOR
      );
    }

    function routeScore(segments, obstacles, sourceTableName, targetTableName) {
      return routeTableCrossingCount(segments, obstacles, sourceTableName, targetTableName) * ROUTE_TABLE_COLLISION_PENALTY;
    }

    function routeTableCrossingCount(segments, obstacles, sourceTableName, targetTableName) {
      let score = 0;
      for (let index = 0; index < segments.length; index += 1) {
        const segment = segments[index];
        for (const obstacle of obstacles) {
          const isSourceExit = index === 0 && obstacle.tableName === sourceTableName;
          const isTargetApproach = index === segments.length - 1 && obstacle.tableName === targetTableName;
          if (isSourceExit || isTargetApproach) continue;
          if (segmentIntersectsRect(segment, obstacle)) score += 1;
        }
      }
      return score;
    }

    function routeOverlapScore(segments, previousSegments) {
      let score = 0;
      for (const segment of segments) {
        for (const previous of previousSegments) {
          const overlap = segmentOverlapLength(segment, previous);
          if (overlap > 0) score += ROUTE_OVERLAP_BASE_PENALTY + overlap * ROUTE_OVERLAP_LENGTH_PENALTY;
        }
      }
      return score;
    }

    function routeOverlapCount(segments, previousSegments) {
      let count = 0;
      for (const segment of segments) {
        for (const previous of previousSegments) {
          if (segmentOverlapLength(segment, previous) > 0) count += 1;
        }
      }
      return count;
    }

    function segmentOverlapLength(segment, previous) {
      if (segment.horizontal && previous.horizontal && segment.y1 === previous.y1) {
        return rangeOverlapLength(segment.x1, segment.x2, previous.x1, previous.x2);
      }
      if (segment.vertical && previous.vertical && segment.x1 === previous.x1) {
        return rangeOverlapLength(segment.y1, segment.y2, previous.y1, previous.y2);
      }
      return 0;
    }

    function rangeOverlapLength(startA, endA, startB, endB) {
      const minA = Math.min(startA, endA);
      const maxA = Math.max(startA, endA);
      const minB = Math.min(startB, endB);
      const maxB = Math.max(startB, endB);
      return Math.max(0, Math.min(maxA, maxB) - Math.max(minA, minB));
    }

    function routeBendCount(points) {
      let bends = 0;
      for (let index = 1; index < points.length - 1; index += 1) {
        const previous = points[index - 1];
        const current = points[index];
        const next = points[index + 1];
        const previousHorizontal = previous.y === current.y;
        const nextHorizontal = current.y === next.y;
        if (previousHorizontal !== nextHorizontal) bends += 1;
      }
      return bends;
    }

    function routeLength(segments) {
      return segments.reduce(
        (total, segment) => total + Math.abs(segment.x2 - segment.x1) + Math.abs(segment.y2 - segment.y1),
        0,
      );
    }

    function segmentIntersectsRect(segment, rect) {
      if (segment.horizontal) {
        const minX = Math.min(segment.x1, segment.x2);
        const maxX = Math.max(segment.x1, segment.x2);
        return segment.y1 >= rect.top && segment.y1 <= rect.top + rect.height && maxX >= rect.left && minX <= rect.left + rect.width;
      }
      const minY = Math.min(segment.y1, segment.y2);
      const maxY = Math.max(segment.y1, segment.y2);
      return segment.x1 >= rect.left && segment.x1 <= rect.left + rect.width && maxY >= rect.top && minY <= rect.top + rect.height;
    }

    function expandBounds(bounds, amount) {
      return {
        tableName: bounds.tableName,
        left: bounds.left - amount,
        top: bounds.top - amount,
        width: bounds.width + amount * 2,
        height: bounds.height + amount * 2,
      };
    }

    function routedPathData(points, previousSegments, bridgedCrossings) {
      const parts = [`M ${points[0].x} ${points[0].y}`];
      const segments = routeSegments(points);
      for (const segment of segments) {
        const crossings = previousSegments
          .map((previous) => segmentCrossing(segment, previous))
          .filter(Boolean)
          .filter((crossing) => reserveBridge(crossing, bridgedCrossings))
          .sort((left, right) => distanceAlong(segment, left) - distanceAlong(segment, right));
        appendSegmentWithBridges(parts, segment, crossings);
      }
      return parts.join(" ");
    }

    function appendSegmentWithBridges(parts, segment, crossings) {
      const radius = 8;
      let cursor = { x: segment.x1, y: segment.y1 };
      const dirX = Math.sign(segment.x2 - segment.x1);
      const dirY = Math.sign(segment.y2 - segment.y1);
      for (const crossing of crossings) {
        if (segment.horizontal) {
          const before = { x: crossing.x - radius * dirX, y: segment.y1 };
          const after = { x: crossing.x + radius * dirX, y: segment.y1 };
          if (pointBetween(cursor, before, segment)) {
            parts.push(`L ${before.x} ${before.y}`);
            parts.push(`Q ${crossing.x} ${crossing.y - 10} ${after.x} ${after.y}`);
            cursor = after;
          }
        } else {
          const before = { x: segment.x1, y: crossing.y - radius * dirY };
          const after = { x: segment.x1, y: crossing.y + radius * dirY };
          if (pointBetween(cursor, before, segment)) {
            parts.push(`L ${before.x} ${before.y}`);
            parts.push(`Q ${crossing.x + 10} ${crossing.y} ${after.x} ${after.y}`);
            cursor = after;
          }
        }
      }
      parts.push(`L ${segment.x2} ${segment.y2}`);
    }

    function pointBetween(start, point, segment) {
      if (segment.horizontal) {
        return point.x >= Math.min(start.x, segment.x2) && point.x <= Math.max(start.x, segment.x2);
      }
      return point.y >= Math.min(start.y, segment.y2) && point.y <= Math.max(start.y, segment.y2);
    }

    function segmentCrossing(segment, previous) {
      if (segment.horizontal === previous.horizontal) return null;
      const horizontal = segment.horizontal ? segment : previous;
      const vertical = segment.vertical ? segment : previous;
      const minX = Math.min(horizontal.x1, horizontal.x2) + 14;
      const maxX = Math.max(horizontal.x1, horizontal.x2) - 14;
      const minY = Math.min(vertical.y1, vertical.y2) + 14;
      const maxY = Math.max(vertical.y1, vertical.y2) - 14;
      if (vertical.x1 > minX && vertical.x1 < maxX && horizontal.y1 > minY && horizontal.y1 < maxY) {
        return {
          x: vertical.x1,
          y: horizontal.y1,
          key: crossingKey(vertical.x1, horizontal.y1, segment, previous),
        };
      }
      return null;
    }

    function crossingKey(x, y, segment, previous) {
      return [
        Math.round(x),
        Math.round(y),
        normalizeSegmentId(segment),
        normalizeSegmentId(previous),
      ].sort().join("::");
    }

    function normalizeSegmentId(segment) {
      const first = `${Math.round(segment.x1)},${Math.round(segment.y1)}`;
      const second = `${Math.round(segment.x2)},${Math.round(segment.y2)}`;
      return first < second ? `${first}|${second}` : `${second}|${first}`;
    }

    function reserveBridge(crossing, bridgedCrossings) {
      if (bridgedCrossings.has(crossing.key)) return false;
      bridgedCrossings.add(crossing.key);
      return true;
    }

    function distanceAlong(segment, point) {
      return segment.horizontal ? Math.abs(point.x - segment.x1) : Math.abs(point.y - segment.y1);
    }

    function routeLabelPoint(points) {
      const segments = routeSegments(points);
      const total = Math.max(1, routeLength(segments));
      let distance = 0;
      for (const segment of segments) {
        const length = Math.abs(segment.x2 - segment.x1) + Math.abs(segment.y2 - segment.y1);
        if (distance + length >= total / 2) {
          const remaining = total / 2 - distance;
          const ratio = length === 0 ? 0 : remaining / length;
          return {
            x: segment.x1 + (segment.x2 - segment.x1) * ratio,
            y: segment.y1 + (segment.y2 - segment.y1) * ratio,
          };
        }
        distance += length;
      }
      return points[Math.floor(points.length / 2)];
    }

    function columnBounds(tableName, columnName, position) {
      const card = document.getElementById(`table-${tableName}`);
      const cardBox = cardBounds(tableName, position);
      const column = card
        ? Array.from(card.querySelectorAll(".column")).find((item) => item.dataset.column === columnName)
        : null;
      if (!column) return cardBox;
      const top = position.y + column.offsetTop;
      const height = column.offsetHeight;
      return {
        left: cardBox.left,
        top,
        width: cardBox.width,
        height,
        centerX: cardBox.centerX,
        centerY: top + height / 2,
      };
    }

    function sourceAnchorBounds(relationship, position, arrowSources) {
      // Default anchor is the FK column row; a dragged source overrides it,
      // clamped inside the card like the target-side drag.
      const savedY = arrowSources[relationshipKey(relationship)];
      if (!Number.isFinite(savedY)) return relationshipSourceBounds(relationship, position);
      const cardBox = cardBounds(relationship.from, position);
      const margin = 28;
      const y = Math.max(cardBox.top + margin, Math.min(cardBox.top + cardBox.height - margin, savedY));
      return {
        left: cardBox.left,
        top: y - 1,
        width: cardBox.width,
        height: 2,
        centerX: cardBox.centerX,
        centerY: y,
      };
    }

    function relationshipSourceBounds(relationship, position) {
      if (!relationship.fields || relationship.fields.length <= 1) {
        return columnBounds(relationship.from, relationship.column, position);
      }
      const boxes = relationship.fields.map((field) => columnBounds(relationship.from, field.column, position));
      const first = boxes[0];
      const centerY = boxes.reduce((total, box) => total + box.centerY, 0) / boxes.length;
      return {
        left: first.left,
        top: centerY - 1,
        width: first.width,
        height: 2,
        centerX: first.centerX,
        centerY,
      };
    }

    function targetAnchorBounds(relationship, position, slotIndex, totalSlots, arrowTargets) {
      const tableName = relationship.to;
      const cardBox = cardBounds(tableName, position);
      const margin = 28;
      const usableHeight = Math.max(1, cardBox.height - margin * 2);
      const slotCount = Math.max(1, totalSlots);
      const savedY = arrowTargets[relationshipKey(relationship)];
      const defaultY = cardBox.top + margin + usableHeight * ((slotIndex + 1) / (slotCount + 1));
      const y = Number.isFinite(savedY)
        ? Math.max(cardBox.top + margin, Math.min(cardBox.top + cardBox.height - margin, savedY))
        : defaultY;
      return {
        left: cardBox.left,
        top: y - 1,
        width: cardBox.width,
        height: 2,
        centerX: cardBox.centerX,
        centerY: y,
      };
    }

    function cardBounds(tableName, position) {
      const card = document.getElementById(`table-${tableName}`);
      const width = card ? card.offsetWidth : 300;
      const height = card ? card.offsetHeight : 420;
      return {
        left: position.x,
        top: position.y,
        width,
        height,
        centerX: position.x + width / 2,
        centerY: position.y + height / 2,
      };
    }

    function applyTransform() {
      stageEl.style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;
    }

    function setScale(nextScale) {
      scale = Math.max(0.35, Math.min(1.6, nextScale));
      applyTransform();
    }

    document.getElementById("zoomOut").addEventListener("click", () => setScale(scale - 0.1));
    document.getElementById("zoomIn").addEventListener("click", () => setScale(scale + 0.1));
    toggleIndexesEl.addEventListener("click", () => {
      showIndexes = !showIndexes;
      toggleIndexesEl.setAttribute("aria-pressed", String(showIndexes));
      render();
    });
    toggleLabelsEl.addEventListener("click", () => {
      showLabels = !showLabels;
      toggleLabelsEl.setAttribute("aria-pressed", String(showLabels));
      render();
    });
    toggleConstraintsEl.addEventListener("click", () => {
      showConstraints = !showConstraints;
      toggleConstraintsEl.setAttribute("aria-pressed", String(showConstraints));
      render();
    });
    toggleDeleteActionsEl.addEventListener("click", () => {
      showDeleteActions = !showDeleteActions;
      toggleDeleteActionsEl.setAttribute("aria-pressed", String(showDeleteActions));
      drawRelationships(relationshipsFor(activeViewTables()), currentPositions);
    });
    canvasEl.addEventListener("wheel", (event) => {
      event.preventDefault();
      setScale(scale + (event.deltaY < 0 ? 0.06 : -0.06));
    }, { passive: false });
    canvasEl.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".table-card")) return;
      dragState = { x: event.clientX, y: event.clientY, offsetX, offsetY };
      canvasEl.classList.add("dragging");
      canvasEl.setPointerCapture(event.pointerId);
    });
    canvasEl.addEventListener("pointermove", (event) => {
      if (!dragState) return;
      offsetX = dragState.offsetX + event.clientX - dragState.x;
      offsetY = dragState.offsetY + event.clientY - dragState.y;
      applyTransform();
    });
    canvasEl.addEventListener("pointerup", () => {
      dragState = null;
      canvasEl.classList.remove("dragging");
    });
    window.addEventListener("pointermove", handleArrowPointerMove);
    window.addEventListener("pointerup", handleArrowPointerUp);

    render();
