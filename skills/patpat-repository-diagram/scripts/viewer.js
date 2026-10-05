(() => {
  "use strict";

  const ui = JSON.parse(document.querySelector('meta[name="patpat-viewer-labels"]').content);
  const svg = document.querySelector("figure svg");
  const figure = document.querySelector("figure");
  const status = document.getElementById("viewer-status");
  const nodes = [...svg.querySelectorAll("[data-node-id]")];
  const edges = [...svg.querySelectorAll("[data-edge-id]")];
  const unique = (items, key) => items.length === new Set(items.map((item) => item.dataset[key])).size;
  const validModel = unique(nodes, "nodeId") && unique(edges, "edgeId") && edges.every((edge) => nodes.some((node) => node.dataset.nodeId === edge.dataset.source) && nodes.some((node) => node.dataset.nodeId === edge.dataset.target));
  const byNode = new Map(nodes.map((node) => [node.dataset.nodeId, node]));
  const byEdge = new Map(edges.map((edge) => [edge.dataset.edgeId, edge]));
  const nodeData = nodes.map((node) => ({
    id: node.dataset.nodeId,
    label: node.dataset.label || node.dataset.nodeId,
    kind: node.dataset.kind || "component",
    certainty: node.dataset.certainty || "unknown",
    evidence: (node.dataset.evidence || "").split(",").filter(Boolean),
    reason: node.dataset.reason || "",
  }));
  const edgeData = edges.map((edge) => ({
    id: edge.dataset.edgeId,
    source: edge.dataset.source,
    target: edge.dataset.target,
    label: edge.dataset.label || edge.dataset.edgeId,
    kind: edge.dataset.kind || "relationship",
    certainty: edge.dataset.certainty || "unknown",
    evidence: (edge.dataset.evidence || "").split(",").filter(Boolean),
    reason: edge.dataset.reason || "",
    order: edge.dataset.order || "",
    feedback: edge.dataset.feedback === "true",
  }));
  let storyViews = [];
  const storyMeta = document.querySelector('meta[name="patpat-viewer-views"]');
  if (storyMeta) {
    try {
      const parsed = JSON.parse(storyMeta.content);
      const elementIds = new Set([...nodeData, ...edgeData].map((item) => item.id));
      const viewIds = new Set();
      if (Array.isArray(parsed) && parsed.length <= 12) {
        storyViews = parsed.filter((view) => {
          if (!view || typeof view.id !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,31}$/.test(view.id)
            || viewIds.has(view.id) || typeof view.label !== "string" || !Array.isArray(view.focus)
            || view.focus.length < 1 || view.focus.length > 40
            || view.focus.some((id) => typeof id !== "string" || !elementIds.has(id))
            || new Set(view.focus).size !== view.focus.length
            || (view.note !== null && view.note !== undefined && typeof view.note !== "string")) return false;
          viewIds.add(view.id);
          return true;
        });
      }
    } catch { storyViews = []; }
  }
  const controls = (id) => document.getElementById(id);
  const params = {
    search: controls("diagram-search"), searchResults: controls("diagram-search-results"), focus: controls("focus-node"), routeFrom: controls("route-from"), routeTo: controls("route-to"),
    lens: controls("semantic-lens"), certainty: controls("evidence-lens"), context: controls("relationship-context"),
    roleA: controls("role-kind-a"), roleB: controls("role-kind-b"), roleStatus: controls("role-comparison-status"),
    storyView: controls("story-view"), storyStatus: controls("story-status"),
    preview: controls("preview-status"), passport: controls("semantic-passport"), passportBody: controls("passport-body"),
    passportStatus: controls("passport-status"), routeDetails: controls("route-details"), routeTitle: controls("route-title"),
    routeList: controls("route-step-list"), routeJourney: controls("route-journey"), routeStepStatus: controls("route-step-status"),
    overview: controls("diagram-overview"),
  };
  let selectedNode = "";
  let selectedEdge = "";
  let searchMatches = [];
  let activeSearchIndex = -1;
  let searchOpen = false;
  let focusNodes = null;
  let focusEdges = null;
  let roleComparison = null;
  let currentStory = null;
  let activeReach = null;
  let currentRoute = null;
  let routeStep = -1;
  let traceTimer = 0;
  let zoom = 1;
  let overviewSvg = null;
  let overviewViewport = null;
  let overviewTransform = null;
  let overviewPointer = null;
  let suppressOverviewClick = false;
  const evidenceRows = new Map();
  const visualPresets = ["balanced", "signal", "mono"];
  const presetSvgStyles = {
    signal: {
      light: ".node-service,.participant{fill:#e5f3f5;stroke:#087f8c}.node-data{fill:#e8f5ed;stroke:#287a55}.node-external{fill:#edf0f4;stroke:#596779}.node-decision{fill:#fff2d8;stroke:#9a6510}.edge-data,.terminal-dot{stroke:#087f8c;fill:#087f8c}.header-kicker{fill:#087f8c}",
      dark: ".node-service,.participant{fill:#182b39;stroke:#53c4d5}.node-data{fill:#16342c;stroke:#56d09b}.node-external{fill:#222a35;stroke:#a7b1c0}.node-decision{fill:#382d1a;stroke:#e4b65d}.edge-data,.terminal-dot{stroke:#62d4df;fill:#62d4df}.header-kicker{fill:#62d4df}",
    },
    mono: {
      light: ".node-shape,.participant,.group-box{fill:#eceff3;stroke:#364152}.edge,.legend-line{stroke:#364152}.flow-arrow,.terminal-dot{fill:#364152}.header-kicker{fill:#364152}",
      dark: ".node-shape,.participant,.group-box{fill:#27313c;stroke:#cbd5e1}.edge,.legend-line{stroke:#cbd5e1}.flow-arrow,.terminal-dot{fill:#cbd5e1}.header-kicker{fill:#cbd5e1}",
    },
  };

  function announce(message) {
    if (status) status.textContent = message;
  }

  function option(select, value, label) {
    const entry = document.createElement("option");
    entry.value = value;
    entry.textContent = label;
    select.append(entry);
  }

  function fillSelectors() {
    for (const select of [params.focus, params.routeFrom, params.routeTo]) {
      if (!select) continue;
      option(select, "", "—");
      for (const node of nodeData) option(select, node.id, `${node.id} · ${node.label}`);
    }
    if (params.lens) {
      for (const kind of [...new Set(nodeData.map((item) => item.kind))].sort()) option(params.lens, `component:${kind}`, `${ui.component_kind} · ${kind}`);
      for (const kind of [...new Set(edgeData.map((item) => item.kind))].sort()) option(params.lens, `relationship:${kind}`, `${ui.relationship_kind} · ${kind}`);
    }
    for (const select of [params.roleA, params.roleB]) {
      if (!select) continue;
      option(select, "", "—");
      for (const kind of [...new Set(nodeData.map((item) => item.kind))].sort()) option(select, kind, kind);
    }
    if (params.storyView) {
      for (const view of storyViews) option(params.storyView, view.id, view.label);
    }
    document.querySelectorAll(".evidence-table tbody tr").forEach((row) => {
      const id = row.querySelector("th code")?.textContent?.trim();
      if (id) evidenceRows.set(id, row);
    });
  }

  function searchFields(item, type) {
    return [item.id, item.label, item.kind, item.certainty, ...item.evidence, ...(type === "relationship" ? [item.source, item.target] : [])];
  }

  function renderSearchResults() {
    if (!params.searchResults || !params.search) return;
    params.searchResults.replaceChildren();
    searchMatches.forEach((match, index) => {
      const option = document.createElement("div");
      option.id = `diagram-search-option-${index}`;
      option.className = "search-result";
      option.setAttribute("role", "option");
      option.setAttribute("aria-selected", String(index === activeSearchIndex));
      option.dataset.searchIndex = String(index);
      const type = match.type === "component" ? ui.component : ui.relationship_kind_label;
      const details = match.type === "relationship" ? `${match.item.source} → ${match.item.target}` : match.item.kind;
      option.textContent = `${type} · ${match.item.id} · ${match.item.label} · ${details} · ${ui[match.item.certainty] || ui.unknown}`;
      option.addEventListener("mousedown", (event) => event.preventDefault());
      option.addEventListener("click", () => activateSearchResult(index));
      params.searchResults.append(option);
    });
    const open = searchOpen && searchMatches.length > 0;
    params.searchResults.hidden = !open;
    params.search.setAttribute("aria-expanded", String(open));
    if (open && activeSearchIndex >= 0) params.search.setAttribute("aria-activedescendant", `diagram-search-option-${activeSearchIndex}`);
    else params.search.removeAttribute("aria-activedescendant");
  }

  function updateSearchResults() {
    const query = params.search?.value.trim().toLocaleLowerCase() || "";
    if (!query) {
      searchMatches = [];
      activeSearchIndex = -1;
      searchOpen = false;
      renderSearchResults();
      return;
    }
    const candidates = [
      ...nodeData.map((item) => ({ type: "component", item })),
      ...edgeData.map((item) => ({ type: "relationship", item })),
    ];
    searchMatches = candidates
      .map((match) => {
        const fields = searchFields(match.item, match.type).map((value) => String(value).toLocaleLowerCase());
        const rank = fields.includes(query) ? 0 : fields.some((value) => value.startsWith(query)) ? 1 : 2;
        return { ...match, rank };
      })
      .filter((match) => searchFields(match.item, match.type).some((value) => String(value).toLocaleLowerCase().includes(query)))
      .sort((left, right) => left.rank - right.rank || left.item.id.localeCompare(right.item.id));
    activeSearchIndex = -1;
    searchOpen = searchMatches.length > 0;
    renderSearchResults();
    announce(searchMatches.length ? ui.search_result_count.replace("{count}", String(searchMatches.length)) : ui.search_result_empty);
  }

  function activateSearchResult(index = activeSearchIndex) {
    const match = searchMatches[index];
    if (!match) return announce(ui.search_result_empty);
    if (match.type === "component") focusOne(match.item.id);
    else pinEdge(match.item.id);
    searchOpen = false;
    renderSearchResults();
  }

  function moveSearchActive(delta) {
    if (!searchMatches.length) return;
    activeSearchIndex = activeSearchIndex < 0
      ? (delta > 0 ? 0 : searchMatches.length - 1)
      : (activeSearchIndex + delta + searchMatches.length) % searchMatches.length;
    renderSearchResults();
    params.searchResults.querySelector(`[data-search-index="${activeSearchIndex}"]`)?.scrollIntoView({ block: "nearest" });
  }

  function handleSearchKeydown(event) {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      if (!searchMatches.length) return;
      event.preventDefault();
      searchOpen = true;
      moveSearchActive(event.key === "ArrowDown" ? 1 : -1);
    } else if (event.key === "Home" && searchOpen && searchMatches.length) {
      event.preventDefault();
      activeSearchIndex = 0;
      renderSearchResults();
    } else if (event.key === "End" && searchOpen && searchMatches.length) {
      event.preventDefault();
      activeSearchIndex = searchMatches.length - 1;
      renderSearchResults();
    } else if (event.key === "Enter") {
      if (activeSearchIndex >= 0) {
        event.preventDefault();
        activateSearchResult();
      } else if (searchMatches.length === 1) {
        event.preventDefault();
        activateSearchResult(0);
      } else if (searchMatches.length > 1) {
        event.preventDefault();
        announce(ui.search_choose_result);
      }
    } else if (event.key === "Escape" && searchOpen) {
      event.preventDefault();
      event.stopPropagation();
      searchOpen = false;
      activeSearchIndex = -1;
      renderSearchResults();
    }
  }

  function matchesFilters(item, isEdge) {
    const kind = params.lens?.value || "all";
    const certainty = params.certainty?.value || "all";
    if (certainty !== "all" && item.dataset.certainty !== certainty) return false;
    if (roleComparison) {
      if (!isEdge) return item.dataset.kind === roleComparison.from || item.dataset.kind === roleComparison.to;
      return Boolean(roleComparisonDirection(item));
    }
    if (kind === "all") return true;
    const [group, value] = kind.split(":", 2);
    return (isEdge ? group === "relationship" : group === "component") && item.dataset.kind === value;
  }

  function roleComparisonDirection(edge) {
    if (!roleComparison) return "";
    const sourceKind = byNode.get(edge.dataset.source)?.dataset.kind;
    const targetKind = byNode.get(edge.dataset.target)?.dataset.kind;
    if (sourceKind === roleComparison.from && targetKind === roleComparison.to) return "forward";
    if (sourceKind === roleComparison.to && targetKind === roleComparison.from) return "reverse";
    return "";
  }

  function updateRoleComparisonStatus() {
    if (!params.roleStatus) return;
    const clear = controls("role-compare-clear");
    if (!roleComparison) {
      params.roleStatus.textContent = "";
      if (clear) clear.disabled = true;
      return;
    }
    let forward = 0;
    let reverse = 0;
    for (const edge of edges) {
      if (params.certainty?.value !== "all" && edge.dataset.certainty !== params.certainty.value) continue;
      const direction = roleComparisonDirection(edge);
      if (direction === "forward") forward += 1;
      else if (direction === "reverse") reverse += 1;
    }
    params.roleStatus.textContent = ui.role_summary
      .replaceAll("{from}", roleComparison.from)
      .replaceAll("{to}", roleComparison.to)
      .replace("{forward}", String(forward))
      .replace("{reverse}", String(reverse));
    if (clear) clear.disabled = false;
  }

  function clearRoleComparison({ hash = true, apply = true } = {}) {
    roleComparison = null;
    if (params.roleA) params.roleA.value = "";
    if (params.roleB) params.roleB.value = "";
    if (params.roleStatus) params.roleStatus.textContent = "";
    const clear = controls("role-compare-clear");
    if (clear) clear.disabled = true;
    if (hash && location.hash.startsWith("#roles/")) {
      const certainty = params.certainty?.value || "all";
      setHash(certainty === "all" ? "" : `certainty/${certainty}`);
    }
    if (apply) applyView();
  }

  function applyRoleComparison({ hash = true, preserveCertainty = false } = {}) {
    const from = params.roleA?.value || "";
    const to = params.roleB?.value || "";
    if (!from || !to || from === to) {
      if (params.roleStatus) params.roleStatus.textContent = ui.role_select_two;
      announce(ui.role_select_two);
      return false;
    }
    roleComparison = { from, to };
    if (params.lens) params.lens.value = "all";
    if (params.certainty && !preserveCertainty) params.certainty.value = "all";
    clearStory({ hash: false, apply: false });
    selectedNode = ""; selectedEdge = ""; activeReach = null; currentRoute = null; routeStep = -1;
    focusNodes = null; focusEdges = null;
    if (params.context) params.context.replaceChildren();
    if (params.routeDetails) params.routeDetails.hidden = true;
    clearPassport();
    if (hash) setHash(roleComparisonHash());
    applyView();
    updateShareButtons();
    announce(`${ui.role_compare} · ${from} / ${to}`);
    return true;
  }

  function roleComparisonHash() {
    if (!roleComparison) return "";
    const certainty = params.certainty?.value || "all";
    const suffix = certainty === "all" ? "" : `/${certainty}`;
    return `roles/${encodeURIComponent(roleComparison.from)}/${encodeURIComponent(roleComparison.to)}${suffix}`;
  }

  function storyForCurrentBeat() {
    if (!currentStory) return null;
    const view = storyViews.find((item) => item.id === currentStory.id);
    const beat = view?.focus[currentStory.index];
    if (!view || !beat) return null;
    const scope = { view, beat, nodes: new Set(), edges: new Set() };
    if (byNode.has(beat)) {
      scope.nodes.add(beat);
      edgeData.filter((item) => item.source === beat || item.target === beat).forEach((item) => {
        scope.edges.add(item.id);
        scope.nodes.add(item.source);
        scope.nodes.add(item.target);
      });
    } else {
      const edge = edgeData.find((item) => item.id === beat);
      if (edge) {
        scope.edges.add(edge.id);
        scope.nodes.add(edge.source);
        scope.nodes.add(edge.target);
      }
    }
    return scope;
  }

  function storyStatusText(view, index) {
    const beatId = view.focus[index];
    const beat = byNode.get(beatId) || byEdge.get(beatId);
    const label = beat?.dataset.label || beatId;
    const note = view.note ? ui.story_note.replace("{note}", view.note) : "";
    return ui.story_status
      .replace("{label}", view.label)
      .replace("{step}", String(index + 1))
      .replace("{total}", String(view.focus.length))
      .replace("{beat}", label) + note;
  }

  function updateStoryControls() {
    if (!params.storyStatus) return;
    const active = Boolean(currentStory);
    const view = active ? storyViews.find((item) => item.id === currentStory.id) : null;
    if (params.storyStatus) params.storyStatus.textContent = view ? storyStatusText(view, currentStory.index) : "";
    if (params.storyView && active) params.storyView.value = view.id;
    if (controls("story-previous")) controls("story-previous").disabled = !view || currentStory.index === 0;
    if (controls("story-next")) controls("story-next").disabled = !view || currentStory.index >= view.focus.length - 1;
    if (controls("story-clear")) controls("story-clear").disabled = !active;
  }

  function clearStory({ hash = true, apply = true } = {}) {
    const wasActive = Boolean(currentStory);
    currentStory = null;
    if (hash && wasActive && location.hash.startsWith("#story/")) setHash("");
    if (apply) applyView();
    else updateStoryControls();
  }

  function applyStoryBeat(viewId, beatId, { hash = true } = {}) {
    const view = storyViews.find((item) => item.id === viewId);
    const index = view?.focus.indexOf(beatId) ?? -1;
    if (!view || index < 0) return false;
    stopTrace(true);
    clearRoleComparison({ hash: false, apply: false });
    if (params.lens) params.lens.value = "all";
    if (params.certainty) params.certainty.value = "all";
    selectedNode = ""; selectedEdge = ""; activeReach = null; currentRoute = null; routeStep = -1;
    focusNodes = null; focusEdges = null;
    if (params.focus) params.focus.value = "";
    if (params.context) params.context.replaceChildren();
    if (params.routeDetails) params.routeDetails.hidden = true;
    clearPassport();
    if (params.storyView) params.storyView.value = view.id;
    if (controls("explore-tools")) controls("explore-tools").open = true;
    currentStory = { id: view.id, index };
    if (hash) setHash(`story/${encodeURIComponent(view.id)}/${encodeURIComponent(beatId)}`);
    applyView();
    updateShareButtons();
    announce(storyStatusText(view, index));
    return true;
  }

  function startStory(viewId = params.storyView?.value) {
    const view = storyViews.find((item) => item.id === viewId);
    if (view) applyStoryBeat(view.id, view.focus[0]);
  }

  function moveStory(step) {
    const view = storyViews.find((item) => item.id === currentStory?.id);
    if (!view) return;
    const index = currentStory.index + step;
    if (index >= 0 && index < view.focus.length) applyStoryBeat(view.id, view.focus[index]);
  }

  function applyView() {
    const story = storyForCurrentBeat();
    for (const [id, node] of byNode) {
      const inFocus = story ? story.nodes.has(id) : !focusNodes || focusNodes.has(id);
      const visible = matchesFilters(node, false);
      node.classList.toggle("is-muted", !inFocus || !visible);
      const roleA = Boolean(roleComparison && node.dataset.kind === roleComparison.from);
      const roleB = Boolean(roleComparison && node.dataset.kind === roleComparison.to);
      node.classList.toggle("is-role-a", roleA);
      node.classList.toggle("is-role-b", roleB);
      node.classList.toggle("is-story-beat", story?.beat === id);
      node.classList.toggle("is-story-context", Boolean(story && story.nodes.has(id) && story.beat !== id));
      node.classList.toggle("is-highlighted", story ? story.nodes.has(id) && visible : Boolean(focusNodes && focusNodes.has(id)) || ((roleA || roleB) && visible));
      node.setAttribute("aria-pressed", String(selectedNode === id));
    }
    for (const [id, edge] of byEdge) {
      const endpointsVisible = story
        ? story.nodes.has(edge.dataset.source) && story.nodes.has(edge.dataset.target)
        : !focusNodes || (focusNodes.has(edge.dataset.source) && focusNodes.has(edge.dataset.target));
      const inFocus = story ? story.edges.has(id) : !focusEdges || focusEdges.has(id);
      const visible = matchesFilters(edge, true);
      const direction = roleComparisonDirection(edge);
      edge.classList.toggle("is-role-forward", direction === "forward" && visible);
      edge.classList.toggle("is-role-reverse", direction === "reverse" && visible);
      edge.classList.toggle("is-story-beat", story?.beat === id);
      edge.classList.toggle("is-story-context", Boolean(story && story.edges.has(id) && story.beat !== id));
      edge.classList.toggle("is-muted", !endpointsVisible || !inFocus || !visible);
      edge.classList.toggle("is-highlighted", story ? story.edges.has(id) && visible : Boolean(focusEdges && focusEdges.has(id)) || (Boolean(direction) && visible));
      edge.setAttribute("aria-pressed", String(selectedEdge === id));
    }
    updateRoleComparisonStatus();
    updateStoryControls();
    updateOverviewViewport();
  }

  function setFocus(ids, edgeIds, message) {
    if (roleComparison) clearRoleComparison({ hash: false, apply: false });
    if (currentStory) clearStory({ hash: false, apply: false });
    focusNodes = ids;
    focusEdges = edgeIds;
    applyView();
    if (message) announce(message);
  }

  function setHash(value) {
    history.replaceState(null, "", `${location.pathname}${location.search}${value ? `#${value}` : ""}`);
  }

  function evidenceLinks(target, ids) {
    const label = document.createElement("strong");
    label.textContent = `${ui.evidence_ids}: `;
    target.append(label);
    if (!ids.length) {
      target.append(document.createTextNode("—"));
      return;
    }
    ids.forEach((id, index) => {
      if (index) target.append(document.createTextNode(" · "));
      const row = evidenceRows.get(id);
      if (row) {
        const link = document.createElement("a");
        link.href = `#evidence-${encodeURIComponent(id)}`;
        link.textContent = id;
        link.addEventListener("click", () => setTimeout(() => row.scrollIntoView({ block: "center" }), 0));
        target.append(link);
      } else target.append(document.createTextNode(id));
    });
  }

  function showPassport(item, type) {
    if (!params.passport || !params.passportBody) return;
    params.passportBody.replaceChildren();
    const facts = document.createElement("div");
    facts.className = "passport-facts";
    const addFact = (value) => {
      const fact = document.createElement("span");
      fact.className = "passport-fact";
      fact.textContent = value;
      facts.append(fact);
    };
    addFact(`${type === "node" ? ui.component : ui.relationship_kind_label} · ${item.id}`);
    addFact(item.label);
    addFact(item.kind);
    addFact(ui[item.certainty] || item.certainty);
    if (type === "edge") addFact(`${item.source} → ${item.target}${item.order ? ` · #${item.order}` : ""}${item.feedback ? " · feedback" : ""}`);
    if (type === "node") {
      const upstream = walk(item.id, true);
      const downstream = walk(item.id, false);
      const directIn = edgeData.filter((edge) => edge.target === item.id).length;
      const directOut = edgeData.filter((edge) => edge.source === item.id).length;
      addFact(ui.passport_upstream.replace("{direct}", String(directIn)).replace("{reachable}", String(upstream.nodes.size - 1)));
      addFact(ui.passport_downstream.replace("{direct}", String(directOut)).replace("{reachable}", String(downstream.nodes.size - 1)));
    }
    params.passportBody.append(facts);
    const evidence = document.createElement("p");
    evidence.className = "passport-evidence";
    evidenceLinks(evidence, item.evidence);
    params.passportBody.append(evidence);
    if (item.reason) {
      const reason = document.createElement("p");
      reason.textContent = item.reason;
      params.passportBody.append(reason);
    }
    const related = type === "node" ? edgeData.filter((edge) => edge.source === item.id || edge.target === item.id) : [];
    if (related.length) {
      const heading = document.createElement("strong");
      heading.textContent = ui.direct_relationships;
      params.passportBody.append(heading);
      const list = document.createElement("ul");
      list.className = "passport-relationships";
      for (const edge of related) {
        const li = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = `${edge.source} → ${edge.target} · ${edge.id} · ${edge.label}`;
        button.addEventListener("click", () => pinEdge(edge.id));
        li.append(button);
        list.append(li);
      }
      params.passportBody.append(list);
    }
    params.passport.hidden = false;
    controls("passport-title").textContent = ui.passport;
    if (params.passportStatus) params.passportStatus.textContent = "";
  }

  function focusOne(id, { hash = true } = {}) {
    const node = byNode.get(id);
    if (!node) return;
    selectedNode = id;
    selectedEdge = "";
    activeReach = null;
    currentRoute = null;
    if (params.routeDetails) params.routeDetails.hidden = true;
    if (params.focus) params.focus.value = id;
    const adjacent = edgeData.filter((edge) => edge.source === id || edge.target === id);
    const reachedNodes = new Set([id, ...adjacent.flatMap((edge) => [edge.source, edge.target])]);
    const reachedEdges = new Set(adjacent.map((edge) => edge.id));
    revealEntity(node);
    setFocus(reachedNodes, reachedEdges, `${node.dataset.label || id} · ${ui[node.dataset.certainty] || ui.unknown}`);
    updateContext(id);
    showPassport(nodeData.find((item) => item.id === id), "node");
    updateShareButtons();
    if (hash) setHash(`node-${encodeURIComponent(id)}`);
  }

  function pinEdge(id, { hash = true } = {}) {
    const edge = byEdge.get(id);
    if (!edge || !byNode.has(edge.dataset.source) || !byNode.has(edge.dataset.target)) {
      announce(ui.pin_conflict);
      return false;
    }
    const item = edgeData.find((entry) => entry.id === id);
    if (!item) {
      announce(ui.pin_conflict);
      return false;
    }
    selectedNode = item.source;
    selectedEdge = id;
    activeReach = null;
    currentRoute = null;
    if (params.routeDetails) params.routeDetails.hidden = true;
    if (params.focus) params.focus.value = item.source;
    revealEntity(edge);
    setFocus(new Set([item.source, item.target]), new Set([id]), `${ui.relation} ${id} · ${ui[item.certainty] || ui.unknown}`);
    updateContext(item.source);
    showPassport(item, "edge");
    updateShareButtons();
    if (hash) setHash(`edge-${encodeURIComponent(id)}`);
    return true;
  }

  function walk(start, reverse) {
    const reached = new Set([start]);
    const routeEdges = new Set();
    const queue = [start];
    while (queue.length) {
      const current = queue.shift();
      for (const edge of edgeData) {
        const follows = reverse ? edge.target === current : edge.source === current;
        if (!follows) continue;
        const next = reverse ? edge.source : edge.target;
        routeEdges.add(edge.id);
        if (!reached.has(next)) {
          reached.add(next);
          queue.push(next);
        }
      }
    }
    return { nodes: reached, edges: routeEdges };
  }

  function exactPath(start, goal) {
    if (!start || !goal || start === goal || !byNode.has(start) || !byNode.has(goal)) return null;
    const queue = [start];
    const previous = new Map([[start, null]]);
    const via = new Map();
    while (queue.length) {
      const current = queue.shift();
      if (current === goal) break;
      for (const edge of edgeData) {
        if (edge.source !== current || previous.has(edge.target)) continue;
        previous.set(edge.target, current);
        via.set(edge.target, edge.id);
        queue.push(edge.target);
      }
    }
    if (!previous.has(goal)) return null;
    const orderedNodes = [];
    const orderedEdges = [];
    for (let cursor = goal; cursor !== null; cursor = previous.get(cursor)) {
      orderedNodes.push(cursor);
      if (via.has(cursor)) orderedEdges.push(via.get(cursor));
    }
    orderedNodes.reverse();
    orderedEdges.reverse();
    return { nodes: new Set(orderedNodes), edges: new Set(orderedEdges), orderedNodes, orderedEdges, start, goal };
  }

  function routeProbe({ hash = true } = {}) {
    const start = params.routeFrom?.value || "";
    const goal = params.routeTo?.value || "";
    const route = exactPath(start, goal);
    if (!route) {
      stopTrace(false);
      selectedNode = "";
      selectedEdge = "";
      activeReach = null;
      currentRoute = null;
      routeStep = -1;
      if (params.focus) params.focus.value = "";
      if (params.context) params.context.replaceChildren();
      if (params.passport) params.passport.hidden = true;
      if (params.routeDetails) params.routeDetails.hidden = true;
      setFocus(null, null, start && start === goal ? ui.no_route_same_node : ui.no_route);
      updateShareButtons();
      return null;
    }
    currentRoute = route;
    selectedNode = start;
    selectedEdge = "";
    activeReach = null;
    routeStep = route.orderedEdges.length - 1;
    if (params.focus) params.focus.value = start;
    revealEntity(byNode.get(start));
    setFocus(route.nodes, route.edges, `${ui.exact_route}: ${route.orderedNodes.join(" → ")} · ${route.orderedEdges.length} ${ui.relationships_count}`);
    renderRoute(route);
    if (params.passport) params.passport.hidden = true;
    updateContext(start);
    updateShareButtons();
    if (hash) setHash(`route/${encodeURIComponent(start)}/${encodeURIComponent(goal)}`);
    return route;
  }

  function renderRoute(route) {
    if (!params.routeDetails || !params.routeList || !params.routeTitle) return;
    params.routeDetails.hidden = false;
    params.routeTitle.textContent = `${ui.exact_route}: ${route.start} → ${route.goal}`;
    params.routeList.replaceChildren();
    route.orderedNodes.forEach((id, index) => {
      const li = document.createElement("li");
      const node = byNode.get(id);
      li.textContent = `${id} · ${node?.dataset.label || id}`;
      if (index < route.orderedEdges.length) {
        const edge = edgeData.find((item) => item.id === route.orderedEdges[index]);
        li.append(document.createTextNode(` — ${edge?.id || ""} · ${edge?.label || ""} →`));
      }
      params.routeList.append(li);
    });
    if (params.routeJourney) params.routeJourney.hidden = false;
    updateJourneyStatus();
  }

  function updateJourneyStatus() {
    if (!currentRoute || !params.routeStepStatus) return;
    const step = Math.max(0, routeStep);
    params.routeStepStatus.textContent = `${ui.route_steps} ${Math.min(step + 1, currentRoute.orderedEdges.length)}/${currentRoute.orderedEdges.length}`;
    const previous = controls("route-previous");
    const next = controls("route-next");
    if (previous) previous.disabled = step <= 0;
    if (next) next.disabled = step >= currentRoute.orderedEdges.length - 1;
  }

  function focusRouteStep(index) {
    if (!currentRoute) return;
    routeStep = Math.max(0, Math.min(index, currentRoute.orderedEdges.length - 1));
    const nodeIds = currentRoute.orderedNodes.slice(0, routeStep + 2);
    const edgeIds = currentRoute.orderedEdges.slice(0, routeStep + 1);
    revealEntity(byEdge.get(edgeIds[edgeIds.length - 1]));
    setFocus(new Set(nodeIds), new Set(edgeIds), `${ui.route_steps} ${routeStep + 1}/${currentRoute.orderedEdges.length} · ${edgeIds[edgeIds.length - 1]}`);
    updateJourneyStatus();
  }

  function stopTrace(restore = true) {
    if (traceTimer) clearTimeout(traceTimer);
    traceTimer = 0;
    if (restore && currentRoute) setFocus(currentRoute.nodes, currentRoute.edges, ui.trace_complete);
  }

  function updateContext(id) {
    if (!params.context || !byNode.has(id)) return;
    params.context.replaceChildren();
    const upstream = walk(id, true);
    const downstream = walk(id, false);
    const directIn = edgeData.filter((edge) => edge.target === id).length;
    const directOut = edgeData.filter((edge) => edge.source === id).length;
    const radar = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    radar.setAttribute("viewBox", "0 0 480 82");
    radar.setAttribute("role", "img");
    radar.setAttribute("aria-label", `${ui.context} · ${id} · ${byNode.get(id)?.dataset.label || id}`);
    const addSvg = (name, attrs = {}, text = "") => {
      const element = document.createElementNS("http://www.w3.org/2000/svg", name);
      for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
      if (text) element.textContent = text;
      radar.append(element);
      return element;
    };
    addSvg("title", {}, `${ui.incoming} ${upstream.nodes.size - 1}; ${ui.outgoing} ${downstream.nodes.size - 1}`);
    addSvg("text", { x: 8, y: 13, class: "radar-label" }, ui.radar_in);
    addSvg("text", { x: 472, y: 13, class: "radar-label", "text-anchor": "end" }, ui.radar_out);
    const incoming = [...upstream.nodes].filter((node) => node !== id).sort().slice(0, 5);
    const outgoing = [...downstream.nodes].filter((node) => node !== id).sort().slice(0, 5);
    incoming.forEach((nodeId, index) => {
      const x = 34 + index * 37;
      addSvg("line", { x1: x, y1: 44, x2: 218, y2: 44, class: "radar-line" });
      const dot = addSvg("circle", { cx: x, cy: 44, r: 10, class: "radar-up" });
      addSvg("text", { x, y: 47, class: "radar-node-index", "text-anchor": "middle" }, String(index + 1));
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = `${nodeId} · ${byNode.get(nodeId)?.dataset.label || nodeId}`;
      dot.append(title);
    });
    addSvg("line", { x1: 221, y1: 44, x2: 259, y2: 44, class: "radar-hub-line" });
    const hub = addSvg("circle", { cx: 240, cy: 44, r: 17, class: "radar-hub" });
    const hubTitle = document.createElementNS("http://www.w3.org/2000/svg", "title");
    hubTitle.textContent = `${id} · ${byNode.get(id)?.dataset.label || id}`;
    hub.append(hubTitle);
    outgoing.forEach((nodeId, index) => {
      const x = 286 + index * 37;
      addSvg("line", { x1: 262, y1: 44, x2: x, y2: 44, class: "radar-line" });
      const dot = addSvg("circle", { cx: x, cy: 44, r: 10, class: "radar-down" });
      addSvg("text", { x, y: 47, class: "radar-node-index", "text-anchor": "middle" }, String(index + 1));
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = `${nodeId} · ${byNode.get(nodeId)?.dataset.label || nodeId}`;
      dot.append(title);
    });
    params.context.append(radar);
    const neighbors = document.createElement("div");
    neighbors.className = "context-neighbors";
    for (const [label, nodes, total] of [
      [ui.radar_in, incoming, upstream.nodes.size - 1],
      [ui.radar_out, outgoing, downstream.nodes.size - 1],
    ]) {
      const group = document.createElement("div");
      group.className = "context-neighbor-group";
      const heading = document.createElement("strong");
      heading.className = "context-neighbor-heading";
      heading.textContent = label;
      const list = document.createElement("div");
      list.className = "context-neighbor-list";
      nodes.forEach((nodeId, index) => {
        const item = document.createElement("span");
        item.className = "context-neighbor";
        const number = document.createElement("span");
        number.className = "context-neighbor-index";
        number.textContent = String(index + 1);
        const code = document.createElement("code");
        code.textContent = nodeId;
        code.title = byNode.get(nodeId)?.dataset.label || nodeId;
        item.append(number, code);
        list.append(item);
      });
      if (!nodes.length) {
        const empty = document.createElement("span");
        empty.className = "context-neighbor-more";
        empty.textContent = "—";
        list.append(empty);
      }
      if (total > nodes.length) {
        const more = document.createElement("span");
        more.className = "context-neighbor-more";
        more.textContent = `+${total - nodes.length}`;
        more.title = `${total - nodes.length} ${label}`;
        list.append(more);
      }
      group.append(heading, list);
      neighbors.append(group);
    }
    params.context.append(neighbors);
    for (const text of [
      `${ui.incoming}: ${directIn} direct · ${upstream.nodes.size - 1} reachable`,
      `${ui.outgoing}: ${directOut} direct · ${downstream.nodes.size - 1} reachable`,
      `${ui.confirmed_relationships}: ${edgeData.filter((edge) => edge.certainty === "confirmed" && (upstream.edges.has(edge.id) || downstream.edges.has(edge.id))).length}`,
      `${ui.uncertain_relationships}: ${edgeData.filter((edge) => edge.certainty !== "confirmed" && (upstream.edges.has(edge.id) || downstream.edges.has(edge.id))).length}`,
    ]) {
      const item = document.createElement("span");
      item.className = "context-metric";
      item.textContent = text;
      params.context.append(item);
    }
  }

  function focusReach(direction, { hash = true } = {}) {
    if (!selectedNode || !byNode.has(selectedNode)) return announce(ui.choose_component);
    currentRoute = null;
    selectedEdge = "";
    if (params.routeDetails) params.routeDetails.hidden = true;
    const result = walk(selectedNode, direction === "upstream");
    if (result.nodes.size <= 1 || result.edges.size === 0) {
      activeReach = null;
      updateShareButtons();
      return announce(ui.no_reach);
    }
    activeReach = { direction, center: selectedNode, nodes: result.nodes, edges: result.edges };
    revealEntity(byNode.get(selectedNode));
    currentRoute = null;
    selectedEdge = "";
    setFocus(result.nodes, result.edges, `${direction === "upstream" ? ui.upstream_status : ui.downstream_status} · ${result.nodes.size - 1} reachable · ${result.edges.size} relationships`);
    params.routeDetails.hidden = true;
    updateShareButtons();
    if (hash) setHash(`reach/${direction}/${encodeURIComponent(selectedNode)}`);
  }

  function updateShareButtons() {
    const routeButton = controls("route-share");
    const reachButton = controls("reach-share");
    if (routeButton) routeButton.disabled = !currentRoute;
    if (reachButton) reachButton.disabled = !activeReach;
  }

  function clonedSvg({ theme = "light", nodesInCard = null, edgesInCard = null } = {}) {
    const clone = svg.cloneNode(true);
    clone.querySelectorAll(".is-muted,.is-highlighted,.is-intent-preview").forEach((element) => element.classList.remove("is-muted", "is-highlighted", "is-intent-preview"));
    clone.querySelectorAll("[data-node-id],[data-edge-id]").forEach((element) => {
      element.removeAttribute("aria-pressed");
      element.removeAttribute("tabindex");
      element.setAttribute("role", "group");
    });
    if (nodesInCard || edgesInCard) {
      for (const node of clone.querySelectorAll("[data-node-id]")) {
        if (!nodesInCard?.has(node.dataset.nodeId)) node.classList.add("is-muted");
        else node.classList.add("is-highlighted");
      }
      for (const edge of clone.querySelectorAll("[data-edge-id]")) {
        if (!edgesInCard?.has(edge.dataset.edgeId)) edge.classList.add("is-muted");
        else edge.classList.add("is-highlighted");
      }
      addSvgStyle(clone, ".is-muted{opacity:.13}.is-highlighted .node-shape{stroke:#b45309;stroke-width:3}.is-highlighted path.edge{stroke:#b45309;stroke-width:3}");
    }
    const darkStyles = ".canvas{fill:#0b0e14}.paper{fill:#121821;stroke:#2d3744}text{fill:#e5eaf0}.header-kicker{fill:#62d4df}.summary,.provenance,.legend,.node-id,.certainty-mark,.group-title,.edge,.legend-title{fill:#a3afbd}.edge,.legend-line{stroke:#a9b7c8}.flow-arrow{fill:#a9b7c8}.node-service,.participant{fill:#182b39;stroke:#53c4d5}.node-data{fill:#16342c;stroke:#56d09b}.node-external{fill:#222a35;stroke:#a7b1c0}.node-decision{fill:#382d1a;stroke:#e4b65d}.node-unknown,.participant-unknown{fill:#3a2422;stroke:#f19a86}.edge-label-bg{fill:#121821;stroke:#384554}.group-box{fill:#171e28;stroke:#738196}.lifeline{stroke:#647387}.edge-data{stroke:#53c4d5}.edge-unknown,.unknown-mark{stroke:#f19a86;fill:#f19a86}";
    const renderedTheme = theme === "auto" ? "light" : theme;
    if (renderedTheme === "dark") addSvgStyle(clone, darkStyles);
    const preset = document.body.dataset.visualPreset || "balanced";
    const presetStyle = presetSvgStyles[preset]?.[renderedTheme];
    if (presetStyle) addSvgStyle(clone, presetStyle);
    if (theme === "auto") {
      const darkPreset = presetSvgStyles[preset]?.dark || "";
      addSvgStyle(clone, `@media (prefers-color-scheme: dark){${darkStyles}${darkPreset}}`);
    }
    return clone;
  }

  function addSvgStyle(root, css) {
    let defs = root.querySelector("defs");
    if (!defs) {
      defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
      root.prepend(defs);
    }
    const style = document.createElementNS("http://www.w3.org/2000/svg", "style");
    style.textContent = css;
    defs.append(style);
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.hidden = true;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function serializeSvg(options) {
    return new Blob([new XMLSerializer().serializeToString(clonedSvg(options))], { type: "image/svg+xml;charset=utf-8" });
  }

  function saveSvg(theme) {
    downloadBlob(serializeSvg({ theme }), theme === "auto" ? "repository-diagram.svg" : `repository-diagram-${theme}.svg`);
    announce(`${theme} SVG ${ui.exported}`);
  }

  async function rasterize(blob, format, background, exactSize = false) {
    const url = URL.createObjectURL(blob);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const bounds = image.width && image.height ? { width: image.width, height: image.height } : svg.viewBox.baseVal;
      const scale = exactSize ? 1 : Math.min(2, 8192 / bounds.width, 8192 / bounds.height, Math.sqrt(24000000 / (bounds.width * bounds.height)));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bounds.width * scale));
      canvas.height = Math.max(1, Math.round(bounds.height * scale));
      const context = canvas.getContext("2d", { alpha: false });
      context.fillStyle = background;
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      const mime = { png: "image/png", jpeg: "image/jpeg", webp: "image/webp" }[format];
      const output = await new Promise((resolve) => canvas.toBlob(resolve, mime, 0.94));
      if (!output || (format === "webp" && output.type !== "image/webp")) throw new Error(ui.export_unavailable);
      return output;
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  async function saveRaster(format) {
    const theme = document.body.dataset.theme === "dark" ? "dark" : "light";
    const background = theme === "dark" ? "#101827" : "#f6f8fc";
    const extension = format === "jpeg" ? "jpg" : format;
    const output = await rasterize(serializeSvg({ theme }), format, background);
    downloadBlob(output, `repository-diagram.${extension}`);
    announce(`${format.toUpperCase()} ${ui.exported}`);
  }

  async function copyPng() {
    const theme = document.body.dataset.theme === "dark" ? "dark" : "light";
    const background = theme === "dark" ? "#101827" : "#f6f8fc";
    const png = await rasterize(serializeSvg({ theme }), "png", background);
    if (!navigator.clipboard?.write || typeof ClipboardItem === "undefined") {
      downloadBlob(png, "repository-diagram.png");
      return announce(ui.png_copy_unavailable);
    }
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": png })]);
      announce(ui.png_copied);
    } catch {
      downloadBlob(png, "repository-diagram.png");
      announce(ui.png_copy_failed);
    }
  }

  function cardSvg(title, subtitle) {
    const root = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    root.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    root.setAttribute("width", "1200");
    root.setAttribute("height", "630");
    root.setAttribute("viewBox", "0 0 1200 630");
    const add = (tag, attrs, value = "") => {
      const item = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attrs).forEach(([key, val]) => item.setAttribute(key, String(val)));
      if (value) item.textContent = value;
      root.append(item);
      return item;
    };
    add("title", {}, title);
    add("rect", { x: 0, y: 0, width: 1200, height: 630, fill: "#101827" });
    add("rect", { x: 34, y: 34, width: 1132, height: 562, rx: 24, fill: "#172235", stroke: "#52647c", "stroke-width": 2 });
    add("text", { x: 72, y: 94, fill: "#8db0ff", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 17, "font-weight": 700, "letter-spacing": 2 }, "PATPAT · REPOSITORY DIAGRAM");
    add("text", { x: 72, y: 145, fill: "#f3f6fb", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 29, "font-weight": 750 }, title);
    add("text", { x: 72, y: 181, fill: "#bdc9db", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 16 }, subtitle);
    return { root, add };
  }

  function compact(value, limit = 24) {
    return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
  }

  async function exportShareCard(kind) {
    let card;
    if (kind === "route") {
      if (!currentRoute) return announce(ui.no_route_card);
      const route = currentRoute;
      const title = ui.route_card_title;
      const routeLength = route.orderedNodes.length;
      card = cardSvg(title, `${routeLength} ${ui.components_count} · ${route.orderedEdges.length} ${ui.relationships_count}`);
      const indices = routeLength > 5 ? [0, 1, null, routeLength - 2, routeLength - 1] : route.orderedNodes.map((_, index) => index);
      const cardWidth = 184;
      const gap = 28;
      const totalWidth = indices.length * cardWidth + (indices.length - 1) * gap;
      const startX = (1200 - totalWidth) / 2;
      const y = 280;
      indices.forEach((routeIndex, index) => {
        const x = startX + index * (cardWidth + gap);
        if (routeIndex === null) {
          const omittedNodes = routeLength - 4;
          const omittedEdges = route.orderedEdges.length - 2;
          card.add("rect", { x, y, width: cardWidth, height: 142, rx: 14, fill: "#202d42", stroke: "#8db0ff", "stroke-width": 2, "stroke-dasharray": "7 5" });
          card.add("text", { x: x + cardWidth / 2, y: y + 38, fill: "#8db0ff", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 32, "font-weight": 700, "text-anchor": "middle" }, "…");
          card.add("text", { x: x + cardWidth / 2, y: y + 81, fill: "#f3f6fb", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 11, "text-anchor": "middle" }, ui.route_nodes_omitted.replace("{count}", String(omittedNodes)));
          card.add("text", { x: x + cardWidth / 2, y: y + 105, fill: "#bdc9db", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 11, "text-anchor": "middle" }, ui.route_edges_omitted.replace("{count}", String(omittedEdges)));
        } else {
          const id = route.orderedNodes[routeIndex];
          const node = byNode.get(id);
          const isEndpoint = routeIndex === 0 || routeIndex === routeLength - 1;
          const tile = card.add("rect", { x, y, width: cardWidth, height: 142, rx: 14, fill: isEndpoint ? "#263753" : "#202d42", stroke: isEndpoint ? "#8db0ff" : "#647b9a", "stroke-width": isEndpoint ? 3 : 2 });
          const idLines = id.match(/.{1,20}/g) || [id];
          idLines.slice(0, 2).forEach((line, lineIndex) => card.add("text", { x: x + 12, y: y + 25 + lineIndex * 16, fill: "#8db0ff", "font-family": "ui-monospace, monospace", "font-size": 11, "font-weight": 700 }, line));
          card.add("text", { x: x + 12, y: y + (idLines.length > 1 ? 70 : 58), fill: "#f3f6fb", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 16, "font-weight": 650 }, compact(node?.dataset.label || id, 19));
          const accessibleTitle = document.createElementNS("http://www.w3.org/2000/svg", "title");
          accessibleTitle.textContent = `${id} · ${node?.dataset.label || id}`;
          tile.append(accessibleTitle);
        }
        if (index < indices.length - 1) card.add("text", { x: x + cardWidth + 3, y: y + 82, fill: "#8db0ff", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 22, "font-weight": 700 }, "→");
      });
      const image = await rasterize(new Blob([new XMLSerializer().serializeToString(card.root)], { type: "image/svg+xml;charset=utf-8" }), "png", "#101827", true);
      downloadBlob(image, "repository-diagram-route-card.png");
    } else {
      if (!activeReach) return announce(ui.no_reach_card);
      const reach = activeReach;
      const center = byNode.get(reach.center);
      const reachableEdges = [...reach.edges].map((id) => edgeData.find((edge) => edge.id === id)).filter(Boolean).sort((left, right) => left.id.localeCompare(right.id));
      if (!center || reach.nodes.size < 2 || reachableEdges.length !== reach.edges.size || reachableEdges.some((edge) => !reach.nodes.has(edge.source) || !reach.nodes.has(edge.target))) {
        return announce(ui.pin_conflict);
      }
      const title = reach.direction === "upstream" ? ui.reach_upstream_title : ui.reach_downstream_title;
      const related = [...reach.nodes].filter((id) => id !== reach.center).sort();
      card = cardSvg(title, `${related.length} ${ui.components_count} · ${reach.edges.size} ${ui.relationships_count} · ${ui.component} ${reach.center}`);
      card.add("rect", { x: 438, y: 216, width: 324, height: 96, rx: 14, fill: "#263753", stroke: "#8db0ff", "stroke-width": 3 });
      card.add("text", { x: 600, y: 249, fill: "#8db0ff", "font-family": "ui-monospace, monospace", "font-size": 15, "font-weight": 700, "text-anchor": "middle" }, reach.center);
      card.add("text", { x: 600, y: 277, fill: "#f3f6fb", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 17, "text-anchor": "middle" }, compact(center?.dataset.label || reach.center, 31));
      card.add("text", { x: 600, y: 297, fill: "#bdc9db", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 11, "text-anchor": "middle" }, ui[center.dataset.certainty] || ui.unknown);
      card.add("text", { x: 72, y: 330, fill: "#8db0ff", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 14, "font-weight": 700 }, ui.reach_components_heading.replace("{count}", String(related.length)));
      card.add("text", { x: 628, y: 330, fill: "#8db0ff", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 14, "font-weight": 700 }, ui.reach_relationships_heading.replace("{count}", String(reach.edges.size)));
      const visibleComponents = related.slice(0, 4);
      visibleComponents.forEach((id, index) => {
        const x = 72;
        const y = 344 + index * 56;
        const node = byNode.get(id);
        const tile = card.add("rect", { x, y, width: 500, height: 45, rx: 9, fill: "#202d42", stroke: "#52647c", "stroke-width": 1.5 });
        const titleNode = document.createElementNS("http://www.w3.org/2000/svg", "title");
        const certainty = ui[node?.dataset.certainty] || ui.unknown;
        titleNode.textContent = `${id} · ${node?.dataset.label || id} · ${certainty}`;
        tile.append(titleNode);
        card.add("text", { x: x + 12, y: y + 17, fill: "#8db0ff", "font-family": "ui-monospace, monospace", "font-size": 11, "font-weight": 700 }, compact(id, 54));
        card.add("text", { x: x + 12, y: y + 35, fill: "#f3f6fb", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 12 }, compact(node?.dataset.label || id, 44));
        card.add("text", { x: x + 488, y: y + 35, fill: "#bdc9db", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 10, "text-anchor": "end" }, certainty);
      });
      const visibleEdges = reachableEdges.slice(0, 4);
      visibleEdges.forEach((edge, index) => {
        const x = 628;
        const y = 344 + index * 56;
        const tile = card.add("rect", { x, y, width: 500, height: 45, rx: 9, fill: "#202d42", stroke: "#52647c", "stroke-width": 1.5 });
        const titleEdge = document.createElementNS("http://www.w3.org/2000/svg", "title");
        const certainty = ui[edge.certainty] || ui.unknown;
        titleEdge.textContent = `${edge.id} · ${edge.source} → ${edge.target} · ${edge.label} · ${certainty}`;
        tile.append(titleEdge);
        card.add("text", { x: x + 12, y: y + 17, fill: "#8db0ff", "font-family": "ui-monospace, monospace", "font-size": 10, "font-weight": 700 }, compact(`${edge.id} · ${edge.source} → ${edge.target}`, 62));
        card.add("text", { x: x + 12, y: y + 35, fill: "#f3f6fb", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 12 }, compact(edge.label, 44));
        card.add("text", { x: x + 488, y: y + 35, fill: "#bdc9db", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 10, "text-anchor": "end" }, certainty);
      });
      const componentOmissions = related.length - visibleComponents.length;
      const relationshipOmissions = reachableEdges.length - visibleEdges.length;
      if (componentOmissions) card.add("text", { x: 72, y: 586, fill: "#bdc9db", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 13 }, ui.reach_components_omitted.replace("{count}", String(componentOmissions)));
      if (relationshipOmissions) card.add("text", { x: 628, y: 586, fill: "#bdc9db", "font-family": "Segoe UI, Arial, sans-serif", "font-size": 13 }, ui.reach_relationships_omitted.replace("{count}", String(relationshipOmissions)));
      const image = await rasterize(new Blob([new XMLSerializer().serializeToString(card.root)], { type: "image/svg+xml;charset=utf-8" }), "png", "#101827", true);
      downloadBlob(image, `repository-diagram-${reach.direction}-reach-card.png`);
    }
    announce(kind === "route" ? ui.route_card_exported : ui.reach_card_exported);
  }

  async function saveWebm() {
    if (!HTMLCanvasElement.prototype.captureStream || typeof MediaRecorder === "undefined") throw new Error(ui.webm_unavailable);
    const route = currentRoute || routeProbe({ hash: false });
    if (!route) return;
    const theme = document.body.dataset.theme === "dark" ? "dark" : "light";
    const whole = serializeSvg({ theme });
    const url = URL.createObjectURL(whole);
    try {
      const image = new Image();
      image.src = url;
      await image.decode();
      const size = svg.viewBox.baseVal;
      const scale = Math.min(1.5, 3840 / size.width, 2160 / size.height, Math.sqrt(8000000 / (size.width * size.height)));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(size.width * scale));
      canvas.height = Math.max(1, Math.round(size.height * scale));
      const context = canvas.getContext("2d", { alpha: false });
      const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
      const frames = reducedMotion ? [route.orderedEdges.length - 1] : route.orderedEdges.map((_edge, index) => index);
      const mime = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((type) => MediaRecorder.isTypeSupported(type));
      if (!mime) throw new Error(ui.webm_unavailable);
      const chunks = [];
      const stream = canvas.captureStream(12);
      const recorder = new MediaRecorder(stream, { mimeType: mime });
      const completed = new Promise((resolve, reject) => {
        recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
        recorder.onerror = () => reject(new Error(ui.recording_failed));
        recorder.onstop = () => resolve(new Blob(chunks, { type: mime }));
      });
      try {
        recorder.start();
        for (const index of frames) {
          const shownEdges = new Set(route.orderedEdges.slice(0, index + 1));
          const shownNodes = new Set(route.orderedNodes.slice(0, index + 2));
          const frame = serializeSvg({ theme, nodesInCard: shownNodes, edgesInCard: shownEdges });
          const frameUrl = URL.createObjectURL(frame);
          try {
            const frameImage = new Image();
            frameImage.src = frameUrl;
            await frameImage.decode();
            context.fillStyle = theme === "dark" ? "#101827" : "#f6f8fc";
            context.fillRect(0, 0, canvas.width, canvas.height);
            context.drawImage(frameImage, 0, 0, canvas.width, canvas.height);
          } finally { URL.revokeObjectURL(frameUrl); }
          await new Promise((resolve) => setTimeout(resolve, reducedMotion ? 500 : 350));
        }
        recorder.stop();
      } finally {
        if (recorder.state !== "inactive") recorder.stop();
        stream.getTracks().forEach((track) => track.stop());
      }
      downloadBlob(await completed, "repository-diagram-route-trace.webm");
      announce(`${ui.webm_trace} · ${frames.length} frames${reducedMotion ? ` · ${ui.reduced_motion}` : ""}`);
    } finally { URL.revokeObjectURL(url); }
  }

  function startTrace() {
    const route = currentRoute || routeProbe();
    if (!route) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      announce(ui.reduced_motion);
      return;
    }
    stopTrace(false);
    let index = 0;
    const tick = () => {
      if (!currentRoute || document.hidden) return;
      focusRouteStep(index++);
      if (index < route.orderedEdges.length) traceTimer = setTimeout(tick, 650);
      else traceTimer = setTimeout(() => stopTrace(true), 650);
    };
    tick();
  }

  function overviewCoordinates() {
    const centers = nodes.map((node) => {
      const box = node.getBBox();
      return { id: node.dataset.nodeId, x: box.x + box.width / 2, y: box.y + box.height / 2 };
    });
    const width = Math.max(320, params.overview.clientWidth || 600);
    const height = Math.min(390, Math.max(220, centers.length * 23));
    const pad = 20;
    const minX = Math.min(...centers.map((point) => point.x));
    const maxX = Math.max(...centers.map((point) => point.x));
    const minY = Math.min(...centers.map((point) => point.y));
    const maxY = Math.max(...centers.map((point) => point.y));
    const spanX = Math.max(1, maxX - minX);
    const spanY = Math.max(1, maxY - minY);
    const scale = Math.min((width - pad * 2) / spanX, (height - pad * 2) / spanY);
    const renderedWidth = spanX * scale;
    const renderedHeight = spanY * scale;
    const ox = (width - renderedWidth) / 2;
    const oy = (height - renderedHeight) / 2;
    const result = new Map();
    for (const center of centers) result.set(center.id, { x: ox + (center.x - minX) * scale, y: oy + (center.y - minY) * scale });
    overviewTransform = {
      width,
      height,
      x: (value) => ox + (value - minX) * scale,
      y: (value) => oy + (value - minY) * scale,
      inverseX: (value) => (value - ox) / scale + minX,
      inverseY: (value) => (value - oy) / scale + minY,
    };
    return { points: result, width, height };
  }

  function overviewClip() {
    const frame = figure.getBoundingClientRect();
    const left = Math.max(frame.left + figure.clientLeft, 0);
    const top = Math.max(frame.top + figure.clientTop, 0);
    const right = Math.min(frame.left + figure.clientLeft + figure.clientWidth, window.innerWidth);
    const bottom = Math.min(frame.top + figure.clientTop + figure.clientHeight, window.innerHeight);
    return { left, top, right: Math.max(left, right), bottom: Math.max(top, bottom) };
  }

  function updateOverviewViewport() {
    if (!overviewViewport || !overviewSvg) return;
    const frame = svg.getBoundingClientRect();
    const view = svg.viewBox.baseVal;
    const clip = overviewClip();
    const fraction = (value, start, size) => Math.max(0, Math.min(1, (value - start) / Math.max(1, size)));
    const visibleX1 = view.x + fraction(clip.left, frame.left, frame.width) * view.width;
    const visibleX2 = view.x + fraction(clip.right, frame.left, frame.width) * view.width;
    const visibleY1 = view.y + fraction(clip.top, frame.top, frame.height) * view.height;
    const visibleY2 = view.y + fraction(clip.bottom, frame.top, frame.height) * view.height;
    const x1 = overviewTransform.x(visibleX1);
    const x2 = overviewTransform.x(visibleX2);
    const y1 = overviewTransform.y(visibleY1);
    const y2 = overviewTransform.y(visibleY2);
    const left = Math.max(0, Math.min(overviewTransform.width, Math.min(x1, x2)));
    const top = Math.max(0, Math.min(overviewTransform.height, Math.min(y1, y2)));
    const right = Math.max(0, Math.min(overviewTransform.width, Math.max(x1, x2)));
    const bottom = Math.max(0, Math.min(overviewTransform.height, Math.max(y1, y2)));
    overviewViewport.setAttribute("x", String(left));
    overviewViewport.setAttribute("y", String(top));
    overviewViewport.setAttribute("width", String(Math.max(8, right - left)));
    overviewViewport.setAttribute("height", String(Math.max(8, bottom - top)));
  }

  function overviewPoint(event) {
    const point = overviewSvg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(overviewSvg.getScreenCTM().inverse());
  }

  function panOverviewTo(point) {
    if (!overviewTransform || !figure) return;
    const worldX = overviewTransform.inverseX(point.x);
    const worldY = overviewTransform.inverseY(point.y);
    const view = svg.viewBox.baseVal;
    const diagramFrame = svg.getBoundingClientRect();
    const clip = overviewClip();
    const targetX = diagramFrame.left + ((worldX - view.x) / view.width) * diagramFrame.width;
    const targetY = diagramFrame.top + ((worldY - view.y) / view.height) * diagramFrame.height;
    const deltaX = targetX - (clip.left + clip.right) / 2;
    const deltaY = targetY - (clip.top + clip.bottom) / 2;
    figure.scrollLeft = Math.max(0, Math.min(figure.scrollWidth - figure.clientWidth, figure.scrollLeft + deltaX));
    if (figure.scrollHeight > figure.clientHeight) {
      figure.scrollTop = Math.max(0, Math.min(figure.scrollHeight - figure.clientHeight, figure.scrollTop + deltaY));
    } else if (Math.abs(deltaY) > 1) {
      window.scrollBy(0, deltaY);
    }
    updateOverviewViewport();
  }

  function revealEntity(entity) {
    if (!entity) return;
    entity.scrollIntoView({ block: "nearest", inline: "nearest" });
    updateOverviewViewport();
  }

  function renderOverview() {
    if (!params.overview || !validModel) return;
    params.overview.replaceChildren();
    const { points, width, height } = overviewCoordinates();
    overviewSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    overviewSvg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    overviewSvg.setAttribute("role", "group");
    overviewSvg.setAttribute("aria-label", ui.overview);
    overviewSvg.style.height = `${height}px`;
    for (const edge of edgeData) {
      const from = points.get(edge.source);
      const to = points.get(edge.target);
      if (!from || !to) continue;
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", String(from.x)); line.setAttribute("y1", String(from.y));
      line.setAttribute("x2", String(to.x)); line.setAttribute("y2", String(to.y));
      line.setAttribute("class", "overview-edge");
      overviewSvg.append(line);
    }
    const placedLabels = [];
    const mapNodes = [...points].sort((left, right) => left[1].y - right[1].y || left[1].x - right[1].x || left[0].localeCompare(right[0]));
    const compactIds = { REVIEW_GATE: "RVW", DELIVERY_GATE: "DLV", MERGE_GATE: "MRG" };
    for (const [id, point] of mapNodes) {
      const node = byNode.get(id);
      const markerKind = ["start", "decision", "terminal"].includes(node?.dataset.kind) ? node.dataset.kind : "action";
      const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
      group.setAttribute("class", `overview-node overview-node-${markerKind}`);
      group.setAttribute("tabindex", "0"); group.setAttribute("role", "button");
      group.setAttribute("aria-label", `${ui.focus_node} ${id} · ${node?.dataset.label || id}`);
      group.setAttribute("aria-keyshortcuts", "Enter Space");
      group.dataset.overviewNode = id;
      const hit = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      hit.setAttribute("cx", String(point.x)); hit.setAttribute("cy", String(point.y)); hit.setAttribute("r", "10");
      hit.setAttribute("class", "overview-hit"); group.append(hit);
      let marker;
      if (markerKind === "decision") {
        marker = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
        marker.setAttribute("points", `${point.x},${point.y - 7} ${point.x + 7},${point.y} ${point.x},${point.y + 7} ${point.x - 7},${point.y}`);
      } else if (markerKind === "start") {
        marker = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        marker.setAttribute("cx", String(point.x)); marker.setAttribute("cy", String(point.y)); marker.setAttribute("r", "6");
      } else {
        marker = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        marker.setAttribute("x", String(point.x - (markerKind === "terminal" ? 7 : 5)));
        marker.setAttribute("y", String(point.y - 5));
        marker.setAttribute("width", markerKind === "terminal" ? "14" : "10");
        marker.setAttribute("height", "10");
        marker.setAttribute("rx", markerKind === "terminal" ? "5" : "2");
      }
      marker.setAttribute("class", "overview-marker"); group.append(marker);
      const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent = `${id} · ${node?.dataset.label || id}`;
      group.append(title);

      const horizontalCandidates = point.x > width * 0.66 ? ["left", "right"] : ["right", "left"];
      const candidates = [...horizontalCandidates, "above", "below"];
      const labelOptions = [id, compactIds[id], ...Array.from({ length: Math.max(0, id.length - 4) }, (_, index) => `${id.slice(0, id.length - index - 1)}…`)].filter(Boolean);
      let labelPlaced = false;
      for (const displayId of labelOptions) {
        if (labelPlaced) break;
        const labelWidth = Math.max(18, displayId.length * 5.7 + 6);
        for (const side of candidates) {
          const vertical = side === "above" || side === "below";
          const x = side === "right" ? point.x + 10 : side === "left" ? point.x - 10 - labelWidth : point.x - labelWidth / 2;
          const centerY = side === "above" ? point.y - 18 : side === "below" ? point.y + 18 : point.y;
          const box = { left: x, right: x + labelWidth, top: centerY - 7, bottom: centerY + 7 };
          if (box.left < 4 || box.right > width - 4 || box.top < 4 || box.bottom > height - 4) continue;
          const overlapsLabel = placedLabels.some((other) => box.left < other.right + 3 && box.right + 3 > other.left && box.top < other.bottom + 2 && box.bottom + 2 > other.top);
          const overlapsNode = mapNodes.some(([otherId, other]) => {
            if (otherId === id) return false;
            const otherKind = ["start", "decision", "terminal"].includes(byNode.get(otherId)?.dataset.kind) ? byNode.get(otherId).dataset.kind : "action";
            const radius = otherKind === "decision" || otherKind === "terminal" ? 7 : otherKind === "start" ? 6 : 5;
            const markerBounds = { left: other.x - radius - 2, right: other.x + radius + 2, top: other.y - radius - 2, bottom: other.y + radius + 2 };
            return box.left < markerBounds.right && box.right > markerBounds.left && box.top < markerBounds.bottom && box.bottom > markerBounds.top;
          });
          if (overlapsLabel || overlapsNode) continue;
          const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
          label.setAttribute("x", side === "right" ? String(box.left + 2) : side === "left" ? String(box.right - 2) : String(point.x));
          label.setAttribute("y", String(centerY + 3));
          label.setAttribute("text-anchor", vertical ? "middle" : side === "right" ? "start" : "end");
          label.setAttribute("class", "overview-node-id");
          label.textContent = displayId;
          group.append(label);
          placedLabels.push(box);
          labelPlaced = true;
          break;
        }
      }
      overviewSvg.append(group);
    }
    overviewViewport = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    overviewViewport.setAttribute("class", "overview-viewport");
    overviewSvg.append(overviewViewport);
    params.overview.append(overviewSvg);
    overviewSvg.addEventListener("pointerdown", (event) => {
      if (event.target.closest("[data-overview-node]")) return;
      overviewPointer = { id: event.pointerId, x: event.clientX, y: event.clientY, moved: false };
      overviewSvg.setPointerCapture(event.pointerId);
    });
    overviewSvg.addEventListener("pointermove", (event) => {
      if (!overviewPointer || overviewPointer.id !== event.pointerId) return;
      const delta = Math.hypot(event.clientX - overviewPointer.x, event.clientY - overviewPointer.y);
      if (delta > 3) overviewPointer.moved = true;
      if (overviewPointer.moved) panOverviewTo(overviewPoint(event));
    });
    const endOverviewPointer = (event) => {
      if (!overviewPointer || overviewPointer.id !== event.pointerId) return;
      const moved = overviewPointer.moved;
      overviewPointer = null;
      if (moved) {
        suppressOverviewClick = true;
        setTimeout(() => { suppressOverviewClick = false; }, 0);
      }
      if (overviewSvg.hasPointerCapture(event.pointerId)) overviewSvg.releasePointerCapture(event.pointerId);
    };
    overviewSvg.addEventListener("pointerup", endOverviewPointer);
    overviewSvg.addEventListener("pointercancel", endOverviewPointer);
    overviewSvg.addEventListener("click", (event) => {
      if (suppressOverviewClick) { suppressOverviewClick = false; return; }
      const node = event.target.closest("[data-overview-node]");
      if (node) return focusOne(node.dataset.overviewNode);
      panOverviewTo(overviewPoint(event));
    });
    overviewSvg.addEventListener("keydown", (event) => {
      if (!(event.key === "Enter" || event.key === " ")) return;
      const node = event.target.closest("[data-overview-node]");
      if (node) { event.preventDefault(); focusOne(node.dataset.overviewNode); }
    });
    updateOverviewViewport();
  }

  function previewIntent(target) {
    svg.querySelectorAll(".is-intent-preview").forEach((element) => element.classList.remove("is-intent-preview"));
    const node = target.closest("[data-node-id]");
    const edge = target.closest("[data-edge-id]");
    const ids = new Set();
    if (node) {
      const id = node.dataset.nodeId;
      ids.add(id);
      edgeData.filter((item) => item.source === id || item.target === id).forEach((item) => { ids.add(item.id); ids.add(item.source); ids.add(item.target); });
    } else if (edge) {
      ids.add(edge.dataset.edgeId); ids.add(edge.dataset.source); ids.add(edge.dataset.target);
    }
    ids.forEach((id) => (byNode.get(id) || byEdge.get(id))?.classList.add("is-intent-preview"));
  }

  function clearPassport() {
    if (params.passport) params.passport.hidden = true;
    if (params.passportStatus) params.passportStatus.textContent = "";
  }

  function handleHash() {
    if (!validModel) return announce(ui.pin_conflict);
    const hash = decodeURIComponent(location.hash.slice(1));
    let match = hash.match(/^node-([A-Za-z][A-Za-z0-9_-]{0,31})$/);
    if (match && byNode.has(match[1])) return focusOne(match[1], { hash: false });
    match = hash.match(/^edge-([A-Za-z][A-Za-z0-9_-]{0,31})$/);
    if (match && byEdge.has(match[1])) return pinEdge(match[1], { hash: false });
    match = hash.match(/^route\/([A-Za-z][A-Za-z0-9_-]{0,31})\/([A-Za-z][A-Za-z0-9_-]{0,31})$/);
    if (match) {
      params.routeFrom.value = match[1]; params.routeTo.value = match[2];
      return routeProbe({ hash: false });
    }
    match = hash.match(/^reach\/(upstream|downstream)\/([A-Za-z][A-Za-z0-9_-]{0,31})$/);
    if (match && byNode.has(match[2])) {
      focusOne(match[2], { hash: false });
      return focusReach(match[1], { hash: false });
    }
    match = hash.match(/^roles\/([A-Za-z][A-Za-z0-9_-]{0,31})\/([A-Za-z][A-Za-z0-9_-]{0,31})(?:\/(confirmed|inferred|unknown))?$/);
    if (match && match[1] !== match[2]
      && [...params.roleA.options].some((item) => item.value === match[1])
      && [...params.roleB.options].some((item) => item.value === match[2])) {
      params.roleA.value = match[1];
      params.roleB.value = match[2];
      if (params.certainty) params.certainty.value = match[3] || "all";
      return applyRoleComparison({ hash: false, preserveCertainty: true });
    }
    match = hash.match(/^story\/([A-Za-z][A-Za-z0-9_-]{0,31})\/([A-Za-z][A-Za-z0-9_-]{0,31})$/);
    if (match && storyViews.some((view) => view.id === match[1] && view.focus.includes(match[2]))) {
      return applyStoryBeat(match[1], match[2], { hash: false });
    }
    match = hash.match(/^lens\/(component|relationship)\/([A-Za-z][A-Za-z0-9_-]{0,31})$/);
    if (match && [...params.lens.options].some((item) => item.value === `${match[1]}:${match[2]}`)) {
      clearRoleComparison({ hash: false, apply: false });
      params.lens.value = `${match[1]}:${match[2]}`;
      applyView();
      return announce(`${ui[match[1] === "component" ? "component_kind" : "relationship_kind"]} · ${match[2]}`);
    }
    match = hash.match(/^certainty\/(confirmed|inferred|unknown)$/);
    if (match) {
      clearRoleComparison({ hash: false, apply: false });
      clearStory({ hash: false, apply: false });
      params.certainty.value = match[1];
      applyView();
      return announce(`${ui.certainty_lens} · ${ui[match[1]]}`);
    }
  }

  function clearFocus() {
    stopTrace(false);
    selectedNode = ""; selectedEdge = ""; activeReach = null; currentRoute = null; routeStep = -1;
    clearRoleComparison({ hash: false, apply: false });
    clearStory({ hash: false, apply: false });
    if (params.focus) params.focus.value = "";
    if (params.context) params.context.replaceChildren();
    if (params.routeDetails) params.routeDetails.hidden = true;
    clearPassport();
    setHash(""); setFocus(null, null, ui.all_visible); updateShareButtons();
  }

  function bind() {
    if (!validModel) {
      announce(ui.pin_conflict);
      return;
    }
    const requestedTheme = new URLSearchParams(location.search).get("theme")
      || document.querySelector('meta[name="patpat-browser-check-theme"]')?.content;
    if (requestedTheme === "light" || requestedTheme === "dark") {
      document.body.dataset.theme = requestedTheme;
      controls("theme-toggle")?.setAttribute("aria-pressed", String(requestedTheme === "dark"));
    }
    setVisualPreset(document.body.dataset.visualPreset || "balanced", false);
    fillSelectors();
    renderOverview();
    params.overview?.closest(".overview-drawer")?.addEventListener("toggle", (event) => {
      if (event.target.open) requestAnimationFrame(renderOverview);
    });
    nodes.forEach((node) => { node.setAttribute("tabindex", "0"); node.setAttribute("role", "button"); });
    edges.forEach((edge) => { edge.setAttribute("tabindex", "0"); edge.setAttribute("role", "button"); });
    params.focus?.addEventListener("change", () => params.focus.value && focusOne(params.focus.value));
    params.search?.addEventListener("input", updateSearchResults);
    params.search?.addEventListener("focus", () => {
      if (params.search.value.trim() && searchMatches.length) {
        searchOpen = true;
        renderSearchResults();
      }
    });
    params.search?.addEventListener("keydown", handleSearchKeydown);
    document.addEventListener("click", (event) => {
      if (event.target.closest?.(".search-field") || !searchOpen) return;
      searchOpen = false;
      activeSearchIndex = -1;
      renderSearchResults();
    });
    controls("role-compare")?.addEventListener("click", () => applyRoleComparison());
    controls("role-compare-clear")?.addEventListener("click", () => clearRoleComparison());
    controls("story-start")?.addEventListener("click", () => startStory());
    controls("story-previous")?.addEventListener("click", () => moveStory(-1));
    controls("story-next")?.addEventListener("click", () => moveStory(1));
    controls("story-clear")?.addEventListener("click", () => clearStory());
    params.storyView?.addEventListener("change", () => {
      if (currentStory && currentStory.id !== params.storyView.value) clearStory();
    });
    params.lens?.addEventListener("change", () => {
      clearRoleComparison({ hash: false, apply: false });
      clearStory({ hash: false, apply: false });
      applyView();
      const [group, kind] = params.lens.value.split(":", 2);
      if (group && kind) setHash(`lens/${group}/${encodeURIComponent(kind)}`);
      else setHash("");
      const count = [...nodes, ...edges].filter((item) => matchesFilters(item, item.hasAttribute("data-edge-id"))).length;
      announce(`${count} ${ui.kind_count}`);
    });
    params.certainty?.addEventListener("change", () => {
      clearStory({ hash: false, apply: false });
      applyView();
      if (roleComparison) setHash(roleComparisonHash());
      else setHash(params.certainty.value === "all" ? "" : `certainty/${params.certainty.value}`);
      const count = [...nodes, ...edges].filter((item) => matchesFilters(item, item.hasAttribute("data-edge-id"))).length;
      announce(`${count} ${ui.kind_count}`);
    });
    controls("focus-upstream")?.addEventListener("click", () => focusReach("upstream"));
    controls("focus-downstream")?.addEventListener("click", () => focusReach("downstream"));
    controls("focus-clear")?.addEventListener("click", clearFocus);
    controls("route-probe")?.addEventListener("click", () => routeProbe());
    controls("route-share")?.addEventListener("click", () => exportShareCard("route"));
    controls("reach-share")?.addEventListener("click", () => exportShareCard("reach"));
    controls("motion-trace")?.addEventListener("click", startTrace);
    controls("route-previous")?.addEventListener("click", () => focusRouteStep(routeStep - 1));
    controls("route-next")?.addEventListener("click", () => focusRouteStep(routeStep + 1));
    controls("route-stop")?.addEventListener("click", () => stopTrace(true));
    controls("route-from")?.addEventListener("change", () => { if (currentRoute) routeProbe(); });
    controls("route-to")?.addEventListener("change", () => { if (currentRoute) routeProbe(); });
    controls("passport-close")?.addEventListener("click", clearPassport);
    document.addEventListener("click", (event) => {
      if (!params.passport || params.passport.hidden || params.passport.contains(event.target)) return;
      if (event.target.closest?.("[data-node-id],[data-edge-id]")) return;
      clearPassport();
    });
    controls("passport-copy")?.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(location.href); params.passportStatus.textContent = ui.passport_copied; }
      catch { params.passportStatus.textContent = ui.passport_copy_manual; }
    });
    document.querySelectorAll("#diagram-depth [data-depth]").forEach((button) => button.addEventListener("click", () => setDepthMode("manual", button.dataset.depth)));
    controls("depth-auto")?.addEventListener("click", () => setDepthMode("auto"));
    document.body.dataset.depthMode ||= "auto";
    if (document.body.dataset.depthMode === "auto") applyAutomaticDepth();
    else syncDepthControls();
    controls("theme-toggle")?.addEventListener("click", toggleTheme);
    controls("visual-preset")?.addEventListener("click", cycleVisualPreset);
    controls("contrast-toggle")?.addEventListener("click", (event) => event.currentTarget.setAttribute("aria-pressed", String(document.body.classList.toggle("high-contrast"))));
    let presentationScrollLeft = null;
    let presentationScrollProgress = null;
    let presentationGeneration = 0;
    let programmaticFullscreenExit = null;
    const focusWithoutScroll = (controlId) => requestAnimationFrame(() => controls(controlId)?.focus({ preventScroll: true }));
    const exitFullscreen = () => {
      if (programmaticFullscreenExit) return programmaticFullscreenExit.promise;
      if (!document.fullscreenElement || !document.exitFullscreen) return Promise.resolve();
      const transition = { promise: null };
      programmaticFullscreenExit = transition;
      try {
        transition.promise = Promise.resolve(document.exitFullscreen()).catch(() => {
          if (programmaticFullscreenExit === transition) programmaticFullscreenExit = null;
        });
      } catch {
        if (programmaticFullscreenExit === transition) programmaticFullscreenExit = null;
        transition.promise = Promise.resolve();
      }
      return transition.promise;
    };
    const exitPresentation = async () => {
      presentationGeneration += 1;
      document.body.classList.remove("presentation");
      const scrollLeft = presentationScrollLeft;
      presentationScrollLeft = null;
      presentationScrollProgress = null;
      requestAnimationFrame(() => {
        const figure = document.querySelector("figure");
        if (figure && scrollLeft !== null) figure.scrollLeft = scrollLeft;
        controls("presentation-toggle")?.focus({ preventScroll: true });
      });
      await exitFullscreen();
    };
    controls("presentation-toggle")?.addEventListener("click", async () => {
      const enabled = !document.body.classList.contains("presentation");
      if (!enabled) { await exitPresentation(); return; }
      const generation = ++presentationGeneration;
      const figure = document.querySelector("figure");
      presentationScrollLeft = figure?.scrollLeft ?? null;
      presentationScrollProgress = figure?.scrollWidth
        ? (figure.scrollLeft + figure.clientWidth / 2) / figure.scrollWidth
        : null;
      document.body.classList.add("presentation");
      requestAnimationFrame(() => {
        if (!figure || !document.body.classList.contains("presentation") || presentationScrollProgress === null) return;
        const maxScroll = Math.max(0, figure.scrollWidth - figure.clientWidth);
        figure.scrollLeft = Math.max(0, Math.min(maxScroll, figure.scrollWidth * presentationScrollProgress - figure.clientWidth / 2));
      });
      focusWithoutScroll("presentation-exit");
      if (document.documentElement.requestFullscreen) {
        try {
          await document.documentElement.requestFullscreen();
          if (generation !== presentationGeneration && !document.body.classList.contains("presentation")) await exitFullscreen();
        }
        catch { if (generation === presentationGeneration && document.body.classList.contains("presentation")) announce(ui.presentation_fallback); }
      } else announce(ui.presentation_fallback);
    });
    controls("presentation-exit")?.addEventListener("click", exitPresentation);
    document.addEventListener("fullscreenchange", () => {
      // Consume the pending programmatic transition before reconciling newer presentation intent.
      if (programmaticFullscreenExit) {
        programmaticFullscreenExit = null;
        return;
      }
      if (!document.fullscreenElement && document.body.classList.contains("presentation")) {
        void exitPresentation();
      } else if (document.fullscreenElement && !document.body.classList.contains("presentation")) {
        void exitFullscreen();
      }
    });
    controls("zoom-in")?.addEventListener("click", () => changeZoom(0.15));
    controls("zoom-out")?.addEventListener("click", () => changeZoom(-0.15));
    controls("zoom-reset")?.addEventListener("click", () => changeZoom(1 - zoom));
    document.querySelectorAll("[data-export]").forEach((button) => button.addEventListener("click", async () => {
      try {
        const format = button.dataset.export;
        if (format === "svg-pair") { saveSvg("light"); saveSvg("dark"); }
        else if (format === "svg-auto") saveSvg("auto");
        else if (format === "webm") await saveWebm();
        else if (format === "png-copy") await copyPng();
        else if (format === "svg-light") saveSvg("light");
        else if (format === "svg-dark") saveSvg("dark");
        else await saveRaster(format);
      } catch (error) { announce(error instanceof Error ? error.message : ui.export_failed); }
    }));
    svg.addEventListener("click", (event) => {
      const node = event.target.closest("[data-node-id]");
      if (node) return focusOne(node.dataset.nodeId);
      const edge = event.target.closest("[data-edge-id]");
      if (edge) pinEdge(edge.dataset.edgeId);
    });
    svg.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const node = event.target.closest("[data-node-id]");
      const edge = event.target.closest("[data-edge-id]");
      if (node || edge) { event.preventDefault(); node ? focusOne(node.dataset.nodeId) : pinEdge(edge.dataset.edgeId); }
    });
    svg.addEventListener("mouseover", (event) => previewIntent(event.target));
    svg.addEventListener("focusin", (event) => previewIntent(event.target));
    svg.addEventListener("mouseout", (event) => { if (!event.relatedTarget || !svg.contains(event.relatedTarget)) svg.querySelectorAll(".is-intent-preview").forEach((item) => item.classList.remove("is-intent-preview")); });
    svg.addEventListener("focusout", (event) => { if (!event.relatedTarget || !svg.contains(event.relatedTarget)) svg.querySelectorAll(".is-intent-preview").forEach((item) => item.classList.remove("is-intent-preview")); });
    window.addEventListener("scroll", updateOverviewViewport, { passive: true });
    window.addEventListener("resize", updateOverviewViewport);
    figure.addEventListener("scroll", updateOverviewViewport, { passive: true });
    window.addEventListener("hashchange", handleHash);
    document.addEventListener("visibilitychange", () => { if (document.hidden) stopTrace(true); });
    document.addEventListener("keydown", (event) => {
      const target = event.target;
      const editable = target instanceof HTMLElement && (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName));
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === "Escape") {
        if (document.body.classList.contains("presentation")) { event.preventDefault(); exitPresentation(); return; }
        clearPassport();
        stopTrace(true);
      } else if (editable) return;
      else if (event.key === "/") { event.preventDefault(); params.search?.focus(); }
      else if (event.key.toLowerCase() === "s") { event.preventDefault(); cycleVisualPreset(); }
      else if (event.key.toLowerCase() === "t") { event.preventDefault(); toggleTheme(); }
      else if (event.key.toLowerCase() === "e") { event.preventDefault(); openExport(); }
      else if (event.key.toLowerCase() === "r") {
        event.preventDefault();
        if (params.routeFrom?.value && params.routeTo?.value) routeProbe();
        else params.routeFrom?.focus();
      }
      else if (event.key.toLowerCase() === "l") { event.preventDefault(); params.lens?.focus(); }
      else if (event.key.toLowerCase() === "m") { event.preventDefault(); focusOverview(); }
      else if (event.key.toLowerCase() === "f") { event.preventDefault(); controls("presentation-toggle")?.click(); }
      else if (event.key === "+" || event.key === "=") changeZoom(0.15);
      else if (event.key === "-") changeZoom(-0.15);
      else if (event.key === "0") changeZoom(1 - zoom);
      else if (event.key === "?") { const guide = document.querySelector(".viewer-guide"); if (guide) guide.open = !guide.open; }
    });
    handleHash();
    updateShareButtons();
    if (
      new URLSearchParams(location.search).get("patpat-preview") === "1"
      && location.protocol === "http:"
      && location.hostname === "127.0.0.1"
    ) {
      params.preview.hidden = false;
      let generation = "";
      const refreshPreview = async () => {
        try {
          const response = await fetch("/status", { cache: "no-store" });
          if (!response.ok) throw new Error("preview status unavailable");
          const value = await response.json();
          params.preview.textContent = value.status === "ready" ? ui.preview_current : ui.preview_last_good;
          if (value.status === "ready" && generation && value.generation !== generation) location.reload();
          if (value.status === "ready") generation = value.generation;
        } catch { params.preview.textContent = ui.preview_reconnecting; }
      };
      refreshPreview();
      setInterval(refreshPreview, 1200);
    }
  }

  function changeZoom(delta) {
    zoom = Math.min(2.5, Math.max(0.6, Number((zoom + delta).toFixed(2))));
    if (figure) figure.dataset.zoom = String(Math.round(zoom * 100));
    if (document.body.dataset.depthMode === "auto") applyAutomaticDepth();
    updateOverviewViewport();
  }

  function depthAtScale(scale) {
    if (scale < 1) return "map";
    if (scale >= 1.75) return "full";
    return "read";
  }

  function syncDepthControls() {
    const mode = document.body.dataset.depthMode || "auto";
    const depth = document.body.dataset.depth || "read";
    const automatic = controls("depth-auto");
    if (automatic) {
      const label = ui.depth_auto_status.replace("{depth}", ui[`${depth}_mode`]);
      automatic.textContent = label;
      automatic.setAttribute("aria-label", label);
      automatic.setAttribute("aria-pressed", String(mode === "auto"));
    }
    document.querySelectorAll("#diagram-depth [data-depth]").forEach((button) => {
      button.setAttribute("aria-pressed", String(mode === "manual" && button.dataset.depth === depth));
    });
  }

  function applyAutomaticDepth() {
    document.body.dataset.depth = depthAtScale(zoom);
    syncDepthControls();
  }

  function setDepthMode(mode, depth = "read") {
    document.body.dataset.depthMode = mode === "auto" ? "auto" : "manual";
    if (mode === "auto") applyAutomaticDepth();
    else {
      document.body.dataset.depth = ["map", "read", "full"].includes(depth) ? depth : "read";
      syncDepthControls();
    }
  }

  function setVisualPreset(name, notifyChange = true) {
    const preset = visualPresets.includes(name) ? name : "balanced";
    document.body.dataset.visualPreset = preset;
    const button = controls("visual-preset");
    const label = ui.visual_preset_status.replace("{preset}", ui.preset_names[preset]);
    if (button) {
      button.textContent = label;
      button.setAttribute("aria-label", label);
      button.dataset.preset = preset;
    }
    if (notifyChange) announce(label);
  }

  function cycleVisualPreset() {
    const current = visualPresets.indexOf(document.body.dataset.visualPreset || "balanced");
    setVisualPreset(visualPresets[(current + 1) % visualPresets.length]);
  }

  function toggleTheme() {
    const dark = document.body.dataset.theme !== "dark";
    document.body.dataset.theme = dark ? "dark" : "light";
    controls("theme-toggle")?.setAttribute("aria-pressed", String(dark));
  }

  function openExport() {
    const panel = controls("export-tools");
    if (!panel) return;
    panel.open = true;
    panel.scrollIntoView({ block: "nearest" });
    panel.querySelector("button:not(:disabled)")?.focus();
  }

  function focusOverview() {
    if (!params.overview) return;
    params.overview.scrollIntoView({ block: "center" });
    params.overview.querySelector("[tabindex=\"0\"]")?.focus();
  }

  function centerMobileCanvas() {
    if (location.hash || !window.matchMedia("(max-width: 760px)").matches) return;
    const figure = document.querySelector("figure");
    if (!figure) return;
    const firstNode = figure.querySelector("[data-node-id]");
    requestAnimationFrame(() => {
      const maxScroll = Math.max(0, figure.scrollWidth - figure.clientWidth);
      if (!firstNode) {
        figure.scrollLeft = maxScroll / 2;
        return;
      }
      const figureBounds = figure.getBoundingClientRect();
      const nodeBounds = firstNode.getBoundingClientRect();
      const nodeCenter = nodeBounds.left - figureBounds.left + figure.scrollLeft + nodeBounds.width / 2;
      figure.scrollLeft = Math.max(0, Math.min(maxScroll, nodeCenter - figure.clientWidth / 2));
    });
  }

  document.body.dataset.depth ||= "read";
  bind();
  centerMobileCanvas();
  document.body.dataset.viewerReady = "true";
  if (
    new URLSearchParams(location.search).has("patpat-browser-check")
    || document.querySelector('meta[name="patpat-browser-check"]')?.content === "1"
  ) {
    document.documentElement.dataset.patpatBrowserViewport = String(window.innerWidth);
    document.documentElement.dataset.patpatBrowserViewportHeight = String(window.innerHeight);
    document.documentElement.dataset.patpatBrowserScrollWidth = String(document.documentElement.scrollWidth);
  }
})();
