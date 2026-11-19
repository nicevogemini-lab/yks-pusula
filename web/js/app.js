// app.js — kabuk, yönlendirme ve açılış
import { api } from "./api.js";
import { h, ikon, hataKarti, yukleniyorKarti } from "./ui.js";
import { kurulumGoster } from "./pages/kurulum.js";
import * as panel from "./pages/panel.js";
import * as mufredat from "./pages/mufredat.js";
import * as plan from "./pages/plan.js";
import * as deneme from "./pages/deneme.js";
import * as koc from "./pages/koc.js";
import * as ayarlar from "./pages/ayarlar.js";

const SAYFALAR = [
  { kod: "panel", ad: "Panel", ikon: "panel", modul: panel },
  { kod: "mufredat", ad: "Müfredat", ikon: "kitap", modul: mufredat },
  { kod: "plan", ad: "Plan", ikon: "takvim", modul: plan },
  { kod: "deneme", ad: "Denemeler", ikon: "grafik", modul: deneme },
  { kod: "koc", ad: "Yapay Zekâ Koçu", ikon: "sohbet", modul: koc },
  { kod: "ayarlar", ad: "Ayarlar", ikon: "ayar", modul: ayarlar },
];

const kok = document.getElementById("kok");
const durum = { meta: null, profil: null, sayfa: "panel", icerik: null };

// Arayüz sürümü: kullanıcı yeni sürümün yüklendiğini menünün altından görür
const SURUM = "v2.5";

// ---------------------------------------------------------------- yardımcı
function kalanGun(isoTarih) {
  if (!isoTarih) return 0;
  const hedef = new Date(`${isoTarih}T00:00:00`);
  const bugun = new Date();
  bugun.setHours(0, 0, 0, 0);
  return Math.max(0, Math.round((hedef - bugun) / 86400000));
}

function aktifSayfa() {
  const kod = (location.hash || "#/panel").replace(/^#\/?/, "");
  return SAYFALAR.find((s) => s.kod === kod) || SAYFALAR[0];
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
        h("b", { text: "YKS Pusula" }),
        h("small", { text: "Koçluk Platformu" })
      )
    ),
    h("div", { class: "menu-baslik", text: "Çalışma Alanı" })
  );

  SAYFALAR.forEach((sayfa) => {
    menu.append(
      h(
        "a",
        { class: "menu-oge", href: `#/${sayfa.kod}`, dataset: { kod: sayfa.kod } },
        ikon(sayfa.ikon, 17),
        h("span", { text: sayfa.ad })
      )
    );
  });

  const yuzdeMetni = `${durum.profil.alan_etiketi} · ${durum.profil.sinif_etiketi}`;
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
      // Giriş kapısı açıksa oturumu kapatma bağlantısı görünür
      durum.meta?.giris_acik
        ? h("a", { class: "cikis-link", href: "/cikis", title: "Oturumu kapat", text: "Çıkış" })
        : null,
      geriSayim,
      h(
        "a",
        { class: "profil-cip", href: "#/ayarlar" },
        h("span", { class: "avatar", text: (durum.profil.ad || "Ö").trim().charAt(0).toUpperCase() }),
        h(
          "div",
          {},
          h("b", { text: durum.profil.ad }),
          h("small", { text: yuzdeMetni })
        )
      )
    )
  );

  kok.replaceChildren(h("div", { class: "uygulama" }, menu, h("div", { class: "govde" }, ustBar, icerik)));

  durum.icerik = icerik;
  durum.baslik = baslik;
  durum.alt = alt;
  durum.geriSayim = geriSayim;
}

function ustBarGuncelle(sayfa) {
  durum.baslik.textContent = sayfa.modul.baslik || sayfa.ad;
  durum.alt.textContent = sayfa.modul.alt || "";
  const gun = kalanGun(durum.profil.sinav_tarihi);
  durum.geriSayim.replaceChildren(
    h("b", { text: String(gun) }),
    document.createTextNode("gün kaldı")
  );
  document.querySelectorAll(".menu-oge").forEach((oge) => {
    oge.classList.toggle("aktif", oge.dataset.kod === sayfa.kod);
  });
  document.title = `${sayfa.modul.baslik || sayfa.ad} · YKS Pusula`;
}

// ---------------------------------------------------------------- yönlendirme
async function sayfaCiz() {
  const sayfa = aktifSayfa();
  durum.sayfa = sayfa.kod;
  ustBarGuncelle(sayfa);
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
  if (!location.hash) location.hash = "#/panel";
  else sayfaCiz();
}

/** Sayfaların veri değişikliğinden sonra çağırdığı tazeleme */
durum.yenile = () => sayfaCiz();
durum.profilGuncellendi = async (yeni) => {
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
    const profiller = await api.get("/api/profiller");
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
    kurulumGoster(kok, durum.meta, async (profil) => {
      durum.profil = profil;
      localStorage.setItem("pusula_profil", String(profil.id));
      kabukCiz();
      yonlendirmeKur();
    });
    return;
  }

  kabukCiz();
  yonlendirmeKur();
}

basla();
