const yearSelect = document.querySelector("#yearSelect");
const tabs = document.querySelectorAll(".tab");
const panels = {
  new: document.querySelector("#newPanel"),
  view: document.querySelector("#viewPanel"),
  edit: document.querySelector("#editPanel"),
};
const entryForm = document.querySelector("#entryForm");
const recordsBody = document.querySelector("#recordsBody");
const totalHlf = document.querySelector("#totalHlf");
const totalReceipt = document.querySelector("#totalReceipt");
const personSelect = document.querySelector("#personSelect");
const entrySelect = document.querySelector("#entrySelect");
const orderSelect = document.querySelector("#orderSelect");
const editArea = document.querySelector("#editArea");
const toast = document.querySelector("#toast");
const warningDialog = document.querySelector("#warningDialog");
const warningText = document.querySelector("#warningText");
const cancelWarning = document.querySelector("#cancelWarning");
const confirmWarning = document.querySelector("#confirmWarning");

let pendingSave = null;
let currentPersonRecords = [];
const streetTypes = ["utca", "tér", "körút", "út", "sugárút", "köz", "sor", "park", "lakótelep", "dűlő", "tanya", "major", "egyéb"];
const locations = window.HUNGARY_LOCATIONS || {};

function formatMoney(value) {
  return new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 0 }).format(Number(value || 0)) + " Ft";
}

function formatNumber(value) {
  return new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 3 }).format(Number(value || 0));
}

function formatHlf(value) {
  return new Intl.NumberFormat("hu-HU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Number(value || 0));
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function streetTypeOptions(selected = "") {
  return `<option value="">Válassz</option>` + streetTypes
    .map((type) => `<option ${type === selected ? "selected" : ""}>${esc(type)}</option>`)
    .join("");
}

function datalistOptions(values) {
  return values
    .map((value) => `<option value="${esc(value)}"></option>`)
    .join("");
}

function citiesForCounty(county) {
  return locations[county] || [];
}

function fillCityList(datalist, county) {
  datalist.innerHTML = citiesForCounty(county)
    .map((city) => `<option value="${esc(city.name)}"></option>`)
    .join("");
}

function zipMatches(zip) {
  const cleanZip = String(zip || "").trim();
  if (!cleanZip) return [];
  const matches = [];
  Object.entries(locations).forEach(([county, cities]) => {
    cities.forEach((city) => {
      if (city.zips.includes(cleanZip)) {
        matches.push({ county, name: city.name, zips: city.zips });
      }
    });
  });
  return matches;
}

function fillCityListFromMatches(datalist, matches) {
  datalist.innerHTML = matches
    .map((city) => `<option value="${esc(city.name)}"></option>`)
    .join("");
}

function wireAddressControls(root) {
  root.querySelectorAll("input[name='kozterulet_jellege'][list]").forEach((input) => {
    const list = input.ownerDocument.getElementById(input.getAttribute("list"));
    if (list) list.innerHTML = datalistOptions(streetTypes);
  });

  root.querySelectorAll(".county-select").forEach((countyInput) => {
    const countyList = countyInput.ownerDocument.getElementById(countyInput.getAttribute("list"));
    if (countyList) countyList.innerHTML = datalistOptions(Object.keys(locations));
    const form = countyInput.closest("form");
    const cityInput = form.querySelector(".city-input");
    const datalist = cityInput.ownerDocument.getElementById(cityInput.getAttribute("list"));
    const zipInput = form.elements.iranyitoszam;
    fillCityList(datalist, countyInput.value);
    countyInput.addEventListener("change", () => {
      cityInput.value = "";
      zipInput.value = "";
      fillCityList(datalist, countyInput.value);
    });
    cityInput.addEventListener("change", () => {
      const city = citiesForCounty(countyInput.value).find((item) => item.name === cityInput.value);
      if (city && city.zips.length === 1) {
        zipInput.value = city.zips[0];
      }
    });
    zipInput.addEventListener("input", () => {
      const matches = zipMatches(zipInput.value);
      if (!matches.length) return;
      fillCityListFromMatches(datalist, matches);

      const counties = [...new Set(matches.map((match) => match.county))];
      const cityNames = [...new Set(matches.map((match) => match.name))];
      if (counties.length === 1) {
        countyInput.value = counties[0];
      }
      if (cityNames.length === 1) {
        cityInput.value = cityNames[0];
      }
    });
  });
}

function showToast(text) {
  toast.textContent = text;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2300);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok && response.status !== 409) {
    throw new Error(data.error || "Hiba történt.");
  }
  return { response, data };
}

function selectedYear() {
  return Number(yearSelect.value);
}

function calculateInto(form) {
  const kezdo = Number(form.elements.kezdo.value || 0);
  const zaro = Number(form.elements.zaro.value || 0);
  const szesz = Number(form.elements.szesz_foka.value || 0);
  const liter = Math.max(0, zaro - kezdo);
  const hlf = Math.round(((liter * szesz) / 100) * 10) / 10;
  form.elements.mennyiseg_literben.value = liter ? liter.toFixed(3) : "";
  form.elements.hektoliterfokban.value = hlf ? hlf.toFixed(1) : "";
  form.elements.nyugtaertek.value = hlf ? Math.round(hlf * 1400) : "";
}

function payloadFromForm(form) {
  calculateInto(form);
  return Object.fromEntries(new FormData(form).entries());
}

function wireCalculation(form) {
  ["kezdo", "zaro", "szesz_foka"].forEach((name) => {
    form.elements[name].addEventListener("input", () => calculateInto(form));
  });
}

function showWarnings(warnings, onConfirm) {
  const parts = warnings.map((warning) => {
    if (warning.type === "possible_existing_client") {
      const names = warning.matches
        .map((match) => `<li>${match.nev}: egyezés: ${match.same.join(", ")}</li>`)
        .join("");
      return `<p><strong>Lehet, hogy ez már meglévő ügyfél.</strong></p><ul>${names}</ul><p>Ha ez új főzés ugyanannak vagy mégis helyes adat, menthető.</p>`;
    }
    if (warning.type === "high_hektoliter") {
      return `<p><strong>Hektoliterfok: ${formatHlf(warning.value)}</strong></p><p>Ez 43 vagy több, ellenőrizd mentés előtt.</p>`;
    }
    return `<p>${warning.message}</p>`;
  });
  warningText.innerHTML = parts.join("");
  pendingSave = onConfirm;
  warningDialog.showModal();
}

cancelWarning.addEventListener("click", () => {
  pendingSave = null;
  warningDialog.close();
});

confirmWarning.addEventListener("click", async () => {
  const save = pendingSave;
  pendingSave = null;
  warningDialog.close();
  if (save) await save();
});

async function loadYears() {
  const { data } = await api("/api/years");
  const now = new Date().getFullYear();
  const years = [...new Set([now, ...data.years])].sort((a, b) => b - a);
  yearSelect.innerHTML = years.map((year) => `<option value="${year}">${year}</option>`).join("");
}

async function loadRecords() {
  const { data } = await api(`/api/records?year=${selectedYear()}&order=${orderSelect.value}`);
  totalHlf.textContent = formatHlf(data.totals.hektoliterfokban);
  totalReceipt.textContent = formatMoney(data.totals.nyugtaertek);
  recordsBody.innerHTML = data.records.length
    ? data.records
        .map(
          (row) => `
            <tr>
              <td>${esc(row.nev)}</td>
              <td>${esc(row.adoszam)}</td>
              <td>${esc(row.allando_lakcim)}</td>
              <td>${esc(row.kozterulet_jellege || "")}</td>
              <td>${esc(row.fozes_start)} - ${esc(row.fozes_end)}</td>
              <td>${formatNumber(row.mennyiseg_literben)}</td>
              <td class="${row.hektoliterfokban >= 43 ? "high" : ""}">${formatHlf(row.hektoliterfokban)}</td>
              <td>${formatMoney(row.nyugtaertek)}</td>
            </tr>
          `
        )
        .join("")
    : `<tr><td colspan="8">Nincs még adat ebben az évben.</td></tr>`;
}

async function loadPeople() {
  const { data } = await api(`/api/people?year=${selectedYear()}`);
  personSelect.innerHTML = data.people.length
    ? `<option value="">Válassz személyt</option>` + data.people.map((name) => `<option>${esc(name)}</option>`).join("")
    : `<option value="">Nincs személy ebben az évben</option>`;
  entrySelect.innerHTML = `<option value="">Előbb válassz személyt</option>`;
  currentPersonRecords = [];
  editArea.innerHTML = "";
}

function editFormHtml(row) {
  return `
    <article class="edit-card">
      <h3>${esc(row.nev)} - ${esc(row.fozes_start)}</h3>
      <form class="edit-form" data-id="${row.id}">
        <label>Név<input name="nev" value="${esc(row.nev)}"></label>
        <label>Azonosító szám<input name="azonosito_szam" value="${esc(row.azonosito_szam)}"></label>
        <label>Adószám<input name="adoszam" value="${esc(row.adoszam)}"></label>
        <label>Irányítószám<input name="iranyitoszam" inputmode="numeric" value="${esc(row.iranyitoszam || "")}"></label>
        <label>Megye<input name="megye" class="county-select" list="countyListEdit${row.id}" value="${esc(row.megye || "")}"><datalist id="countyListEdit${row.id}"></datalist></label>
        <label>Város<input name="varos" class="city-input" list="cityListEdit${row.id}" value="${esc(row.varos || "")}"><datalist id="cityListEdit${row.id}"></datalist></label>
        <label>Közterület neve<input name="kozterulet_neve" value="${esc(row.kozterulet_neve || "")}"></label>
        <label>Közterület jellege<input name="kozterulet_jellege" list="streetTypeListEdit${row.id}" value="${esc(row.kozterulet_jellege || "")}"><datalist id="streetTypeListEdit${row.id}"></datalist></label>
        <label>Közterület száma<input name="kozterulet_szama" value="${esc(row.kozterulet_szama || "")}"></label>
        <label>Emelet<input name="emelet" value="${esc(row.emelet || "")}"></label>
        <label>Ajtószám<input name="ajtoszam" value="${esc(row.ajtoszam || "")}"></label>
        <label>Cefre átvételi azonosító<input name="cefre_atveteli_azonosito" value="${esc(row.cefre_atveteli_azonosito)}"></label>
        <label>Főzés kezdete<input name="fozes_start" type="datetime-local" value="${esc(row.fozes_start)}"></label>
        <label>Főzés vége<input name="fozes_end" type="datetime-local" value="${esc(row.fozes_end)}"></label>
        <label>Kezdő óraállás<input name="kezdo" type="number" step="0.001" value="${esc(row.kezdo)}"></label>
        <label>Záró óraállás<input name="zaro" type="number" step="0.001" value="${esc(row.zaro)}"></label>
        <label>Szesz foka<input name="szesz_foka" type="number" step="0.1" value="${esc(row.szesz_foka)}"></label>
        <label>Mennyiség literben<input name="mennyiseg_literben" readonly value="${esc(row.mennyiseg_literben)}"></label>
        <label>Hektoliterfokban<input name="hektoliterfokban" readonly value="${esc(row.hektoliterfokban)}"></label>
        <label>Kiadás dátuma<input name="kiadas_datuma" type="date" value="${esc(row.kiadas_datuma)}"></label>
        <label>Nyugtaérték<input name="nyugtaertek" readonly value="${esc(row.nyugtaertek)}"></label>
        <div class="actions wide">
          <button class="primary" type="submit">Módosítás mentése</button>
          <button class="danger delete-entry" type="button">Bejegyzés törlése</button>
        </div>
      </form>
    </article>
  `;
}

async function loadPersonRecords() {
  const name = personSelect.value;
  if (!name) {
    entrySelect.innerHTML = `<option value="">Előbb válassz személyt</option>`;
    currentPersonRecords = [];
    editArea.innerHTML = "";
    return;
  }
  const { data } = await api(`/api/person?year=${selectedYear()}&nev=${encodeURIComponent(name)}`);
  currentPersonRecords = data.records;
  entrySelect.innerHTML = currentPersonRecords.length
    ? `<option value="">Válassz bejegyzést</option>` +
      currentPersonRecords
        .map(
          (row) =>
            `<option value="${row.id}">${esc(row.fozes_start)} - ${formatNumber(row.mennyiseg_literben)} liter, ${formatHlf(row.hektoliterfokban)} hlf</option>`
        )
        .join("")
    : `<option value="">Nincs bejegyzés</option>`;
  editArea.innerHTML = "";
}

function showSelectedEntry() {
  const id = Number(entrySelect.value);
  const row = currentPersonRecords.find((item) => item.id === id);
  if (!row) {
    editArea.innerHTML = "";
    return;
  }
  editArea.innerHTML = editFormHtml(row);
  const form = editArea.querySelector("form");
  wireAddressControls(form);
  wireCalculation(form);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await saveEdit(form);
  });
  form.querySelector(".delete-entry").addEventListener("click", async () => {
    await deleteEntry(form.dataset.id);
  });
}

async function saveNew(force = false) {
  const body = { ...payloadFromForm(entryForm), year: selectedYear(), force };
  const { response, data } = await api("/api/records", { method: "POST", body: JSON.stringify(body) });
  if (response.status === 409) {
    showWarnings(data.warnings, () => saveNew(true));
    return;
  }
  entryForm.reset();
  if (data.year) {
    await loadYears();
    yearSelect.value = data.year;
  }
  await refreshAll();
  showToast("Mentve.");
}

async function saveEdit(form, force = false) {
  const id = form.dataset.id;
  const body = { ...payloadFromForm(form), year: selectedYear(), force };
  const { response, data } = await api(`/api/records/${id}`, { method: "PUT", body: JSON.stringify(body) });
  if (response.status === 409) {
    showWarnings(data.warnings, () => saveEdit(form, true));
    return;
  }
  await refreshAll();
  showToast("Módosítás mentve.");
}

async function deleteEntry(id) {
  const ok = window.confirm("Biztosan törlöd ezt a bejegyzést? Ezt nem lehet visszavonni.");
  if (!ok) return;
  await api(`/api/records/${id}?year=${selectedYear()}`, { method: "DELETE" });
  await refreshAll();
  showToast("Bejegyzés törölve.");
}

async function refreshAll() {
  await loadRecords();
  await loadPeople();
}

tabs.forEach((tab) => {
  tab.addEventListener("click", async () => {
    tabs.forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    Object.values(panels).forEach((panel) => panel.classList.remove("active-panel"));
    panels[tab.dataset.tab].classList.add("active-panel");
    if (tab.dataset.tab === "edit") await loadPeople();
  });
});

yearSelect.addEventListener("change", refreshAll);
personSelect.addEventListener("change", loadPersonRecords);
entrySelect.addEventListener("change", showSelectedEntry);
orderSelect.addEventListener("change", loadRecords);
entryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await saveNew();
});
entryForm.addEventListener("reset", () => setTimeout(() => calculateInto(entryForm), 0));
wireCalculation(entryForm);
wireAddressControls(entryForm);

loadYears().then(refreshAll).catch((error) => showToast(error.message));
