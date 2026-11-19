// panel.js — günlük özet ekranı
import { api } from "../api.js";
import {
  h, ikon, rozet, tarihTr, kisaTarih, dakikaMetni, yuzde, halka, cubuk,
  bosDurum, bildir,
} from "../ui.js";
import { hedefKarti } from "../hedef-karti.js";

export const baslik = "Panel";
export const alt = "Bugünkü durumun ve öncelikli konuların";

export async function ciz(kap, durum) {
  const veri = await api.get(`/api/panel/${durum.profil.id}`);
  kap.replaceChildren(
    h("section", { class: "izgara ozet-serit" },
      sayacKarti(veri),
      ilerlemeKarti(veri),
      bugunOzetKarti(veri),
      denemeOzetKarti(veri)),
    maarifSeridi(),
    hedefKarti(veri.hedef),
    h("div", { class: "izgara izgara-panel" },
      bugunPlanKarti(veri, durum),
      oncelikKarti(veri)),
    h("div", { class: "izgara izgara-2" },
      haftaKarti(veri),
      dersIlerlemeKarti(veri)),
    sonDenemelerKarti(veri)
  );
}

// ------------------------------------------------------------------ kartlar
function sayacKarti(veri) {
  const gun = veri.kalan_gun;
  return h(
    "article",
    { class: "kart sayac-kart" },
    h("div", { class: "etiket", text: "Sınava kalan" }),
    h("div", { class: "buyuk" }, String(Math.max(0, gun)), h("small", { text: "gün" })),
    h("div", {
      class: "alt",
      text: `${tarihTr(veri.profil.sinav_tarihi)} · ${veri.profil.alan_etiketi} / ${veri.profil.sinif_etiketi}`,
    })
  );
}

function ilerlemeKarti(veri) {
  const y = veri.ilerleme.yuzde;
  return h(
    "article",
    { class: "kart stat" },
    h("div", { class: "etiket", text: "Müfredat ilerlemesi" }),
    h(
      "div",
      { class: "halka-sarici", style: { marginTop: "6px" } },
      halka(y, 76),
      h(
        "div",
        { class: "halka-metin" },
        h("b", { text: `${veri.ilerleme.tamam} / ${veri.ilerleme.toplam}` }),
        document.createTextNode("konu tamamlandı")
      )
    )
  );
}

function bugunOzetKarti(veri) {
  const { tamam_dk, hedef_dk } = veri.bugun;
  const y = yuzde(tamam_dk, hedef_dk);
  return h(
    "article",
    { class: "kart stat" },
    h("div", { class: "etiket", text: "Bugünkü çalışma" }),
    h("div", { class: "deger" },
      dakikaMetni(tamam_dk),
      h("small", { text: ` / ${dakikaMetni(hedef_dk)}` })),
    h("div", { style: { marginTop: "8px" } }, cubuk(y)),
    h("div", { class: "fark", text: `Hedefin %${y} tamamlandı` })
  );
}

function denemeOzetKarti(veri) {
  const son = veri.son_denemeler[0];
  return h(
    "article",
    { class: "kart stat" },
    h("div", { class: "etiket", text: son ? `Son ${son.tur} denemesi` : "Deneme durumu" }),
    h(
      "div",
      { class: "deger" },
      son ? String(son.toplam_net) : "—",
      son ? h("small", { text: " net" }) : null
    ),
    h("div", {
      class: "fark",
      text: son ? `${kisaTarih(son.tarih)} · tahmini puan ${son.puan.yerlestirme}` : "Henüz deneme girilmedi",
    }),
    h(
      "div",
      { class: "fark", style: { marginTop: "4px" } },
      rozet(`${veri.seri} günlük seri`, veri.seri >= 3 ? "basari" : "")
    )
  );
}

function maarifSeridi() {
  return h(
    "section",
    { class: "maarif-serit" },
    h("div", { class: "ikon-kutu" }, ikon("hedef", 18)),
    h(
      "div",
      {},
      h("b", { text: "2028 YKS: beceri ve bağlam temelli soru modeli" }),
      h("p", {
        text: "Bu kuşak, Türkiye Yüzyılı Maarif Modeli ile sınava giren ilk grup. Program; kavramsal beceri, alan becerisi, sosyal-duygusal beceri ve okuryazarlık boyutlarını her konuda takip eder — ezber yerine bilgiyi yeni duruma uygulamayı hedefler.",
      })
    )
  );
}

function bildirimBasligi(konu, duyuru) {
  return h("div", { class: "kart-baslik" }, h("div", {}, h("h2", { text: konu }), duyuru ? h("p", { text: duyuru }) : null));
}

function bugunPlanKarti(veri, durum) {
  const liste = h("div", { class: "plan-liste" });
  if (!veri.bugun.plan.length) {
    liste.append(
      bosDurum("Bugün için plan maddesi yok", "Plan sayfasından yeni bir program üretebilirsin.")
    );
  }
  veri.bugun.plan.forEach((madde) => liste.append(planMaddesi(madde, durum)));

  const toplam = veri.bugun.plan.length;
  const bitti = veri.bugun.plan.filter((m) => m.durum === "tamam").length;

  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Bugünün planı" }),
        h("p", { text: `${bitti}/${toplam} madde tamam · hedef ${dakikaMetni(veri.bugun.hedef_dk)}` })),
      h("a", { class: "dugme ikincil kucuk", href: "#/plan" }, "Haftalık plan")
    ),
    liste
  );
}

export function planMaddesi(madde, durum) {
  const kutu = h("div", { class: `plan-madde ${madde.durum === "tamam" ? "tamam" : ""}`.trim() });
  const onay = h(
    "button",
    {
      class: "plan-onay",
      type: "button",
      title: madde.durum === "tamam" ? "Geri al" : "Tamamlandı olarak işaretle",
      "aria-label": "Tamamlandı olarak işaretle",
    },
    ikon("tik", 13)
  );

  onay.addEventListener("click", async () => {
    const yeniDurum = madde.durum === "tamam" ? "bekliyor" : "tamam";
    onay.disabled = true;
    try {
      await api.post(`/api/plan-madde/${madde.id}?durum=${yeniDurum}`);
      madde.durum = yeniDurum;
      kutu.className = `plan-madde ${yeniDurum === "tamam" ? "tamam" : ""}`.trim();
      if (yeniDurum === "tamam") bildir("Çalışma kaydedildi.");
      if (durum?.yenile) setTimeout(() => durum.yenile(), 260);
    } catch (hata) {
      bildir(hata.message, "hata");
    } finally {
      onay.disabled = false;
    }
  });

  const turEtiket = { konu: "Konu", soru: "Soru", tekrar: "Tekrar", deneme: "Deneme" }[madde.tur] || madde.tur;

  kutu.append(
    onay,
    h(
      "div",
      { class: "icerik" },
      h("div", { class: "baslik", text: madde.baslik }),
      h(
        "div",
        { class: "meta" },
        h("span", { class: "nokta", style: { background: madde.renk || "#ea580c" } }),
        h("span", { text: `${turEtiket} · ${madde.ders || madde.ders_kod}` }),
        madde.baslangic
          ? h("span", { class: "saat-cip", text: `${madde.baslangic}–${madde.bitis || ""}` })
          : null,
        ...(madde.beceri || []).map((kod) => h("span", { class: "beceri-cip", text: kod }))
      )
    ),
    h("span", { class: "sure-cip", text: dakikaMetni(madde.sure_dk) })
  );
  return kutu;
}

function oncelikKarti(veri) {
  const liste = h("div", { class: "oncelik-liste" });
  if (!veri.oncelikli.length) {
    liste.append(bosDurum("Tüm konular tamam", "Deneme analizine geçme zamanı."));
  }
  veri.oncelikli.forEach((konu, i) => {
    liste.append(
      h(
        "div",
        { class: "oncelik-oge" },
        h("span", { class: "sira", text: String(i + 1) }),
        h(
          "div",
          { style: { minWidth: 0 } },
          h("div", { class: "ad", text: konu.ad }),
          h("div", { class: "meta", text: `${konu.ders} · ${konu.sinif}. sınıf · ağırlık ${konu.puan}` })
        )
      )
    );
  });

  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Şimdi odaklan" }),
        h("p", { text: "Sınav ağırlığı + özgüven açığına göre sıralandı" })),
      h("a", { class: "dugme sessiz kucuk", href: "#/mufredat" }, "Müfredat")
    ),
    liste
  );
}

function haftaKarti(veri) {
  const enBuyuk = Math.max(...veri.hafta.map((g) => Math.max(g.plan_dk, g.tamam_dk)), 60);
  const grafik = h("div", { class: "hafta-grafik" });
  veri.hafta.forEach((gun, i) => {
    const oran = Math.round((gun.tamam_dk / enBuyuk) * 100);
    const bugunMu = i === veri.hafta.length - 1;
    const bosMu = !gun.tamam_dk;
    grafik.append(
      h(
        "div",
        { class: `grafik-gun ${bugunMu ? "bugun" : ""} ${bosMu ? "bos-gun" : ""}`.trim() },
        h("div", {
          class: "grafik-cubuk",
          title: bosMu
            ? `${gun.gun} · ${dakikaMetni(gun.plan_dk)} planlandı, çalışma yok`
            : `${gun.gun} · ${dakikaMetni(gun.tamam_dk)} / ${dakikaMetni(gun.plan_dk)}`,
        }, bosMu ? null : h("div", { class: "dolu", style: { height: `${Math.max(6, oran)}%` } })),
        h("small", { text: gun.gun })
      )
    );
  });

  const toplam = veri.hafta.reduce((t, g) => t + g.tamam_dk, 0);
  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Haftalık çalışma" }),
        h("p", { text: `Son 7 günde ${dakikaMetni(toplam)} tamamlandı` }))
    ),
    grafik
  );
}

function dersIlerlemeKarti(veri) {
  const liste = h("div", { class: "ders-liste" });
  veri.dersler.forEach((ders) => {
    liste.append(
      h(
        "div",
        { class: "ders-satir" },
        h("div", { class: "ad" },
          h("span", { class: "nokta", style: { background: ders.renk } }),
          ders.ad,
          ders.sinav === "AYT" ? rozet("AYT", "marka") : null),
        h("div", { class: "sayi", text: `${ders.tamam}/${ders.toplam}` }),
        cubuk(ders.yuzde, ders.renk)
      )
    );
  });

  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Ders bazlı ilerleme" }),
        h("p", { text: "Alanına ait dersler" })),
      h("a", { class: "dugme sessiz kucuk", href: "#/mufredat" }, "Detay")
    ),
    liste
  );
}

function sonDenemelerKarti(veri) {
  const kart = h("section", { class: "kart" });
  kart.append(
    h(
      "div",
      { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Son denemeler" }),
        h("p", { text: "Net gelişimi ve zayıf dersler" })),
      h("a", { class: "dugme ikincil kucuk", href: "#/deneme" }, "Deneme ekle")
    )
  );

  if (!veri.son_denemeler.length) {
    kart.append(bosDurum("Henüz deneme kaydı yok", "İlk denemeni eklediğinde analiz burada görünecek."));
    return kart;
  }

  const satirlar = h("div", { style: { display: "grid", gap: "10px" } });
  veri.son_denemeler.forEach((d) => {
    satirlar.append(
      h(
        "div",
        { class: "deneme-kart" },
        h(
          "div",
          { class: "deneme-ust" },
          rozet(d.tur, "marka"),
          h("b", { text: d.ad || `${d.tur} denemesi` }),
          h("span", { class: "tarih", text: kisaTarih(d.tarih) }),
          h(
            "div",
            { class: "sag" },
            h("span", { class: "deneme-net", text: String(d.toplam_net) }),
            h("span", { class: "tarih", text: "net" })
          )
        ),
        h(
          "div",
          { class: "alt-satirlar" },
          h("span", { class: "mini-net" }, "TYT ", h("b", { text: String(d.tyt_net) })),
          d.tur === "AYT"
            ? h("span", { class: "mini-net" }, "AYT ", h("b", { text: String(d.ayt_net) }))
            : null,
          h("span", { class: "mini-net" }, "Yerleştirme ", h("b", { text: String(d.puan.yerlestirme) })),
          h("span", { class: "mini-net" }, "TYT puan ", h("b", { text: String(d.puan.tyt) }))
        )
      )
    );
  });
  kart.append(satirlar);
  return kart;
}
