# --- 1. SQLite compatibility fix (required for ChromaDB) ---
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
from pydub import AudioSegment

import chromadb
from sentence_transformers import SentenceTransformer
from app.utils.error_handler import handle_errors, AppError, ValidationError
from app.utils.response import success_response
from app.utils.validation import validate_payload, ChatAskPayload

# --- New Imports for Local STT & XTTS ---
import torch
import torchaudio
from transformers import pipeline
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
# ---------------------------------------

# ==========================================
# ===   Load ML Models (Global Scope)    ===
# ==========================================
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"[INFO] Using device: {device}")

# 1. Load Whisper Fine-Tuned (STT) - Local Model
WHISPER_MODEL_DIR = "openai/whisper-small"
try:
    stt_pipe = pipeline("automatic-speech-recognition", model=WHISPER_MODEL_DIR, device=device)
    print("[OK] Local Whisper STT Loaded Successfully")
except Exception as e:
    print(f"[ERROR] Local Whisper STT could not load: {e}")
    stt_pipe = None

# 2. Load Egyptian TTS (Local XTTS v2)
TTS_BASE_MODEL_DIR = "/home/ubuntu/mobile/authentication/app/controllers/chat_model"
CONFIG_PATH = os.path.join(TTS_BASE_MODEL_DIR, "config.json")
VOCAB_PATH = os.path.join(TTS_BASE_MODEL_DIR, "vocab.json")
SPEAKER_AUDIO_PATH = os.path.join(TTS_BASE_MODEL_DIR, "speaker_reference.wav")

try:
    print("[INFO] Loading EGTTS (XTTS) Config...")
    config = XttsConfig()
    config.load_json(CONFIG_PATH)
    tts_model = Xtts.init_from_config(config)
    tts_model.load_checkpoint(config, checkpoint_dir=TTS_BASE_MODEL_DIR, use_deepspeed=False, vocab_path=VOCAB_PATH)
    tts_model.to(device)

    print("[INFO] Computing speaker latents...")
    gpt_cond_latent, speaker_embedding = tts_model.get_conditioning_latents(audio_path=[SPEAKER_AUDIO_PATH])
    print("[OK] Local EGTTS Loaded Successfully via XTTS")
except Exception as e:
    print(f"[ERROR] Local EGTTS could not load: {e}")
    tts_model = None
    gpt_cond_latent = None
    speaker_embedding = None

# --- Vector DB Initialization ---
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

# --- Gemini API Configuration ---
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

# ==========================================
# ===         Memory Functions (RAG)     ===
# ==========================================
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

# ==========================================
# ===       Data Retrieval Function      ===
# ==========================================
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

    care_name = "Not Assigned"
    care_phone = "N/A"
    care_rel = "Caregiver"
    if hasattr(patient, 'care_giver') and patient.care_giver:
        care_name = patient.care_giver.name
        care_phone = getattr(patient.care_giver, 'phone', 'N/A')
        care_rel = getattr(patient.care_giver, 'relation', 'Relative')

    info += (
        f"\n=== MEDICAL TEAM (CONTACTS) ===\n"
        f"Treating Doctor: {doctor_name} (Phone: {doctor_phone})\n"
        f"Caregiver/Emergency: {care_name} ({care_rel}, Phone: {care_phone})\n"
    )

    if patient.prescriptions:
        info += "\n=== MEDICATION SCHEDULE ===\n"
        for presc in patient.prescriptions:
            med_name = getattr(presc.medicine, 'name', getattr(presc, 'medicine_name', 'Unknown'))
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
            game_info += f"- Game: {getattr(score, 'game_name', 'Memory Game')} | Score: {getattr(score, 'score', 0)}\n"
    elif hasattr(patient, 'games') and patient.games:
        found_games = True
        for game in patient.games:
            game_info += f"- Game: {getattr(game, 'name', 'Game')} | Score: {getattr(game, 'high_score', 0)}\n"

    if not found_games:
        game_info += "No game records found yet.\n"

    info += game_info
    return info

# ==========================================
# ===            Audio Helpers           ===
# ==========================================
def speech_to_text(audio_file_path):
    """ Converts Speech to Text using local fine-tuned Whisper """
    if not stt_pipe:
        print("[ERROR] STT Pipeline is not initialized.")
        return None
    try:
        result = stt_pipe(audio_file_path)
        return result.get("text", "").strip()
    except Exception as e:
        print(f"[ERROR] Whisper STT processing failed: {e}")
        return None

def text_to_speech(text, output_path):
    """ Converts Text to Speech using Local XTTS Model """
    if not tts_model:
        print("[ERROR] EGTTS Model is not initialized.")
        return False
    try:
        out = tts_model.inference(
            text=text,
            language="ar",
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            temperature=0.3
        )
        # حفظ الملف الصوتي بمعدل 24000 هرتز المتوافق مع XTTS
        torchaudio.save(output_path, torch.tensor(out["wav"]).unsqueeze(0), 24000)
        return True
    except Exception as e:
        print(f"[ERROR] Local XTTS processing failed: {e}")
        return False

# ==========================================
# ===            Endpoints               ===
# ==========================================
@handle_errors('AI Error')
def ask_text():
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        raise AppError('Access denied.', status_code=403)

    patient_id = payload.get('sub')
    data = validate_payload(ChatAskPayload, request.get_json() or {})
    question = data.get('message')
    if not question:
        raise ValidationError('Message required')

    patient_context = get_patient_context(patient_id) or "No structured data."
    store_patient_vector(patient_id, patient_context)
    vector_context = search_patient_vectors(patient_id, question)

    current_time = datetime.now().strftime("%Y-%m-%d %I:%M %p")

    final_context = f"""
    Current Time: {current_time}
    Structured Database Info (Doctor, Meds, Games, Caregiver):
    {patient_context}
    Relevant Memory (Previous Chats):
    {vector_context}
    """

    system_prompt = f"""
    You are a smart, kind, and comprehensive medical assistant for an Alzheimer's patient.
    You have full access to the patient's private records below.
    Use ONLY this data to answer. Do NOT hallucinate names or relations.
    {final_context}
    Instructions:
    1. **Doctor & Caregiver:** If asked about the doctor, caregiver, or who to call, look EXCLUSIVELY at the "MEDICAL TEAM (CONTACTS)" section.
    2. **Medicines:** If asked about meds or time, check "MEDICATION SCHEDULE". Compare with "Current Time".
    3. **Games:** If asked about performance, check "GAME SCORES".
    4. **Language:** Reply concisely and warmly in the SAME language as the user (Arabic/English).

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
    output_path = f"/tmp/{unique_id}_out.wav"

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
        You are a smart voice assistant for an Alzheimer's patient.
        Context: {final_context}
        User said: "{user_text}"

        Instructions:
        - If asked about Doctor or Caregiver, look at the "MEDICAL TEAM (CONTACTS)" in DB Data.
        - If asked about Meds, check "MEDICATION SCHEDULE".
        - Do not invent information. If it's not in the Context, say you don't know.
        - Reply warmly and concisely in Arabic (Egyptian dialect preferred). Make sure the text is written in clean Arabic letters so the TTS model reads it naturally.
        """

        response = model.generate_content(system_prompt, safety_settings=safety_settings)
        try:
            ai_text = response.text
        except ValueError:
            ai_text = "عذراً، لا يمكنني الرد حالياً."

        if text_to_speech(ai_text, output_path):
            return send_file(output_path, mimetype="audio/wav", as_attachment=True, download_name="reply.wav")
        raise AppError('TTS Failed', status_code=500)

    finally:
        for path in [input_path, wav_path, output_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
