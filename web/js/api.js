// api.js — sunucu ile konuşan tek nokta
const KOK = "";

async function istek(yol, secenekler = {}) {
  const yanit = await fetch(KOK + yol, {
    headers: { "Content-Type": "application/json" },
    ...secenekler,
  });
  if (yanit.status === 401) {
    // Oturum çerezi düşmüşse giriş ekranına dön
    location.href = "/giris";
    throw new Error("Oturum gerekli");
  }
  if (!yanit.ok) {
    let mesaj = `Sunucu hatası (${yanit.status})`;
    try {
      const govde = await yanit.json();
      if (typeof govde.detail === "string") mesaj = govde.detail;
      else if (Array.isArray(govde.detail)) mesaj = govde.detail.map((d) => d.msg).join(", ");
    } catch (_) { /* gövde JSON değilse varsayılan mesaj kalır */ }
    throw new Error(mesaj);
  }
  return yanit.status === 204 ? null : yanit.json();
}

export const api = {
  get: (yol) => istek(yol),
  post: (yol, govde) => istek(yol, { method: "POST", body: JSON.stringify(govde ?? {}) }),
  patch: (yol, govde) => istek(yol, { method: "PATCH", body: JSON.stringify(govde ?? {}) }),
  sil: (yol) => istek(yol, { method: "DELETE" }),
};
