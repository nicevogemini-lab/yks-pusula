// plan.js — günlük / haftalık / aylık çalışma programı
import { api } from "../api.js";
import { h, ikon, tarihTr, kisaTarih, dakikaMetni, bildir, bosDurum } from "../ui.js";
import { planMaddesi } from "./panel.js";
import { hedefKarti } from "../hedef-karti.js";

export const baslik = "Çalışma Planı";
export const alt = "Günlük, haftalık ve aylık program · konu ağırlığına göre";

let donem = "gunluk";

export async function ciz(kap, durum) {
  const [veri, hedef] = await Promise.all([
    donemVerisi(durum.profil.id),
    api.get(`/api/hedef/${durum.profil.id}`),
  ]);

  kap.replaceChildren(
    ustKart(veri, durum, hedef),
    hedefKarti(hedef, {
      kompakt: true,
      baslik: "Bu program hangi hedefe göre kuruldu?",
      alt: "Ders payları, hedef sıralamanın gerektirdiği netlerden hesaplanır. En büyük açığı olan ders en çok blok alır.",
    }),
    ...govde(veri, durum)
  );
}

async function donemVerisi(profilId) {
  if (donem === "haftalik") return api.get(`/api/plan/${profilId}/ozet?gun=7`);
  if (donem === "aylik") return api.get(`/api/plan/${profilId}/aylik?hafta=4`);
  return api.get(`/api/plan/${profilId}?gun=7`);
}

// ------------------------------------------------------------------- üst kart
function ustKart(veri, durum, hedef) {
  const aylik = donem === "aylik";
  const uret = h(
    "button",
    { class: "dugme kucuk", type: "button" },
    ikon("arti", 15),
    aylik ? "4 haftalık planı oluştur" : "Planı yeniden üret"
  );
  uret.addEventListener("click", async () => {
    uret.disabled = true;
    uret.textContent = "Üretiliyor…";
    try {
      const yol = aylik
        ? `/api/plan/${durum.profil.id}/aylik-uret?hafta=4`
        : `/api/plan/${durum.profil.id}/uret?gun=7`;
      const yanit = await api.post(yol);
      bildir(`${yanit.eklenen} plan maddesi oluşturuldu.`);
      await durum.yenile();
    } catch (hata) {
      bildir(hata.message, "hata");
      uret.disabled = false;
      uret.textContent = aylik ? "4 haftalık planı oluştur" : "Planı yeniden üret";
    }
  });

  const cerceve = veri.zaman_cercevesi;
  const altYazi = aylik
    ? `${veri.hafta_sayisi} hafta · ${tarihTr(veri.baslangic)} – ${tarihTr(veri.bitis)} · haftalık hedef +${hedef.haftalik_gereken_net} net`
    : `Günlük hedef ${dakikaMetni(durum.profil.gunluk_hedef_dk)} · haftalık hedef +${hedef.haftalik_gereken_net} net${
        cerceve ? ` · gün ${cerceve.uyanma}–${cerceve.yatis}` : ""
      }`;

  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik", style: { alignItems: "center" } },
      h("div", {}, h("h2", { text: "Çalışma programı" }), h("p", { text: altYazi })),
      h(
        "div",
        { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
        h("a", { class: "dugme ikincil kucuk", href: "#/mufredat" }, "Konu durumları"),
        uret
      )
    ),
    sekmeler(durum),
    h("p", {
      class: "ipucu",
      text: "Program üç kaynağa göre kurulur: deneme sonuçları (yanlış çıkan konu öne alınır), YKS kazanım ağırlığı ve PDR önerileri (8 saat uyku, en fazla 50 dakikalık bloklar, 10 dakika mola, okul sonrası geçiş molası, haftada bir yarım gün serbest). Aylık görünümde hafta içi konu blokları, cumartesi gerçek saatinde deneme, pazar tekrar ve sosyal-duygusal öz değerlendirme yer alır.",
    })
  );
}

function sekmeler(durum) {
  const secenekler = [
    ["gunluk", "Günlük"],
    ["haftalik", "Haftalık"],
    ["aylik", "Aylık"],
  ];
  return h(
    "div",
    { class: "plan-sekmeler", role: "tablist" },
    secenekler.map(([kod, ad]) =>
      h(
        "button",
        {
          type: "button",
          class: `plan-sekme ${donem === kod ? "aktif" : ""}`.trim(),
          role: "tab",
          "aria-selected": donem === kod ? "true" : "false",
          onclick: async () => {
            if (donem === kod) return;
            donem = kod;
            await durum.yenile();
          },
        },
        ad
      )
    )
  );
}

// -------------------------------------------------------------------- gövdeler
function govde(veri, durum) {
  if (donem === "haftalik") return [haftalikKart(veri)];
  if (donem === "aylik") return [aylikKart(veri)];
  return [gunlukListe(veri, durum), pdrKarti(veri), beceriKarti(veri)];
}

const AKIS_ETIKET = {
  okul: "Okul",
  yemek: "Öğün",
  mola: "Mola",
  hazirlik: "Hazırlık",
  ulasim: "Yol",
  serbest: "Serbest",
  gelisim: "SD",
  uyku: "Uyku",
  deneme: "Deneme",
  calisma: "Çalışma",
  bos: "Boş",
};

function ozetCip(ad, deger) {
  return h("span", { class: "akis-ozet-cip" }, h("i", { text: ad }), h("b", { text: deger }));
}

// Gün akışında bir satır: rutin dilimi ya da tamamlanabilir plan maddesi
function akisSatiri(dilim, gun, durum) {
  const saat = h(
    "div",
    { class: "akis-saat" },
    h("b", { text: dilim.baslangic }),
    dilim.bitis && dilim.bitis !== dilim.baslangic ? h("span", { text: dilim.bitis }) : null
  );

  if (dilim.kaynak === "plan") {
    const madde = gun.maddeler.find((m) => m.id === dilim.madde_id);
    if (madde) {
      return h(
        "div",
        { class: "akis-satir plan" },
        saat,
        h("div", { class: "akis-govde" }, planMaddesi(madde, durum))
      );
    }
  }

  return h(
    "div",
    { class: `akis-satir ${dilim.tur}`.trim() },
    saat,
    h(
      "div",
      { class: "akis-govde" },
      h(
        "div",
        { class: "akis-ust" },
        h("span", { class: "akis-tur", text: AKIS_ETIKET[dilim.tur] || dilim.tur }),
        h("b", { text: dilim.baslik })
      ),
      dilim.aciklama ? h("p", { class: "akis-not", text: dilim.aciklama }) : null
    )
  );
}

function gunlukListe(veri, durum) {
  const tumMaddeler = veri.gunler.flatMap((g) => g.maddeler);
  const toplamDk = tumMaddeler.reduce((t, m) => t + m.sure_dk, 0);
  const tamamDk = tumMaddeler.filter((m) => m.durum === "tamam").reduce((t, m) => t + m.sure_dk, 0);

  const gunler = h("div", { style: { display: "grid", gap: "12px" } });
  veri.gunler.forEach((gun) => {
    const blok = h("div", { class: `gun-blok ${gun.bugun ? "bugun" : ""}`.trim() });
    const bitti = gun.maddeler.filter((m) => m.durum === "tamam").length;
    const gunDk = gun.maddeler.reduce((t, m) => t + m.sure_dk, 0);
    blok.append(
      h(
        "div",
        { class: "gun-ust" },
        h("b", { text: gun.gun_adi }),
        h("span", { class: "tarih", text: tarihTr(gun.tarih) }),
        h("span", {
          class: `rozet ${gun.gun_tipi === "deneme" ? "uyari" : ""}`.trim(),
          text: gun.gun_tipi_etiketi,
        }),
        gun.bugun ? h("span", { class: "rozet marka", text: "bugün" }) : null,
        h("span", {
          class: "toplam",
          text: `${bitti}/${gun.maddeler.length} tamam · ${dakikaMetni(gunDk)}`,
        })
      ),
      h(
        "div",
        { class: "gun-ozet" },
        ozetCip("Uyanış", gun.uyanma),
        ozetCip("Yatış", gun.yatis),
        gun.okul ? ozetCip("Okul", `${gun.okul.baslangic}–${gun.okul.bitis}`) : null,
        gun.okul && gun.okul.donus ? ozetCip("Dönüş", gun.okul.donus) : null,
        ozetCip("Çalışma", dakikaMetni(gun.ozet.calisma_dk)),
        ozetCip("Mola", dakikaMetni(gun.ozet.mola_dk)),
        ozetCip("Uyku", `${gun.ozet.uyku_saat} saat`)
      ),
      h(
        "div",
        { class: "gun-akis" },
        gun.akis.map((dilim) => akisSatiri(dilim, gun, durum))
      )
    );
    if (gun.notlar && gun.notlar.length) {
      blok.append(h("p", { class: "gun-not", text: gun.notlar.join(" · ") }));
    }
    gunler.append(blok);
  });

  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h(
        "div",
        {},
        h("h2", { text: "Günlük program (7 gün)" }),
        h("p", {
          text: `${tamamDk} / ${toplamDk} dakika tamamlandı · günlük hedef ${dakikaMetni(
            durum.profil.gunluk_hedef_dk
          )} · sabah uyanıştan gece yatışa tam gün akışı`,
        })
      )
    ),
    gunler
  );
}

// Programın dayandığı PDR ilkeleri: okul, öğün, mola, uyku ve deneme kurgusu
function pdrKarti(veri) {
  const z = veri.zaman_cercevesi || {};
  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h(
        "div",
        {},
        h("h2", { text: "Gün nasıl kurgulandı?" }),
        h("p", {
          text: `Uyanış ${z.uyanma || "—"} · okul ${z.okul_baslangic || "—"}–${
            z.okul_bitis || "—"
          }${z.okul_donus ? `, eve dönüş ${z.okul_donus}` : ""} · yatış ${z.yatis || "—"}. Saatler Ayarlar'dan öğrencinin gerçek düzenine göre değiştirilebilir; program her değişiklikte yeniden kurulur.`,
        })
      ),
      h("span", { class: "rozet", text: "PDR ilkeleri" })
    ),
    h(
      "div",
      { class: "pdr-izgara" },
      veri.pdr_ilkeleri.map((ilke) =>
        h("div", { class: "pdr-kart" }, h("b", { text: ilke.baslik }), h("p", { text: ilke.metin }))
      )
    )
  );
}

function beceriKarti(veri) {
  const satirlar = veri.beceri_dengesi || [];
  const kart = h("section", { class: "kart" });
  kart.append(
    h(
      "div",
      { class: "kart-baslik" },
      h(
        "div",
        {},
        h("h2", { text: "Beceri dengesi (Maarif Modeli)" }),
        h("p", {
          text: "Haftanın çalışma dakikaları, konuların beceri kodlarına göre dağıtılır: KB kavramsal, AB alan, SD sosyal-duygusal, OK okuryazarlık.",
        })
      )
    )
  );

  if (satirlar.length) {
    kart.append(
      h(
        "div",
        { style: { overflowX: "auto" } },
        h(
          "table",
          { class: "sonuc-tablo" },
          h(
            "thead",
            {},
            h(
              "tr",
              {},
              h("th", { text: "Beceri" }),
              h("th", { text: "Dakika" }),
              h("th", { text: "Pay" }),
              h("th", {})
            )
          ),
          h(
            "tbody",
            {},
            satirlar.map((s) =>
              h(
                "tr",
                {},
                h("td", { text: s.ad }),
                h("td", { text: dakikaMetni(s.dk) }),
                h("td", { text: `%${s.pay}` }),
                h(
                  "td",
                  {},
                  h("div", { class: "beceri-cubuk" }, h("span", { style: { width: `${s.pay}%` } }))
                )
              )
            )
          )
        )
      )
    );
  }

  const odak = veri.deneme_odagi;
  if (odak) {
    const konular = (odak.konular || []).map((k) => `${k.konu} (${k.yanlis} yanlış)`).join(", ");
    kart.append(
      h("p", {
        class: "ipucu",
        text: `Deneme sonuçları: haftanın %${odak.pay} oranındaki bölümü (${dakikaMetni(
          odak.dakika
        )}) denemede yanlış çıkan ${odak.konu_sayisi} konuya ayrıldı${konular ? " · " + konular : ""}.`,
      })
    );
  }

  return kart;
}

function haftalikKart(ozet) {
  const kart = h("section", { class: "kart" });
  kart.append(
    h(
      "div",
      { class: "kart-baslik" },
      h(
        "div",
        {},
        h("h2", { text: "Haftalık özet" }),
        h("p", {
          text: `${tarihTr(ozet.baslangic)} – ${tarihTr(ozet.bitis)} · ${ozet.madde_sayisi} madde · ${dakikaMetni(ozet.toplam_dk)}`,
        })
      ),
      h("span", { class: "rozet marka", text: `%${ozet.tamam_orani} tamamlandı` })
    )
  );

  if (!ozet.madde_sayisi) {
    kart.append(bosDurum("Bu hafta için plan yok", "Günlük sekmesinden planı üret, sonra buraya dön."));
    return kart;
  }

  kart.append(
    dersTablosu(ozet.dersler, ozet.toplam_dk),
    h("div", { class: "alt-satirlar", style: { marginTop: "12px" } },
      h("span", { class: "mini-net" }, "Haftalık hedef net ", h("b", { text: `+${ozet.hedef.haftalik_gereken_net}` })),
      h("span", { class: "mini-net" }, "Hedef sıralama ", h("b", { text: String(ozet.hedef.hedef_siralama) })),
      ozet.deneme_gunleri.length
        ? h("span", { class: "rozet uyari", text: `deneme: ${ozet.deneme_gunleri.map((t) => kisaTarih(t)).join(", ")}` })
        : null)
  );
  return kart;
}

function aylikKart(aylik) {
  const kart = h("section", { class: "kart" });
  kart.append(
    h(
      "div",
      { class: "kart-baslik" },
      h(
        "div",
        {},
        h("h2", { text: "Aylık program" }),
        h("p", {
          text: `${tarihTr(aylik.baslangic)} – ${tarihTr(aylik.bitis)} · haftalık hedef +${aylik.hedef.haftalik_gereken_net} net`,
        })
      ),
      aylik.uretilmis
        ? h("span", { class: "rozet basari", text: "takvim oluşturuldu" })
        : h("span", { class: "rozet uyari", text: "takvim bekliyor" })
    )
  );

  if (!aylik.uretilmis) {
    kart.append(
      h("p", {
        class: "ipucu",
        text: "Henüz 4 haftalık takvim üretilmedi. Yukarıdaki düğmeyle oluştur: hafta içi konu blokları, cumartesi deneme, pazar tekrar ve hata defteri yerleşir.",
      })
    );
  }

  const haftalar = h("div", { style: { display: "grid", gap: "12px", marginTop: "12px" } });
  aylik.haftalar.forEach((hafta) => haftalar.append(haftaKarti(hafta)));
  kart.append(haftalar);
  return kart;
}

function haftaKarti(hafta) {
  const blok = h("div", { class: "gun-blok" });
  blok.append(
    h(
      "div",
      { class: "gun-ust" },
      h("b", { text: `${hafta.hafta}. hafta` }),
      h("span", { class: "tarih", text: `${kisaTarih(hafta.baslangic)} – ${kisaTarih(hafta.bitis)}` }),
      h("span", { class: "toplam", text: `${dakikaMetni(hafta.toplam_dk)} / hedef ${dakikaMetni(hafta.hedef_dk)}` })
    )
  );

  const icerik = h("div", { style: { padding: "12px 14px", display: "grid", gap: "10px" } });
  icerik.append(
    h(
      "div",
      { style: { display: "flex", gap: "6px", flexWrap: "wrap" } },
      hafta.odak_konular.map((k) =>
        h("span", {
          class: "rozet",
          title: `${k.beklenen_soru} soru · %${k.basari_yuzde} başarı · ${k.kaynak}`,
          text: `${k.konu} · ${k.ders}`,
        })
      )
    )
  );

  icerik.append(
    h(
      "p",
      { style: { fontSize: "12.5px", color: "#6b7280", margin: 0 } },
      hafta.deneme_tarihleri.length
        ? `Deneme günü: ${hafta.deneme_tarihleri.map((t) => tarihTr(t)).join(", ")} · kümülatif hedef +${hafta.hedef_net} net`
        : hafta.madde_sayisi
          ? `Bu hafta deneme günü yok · kümülatif hedef +${hafta.hedef_net} net`
          : `Bu hafta takvimi henüz üretilmedi · kümülatif hedef +${hafta.hedef_net} net`
    )
  );

  if (hafta.dersler.length) icerik.append(dersTablosu(hafta.dersler, hafta.toplam_dk));
  blok.append(icerik);
  return blok;
}

function dersTablosu(dersler, toplamDk) {
  const tablo = h("table", { class: "sonuc-tablo" });
  tablo.append(
    h(
      "thead",
      {},
      h("tr", {},
        h("th", { text: "Ders" }),
        h("th", { text: "Dakika" }),
        h("th", { text: "Pay" }),
        h("th", { text: "Tamamlanan" }))
    ),
    h(
      "tbody",
      {},
      dersler.map((d) =>
        h("tr", {},
          h("td", {},
            h("span", { style: { display: "inline-flex", alignItems: "center", gap: "7px" } },
              h("span", { class: "nokta", style: { background: d.renk } }),
              d.ad),
            d.sinav ? h("small", { text: d.sinav, style: { display: "block", color: "#6b7280", marginTop: "2px" } }) : null),
          h("td", { text: dakikaMetni(d.dk) }),
          h("td", { text: toplamDk ? `${Math.round((100 * d.dk) / toplamDk)}%` : "—" }),
          h("td", { class: "net-hucre", text: `${d.tamam}/${d.madde}` }))
      )
    )
  );
  return h("div", { style: { overflowX: "auto" } }, tablo);
}
