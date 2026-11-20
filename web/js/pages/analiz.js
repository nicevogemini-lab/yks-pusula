// analiz.js — konu ağırlığı, müfredat yorumu, plan uyumu ve değerlendirme
import { api } from "../api.js";
import { h, ikon, rozet, tarihTr, dakikaMetni, bosDurum, bildir, metinBalonu } from "../ui.js";
import { hedefKarti } from "../hedef-karti.js";

export const baslik = "Analiz";
export const alt = "Konu ağırlığı, müfredat açığı, plan uyumu ve yapay zekâ değerlendirmesi";

// Konu tablosunda bir seferde gösterilen satır sayısı
const SAYFA_BOYU = 40;
const SINIF_ETIKET = { 9: "9. sınıf", 10: "10. sınıf", 11: "11. sınıf", 12: "12. sınıf", 0: "Mezun" };
const SIKLIK_ETIKET = { 7: "Haftada 1 deneme", 3: "3 günde 1 deneme" };

let uygulama = null;
let analizVerisi = null;
// Konu tablosu süzgeçleri: ders kodu, sınıf (metin), seviye
let filtre = { ders: "", sinif: "", seviye: "" };
let satirSiniri = SAYFA_BOYU;
let tabloKabi = null;
let tabloAlt = null;
let aiAktif = false;
let degerlendirme = null;
let degerlendirmeKabi = null;
let degerlendirDugmesi = null;

export async function ciz(kap, durum) {
  uygulama = durum;
  const [analiz, aiDurum, kayit] = await Promise.all([
    api.get(`/api/analiz/${durum.profil.id}`),
    api.get("/api/ai/durum"),
    api.get(`/api/analiz/${durum.profil.id}/degerlendirme`),
  ]);
  analizVerisi = analiz;
  aiAktif = Boolean(aiDurum?.aktif);
  degerlendirme = kayit?.var ? kayit : null;
  filtre = { ders: "", sinif: "", seviye: "" };
  satirSiniri = SAYFA_BOYU;
  tabloKabi = h("div", { style: { overflowX: "auto" } });
  tabloAlt = h("div", { style: { display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap", marginTop: "10px" } });

  kap.replaceChildren(
    ozetSeridi(analiz),
    hedefKarti(analiz.hedef, {
      kompakt: true,
      baslik: "Denemelerin hedefe göre neresinde?",
      alt: "Her deneme, hedef sıralamanın gerektirdiği TYT/AYT netiyle karşılaştırılır.",
    }),
    dersKarti(analiz),
    konuKarti(),
    mufredatKarti(analiz),
    planUyumuKarti(analiz),
    degerlendirmeKarti()
  );
  konuTablosunuCiz();
}

// ------------------------------------------------------------- ortak parçalar
function kartBasligi(baslik, alt, sag = null) {
  return h(
    "div",
    { class: "kart-baslik", style: { alignItems: "center" } },
    h("div", {}, h("h2", { text: baslik }), alt ? h("p", { text: alt }) : null),
    sag
  );
}

function baslikSatiri(metinler) {
  return h("thead", {}, h("tr", {}, metinler.map((t) => h("th", { text: t }))));
}

function statKarti(etiket, deger, alt, ton = "") {
  return h(
    "article",
    { class: "kart stat" },
    h("div", { class: "etiket", text: etiket }),
    h("div", { class: "deger", text: deger }),
    h("div", { class: `fark ${ton}`.trim(), text: alt })
  );
}

function seviye(basari) {
  if (basari == null) return "veri yok";
  if (basari < 0.45) return "zayıf";
  if (basari < 0.7) return "orta";
  return "iyi";
}

function sinifMetni(sinif) {
  return SINIF_ETIKET[sinif] || `${sinif}. sınıf`;
}

// ------------------------------------------------------------- özet kartları
function ozetSeridi(analiz) {
  const calisilan = analiz.dersler.filter((d) => d.deneme_sayisi);
  const toplamNet = Math.round(calisilan.reduce((t, d) => t + d.net, 0) * 100) / 100;
  const mufredat = analiz.mufredat || {};
  const plan = analiz.plan_uyumu || {};
  const acik = analiz.acik_konu_sayisi ?? 0;
  const kapsam = plan.kapsam_orani ?? 100;

  return h(
    "section",
    { class: "izgara ozet-serit" },
    statKarti(
      "Deneme neti",
      String(toplamNet),
      `${analiz.deneme_sayisi} deneme · ${calisilan.length} ders`,
      calisilan.length ? "" : "kotu"
    ),
    statKarti(
      "Açık konu",
      String(acik),
      `${mufredat.kapsam_ici_konu ?? 0} kapsam içi konudan`,
      acik ? "kotu" : "iyi"
    ),
    statKarti(
      "Kapsam",
      String(mufredat.kapsam_ici_konu ?? 0),
      mufredat.kapsam_etiketi || "Tüm YKS müfredatı"
    ),
    statKarti(
      "Plan kapsamı",
      `%${kapsam}`,
      `${(plan.planda_olmayan_aciklar || []).length} açık konu planda yok`,
      kapsam < 60 ? "kotu" : "iyi"
    )
  );
}

// ------------------------------------------------------------- ders tablosu
function dersKarti(analiz) {
  const kart = h("section", { class: "kart" });
  const mufredatDersleri = {};
  (analiz.mufredat?.dersler || []).forEach((d) => { mufredatDersleri[d.ders_kod] = d; });

  kart.append(
    kartBasligi(
      "Ders bazlı tablo",
      "Denemelerdeki doğru/yanlış/boş toplamı ve müfredat açığı",
      h("a", { class: "dugme ikincil kucuk", href: "#/deneme" }, "Deneme ekle")
    )
  );

  if (!analiz.dersler.some((d) => d.deneme_sayisi)) {
    kart.append(
      bosDurum(
        "Henüz deneme yok",
        "İlk denemeni kaydettiğinde ders bazlı doğru/yanlış burada listelenir."
      )
    );
    return kart;
  }

  const tablo = h("table", { class: "sonuc-tablo" });
  tablo.append(baslikSatiri(["Ders", "D/Y/B", "Net", "Başarı", "Seviye", "Açık konu"]));
  tablo.append(
    h(
      "tbody",
      {},
      analiz.dersler.filter((d) => d.deneme_sayisi).map((d) => {
        const m = mufredatDersleri[d.kod] || {};
        return h(
          "tr",
          {},
          h(
            "td",
            {},
            h(
              "span",
              { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
              h("span", { class: "nokta", style: { background: d.renk } }),
              d.ad
            ),
            h("small", { text: d.sinav, style: { display: "block", color: "#6b7280", marginTop: "2px" } })
          ),
          h("td", {
            text: `${d.dogru}/${d.yanlis}/${d.bos}`,
            style: { fontSize: "12.5px", color: "#6b7280" },
          }),
          h("td", { class: "net-hucre", text: String(d.net) }),
          h("td", { text: d.basari_yuzde == null ? "—" : `%${d.basari_yuzde}` }),
          h(
            "td",
            {},
            rozet(d.seviye, d.seviye === "zayıf" ? "uyari" : d.seviye === "iyi" ? "basari" : "")
          ),
          h(
            "td",
            {},
            m.acik_sayisi
              ? h("span", {}, `${m.acik_sayisi} / ${m.konu_sayisi}`, h("small", { text: `  (%${m.acik_oran})`, style: { color: "#6b7280" } }))
              : h("span", { text: "—", style: { color: "#9aa1ad" } })
          )
        );
      })
    )
  );

  kart.append(h("div", { style: { overflowX: "auto" } }, tablo));
  return kart;
}

// ------------------------------------------------------------- konu tablosu
function konuKarti() {
  const kart = h("section", { class: "kart" });
  kart.append(
    kartBasligi(
      "Konu tablosu",
      "Etkin puan = beklenen soru × (1 − başarı). Sıralama hedef sıralamana göre ağırlıklandırılır."
    )
  );

  const dersler = [];
  const gorulen = new Set();
  (analizVerisi.konular || []).forEach((k) => {
    if (gorulen.has(k.ders_kod)) return;
    gorulen.add(k.ders_kod);
    dersler.push([k.ders_kod, k.ders_ad]);
  });
  dersler.sort((a, b) => a[1].localeCompare(b[1], "tr"));

  kart.append(
    h(
      "div",
      { style: { display: "flex", gap: "10px", flexWrap: "wrap", marginBottom: "12px" } },
      suzgec("Ders", "ders", [["", "Tüm dersler"], ...dersler]),
      suzgec("Sınıf", "sinif", [
        ["", "Tüm sınıflar"],
        ["9", "9. sınıf"],
        ["10", "10. sınıf"],
        ["11", "11. sınıf"],
        ["12", "12. sınıf"],
      ]),
      suzgec("Seviye", "seviye", [
        ["", "Tüm seviyeler"],
        ["zayıf", "Zayıf (%0-44)"],
        ["orta", "Orta (%45-69)"],
        ["iyi", "İyi (%70+)"],
      ])
    ),
    tabloKabi,
    tabloAlt
  );
  return kart;
}

function suzgec(etiket, anahtar, secenekler) {
  const secim = h(
    "select",
    {
      class: "secim",
      onchange: (olay) => {
        filtre[anahtar] = olay.target.value;
        satirSiniri = SAYFA_BOYU;
        konuTablosunuCiz();
      },
    },
    secenekler.map(([deger, ad]) =>
      h("option", { value: deger, selected: filtre[anahtar] === deger }, ad))
  );
  return h(
    "div",
    { class: "form-alan", style: { minWidth: "160px" } },
    h("label", { text: etiket }),
    secim
  );
}

function suzulenler() {
  const konular = analizVerisi?.konular || [];
  return konular.filter((k) => {
    if (filtre.ders && k.ders_kod !== filtre.ders) return false;
    if (filtre.sinif && String(k.sinif) !== filtre.sinif) return false;
    if (filtre.seviye && seviye(k.basari) !== filtre.seviye) return false;
    return true;
  });
}

function konuTablosunuCiz() {
  if (!tabloKabi || !analizVerisi) return;
  const tumu = suzulenler();
  const gorunen = tumu.slice(0, satirSiniri);

  const tablo = h("table", { class: "sonuc-tablo" });
  tablo.append(baslikSatiri(["Konu", "Beklenen soru", "Başarı", "Deneme D/Y/B", "Etkin puan"]));
  tablo.append(
    h(
      "tbody",
      {},
      gorunen.map((k) =>
        h(
          "tr",
          {},
          h(
            "td",
            {},
            h(
              "span",
              { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
              h("span", { class: "nokta", style: { background: k.renk } }),
              k.ad
            ),
            h("small", {
              text: `${k.ders_ad} · ${sinifMetni(k.sinif)} · ${k.kaynak} verisi${k.kapsam_disi ? " · kapsam dışı" : ""}`,
              style: { display: "block", color: "#6b7280", marginTop: "2px" },
            })
          ),
          h("td", { text: k.beklenen_soru.toFixed(1) }),
          h("td", { text: `%${k.basari_yuzde}` }),
          h("td", {
            text: `${k.deneme_dogru}/${k.deneme_yanlis}/${k.deneme_bos}`,
            style: { fontSize: "12.5px", color: "#6b7280" },
          }),
          h("td", { class: "net-hucre", text: String(k.etkin_puan) })
        )
      )
    )
  );

  if (!gorunen.length) {
    tabloKabi.replaceChildren(
      bosDurum("Süzgece uyan konu yok", "Ders, sınıf ve seviye seçimini değiştir.")
    );
  } else {
    tabloKabi.replaceChildren(tablo);
  }

  tabloAlt.replaceChildren(
    h("span", { class: "ipucu", text: `${gorunen.length}/${tumu.length} konu · etkin puana göre sıralı` }),
    tumu.length > gorunen.length
      ? h(
          "button",
          {
            class: "dugme sessiz kucuk",
            type: "button",
            onclick: () => {
              satirSiniri += SAYFA_BOYU;
              konuTablosunuCiz();
            },
          },
          `${Math.min(SAYFA_BOYU, tumu.length - gorunen.length)} konu daha göster`
        )
      : null
  );
}

// ------------------------------------------------------------- müfredat yorumu
function mufredatKarti(analiz) {
  const mufredat = analiz.mufredat;
  const kart = h("section", { class: "kart" });
  if (!mufredat) return kart;

  kart.append(
    kartBasligi(
      "Müfredat yorumu",
      `${mufredat.kapsam_etiketi} · ${mufredat.kapsam_ici_konu} konu · ${mufredat.acik_konu_sayisi} açık`,
      h("a", { class: "dugme ikincil kucuk", href: "#/mufredat" }, "Müfredat")
    ),
    h("p", { class: "ipucu", style: { margin: "0 0 12px" }, text: mufredat.yorum })
  );

  const dersler = (mufredat.dersler || []).filter((d) => d.acik_sayisi);
  if (dersler.length) {
    const tablo = h("table", { class: "sonuc-tablo" });
    tablo.append(baslikSatiri(["Ders", "Kapsam içi konu", "Açık", "Açık oran"]));
    tablo.append(
      h(
        "tbody",
        {},
        dersler.map((d) =>
          h(
            "tr",
            {},
            h(
              "td",
              {},
              h(
                "span",
                { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
                h("span", { class: "nokta", style: { background: d.renk } }),
                d.ders
              )
            ),
            h("td", { text: String(d.konu_sayisi) }),
            h("td", { text: String(d.acik_sayisi) }),
            h("td", {}, rozet(`%${d.acik_oran}`, d.acik_oran >= 50 ? "uyari" : ""))
          )
        )
      )
    );
    kart.append(h("div", { style: { overflowX: "auto" } }, tablo));
  } else {
    kart.append(h("p", { class: "ipucu", text: "Ders bazında açık konu yok; denemede konu işaretledikçe bu tablo dolar." }));
  }

  if (!(mufredat.konular || []).length) {
    kart.append(
      bosDurum(
        "Yorumlanacak açık konu yok",
        "Denemede konu bazlı yanlış/boş işaretledikçe bu kart konu bazlı yorum üretir."
      )
    );
    return kart;
  }

  const liste = h("div", { class: "acik-konular" });
  mufredat.konular.forEach((k) => {
    liste.append(
      h(
        "div",
        { class: "acik-konu-grup" },
        h(
          "div",
          { class: "acik-konu-baslik" },
          h("span", { class: "nokta", style: { background: k.renk } }),
          h("b", { text: k.konu }),
          rozet(`${k.ders} · ${sinifMetni(k.sinif)}`),
          rozet(`%${k.basari_yuzde} başarı`, k.basari_yuzde < 45 ? "uyari" : ""),
          k.onkosul.length && !k.onkosul_hazir ? rozet("ön koşul eksik", "uyari") : null
        ),
        h(
          "div",
          { class: "konu-cipleri" },
          (k.beceri_etiket || []).map((b) => h("span", { class: "rozet" }, b)),
          h("span", { class: "rozet", text: `${k.beklenen_soru.toFixed(1)} soru` }),
          h("span", { class: "rozet", text: `ağırlık ${k.agirlik}` }),
          h("span", { class: "rozet", text: `D/Y/B ${k.deneme_dogru}/${k.deneme_yanlis}/${k.deneme_bos}` }),
          h("span", { class: "rozet", text: k.kaynak }),
          k.tahmini_dk ? h("span", { class: "rozet", text: `${k.tahmini_dk} dk` }) : null
        )
      )
    );
  });
  kart.append(
    h("h3", { text: "Konu bazlı yorum", style: { margin: "14px 0 8px", fontSize: "13.5px" } }),
    h("div", { style: { maxHeight: "420px", overflowY: "auto" } }, liste)
  );
  return kart;
}

// ------------------------------------------------------------- plan uyumu
function planUyumuKarti(analiz) {
  const plan = analiz.plan_uyumu;
  const kart = h("section", { class: "kart" });
  if (!plan) return kart;

  kart.append(
    kartBasligi(
      "Plan uyumu",
      `Önümüzdeki ${plan.gun} gün · ${plan.plan_madde_sayisi} madde · ${plan.plan_konu_sayisi} konu`,
      h("a", { class: "dugme ikincil kucuk", href: "#/plan" }, "Planı aç")
    ),
    h("p", { class: "ipucu", style: { margin: "0 0 12px" }, text: plan.yorum })
  );

  const eksikler = plan.planda_olmayan_aciklar || [];
  if (eksikler.length) {
    const tablo = h("table", { class: "sonuc-tablo" });
    tablo.append(baslikSatiri(["Açık konu", "Ders", "Başarı", "Etkin puan", ""]));
    tablo.append(
      h(
        "tbody",
        {},
        eksikler.map((k) => {
          const ekle = h(
            "button",
            { class: "dugme sessiz kucuk", type: "button", title: "Bugünün planına ekle" },
            ikon("arti", 14),
            "Plana ekle"
          );
          ekle.addEventListener("click", () => planaEkle(k.konu_id, ekle));
          return h(
            "tr",
            {},
            h(
              "td",
              {},
              h(
                "span",
                { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
                h("span", { class: "nokta", style: { background: k.renk } }),
                k.konu
              ),
              h("small", {
                text: sinifMetni(k.sinif),
                style: { display: "block", color: "#6b7280", marginTop: "2px" },
              })
            ),
            h("td", { text: k.ders }),
            h("td", { text: `%${k.basari_yuzde}` }),
            h("td", { class: "net-hucre", text: String(k.etkin_puan) }),
            h("td", {}, ekle)
          );
        })
      )
    );
    kart.append(
      h("h3", { text: "Planda olmayan açık konular", style: { margin: "0 0 8px", fontSize: "13.5px" } }),
      h("div", { style: { overflowX: "auto" } }, tablo)
    );
  } else {
    kart.append(
      h("p", { class: "ipucu", text: "Önümüzdeki haftada açık konuların tümü programda yer alıyor." })
    );
  }

  const gereksiz = plan.planda_gereksiz || [];
  if (gereksiz.length) {
    const tablo = h("table", { class: "sonuc-tablo", style: { marginTop: "10px" } });
    tablo.append(baslikSatiri(["Tarih", "Blok", "Süre", "Tür"]));
    tablo.append(
      h(
        "tbody",
        {},
        gereksiz.map((m) =>
          h(
            "tr",
            {},
            h("td", { text: tarihTr(m.tarih) }),
            h("td", { text: m.baslik }),
            h("td", { text: dakikaMetni(m.sure_dk) }),
            h("td", { text: m.tur })
          )
        )
      )
    );
    kart.append(
      h("h3", { text: "Artık gerektirmeyen bloklar", style: { margin: "18px 0 8px", fontSize: "13.5px" } }),
      h("p", { class: "ipucu", style: { margin: "0 0 8px" },
        text: "Bu konular güvenle tamamlandı; plan bloğunu başka açık konuya kaydırabilirsin." }),
      h("div", { style: { overflowX: "auto" } }, tablo)
    );
  }

  return kart;
}

async function planaEkle(konuId, dugme) {
  if (!uygulama) return;
  dugme.disabled = true;
  dugme.textContent = "Ekleniyor…";
  try {
    const yanit = await api.post(`/api/plan/${uygulama.profil.id}/madde`, { konu_id: konuId });
    bildir(
      yanit.zaten_var
        ? "Bu konu bugünün planında zaten var"
        : `Plana eklendi · ${tarihTr(yanit.tarih)}`
    );
    await uygulama.yenile();
  } catch (hata) {
    bildir(hata.message, "hata");
    dugme.disabled = false;
    dugme.replaceChildren(ikon("arti", 14), "Plana ekle");
  }
}

// --------------------------------------------------- yapay zekâ değerlendirmesi
function degerlendirDugmeYaz(metin) {
  if (!degerlendirDugmesi) return;
  degerlendirDugmesi.replaceChildren(ikon("sohbet", 16), metin);
}

function degerlendirmeKarti() {
  const kart = h("section", { class: "kart" });
  degerlendirDugmesi = h("button", { class: "dugme", type: "button" });
  degerlendirDugmeYaz(degerlendirme ? "Yeniden değerlendir" : "Değerlendir");

  kart.append(
    h(
      "div",
      { class: "kart-baslik", style: { alignItems: "center" } },
      h(
        "div",
        {},
        h("h2", { text: "Yapay zekâ değerlendirmesi" }),
        h("p", { text: "Deneme doğru/yanlışları ve konu ağırlıkları yorumlanır; açığı kapatacak deneme sıklığı ve takvimi çıkarılır." })
      ),
      degerlendirDugmesi
    )
  );
  degerlendirmeKabi = h("div", {});
  kart.append(degerlendirmeKabi);
  degerlendirmeCiz();

  degerlendirDugmesi.addEventListener("click", async () => {
    if (!uygulama) return;
    degerlendirDugmesi.disabled = true;
    degerlendirDugmeYaz("Değerlendiriliyor…");
    try {
      degerlendirme = await api.post(`/api/analiz/${uygulama.profil.id}/degerlendir`, {});
      degerlendirmeCiz();
      bildir(degerlendirme.kaynak === "gemini" ? "Yapay zekâ değerlendirmesi hazır" : "Yerel değerlendirme hazır");
    } catch (hata) {
      bildir(hata.message, "hata");
    } finally {
      degerlendirDugmesi.disabled = false;
      degerlendirDugmeYaz("Yeniden değerlendir");
    }
  });
  return kart;
}

function degerlendirmeCiz() {
  if (!degerlendirmeKabi) return;
  if (!degerlendirme) {
    degerlendirmeKabi.replaceChildren(
      h("p", { class: "ipucu",
        text: aiAktif
          ? "Gemini anahtarı hazır: sonuçlar ve konu analizi yapay zekâ ile yorumlanacak."
          : "Yapay zekâ anahtarı yok; değerlendirme yerel analizle üretilir. Ayarlar > Yapay Zekâ bölümünden anahtar ekleyebilirsin." })
    );
    return;
  }

  const takvim = degerlendirme.takvim;
  const meta = h("div", { style: { display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", marginBottom: "10px" } },
    rozet(degerlendirme.kaynak === "gemini" ? `Gemini · ${degerlendirme.model}` : "Yerel analiz",
      degerlendirme.kaynak === "gemini" ? "basari" : ""),
    h("span", { class: "ipucu", text: `${tarihTr(degerlendirme.olusturma)} tarihli` }),
    h("span", { class: "ipucu", text: `${degerlendirme.deneme_sayisi} deneme · ${degerlendirme.acik_net} net açık · ${degerlendirme.acik_konu_sayisi ?? 0} açık konu` }));

  const parcalar = [meta];
  if (degerlendirme.not) {
    parcalar.push(h("p", { class: "ipucu", style: { color: "#a16207", marginBottom: "8px" }, text: degerlendirme.not }));
  }
  parcalar.push(metinBalonu(degerlendirme.metin));

  parcalar.push(
    h("div", { style: { display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", margin: "16px 0 4px" } },
      h("b", { text: "Deneme sıklığı:", style: { fontSize: "13px" } }),
      h("div", { class: "plan-sekmeler", style: { margin: "0" } },
        [7, 3].map((gun) =>
          h("button", {
            class: `plan-sekme${takvim.siklik === gun ? " aktif" : ""}`,
            type: "button",
            "aria-selected": takvim.siklik === gun ? "true" : "false",
            onclick: () => siklikSec(gun),
          }, SIKLIK_ETIKET[gun])))),
    h("p", { class: "ipucu", style: { margin: "6px 0 14px" }, text: `Öneri: ${degerlendirme.gerekce}` })
  );

  const tablo = h("table", { class: "sonuc-tablo" });
  tablo.append(
    baslikSatiri(["Tarih", "Sınav", "Süre", "Hedef net", "Odak konular"]),
    h("tbody", {},
      takvim.denemeler.map((d) =>
        h("tr", {},
          h("td", { text: d.tarih_tr }),
          h("td", { text: d.ad }),
          h("td", { text: `${d.sure_dk} dk` }),
          h("td", { class: "net-hucre", text: String(d.hedef_net) }),
          h("td", { text: d.odak.length ? d.odak.map((k) => k.konu).join(", ") : "—",
            style: { fontSize: "12.5px", color: "#6b7280" } }))))
  );

  const yaz = h("button", { class: "dugme ikincil", type: "button" }, ikon("takvim", 16), "Takvimi plana yaz");
  yaz.addEventListener("click", () => takvimiYaz(yaz));

  parcalar.push(
    h("div", { style: { display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap", marginBottom: "8px" } },
      h("h3", { text: "Deneme takvimi", style: { margin: "0", fontSize: "13.5px" } }),
      h("span", { class: "ipucu",
        text: `${takvim.adet} deneme · ${tarihTr(takvim.denemeler[0]?.tarih)} – ${tarihTr(takvim.bitis)} · ${dakikaMetni(takvim.toplam_dk)}` })),
    h("div", { style: { overflowX: "auto" } }, tablo),
    h("div", { style: { display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap", marginTop: "12px" } },
      yaz,
      h("span", { class: "ipucu", text: "Sınav günlerinde bekleyen konu blokları kaldırılır; 40 dk analiz bloğu eklenir." }))
  );

  const program = degerlendirme.program;
  if (program?.gunler?.length) {
    const pTablo = h("table", { class: "sonuc-tablo" });
    pTablo.append(
      baslikSatiri(["Gün", "Tarih", "Matematik", "Paragraf", "Odak konular"]),
      h("tbody", {},
        program.gunler.map((g) =>
          h("tr", {},
            h("td", { text: g.gun_adi }),
            h("td", { text: g.tarih_tr }),
            h("td", { text: g.matematik ? `${g.matematik.soru} soru · ${g.matematik.konu}` : "—" }),
            h("td", { text: `${g.paragraf.soru} soru` }),
            h("td", { text: g.odak.length ? g.odak.map((k) => k.konu).join(", ") : "—",
              style: { fontSize: "12.5px", color: "#6b7280" } }))
        )
    ));

    const programYaz = h("button", { class: "dugme ikincil", type: "button" }, ikon("takvim", 16), "Programı plana yaz");
    programYaz.addEventListener("click", () => programiYaz(programYaz));

    parcalar.push(
      h("div", { style: { marginTop: "20px" } },
        h("div", { style: { display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap", marginBottom: "8px" } },
          h("h3", { text: "Haftalık program (her gün matematik + paragraf)", style: { margin: "0", fontSize: "13.5px" } }),
          h("span", { class: "ipucu", text: program.kural })),
        h("div", { style: { overflowX: "auto" } }, pTablo),
        h("div", { style: { display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap", marginTop: "12px" } },
          programYaz,
          h("span", { class: "ipucu", text: "Planı bugünden itibaren 7 gün için tazeler; aynı sıra günlük planda da kullanılır." })))
    );
  }

  degerlendirmeKabi.replaceChildren(...parcalar);
}

async function programiYaz(dugme) {
  if (!uygulama) return;
  dugme.disabled = true;
  dugme.textContent = "Yazılıyor…";
  try {
    const yanit = await api.post(`/api/plan/${uygulama.profil.id}/uret?gun=7`, {});
    bildir(`${yanit.eklenen} madde plana yazıldı`);
    await uygulama.yenile();
  } catch (hata) {
    bildir(hata.message, "hata");
    dugme.disabled = false;
    dugme.replaceChildren(ikon("takvim", 16), "Programı plana yaz");
  }
}

async function siklikSec(gun) {
  if (!uygulama || !degerlendirme) return;
  try {
    const takvim = await api.get(`/api/deneme-takvimi/${uygulama.profil.id}?siklik=${gun}&hafta=4`);
    degerlendirme = { ...degerlendirme, siklik: gun, takvim };
    degerlendirmeCiz();
  } catch (hata) {
    bildir(hata.message, "hata");
  }
}

async function takvimiYaz(dugme) {
  if (!uygulama || !degerlendirme) return;
  const gun = degerlendirme.takvim.siklik;
  dugme.disabled = true;
  dugme.textContent = "Yazılıyor…";
  try {
    const yanit = await api.post(`/api/plan/${uygulama.profil.id}/deneme-takvimi?siklik=${gun}&hafta=4`, {});
    bildir(`${yanit.eklenen} deneme/analiz bloğu plana yazıldı`);
    await uygulama.yenile();
  } catch (hata) {
    bildir(hata.message, "hata");
    dugme.disabled = false;
    dugme.replaceChildren(ikon("takvim", 16), "Takvimi plana yaz");
  }
}
