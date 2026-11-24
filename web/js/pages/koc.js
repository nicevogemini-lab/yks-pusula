// koc.js — yapay zekâ koçu sohbeti
import { api } from "../api.js";
import { h, ikon, rozet, metinBalonu, bildir, bosDurum } from "../ui.js";

export const baslik = "Yapay Zekâ Koçu";
export const alt = "Alanına ve sınıfına göre kişisel rehberlik";

const HIZLI_SORULAR = [
  "Bu hafta neye çalışmalıyım?",
  "Matematik netimi nasıl artırırım?",
  "Son denememi yorumla",
  "Motivasyonum düştü, ne yapmalıyım?",
  "Sınav kaygısını nasıl yönetirim?",
];

let sohbetKabi = null;
let girisAlani = null;
let durumRef = null;

export async function ciz(kap, durum) {
  durumRef = durum;
  const [gecmis, aiDurum] = await Promise.all([
    api.get(`/api/koc/${durum.profil.id}`),
    api.get("/api/ai/durum"),
  ]);

  sohbetKabi = h("div", { class: "sohbet-kutu", id: "sohbet" });
  girisAlani = h("textarea", {
    class: "alan",
    placeholder: "Sorunu yaz… (Enter ile gönder, Shift+Enter yeni satır)",
    rows: "1",
  });
  girisAlani.addEventListener("keydown", (olay) => {
    if (olay.key === "Enter" && !olay.shiftKey) {
      olay.preventDefault();
      gonder();
    }
  });

  const gonderDugme = h("button", { class: "dugme", type: "button" }, ikon("sohbet", 16), "Gönder");
  gonderDugme.addEventListener("click", () => gonder(gonderDugme));

  const hizli = h("div", { class: "hizli-sorular" });
  HIZLI_SORULAR.forEach((soru) => {
    hizli.append(
      h("button", {
        class: "hizli-soru",
        type: "button",
        text: soru,
        onclick: () => {
          girisAlani.value = soru;
          gonder(gonderDugme);
        },
      })
    );
  });

  if (gecmis.length) {
    gecmis.forEach((m) => balonEkle(m.rol === "kullanici" ? "kullanici" : "koc", m.icerik, m.kaynak));
  } else {
    sohbetKabi.append(
      bosDurum(
        "Koç hazır",
        "Bugünkü durumunu, denemelerini ve öncelikli konularını biliyor. Aşağıdan bir soru sorabilirsin."
      )
    );
  }

  kap.replaceChildren(
    h(
      "section",
      { class: "kart" },
      h(
        "div",
        { class: "kart-baslik" },
        h("div", {},
          h("h2", { text: `Koç · ${durum.profil.ad}` }),
          h("p", {
            text: `${durum.profil.alan_etiketi} · ${durum.profil.sinif_etiketi} · Maarif Modeli ve 2028 soru modeli bağlamında yanıtlar`,
          })),
        h("div", { style: { display: "flex", gap: "6px", alignItems: "center" } },
          rozet(aiDurum.aktif ? `Gemini · ${aiDurum.model}` : "Yerel koç modu", aiDurum.aktif ? "basari" : "uyari"),
          h("a", { class: "dugme sessiz kucuk", href: "#/ayarlar" }, "Ayarlar"))
      ),
      aiDurum.aktif ? null : baglantiKarti(),
      hizli,
      sohbetKabi,
      h("div", { class: "sohbet-giris" }, girisAlani, gonderDugme)
    ),
    soruUretKarti(durum)
  );
}

function baglantiKarti() {
  return h(
    "div",
    { class: "ipucu", style: { marginBottom: "12px", flexWrap: "wrap", gap: "10px" } },
    ikon("uyari", 16),
    h("span", {
      style: { flex: "1 1 240px" },
      text: "Yapay zekâ anahtarı yok: koç şu an yerel motorla çalışıyor (öncelikli konular + deneme netleri). Kişisel sohbet için ücretsiz Gemini anahtarı yeterli.",
    }),
    h("a", { class: "dugme kucuk", href: "#/ayarlar" }, "Anahtarı Ayarlar'dan gir"),
    h("a", { class: "dugme sessiz kucuk", href: "https://aistudio.google.com/apikey", target: "_blank", rel: "noopener" }, "Anahtarı al")
  );
}

function sonaKaydir(oge) {
  // Kutu kendi içinde kaydırılabiliyorsa onu, değilse sayfayı kaydır
  if (sohbetKabi.scrollHeight > sohbetKabi.clientHeight + 2) {
    sohbetKabi.scrollTop = sohbetKabi.scrollHeight;
  } else {
    oge.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function balonEkle(kim, metin, kaynak) {
  if (sohbetKabi.firstElementChild?.classList.contains("bos")) {
    sohbetKabi.replaceChildren();
  }
  const mesaj = h(
    "div",
    { class: `mesaj ${kim === "kullanici" ? "kullanici" : ""}`.trim() },
    h(
      "div",
      { style: { maxWidth: "100%" } },
      h("div", {
        class: "kim",
        text: kim === "kullanici" ? "Sen" : kaynak === "gemini" ? "A-KEY Koç · Gemini" : "A-KEY Koç · yerel",
      }),
      metinBalonu(metin)
    )
  );
  sohbetKabi.append(mesaj);
  sonaKaydir(mesaj);
  return mesaj;
}

function yaziyorBalonu() {
  const kutu = h(
    "div",
    { class: "mesaj" },
    h("div", {}, h("div", { class: "kim", text: "A-KEY Koç" },
      h("div", { class: "balon" }, h("div", { class: "yaziyor" }, h("span"), h("span"), h("span")))))
  );
  sohbetKabi.append(kutu);
  sonaKaydir(kutu);
  return kutu;
}

async function gonder(dugme) {
  const metin = (girisAlani?.value || "").trim();
  if (!metin) return;
  girisAlani.value = "";
  balonEkle("kullanici", metin);
  const bekleyen = yaziyorBalonu();
  if (dugme) dugme.disabled = true;

  try {
    const yanit = await api.post(`/api/koc/${durumRef.profil.id}`, { mesaj: metin });
    bekleyen.remove();
    balonEkle("koc", yanit.metin, yanit.kaynak);
  } catch (hata) {
    bekleyen.remove();
    bildir(hata.message, "hata");
  } finally {
    if (dugme) dugme.disabled = false;
  }
}

function soruUretKarti(durum) {
  const konuGirdi = h("input", {
    class: "alan",
    type: "text",
    placeholder: "Konu adı (örn. Türev, Kalıtım, Paragraf, Üslü sayılar)",
  });
  const adetSecim = h("select", { class: "secim" },
    [1, 2, 3, 5, 10, 15].map((n) => h("option", { value: n, selected: n === 3 }, `${n} soru`)));
  const zorlukSecim = h("select", { class: "secim" },
    ["kolay", "orta", "zor"].map((z) => h("option", { value: z, selected: z === "orta" }, z)));
  const cikti = h("div", { style: { marginTop: "14px" } });
  const kartlarKutu = h("div", {});
  const altKutu = h("div", {});
  cikti.append(kartlarKutu, altKutu);
  const uretilenler = []; // ekrandaki sorular: sıra numarası ve tekrar kontrolü için
  let hedefAdet = 3;
  const uret = h("button", { class: "dugme ikincil", type: "button" }, "Soru üret");

  /** Tekrarları ayıklamak için sorunun sadeleştirilmiş kök metni */
  function soruKoku(soru) {
    return String(soru.soru || "").toLowerCase().replace(/\s+/g, " ").trim().slice(0, 120);
  }

  async function uretSorular(adetIstenen, ekle) {
    const konu = konuGirdi.value.trim();
    if (!konu) {
      bildir("Konu adı gir.", "hata");
      return;
    }
    uret.disabled = true;
    const eskiMetin = uret.textContent;
    uret.textContent = "Üretiliyor…";
    if (!ekle) {
      hedefAdet = Number(adetIstenen);
      uretilenler.length = 0;
      kartlarKutu.replaceChildren();
      altKutu.replaceChildren(
        h("p", {
          class: "ipucu",
          text: "Sorular hazırlanıyor: 15 soru 3 partide istenir; modelin yoğunluğuna göre 1-2 dakika sürebilir. Sekmeyi kapatma.",
        })
      );
    } else {
      altKutu.replaceChildren(h("p", { class: "ipucu", text: "Kalan sorular hazırlanıyor…" }));
    }
    try {
      const yanit = await api.post(
        `/api/koc/${durum.profil.id}/soru?konu=${encodeURIComponent(konu)}&adet=${adetIstenen}&zorluk=${zorlukSecim.value}`
      );
      altKutu.replaceChildren();
      if (yanit.hata) {
        altKutu.append(h("p", { class: "ipucu", text: yanit.hata }));
        return;
      }
      const gorulen = new Set(uretilenler.map(soruKoku));
      const yeni = yanit.sorular.filter((soru) => !gorulen.has(soruKoku(soru)));
      if (yeni.length === 0 && uretilenler.length > 0) {
        altKutu.append(
          h("p", { class: "soru-uyari", text: "Gelen sorular öncekilerle aynıydı; tekrar dene." })
        );
        return;
      }
      if (yanit.uyari) altKutu.append(h("p", { class: "soru-uyari", text: yanit.uyari }));
      kartlarKutu.append(...yeni.map((soru, i) => soruGorunumu(soru, uretilenler.length + i + 1)));
      uretilenler.push(...yeni);
      const kalan = Math.max(0, hedefAdet - uretilenler.length);
      if (kalan > 0) {
        const kalanDugme = h("button", {
          class: "dugme sessiz kucuk",
          type: "button",
          text: `Kalan ${kalan} soruyu üret`,
        });
        kalanDugme.addEventListener("click", () => uretSorular(kalan, true));
        altKutu.append(kalanDugme);
      }
    } catch (hata) {
      bildir(hata.message, "hata");
    } finally {
      uret.disabled = false;
      uret.textContent = eskiMetin;
    }
  }

  uret.addEventListener("click", () => uretSorular(adetSecim.value, false));

  return h(
    "section",
    { class: "kart" },
    h("div", { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Maarif model temelli soru üret" }),
        h("p", { text: "Maarif Modeli ve 2028 soru modeline uygun, bağlam temelli sorular (15'e kadar)" }))),
    h("div", { class: "soru-form" },
      h("div", { class: "form-alan" }, h("label", { text: "Konu" }), konuGirdi),
      h("div", { class: "form-alan" }, h("label", { text: "Adet" }), adetSecim),
      h("div", { class: "form-alan" }, h("label", { text: "Zorluk" }), zorlukSecim),
      uret),
    h("p", { class: "soru-ipucu", text: "Sorular metin olarak üretilir; şekil/grafik yerine metin tablo ve veri kullanılır. Doğru cevap, sen seçim yaptıktan sonra açılır." }),
    cikti
  );
}

const US_DESENI =
  /\^\{([^{}]+)\}|\^\(([^()]{1,16})\)|\^([-+]?[\d.,]+|[A-Za-zÇĞİÖŞÜçğıöşü]+)/g;

/** "2^10", "x^{2}", "2^(a+b)" gibi üsleri <sup> olarak çizer (XSS üretmez) */
function usluMetin(metin) {
  const parca = document.createDocumentFragment();
  const kaynak = String(metin ?? "");
  let son = 0;
  for (const eslesme of kaynak.matchAll(US_DESENI)) {
    if (eslesme.index > son) parca.append(document.createTextNode(kaynak.slice(son, eslesme.index)));
    const us = eslesme[1] ?? (eslesme[2] ? `(${eslesme[2]})` : eslesme[3]);
    parca.append(h("sup", { text: us }));
    son = eslesme.index + eslesme[0].length;
  }
  if (son < kaynak.length) parca.append(document.createTextNode(kaynak.slice(son)));
  return parca;
}

function soruGorunumu(soru, sira) {
  const secenekler = h("div", { class: "soru-secenekler" });
  const durumKutu = h("div", { class: "soru-durum" });
  const ipucu = h("p", { class: "soru-ipucu", text: "Bir seçenek işaretle; doğru cevap ve çözüm sonra açılır." });
  const cozumKutu = h(
    "div",
    { class: "soru-cozum", hidden: true },
    h("div", { class: "soru-cozum-baslik", text: "Çözüm" }),
    h("p", { class: "soru-cozum-metin" }, usluMetin(soru.cozum || "Çözüm eklenmedi."))
  );
  const dugumler = Object.create(null);
  let cevaplandi = false;

  function cevapla(harf) {
    if (cevaplandi) return;
    cevaplandi = true;
    const dogruHarf = dugumler[soru.dogru] ? soru.dogru : null;
    const dogruMu = harf === dogruHarf;
    Object.values(dugumler).forEach((dugme) => { dugme.disabled = true; });
    dugumler[harf].classList.add(dogruMu ? "dogru" : "yanlis");
    dugumler[harf].querySelector(".soru-isaret").textContent = dogruMu ? "seçimin · doğru" : "seçimin · yanlış";
    if (dogruHarf && !dogruMu) {
      dugumler[dogruHarf].classList.add("dogru");
      dugumler[dogruHarf].querySelector(".soru-isaret").textContent = "doğru cevap";
    }
    durumKutu.classList.add(dogruMu ? "basari" : "hata");
    durumKutu.textContent = dogruMu
      ? "Doğru. Çözümdeki adımlarla kendi çözümünü karşılaştır."
      : `Yanlış. Doğru cevap: ${dogruHarf || "—"}. Çözümü incele, hatanı not et.`;
    ipucu.hidden = true;
    cozumKutu.hidden = false;
  }

  Object.entries(soru.secenekler || {}).forEach(([harf, metin]) => {
    const dugme = h(
      "button",
      { class: "soru-secenek", type: "button" },
      h("span", { class: "soru-harf", text: harf }),
      h("span", { class: "soru-secenek-metin" }, usluMetin(metin)),
      h("span", { class: "soru-isaret" })
    );
    dugme.addEventListener("click", () => cevapla(harf));
    dugumler[harf] = dugme;
    secenekler.append(dugme);
  });

  return h(
    "div",
    { class: "deneme-kart soru-kart" },
    h("div", { class: "soru-ust" },
      h("span", { class: "soru-no", text: `Soru ${sira}` }),
      rozet(soru.beceri || "beceri", "marka"),
      soru.kazanim ? h("span", { class: "soru-kazanim", text: soru.kazanim }) : null),
    h("p", { class: "soru-metin" }, usluMetin(soru.soru)),
    soru.veri ? h("pre", { class: "soru-veri", text: soru.veri }) : null,
    secenekler,
    ipucu,
    durumKutu,
    cozumKutu
  );
}
