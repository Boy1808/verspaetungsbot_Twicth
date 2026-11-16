// Gemeinsame Hilfsfunktionen für beide Seiten
function deutscheZeit(iso, mitJahr = false) {
  if (!iso) return "–";
  return new Date(iso).toLocaleString("de-DE", {
    timeZone: "Europe/Berlin",
    day: "2-digit", month: "2-digit", ...(mitJahr ? { year: "numeric" } : {}),
    hour: "2-digit", minute: "2-digit",
  }) + " Uhr";
}

function klasse(min) {
  if (min === null || min === undefined) return "leer";
  if (min < -5) return "zu-frueh";
  if (min <= 5) return "puenktlich";
  if (min <= 15) return "etwas";
  return "azb";
}

function minutenText(min, lang = false) {
  if (min === null || min === undefined) return "–";
  const wert = Math.round(min);
  if (lang) {
    if (wert < 0) return `${-wert} Min. zu früh`;
    if (wert === 0) return "auf die Minute";
    return `${wert} Min. zu spät`;
  }
  return (wert > 0 ? "+" : wert < 0 ? "−" : "±") + Math.abs(wert) + " Min.";
}

function prozent(p) {
  return p === null || p === undefined ? "–" : `${Math.round(p)} %`;
}

function esc(text) {
  const d = document.createElement("div");
  d.textContent = text ?? "";
  return d.innerHTML;
}