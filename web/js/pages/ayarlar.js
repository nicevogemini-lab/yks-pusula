// ayarlar.js — profil, yapay zekâ ve veri yönetimi
import { api } from "../api.js";
import { h, ikon, rozet, tarihTr, bildir } from "../ui.js";

export const baslik = "Ayarlar";
export const alt = "Profil, yapay zekâ bağlantısı ve veri";

export async function ciz(kap, durum) {
  const [aiDurum, saglik, hedef] = await Promise.all([
    api.get("/api/ai/durum"),
    api.get("/api/saglik"),
    api.get(`/api/hedef/${durum.profil.id}`),
  ]);
  kap.replaceChildren(
    profilKarti(durum, hedef),
    aiKarti(aiDurum),
    veriKarti(saglik, durum),
    hakkindaKarti()
  );
}

function profilKarti(durum, hedef) {
  const p = durum.profil;

  const adGirdi = h("input", { class: "alan", type: "text", value: p.ad, maxlength: "40" });

  const alanSecim = h(
    "select",
    { class: "secim" },
    durum.meta.alanlar.map((a) => h("option", { value: a.kod, selected: p.alan === a.kod }, a.ad))
  );

  const sinifSecim = h(
    "select",
    { class: "secim" },
    durum.meta.siniflar.map((s) => h("option", { value: s.kod, selected: p.sinif === s.kod }, s.ad))
  );

  const hedefSecim = h(
    "select",
    { class: "secim" },
    [90, 120, 150, 180, 210, 240, 300, 360, 420].map((dk) =>
      h("option", { value: dk, selected: p.gunluk_hedef_dk === dk }, `${dk} dakika`))
  );

  const siralamaGirdi = h("input", {
    class: "alan", type: "number", min: "0", step: "1000",
    value: String(p.hedef_siralama || ""), placeholder: "örn. 20000",
  });

  const tarihGirdi = h("input", { class: "alan", type: "date", value: p.sinav_tarihi || "" });

  // Gün akışı saatleri: program sabah uyanıştan gece yatışa bu saatlere kurulur
  const uyanmaGirdi = h("input", { class: "alan", type: "time", value: p.uyanma_saati || "06:45" });
  const yatmaGirdi = h("input", { class: "alan", type: "time", value: p.yatma_saati || "22:45" });
  const okulBasGirdi = h("input", { class: "alan", type: "time", value: p.okul_baslangic || "08:20" });
  const okulBitGirdi = h("input", { class: "alan", type: "time", value: p.okul_bitis || "15:20" });
  // Okuldan eve varış: boşsa 35 dk yol varsayılır
  const okulDonusGirdi = h("input", { class: "alan", type: "time", value: p.okul_donus || "" });

  const kaydet = h("button", { class: "dugme", type: "button" }, "Değişiklikleri kaydet");
  kaydet.addEventListener("click", async () => {
    kaydet.disabled = true;
    kaydet.textContent = "Kaydediliyor…";
    try {
      const yeni = await api.patch(`/api/profil/${p.id}`, {
        ad: adGirdi.value.trim() || "Öğrenci",
        alan: alanSecim.value,
        sinif: Number(sinifSecim.value),
        gunluk_hedef_dk: Number(hedefSecim.value),
        hedef_siralama: Number(siralamaGirdi.value) || 0,
        sinav_tarihi: tarihGirdi.value || null,
        uyanma_saati: uyanmaGirdi.value || "06:45",
        yatma_saati: yatmaGirdi.value || "22:45",
        okul_baslangic: okulBasGirdi.value || "08:20",
        okul_bitis: okulBitGirdi.value || "15:20",
        okul_donus: okulDonusGirdi.value || "",
      });
      bildir("Profil güncellendi, plan yenilendi.");
      await durum.profilGuncellendi(yeni);
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
      kaydet.textContent = "Değişiklikleri kaydet";
    }
  });

  return h(
    "section",
    { class: "kart" },
    h("div", { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Öğrenci profili" }),
        h("p", { text: "Alan, sınıf, süre, hedef sıralama veya gün saatleri değişirse 7 günlük plan yeniden üretilir." }))),
    h(
      "div",
      { class: "ayar-bolum" },
      h("div", { class: "ayar-izgara" },
        h("div", { class: "form-alan" }, h("label", { text: "Ad" }), adGirdi),
        h("div", { class: "form-alan" }, h("label", { text: "Alan" }), alanSecim),
        h("div", { class: "form-alan" }, h("label", { text: "Sınıf" }), sinifSecim),
        h("div", { class: "form-alan" }, h("label", { text: "Günlük hedef" }), hedefSecim),
        h("div", { class: "form-alan" }, h("label", { text: "Hedef sıralama" }), siralamaGirdi,
          h("small", { text: hedefAciklamasi(hedef) })),
        h("div", { class: "form-alan" }, h("label", { text: "Sınav tarihi" }), tarihGirdi,
          h("small", { text: `Şu an: ${tarihTr(p.sinav_tarihi)}` })),
        h("div", { class: "form-alan" }, h("label", { text: "Sabah uyanış" }), uyanmaGirdi,
          h("small", { text: "PDR önerisi: her gün aynı saatte kalk." })),
        h("div", { class: "form-alan" }, h("label", { text: "Gece yatış" }), yatmaGirdi,
          h("small", { text: "Ergen için 8 saat uyku hedefi." })),
        h("div", { class: "form-alan" }, h("label", { text: "Okul başlangıcı" }), okulBasGirdi,
          h("small", { text: "Hafta içi program okul saatlerini boş bırakır." })),
        h("div", { class: "form-alan" }, h("label", { text: "Okul bitişi" }), okulBitGirdi,
          h("small", { text: "Derslerin bittiği saat; dönüş ve mola bunun ardından işlenir." })),
        h("div", { class: "form-alan" }, h("label", { text: "Okuldan dönüş (eve varış)" }), okulDonusGirdi,
          h("small", { text: "Boş bırakırsan 35 dk yol varsayılır. Akşam blokları bu saate göre kurulur." }))),
      h("div", { class: "ipucu" },
        ikon("hedef", 16),
        h("span", {
          text: "Hedef sıralama ders ve çalışma programını belirler: sıralamadan gereken TYT/AYT netleri hesaplanır, bu netler derslere dağıtılır ve en büyük açığı olan ders günlük planda en çok bloğu alır. Ders seçimi de bu netlere göre yapılır.",
        })),
      h("div", { style: { display: "flex", justifyContent: "flex-end" } }, kaydet)
    )
  );
}

function hedefAciklamasi(hedef) {
  if (!hedef) return "Girilmezse 100.000 varsayılır.";
  if (hedef.varsayilan) {
    return `Girilmedi: 100.000 varsayıldı → TYT ${hedef.tyt_hedef_net} · AYT ${hedef.ayt_hedef_net} net.`;
  }
  return `Bu sıralama ≈ TYT ${hedef.tyt_hedef_net} · AYT ${hedef.ayt_hedef_net} net (haftada ${hedef.haftalik_gereken_net} net).`;
}

function aiKarti(aiDurum) {
  const anahtarGirdi = h("input", {
    class: "alan",
    type: "password",
    placeholder: aiDurum.aktif ? "Anahtar kayıtlı · değiştirmek için yenisini yapıştır" : "AIza… veya AQ.… ile başlayan anahtar",
    autocomplete: "off",
    spellcheck: "false",
  });
  const modelGirdi = h("input", { class: "alan", type: "text", value: aiDurum.model });
  const sonuc = h("div", { id: "ai-sonuc" });

  function sonucGoster(veri) {
    sonuc.replaceChildren(
      h("div", { class: `ipucu ${veri.ok ? "iyi" : "kotu"}`.trim() },
        ikon(veri.ok ? "tik" : "uyari", 16),
        h("span", { text: veri.mesaj }))
    );
  }

  async function durumYenile() {
    const yeni = await api.get("/api/ai/durum");
    const kart = document.querySelector("#ai-kart");
    if (kart) kart.replaceWith(aiKarti(yeni));
  }

  const test = h("button", { class: "dugme ikincil", type: "button" }, "Bağlantıyı test et");
  test.addEventListener("click", async () => {
    test.disabled = true;
    test.textContent = "Deneniyor…";
    sonuc.replaceChildren(h("div", { class: "ipucu" }, h("span", { text: "Google'a bağlanılıyor…" })));
    try {
      const yanit = await api.post("/api/ai/test", {
        anahtar: anahtarGirdi.value.trim(),
        model: modelGirdi.value.trim(),
      });
      sonucGoster(yanit);
    } catch (hata) {
      sonucGoster({ ok: false, mesaj: hata.message });
    } finally {
      test.disabled = false;
      test.textContent = "Bağlantıyı test et";
    }
  });

  const kaydet = h("button", { class: "dugme", type: "button" }, "Bağlantıyı kaydet");
  kaydet.addEventListener("click", async () => {
    kaydet.disabled = true;
    kaydet.textContent = "Kaydediliyor…";
    try {
      const anahtar = anahtarGirdi.value.trim();
      await api.post("/api/ai/anahtar", {
        anahtar,
        model: modelGirdi.value.trim() || "gemini-3.5-flash-lite",
      });
      if (anahtar) {
        const dogrulama = await api.post("/api/ai/test", { anahtar: "", model: modelGirdi.value.trim() });
        if (dogrulama.ok) bildir("Anahtar kaydedildi ve bağlantı doğrulandı.");
        else bildir(`Kaydedildi, ancak bağlantı doğrulanamadı: ${dogrulama.mesaj}`, "hata");
      } else {
        bildir("Model adı güncellendi.");
      }
      await durumYenile();
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
      kaydet.textContent = "Bağlantıyı kaydet";
    }
  });

  const sil = h("button", { class: "dugme sessiz kucuk", type: "button" }, "Anahtarı kaldır");
  sil.addEventListener("click", async () => {
    if (!window.confirm("Kayıtlı yapay zekâ anahtarı silinsin mi?")) return;
    try {
      await api.post("/api/ai/anahtar", { anahtar: "", model: modelGirdi.value.trim(), sil: true });
      bildir("Anahtar kaldırıldı, yerel koç devrede.");
      await durumYenile();
    } catch (hata) {
      bildir(hata.message, "hata");
    }
  });

  const nasil = aiDurum.aktif
    ? null
    : h(
        "ol",
        { class: "ai-adimlar" },
        h("li", {},
          "Google AI Studio'yu aç, ",
          h("a", { href: "https://aistudio.google.com/apikey", target: "_blank", rel: "noopener", text: "Create API key" }),
          " ile ücretsiz bir anahtar oluştur."),
        h("li", {}, "Çıkan anahtarı (AIza… veya AQ.… ile başlar) kopyalayıp aşağıdaki alana yapıştır."),
        h("li", {}, "Önce “Bağlantıyı test et”; “Bağlantı başarılı” derse “Bağlantıyı kaydet” butonuna bas.")
      );

  return h(
    "section",
    { class: "kart", id: "ai-kart" },
    h("div", { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Yapay zekâ (Gemini)" }),
        h("p", { text: aiDurum.aktif
          ? "Bağlı. Koç kişisel sohbeti ve beceri temelli soruları bu anahtarla üretir."
          : "Koçun kişisel sohbeti ve soru üretimi için ücretsiz Gemini anahtarı gerekir. Anahtarsız da program çalışır (yerel koç)." })),
      rozet(aiDurum.aktif ? "bağlı" : "bağlı değil", aiDurum.aktif ? "basari" : "uyari")),
    h(
      "div",
      { class: "ayar-bolum" },
      nasil,
      h("div", { class: "ayar-izgara" },
        h("div", { class: "form-alan" },
          h("label", { text: "API anahtarı" }),
          anahtarGirdi,
          h("small", { text: "aistudio.google.com/apikey adresinden ücretsiz alınır (AIza… veya AQ.…)." })),
        h("div", { class: "form-alan" },
          h("label", { text: "Model" }),
          modelGirdi,
          h("small", { text: "Önerilen: gemini-3.5-flash-lite (hızlı). Daha derin yanıt: gemini-3.5-flash" }))),
      sonuc,
      h("div", { class: "ipucu" },
        ikon("uyari", 16),
        h("span", { text: "Anahtar yalnızca bu bilgisayardaki veritabanında saklanır ve arayüze geri döndürülmez. Ortak kullanılan bir cihazda girmemen önerilir. Alternatif: .env dosyasına GEMINI_API_KEY=… yazmak." })),
      h("div", { style: { display: "flex", gap: "8px", justifyContent: "flex-end", flexWrap: "wrap" } },
        aiDurum.aktif
          ? sil
          : h("a", { class: "dugme sessiz kucuk", href: "https://aistudio.google.com/apikey", target: "_blank", rel: "noopener" }, "Anahtarı al"),
        test,
        kaydet)
    )
  );
}

function veriKarti(saglik, durum) {
  const yeniProfil = h("button", { class: "dugme ikincil kucuk", type: "button" }, "Yeni öğrenci profili");
  yeniProfil.addEventListener("click", () => {
    if (!window.confirm("Yeni profil kurulumu açılsın mı? Mevcut veriler silinmez.")) return;
    localStorage.removeItem("pusula_profil");
    location.reload();
  });

  return h(
    "section",
    { class: "kart" },
    h("div", { class: "kart-baslik" },
      h("div", {},
        h("h2", { text: "Veri ve yedek" }),
        h("p", { text: "Tüm kayıtlar tek bir SQLite dosyasında tutulur." }))),
    h(
      "div",
      { class: "ayar-bolum" },
      h("div", { class: "ayar-izgara" },
        h("div", { class: "form-alan" },
          h("label", { text: "Veritabanı" }),
          h("p", { style: { fontSize: "13px" }, text: "veri/pusula.db" }),
          h("small", { text: `${saglik.ders} ders · ${saglik.konu} konu · ${saglik.profil} profil` })),
        h("div", { class: "form-alan" },
          h("label", { text: "Yedekleme" }),
          h("a", { class: "dugme ikincil kucuk", href: "/api/yedek", download: "pusula-yedek.db" }, "Veritabanını indir"),
          h("small", { text: "Dosyayı Google Drive veya harici diske kopyalaman yeterli." }))),
      h("div", { style: { display: "flex", gap: "8px", justifyContent: "flex-end" } },
        h("a", { class: "dugme sessiz kucuk", href: "#/panel" }, "Panele dön"),
        yeniProfil)
    )
  );
}

function hakkindaKarti() {
  return h(
    "section",
    { class: "kart" },
    h("div", { class: "kart-baslik" }, h("div", {}, h("h2", { text: "Program hakkında" }))),
    h(
      "div",
      { style: { display: "grid", gap: "10px", fontSize: "13px", color: "#3b4250" } },
      h("p", { text: "YKS Pusula 0.1.0 — iskelet sürümü. Müfredat verisi; ders, konu, sınıf düzeyi, tahmini soru ağırlığı ve Maarif beceri etiketleriyle birlikte gömülüdür." }),
      h("p", { text: "Yöntem: aralıklı tekrar (1-3-7-21-45 gün), aktif geri çağırma (soru çözümü), ön koşul sıralı konu haritası ve deneme netlerinden zayıf konu çıkarımı." }),
      h("p", { text: "Dayanak: Millî Eğitim Bakanlığı Türkiye Yüzyılı Maarif Modeli (beceri temelli öğretim) ve 2028 YKS beceri/bağlam temelli soru modeli." })
    )
  );
}
