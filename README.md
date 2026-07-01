# MATE — Endüstriyel Robot Kontrol Paneli

MATE, Raspberry Pi (Pi Zero / Pi 4 vb.) gibi son derece kısıtlı donanıma sahip (örn. 512MB RAM) gömülü sistemler için geliştirilmiş, **tamamen "Edge Processing" (Uç Bilişim)** mimarisiyle çalışan endüstriyel bir yapay zeka kontrol panelidir. 

Sistem, yapay zeka görüş (Computer Vision) ve ses-metin dönüşümü (STT) gibi çok ağır yükleri Raspberry Pi'nin üzerinden alarak tamamen kontrolcü cihazın (PC/Telefon) tarayıcısına yıkar. Bu sayede Pi'nin işlemcisi **%0'a yakın AI yüküyle** çalışır.

## 📸 Ekran Görüntüsü

*Endüstriyel Dashboard ve Donanımsal Kamera Akışı:*

<img width="300" height="400" alt="mobil_gorunum" src="https://github.com/user-attachments/assets/b0f00fb6-a083-484d-9999-f55ca535ad32" />

</p>

## 🚀 Öne Çıkan Özellikler (Edge Mimari)

*   **Sıfır CPU Yükü ile Görüntü İşleme:** Pi üzerindeki kamera görüntüsü, donanımsal hızlandırıcı (`rpicam-vid`) kullanılarak hiçbir CPU kodlamasına girmeden doğrudan MJPEG olarak sunulur.
*   **Tarayıcı Tabanlı MediaPipe (WASM):** Yüz algılama, duygu analizi ve el hareketi tanıma işlemleri Pi'de değil; PC'nizin/Telefonunuzun tarayıcısında (WebAssembly motoruyla) yerel olarak gerçekleşir.
*   **İstemci Tabanlı STT:** Sesinizi metne çevirmek için Pi'ye ffmpeg veya ağır ses kütüphaneleri kurulmaz. Tarayıcının yerleşik `webkitSpeechRecognition` motoru kullanılır ve Pi'ye sadece metin iletilir.
*   **Offline/LAN Uyumluluğu:** Sistem dış dünyaya kapalı bir yerel ağda (LAN) çalışmak üzere tasarlanmıştır. Gerekli tüm yapay zeka (MediaPipe JS/WASM) kütüphaneleri Pi'nin içinde barındırılır.
*   **Fiziksel Robot Yanıtı:** Gönderilen metin Gemini LLM tarafından işlenir ve robotun üzerine bağlı hoparlörden `gTTS/espeak` ile doğrudan fiziksel ortama sesli olarak aktarılır.
*   **Kurumsal SCADA Arayüzü:** Hiçbir emoji veya harici CSS/Font (CDN) kullanılmadan, saf SVG ikonlar ve endüstriyel bir renk paletiyle tasarlanmış profesyonel arayüz.

---

## 🏗️ Mimari Şema

```text
Raspberry Pi (Server - 512MB RAM)                PC / Telefon (Client)
=================================                =====================
[Kamera] -> rpicam-vid (Donanım) ---- MJPEG ---> [Tarayıcı] <img> -> <canvas>
                                                          |
[Hoparlör] <- gTTS (Ses Çıkışı)                   [MediaPipe JS / WASM] (Yüz/El Analizi)
                                                          |
[Gemini API] <- Metin İsteği <------ (JSON) <--- [Mikrofon (STT)]
```

---

## 🛠️ Kurulum Gereksinimleri

### 1. Sistem Kütüphaneleri (Raspberry Pi)
OpenCV ve TTS motorları için gerekli sistem paketlerini kurun:
```bash
sudo apt-get update
sudo apt-get install -y mpg123 espeak alsa-utils
sudo apt-get install -y libatlas-base-dev libopenblas-dev libglib2.0-0
```

### 2. Python Sanal Ortam (Virtual Environment)
Sistem kütüphanelerinin bozulmaması için (PEP 668) projeyi izole bir ortama kuruyoruz:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Paket Bağımlılıkları
**Önemli:** Raspberry Pi (ARM) mimarisinde stabilite için Numpy v1.x ve OpenCV v4.9 (ve altı) şarttır.
```bash
pip install "numpy<2"
pip install "opencv-python-headless<4.10"
pip install flask gtts requests
```

### 4. MediaPipe Modellerini İndirme
Tarayıcının AI işlemleri yapabilmesi için gereken dosyaları Pi'ye indiriyoruz:
```bash
# JS ve WebAssembly dosyalarını indir (1 kere çalıştırılır)
python setup_mediapipe.py

# Yapay Zeka task modellerini indir
wget -qO face_landmarker.task https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
wget -qO gesture_recognizer.task https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
```

### 5. API Anahtarı
`app.py` içerisindeki 55. satırda bulunan `GEMINI_API_KEY` değişkenine kendi Gemini API anahtarınızı girin.

---

## 🚀 Sistemi Başlatma

Sanal ortam aktifken (`source .venv/bin/activate`):

Eğer standart bir USB kamera kullanıyorsanız:
```bash
export CAMERA_SOURCE="0"
python app.py
```

Eğer Raspberry Pi Kamera Modülü (Şerit kablolu IMX219 vb.) kullanıyorsanız **(Önerilen, %0 CPU Yükü)**:
```bash
export CAMERA_SOURCE="rpicam"
python app.py
```

---

## 🌐 Tarayıcıdan Bağlantı ve Mikrofon İzni

Uygulama çalıştıktan sonra bilgisayar veya telefonunuzun tarayıcısından `http://<RASPBERRY_PI_IP_ADRESI>:5000` adresine girin.

**Mikrofon İzni İçin Önemli Not (Chrome/Edge):**
Tarayıcılar `http://` bağlantılarında güvenli olmadığı için mikrofonu otomatik bloklar. Yerel ağınızda SSL (https) olmadan mikrofonu açmak için:
1. Chrome'da adres çubuğuna yazın: `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. Kutuya Pi'nizin adresini yazın (Örn: `http://192.168.1.50:5000`)
3. `Enabled` yapıp tarayıcıyı yeniden başlatın.

Artık mikrofona tıklayıp konuştuğunuzda sesiniz yazıya dökülecek ve Raspberry Pi üzerinden size fiziksel olarak yanıt verecektir!

---
*Developed for advanced hardware constraints by deep architectural optimizations.*
