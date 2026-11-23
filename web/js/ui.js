// ui.js — ortak arayüz yardımcıları (DOM kurucular ve biçimlendiriciler)
const SVG_NS = "http://www.w3.org/2000/svg";

export function h(etiket, ozellik = {}, ...cocuklar) {
  const e = document.createElement(etiket);
  for (const [anahtar, deger] of Object.entries(ozellik || {})) {
    if (deger === undefined || deger === null || deger === false) continue;
    if (anahtar === "class") e.className = deger;
    else if (anahtar === "text") e.textContent = deger;
    else if (anahtar === "html") e.innerHTML = deger;
    else if (anahtar === "dataset") Object.assign(e.dataset, deger);
    else if (anahtar === "style" && typeof deger === "object") Object.assign(e.style, deger);
    else if (anahtar.startsWith("on") && typeof deger === "function")
      e.addEventListener(anahtar.slice(2).toLowerCase(), deger);
    else e.setAttribute(anahtar, deger === true ? "" : deger);
  }
  for (const c of cocuklar.flat(3)) {
    if (c === null || c === undefined || c === false) continue;
    e.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return e;
}

const IKONLAR = {
  panel: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
  kitap: '<path d="M4 5.5A2.5 2.5 0 016.5 3H20v15.5H6.5A2.5 2.5 0 004 21z"/><path d="M4 18.5V5.5"/>',
  takvim: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/>',
  grafik: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  sohbet: '<path d="M21 12a8 8 0 01-8 8H8l-4 3v-6.5A8 8 0 1121 12z"/>',
  ayar: '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.7 1.7 0 00.34 1.87l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.7 1.7 0 00-1.87-.34 1.7 1.7 0 00-1.03 1.56V21a2 2 0 11-4 0v-.09A1.7 1.7 0 007.2 19.4a1.7 1.7 0 00-1.87.34l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.7 1.7 0 003 15a1.7 1.7 0 00-1.56-1.03H1.3a2 2 0 110-4h.09A1.7 1.7 0 003 8.94 1.7 1.7 0 002.66 7.07l-.06-.06a2 2 0 112.83-2.83l.06.06A1.7 1.7 0 007.36 4.6H7.4a1.7 1.7 0 001.03-1.56V3a2 2 0 114 0v.09a1.7 1.7 0 001.03 1.56 1.7 1.7 0 001.87-.34l.06-.06a2 2 0 112.83 2.83l-.06.06A1.7 1.7 0 0019.4 9v.04a1.7 1.7 0 001.56 1.03H21a2 2 0 110 4h-.09A1.7 1.7 0 0019.4 15z"/>',
  tik: '<path d="M20 6L9 17l-5-5"/>',
  yildiz: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
  ok: '<path d="M9 6l6 6-6 6"/>',
  arti: '<path d="M12 5v14M5 12h14"/>',
  yukleniyor: '<path d="M21 12a9 9 0 11-6.2-8.56"/>',
  uyari: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9L2.5 17a2 2 0 001.7 3h15.6a2 2 0 001.7-3L13.7 3.9a2 2 0 00-3.4 0z"/>',
  kalem: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/>',
  hedef: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4"/>',
  pusula: '<path d="M12 2l8 5v10l-8 5-8-5V7z"/><path d="M12 8l3 7-3-1.6L9 15z"/>',
  okul: '<path d="M3 21h18"/><path d="M5 21V9l7-4 7 4v12"/><path d="M9 21v-6h6v6"/>',
};

export function ikon(ad, boyut = 18) {
  const s = document.createElementNS(SVG_NS, "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("width", boyut);
  s.setAttribute("height", boyut);
  s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "1.8");
  s.setAttribute("stroke-linecap", "round");
  s.setAttribute("stroke-linejoin", "round");
  s.setAttribute("aria-hidden", "true");
  s.innerHTML = IKONLAR[ad] || "";
  return s;
}

/** Dolu yıldız ikonu (güven göstergesi) */
export function doluYildiz(boyut = 17) {
  const s = document.createElementNS(SVG_NS, "svg");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("width", boyut);
  s.setAttribute("height", boyut);
  s.setAttribute("fill", "currentColor");
  s.innerHTML = IKONLAR.yildiz;
  return s;
}

export function rozet(metin, tur = "") {
  return h("span", { class: `rozet ${tur}`.trim(), text: metin });
}

export function tarihTr(iso) {
  if (!iso) return "";
  const [y, a, g] = iso.split("-");
  const aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
  return `${Number(g)} ${aylar[Number(a) - 1]} ${y}`;
}

export function kisaTarih(iso) {
  if (!iso) return "";
  const [, a, g] = iso.split("-");
  return `${Number(g)}.${String(a).padStart(2, "0")}`;
}

export function dakikaMetni(dk) {
  dk = Math.max(0, Math.round(dk || 0));
  if (dk < 60) return `${dk} dk`;
  const saat = Math.floor(dk / 60);
  const kalan = dk % 60;
  return kalan ? `${saat} sa ${kalan} dk` : `${saat} sa`;
}

export function yuzde(parca, toplam) {
  if (!toplam) return 0;
  return Math.round((parca / toplam) * 100);
}

export function halka(yuzdeDeger, boyut = 84) {
  const yaricap = 34;
  const cevre = 2 * Math.PI * yaricap;
  let dolu = (Math.min(100, Math.max(0, yuzdeDeger)) / 100) * cevre;
  // Çok küçük değerlerde yay tamamen kaybolmasın
  if (yuzdeDeger > 0 && dolu < 11) dolu = 11;
  const s = document.createElementNS(SVG_NS, "svg");
  s.setAttribute("class", "halka");
  s.setAttribute("width", boyut);
  s.setAttribute("height", boyut);
  s.setAttribute("viewBox", "0 0 84 84");
  s.innerHTML = `
    <defs><linearGradient id="halkaGecis" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ea580c"/><stop offset="100%" stop-color="#f59e0b"/>
    </linearGradient></defs>
    <circle class="iz" cx="42" cy="42" r="${yaricap}"/>
    <circle class="dolu" cx="42" cy="42" r="${yaricap}"
      stroke-dasharray="${cevre.toFixed(1)}"
      stroke-dashoffset="${(cevre - dolu).toFixed(1)}"/>`;
  return s;
}

export function cubuk(yuzdeDeger, renk) {
  const span = h("span", { style: { width: `${Math.min(100, yuzdeDeger)}%` } });
  if (renk) span.style.background = renk;
  return h("div", { class: "cubuk" }, span);
}

let bildirimZaman;
export function bildir(mesaj, tur = "") {
  const kutu = document.getElementById("bildirim");
  if (!kutu) return;
  kutu.textContent = mesaj;
  kutu.className = `bildirim gorunur ${tur}`.trim();
  clearTimeout(bildirimZaman);
  bildirimZaman = setTimeout(() => {
    kutu.className = "bildirim";
  }, 3200);
}

export function yukleniyorKarti(mesaj = "Yükleniyor…") {
  return h(
    "div",
    { class: "kart", style: { display: "grid", placeItems: "center", gap: "10px", padding: "40px" } },
    h("div", { class: "ibre" }),
    h("p", { text: mesaj, style: { color: "#6b7280", fontSize: "13px" } })
  );
}

export function bosDurum(baslik, aciklama = "") {
  return h("div", { class: "bos" }, h("b", { text: baslik }), aciklama);
}

export function hataKarti(hata) {
  return h(
    "div",
    { class: "kart", style: { borderColor: "#f3c6c6", background: "#fff7f7" } },
    h("h2", { text: "Bir sorun oluştu", style: { fontSize: "14px", marginBottom: "6px" } }),
    h("p", { text: hata?.message || String(hata), style: { fontSize: "13px", color: "#a01b1b" } })
  );
}

/** Bir satırdaki **kalın**, *eğik* ve `kod` işaretlerini DOM düğümlerine çevirir */
function satirParcala(metin) {
  const parca = document.createDocumentFragment();
  const desen = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\n]+\*|_[^_\n]+_)/g;
  let son = 0;
  for (const eslesme of metin.matchAll(desen)) {
    if (eslesme.index > son) parca.append(document.createTextNode(metin.slice(son, eslesme.index)));
    const p = eslesme[0];
    if (p.startsWith("**") || p.startsWith("__")) parca.append(h("b", { text: p.slice(2, -2) }));
    else if (p.startsWith("`")) parca.append(h("code", { text: p.slice(1, -1) }));
    else parca.append(h("em", { text: p.slice(1, -1) }));
    son = eslesme.index + p.length;
  }
  if (son < metin.length) parca.append(document.createTextNode(metin.slice(son)));
  return parca;
}

/** Sunucudan gelen hafif Markdown metnini güvenli biçimde çizer */
export function metinBalonu(metin) {
  const kutu = h("div", { class: "balon" });
  const satirlar = String(metin ?? "").replace(/\r/g, "").split("\n");
  let liste = null; // açık olan <ul>/<ol>

  const listeyiKapat = () => { liste = null; };

  satirlar.forEach((ham) => {
    const satir = ham.replace(/\s+$/, "");
    if (!satir.trim()) {
      listeyiKapat();
      kutu.append(h("div", { class: "balon-bosluk" }));
      return;
    }

    // ### Başlık
    const baslik = satir.match(/^(#{1,6})\s+(.*)$/);
    if (baslik) {
      listeyiKapat();
      const seviye = Math.min(2, Math.max(0, baslik[1].length - 1)); // # -> sv0, ## -> sv1, ###+ -> sv2
      kutu.append(h("div", { class: `balon-baslik sv${seviye}` }, satirParcala(baslik[2])));
      return;
    }

    // --- ayırıcı
    if (/^([-*_])\1{2,}$/.test(satir.trim())) {
      listeyiKapat();
      kutu.append(h("div", { class: "balon-bosluk" }));
      return;
    }

    // > alıntı
    const alinti = satir.match(/^>\s?(.*)$/);
    if (alinti) {
      listeyiKapat();
      kutu.append(h("div", { class: "balon-alinti" }, satirParcala(alinti[1])));
      return;
    }

    // - madde imi
    const madde = satir.match(/^\s*[-*•]\s+(.*)$/);
    if (madde) {
      if (!liste || liste.tagName !== "UL") {
        liste = h("ul", { class: "balon-liste" });
        kutu.append(liste);
      }
      liste.append(h("li", {}, satirParcala(madde[1])));
      return;
    }

    // 1. numaralı liste
    const numarali = satir.match(/^\s*\d+[.)]\s+(.*)$/);
    if (numarali) {
      if (!liste || liste.tagName !== "OL") {
        liste = h("ol", { class: "balon-liste" });
        kutu.append(liste);
      }
      liste.append(h("li", {}, satirParcala(numarali[1])));
      return;
    }

    listeyiKapat();
    kutu.append(h("div", { class: "balon-satir" }, satirParcala(satir)));
  });

  return kutu;
}
