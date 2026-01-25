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

# مكتبات الذاكرة الجديدة
import chromadb
from sentence_transformers import SentenceTransformer

# تصحيح الاسم هنا (__name__)
chat_bp = Blueprint('chat', __name__)

# ===== Vector DB (Chroma) Setup =====
# سيتم إنشاء مجلد جديد اسمه vector_db لحفظ الذاكرة
chroma_client = chromadb.PersistentClient(path="./vector_db")
collection = chroma_client.get_or_create_collection("patients")

# Embedding model (local & free)
# سيتم تحميل هذا الموديل مرة واحدة عند تشغيل السيرفر
try:
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
except Exception as e:
    print(f"Error loading embedding model: {e}")

# --- إعداد Gemini API ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

# استخدام الموديل المتوفر لديك
try:
    model = genai.GenerativeModel('gemini-flash-latest')
except:
    model = genai.GenerativeModel('gemini-1.5-flash')

# --- دوال مساعدة ---

def get_patient_context(patient_id):
    """
    جلب بيانات المريض + جدول أدويته (Prescriptions) من الداتا بيز
    """
    patient = Patient.query.filter_by(patient_id=patient_id).first()

    if not patient:
        return None

    info = (
        f"Patient Name: {patient.name}\n"
        f"Age: {patient.age}\n"
        f"Condition: {getattr(patient, 'condition', 'Not specified')}\n"
    )

    if patient.prescriptions:
        info += "\n--- Medication Schedule ---\n"
        for presc in patient.prescriptions:
            med_name = presc.medicine.name if (hasattr(presc, 'medicine') and presc.medicine) else getattr(presc, 'medicine_name', 'Unknown Medicine')
            time_str = str(presc.schedule_time) if presc.schedule_time else "No time specified"
            notes = presc.notes if presc.notes else "No notes"
            info += f"- Medicine: {med_name} | Time: {time_str} | Notes: {notes}\n"
    else:
        info += "\nNo prescriptions found for this patient.\n"

    return info

def embed_text(text: str):
    return embedding_model.encode(text).tolist()

def store_patient_vector(patient_id: str, text: str):
    """تخزين أو تحديث بيانات المريض في الذاكرة"""
    vector = embed_text(text)
    # نستخدم upsert بدلاً من add لتحديث البيانات لو موجودة، وإضافتها لو جديدة
    collection.upsert(
        ids=[str(patient_id)],
        embeddings=[vector],
        documents=[text],
        metadatas=[{"patient_id": str(patient_id)}]
    )

def search_patient_vectors(patient_id: str, query: str, k: int = 3):
    """البحث في الذاكرة عن معلومات ذات صلة بالسؤال"""
    query_vector = embed_text(query)
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=k,
        where={"patient_id": str(patient_id)}
    )

    if not results or not results.get("documents") or not results["documents"][0]:
        return "No relevant memory found."

    docs = results["documents"][0]
    return "\n".join(docs)

def speech_to_text(audio_file_path):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file_path) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language="ar-EG")
            return text
    except:
        return None

def text_to_speech(text, output_path):
    try:
        tts = gTTS(text=text, lang='ar')
        tts.save(output_path)
        return True
    except:
        return False

# ==========================================
# ===            Endpoints               ===
# ==========================================

@chat_bp.route('/ask', methods=['POST'])
@jwt_required()
def ask_text():
    """شات نصي مع ذاكرة Vector DB"""
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        return jsonify({"error": "Access denied."}), 403

    patient_id = payload.get('sub')
    data = request.get_json()
    question = data.get('message')
    if not question:
        return jsonify({"error": "Message required"}), 400

    # 1. جلب البيانات من SQL وتنسيقها
    patient_context = get_patient_context(patient_id) or "No structured data."

    # 2. تحديث الذاكرة (ChromaDB) بالبيانات الجديدة
    try:
        store_patient_vector(patient_id, patient_context)
    except Exception as e:
        print(f"Vector Store Error: {e}")

    # 3. البحث في الذاكرة عن إجابة للسؤال
    vector_context = search_patient_vectors(patient_id, question)

    final_context = f"""
    Structured Patient Data (SQL):
    {patient_context}

    Relevant Retrieved Memory (Vector DB):
    {vector_context}
    """

    system_prompt = f"""
    You are a calm, kind, and professional medical assistant for Alzheimer's patients.

    Follow these rules strictly:
    - Use ONLY the information inside "Structured Patient Data" and "Relevant Retrieved Memory".
    - Do NOT make up information.
    - If the answer is not found, reply: "Insufficient information to answer."
    - Detect the language of the user's question automatically.
    - Reply in the same language as the user.
    - Keep answers short, clear, and easy to understand.

    Context:
    {final_context}

    User said:
    "{question}"
    """

    try:
        response = model.generate_content(system_prompt)
        return jsonify({
            "response": response.text,
            "source": "Gemini AI + RAG"
        }), 200

    except Exception as e:
        print(f"Gemini Error: {e}")
        return jsonify({"error": "AI Error"}), 500


@chat_bp.route('/voice', methods=['POST'])
@jwt_required()
def ask_voice():
    """شات صوتي مع ذاكرة Vector DB"""
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

        # جلب وتحديث السياق
        patient_context = get_patient_context(patient_id) or "No structured data."
        try:
            store_patient_vector(patient_id, patient_context)
        except:
            pass

        vector_context = search_patient_vectors(patient_id, user_text)

        final_context = f"""
        Structured Patient Data:
        {patient_context}

        Relevant Memory:
        {vector_context}
        """

        system_prompt = f"""
        You are a medical assistant.
        Context: {final_context}
        User said: "{user_text}"
        Reply concisely in the user's language (Arabic preferred if spoken).
        """

        response = model.generate_content(system_prompt)
        ai_text = response.text

        if text_to_speech(ai_text, output_path):
            return send_file(output_path, mimetype="audio/mpeg", as_attachment=True, download_name="reply.mp3")
        else:
            return jsonify({"error": "TTS Failed"}), 500

    except Exception as e:
        print(f"Voice Error: {e}")
        return jsonify({"error": str(e)}), 500

    finally:
        for p in [input_path, wav_path, output_path]:
            if os.path.exists(p): os.remove(p)
