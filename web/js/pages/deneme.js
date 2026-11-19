// deneme.js — deneme sınavı girişi ve analizi
import { api } from "../api.js";
import { h, ikon, rozet, kisaTarih, tarihTr, dakikaMetni, bosDurum, bildir, metinBalonu } from "../ui.js";
import { hedefKarti, sayiMetni } from "../hedef-karti.js";

export const baslik = "Deneme Analizi";
export const alt = "Net hesabı, konu ağırlığı, yapay zekâ değerlendirmesi ve deneme takvimi";

let uygulama = null;
let dersler = [];
let tur = "TYT";
let girisler = {};
let tabloKabi = null;
let toplamKabi = null;
let degerlendirme = null;
let degerlendirmeKabi = null;
let aiAktif = false;
// ders_kod -> konular: denemede yanlış konu işaretlemek için
let konuHaritasi = {};

function bugunIso() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function netHesapla(g) {
  return Math.round((g.dogru - g.yanlis / 4) * 100) / 100;
}

export async function ciz(kap, durum) {
  uygulama = durum;
  const [mufredat, denemeler, hedef, analiz, aiDurum, kayit] = await Promise.all([
    api.get(`/api/mufredat/${durum.profil.id}`),
    api.get(`/api/denemeler/${durum.profil.id}`),
    api.get(`/api/hedef/${durum.profil.id}`),
    api.get(`/api/analiz/${durum.profil.id}`),
    api.get("/api/ai/durum"),
    api.get(`/api/analiz/${durum.profil.id}/degerlendirme`),
  ]);
  degerlendirme = kayit?.var ? kayit : null;
  aiAktif = Boolean(aiDurum?.aktif);
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
  dersler.forEach((d) => { girisler[d.kod] = { dogru: 0, yanlis: 0, bos: 0 }; });
  tur = "TYT";

  kap.replaceChildren(
    hedefKarti(hedef, {
      kompakt: true,
      baslik: "Denemelerin hedefe göre neresinde?",
      alt: "Her deneme, hedef sıralamanın gerektirdiği TYT/AYT netiyle karşılaştırılır.",
    }),
    konuKarti(analiz),
    degerlendirmeKarti(),
    formKarti(durum),
    listeKarti(denemeler, durum, hedef)
  );
  tabloCiz();
}

// ------------------------------------------------- konu ağırlığı analizi
function konuKarti(analiz) {
  const kart = h("section", { class: "kart" });
  kart.append(
    h(
      "div",
      { class: "kart-baslik", style: { alignItems: "center" } },
      h(
        "div",
        {},
        h("h2", { text: "Konu ağırlığı analizi" }),
        h("p", { text: "Doğru/yanlış sayıların, konuların gerçek YKS'deki beklenen soru sayısıyla birleşir." })
      ),
      h("a", { class: "dugme ikincil kucuk", href: "#/plan" }, "Programa yansıt")
    )
  );

  if (!analiz.deneme_sayisi) {
    kart.append(
      bosDurum(
        "Henüz deneme yok",
        "İlk denemeni kaydettiğinde ders bazlı doğru/yanlış, konu ağırlıklarıyla çarpılıp burada sıralanır."
      )
    );
    return kart;
  }

  const dersler = analiz.dersler.filter((d) => d.deneme_sayisi);
  const dersTablo = h("table", { class: "sonuc-tablo" });
  dersTablo.append(
    h("thead", {},
      h("tr", {},
        h("th", { text: "Ders" }),
        h("th", { text: "D/Y/B" }),
        h("th", { text: "Net" }),
        h("th", { text: "Başarı" }),
        h("th", { text: "Seviye" }))),
    h("tbody", {},
      dersler.map((d) =>
        h("tr", {},
          h("td", {},
            h("span", { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
              h("span", { class: "nokta", style: { background: d.renk } }),
              d.ad),
            h("small", { text: d.sinav, style: { display: "block", color: "#6b7280", marginTop: "2px" } })),
          h("td", { text: `${d.dogru}/${d.yanlis}/${d.bos}`, style: { fontSize: "12.5px", color: "#6b7280" } }),
          h("td", { class: "net-hucre", text: String(d.net) }),
          h("td", { text: d.basari_yuzde == null ? "—" : `${d.basari_yuzde}%` }),
          h("td", {}, rozet(d.seviye, d.seviye === "zayıf" ? "uyari" : d.seviye === "iyi" ? "basari" : ""))))
    )
  );

  const konular = analiz.en_cok_kazanc;
  const konuTablo = h("table", { class: "sonuc-tablo" });
  konuTablo.append(
    h("thead", {},
      h("tr", {},
        h("th", { text: "Konu" }),
        h("th", { text: "YKS'de beklenen" }),
        h("th", { text: "Başarı" }),
        h("th", { text: "Etkin puan" }))),
    h("tbody", {},
      konular.map((k) =>
        h("tr", {},
          h("td", {},
            h("span", { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
              h("span", { class: "nokta", style: { background: k.renk } }),
              k.ad),
            h("small", { text: `${k.ders_ad} · ${k.kaynak} verisi`, style: { display: "block", color: "#6b7280", marginTop: "2px" } })),
          h("td", { text: `${k.beklenen_soru.toFixed(1)} soru` }),
          h("td", { text: `${k.basari_yuzde}%` }),
          h("td", { class: "net-hucre", text: String(k.etkin_puan) })))
    )
  );

  kart.append(
    h("div", { style: { display: "grid", gap: "18px" } },
      h("div", {},
        h("h3", { text: "Denemelerde ders bazlı doğru/yanlış", style: { margin: "4px 0 8px", fontSize: "13.5px" } }),
        h("div", { style: { overflowX: "auto" } }, dersTablo)),
      h("div", {},
        h("h3", { text: "En çok net kazandıracak konular", style: { margin: "0 0 8px", fontSize: "13.5px" } }),
        h("div", { style: { overflowX: "auto" } }, konuTablo),
        h("p", { class: "ipucu", style: { marginTop: "10px" },
          text: "Etkin puan = beklenen soru sayısı × (1 − başarı oranı). Sıralama; hedef sıralamana göre ders payı ile ağırlıklandırılır. Günlük, haftalık ve aylık programlar bu sıradan kurulur." })),
      h("div", {},
        h("h3", { text: "Konu bazlı açıklar", style: { margin: "0 0 8px", fontSize: "13.5px" } }),
        konuAcikListesi(analiz),
        h("p", { class: "ipucu", style: { marginTop: "10px" },
          text: "Kanıt; denemede işaretlediğin yanlış konulardan ve çalışma günlüğünden gelir. Aşağıdaki deneme kartlarında 'Yanlış konuları işaretle' ile açığı konu adıyla tespit et; günlük program bu konuları öne alır. Her gün matematik ve paragraf soruları programda sabittir." }))
    )
  );

  return kart;
}

function konuAcikListesi(analiz) {
  const gruplar = analiz.konu_aciklari || [];
  if (!gruplar.length) {
    return bosDurum(
      "Henüz konu bazlı kanıt yok",
      "Deneme kartlarındaki 'Yanlış konuları işaretle' bölümünden yanlış yaptığın konuları seç; derslerin içindeki açık konular burada listelenir."
    );
  }

  return h("div", { class: "acik-konular" },
    gruplar.map((grup) =>
      h("div", { class: "acik-konu-grup" },
        h("div", { class: "acik-konu-baslik" },
          h("span", { class: "nokta", style: { background: grup.renk } }),
          h("b", { text: grup.ders }),
          rozet(`${grup.acik_sayisi} açık konu`, "uyari")),
        h("div", { class: "konu-cipleri" },
          grup.konular.map((k) =>
            h("span", { class: "rozet", title: `${k.kaynak} verisi` },
              `${k.konu} · %${k.basari_yuzde}`,
              k.deneme_yanlis
                ? h("b", { text: `${k.deneme_yanlis}Y`, style: { color: "#a01b1b" } })
                : null)))))
  );
}

// ------------------------------------------------- yapay zekâ değerlendirmesi
const SIKLIK_ETIKET = { 7: "Haftada 1 deneme", 3: "3 günde 1 deneme" };
let degerlendirDugmesi = null;

function degerlendirDugmeYaz(metin) {
  if (!degerlendirDugmesi) return;
  degerlendirDugmesi.replaceChildren(ikon("sohbet", 16), metin);
}

function degerlendirmeKarti() {
  const kart = h("section", { class: "kart" });
  degerlendirDugmesi = h("button", { class: "dugme", type: "button" });
  degerlendirDugmeYaz(degerlendirme ? "Yeniden değerlendir" : "Değerlendir");

  kart.append(
    h("div", { class: "kart-baslik", style: { alignItems: "center" } },
      h("div", {},
        h("h2", { text: "Yapay zekâ değerlendirmesi" }),
        h("p", { text: "Deneme doğru/yanlışları ve konu ağırlıkları yorumlanır; açığı kapatacak deneme sıklığı ve takvimi çıkarılır." })),
      degerlendirDugmesi)
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
    h("thead", {},
      h("tr", {},
        ["Tarih", "Sınav", "Süre", "Hedef net", "Odak konular"].map((t) => h("th", { text: t })))),
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
      h("thead", {},
        h("tr", {},
          ["Gün", "Tarih", "Matematik", "Paragraf", "Odak konular"].map((t) => h("th", { text: t })))),
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

// ------------------------------------------------------------------- form
function formKarti(durum) {
  const turSecim = h(
    "select",
    {
      class: "secim",
      onchange: (o) => {
        tur = o.target.value;
        girisler = {};
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

    if (!sonuclar.length) {
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
      });
      bildir(`Kaydedildi · tahmini TYT puanı ${yanit.ozet.puan.tyt}`);
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
    h("div", { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Yeni deneme gir" }),
        h("p", { text: "Net = doğru − yanlış/4. Boş sorular neti değiştirmez." }))),
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
  const tablo = h("table", { class: "sonuc-tablo" });
  tablo.append(
    h("thead", {},
      h("tr", {},
        h("th", { text: "Ders" }),
        h("th", { text: "Soru" }),
        h("th", { text: "Doğru" }),
        h("th", { text: "Yanlış" }),
        h("th", { text: "Boş" }),
        h("th", { text: "Net" })))
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

    govde.append(
      h("tr", {},
        h("td", {},
          h("span", { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
            h("span", { class: "nokta", style: { background: ders.renk } }),
            ders.ad)),
        h("td", { text: String(ders.soru_sayisi || "-"), style: { color: "#6b7280", fontSize: "12px" } }),
        h("td", {}, alan("dogru")),
        h("td", {}, alan("yanlis")),
        h("td", {}, alan("bos")),
        netHucre)
    );
  });

  tablo.append(govde);
  tabloKabi.replaceChildren(tablo);
  toplamlariCiz();
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
        h("p", { text: "Net gelişimi, ders kırılımı ve tahmini puan" })))
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
  const secilebilir = (deneme.satirlar || []).filter(
    (s) => s.yanlis > 0 && (konuHaritasi[s.ders_kod] || []).length
  );
  if (!secilebilir.length) return null;

  const secili = new Set((deneme.konular || []).map((k) => k.konu_id));
  const govde = h("div", { style: { display: "grid", gap: "12px", marginTop: "12px" } });

  secilebilir.forEach((satir) => {
    govde.append(
      h("div", {},
        h("div", { style: { display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" } },
          h("span", { class: "nokta", style: { background: satir.renk } }),
          h("b", { text: satir.ders, style: { fontSize: "12.5px" } }),
          h("span", { class: "ipucu", text: `${satir.yanlis} yanlış` })),
        h("div", { class: "konu-cipleri" },
          konuHaritasi[satir.ders_kod].map((konu) => {
            const cip = h("button", {
              class: `konu-cip${secili.has(konu.id) ? " aktif" : ""}`,
              type: "button",
              "aria-pressed": secili.has(konu.id) ? "true" : "false",
              onclick: () => {
                if (secili.has(konu.id)) secili.delete(konu.id);
                else secili.add(konu.id);
                cip.classList.toggle("aktif", secili.has(konu.id));
                cip.setAttribute("aria-pressed", secili.has(konu.id) ? "true" : "false");
              },
            }, konu.ad);
            return cip;
          })))
    );
  });

  const kaydet = h("button", { class: "dugme ikincil kucuk", type: "button" }, "Yanlış konuları kaydet");
  kaydet.addEventListener("click", async () => {
    kaydet.disabled = true;
    kaydet.textContent = "Kaydediliyor…";
    try {
      const konular = [...secili].map((konu_id) => ({ konu_id, yanlis: 1 }));
      const yanit = await api.post(`/api/deneme/${deneme.id}/konular`, { konular });
      bildir(`${yanit.konu_sayisi} yanlış konu kaydedildi`);
      await durum.yenile();
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
      kaydet.textContent = "Yanlış konuları kaydet";
    }
  });

  return h("details", { class: "konu-secim" },
    h("summary", { text: `Yanlış konuları işaretle${secili.size ? ` (${secili.size})` : ""}` }),
    h("p", { class: "ipucu", style: { margin: "10px 0 0" },
      text: "Yanlış yaptığın konuları seç; konu bazlı analiz ve günlük program buna göre güncellenir. Her gün matematik ve paragraf soruları programda kalır." }),
    govde,
    h("div", { style: { marginTop: "12px" } }, kaydet));
}
