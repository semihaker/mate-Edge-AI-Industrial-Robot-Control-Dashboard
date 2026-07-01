"""
MATE — Endustriyel Kontrol Paneli Backend
==========================================
Raspberry Pi uzerinde calisir.

Gorev dagilimi:
  Pi (bu dosya):
    - Ham kamera akisi (MJPEG, AI islemsiz)
    - LLM sorgu (Gemini API)
    - TTS seslendirme (gTTS + mpg123 / espeak)
    - Ses seviyesi kontrolu (amixer)

  Tarayici (index.html):
    - Goruntu isleme (MediaPipe JS, WASM)
    - Ses-metin donusumu (webkitSpeechRecognition)
    - Arayuz ve kullanici etkilesimi

Kurulum (Raspberry Pi):
  sudo apt-get install -y mpg123 espeak alsa-utils
  pip install flask gtts requests opencv-python-headless
  python setup_mediapipe.py   # MediaPipe JS dosyalari (bir kere)

Calistirma:
  python app.py
"""

import os
import json
import uuid
import subprocess
import tempfile
import mimetypes
import threading
import time
import atexit
import requests
from flask import Flask, render_template, request, jsonify, Response, send_from_directory

# Opsiyonel: kamera icin
try:
    import cv2
    import numpy as np
    CV2_OK = True
except ImportError:
    CV2_OK = False

# MIME kayitlari
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")

# ==========================================================================
#  YAPILANDIRMA
# ==========================================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "BURAYA_KENDI_API_ANAHTARINIZI_YAZIN")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
)
POLLINATIONS_BASE = "https://text.pollinations.ai/"
SYSTEM_PROMPT = (
    "Senin adin Mate. Sen Raspberry Pi tabanli, kucuk ve sevimli bir robot asistansin. "
    "Kisa, samimi ve oz konusursun. Her zaman Turkce cevap verirsin. "
    "Kesinlikle emoji kullanma. Cevaplarini 2-3 cumle ile sinirla."
)

CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "0")
TTS_DIR = tempfile.gettempdir()
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
sohbet_gecmisi = []
_son_komut = {"command": "BEKLE", "gesture": "---", "emotion": "Notr", "target": None}

# ==========================================================================
#  KAMERA — YALNIZCA HAM MJPEG AKISI (SIFIR AI ISLEMI)
# ==========================================================================

_cam_lock = threading.Lock()
_latest_frame_jpg = None
_latest_frame_cv2 = None
_cam_active = False
_shutdown = threading.Event()


def _sinyal_yok_jpg():
    """Kamera bagli degilken gosterilecek statik kare (OpenCV varsa)."""
    if not CV2_OK:
        return b""
    f = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(f, "SINYAL YOK", (210, 230), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (60, 60, 60), 2)
    cv2.putText(f, "Kamera kaynagi: " + str(CAMERA_SOURCE), (140, 270),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (40, 40, 40), 1)
    ret, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return buf.tobytes() if ret else b""


def _kamera_dongusu_rpicam():
    """Raspberry Pi kamerasini (IMX219 vb.) rpicam-vid ile donanimsal okur. SIFIR CPU!"""
    global _latest_frame_jpg, _cam_active
    print("[KAMERA] rpicam-vid donanimsal hizlandirici ile baslatiliyor...")
    
    while not _shutdown.is_set():
        cmd = [
            "rpicam-vid", "-t", "0", "--inline", "--codec", "mjpeg",
            "--width", "640", "--height", "480", "--framerate", "15",
            "--nopreview", "-o", "-"
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=10**6)
        
        with _cam_lock:
            _cam_active = True
            
        chunk = b''
        while not _shutdown.is_set():
            data = proc.stdout.read(8192)
            if not data:
                break
            chunk += data
            
            # Guvenli JPEG (FFD8 -> FFD9) ayiklama
            a = chunk.find(b'\xff\xd8')
            if a != -1:
                b = chunk.find(b'\xff\xd9', a + 2)
                if b != -1:
                    jpg = chunk[a:b+2]
                    chunk = chunk[b+2:]
                    with _cam_lock:
                        _latest_frame_jpg = jpg
                else:
                    chunk = chunk[a:]
                    
        proc.kill()
        with _cam_lock:
            _cam_active = False
            _latest_frame_jpg = _sinyal_yok_jpg()
            
        if not _shutdown.is_set():
            print("[KAMERA] rpicam-vid koptu, yeniden deneniyor...")
            _shutdown.wait(3)


def _kamera_dongusu_cv2():
    """Klasik USB kameralar veya V4L2 aygitlari icin OpenCV dongusu."""
    global _latest_frame_cv2, _cam_active

    if not CV2_OK:
        return

    try:
        kaynak = int(CAMERA_SOURCE)
    except ValueError:
        kaynak = CAMERA_SOURCE

    while not _shutdown.is_set():
        cap = cv2.VideoCapture(kaynak)
        if not cap.isOpened():
            print(f"[KAMERA] Kaynak acilamadi: {kaynak}")
            with _cam_lock:
                _cam_active = False
                _latest_frame_cv2 = None
            _shutdown.wait(5)
            continue

        print(f"[KAMERA] Baglanti kuruldu: {kaynak}")
        with _cam_lock:
            _cam_active = True

        while not _shutdown.is_set() and cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            with _cam_lock:
                _latest_frame_cv2 = frame

        cap.release()
        with _cam_lock:
            _cam_active = False
            _latest_frame_cv2 = None

        if not _shutdown.is_set():
            print("[KAMERA] Baglanti kesildi. Yeniden deneniyor...")
            _shutdown.wait(3)


def _kamera_dongusu():
    if str(CAMERA_SOURCE).lower() == "rpicam":
        _kamera_dongusu_rpicam()
    else:
        _kamera_dongusu_cv2()


def _mjpeg_uret():
    """Son kareyi JPEG olarak surekli yield eder."""
    use_rpicam = str(CAMERA_SOURCE).lower() == "rpicam"
    
    while not _shutdown.is_set():
        buf_bytes = None
        
        with _cam_lock:
            if use_rpicam:
                buf_bytes = _latest_frame_jpg
            else:
                f = _latest_frame_cv2
                if f is None:
                    buf_bytes = _sinyal_yok_jpg()
                elif CV2_OK:
                    ret, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 72])
                    if ret: buf_bytes = buf.tobytes()
                    
        if buf_bytes:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + buf_bytes + b"\r\n")
        
        time.sleep(0.033)


# ==========================================================================
#  LLM + TTS
# ==========================================================================

def gemini_sor(metin):
    prompt = f"{SYSTEM_PROMPT}\n\nKullanici: {metin}"
    try:
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(GEMINI_URL, headers={"Content-Type": "application/json"},
                            data=json.dumps(payload), timeout=15)
        if res.status_code == 200:
            return res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"[LLM] Gemini HTTP {res.status_code}")
    except Exception as e:
        print(f"[LLM] Gemini hatasi: {e}")

    try:
        import urllib.parse
        res = requests.get(f"{POLLINATIONS_BASE}{urllib.parse.quote(prompt)}", timeout=30)
        if res.status_code == 200:
            return res.text.strip()
    except Exception as e:
        print(f"[LLM] Yedek API hatasi: {e}")

    return "Baglanti saglanamadi."


def seslendir(metin):
    dosya = os.path.join(TTS_DIR, f"mate_{uuid.uuid4().hex[:8]}.mp3")
    try:
        from gtts import gTTS
        tts = gTTS(text=metin, lang="tr")
        tts.save(dosya)
        subprocess.run(["mpg123", "-q", dosya],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    except Exception as e:
        print(f"[TTS] gTTS basarisiz ({e}), espeak deneniyor")
        try:
            subprocess.run(["espeak", "-v", "tr", metin],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except Exception as e2:
            print(f"[TTS] espeak basarisiz: {e2}")
    finally:
        if os.path.exists(dosya):
            try:
                os.remove(dosya)
            except OSError:
                pass


# ==========================================================================
#  FLASK ROTALARI
# ==========================================================================

@app.route("/")
def anasayfa():
    return render_template("index.html")


@app.route("/video_feed")
def video_akisi():
    """Ham MJPEG kamera akisi. Hicbir AI islemi uygulanmaz."""
    if not CV2_OK:
        return "Kamera modulu yuklu degil", 503
    return Response(_mjpeg_uret(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/models/<path:filename>")
def model_dosyasi(filename):
    return send_from_directory(SCRIPT_DIR, filename)


@app.route("/set_volume", methods=["POST"])
def ses_ayarla():
    try:
        data = request.get_json(force=True)
        volume = max(0, min(100, int(data.get("volume", 50))))
        subprocess.run(["amixer", "sset", "Master", f"{volume}%"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return jsonify({"success": True, "volume": volume})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/process_text", methods=["POST"])
def metin_isle():
    """
    Tarayicidan gelen METIN'i isler.
    STT tarayicida yapilir, buraya sadece string gelir.
    Akis: metin -> LLM -> TTS (hoparlorden seslendir) -> JSON yanit
    """
    data = request.get_json(force=True)
    metin = data.get("text", "").strip()
    if not metin:
        return jsonify({"success": False, "error": "Giris metni bos."}), 400

    print(f"[GIRIS] {metin}")
    ai_cevabi = gemini_sor(metin)
    print(f"[YANIT] {ai_cevabi}")
    seslendir(ai_cevabi)

    sohbet_gecmisi.append({"rol": "user", "metin": metin})
    sohbet_gecmisi.append({"rol": "mate", "metin": ai_cevabi})

    return jsonify({"success": True, "user_text": metin, "ai_text": ai_cevabi})


@app.route("/send_command", methods=["POST"])
def komut_al():
    global _son_komut
    data = request.get_json(force=True)
    _son_komut = {
        "command": data.get("command", "BEKLE"),
        "gesture": data.get("gesture", "---"),
        "emotion": data.get("emotion", "Notr"),
        "target":  data.get("target"),
    }
    return jsonify({"success": True})


@app.route("/robot_status")
def robot_durumu():
    with _cam_lock:
        active = _cam_active
    return jsonify({**_son_komut, "camera_active": active})


@app.route("/chat_history")
def sohbet_tarihcesi():
    return jsonify({"success": True, "history": sohbet_gecmisi})


@app.route("/clear_history", methods=["POST"])
def gecmisi_temizle():
    sohbet_gecmisi.clear()
    return jsonify({"success": True})


# ==========================================================================
#  BASLAT
# ==========================================================================

def _temizlik():
    _shutdown.set()

atexit.register(_temizlik)

if __name__ == "__main__":
    mp_path = os.path.join(SCRIPT_DIR, "static", "mediapipe", "vision_bundle.mjs")
    if not os.path.exists(mp_path):
        print("[UYARI] MediaPipe JS bulunamadi. Calistirin: python setup_mediapipe.py")

    print("=" * 58)
    print("  MATE — Endustriyel Kontrol Paneli")
    print("=" * 58)
    print(f"  LLM            : {GEMINI_MODEL}")
    print(f"  Kamera Kaynagi : {CAMERA_SOURCE}")
    print(f"  OpenCV         : {'Yuklu' if CV2_OK else 'Yuklu degil'}")
    print(f"  Adres          : http://0.0.0.0:5000")
    print("-" * 58)
    print("  Pi Gorevleri   : MJPEG akis, LLM, TTS")
    print("  Tarayici       : MediaPipe, STT, Arayuz")
    print("=" * 58)

    if CV2_OK:
        cam_t = threading.Thread(target=_kamera_dongusu, daemon=True, name="kamera")
        cam_t.start()
    else:
        print("[KAMERA] opencv-python-headless yuklu degil, video akisi devre disi.")

    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
