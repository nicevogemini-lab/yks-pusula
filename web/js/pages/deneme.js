// deneme.js — deneme sınavı girişi ve kayıtlı denemeler
import { api } from "../api.js";
import { h, ikon, rozet, tarihTr, bosDurum, bildir } from "../ui.js";
import { sayiMetni } from "../hedef-karti.js";

export const baslik = "Denemeler";
export const alt = "Deneme gir, kayıtlı denemeleri ve konu kırılımını yönet";

let dersler = [];
let tur = "TYT";
let girisler = {};
// ders_kod -> { konu_id: {dogru, yanlis, bos} }: konu bazlı deneme girişi
let konuGirisleri = {};
// ders_kod -> satırdaki girdi ve net hücreleri (konu toplamı otomatik yazılır)
let satirGirdileri = {};
let tabloKabi = null;
let toplamKabi = null;
// ders_kod -> konular: denemede konu kırılımı girmek için
let konuHaritasi = {};

function bugunIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function netHesapla(g) {
  return Math.round((g.dogru - g.yanlis / 4) * 100) / 100;
}

export async function ciz(kap, durum) {
  const [mufredat, denemeler, hedef] = await Promise.all([
    api.get(`/api/mufredat/${durum.profil.id}`),
    api.get(`/api/denemeler/${durum.profil.id}`),
    api.get(`/api/hedef/${durum.profil.id}`),
  ]);
  dersler = mufredat.dersler.map((d) => ({
    kod: d.kod,
    ad: d.ad,
    sinav: d.sinav,
    soru_sayisi: d.soru_sayisi,
    renk: d.renk,
  }));
  konuHaritasi = {};
  mufredat.dersler.forEach((d) => {
    konuHaritasi[d.kod] = (d.konular || []).map((k) => ({ id: k.id, ad: k.ad }));
  });
  girisler = {};
  konuGirisleri = {};
  dersler.forEach((d) => { girisler[d.kod] = { dogru: 0, yanlis: 0, bos: 0 }; });
  tur = "TYT";

  kap.replaceChildren(
    formKarti(durum),
    listeKarti(denemeler, durum, hedef)
  );
  tabloCiz();
}

// ------------------------------------------------------------------- form
function formKarti(durum) {
  const turSecim = h(
    "select",
    {
      class: "secim",
      onchange: (o) => {
        tur = o.target.value;
        girisler = {};
        konuGirisleri = {};
        dersler.forEach((d) => { girisler[d.kod] = { dogru: 0, yanlis: 0, bos: 0 }; });
        tabloCiz();
      },
    },
    ["TYT", "AYT"].map((t) => h("option", { value: t, selected: tur === t }, t))
  );

  const adGirdi = h("input", { class: "alan", type: "text", placeholder: "Örn. Kurumsal Deneme 4", maxlength: "80" });
  const tarihGirdi = h("input", { class: "alan", type: "date", value: bugunIso() });
  const sureGirdi = h("input", { class: "alan", type: "number", min: "0", max: "400", value: "165" });

  tabloKabi = h("div", { style: { overflowX: "auto" } });
  toplamKabi = h("div", { style: { display: "flex", alignItems: "center", gap: "14px", flexWrap: "wrap" } });

  const kaydet = h("button", { class: "dugme", type: "button" }, ikon("arti", 16), "Denemeyi kaydet");
  kaydet.addEventListener("click", async () => {
    const sonuclar = Object.entries(girisler)
      .filter(([, g]) => g.dogru + g.yanlis + g.bos > 0)
      .map(([ders_kod, g]) => ({ ders_kod, ...g }));
    const konular = doluKonular();

    if (!sonuclar.length && !konular.length) {
      bildir("En az bir ders için doğru/yanlış/boş gir.", "hata");
      return;
    }
    kaydet.disabled = true;
    kaydet.textContent = "Kaydediliyor…";
    try {
      const yanit = await api.post("/api/deneme", {
        profil_id: durum.profil.id,
        tur,
        ad: adGirdi.value.trim(),
        tarih: tarihGirdi.value || null,
        sure_dk: Number(sureGirdi.value) || 0,
        sonuclar,
        konular,
      });
      bildir(
        konular.length
          ? `Kaydedildi · ${konular.length} konu · TYT puanı ${yanit.ozet.puan.tyt}`
          : `Kaydedildi · tahmini TYT puanı ${yanit.ozet.puan.tyt}`
      );
      await durum.yenile();
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
      kaydet.textContent = "Denemeyi kaydet";
    }
  });

  return h(
    "section",
    { class: "kart" },
    h("div", { class: "kart-baslik", style: { alignItems: "center" } },
      h("div", {},
        h("h2", { text: "Yeni deneme gir" }),
        h("p", { text: "Net = doğru − yanlış/4. Boş sorular neti değiştirmez." })),
      h("a", { class: "dugme ikincil kucuk", href: "#/analiz" }, "Analizi aç")),
    h(
      "div",
      { class: "deneme-form" },
      h("div", { class: "ust-satir" },
        h("div", { class: "form-alan" }, h("label", { text: "Sınav" }), turSecim),
        h("div", { class: "form-alan" }, h("label", { text: "Deneme adı" }), adGirdi),
        h("div", { class: "form-alan" }, h("label", { text: "Tarih" }), tarihGirdi),
        h("div", { class: "form-alan" }, h("label", { text: "Süre (dk)" }), sureGirdi)),
      tabloKabi,
      h("div", { style: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", flexWrap: "wrap" } },
        toplamKabi,
        h("div", { style: { display: "flex", gap: "8px" } },
          h("button", {
            class: "dugme ikincil",
            type: "button",
            onclick: () => {
              dersler.forEach((d) => { girisler[d.kod] = { dogru: 0, yanlis: 0, bos: 0 }; });
              konuGirisleri = {};
              tabloCiz();
            },
          }, "Temizle"),
          kaydet))
    )
  );
}

function tabloCiz() {
  if (!tabloKabi) return;
  const secili = dersler.filter((d) => d.sinav === tur);
  satirGirdileri = {};
  const tablo = h("table", { class: "sonuc-tablo" });
  tablo.append(
    h("thead", {},
      h("tr", {},
        h("th", { text: "Ders" }),
        h("th", { text: "Soru" }),
        h("th", { text: "Doğru" }),
        h("th", { text: "Yanlış" }),
        h("th", { text: "Boş" }),
        h("th", { text: "Net" }),
        h("th", { text: "Konular" })))
  );

  const govde = h("tbody");
  secili.forEach((ders) => {
    const g = girisler[ders.kod];
    const netHucre = h("td", { class: "net-hucre", text: "0" });

    const alan = (ad) =>
      h("input", {
        type: "number",
        min: "0",
        max: String(ders.soru_sayisi || 40),
        value: String(g[ad]),
        oninput: (o) => {
          g[ad] = Math.max(0, Number(o.target.value) || 0);
          netHucre.textContent = String(netHesapla(g));
          toplamlariCiz();
        },
      });

    const satirGirdisi = {
      dogru: alan("dogru"),
      yanlis: alan("yanlis"),
      bos: alan("bos"),
      net: netHucre,
    };
    satirGirdileri[ders.kod] = satirGirdisi;

    // Konu paneli: dersin konuları doğru/yanlış/boş olarak girilir,
    // ders satırı toplamı otomatik hesaplanır (elle de değiştirilebilir).
    const panel = h("tr", { class: "konu-satiri", style: { display: "none" } });
    const panelHucre = h("td", { colspan: "7" });
    panel.append(panelHucre);
    const konuDugme = h(
      "button",
      { class: "dugme sessiz kucuk", type: "button", title: "Konu bazlı giriş" },
      "Konular"
    );
    let dolu = false;
    konuDugme.addEventListener("click", () => {
      dolu = !dolu;
      if (dolu && !panelHucre.hasChildNodes()) {
        panelHucre.append(
          konuPaneliCiz(ders.kod, konuGirisleri, () => {
            konuToplaminiUygula(ders.kod);
            netHucre.textContent = String(netHesapla(g));
          })
        );
      }
      panel.style.display = dolu ? "" : "none";
    });

    govde.append(
      h("tr", {},
        h("td", {},
          h("span", { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
            h("span", { class: "nokta", style: { background: ders.renk } }),
            ders.ad)),
        h("td", { text: String(ders.soru_sayisi || "-"), style: { color: "#6b7280", fontSize: "12px" } }),
        h("td", {}, satirGirdisi.dogru),
        h("td", {}, satirGirdisi.yanlis),
        h("td", {}, satirGirdisi.bos),
        netHucre,
        h("td", {}, konuDugme)),
      panel
    );
  });

  tablo.append(govde);
  tabloKabi.replaceChildren(tablo);
  toplamlariCiz();
}

/** Bir dersin konularını doğru/yanlış/boş girdileriyle listeler */
function konuPaneliCiz(dersKod, depo, degisti) {
  const konular = konuHaritasi[dersKod] || [];
  if (!konular.length) return h("p", { class: "ipucu", text: "Bu ders için tanımlı konu yok." });
  depo[dersKod] = depo[dersKod] || {};
  const kayitlar = depo[dersKod];

  const tablo = h("table", { class: "sonuc-tablo", style: { margin: "8px 0" } });
  tablo.append(
    h("thead", {},
      h("tr", {},
        ["Konu", "Doğru", "Yanlış", "Boş"].map((t) => h("th", { text: t }))))
  );

  const govde = h("tbody");
  konular.forEach((konu) => {
    const kayit = kayitlar[konu.id] || (kayitlar[konu.id] = { dogru: 0, yanlis: 0, bos: 0 });
    const alan = (ad) =>
      h("input", {
        type: "number",
        min: "0",
        value: String(kayit[ad]),
        oninput: (o) => {
          kayit[ad] = Math.max(0, Number(o.target.value) || 0);
          degisti();
        },
      });
    govde.append(
      h("tr", {},
        h("td", { text: konu.ad, style: { fontSize: "12.5px" } }),
        h("td", {}, alan("dogru")),
        h("td", {}, alan("yanlis")),
        h("td", {}, alan("bos")))
    );
  });
  tablo.append(govde);
  return h(
    "div",
    {},
    h("p", { class: "ipucu", style: { margin: "6px 0" },
      text: "Konu toplamı ders satırına yazılır; emin olmadığın konuyu boş bırak." }),
    h("div", { style: { maxHeight: "320px", overflowY: "auto" } }, tablo)
  );
}

/** Konu girdilerinin toplamını ders satırına yazar */
function konuToplaminiUygula(dersKod) {
  const kayitlar = konuGirisleri[dersKod] || {};
  const toplam = { dogru: 0, yanlis: 0, bos: 0 };
  Object.values(kayitlar).forEach((k) => {
    toplam.dogru += k.dogru;
    toplam.yanlis += k.yanlis;
    toplam.bos += k.bos;
  });
  if (toplam.dogru + toplam.yanlis + toplam.bos === 0) return;

  const g = girisler[dersKod];
  if (!g) return;
  g.dogru = toplam.dogru;
  g.yanlis = toplam.yanlis;
  g.bos = toplam.bos;
  const satir = satirGirdileri[dersKod];
  if (satir) {
    satir.dogru.value = String(g.dogru);
    satir.yanlis.value = String(g.yanlis);
    satir.bos.value = String(g.bos);
    satir.net.textContent = String(netHesapla(g));
  }
  toplamlariCiz();
}

/** Girilmiş konu satırlarını API gövdesine çevirir */
function doluKonular() {
  const satirlar = [];
  Object.entries(konuGirisleri).forEach(([, kayitlar]) => {
    Object.entries(kayitlar).forEach(([konu_id, k]) => {
      if (k.dogru + k.yanlis + k.bos > 0) {
        satirlar.push({ konu_id: Number(konu_id), dogru: k.dogru, yanlis: k.yanlis, bos: k.bos });
      }
    });
  });
  return satirlar;
}

function toplamlariCiz() {
  if (!toplamKabi) return;
  const secili = dersler.filter((d) => d.sinav === tur);
  const toplamNet = secili.reduce((t, d) => t + netHesapla(girisler[d.kod]), 0);
  const dolu = secili.filter((d) => {
    const g = girisler[d.kod];
    return g.dogru + g.yanlis + g.bos > 0;
  }).length;

  toplamKabi.replaceChildren(
    h("span", { style: { fontSize: "13px", color: "#6b7280" } },
      `${dolu}/${secili.length} ders dolduruldu`),
    h("span", { style: { fontSize: "15px", fontWeight: "650" } },
      `${tur} toplam net: ${Math.round(toplamNet * 100) / 100}`)
  );
}

// ------------------------------------------------------------------- liste
function hedefFarki(d, hedef) {
  if (!hedef) return null;
  const hedefNet = d.tur === "AYT" ? hedef.ayt_hedef_net : hedef.tyt_hedef_net;
  if (!hedefNet) return null;
  const fark = Math.round((d.toplam_net - hedefNet) * 100) / 100;
  return fark >= 0
    ? rozet(`hedefin ${sayiMetni(fark)} net üzerinde`, "basari")
    : rozet(`hedefe ${sayiMetni(-fark)} net`, "uyari");
}

function listeKarti(denemeler, durum, hedef) {
  const kart = h("section", { class: "kart" });
  kart.append(
    h("div", { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Kayıtlı denemeler" }),
        h("p", { text: "Net gelişimi, ders kırılımı ve tahmini puan" })),
      h("a", { class: "dugme ikincil kucuk", href: "#/analiz" }, "Analiz"))
  );

  if (!denemeler.length) {
    kart.append(bosDurum("Henüz deneme yok", "Yukarıdaki formdan ilk denemeni gir."));
    return kart;
  }

  const sarmal = h("div", { style: { display: "grid", gap: "12px" } });
  denemeler.forEach((d) => {
    const kartEl = h("div", { class: "deneme-kart" });

    const silDugme = h("button", { class: "dugme sessiz kucuk", type: "button", title: "Denemeyi sil" }, "Sil");
    silDugme.addEventListener("click", async () => {
      if (!window.confirm("Bu deneme kaydı silinsin mi?")) return;
      try {
        await api.sil(`/api/deneme/${d.id}`);
        bildir("Deneme silindi.");
        await durum.yenile();
      } catch (hata) {
        bildir(hata.message, "hata");
      }
    });

    kartEl.append(
      h("div", { class: "deneme-ust" },
        rozet(d.tur, "marka"),
        h("b", { text: d.ad || `${d.tur} denemesi` }),
        h("span", { class: "tarih", text: tarihTr(d.tarih) }),
        h("div", { class: "sag" },
          h("span", { class: "deneme-net", text: String(d.toplam_net) }),
          h("span", { class: "tarih", text: "net" }),
          silDugme)),
      h("div", { class: "alt-satirlar" },
        h("span", { class: "mini-net" }, `${d.tur} puan `, h("b", { text: String(d.tur === "AYT" ? d.puan.ayt : d.puan.tyt) })),
        h("span", { class: "mini-net" }, "Yerleştirme ", h("b", { text: String(d.puan.yerlestirme) })),
        hedefFarki(d, hedef),
        d.zayif_dersler.length
          ? h("span", { class: "rozet uyari", text: `zayıf: ${d.zayif_dersler.map((z) => z.ad).join(", ")}` })
          : null)
    );

    if (d.satirlar.length) {
      const tablo = h("table", { class: "sonuc-tablo", style: { marginTop: "10px" } });
      tablo.append(
        h("thead", {},
          h("tr", {},
            h("th", { text: "Ders" }), h("th", { text: "D" }), h("th", { text: "Y" }),
            h("th", { text: "B" }), h("th", { text: "Net" }))),
        h("tbody", {},
          d.satirlar.map((s) =>
            h("tr", {},
              h("td", {},
                h("span", { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
                  h("span", { class: "nokta", style: { background: s.renk } }),
                  s.ders)),
              h("td", { text: String(s.dogru) }),
              h("td", { text: String(s.yanlis) }),
              h("td", { text: String(s.bos) }),
              h("td", { class: "net-hucre", text: String(s.net) }))))
      );
      kartEl.append(tablo);
    }

    const konuPaneli = konuSecimPaneli(d, durum);
    if (konuPaneli) kartEl.append(konuPaneli);

    if (d.notlar) kartEl.append(h("p", { style: { marginTop: "8px", fontSize: "12.5px", color: "#6b7280" }, text: d.notlar }));
    sarmal.append(kartEl);
  });

  kart.append(sarmal);
  return kart;
}

function konuSecimPaneli(deneme, durum) {
  // Kayıtlı denemenin konu kırılımı: konu bazlı doğru/yanlış/boş düzenlenebilir
  const dersli = (deneme.satirlar || []).filter((s) => (konuHaritasi[s.ders_kod] || []).length);
  if (!dersli.length) return null;

  const depo = {};
  (deneme.konular || []).forEach((k) => {
    const kayitlar = depo[k.ders_kod] || (depo[k.ders_kod] = {});
    kayitlar[k.konu_id] = { dogru: k.dogru || 0, yanlis: k.yanlis || 0, bos: k.bos || 0 };
  });

  const govde = h("div", { style: { display: "grid", gap: "14px", marginTop: "12px" } });
  dersli.forEach((satir) => {
    govde.append(
      h("div", {},
        h("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
          h("span", { class: "nokta", style: { background: satir.renk } }),
          h("b", { text: satir.ders, style: { fontSize: "12.5px" } }),
          h("span", { class: "ipucu", text: `${satir.dogru}D / ${satir.yanlis}Y / ${satir.bos}B` })),
        konuPaneliCiz(satir.ders_kod, depo, () => {}))
    );
  });

  const kaydet = h("button", { class: "dugme ikincil kucuk", type: "button" }, "Konu kırılımını kaydet");
  kaydet.addEventListener("click", async () => {
    kaydet.disabled = true;
    kaydet.textContent = "Kaydediliyor…";
    try {
      const konular = [];
      Object.entries(depo).forEach(([, kayitlar]) => {
        Object.entries(kayitlar).forEach(([konu_id, k]) => {
          if (k.dogru + k.yanlis + k.bos > 0) {
            konular.push({ konu_id: Number(konu_id), dogru: k.dogru, yanlis: k.yanlis, bos: k.bos });
          }
        });
      });
      const yanit = await api.post(`/api/deneme/${deneme.id}/konular`, { konular });
      bildir(`${yanit.konu_sayisi} konu kaydedildi`);
      await durum.yenile();
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
      kaydet.textContent = "Konu kırılımını kaydet";
    }
  });

  return h("details", { class: "konu-secim" },
    h("summary", { text: `Konu kırılımı (${(deneme.konular || []).length} konu)` }),
    h("p", { class: "ipucu", style: { margin: "10px 0 0" },
      text: "Hangi konudan kaç doğru/yanlış/boş yaptığını gir; konu bazlı analiz ve günlük program buna göre güncellenir." }),
    govde,
    h("div", { style: { marginTop: "12px" } }, kaydet));
}
