/* UK campaign map: renders a real open-source SVG of the United Kingdom and
   colours its 12 NUTS1 regions. Game counties (16 on easy/medium, 32 split
   halves on hard) aggregate onto the NUTS1 path that contains them — the
   dominant owner paints the region. County ids match backend/config.

   Map source: https://mapsvg.com/maps/united-kingdom (MapSVG),
   licensed CC0 1.0: https://creativecommons.org/publicdomain/zero/1.0/ */
"use strict";

const UKMAP = {
  SVG_URL: "static/map/united-kingdom.svg",
  DEFAULT_FILL: "#22314f",
  _svgText: null,

  // The 12 colourable regions, in reveal order (roughly north to south).
  NUTS1: [
    { id: "GB-UKM", name: "Scotland" },
    { id: "GB-UKN", name: "Northern Ireland" },
    { id: "GB-UKC", name: "North East" },
    { id: "GB-UKD", name: "North West" },
    { id: "GB-UKE", name: "Yorkshire & the Humber" },
    { id: "GB-UKF", name: "East Midlands" },
    { id: "GB-UKG", name: "West Midlands" },
    { id: "GB-UKH", name: "East of England" },
    { id: "GB-UKI", name: "Greater London" },
    { id: "GB-UKJ", name: "South East" },
    { id: "GB-UKK", name: "South West" },
    { id: "GB-UKL", name: "Wales" },
  ],

  // Territories that are on the map but are not up for election.
  FOREIGN: ["GG", "JE", "IM", "IE"],

  // game county id -> NUTS1 path id. Covers easy/medium counties and the
  // hard-mode split halves.
  COUNTY_MAP: {
    // easy/medium
    cornwall_devon: "GB-UKK",
    lancashire_cumbria: "GB-UKD",
    wales: "GB-UKL",
    scotland: "GB-UKM",
    north_east: "GB-UKC",
    yorkshire: "GB-UKE",
    east_midlands: "GB-UKF",
    west_midlands: "GB-UKG",
    east_anglia: "GB-UKH",
    essex: "GB-UKH",
    london: "GB-UKI",
    thames_valley: "GB-UKJ",
    hampshire: "GB-UKJ",
    sussex: "GB-UKJ",
    kent: "GB-UKJ",
    northern_ireland: "GB-UKN",
    // hard-mode split halves
    cornwall: "GB-UKK",
    devon: "GB-UKK",
    lancashire: "GB-UKD",
    cumbria: "GB-UKD",
    north_wales: "GB-UKL",
    south_wales: "GB-UKL",
    lowlands_scot: "GB-UKM",
    highlands_scot: "GB-UKM",
    tyneside: "GB-UKC",
    county_durham: "GB-UKC",
    north_yorkshire: "GB-UKE",
    south_yorkshire: "GB-UKE",
    nottinghamshire: "GB-UKF",
    lincolnshire: "GB-UKF",
    birmingham: "GB-UKG",
    shropshire: "GB-UKG",
    norfolk: "GB-UKH",
    suffolk: "GB-UKH",
    southend_essex: "GB-UKH",
    rural_essex: "GB-UKH",
    inner_london: "GB-UKI",
    outer_london: "GB-UKI",
    oxfordshire: "GB-UKJ",
    berkshire: "GB-UKJ",
    north_hampshire: "GB-UKJ",
    south_hampshire: "GB-UKJ",
    east_sussex: "GB-UKJ",
    west_sussex: "GB-UKJ",
    west_kent: "GB-UKJ",
    east_kent: "GB-UKJ",
    belfast: "GB-UKN",
    ulster_countryside: "GB-UKN",
  },

  nutsFor(countyId) {
    return UKMAP.COUNTY_MAP[countyId] || null;
  },

  nutsName(nutsId) {
    const n = UKMAP.NUTS1.find((n) => n.id === nutsId);
    return n ? n.name : nutsId;
  },

  _postProcess(container) {
    const svg = container.querySelector("svg");
    if (!svg) throw new Error("map file contains no svg");
    const w = parseFloat(svg.getAttribute("width"));
    const h = parseFloat(svg.getAttribute("height"));
    if (!svg.getAttribute("viewBox") && w && h) {
      svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
    }
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    svg.classList.add("ukmap");
    for (const id of UKMAP.FOREIGN) {
      const p = svg.querySelector(`[id="${id}"]`);
      if (p) p.classList.add("foreign");
    }
    return svg;
  },

  // Fetch (once) and inject the map into a container. Resolves with the svg.
  async mount(container) {
    if (!UKMAP._svgText) {
      const res = await fetch(UKMAP.SVG_URL);
      if (!res.ok) throw new Error(`map failed to load (${res.status})`);
      UKMAP._svgText = await res.text();
    }
    container.innerHTML = UKMAP._svgText;
    return UKMAP._postProcess(container);
  },

  // colors/titles keyed by NUTS1 id; highlight is a NUTS1 id or null.
  apply(container, colors = {}, highlight = null, titles = {}) {
    const svg = container.querySelector("svg");
    if (!svg) return;
    for (const { id, name } of UKMAP.NUTS1) {
      const p = svg.querySelector(`[id="${id}"]`);
      if (!p) continue;
      p.style.fill = colors[id] || UKMAP.DEFAULT_FILL;
      p.classList.toggle("highlight", id === highlight);
      const text = titles[id] || name;
      p.setAttribute("title", text);
      let t = p.querySelector("title");
      if (!t) {
        t = document.createElementNS("http://www.w3.org/2000/svg", "title");
        p.appendChild(t);
      }
      t.textContent = text;
    }
  },
};
