// kullanicilar.js — yönetici: yönetici / veli / öğrenci hesap tanımları
import { api } from "../api.js";
import { h, ikon, rozet, bosDurum, bildir } from "../ui.js";

export const baslik = "Kullanıcılar";
export const alt = "Hesap tanımlama, öğrenci-veli bağlantısı ve şifre sıfırlama";

const ROLLER = [
  { kod: "yonetici", ad: "Yönetici", not: "Her şey + kullanıcı tanımlama" },
  { kod: "veli", ad: "Veli", not: "Tanımlama hariç her şey" },
  { kod: "ogrenci", ad: "Öğrenci", not: "Deneme girişi ve ayarlar kapalı" },
];

let uygulama = null;
let profiller = [];
let duzenlenen = null; // düzenlenen kullanıcı sözlüğü (null = yeni kayıt)

export async function ciz(kap, durum) {
  uygulama = durum;
  if (durum.kullanici?.rol !== "yonetici") {
    kap.replaceChildren(bosDurum("Bu sayfa yalnız yöneticiye açık", "Hesap tanımlamaları yönetici tarafından yapılır."));
    return;
  }
  const [liste, profilListesi] = await Promise.all([
    api.get("/api/kullanicilar"),
    api.get("/api/profiller"),
  ]);
  profiller = profilListesi;
  kap.replaceChildren(formKarti(), listeKarti(liste));
}

function yenidenCiz() {
  return ciz(uygulama.icerik, uygulama);
}

// ---------------------------------------------------------------- form
function formKarti() {
  const mevcut = duzenlenen;
  const kullaniciGirdi = h("input", {
    class: "alan",
    type: "text",
    maxlength: "40",
    value: mevcut?.kullanici_adi || "",
    placeholder: "ör. elif.yilmaz",
    disabled: Boolean(mevcut),
  });
  const adGirdi = h("input", {
    class: "alan",
    type: "text",
    maxlength: "60",
    value: mevcut?.ad_soyad || "",
    placeholder: "Ad Soyad",
  });
  const rolSecim = h(
    "select",
    { class: "secim" },
    ROLLER.map((r) =>
      h("option", { value: r.kod, selected: (mevcut?.rol || "ogrenci") === r.kod }, r.ad))
  );
  const sifreGirdi = h("input", {
    class: "alan",
    type: "password",
    maxlength: "128",
    placeholder: mevcut ? "Boş bırakırsan değişmez" : "En az 6 karakter",
  });

  // Öğrenci: tek profile bağlıdır
  const ogrenciSecim = h(
    "select",
    { class: "secim" },
    profiller.map((p) =>
      h("option", { value: p.id, selected: mevcut?.profil_id === p.id }, `${p.ad} · ${p.sinif_etiketi}`))
  );

  // Veli: birden çok öğrenciyi görür
  const ogrenciKutulari = h(
    "div",
    { style: { display: "grid", gap: "6px" } },
    profiller.map((p) => {
      const kutu = h("input", {
        type: "checkbox",
        checked: (mevcut?.profil_idler || []).includes(p.id),
      });
      kutu.dataset.profilId = String(p.id);
      return h(
        "label",
        { style: { display: "flex", alignItems: "center", gap: "8px", fontSize: "13px" } },
        kutu,
        h("span", { text: `${p.ad} · ${p.sinif_etiketi}` })
      );
    })
  );

  const ogrenciAlani = h("div", { class: "form-alan" }, h("label", { text: "Bağlı öğrenci" }), ogrenciSecim);
  const veliAlani = h("div", { class: "form-alan" }, h("label", { text: "Gördüğü öğrenciler" }), ogrenciKutulari);
  const aktifKutu = h("input", { type: "checkbox", checked: mevcut ? mevcut.aktif : true });
  const rolNotu = h("small");

  function rolleriGuncelle() {
    const rol = rolSecim.value;
    ogrenciAlani.style.display = rol === "ogrenci" ? "" : "none";
    veliAlani.style.display = rol === "veli" ? "" : "none";
    rolNotu.textContent = ROLLER.find((r) => r.kod === rol)?.not || "";
  }
  rolSecim.addEventListener("change", rolleriGuncelle);
  rolleriGuncelle();

  const kaydet = h("button", { class: "dugme", type: "button" }, mevcut ? "Değişiklikleri kaydet" : "Kullanıcı ekle");
  kaydet.addEventListener("click", async () => {
    const seciliOgrenciler = Array.from(ogrenciKutulari.querySelectorAll("input:checked")).map(
      (k) => Number(k.dataset.profilId)
    );
    const govde = {
      rol: rolSecim.value,
      ad_soyad: adGirdi.value.trim(),
      sifre: sifreGirdi.value,
    };
    if (govde.rol === "ogrenci") govde.profil_id = Number(ogrenciSecim.value);
    if (govde.rol === "veli") govde.profil_idler = seciliOgrenciler;
    if (govde.rol !== "ogrenci") govde.profil_id = null;

    kaydet.disabled = true;
    kaydet.textContent = "Kaydediliyor…";
    try {
      if (mevcut) {
        await api.patch(`/api/kullanicilar/${mevcut.id}`, { ...govde, aktif: aktifKutu.checked });
        bildir("Kullanıcı güncellendi.");
      } else {
        await api.post("/api/kullanicilar", { ...govde, kullanici_adi: kullaniciGirdi.value.trim() });
        bildir("Kullanıcı eklendi.");
      }
      duzenlenen = null;
      await yenidenCiz();
    } catch (hata) {
      bildir(hata.message, "hata");
      kaydet.disabled = false;
      kaydet.textContent = mevcut ? "Değişiklikleri kaydet" : "Kullanıcı ekle";
    }
  });

  const vazgec = mevcut
    ? h("button", {
        class: "dugme ikincil",
        type: "button",
        onclick: () => {
          duzenlenen = null;
          yenidenCiz();
        },
      }, "Vazgeç")
    : null;

  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h(
        "div",
        {},
        h("h2", { text: mevcut ? `Kullanıcıyı düzenle · ${mevcut.kullanici_adi}` : "Yeni kullanıcı" }),
        h("p", {
          text: mevcut
            ? "Kullanıcı adı değiştirilemez; şifre alanı boş bırakılırsa eski şifre geçerli kalır."
            : "Öğrenci hesabı bir profille eşleşmeli. Veli hesabı birden çok öğrenciyi görebilir.",
        })
      )
    ),
    h(
      "div",
      { class: "ayar-bolum" },
      h(
        "div",
        { class: "ayar-izgara" },
        h("div", { class: "form-alan" }, h("label", { text: "Kullanıcı adı" }), kullaniciGirdi),
        h("div", { class: "form-alan" }, h("label", { text: "Ad soyad" }), adGirdi),
        h(
          "div",
          { class: "form-alan" },
          h("label", { text: "Rol" }),
          rolSecim,
          rolNotu
        ),
        h(
          "div",
          { class: "form-alan" },
          h("label", { text: mevcut ? "Yeni şifre" : "Şifre" }),
          sifreGirdi,
          h("small", { text: "Şifre sıfırlama bu alandan yapılır; eski oturumlar düşer." })
        ),
        ogrenciAlani,
        veliAlani,
        h(
          "label",
          { class: "form-alan", style: { flexDirection: "row", alignItems: "center", gap: "8px" } },
          aktifKutu,
          h("span", { text: "Hesap aktif", style: { fontSize: "13px" } })
        )
      ),
      h(
        "div",
        { style: { display: "flex", justifyContent: "flex-end", gap: "10px" } },
        vazgec,
        kaydet
      )
    )
  );
}

// ---------------------------------------------------------------- liste
function listeKarti(liste) {
  const tablo = h("table", { class: "sonuc-tablo" });
  tablo.append(
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        h("th", { text: "Kullanıcı" }),
        h("th", { text: "Rol" }),
        h("th", { text: "Bağlantı" }),
        h("th", { text: "Durum" }),
        h("th", { text: "" })
      )
    ),
    h("tbody", {}, liste.map((k) => satir(k)))
  );

  return h(
    "section",
    { class: "kart" },
    h(
      "div",
      { class: "kart-baslik" },
      h(
        "div",
        {},
        h("h2", { text: "Tanımlı hesaplar" }),
        h("p", { text: `${liste.length} hesap · öğrenci hesapları yalnız kendi sayfasını görür.` })
      )
    ),
    liste.length ? tablo : bosDurum("Henüz veli/öğrenci hesabı yok", "Yukarıdaki formdan ekleyebilirsin.")
  );
}

function satir(k) {
  const baglanti =
    k.rol === "ogrenci"
      ? k.profil_adi || "—"
      : k.rol === "veli"
      ? (k.profil_idler || [])
          .map((pid) => profiller.find((p) => p.id === pid)?.ad || `#${pid}`)
          .join(", ") || "Öğrenci atanmadı"
      : "Tüm öğrenciler";

  return h(
    "tr",
    {},
    h(
      "td",
      {},
      h("b", { text: k.ad_soyad || k.kullanici_adi }),
      h("small", { text: k.kullanici_adi, style: { display: "block", color: "#6b7280", marginTop: "2px" } })
    ),
    h("td", {}, rozet(k.rol_etiketi, k.rol === "yonetici" ? "marka" : "")),
    h("td", { text: baglanti, style: { fontSize: "12.5px", color: "#6b7280" } }),
    h("td", {}, k.aktif ? rozet("aktif", "basari") : rozet("pasif", "uyari")),
    h(
      "td",
      {},
      h(
        "div",
        { style: { display: "flex", gap: "6px", justifyContent: "flex-end" } },
        h(
          "button",
          {
            class: "dugme ikincil kucuk",
            type: "button",
            onclick: () => {
              duzenlenen = k;
              yenidenCiz();
            },
          },
          ikon("kalem", 13),
          "Düzenle"
        ),
        h(
          "button",
          {
            class: "dugme ikincil kucuk",
            type: "button",
            onclick: () => durumDegistir(k, { aktif: !k.aktif }),
          },
          k.aktif ? "Pasifleştir" : "Aktifleştir"
        ),
        h(
          "button",
          {
            class: "dugme sessiz kucuk",
            type: "button",
            onclick: () => sil(k),
          },
          "Sil"
        )
      )
    )
  );
}

async function durumDegistir(k, govde) {
  try {
    await api.patch(`/api/kullanicilar/${k.id}`, govde);
    bildir(govde.aktif ? "Hesap açıldı." : "Hesap kapatıldı.");
    await yenidenCiz();
  } catch (hata) {
    bildir(hata.message, "hata");
  }
}

async function sil(k) {
  if (!confirm(`${k.ad_soyad || k.kullanici_adi} hesabı silinsin mi?`)) return;
  try {
    await api.sil(`/api/kullanicilar/${k.id}`);
    bildir("Kullanıcı silindi.");
    await yenidenCiz();
  } catch (hata) {
    bildir(hata.message, "hata");
  }
}
