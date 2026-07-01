"""
MediaPipe JS Dosya Indirici
============================
Bu scripti bir kere calistirarak MediaPipe Vision JS kutuphanesini
ve WASM dosyalarini yerel olarak indirir. Boylece tarayici
kamera + el/yuz algilama islemlerini CDN'siz yapabilir.

Kullanim:
  python setup_mediapipe.py

Indirilen dosyalar:
  static/mediapipe/vision_bundle.mjs   (~1.5 MB)
  static/mediapipe/wasm/               (~8 MB toplam)

Not: Bu script internet baglantisi gerektirir (sadece bir kere).
"""

import os
import sys
import urllib.request
import ssl

# MediaPipe Tasks Vision versiyonu
VERSION = "0.10.14"
CDN_BASE = f"https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@{VERSION}"

# Indirilecek dosyalar
DOSYALAR = [
    ("vision_bundle.mjs", f"{CDN_BASE}/vision_bundle.mjs"),
    ("wasm/vision_wasm_internal.js", f"{CDN_BASE}/wasm/vision_wasm_internal.js"),
    ("wasm/vision_wasm_internal.wasm", f"{CDN_BASE}/wasm/vision_wasm_internal.wasm"),
    ("wasm/vision_wasm_nosimd_internal.js", f"{CDN_BASE}/wasm/vision_wasm_nosimd_internal.js"),
    ("wasm/vision_wasm_nosimd_internal.wasm", f"{CDN_BASE}/wasm/vision_wasm_nosimd_internal.wasm"),
]

HEDEF_DIZIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "mediapipe")


def indir(url, hedef_yol):
    """Tek bir dosyayi indirir. Basari/basarisizlik durumunu doner."""
    os.makedirs(os.path.dirname(hedef_yol), exist_ok=True)

    # SSL dogrulama sorunlari icin yedek context
    try:
        ctx = ssl.create_default_context()
    except Exception:
        ctx = ssl._create_unverified_context()

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mate-Setup/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=60) as yanit:
            veri = yanit.read()
            with open(hedef_yol, "wb") as f:
                f.write(veri)
            boyut_kb = len(veri) / 1024
            return True, f"{boyut_kb:.0f} KB"
    except Exception as e:
        return False, str(e)


def main():
    print("=" * 55)
    print("  MediaPipe JS Dosya Indirici")
    print(f"  Versiyon: {VERSION}")
    print(f"  Hedef: {HEDEF_DIZIN}")
    print("=" * 55)

    basarili = 0
    basarisiz = 0

    for dosya_adi, url in DOSYALAR:
        hedef_yol = os.path.join(HEDEF_DIZIN, dosya_adi)

        # Zaten varsa atla
        if os.path.exists(hedef_yol) and os.path.getsize(hedef_yol) > 100:
            print(f"  [MEVCUT] {dosya_adi}")
            basarili += 1
            continue

        print(f"  [INDIRILIYOR] {dosya_adi}...", end=" ", flush=True)
        ok, detay = indir(url, hedef_yol)

        if ok:
            print(f"OK ({detay})")
            basarili += 1
        else:
            print(f"HATA: {detay}")
            basarisiz += 1

    print("-" * 55)

    if basarisiz == 0:
        print(f"  Tumu basarili ({basarili}/{len(DOSYALAR)} dosya).")
        print("  Artik 'python app.py' ile sunucuyu baslatabilirsiniz.")
    else:
        print(f"  {basarisiz} dosya indirilemedi.")
        print("  Internet baglantinizi kontrol edip tekrar deneyin.")
        print()
        print("  Manuel indirme icin:")
        for dosya_adi, url in DOSYALAR:
            hedef_yol = os.path.join(HEDEF_DIZIN, dosya_adi)
            if not os.path.exists(hedef_yol):
                print(f"    {url}")
                print(f"    -> {hedef_yol}")

    print("=" * 55)
    return 0 if basarisiz == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
