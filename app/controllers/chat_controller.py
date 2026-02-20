# --- 1. إصلاح مشكلة SQLite (ضروري جداً لمكتبة ChromaDB) ---
try:
    __import__('pysqlite3')
    import sys
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass
# -----------------------------------------------------------

import os
import uuid
from datetime import datetime
from flask import request, send_file
import google.generativeai as genai
from app.models.patient import Patient
import speech_recognition as sr
from gtts import gTTS
from pydub import AudioSegment

import chromadb
from sentence_transformers import SentenceTransformer
from app.utils.error_handler import handle_errors, AppError, ValidationError
from app.utils.response import success_response


DB_PATH = "/home/ubuntu/mobile/authentication/vector_db"

try:
    if not os.path.exists(DB_PATH):
        os.makedirs(DB_PATH, exist_ok=True)

    chroma_client = chromadb.PersistentClient(path=DB_PATH)
    collection = chroma_client.get_or_create_collection("patients")

    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    print("[OK] Vector DB & Model Loaded Successfully")

except Exception as e:
    print(f"[ERROR] Critical Warning: Vector DB could not load: {e}")
    chroma_client = None
    collection = None
    embedding_model = None


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)

try:
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception:
    model = genai.GenerativeModel('gemini-1.5-flash')

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


def embed_text(text: str):
    if not embedding_model:
        return []
    return embedding_model.encode(text).tolist()


def store_patient_vector(patient_id: str, text: str):
    if not collection or not embedding_model:
        return
    try:
        vector = embed_text(text)
        collection.upsert(
            ids=[str(patient_id)],
            embeddings=[vector],
            documents=[text],
            metadatas=[{"patient_id": str(patient_id)}]
        )
    except Exception as e:
        print(f"Store Vector Error: {e}")


def search_patient_vectors(patient_id: str, query: str, k: int = 3):
    if not collection or not embedding_model:
        return "Memory system inactive."
    try:
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
    except Exception as e:
        print(f"Search Vector Error: {e}")
        return "Error retrieving memory."


def get_patient_context(patient_id):
    patient = Patient.query.filter_by(patient_id=patient_id).first()

    if not patient:
        return None

    info = (
        f"=== PERSONAL INFO ===\n"
        f"Name: {patient.name}\n"
        f"Age: {patient.age}\n"
        f"Gender: {getattr(patient, 'gender', 'Not specified')}\n"
        f"Condition: {getattr(patient, 'condition', 'Alzheimer')}\n"
    )

    doctor_name = "Not Assigned"
    doctor_phone = "N/A"
    if hasattr(patient, 'doctor') and patient.doctor:
        doctor_name = patient.doctor.name
        doctor_phone = getattr(patient.doctor, 'phone', 'N/A')

    caregiver_name = getattr(patient, 'caregiver_name', 'Not Assigned')
    emergency_phone = getattr(patient, 'emergency_phone', 'N/A')

    info += (
        f"\n=== CONTACTS ===\n"
        f"Treating Doctor: {doctor_name} (Phone: {doctor_phone})\n"
        f"Caregiver/Emergency: {caregiver_name} (Phone: {emergency_phone})\n"
    )

    if patient.prescriptions:
        info += "\n=== MEDICATION SCHEDULE ===\n"
        for presc in patient.prescriptions:
            med_name = "Unknown"
            if hasattr(presc, 'medicine') and presc.medicine:
                med_name = presc.medicine.name
            elif hasattr(presc, 'medicine_name'):
                med_name = presc.medicine_name

            time_str = str(presc.schedule_time) if presc.schedule_time else "Any time"
            notes = presc.notes if presc.notes else "-"
            info += f"- Drug: {med_name} | Time: {time_str} | Note: {notes}\n"
    else:
        info += "\n=== MEDICATION SCHEDULE ===\nNo active prescriptions.\n"

    found_games = False
    game_info = "\n=== GAME SCORES (MEMORY EXERCISES) ===\n"

    if hasattr(patient, 'game_scores') and patient.game_scores:
        found_games = True
        for score in patient.game_scores:
            g_name = getattr(score, 'game_name', 'Memory Game')
            g_score = getattr(score, 'score', 0)
            game_info += f"- Game: {g_name} | Score: {g_score}\n"

    elif hasattr(patient, 'games') and patient.games:
        found_games = True
        for game in patient.games:
            g_name = getattr(game, 'name', 'Game')
            g_score = getattr(game, 'high_score', 0)
            game_info += f"- Game: {g_name} | Score: {g_score}\n"

    if not found_games:
        game_info += "No game records found yet.\n"

    info += game_info

    return info


def speech_to_text(audio_file_path):
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_file_path) as source:
            audio_data = recognizer.record(source)
            return recognizer.recognize_google(audio_data, language="ar-EG")
    except Exception:
        return None


def text_to_speech(text, output_path):
    try:
        tts = gTTS(text=text, lang='ar')
        tts.save(output_path)
        return True
    except Exception:
        return False


@handle_errors('AI Error')
def ask_text():
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        raise AppError('Access denied.', status_code=403)

    patient_id = payload.get('sub')
    data = request.get_json() or {}
    question = data.get('message')
    if not question:
        raise ValidationError('Message required')

    patient_context = get_patient_context(patient_id) or "No structured data."
    store_patient_vector(patient_id, patient_context)
    vector_context = search_patient_vectors(patient_id, question)

    current_time = datetime.now().strftime("%Y-%m-%d %I:%M %p")

    final_context = f"""
    Current Time: {current_time}

    Structured Database Info (Doctor, Meds, Games):
    {patient_context}

    Relevant Memory (Previous Chats):
    {vector_context}
    """

    system_prompt = f"""
    You are a smart, kind, and comprehensive medical assistant for an Alzheimer's patient.

    You have full access to the patient's records below.
    Use ONLY this data. Do not hallucinate.

    {final_context}

    Instructions:
    1. **Doctor/Contact:** If asked about doctor or help, check the "CONTACTS" section.
    2. **Medicines:** If asked about meds or time, check "MEDICATION SCHEDULE". Compare with "Current Time".
    3. **Games:** If asked about performance, check "GAME SCORES".
    4. **Language:** Reply in the SAME language as the user (Arabic/English).

    User Question: "{question}"
    """

    response = model.generate_content(system_prompt, safety_settings=safety_settings)
    try:
        reply_text = response.text
    except ValueError:
        reply_text = "عذراً، لا يمكنني الإجابة لأسباب أمنية."

    return success_response(
        data={"response": reply_text, "source": "Gemini RAG + DB"},
        message='AI response generated',
        status_code=200,
    )


@handle_errors('Voice processing failed')
def ask_voice():
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        raise AppError('Access denied.', status_code=403)
    patient_id = payload.get('sub')

    if 'audio' not in request.files:
        raise ValidationError('No audio')

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
            raise ValidationError('Could not understand audio')

        patient_context = get_patient_context(patient_id) or "No data."
        store_patient_vector(patient_id, patient_context)
        vector_context = search_patient_vectors(patient_id, user_text)

        current_time = datetime.now().strftime("%I:%M %p")

        final_context = f"""
        Time: {current_time}
        DB Data: {patient_context}
        Memory: {vector_context}
        """

        system_prompt = f"""
        You are a voice assistant.
        Context: {final_context}
        User said: "{user_text}"
        Instructions:
        - If asked about Doctor, Games, or Meds, look at DB Data.
        - Reply concisely in Arabic (Egyptian dialect preferred).
        """

        response = model.generate_content(system_prompt, safety_settings=safety_settings)
        try:
            ai_text = response.text
        except ValueError:
            ai_text = "عذراً، لا يمكنني الرد حالياً."

        if text_to_speech(ai_text, output_path):
            return send_file(output_path, mimetype="audio/mpeg", as_attachment=True, download_name="reply.mp3")
        raise AppError('TTS Failed', status_code=500)

    finally:
        for path in [input_path, wav_path, output_path]:
            if os.path.exists(path):
                os.remove(path)
