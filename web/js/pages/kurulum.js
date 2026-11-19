// kurulum.js — ilk giriş: alan, sınıf ve hedef seçimi
import { api } from "../api.js";
import { h, ikon, bildir } from "../ui.js";

export function kurulumGoster(kok, meta, bitti) {
  const secim = { alan: null, sinif: null, ad: "", gunluk_hedef_dk: 180, hedef_siralama: 0 };
  let adim = 1;
  const toplamAdim = 3;

  const govde = h("div", { class: "kurulum-govde" });
  const noktalar = h("div", { class: "adim-noktalari" });
  const geriDugme = h("button", { class: "dugme ikincil", type: "button" }, "Geri");
  const ileriDugme = h("button", { class: "dugme", type: "button" }, "Devam et");

  const kart = h(
    "div",
    { class: "kurulum-kart" },
    h(
      "header",
      { class: "kurulum-ust" },
      h(
        "div",
        { class: "marka" },
        h("span", { class: "marka-isaret" }, ikon("pusula")),
        h(
          "div",
          { class: "marka-metin" },
          h("b", { text: "YKS Pusula" }),
          h("small", { text: "Eğitim Koçluğu Platformu" })
        )
      ),
      h("h1", { text: "Sana uygun pusulayı kuralım" }),
      h("p", {
        text: "Seçimlerin; müfredat, günlük plan ve yapay zekâ koçunun cevaplarını belirler. Sonradan Ayarlar’dan değiştirebilirsin.",
      })
    ),
    govde,
    h(
      "footer",
      { class: "kurulum-alt" },
      noktalar,
      h("div", { style: { display: "flex", gap: "10px" } }, geriDugme, ileriDugme)
    )
  );

  function noktalariCiz() {
    noktalar.replaceChildren();
    for (let i = 1; i <= toplamAdim; i += 1) {
      noktalar.append(
        h("span", { class: `adim-nokta ${i === adim ? "aktif" : i < adim ? "bitti" : ""}`.trim() })
      );
    }
  }

  function baslikCiz(baslik, aciklama) {
    govde.replaceChildren(
      h("div", { class: "kurulum-baslik", text: baslik }),
      h("p", { class: "kurulum-aciklama", text: aciklama })
    );
  }

  function adimAlan() {
    baslikCiz("1. Hangi alanda sınava gireceksin?", "Alan seçimi, AYT’de çözeceğin dersleri belirler.");
    const kutu = h("div", { class: "secenekler uc" });
    meta.alanlar.forEach((alan) => {
      const dugme = h(
        "button",
        {
          class: `secenek ${secim.alan === alan.kod ? "secili" : ""}`.trim(),
          type: "button",
          onclick: () => {
            secim.alan = alan.kod;
            adimAlan();
            ileriDugme.disabled = false;
          },
        },
        h("span", { class: "tik" }, ikon("tik", 11)),
        h("span", { class: "baslik", text: alan.ad }),
        h("span", { class: "aciklama", text: alan.aciklama }),
        h("span", { class: "vurgu", text: alan.vurgu })
      );
      kutu.append(dugme);
    });
    if (secim.alan) {
      const secili = meta.alanlar.find((a) => a.kod === secim.alan);
      govde.append(kutu, h("p", { class: "ipucu", style: { marginTop: "14px" } },
        `AYT derslerin: ${secili.ayt_dersleri.join(" · ")}`));
    } else {
      govde.append(kutu);
    }
    ileriDugme.disabled = !secim.alan;
  }

  function adimSinif() {
    baslikCiz("2. Hangi sınıftasın?", "Sınav yılın ve konu önceliklerin buna göre hesaplanır.");
    const kutu = h("div", { class: "secenekler uc" });
    meta.siniflar.forEach((sinif) => {
      kutu.append(
        h(
          "button",
          {
            class: `secenek ${secim.sinif === sinif.kod ? "secili" : ""}`.trim(),
            type: "button",
            onclick: () => {
              secim.sinif = sinif.kod;
              adimSinif();
              ileriDugme.disabled = false;
            },
          },
          h("span", { class: "tik" }, ikon("tik", 11)),
          h("span", { class: "baslik", text: sinif.ad }),
          h("span", { class: "aciklama", text: sinif.not })
        )
      );
    });
    govde.append(kutu);
    ileriDugme.disabled = secim.sinif === null;
  }

  function adimHedef() {
    baslikCiz("3. Hedefini belirle", "Hedef sıralaman hem ders seçimini hem günlük programını belirler.");

    const adGirdi = h("input", {
      class: "alan",
      type: "text",
      maxlength: "40",
      placeholder: "Örn. Elif",
      value: secim.ad,
      oninput: (o) => { secim.ad = o.target.value; },
    });

    const hedefSecim = h(
      "select",
      {
        class: "secim",
        onchange: (o) => { secim.gunluk_hedef_dk = Number(o.target.value); },
      },
      [90, 120, 150, 180, 210, 240, 300, 360, 420].map((dk) =>
        h("option", { value: dk, selected: dk === secim.gunluk_hedef_dk }, `${dk} dakika (${dk / 60} saat)`)
      )
    );

    const siralamaGirdi = h("input", {
      class: "alan",
      type: "number",
      min: "0",
      step: "1000",
      placeholder: "Örn. 20000",
      value: secim.hedef_siralama || "",
      oninput: (o) => { secim.hedef_siralama = Number(o.target.value) || 0; },
    });

    govde.append(
      h(
        "div",
        { style: { display: "grid", gap: "14px" } },
        h("div", { class: "form-alan" }, h("label", { text: "Öğrencinin adı" }), adGirdi),
        h(
          "div",
          { class: "form-alan" },
          h("label", { text: "Günlük çalışma hedefi" }),
          hedefSecim,
          h("small", { text: "Gerçekçi başla; zamanla artırabilirsin." })
        ),
        h(
          "div",
          { class: "form-alan" },
          h("label", { text: "Hedef sıralama (isteğe bağlı)" }),
          siralamaGirdi,
          h("small", {
            text: "Girersen program bu sıralamanın gerektirdiği netleri hesaplar ve planı ona göre kurar (ör. 20.000 ≈ TYT 90 / AYT 60 net). Boş bırakırsan 100.000 varsayılır; sonradan Ayarlar'dan değiştirebilirsin.",
          })
        ),
        h("p", {
          class: "ipucu",
          text: "Not: Seçimlerinle birlikte 7 günlük ilk çalışma planın otomatik oluşturulacak.",
        })
      )
    );
    ileriDugme.disabled = false;
  }

  function ciz() {
    noktalariCiz();
    geriDugme.style.visibility = adim === 1 ? "hidden" : "visible";
    ileriDugme.textContent = adim === toplamAdim ? "Programı başlat" : "Devam et";
    if (adim === 1) adimAlan();
    else if (adim === 2) adimSinif();
    else adimHedef();
  }

  geriDugme.addEventListener("click", () => {
    if (adim > 1) { adim -= 1; ciz(); }
  });

  ileriDugme.addEventListener("click", async () => {
    if (adim === 1 && !secim.alan) return;
    if (adim === 2 && secim.sinif === null) return;
    if (adim < toplamAdim) { adim += 1; ciz(); return; }

    ileriDugme.disabled = true;
    ileriDugme.textContent = "Hazırlanıyor…";
    try {
      const profil = await api.post("/api/profil", {
        ad: secim.ad.trim() || "Öğrenci",
        alan: secim.alan,
        sinif: secim.sinif,
        gunluk_hedef_dk: secim.gunluk_hedef_dk,
        hedef_siralama: secim.hedef_siralama,
      });
      localStorage.setItem("pusula_profil", String(profil.id));
      bildir("Profil oluşturuldu, planın hazır.");
      bitti(profil);
    } catch (hata) {
      bildir(hata.message, "hata");
      ileriDugme.disabled = false;
      ileriDugme.textContent = "Programı başlat";
    }
  });

  kok.replaceChildren(h("div", { class: "kurulum" }, kart));
  ciz();
}
