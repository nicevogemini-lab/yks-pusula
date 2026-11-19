# YKS Pusula

Türkiye Yüzyılı Maarif Modeli'ne göre kurgulanmış, yapay zekâ destekli YKS koçluk
platformu. Öğrencinin alanı (Sayısal / Eşit Ağırlık / Sözel), sınıf düzeyi (11, 12,
mezun) ve hedefi doğrultusunda günlük çalışma planı üretir; deneme sonuçlarını
analiz eder; yapay zekâ koçuyla kişisel rehberlik verir.

> Sürüm 0.1.0 — iskelet. Çalışır durumda: müfredat haritası, plan üretimi, deneme
> analizi, koç sohbeti, ayarlar ve yedekleme.

## Neden bu kurgu

- **Maarif Modeli**: 22 ders / 270 konu; her konu sınıf düzeyi, tahmini soru ağırlığı
  ve beceri etiketleriyle (kavramsal beceri, alan becerisi, sosyal-duygusal beceri,
  okuryazarlık) tanımlı.
- **2028 soru modeli**: Bu kuşak, beceri ve bağlam temelli sorularla sınava giren ilk
  grup. Program ezber yerine bilgiyi yeni duruma uygulamayı öne çıkarır; koç istemi de
  bu çerçevede kurulur.
- **Öğrenme bilimi**: aralıklı tekrar (1-3-7-21-45 gün), aktif geri çağırma (soru
  çözümü), ön koşul sıralı konu haritası, deneme netlerinden zayıf konu çıkarımı.

## Hızlı başlangıç

Gereken: Python 3.11 veya üzeri ([python.org](https://www.python.org/downloads/),
kurulumda "Add python.exe to PATH" işaretli olsun).

```powershell
cd YKS-Pusula
.\baslat.ps1
```

PowerShell betik çalıştırma izni kapalıysa çift tıklanabilir sarmalayıcıyı kullan:
`baslat.cmd` (politika ayarını değiştirmeden `baslat.ps1`'i çalıştırır).

`baslat.ps1` ilk çalıştırmada `.venv` klasörünü kurar, bağımlılıkları yükler,
`.env` dosyasını oluşturur ve sunucuyu açar. Tarayıcı kendiliğinden açılır:

- Bu bilgisayar: <http://127.0.0.1:8317>
- Aynı ağdaki telefon/tablet: `http://<bilgisayarın-yerel-ip'si>:8317`

Kapatmak için PowerShell penceresinde `Ctrl + C`.

### Telefondan bağlanma

Telefon aynı Wi-Fi ağındaysa ve yine bağlanamıyorsa Windows güvenlik duvarı
8317 portunu kapatıyor olabilir. Bir kez, yönetici olarak:

```powershell
.\guvenlik_duvari.ps1
```

Betik 8317 portunu **yalnızca aynı ağdaki cihazlara** (`LocalSubnet`) açar ve
telefondan yazılacak adresi ekrana basar (`http://192.168.x.x:8317`).
Modemde "istemci yalıtımı / AP isolation" açıksa cihazlar birbirini göremez;
bu durumda modem ayarından kapatılması gerekir.

Elle çalıştırma:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe baslat.py
```

## İlk açılış

1. Alan seçimi (Sayısal / Eşit Ağırlık / Sözel)
2. Sınıf seçimi (11 / 12 / Mezun) — sınav tarihi otomatik hesaplanır
3. Günlük hedef süre ve hedef sıralama

Kurulum bitince panel açılır: kalan gün, müfredat ilerlemesi, bugünün planı,
öncelikli konular, haftalık çalışma grafiği ve son denemeler.

## Hedef sıralama → netler → program

Hedef sıralama tek bir sayı değil, programın kaynağıdır. Zincir şöyle işler:

1. **Sıralama → gereken net.** Alanına göre eşik tablosundan (ör. sayısal
   20.000 ≈ TYT 90 / AYT 60 net) logaritmik ölçekte ara değer alınır.
2. **Netler → ders hedefleri.** Toplam net, derslerin soru sayısı payına göre
   dağıtılır (Türkçe 30, Temel Matematik 24, Matematik 24, Fizik 10,5 …).
3. **Ders hedefi + deneme netleri → ağırlık.** Ders ağırlığı
   `√hedef net × (0,4 … 1,6 açık oranı)` ile hesaplanır: hedefe ulaşmış ders
   bakım ağırlığına düşer, açığı büyük ders en çok bloğu alır.
4. **Ağırlık → plan.** Günlük konu kotası bu paylara göre açık kotası yöntemiyle
   dağıtılır; hafta boyunca hiçbir ders tamamen dışlanmaz.

Öğrenci bir derste hedefe yaklaştıkça bloklar kendiliğinden diğer açıklara
kayar. Hedef sıralama boş bırakılırsa 100.000 eşdeğeri kullanılır ve arayüzde
"varsayılan" olarak işaretlenir. Hedefi değiştirmek Ayarlar'dan yapılır ve
7 günlük plan anında yeniden üretilir.

## Sayfalar

| Sayfa | Ne yapar |
| --- | --- |
| Panel | Günlük özet, **hedef sıralama ve gereken netler**, öncelikli konular, haftalık çalışma, ders bazlı ilerleme |
| Müfredat | Ders → konu listesi; durum (başlanmadı / çalışılıyor / tamam / tekrar) ve 1-5 özgüven puanı |
| Plan | Günlük / haftalık / aylık program; açık konu önceliği, **her gün matematik + paragraf**, aylık takvimde cumartesi deneme, pazar tekrar |
| Denemeler | TYT ve AYT deneme girişi, canlı net hesabı, **hedefe kalan net**, tahmini puan, **konu bazlı açık analizi**, **yapay zekâ değerlendirmesi ve deneme takvimi** |
| Yapay Zekâ Koçu | Kişisel sohbet + beceri temelli soru üretimi; hedef sıralamaya göre ders ve program önerisi |
| Ayarlar | Profil, **hedef sıralama (planı belirler)**, Gemini anahtarı, veritabanı yedeği |

### Konu ağırlığı ve deneme analizi

Deneme sayfasındaki "Konu ağırlığı analizi" kartı iki katmanı birleştirir:

1. **Sınav ağırlığı.** Dersin YKS soru sayısı, konuların 1-3 arası soru
   yoğunluğuna göre paylaştırılır; her konunun sınavdaki **beklenen soru sayısı**
   çıkar (TYT 120 + AYT 80 = 200 soru).
2. **Öğrenci başarısı.** Denemelerdeki doğru/yanlış/boş toplamı ders bazında,
   çalışma günlüğündeki doğru/yanlış ise konu bazında başarı oranına çevrilir.

`Etkin puan = beklenen soru × (1 − başarı) × hedef ders çarpanı`. Puanı yüksek
konu, "çalışırsan en çok net kazanırsın" demektir; günlük, haftalık ve aylık
programlar bu sıradan kurulur. Aylık görünümde hafta içi konu blokları, cumartesi
tam süreli deneme (TYT/AYT dönüşümlü), pazar tekrar ve hata defteri yer alır.

### Konu bazlı açık analizi

Deneme analizi ders adında durmaz; açık **konu** bazında tespit edilir. Her
deneme kartında **Yanlış konuları işaretle** bölümü vardır: o denemede yanlış
çıkan dersin konuları çip olarak seçilir ve `POST /api/deneme/{id}/konular` ile
`deneme_konulari` tablosuna yazılır. Böylece deneme kanıtı konu seviyesine iner.

Konu başarısı çalışma günlüğü + deneme işareti birleşiminden çıkar:

```
başarı = (çalışma_dogru + 1) / (çalışma_doğru + çalışma_yanlış + deneme_yanlış + 2)
```

Laplace düzeltmesi az soruda %0 / %100 uçlarına savrulmayı önler. "Konu bazlı
açıklar" tablosu yalnız **konuya özgü kanıtı** olan satırları gösterir: denemede
işaretlenen yanlış ya da en az 4 soruluk çalışma günlüğü. Ders ortalamasından
türetilen tahmin konu ayrımı taşımadığı için listeye girmez; bu, tablonun
"her konu açık" görünmesini engeller.

### Günlük matematik ve paragraf

Programın değişmez iki bloğu vardır: **her gün 20 matematik** (en yüksek etkin
puanlı ilk üç matematik konusu arasında döner) ve **her gün 20 paragraf**
sorusu. Bu bloklar günlük hedeften düşülerek yazılır, toplam süre öğrencinin
günlük hedefine yakın kalır. Matematik derslerinin kota payı
`MATEMATIK_KATSAYI = 1.35` ile yükseltilir.

Konu önceliği artık doğrudan açığa bağlıdır:

```
öncelik = etkin_puan × 6 + 2 × deneme_yanlış
```

Üzerine durum (tekrar/başlanmadı) ve düşük özgüven eklenir; 9-10. sınıf konusu
sağlam biliniyorsa geri plana düşer. Yani denemede işaretlediğin yanlış konu,
ertesi gün planın ilk bloklarına girer.

### Yapay zekâ değerlendirmesi ve deneme takvimi

"Konu ağırlığı analizi" kartının altındaki **Yapay zekâ değerlendirmesi**
kartında **Değerlendir** düğmesi, ders/konu tablosu, konu açıkları ve haftalık
program taslağını Gemini'ye yorumlatır. Anahtar yoksa ya da bağlantı
kurulamazsa aynı sayılardan yerel metin üretilir ve kart bunu "Yerel analiz"
rozetiyle belirtir. Metin beş başlık taşır: genel durum, konu bazlı açıklar,
açığı en hızlı kapatan 3 hamle, haftalık program, deneme planı yorumu. İstem
"ders adıyla yetinme, açığı konu adıyla söyle" kuralını taşır. Son değerlendirme
`Ayar` tablosunda saklanır; sayfa yenilendiğinde yapay zekâya yeniden gidilmez,
konu açıkları ve program taslağı güncel veriden yeniden hesaplanır.

Kartta ayrıca her gün matematik + paragraf sorusu ve günün odak konularını
gösteren **haftalık program** tablosu yer alır. **Programı plana yaz**, 7 günlük
günlük planı bu sırayla tazeler (`POST /api/plan/{id}/uret?gun=7`).

Aynı değerlendirme deneme sıklığını da belirler:

- **Haftada 1 deneme** — deneme geçmişi yoksa ya da net artışı hedefe yetiyorsa.
- **3 günde 1 deneme** — son iki deneme arasındaki net artışı haftalık hedefin
yarısının altındaysa; ya da sınava 180 günden az kalmış ve 40+ net açık varsa.

Takvim **cumartesi** başlar: 7 günlük tempoda TYT/AYT dönüşümlü, 3 günlük
tempoda TYT → AYT → zayıf dersin branş denemesi döngüsü. Her sınav için
**odak konular** (ders başına en yüksek etkin puanlı konu) ve hedef net
gösterilir. **Takvimi plana yaz**, sınav günlerindeki bekleyen konu bloklarını
kaldırır; yerine sınav + 40 dk "deneme analizi" bloğu ekler. Aylık planın
cumartesi denemeleri de bu adımla tazelenir, böylece çift blok oluşmaz.

## Yapay zekâ

İki katmanlı çalışır:

- **Gemini bağlı**: Ayarlar > Yapay zekâ (Gemini) kartındaki adımları izle:
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey) adresinden ücretsiz
  anahtar oluştur, alana yapıştır, **Bağlantıyı test et** ile doğrula (geçersiz
  anahtar / kota / model hatalarını Türkçe açıklar), sonra **Bağlantıyı kaydet**.
  Kaydetme, yeni anahtarı otomatik olarak bir kez daha dener. Koç, alan ve sınıf
  bilgisini bilerek yanıtlar.
- **Anahtar yok**: yerel koç devreye girer. Veritabanındaki ilerleme, öncelikli konular
  ve deneme netlerinden somut öneri üretir. Program internetsiz de anlamlı çalışır;
  Koç sayfası anahtarı nereden alacağını ve nereye gireceğini gösterir.

Her iki katman da öğrencinin hedef sıralamasını bilir: “YKS'de başarı sıralamam ne
olmalı?” gibi bir soruya gereken TYT/AYT netleri, ders bazlı açıklar ve haftalık net
hızıyla yanıt verir; ardından çalışma programını bu netlere göre kurar.

Anahtar yalnızca bu bilgisayardaki SQLite dosyasında saklanır, arayüze geri
döndürülmez. Alternatif olarak `.env` dosyasına `GEMINI_API_KEY=…` yazılabilir;
panelden girilen anahtar geçerlidir ve `.env` değerini ezer.

## Veri, yedek, taşıma

- Tüm kayıtlar tek dosyada: `veri/pusula.db`
- Panelden indirme: Ayarlar > "Veritabanını indir" (`/api/yedek`)
- Yolu değiştirmek için `.env` içinde `PUSULA_DB` (mutlak yol da olabilir)

### Ayrı bir klasöre taşıma

```powershell
powershell -ExecutionPolicy Bypass -File .\tasi.ps1 -Hedef "C:\Users\<kullanıcı>\Desktop" -VeriyiTasi
```

Kaynak kopyalanır; `.venv` taşınmaz (mutlak yol içerir). Yeni yerde bir kez
`.\baslat.ps1` çalıştırınca sanal ortam yeniden kurulur.

### Google Drive

1. [Google Drive for desktop](https://www.google.com/drive/download/) kurulur ve
   `My Drive` bu bilgisayara bağlanır (genelde `G:\My Drive`).
2. `powershell -ExecutionPolicy Bypass -File .\tasi.ps1 -Hedef "G:\My Drive" -VeriyiTasi`
3. `G:\My Drive\YKS-Pusula\baslat.cmd` ile açılır.

Not: Google Drive bir ağ sürücüsü gibi davrandığı için SQLite kilitlenmeleri
yaşanabilir. Veritabanının bulutta değil **yerel diskte** durması önerilir: program
Drive klasöründen çalışsın, `.env` içinde `PUSULA_DB` yerel bir yolu göstersin
(örn. `%LOCALAPPDATA%\YKS-Pusula\pusula.db`). Böylece kod yedeklenir, veri hızlı kalır.

## Klasör yapısı

```
YKS-Pusula/
├── baslat.cmd, baslat.ps1, baslat.py   # başlatıcı
├── tasi.ps1                            # ayrı klasöre / Drive'a kopyalama
├── requirements.txt, .env.example
├── app/
│   ├── main.py               # FastAPI uygulaması, statik dosyalar
│   ├── api.py                # REST uçları (/api/...)
│   ├── models.py             # SQLAlchemy tabloları
│   ├── database.py           # motor, oturum, yol çözümleme
│   ├── seed.py               # müfredatı idempotent yükleme
│   ├── data/                 # TYT + AYT ders/konu verisi
│   └── services/             # plan, puanlama, yapay zekâ
├── web/                      # arayüz (derleme adımı yok, saf ES modülleri)
│   ├── index.html, css/app.css
│   └── js/{api,ui,app}.js, js/pages/*
├── tests/test_api.py         # 11 uçtan uca API testi
└── veri/pusula.db            # veritabanı (otomatik oluşur)
```

Mimari: tek süreç, tek dosya veritabanı, derlemesiz arayüz. Amaç, 10 yıl sonra da
açılabilen bir program: `pip install -r requirements.txt` dışında bağımlılık yok.

## Geliştirme

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # testler
.\.venv\Scripts\python.exe baslat.py             # geliştirme sunucusu
.\.venv\Scripts\python.exe baslat.py --tarayici-acma
```

Deneme girişi, net hesabı (`doğru − yanlış/4`), plan üretimi ve koç yanıtı API testleriyle
kapsanmıştır. Arayüz değişikliğinden sonra en az bir kez tarayıcıda tur atılması önerilir.

## Bilinen sınırlar (sonraki adımlar)

- Konu ağırlıkları ve puan katsayıları tahminidir; ÖSYM/MEB resmî tablolarıyla
  güncellenmeli. Hedef sıralamanın net karşılıkları da yaklaşık eşik tablosudur
  (`app/services/hedef.py`) — kesin puan/sıralama iddiası taşımaz.
- Çoklu öğrenci aynı kurulumda çalışır ama profil değiştirme arayüzü henüz Ayarlar'da
  ("Yeni öğrenci profili").
- Deneme sorularının fotoğraftan okunması, veli raporu ve mobil uygulama kapsam dışı.
