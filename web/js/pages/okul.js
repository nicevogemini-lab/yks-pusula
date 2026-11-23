// okul.js — haftalık okul ders programı ve "bugün işlenen konular" girişi
//
// Çizelge hücreleri YKS ders kodu değil okul dersi anahtarı tutar
// (matematik, fizik ...). Beden eğitimi gibi dersler çizelgede görünür ama
// konu seçeneği üretmez. İşaretlenen konular günlük plana tekrar ve
// pekiştirme bloğu olarak yazılır.
import { api } from "../api.js";
import { h, ikon, bildir, tarihTr, bosDurum, rozet } from "../ui.js";

export const baslik = "Okul Ders Programı";
export const alt = "11. ve 12. sınıf çizelgesi · bugün işlenen konular plana tekrar olarak girer";

export async function ciz(kap, durum) {
  const profilId = durum.profil.id;
  const [veri, gecmis] = await Promise.all([
    api.get(`/api/profil/${profilId}/ders-programi`),
    api.get(`/api/profil/${profilId}/islenen?gun=7`),
  ]);
  kap.replaceChildren(
    ...[cizelgeKarti(veri, durum), bugunKarti(veri, durum), gecmisKarti(gecmis)].filter(Boolean)
  );
}

/** Kart başlığı: sol metin, sağ eylemler */
function kartBasligi(baslikMetni, altMetni, ...eylemler) {
  return h(
    "div",
    { class: "kart-baslik", style: { alignItems: "center", flexWrap: "wrap" } },
    h("div", {}, h("h2", { text: baslikMetni }), h("p", { text: altMetni })),
    h(
      "div",
      { style: { display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" } },
      ...eylemler
    )
  );
}

// ------------------------------------------------------------------ çizelge
function cizelgeKarti(veri, durum) {
  const kart = h("section", { class: "kart" });
  const baslikMetni = `Haftalık ders programı (${veri.sinif_etiketi} · ${veri.alan_etiketi})`;

  if (!veri.sinif) {
    kart.append(
      kartBasligi(
        "Haftalık ders programı",
        "Mezun öğrencide okul çizelgesi yok; konu girişi için 11. veya 12. sınıf profili gerekir."
      ),
      bosDurum(
        "Çizelge yalnız 11. ve 12. sınıf için",
        "Sınıf bilgisini Ayarlar sayfasından güncelleyebilirsin."
      )
    );
    return kart;
  }

  // Seçili hücreler: "gun-sira" -> okul dersi anahtarı
  const hucreler = new Map(veri.hucreler.map((c) => [`${c.gun}-${c.sira}`, c.ders]));
  const izgara = h("div", { class: "okul-izgara" });

  izgara.append(h("div", { class: "okul-baslik", text: "Ders saati" }));
  veri.gunler.forEach((gun) => {
    izgara.append(
      h(
        "div",
        { class: `okul-baslik ${gun.gun === veri.gun ? "bugun" : ""}`.trim() },
        h("b", { text: gun.ad }),
        gun.gun === veri.gun ? h("small", { text: "bugün" }) : null
      )
    );
  });

  for (let sira = 1; sira <= veri.gunluk_saat; sira += 1) {
    izgara.append(h("div", { class: "okul-saat", text: `${sira}. ders` }));
    veri.gunler.forEach((gun) => {
      const anahtar = `${gun.gun}-${sira}`;
      const secim = h("select", {
        class: `secim okul-secim ${gun.gun === veri.gun ? "bugun" : ""}`.trim(),
        "aria-label": `${gun.ad} ${sira}. ders`,
      });
      secim.append(h("option", { value: "" }, "—"));
      veri.dersler.forEach((ders) => {
        secim.append(
          h(
            "option",
            { value: ders.kod, selected: hucreler.get(anahtar) === ders.kod },
            ders.ders.length ? ders.ad : `${ders.ad} (konusuz)`
          )
        );
      });
      secim.addEventListener("change", () => {
        if (secim.value) hucreler.set(anahtar, secim.value);
        else hucreler.delete(anahtar);
      });
      izgara.append(secim);
    });
  }

  const kaydet = h(
    "button",
    { class: "dugme kucuk", type: "button" },
    ikon("tik", 15),
    "Çizelgeyi kaydet"
  );
  kaydet.addEventListener("click", async () => {
    kaydet.disabled = true;
    try {
      const liste = [...hucreler.entries()].map(([anahtar, ders]) => {
        const [gun, sira] = anahtar.split("-").map(Number);
        return { gun, sira, ders };
      });
      const yanit = await api.put(`/api/profil/${durum.profil.id}/ders-programi`, {
        hucreler: liste,
      });
      bildir(`${yanit.hucre} ders saati kaydedildi.`);
      await durum.yenile();
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
    }
  });

  const sablonDugmesi = (sinif) =>
    h(
      "button",
      {
        class: "dugme ikincil kucuk",
        type: "button",
        onclick: async (olay) => {
          const dugme = olay.currentTarget;
          dugme.disabled = true;
          try {
            const yanit = await api.put(`/api/profil/${durum.profil.id}/ders-programi`, {
              hucreler: [],
              sablon_uygula: sinif,
            });
            bildir(`${sinif}. sınıf çizelgesi yüklendi (${yanit.hucre} ders saati).`);
            await durum.yenile();
          } catch (hata) {
            bildir(hata.message, "hata");
            dugme.disabled = false;
          }
        },
      },
      `${sinif}. sınıf çizelgesi`
    );

  kart.append(
    kartBasligi(
      baslikMetni,
      veri.hucreler.length
        ? `${veri.hucreler.length} ders saati tanımlı · hücreye tıklayıp dersi değiştir`
        : "Çizelge boş: hazır çizelgeyi yükle ya da hücreleri tek tek doldur",
      sablonDugmesi(11),
      sablonDugmesi(12),
      kaydet
    ),
    izgara,
    h("p", {
      class: "ipucu",
      text: "Çizelge okulun gerçek programı kadar doğru olmalı: günlük plan okulda işlenen konuyu aynı gün tekrar, ertesi gün, 3. ve 7. günde pekiştirme bloğu olarak yazar. Beden eğitimi, İngilizce ve etüt dersleri çizelgede görünür, konu listesi üretmez.",
    })
  );
  return kart;
}

// --------------------------------------------------- bugün işlenen konular
function bugunKarti(veri, durum) {
  const kart = h("section", { class: "kart" });
  const secili = new Set(veri.islenen);
  const gruplar = veri.bugun_dersleri
    .map(({ ders, ad }) => ({ ders, ad, konular: veri.secenekler[ders] || [] }))
    .filter((grup) => grup.konular.length);

  const basliklar = veri.bugun_dersleri.length
    ? veri.bugun_dersleri.map((ders) => rozet(ders.ad))
    : [rozet("Bugün okul yok", "uyari")];

  const kaydet = h(
    "button",
    { class: "dugme kucuk", type: "button" },
    ikon("tik", 15),
    "İşlenen konuları kaydet"
  );
  kaydet.addEventListener("click", async () => {
    kaydet.disabled = true;
    kaydet.textContent = "Kaydediliyor…";
    try {
      const yanit = await api.post(`/api/profil/${durum.profil.id}/islenen`, {
        tarih: veri.tarih,
        konu_idler: [...secili],
      });
      bildir(
        yanit.plan
          ? `Kaydedildi · ${yanit.plan} plan maddesi tazelendi, tekrar ve pekiştirme eklendi.`
          : "Kaydedildi · program bu konuları tekrar bloğu olarak yazacak."
      );
      await durum.yenile();
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
      kaydet.textContent = "İşlenen konuları kaydet";
    }
  });

  kart.append(
    kartBasligi(
      `Bugün okulda işlenen konular · ${veri.gun_adi} ${tarihTr(veri.tarih)}`,
      "İşaretlediklerin bugünün planına tekrar ve pekiştirme bloğu olarak yazılır; günlük plan kaydettikten sonra tazelenir.",
      ...basliklar,
      gruplar.length ? kaydet : null
    )
  );

  if (!gruplar.length) {
    kart.append(
      bosDurum(
        veri.bugun_dersleri.length ? "Bugünün derslerinde konu listesi yok" : "Bugün ders yok",
        veri.bugun_dersleri.length
          ? "Bugünün dersleri sınavda çıkmayan derslerden oluşuyor (beden, etüt vb.). Haftalık çizelgeye sınav dersi ekleyince konu girişi burada açılır."
          : "Haftalık çizelgede bugüne ders ekleyince o dersin konuları burada listelenir."
      )
    );
    return kart;
  }

  const izgara = h("div", { class: "okul-gruplar" });
  gruplar.forEach((grup) => izgara.append(konuGrubu(grup, secili)));
  kart.append(izgara);
  return kart;
}

/** Bir dersin konu listesi: işaretli konular tekrar bloğuna girer */
function konuGrubu(grup, secili) {
  const kutu = h("div", { class: "okul-konu-grubu" });
  const sayac = h("span", { class: "rozet" });
  const sayacYaz = () => {
    const adet = grup.konular.filter((konu) => secili.has(konu.id)).length;
    sayac.textContent = adet ? `${adet} konu seçildi` : "konu seçilmedi";
    sayac.className = `rozet ${adet ? "marka" : ""}`.trim();
  };

  const liste = h("div", { class: "okul-konular" });
  grup.konular.forEach((konu) => {
    const onay = h("input", { type: "checkbox", checked: secili.has(konu.id) });
    onay.addEventListener("change", () => {
      if (onay.checked) secili.add(konu.id);
      else secili.delete(konu.id);
      sayacYaz();
    });
    const sinifEtiketi = konu.sinif ? ` · ${konu.sinif}. sınıf` : "";
    liste.append(
      h(
        "label",
        { class: "okul-konu" },
        onay,
        h("span", { text: `${konu.ad}${sinifEtiketi}` })
      )
    );
  });

  kutu.append(h("div", { class: "okul-grup-baslik" }, h("b", { text: grup.ad }), sayac), liste);
  sayacYaz();
  return kutu;
}

// ------------------------------------------------------------ son günler
function gecmisKarti(gecmis) {
  const kart = h("section", { class: "kart" });
  kart.append(
    kartBasligi(
      "Son girilen konular",
      "Tekrar takvimi: konu işlendiği gün, ertesi gün, 3. ve 7. günde plana girer."
    )
  );

  if (!gecmis.length) {
    kart.append(
      bosDurum("Henüz konu girilmedi", "Okulda işlenen ilk konuyu yukarıdaki karttan işaretle.")
    );
    return kart;
  }

  const liste = h("div", { class: "okul-gecmis" });
  gecmis.forEach((gun) => {
    liste.append(
      h(
        "div",
        { class: "okul-gecmis-satir" },
        h("b", { text: `${gun.gun_adi} · ${tarihTr(gun.tarih)}` }),
        h(
          "div",
          { class: "okul-gecmis-konular" },
          gun.konular.map((konu) => rozet(`${konu.ders_ad}: ${konu.ad}`))
        )
      )
    );
  });
  kart.append(liste);
  return kart;
}
