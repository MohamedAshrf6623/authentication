import os
import io
import uuid
from flask import Blueprint, request, jsonify, send_file
import google.generativeai as genai
from app.models.patient import Patient
from app.utils.jwt import jwt_required
from app import db
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment

chat_bp = Blueprint('chat', __name__)

# --- إعداد Gemini API ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# محاولة استخدام الموديل الأحدث، والعودة للقديم إذا لم يكن متاحاً
try:
    model = genai.GenerativeModel('gemini-2.0-flash')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- دوال مساعدة ---

def get_patient_context(patient_id):
    """جلب بيانات المريض من الداتا بيز"""
    # ### التعديل الهام هنا: استخدام patient_id بدلاً من id ###
    patient = Patient.query.filter_by(patient_id=patient_id).first()
    
    if not patient:
        return None
    
    info = (
        f"Patient Name: {patient.name}\n"
        f"Age: {patient.age}\n"
        f"Condition: {getattr(patient, 'condition', 'Not specified')}\n"
        f"Medicine Schedule: {getattr(patient, 'medicine_schedule', 'No schedule')}\n"
    )
    return info

def speech_to_text(audio_file_path):
    """تحويل ملف الصوت إلى نص"""
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file_path) as source:
            audio_data = recognizer.record(source)
            # يدعم العربية (ar-EG)
            text = recognizer.recognize_google(audio_data, language="ar-EG")
            return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError:
        return None
    except Exception as e:
        print(f"STT Error: {e}")
        return None

def text_to_speech(text, output_path):
    """تحويل النص إلى ملف صوتي"""
    try:
        tts = gTTS(text=text, lang='ar') 
        tts.save(output_path)
        return True
    except Exception as e:
        print(f"TTS Error: {e}")
        return False

# ==========================================
# ===            Endpoints               ===
# ==========================================

@chat_bp.route('/ask', methods=['POST'])
@jwt_required()
def ask_text():
    """
    شات نصي: يستقبل JSON ويرد بـ JSON
    """
    # 1. التحقق من المستخدم
    payload = getattr(request, 'current_user_payload', None)
    if not payload:
        return jsonify({"error": "Unauthorized"}), 401
        
    if payload.get('role') != 'patient':
        return jsonify({"error": "Access denied. Patients only."}), 403
    
    patient_id = payload.get('sub')
    
    # 2. استلام السؤال
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400
        
    question = data.get('message')
    if not question:
        return jsonify({"error": "Message is required"}), 400

    # 3. جلب البيانات
    patient_context = get_patient_context(patient_id)
    if not patient_context:
        patient_context = "No specific medical data available for this patient."

    # 4. تجهيز البرومبت
    system_prompt = f"""
    You are a caring medical assistant for an Alzheimer's patient.
    
    Here is the patient's profile data:
    {patient_context}
    
    The patient asks: "{question}"
    
    Instructions:
    - Answer strictly based on the provided profile data if related to medication/condition.
    - Be gentle, short, and clear.
    - Reply in the same language as the user (Arabic or English).
    """

    try:
        # 5. سؤال Gemini
        response = model.generate_content(system_prompt)
        return jsonify({
            "response": response.text,
            "source": "Gemini AI"
        }), 200

    except Exception as e:
        print(f"Gemini Error: {e}")
        return jsonify({"error": "Failed to process request by AI"}), 500


@chat_bp.route('/voice', methods=['POST'])
@jwt_required()
def ask_voice():
    """
    شات صوتي: يستقبل ملف صوت ويرد بملف صوت
    """
    # 1. التحقق من المستخدم
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        return jsonify({"error": "Access denied."}), 403
    patient_id = payload.get('sub')

    # 2. استلام الملف
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    
    # مسارات الملفات المؤقتة
    unique_id = uuid.uuid4()
    input_path = f"/tmp/{unique_id}_in"
    wav_path = f"/tmp/{unique_id}.wav"
    output_path = f"/tmp/{unique_id}_out.mp3"
    
    try:
        # حفظ الملف الأصلي
        audio_file.save(input_path)
        
        # تحويل إلى WAV (لأن SpeechRecognition يفضل WAV)
        sound = AudioSegment.from_file(input_path)
        sound.export(wav_path, format="wav")

        # 3. تحويل الصوت لنص
        user_text = speech_to_text(wav_path)
        if not user_text:
            return jsonify({"error": "Sorry, I could not understand the audio."}), 400
            
        print(f"User (Voice) said: {user_text}")

        # 4. الذكاء الاصطناعي (Gemini)
        patient_context = get_patient_context(patient_id) or "No data."
        
        system_prompt = f"""
        You are a voice assistant for a patient.
        Profile: {patient_context}
        User said: "{user_text}"
        Reply concisely in Arabic (suitable for speech synthesis).
        Do not use emojis or markdown.
        """
        
        response = model.generate_content(system_prompt)
        ai_text = response.text
        
        # 5. تحويل الرد لصوت
        if text_to_speech(ai_text, output_path):
            return send_file(
                output_path,
                mimetype="audio/mpeg",
                as_attachment=True,
                download_name="reply.mp3"
            )
        else:
            return jsonify({"error": "Failed to generate voice response"}), 500

    except Exception as e:
        print(f"Voice Process Error: {e}")
        return jsonify({"error": str(e)}), 500
        
    finally:
        # تنظيف الملفات
        for p in [input_path, wav_path, output_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except:
                    pass
