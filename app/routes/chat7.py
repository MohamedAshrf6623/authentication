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

# استخدام الموديل المستقر (تم إصلاح المسافة البادئة هنا)
model = genai.GenerativeModel('gemini-flash-latest')

# --- دوال مساعدة ---

def get_patient_context(patient_id):
    """
    جلب بيانات المريض + جدول أدويته (Prescriptions) من الداتا بيز
    """
    # 1. جلب المريض
    patient = Patient.query.filter_by(patient_id=patient_id).first()
    
    if not patient:
        return None
    
    # 2. تجهيز البيانات الأساسية
    info = (
        f"Patient Name: {patient.name}\n"
        f"Age: {patient.age}\n"
        f"Condition: {getattr(patient, 'condition', 'Not specified')}\n"
    )

    # 3. جلب وتنسيق قائمة الأدوية
    if patient.prescriptions:
        info += "\n--- Medication Schedule ---\n"
        for presc in patient.prescriptions:
            # التعامل مع احتمالية أن يكون الدواء مرتبط بجدول Medicines أو محفوظ كاسم نصي
            med_name = presc.medicine.name if (hasattr(presc, 'medicine') and presc.medicine) else getattr(presc, 'medicine_name', 'Unknown Medicine')
            
            # تنسيق الوقت
            time_str = str(presc.schedule_time) if presc.schedule_time else "No time specified"
            
            # الملاحظات
            notes = presc.notes if presc.notes else "No notes"
            
            info += f"- Medicine: {med_name} | Time: {time_str} | Notes: {notes}\n"
    else:
        info += "\nNo prescriptions found for this patient.\n"
        
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
    """شات نصي"""
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        return jsonify({"error": "Access denied."}), 403
    
    patient_id = payload.get('sub')
    
    data = request.get_json()
    question = data.get('message')
    if not question:
        return jsonify({"error": "Message required"}), 400

    # جلب السياق (شامل الأدوية الآن)
    patient_context = get_patient_context(patient_id)
    if not patient_context:
        patient_context = "No medical data available."

    system_prompt = f"""
    You are a helpful medical assistant for a patient.
    
    Here is the patient's medical profile and medication schedule:
    {patient_context}
    
    The patient asks: "{question}"
    
    Instructions:
    - If they ask about medicines or time, use the "Medication Schedule" provided above.
    - Answer accurately based ONLY on this data.
    - Reply in the same language as the user (Arabic preferred if asked in Arabic).
    - Keep the answer short and friendly.
    """

    try:
        response = model.generate_content(system_prompt)
        return jsonify({
            "response": response.text,
            "source": "Gemini AI"
        }), 200

    except Exception as e:
        print(f"Gemini Error: {e}")
        return jsonify({"error": "AI Error"}), 500


@chat_bp.route('/voice', methods=['POST'])
@jwt_required()
def ask_voice():
    """شات صوتي"""
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        return jsonify({"error": "Access denied."}), 403
    patient_id = payload.get('sub')

    if 'audio' not in request.files:
        return jsonify({"error": "No audio"}), 400
    
    audio_file = request.files['audio']
    unique_id = uuid.uuid4()
    input_path = f"/tmp/{unique_id}_in"
    wav_path = f"/tmp/{unique_id}.wav"
    output_path = f"/tmp/{unique_id}_out.mp3"
    
    try:
        audio_file.save(input_path)
        sound = AudioSegment.from_file(input_path)
        sound.export(wav_path, format="wav")

        user_text = speech_to_text(wav_path)
        if not user_text:
            return jsonify({"error": "Could not understand audio"}), 400
            
        print(f"User said: {user_text}")

        # جلب السياق (شامل الأدوية)
        patient_context = get_patient_context(patient_id) or "No data."
        
        system_prompt = f"""
        You are a voice medical assistant.
        Patient Data: {patient_context}
        User said: "{user_text}"
        Reply concisely in Arabic based on the data.
        """
        
        response = model.generate_content(system_prompt)
        ai_text = response.text
        
        if text_to_speech(ai_text, output_path):
            return send_file(output_path, mimetype="audio/mpeg", as_attachment=True, download_name="reply.mp3")
        else:
            return jsonify({"error": "TTS Failed"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
    finally:
        for p in [input_path, wav_path, output_path]:
            if os.path.exists(p): os.remove(p)
