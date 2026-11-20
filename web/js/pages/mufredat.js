// mufredat.js — konu takibi, durum ve özgüven işaretleme
import { api } from "../api.js";
import {
  h, ikon, rozet, doluYildiz, yuzde, cubuk, bosDurum, bildir, dakikaMetni,
} from "../ui.js";

export const baslik = "Müfredat";
export const alt = "Konu durumu, özgüven ve Maarif beceri etiketleri";

const DURUM_SECENEK = [
  ["yok", "Başlanmadı"],
  ["calisiliyor", "Çalışılıyor"],
  ["tamam", "Tamamlandı"],
  ["tekrar", "Tekrar gerekli"],
];

let veri = null;
let uygulama = null;
let sinavFiltre = "hepsi";
let arama = "";
let yonetici = false;
// Açık olan düzenleme formu: { tip: "konu", dersKod, konu } | { tip: "ders", ders }
let form = null;
let ustBilgi = null;
const acikDersler = new Set();

export async function ciz(kap, durum) {
  uygulama = durum;
  // Müfredat tüm profiller için ortak: düzenleme yetkisi yalnız yöneticide
  yonetici = (durum.kullanici?.rol || "yonetici") === "yonetici";
  veri = await api.get(`/api/mufredat/${durum.profil.id}`);
  arama = "";
  sinavFiltre = "hepsi";
  form = null;
  acikDersler.clear();
  if (veri.dersler.length) acikDersler.add("TYT-MAT");

  const aramaGirdi = h("input", {
    class: "alan",
    type: "search",
    placeholder: "Konu ara…",
    oninput: (o) => { arama = o.target.value.trim().toLocaleLowerCase("tr"); cizListe(); },
  });

  const filtreler = h(
    "div",
    { style: { display: "flex", gap: "6px" } },
    [["hepsi", "Tümü"], ["TYT", "TYT"], ["AYT", "AYT"]].map(([kod, ad]) =>
      h(
        "button",
        {
          class: `dugme ${kod === "hepsi" ? "" : "ikincil"} kucuk`,
          type: "button",
          dataset: { filtre: kod },
          onclick: (o) => {
            sinavFiltre = kod;
            document.querySelectorAll("[data-filtre]").forEach((d) => {
              d.className = `dugme ${d.dataset.filtre === kod ? "" : "ikincil"} kucuk`;
            });
            cizListe();
          },
        },
        ad
      )
    )
  );

  const listeKabi = h("div", { id: "konu-listesi", style: { display: "grid", gap: "12px" } });
  ustBilgi = h("p", { text: ozetMetni() });

  kap.replaceChildren(
    h(
      "section",
      { class: "kart" },
      h(
        "div",
        { class: "kart-baslik", style: { alignItems: "center" } },
        h("div", {},
          h("h2", { text: "Konu haritası" }),
          ustBilgi),
        h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
          veri.kapsam ? rozet(`Kapsam: ${veri.kapsam.etiket}`, "marka") : null,
          filtreler,
          h("div", { style: { width: "220px" } }, aramaGirdi),
          yonetici
            ? h("button", {
                class: "dugme ikincil kucuk",
                type: "button",
                title: "Müfredata yeni ders ekle",
                onclick: () => { form = { tip: "ders", ders: null }; cizListe(); },
              }, ikon("arti", 13), "Ders ekle")
            : null)
      ),
      h("p", {
        class: "ipucu",
        text: "İpucu: Yıldızlar konuya ne kadar güvendiğini gösterir (1 = zayıf, 5 = çok iyi). Plan motoru düşük yıldızlı konuları öne alır.",
      }),
      yonetici
        ? h("p", {
            class: "ipucu",
            text: "Yönetici olarak konu ekleyebilir, düzenleyebilir ve kaldırabilirsin. Elle eklediğin ya da düzenlediğin satırlar, program açılışındaki gömülü müfredat güncellemesiyle ezilmez ya da geri gelmez.",
          })
        : null
    ),
    listeKabi
  );

  cizListe(listeKabi);
}

function ozetMetni() {
  const konuSayisi = veri.dersler.reduce((t, d) => t + d.konular.length, 0);
  const kapsam = veri.kapsam ? veri.kapsam.etiket : "alanına ait TYT + AYT dersleri";
  return `Toplam ${konuSayisi} konu · ${veri.dersler.length} ders · ${kapsam}`;
}

/** Düzenleme sonrası listeyi sunucudan tazeler */
async function yenidenYukle(mesaj) {
  veri = await api.get(`/api/mufredat/${uygulama.profil.id}`);
  form = null;
  if (ustBilgi) ustBilgi.textContent = ozetMetni();
  cizListe();
  if (mesaj) bildir(mesaj);
}

function cizListe(kap = document.getElementById("konu-listesi")) {
  if (!kap) return;
  kap.replaceChildren();

  if (yonetici && form?.tip === "ders") kap.append(dersFormu(form.ders));

  const dersler = veri.dersler.filter((d) => {
    if (sinavFiltre !== "hepsi" && d.sinav !== sinavFiltre) return false;
    if (!arama) return true;
    return d.konular.some((k) => k.ad.toLocaleLowerCase("tr").includes(arama)) ||
      d.ad.toLocaleLowerCase("tr").includes(arama);
  });

  if (!dersler.length) {
    kap.append(bosDurum("Sonuç bulunamadı", "Filtreyi veya arama metnini değiştir."));
    return;
  }
  dersler.forEach((ders) => {
    const konular = arama
      ? ders.konular.filter((k) => k.ad.toLocaleLowerCase("tr").includes(arama))
      : ders.konular;
    const tamam = ders.konular.filter((k) => k.durum === "tamam").length;
    const yuzdeDeger = yuzde(tamam, ders.konular.length);

    const detay = h("details", { class: "ders-kart", open: acikDersler.has(ders.kod) });
    detay.addEventListener("toggle", () => {
      if (detay.open) acikDersler.add(ders.kod);
      else acikDersler.delete(ders.kod);
    });

    const ozet = h(
      "summary",
      {},
      h("span", { class: "nokta", style: { background: ders.renk, width: "10px", height: "10px" } }),
      h(
        "div",
        { class: "baslik-alan" },
        h("b", { text: ders.ad }),
        h("small", { text: `${ders.sinav} · ${ders.soru_sayisi} soru · ${ders.konular.length} konu` })
      ),
      h("div", { class: "mini-cubuk" }, h("span", { style: { width: `${yuzdeDeger}%`, background: ders.renk } })),
      h("span", { class: "yuzde-cip", text: `${yuzdeDeger}%` }),
      h("span", { class: "ok" }, ikon("ok", 14))
    );

    const govde = h("div", { class: "konu-liste" });
    konular.forEach((konu) => govde.append(konuSatiri(konu, ders)));
    if (yonetici) govde.append(dersAltligi(ders));
    detay.append(ozet, govde);
    kap.append(detay);
  });
}

function konuSatiri(konu, ders) {
  const satir = h("div", { class: "konu-satir" });

  const secim = h(
    "select",
    {
      class: "secim",
      style: { fontSize: "12px", padding: "6px 8px" },
      onchange: async (o) => {
        await kaydet(konu, o.target.value, konu.guven, ders.kod);
      },
    },
    DURUM_SECENEK.map(([kod, ad]) =>
      h("option", { value: kod, selected: konu.durum === kod }, ad))
  );

  const yildizKabi = h("div", { class: "yildizlar" });
  for (let i = 1; i <= 5; i += 1) {
    const y = h(
      "button",
      {
        class: `yildiz ${konu.guven >= i ? "dolu" : ""}`.trim(),
        type: "button",
        title: `Özgüven: ${i}/5`,
        "aria-label": `Özgüven ${i}`,
      },
      doluYildiz(17)
    );
    y.addEventListener("click", () => {
      const yeniDurum = konu.durum === "yok" ? "calisiliyor" : konu.durum;
      kaydet(konu, yeniDurum, i, ders.kod);
    });
    yildizKabi.append(y);
  }

  satir.append(
    h(
      "div",
      {},
      h(
        "div",
        { class: "konu-ad" },
        konu.ad,
        konu.agirlik >= 3 ? rozet("yüksek ağırlık", "uyari") : null
      ),
      h(
        "div",
        { class: "konu-alt" },
        `${konu.sinif}. sınıf · ${dakikaMetni(konu.sure_dk)}` +
          (konu.beceri_etiket.length ? ` · ${konu.beceri_etiket.join(", ")}` : "")
      )
    ),
    h("div", { class: "durum-alan" }, secim),
    h("div", { class: "durum-alan" }, yildizKabi)
  );
  if (yonetici) {
    satir.classList.add("yonetici");
    satir.append(
      h(
        "div",
        { class: "konu-islem" },
        h(
          "button",
          {
            class: "simge-dugme",
            type: "button",
            title: "Konuyu düzenle",
            onclick: () => { form = { tip: "konu", dersKod: ders.kod, konu }; cizListe(); },
          },
          ikon("kalem", 15)
        ),
        h(
          "button",
          {
            class: "simge-dugme sil",
            type: "button",
            title: "Konuyu müfredattan kaldır",
            "aria-label": "Konuyu kaldır",
            onclick: () => konuSil(konu),
            text: "\u2715",
          }
        )
      )
    );
  }
  return satir;
}

async function kaydet(konu, yeniDurum, guven, dersKod) {
  try {
    const yanit = await api.post("/api/konu-durum", {
      profil_id: uygulama.profil.id,
      konu_id: konu.id,
      durum: yeniDurum,
      guven,
    });
    konu.durum = yeniDurum;
    konu.guven = guven;
    if (yanit.tekrar_tarihi) {
      bildir(`Kaydedildi · tekrar tarihi ${yanit.tekrar_tarihi}`);
    } else {
      bildir("Kaydedildi.");
    }
    if (!acikDersler.has(dersKod)) acikDersler.add(dersKod);
    cizListe();
  } catch (hata) {
    bildir(hata.message, "hata");
  }
}

// ------------------------------------------------------------------ yönetici
// Müfredat tüm öğrenciler için ortak olduğu için ekleme/düzenleme/silme
// yalnız yöneticiye açılır; sunucu da bu istekleri yöneticiyle sınırlar.
function formAlani(etiket, girdi, not = null) {
  return h("div", { class: "form-alan" }, h("label", { text: etiket }), girdi,
    not ? h("small", { text: not }) : null);
}

function formDugmeleri(kaydetDugmesi) {
  return h("div", { class: "dugmeler" },
    h("button", {
      class: "dugme sessiz kucuk",
      type: "button",
      onclick: () => { form = null; cizListe(); },
    }, "Vazgeç"),
    kaydetDugmesi);
}

/** Ders başlığının altındaki yönetici işlemleri ve açık konu formu */
function dersAltligi(ders) {
  const sarmal = h("div", {});
  const dugmeler = h("div", { class: "mufredat-altlik" },
    h("button", {
      class: "dugme ikincil kucuk",
      type: "button",
      onclick: () => { form = { tip: "konu", dersKod: ders.kod, konu: null }; cizListe(); },
    }, ikon("arti", 13), "Konu ekle"),
    h("button", {
      class: "dugme sessiz kucuk",
      type: "button",
      onclick: () => { form = { tip: "ders", ders }; cizListe(); },
    }, ikon("kalem", 13), "Dersi düzenle"),
    h("button", {
      class: "dugme sessiz kucuk",
      type: "button",
      title: "Dersi ve tüm konularını kaldır",
      onclick: () => dersSil(ders),
    }, "Dersi sil"));
  sarmal.append(dugmeler);
  if (form?.tip === "konu" && form.dersKod === ders.kod) sarmal.append(konuFormu(ders, form.konu));
  return sarmal;
}

/** Konu ekleme/düzenleme formu */
function konuFormu(ders, konu) {
  const yeni = !konu;
  const ad = h("input", {
    class: "alan", type: "text", maxlength: "160",
    value: konu?.ad || "", placeholder: "Konu adı",
  });
  const sinif = h("select", { class: "secim" },
    [9, 10, 11, 12].map((s) =>
      h("option", { value: s, selected: (konu?.sinif ?? 11) === s }, `${s}. sınıf`)));
  const agirlik = h("select", { class: "secim" },
    [1, 2, 3].map((a) =>
      h("option", { value: a, selected: (konu?.agirlik ?? 2) === a }, `Ağırlık ${a}`)));
  const sure = h("input", {
    class: "alan", type: "number", min: "10", max: "600", step: "15",
    value: String(konu?.sure_dk ?? 90),
  });
  const beceri = h("input", {
    class: "alan", type: "text", maxlength: "64",
    value: (konu?.beceri || []).join(","), placeholder: "KB,OK",
  });
  const onkosul = h("input", {
    class: "alan", type: "text", maxlength: "64",
    value: (konu?.onkosul || []).join(","), placeholder: "İsteğe bağlı",
  });

  const kaydetDugmesi = h("button", { class: "dugme", type: "button" },
    yeni ? "Konuyu ekle" : "Değişiklikleri kaydet");
  kaydetDugmesi.addEventListener("click", async () => {
    const govde = {
      ad: ad.value.trim(),
      sinif: Number(sinif.value),
      agirlik: Number(agirlik.value),
      sure_dk: Number(sure.value) || 90,
      beceri: beceri.value.trim(),
      onkosul: onkosul.value.trim(),
    };
    if (govde.ad.length < 2) {
      bildir("Konu adı en az 2 karakter olmalı.", "hata");
      return;
    }
    kaydetDugmesi.disabled = true;
    if (!acikDersler.has(ders.kod)) acikDersler.add(ders.kod);
    try {
      if (yeni) {
        await api.post("/api/mufredat/konu", { ders_kod: ders.kod, ...govde });
        await yenidenYukle(
          kapsamdaMi(govde.sinif)
            ? `“${govde.ad}” müfredata eklendi.`
            : `“${govde.ad}” eklendi; ${govde.sinif}. sınıf bu öğrencinin kapsamı dışında olduğu için listede görünmez.`
        );
      } else {
        await api.patch(`/api/mufredat/konu/${konu.id}`, govde);
        await yenidenYukle("Konu güncellendi.");
      }
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydetDugmesi.disabled = false;
    }
  });

  return h("div", { class: "mufredat-form" },
    h("b", { text: yeni ? `${ders.ad} · yeni konu` : `${konu.ad} · düzenle` }),
    h("div", { class: "izgara" },
      formAlani("Konu adı", ad),
      formAlani("Sınıf", sinif, "Müfredat kapsamını belirler."),
      formAlani("Ağırlık", agirlik, "Tahmini soru yoğunluğu (1-3)."),
      formAlani("Süre (dk)", sure, "İlk öğrenme için önerilen süre."),
      formAlani("Beceri", beceri, "KB, AB, SD, OK — isteğe bağlı."),
      formAlani("Ön koşul", onkosul, "Aynı dersteki konu kodları, virgüllü.")),
    formDugmeleri(kaydetDugmesi));
}

/** Ders ekleme/düzenleme formu */
function dersFormu(ders) {
  const yeni = !ders;
  const kod = h("input", {
    class: "alan", type: "text", maxlength: "16",
    value: ders?.kod || "", placeholder: "ör. AYT-FEL",
  });
  if (!yeni) kod.disabled = true;
  const ad = h("input", {
    class: "alan", type: "text", maxlength: "80",
    value: ders?.ad || "", placeholder: "Ders adı",
  });
  const sinav = h("select", { class: "secim" },
    ["TYT", "AYT"].map((s) =>
      h("option", { value: s, selected: (ders?.sinav || "TYT") === s }, s)));
  const ALAN_SECENEK = [
    ["ortak", "Ortak (herkes)"],
    ["sayisal", "Sayısal"],
    ["ea", "Eşit Ağırlık"],
    ["sozel", "Sözel"],
    ["sayisal,ea,sozel", "Tüm alanlar"],
  ];
  const alanlar = h("select", { class: "secim" },
    ALAN_SECENEK.map(([k, a]) =>
      h("option", { value: k, selected: (ders?.alanlar || "ortak") === k }, a)));
  const soru = h("input", {
    class: "alan", type: "number", min: "0", max: "200",
    value: String(ders?.soru_sayisi ?? 0),
  });
  const renk = h("input", { class: "alan", type: "color", value: ders?.renk || "#ea580c" });
  const sira = h("input", {
    class: "alan", type: "number", min: "0", max: "999",
    value: String(ders?.sira ?? 90),
  });

  const kaydetDugmesi = h("button", { class: "dugme", type: "button" },
    yeni ? "Dersi ekle" : "Değişiklikleri kaydet");
  kaydetDugmesi.addEventListener("click", async () => {
    const govde = {
      ad: ad.value.trim(),
      sinav: sinav.value,
      alanlar: alanlar.value,
      soru_sayisi: Number(soru.value) || 0,
      renk: renk.value,
      sira: Number(sira.value) || 0,
    };
    if (govde.ad.length < 2) {
      bildir("Ders adı en az 2 karakter olmalı.", "hata");
      return;
    }
    if (yeni && kod.value.trim().length < 2) {
      bildir("Ders kodu en az 2 karakter olmalı (ör. AYT-FEL).", "hata");
      return;
    }
    kaydetDugmesi.disabled = true;
    try {
      if (yeni) {
        await api.post("/api/mufredat/ders", { kod: kod.value.trim(), ...govde });
        await yenidenYukle(`“${govde.ad}” dersi eklendi. Konu eklemek için dersin altındaki “Konu ekle”yi kullan.`);
      } else {
        await api.patch(`/api/mufredat/ders/${ders.kod}`, govde);
        await yenidenYukle("Ders güncellendi.");
      }
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydetDugmesi.disabled = false;
    }
  });

  return h("section", { class: "kart mufredat-form" },
    h("div", { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: yeni ? "Yeni ders" : `${ders.ad} · dersi düzenle` }),
        h("p", { text: "Ders eklenince öğrencilerin müfredatında hemen görünür; konuları ayrıca eklenir." }))),
    h("div", { class: "izgara" },
      formAlani("Ders kodu", kod, "Benzersiz: ör. AYT-FEL."),
      formAlani("Ders adı", ad),
      formAlani("Sınav", sinav),
      formAlani("Alan", alanlar, "Ders hangi alanların müfredatına girer."),
      formAlani("Soru sayısı", soru),
      formAlani("Renk", renk),
      formAlani("Sıra", sira, "Ders listesindeki yeri (küçük önce).")),
    formDugmeleri(kaydetDugmesi));
}

/** Konu bu öğrencinin sınıf kapsamında mı? */
function kapsamdaMi(sinif) {
  const aralik = veri.kapsam?.aralik || [];
  if (!aralik.length) return true; // mezun: tüm müfredat
  return aralik.includes(sinif);
}

async function konuSil(konu) {
  const onay = window.confirm(
    `“${konu.ad}” konusu müfredattan kaldırılsın mı?\n\nÖğrencilerin bu konudaki durum/tekrar kayıtları ve geçmiş denemelerdeki konu kırılımı silinir.`
  );
  if (!onay) return;
  try {
    await api.sil(`/api/mufredat/konu/${konu.id}`);
    await yenidenYukle(`“${konu.ad}” kaldırıldı.`);
  } catch (hata) {
    bildir(hata.message, "hata");
  }
}

async function dersSil(ders) {
  const onay = window.confirm(
    `“${ders.ad}” dersi ve altındaki ${ders.konular.length} konu kaldırılsın mı?`
  );
  if (!onay) return;
  try {
    await api.sil(`/api/mufredat/ders/${ders.kod}`);
    await yenidenYukle(`“${ders.ad}” kaldırıldı.`);
  } catch (hata) {
    bildir(hata.message, "hata");
  }
}
