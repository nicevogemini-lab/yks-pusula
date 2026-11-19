// hedef-karti.js — hedef başarı sıralamasından türetilen net hedefleri
import { h, ikon, rozet, cubuk } from "./ui.js";

/** 20000 -> "20.000", 10.5 -> "10,5" */
export function sayiMetni(deger, basamak = 1) {
  const n = Number(deger) || 0;
  return n.toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: basamak });
}

/**
 * Kısa özet (/api/panel -> hedef) ile tam analizi (/api/hedef/{id}) aynı biçime getirir.
 */
export function hedefOzeti(hedef) {
  if (!hedef) return null;
  const dersler = Array.isArray(hedef.dersler) ? hedef.dersler : null;
  return {
    ...hedef,
    hedef_siralama: hedef.gecerli_hedef ?? hedef.hedef_siralama,
    en_buyuk_aciklar:
      hedef.en_buyuk_aciklar ||
      (dersler
        ? dersler
            .filter((s) => s.acik > 0)
            .slice(0, 5)
            .map((s) => ({ ders: s.ad, renk: s.renk, hedef: s.hedef_net, mevcut: s.mevcut_net, acik: s.acik }))
        : []),
  };
}

/**
 * Hedef sıralama kartı. Panel, plan ve deneme sayfalarında ortak kullanılır.
 * @param {object} girdi  /api/panel -> hedef (kısa özet) ya da /api/hedef/{id} (tam analiz)
 * @param {{baslik?:string, alt?:string, kompakt?:boolean}} secenek
 */
export function hedefKarti(girdi, secenek = {}) {
  const hedef = hedefOzeti(girdi);
  const {
    baslik = "Hedef başarı sıralaması",
    alt = "Ders seçimi ve 7 günlük program bu hedeften türetilir: en büyük açığı olan ders en çok blok alır.",
    kompakt = false,
  } = secenek;

  const kart = h("section", { class: `kart hedef-kart ${kompakt ? "kompakt" : ""}`.trim() });
  if (!hedef || !hedef.tyt_hedef_net) {
    kart.append(
      h("div", { class: "kart-baslik" },
        h("div", {}, h("h2", { text: baslik }),
          h("p", { text: "Hedef sıralama okunamadı. Ayarlardan hedefini girip planı yenile." }))),
      h("a", { class: "dugme ikincil kucuk", href: "#/ayarlar" }, "Hedefi gir")
    );
    return kart;
  }

  const rozetler = h("div", { class: "hedef-rozetler" });
  rozetler.append(
    hedef.varsayilan
      ? rozet("sıralama girilmedi · varsayılan", "uyari")
      : rozet(`hedefin %${hedef.tamamlanma} tamam`, hedef.tamamlanma >= 90 ? "basari" : "marka"),
    h("a", { class: "dugme sessiz kucuk", href: "#/ayarlar" }, "Hedefi değiştir")
  );

  kart.append(
    h("div", { class: "kart-baslik" },
      h("div", {}, h("h2", { text: baslik }), h("p", { text: alt })),
      rozetler),
    h("div", { class: "hedef-govde" },
      h("div", { class: "hedef-buyuk" },
        h("div", { class: "etiket" }, ikon("hedef", 14), h("span", { text: "Hedef sıralama" })),
        h("div", { class: "sayi" },
          sayiMetni(hedef.hedef_siralama, 0),
          h("small", { text: "sıralama" })),
        h("div", {
          class: "alt",
          text: hedef.varsayilan
            ? "Sıralama girilmedi; 100.000 eşdeğeri kullanılıyor."
            : `Haftada ~${sayiMetni(hedef.haftalik_gereken_net)} net kapatman gerekiyor.`,
        })),
      h("div", { class: "hedef-netler" },
        netSatiri("TYT", hedef.tyt_hedef_net, hedef.tyt_mevcut_net, hedef.tyt_acik),
        netSatiri("AYT", hedef.ayt_hedef_net, hedef.ayt_mevcut_net, hedef.ayt_acik))),
    acikListesi(hedef)
  );
  return kart;
}

function netSatiri(etiket, hedefNet, mevcutNet, acikNet) {
  const oran = hedefNet ? Math.min(100, Math.round((mevcutNet / hedefNet) * 100)) : 0;
  const tamam = acikNet <= 0;
  return h("div", { class: "hedef-net" },
    h("div", { class: "ust" },
      h("b", { text: etiket }),
      h("span", { class: "deger" },
        sayiMetni(mevcutNet),
        h("small", { text: ` / ${sayiMetni(hedefNet)} net` })),
      h("span", {
        class: `acik ${tamam ? "tamam" : ""}`.trim(),
        text: tamam ? "hedefe ulaşıldı" : `${sayiMetni(acikNet)} net açık`,
      })),
    h("div", { style: { marginTop: "6px" } }, cubuk(oran)));
}

function acikListesi(hedef) {
  const aciklar = hedef.en_buyuk_aciklar || [];
  const sarici = h("div", { class: "hedef-aciklar" });

  if (!aciklar.length) {
    sarici.append(h("span", { class: "rozet basari", text: "Tüm derslerde hedefe ulaşıldı — bakım moduna geç" }));
    return sarici;
  }

  sarici.append(h("span", { class: "hedef-acik-baslik", text: "En büyük açıklar" }));
  aciklar.forEach((a) => {
    sarici.append(
      h("span", { class: "acik-cip" },
        h("span", { class: "nokta", style: { background: a.renk || "#9ca3af" } }),
        h("b", { text: a.ders }),
        h("span", { class: "sayi", text: `${sayiMetni(a.mevcut)} → ${sayiMetni(a.hedef)} net` }),
        h("span", { class: "kalan", text: `−${sayiMetni(a.acik)}` }))
    );
  });
  return sarici;
}
