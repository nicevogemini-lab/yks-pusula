// app.js — kabuk, yönlendirme ve açılış
import { api } from "./api.js";
import { h, ikon, hataKarti, yukleniyorKarti } from "./ui.js";
import * as panel from "./pages/panel.js";
import * as mufredat from "./pages/mufredat.js";
import * as plan from "./pages/plan.js";
import * as okul from "./pages/okul.js";
import * as analiz from "./pages/analiz.js";
import * as deneme from "./pages/deneme.js";
import * as koc from "./pages/koc.js";
import * as ayarlar from "./pages/ayarlar.js";
import * as kullanicilar from "./pages/kullanicilar.js";

// yetki: sayfayı görebilen roller (yoksa herkes görür)
// siniflar: sayfanın anlamlı olduğu sınıflar (yoksa her sınıf); mezun = 0
const SAYFALAR = [
  { kod: "panel", ad: "Panel", ikon: "panel", modul: panel },
  { kod: "mufredat", ad: "Müfredat", ikon: "kitap", modul: mufredat },
  { kod: "plan", ad: "Plan", ikon: "takvim", modul: plan },
  // Okul çizelgesi yalnız okullu öğrencide; mezunda plan TYT/AYT konularına göre kurulur
  { kod: "okul", ad: "Ders Programı", ikon: "okul", modul: okul, siniflar: [11, 12] },
  { kod: "analiz", ad: "Analiz", ikon: "grafik", modul: analiz },
  { kod: "deneme", ad: "Denemeler", ikon: "kalem", modul: deneme, yetki: ["yonetici", "veli"] },
  { kod: "koc", ad: "Yapay Zekâ Koçu", ikon: "sohbet", modul: koc },
  { kod: "ayarlar", ad: "Ayarlar", ikon: "ayar", modul: ayarlar, yetki: ["yonetici", "veli"] },
  { kod: "kullanicilar", ad: "Kullanıcılar", ikon: "hedef", modul: kullanicilar, yetki: ["yonetici"] },
];

const kok = document.getElementById("kok");
const durum = { meta: null, kullanici: null, profiller: [], profil: null, sayfa: "panel", icerik: null };

// Arayüz sürümü: kullanıcı yeni sürümün yüklendiğini menünün altından görür
const SURUM = "v3.6.2";

// ---------------------------------------------------------------- yardımcı
function kalanGun(isoTarih) {
  if (!isoTarih) return 0;
  const hedef = new Date(`${isoTarih}T00:00:00`);
  const bugun = new Date();
  bugun.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((hedef - bugun) / 86400000));
}

/** Oturum sahibinin rolüne ve profilin sınıfına göre görünen sayfalar */
function gorunurSayfalar() {
  const rol = durum.kullanici?.rol || "yonetici";
  const sinif = durum.profil?.sinif;
  return SAYFALAR.filter(
    (s) =>
      (!s.yetki || s.yetki.includes(rol)) &&
      (!s.siniflar || s.siniflar.includes(sinif))
  );
}

/** Menüde görünmeyen bir adres yazılırsa ilk sayfaya düşer */
function istenenSayfa() {
  const kod = (location.hash || "#/panel").replace(/^#\/?/, "");
  return gorunurSayfalar().find((s) => s.kod === kod) || null;
}

function aktifSayfa() {
  const sayfalar = gorunurSayfalar();
  return istenenSayfa() || sayfalar[0] || SAYFALAR[0];
}

// ---------------------------------------------------------------- kabuk
function kabukCiz() {
  const menu = h("nav", { class: "yan-menu" });
  menu.append(
    h(
      "a",
      { class: "marka", href: "#/panel" },
      h("span", { class: "marka-isaret" }, ikon("pusula", 21)),
      h(
        "div",
        { class: "marka-metin" },
        h("b", { text: "A-KEY" }),
        h("small", { text: "Üniversiteye giriş anahtarı" })
      )
    ),
    h("div", { class: "menu-baslik", text: "Çalışma Alanı" })
  );

  gorunurSayfalar().forEach((sayfa) => {
    menu.append(
      h(
        "a",
        { class: "menu-oge", href: `#/${sayfa.kod}`, dataset: { kod: sayfa.kod } },
        ikon(sayfa.ikon, 17),
        h("span", { text: sayfa.ad })
      )
    );
  });

  const yuzdeMetni = durum.profil
    ? `${durum.profil.alan_etiketi} · ${durum.profil.sinif_etiketi}`
    : "Öğrenci seçilmedi";
  menu.append(
    h(
      "div",
      { class: "menu-alt" },
      h("b", { text: "Türkiye Yüzyılı Maarif Modeli" }),
      h("span", { text: "Beceri ve bağlam temelli hazırlık · 2028 YKS" }),
      h("small", { class: "menu-surum", text: `Arayüz ${SURUM} · tam gün akışı` })
    )
  );

  const baslik = h("h1", { class: "sayfa-baslik" });
  const alt = h("p", { class: "sayfa-alt" });
  const geriSayim = h("span", { class: "geri-sayim-cip" });
  const icerik = h("main", { class: "sayfa-icerik", id: "icerik" });

  const ustBar = h(
    "header",
    { class: "ust-bar" },
    h("div", {}, baslik, alt),
    h(
      "div",
      { class: "ust-sag" },
      // Öğrenci tek profil görür; veli/yönetici öğrenci değiştirebilir
      durum.profiller.length > 1 ? profilSecici() : null,
      durum.kullanici?.giris_zorunlu
        ? h("a", { class: "cikis-link", href: "/cikis", title: "Oturumu kapat", text: "Çıkış" })
        : null,
      geriSayim,
      // Yönetici öğrenci seçmeden de kabuğu kullanır; çip o durumda bilgi verir
      durum.profil
        ? h(
            "a",
            { class: "profil-cip", href: "#/ayarlar", title: durum.kullanici?.rol_etiketi || "" },
            h("span", {
              class: "avatar",
              text: (durum.profil.ad || "Ö").trim().charAt(0).toUpperCase(),
            }),
            h("div", {}, h("b", { text: durum.profil.ad }), h("small", { text: yuzdeMetni }))
          )
        : h(
            "span",
            { class: "profil-cip", title: "Tanımlı öğrenci yok" },
            h("span", { class: "avatar", text: "—" }),
            h(
              "div",
              {},
              h("b", { text: "Öğrenci yok" }),
              h("small", { text: "Kullanıcılar sayfasından ekle" })
            )
          ),
      oturumCipi()
    )
  );

  kok.replaceChildren(h("div", { class: "uygulama" }, menu, h("div", { class: "govde" }, ustBar, icerik)));

  durum.icerik = icerik;
  durum.baslik = baslik;
  durum.alt = alt;
  durum.geriSayim = geriSayim;
}

/** Üst barda oturum sahibinin adı ve rolü */
function oturumCipi() {
  const kullanici = durum.kullanici;
  if (!kullanici) return null;
  return h(
    "span",
    { class: "oturum-cip", title: `Kullanıcı adı: ${kullanici.kullanici_adi}` },
    h("b", { text: kullanici.ad }),
    h("small", { text: kullanici.rol_etiketi })
  );
}

/** Veli/yönetici için öğrenci seçici */
function profilSecici() {
  const secim = h(
    "select",
    {
      class: "secim profil-secici",
      title: "Görüntülenen öğrenci",
      onchange: (olay) => {
        const secili = durum.profiller.find((p) => p.id === Number(olay.target.value));
        if (!secili) return;
        durum.profil = secili;
        localStorage.setItem("pusula_profil", String(secili.id));
        kabukCiz();
        sayfaCiz();
      },
    },
    durum.profiller.map((p) =>
      h("option", { value: p.id, selected: durum.profil.id === p.id }, p.ad))
  );
  return secim;
}

function ustBarGuncelle(sayfa) {
  durum.baslik.textContent = sayfa.modul.baslik || sayfa.ad;
  durum.alt.textContent = sayfa.modul.alt || "";
  // Geri sayım öğrenciye bağlı; yönetici öğrenci seçmeden gün sayısı gösterilmez
  if (durum.profil) {
    const gun = kalanGun(durum.profil.sinav_tarihi);
    durum.geriSayim.replaceChildren(
      h("b", { text: String(gun) }),
      document.createTextNode("gün kaldı")
    );
  } else {
    durum.geriSayim.replaceChildren();
  }
  document.querySelectorAll(".menu-oge").forEach((oge) => {
    oge.classList.toggle("aktif", oge.dataset.kod === sayfa.kod);
  });
  document.title = `${sayfa.modul.baslik || sayfa.ad} · A-KEY`;
}

// ---------------------------------------------------------------- yönlendirme
async function sayfaCiz() {
  const sayfalar = gorunurSayfalar();
  const secili = istenenSayfa();
  // Menüde olmayan sayfa adresi (ör. mezunda Ders Programı) ilk sayfaya döner
  if (!secili && location.hash) {
    location.hash = `#/${(sayfalar[0] || SAYFALAR[0]).kod}`;
    return;
  }
  const sayfa = secili || sayfalar[0] || SAYFALAR[0];
  durum.sayfa = sayfa.kod;
  ustBarGuncelle(sayfa);
  // Öğrenci seçili değilse yalnız Kullanıcılar açılır
  if (!durum.profil && sayfa.kod !== "kullanicilar") {
    durum.icerik.replaceChildren(
      h(
        "section",
        { class: "kart" },
        h(
          "div",
          { class: "kart-baslik" },
          h(
            "div",
            {},
            h("h2", { text: "Önce öğrenci tanımla" }),
            h("p", {
              text: "Panel, müfredat, plan ve analiz öğrenci kaydına göre kurulur. Kullanıcılar sayfasından öğrenci ekleyip sınıfını ata.",
            })
          )
        ),
        h(
          "div",
          { style: { display: "flex", justifyContent: "flex-end" } },
          h("a", { class: "dugme", href: "#/kullanicilar", text: "Kullanıcılar sayfasına git" })
        )
      )
    );
    return;
  }
  durum.icerik.replaceChildren(yukleniyorKarti());
  try {
    await sayfa.modul.ciz(durum.icerik, durum);
  } catch (hata) {
    durum.icerik.replaceChildren(hataKarti(hata));
  }
}

let yonlendirmeKuruldu = false;
function yonlendirmeKur() {
  if (!yonlendirmeKuruldu) {
    window.addEventListener("hashchange", sayfaCiz);
    yonlendirmeKuruldu = true;
  }
  // Varsayılan sayfa: yönetici yönetim ekranına, diğerleri kendi paneline düşer
  if (!location.hash) {
    location.hash = durum.kullanici?.rol === "yonetici" ? "#/kullanicilar" : "#/panel";
  } else sayfaCiz();
}

/** Sayfaların veri değişikliğinden sonra çağırdığı tazeleme */
durum.yenile = () => sayfaCiz();
durum.profilGuncellendi = async (yeni) => {
  const sirada = durum.profiller.findIndex((p) => p.id === yeni.id);
  if (sirada >= 0) durum.profiller[sirada] = yeni;
  durum.profil = yeni;
  kabukCiz();
  await sayfaCiz();
};
durum.cikis = () => {
  localStorage.removeItem("pusula_profil");
  location.reload();
};

// ---------------------------------------------------------------- açılış
async function basla() {
  try {
    durum.meta = await api.get("/api/meta");
    durum.kullanici = durum.meta.oturum || null;
    const profiller = await api.get("/api/profiller");
    durum.profiller = profiller;
    const kayitli = Number(localStorage.getItem("pusula_profil"));
    durum.profil = profiller.find((p) => p.id === kayitli) || profiller[0] || null;
  } catch (hata) {
    kok.replaceChildren(
      h(
        "div",
        { class: "kurulum" },
        h(
          "div",
          { class: "kurulum-kart", style: { padding: "28px" } },
          h("h1", { text: "Sunucuya ulaşılamadı", style: { fontSize: "19px", marginBottom: "8px" } }),
          h("p", {
            text: "Program penceresini kapatmış olabilirsin. Proje klasöründeki baslat.py dosyasını çalıştırıp bu sayfayı yenile.",
            style: { fontSize: "13px", color: "#6b7280", marginBottom: "14px" },
          }),
          h("pre", {
            text: String(hata.message || hata),
            style: {
              background: "#f4f7fc",
              border: "1px solid #e3e9f2",
              borderRadius: "9px",
              padding: "10px 12px",
              fontSize: "12px",
              whiteSpace: "pre-wrap",
            },
          })
        )
      )
    );
    return;
  }

  if (!durum.profil) {
    // Veli/öğrenci kendi profiline kavuşamaz: öğrenciyi ve sınıfını yönetici atar
    const rol = durum.kullanici?.rol;
    if (rol && rol !== "yonetici") {
      kok.replaceChildren(
        h(
          "div",
          { class: "kurulum" },
          h(
            "div",
            { class: "kurulum-kart", style: { padding: "28px" } },
            h("h1", {
              text: "Henüz öğrenci atanmadı",
              style: { fontSize: "19px", marginBottom: "8px" },
            }),
            h("p", {
              text: "Yönetici hesabına bir öğrenci bağlayınca program burada açılır. Sınıf ve alan bilgisini de yönetici belirler; yeniden denemek için sayfayı yenile.",
              style: { fontSize: "13px", color: "#6b7280" },
            })
          )
        )
      );
      return;
    }
    // Yönetici sınava girmez: öğrenci kaydı yokken de yönetim kabuğu açılır
    if (!location.hash || location.hash === "#/panel") location.hash = "#/kullanicilar";
    kabukCiz();
    yonlendirmeKur();
    return;
  }

  kabukCiz();
  yonlendirmeKur();
}

basla();
