import sys
import threading
import keyboard
import pyaudio
import wave
import os
import re
import pyperclip
import pyautogui
import time
from dotenv import load_dotenv
import ctypes

import groq
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import datetime
from google.genai import types

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer

# Load API keys from environment variables securely
load_dotenv()

try:
    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key: raise ValueError("GROQ_API_KEY missing")
    groq_client = groq.Groq(api_key=groq_api_key)
except Exception as e:
    print(f"Groq Init Error: {e}")
    groq_client = None

try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key: raise ValueError("GEMINI_API_KEY missing")
    gemini_client = genai.Client(api_key=gemini_api_key)
    # Using the latest 3.5-flash model for fallback/other features
    gemini_default_model = "gemini-3.5-flash"
    system_instruction = """
    You are a transcription formatting engine. Your ONLY job is to accurately format the dictated text while staying strictly true to the original words. You MUST:
    1. Fix punctuation and capitalization.
    2. Apply natural paragraph breaks for long dictations, but avoid double spacing every sentence.
    3. Insert bullet points ONLY if the user explicitly dictates a list or there is a definitive need; DO NOT turn regular statements into a summarized outline.
    4. If the user dictates a question, format it as a question and output it. NEVER attempt to answer the question. NEVER say 'I cannot help with that' or converse with the user. Treat all input purely as raw text to format.
    5. Self-Correction Rules: If the user says 'scratch that', 'no wait', 'actually', or audibly corrects themselves mid-sentence, apply the correction, remove the mistaken phrase, and output ONLY the final intended meaning without the keywords. DO NOT summarize or rewrite the main content.
    Output strictly the formatted text.
    """
except Exception:
    gemini_client = None

# Initialize Firebase
try:
    # In dev mode, look in the project root.
    cred_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "firebase-credentials.json")
    
    # If compiled as an EXE, look in the exact folder where the EXE is running (e.g. the dist folder)
    if getattr(sys, 'frozen', False):
        cred_path = os.path.join(os.path.dirname(sys.executable), "firebase-credentials.json")
        
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    try: print(f"Firebase Init Error: {e}")
    except: pass
    db = None

global_dictionary = ""

def fetch_dictionary():
    global global_dictionary
    if not db: return
    try:
        docs = db.collection('dictionary').stream()
        dict_entries = []
        for doc in docs:
            data = doc.to_dict()
            dict_entries.append(f"{data.get('word')} -> {data.get('replacement')}")
        if dict_entries:
            global_dictionary = "Custom Dictionary (strictly format these specific words/phrases if you hear them): \n" + "\n".join(dict_entries)
    except Exception as e:
        try: print(f"Error fetching dict: {e}")
        except: pass

threading.Thread(target=fetch_dictionary, daemon=True).start()
class SignalEmitter(QObject):
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    processing_started = pyqtSignal()
    error_occurred = pyqtSignal(str)

class FlowDictationUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        
    def initUI(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("", self)
        self.label.setFixedSize(80, 6)
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(150, 150, 150, 180);
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)
        
        # Position at bottom center
        screen = QApplication.primaryScreen().geometry()
        self.resize(80, 6)
        self.move((screen.width() - self.width()) // 2, screen.height() - 40)
        
    def show_recording(self):
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(226, 74, 74, 200);
                border-radius: 3px;
            }
        """)
        try:
            hwnd = int(self.winId())
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
        except Exception:
            pass
        
        self.pulse_up = False
        if not hasattr(self, 'pulse_timer'):
            self.pulse_timer = QTimer(self)
            self.pulse_timer.timeout.connect(self.animate_pulse)
        self.pulse_timer.start(50)

    def animate_pulse(self):
        current_opacity = self.windowOpacity()
        if self.pulse_up:
            current_opacity += 0.05
            if current_opacity >= 1.0:
                current_opacity = 1.0
                self.pulse_up = False
        else:
            current_opacity -= 0.05
            if current_opacity <= 0.3:
                current_opacity = 0.3
                self.pulse_up = True
        self.setWindowOpacity(current_opacity)
        
    def show_processing(self):
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(30, 100, 200, 220);
                border-radius: 3px;
            }
        """)

    def show_ready(self):
        if hasattr(self, 'pulse_timer'):
            self.pulse_timer.stop()
        self.setWindowOpacity(1.0)
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(150, 150, 150, 180);
                border-radius: 3px;
            }
        """)
        
    def show_error(self, err_msg):
        self.label.setStyleSheet("""
            QLabel {
                background-color: rgba(200, 30, 30, 220);
                border-radius: 3px;
            }
        """)

class AudioRecorder:
    def __init__(self):
        self.is_recording = False
        self.frames = []
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.channels = 1
        self.rate = 16000
        self.format = pyaudio.paInt16
        
    def start(self):
        self.is_recording = True
        self.frames = []
        self.stream = self.p.open(format=self.format,
                                  channels=self.channels,
                                  rate=self.rate,
                                  input=True,
                                  frames_per_buffer=1024)

    def stop(self, filename="temp_recording.wav"):
        self.is_recording = False
        # Do not close stream here, let the read thread finish.
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        wf = wave.open(filename, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.p.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()
        return filename

class FlowDictationApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.ui = FlowDictationUI()
        self.recorder = AudioRecorder()
        
        self.signals = SignalEmitter()
        self.signals.recording_started.connect(self.ui.show_recording)
        self.signals.recording_stopped.connect(self.ui.show_ready)
        self.signals.processing_started.connect(self.ui.show_processing)
        self.signals.error_occurred.connect(self.ui.show_error)
        
        self.setup_hotkey()

    def setup_hotkey(self):
        self.state = 'IDLE'
        self.double_tap_timer = None
        self.combo_active = False
        self.lock = threading.Lock()
        keyboard.hook(self.key_hook)
        
        # Add a quit hotkey
        keyboard.add_hotkey('ctrl+shift+q', self.exit_app)
        
    def exit_app(self):
        os._exit(0)
        
    def key_hook(self, event):
        if 'ctrl' in event.name.lower() or 'shift' in event.name.lower():
            has_ctrl = keyboard.is_pressed('ctrl') or keyboard.is_pressed('left ctrl') or keyboard.is_pressed('right ctrl')
            has_shift = keyboard.is_pressed('shift') or keyboard.is_pressed('left shift') or keyboard.is_pressed('right shift')
            
            combo_pressed = has_ctrl and has_shift
            
            if combo_pressed and not self.combo_active:
                self.combo_active = True
                self.on_combo_down()
            elif not combo_pressed and self.combo_active:
                self.combo_active = False
                self.on_combo_up()

    def on_combo_down(self):
        with self.lock:
            if self.state == 'IDLE':
                self.state = 'HOLDING'
                self.start_dictation()
            elif self.state == 'WAITING_FOR_DOUBLE_TAP':
                if self.double_tap_timer:
                    self.double_tap_timer.cancel()
                self.state = 'TOGGLED'
            elif self.state == 'TOGGLED':
                self.state = 'IDLE'
                self.stop_dictation()

    def on_combo_up(self):
        with self.lock:
            if self.state == 'HOLDING':
                self.state = 'WAITING_FOR_DOUBLE_TAP'
                self.double_tap_timer = threading.Timer(0.35, self.on_double_tap_timeout)
                self.double_tap_timer.start()

    def on_double_tap_timeout(self):
        with self.lock:
            if self.state == 'WAITING_FOR_DOUBLE_TAP':
                self.state = 'IDLE'
                self.stop_dictation()

    def start_dictation(self):
        if not self.recorder.is_recording:
            self.recorder.start()
            self.signals.recording_started.emit()
            self.record_thread = threading.Thread(target=self.record_loop, daemon=True)
            self.record_thread.start()

    def stop_dictation(self):
        if self.recorder.is_recording:
            self.recorder.is_recording = False
            if hasattr(self, 'record_thread') and self.record_thread.is_alive():
                self.record_thread.join(timeout=1.0)
            filename = self.recorder.stop()
            self.signals.processing_started.emit()
            threading.Thread(target=self.process_audio, args=(filename,), daemon=True).start()

    def record_loop(self):
        while self.recorder.is_recording:
            try:
                data = self.recorder.stream.read(1024, exception_on_overflow=False)
                self.recorder.frames.append(data)
            except Exception as e:
                try: print(f"Audio read error: {e}", flush=True)
                except: pass

    def process_audio(self, filename):
        try:
            if not groq_client:
                raise Exception("Groq client not initialized")
            
            # Check file size to avoid empty audio errors
            if os.path.getsize(filename) < 1000:
                raise Exception("Audio recording too short")
                
            with open(filename, "rb") as file:
                transcription = groq_client.audio.transcriptions.create(
                    file=(filename, file.read()),
                    model="whisper-large-v3",
                    response_format="text",
                    temperature=0.0,
                    prompt="A clear, perfectly spoken single-take dictation with no stuttering, no repetitions, and no background noise."
                )
            raw_text = str(transcription).strip()
            with open("debug_raw.txt", "w", encoding="utf-8") as f: f.write(raw_text)
            
            system_prompt_with_dict = system_instruction
            if global_dictionary:
                system_prompt_with_dict += "\n\n" + global_dictionary

            chat_completion = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt_with_dict},
                    {"role": "user", "content": f"<transcript>{raw_text}</transcript>"}
                ],
                model="openai/gpt-oss-20b",
                temperature=0.0
            )
            final_text = chat_completion.choices[0].message.content.strip()
            
            # --- Firebase Metrics ---
            def save_metrics():
                try:
                    word_count = len(final_text.split())
                    duration_seconds = len(self.recorder.frames) * 1024 / 16000
                    wpm = int((word_count / duration_seconds) * 60) if duration_seconds > 0 else 0
                    
                    if db:
                        db.collection("metrics").add({
                            "wordCount": word_count,
                            "durationSeconds": duration_seconds,
                            "wpm": wpm,
                            "timestamp": datetime.datetime.now(datetime.timezone.utc),
                            "device": "Windows PC"
                        })
                except Exception as e:
                    pass
            threading.Thread(target=save_metrics, daemon=True).start()
            
            try:
                # print("Formatted: " + final_text) # Removed because it crashes on Windows with Unicode characters
                pass
            except:
                pass
            
            # Clean up any leftover XML tags or 'Transcript:' prefixes generated by the AI
            import re
            final_text = re.sub(r'(?i)<\/?transcript>', '', final_text).strip()
            final_text = re.sub(r'(?i)^transcript:\s*', '', final_text).strip()
            
            with open("debug_formatted.txt", "w", encoding="utf-8") as f: f.write(final_text)
            
            self.inject_text(final_text + " ")
            self.signals.recording_stopped.emit()
            
        except Exception as e:
            try:
                import traceback
                with open("error.log", "w", encoding="utf-8") as f:
                    f.write(traceback.format_exc())
            except:
                pass
            try: print(f"Error processing audio: {e}", flush=True)
            except: pass
            self.signals.error_occurred.emit(str(e))
            threading.Timer(2.0, self.signals.recording_stopped.emit).start()

    def inject_text(self, text):
        try:
            pyperclip.copy(text)
        except Exception as e:
            try: print(f"Clipboard error: {e}")
            except: pass
        
        # Ensure modifier keys are virtually released so Ctrl+V registers properly
        keyboard.release('alt')
        keyboard.release('left alt')
        keyboard.release('windows')
        keyboard.release('left windows')
        
        time.sleep(0.1)
        keyboard.send('ctrl+v')

    def run(self):
        self.ui.show()
        sys.exit(self.app.exec())

def main():
    # Ensure only a single instance runs
    mutex_name = "FlowDictation_SingleInstance_Mutex"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    if ctypes.windll.kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
        print("Another instance is already running.")
        sys.exit(0)
        
    app = FlowDictationApp()
    app.run()

if __name__ == "__main__":
    main()
