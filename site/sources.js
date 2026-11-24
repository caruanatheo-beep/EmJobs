"use strict";
// "Entreprises" tab: the companies Em Jobs reads, grouped by sector.
(() => {
  const byId = id => document.getElementById(id);
  let catalog = [], category = "", loaded = false, loading = false;
  function renderCategories() {
    const group = byId("source-categories");
    const sectors = [...new Set(catalog.map(source => source.sector))].sort((a, b) => a.localeCompare(b, "fr"));
    const buttons = [["", "Tous"], ...sectors.map(sector => [sector, sector])].map(([value, label]) => {
      const button = document.createElement("button");
      button.type = "button"; button.dataset.category = value; button.textContent = label;
      button.addEventListener("click", () => { category = value; renderSources(); });
      return button;
    });
    group.replaceChildren(...buttons);
  }
  function renderSources() {
    const terms = normalize(byId("source-search").value).split(/\s+/).filter(Boolean);
    const selected = catalog.filter(source => (!category || source.sector === category)
      && terms.every(term => normalize(source.name + " " + source.sector).includes(term)));
    const fragment = document.createDocumentFragment();
    for (const source of selected) {
      const url = safeLink(source.url); if (!url) continue;
      const card = byId("source-template").content.firstElementChild.cloneNode(true);
      const title = card.querySelector("h3");
      title.textContent = source.name; title.title = source.name;
      if (source.ai) {
        const spark = document.createElement("span"); spark.className = "source-ai";
        spark.textContent = " ✦"; spark.title = "IA au cœur du produit"; title.append(spark);
      }
      // Link-only career sites cannot be read automatically: they are listed to visit directly.
      const offers = source.link_only === true ? " · site à consulter"
        : Number.isInteger(source.count) && source.count > 0 ? ` · ${source.count} offre${source.count > 1 ? "s" : ""}` : "";
      card.querySelector(".source-type").textContent = source.sector + offers;
      const link = card.querySelector(".source-link"); link.href = url;
      link.setAttribute("aria-label", "Consulter le site carrière : " + source.name);
      const initials = card.querySelector(".initials"), image = card.querySelector("img");
      initials.textContent = source.name.split(/\s+/).slice(0, 2).map(word => word[0] || "").join("").toUpperCase();
      image.hidden = true;
      if (/^logos\/[a-zA-Z0-9._-]+\.png$/.test(source.logo)) {
        image.onload = () => { image.hidden = false; initials.hidden = true; }; image.src = source.logo;
      }
      fragment.append(card);
    }
    byId("source-list").replaceChildren(fragment);
    byId("source-count").textContent = selected.length + " entreprise" + (selected.length > 1 ? "s" : "") + " suivie" + (selected.length > 1 ? "s" : "");
    byId("sources-message").textContent = selected.length ? "" : "Aucune entreprise ne correspond à cette recherche.";
    for (const button of byId("source-categories").querySelectorAll("button")) button.setAttribute("aria-pressed", String(button.dataset.category === category));
  }
  async function loadSources() {
    if (loaded || loading) return;
    loading = true;
    try {
      const response = await fetch("sources.json", {cache: "no-cache", credentials: "omit"});
      if (!response.ok) throw new Error("catalog");
      const data = await response.json();
      if (!Array.isArray(data.sources)) throw new Error("catalog");
      catalog = data.sources;
      loaded = true; renderCategories(); renderSources();
    } catch {
      byId("source-count").textContent = "Entreprises";
      byId("sources-message").textContent = "La liste ne peut pas être chargée pour le moment. Réessaie en revenant sur cet onglet.";
    } finally { loading = false; }
  }
  function showView() {
    const sources = ["#sources", "#proposer-source"].includes(location.hash);
    byId("offers-view").hidden = sources; byId("sources-view").hidden = !sources;
    byId("nav-offers").toggleAttribute("aria-current", !sources);
    byId("nav-sources").toggleAttribute("aria-current", sources);
    byId(sources ? "nav-sources" : "nav-offers").setAttribute("aria-current", "page");
    document.title = (sources ? "Entreprises" : "Offres") + " · Em Jobs";
    if (openFilter) openFilter.close();
    if (typeof closeSheet === "function") closeSheet(false);
    if (sources) loadSources();
  }
  byId("suggest-source").addEventListener("click", () => byId("proposer-source").scrollIntoView({block: "start"}));
  byId("source-search").addEventListener("input", renderSources);
  // Without a repository link (local preview), the suggestion button is hidden.
  if (!byId("suggest-link")) byId("suggest-source").hidden = true;
  window.addEventListener("hashchange", showView); showView();
  if ("IntersectionObserver" in window) {
    new IntersectionObserver(entries => {
      byId("suggest-source").classList.toggle("is-form-visible", entries.some(entry => entry.isIntersecting));
    }).observe(byId("proposer-source"));
  }
})();
