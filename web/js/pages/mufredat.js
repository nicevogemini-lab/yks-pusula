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
const acikDersler = new Set();

export async function ciz(kap, durum) {
  uygulama = durum;
  veri = await api.get(`/api/mufredat/${durum.profil.id}`);
  arama = "";
  sinavFiltre = "hepsi";
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

  kap.replaceChildren(
    h(
      "section",
      { class: "kart" },
      h(
        "div",
        { class: "kart-baslik", style: { alignItems: "center" } },
        h("div", {},
          h("h2", { text: "Konu haritası" }),
          h("p", { text: `Toplam ${veri.dersler.reduce((t, d) => t + d.konular.length, 0)} konu · alanına ait TYT + AYT dersleri` })),
        h("div", { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
          filtreler,
          h("div", { style: { width: "220px" } }, aramaGirdi))
      ),
      h("p", {
        class: "ipucu",
        text: "İpucu: Yıldızlar konuya ne kadar güvendiğini gösterir (1 = zayıf, 5 = çok iyi). Plan motoru düşük yıldızlı konuları öne alır.",
      })
    ),
    listeKabi
  );

  cizListe(listeKabi);
}

function cizListe(kap = document.getElementById("konu-listesi")) {
  if (!kap) return;
  kap.replaceChildren();

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
