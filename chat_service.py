import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.patient import Patient
# from app.models.prescription import MPrescription  <-- تأكد من استيراد موديل الروشيتات
import google.generativeai as genai

# إعداد Gemini
# (يفضل وضع API KEY في ملف .env)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") 
genai.configure(api_key=GOOGLE_API_KEY)

chat_bp = Blueprint('chat', __name__)

def get_patient_context(patient_id):
    """
    هذه الدالة تجمع كل ما نعرفه عن المريض في نص واحد
    """
    patient = Patient.query.get(patient_id)
    if not patient:
        return None

    # 1. البيانات الأساسية
    context = f"Profile: Patient Name is {patient.name}, Age: {patient.age}, Condition: {patient.condition}.\n"
    
    # 2. الأدوية (نفترض وجود علاقة prescriptions)
    # if patient.prescriptions:
    #     meds = ", ".join([p.medicine_name for p in patient.prescriptions])
    #     context += f"Current Medications: {meds}.\n"
    
    # 3. جدول المواعيد
    if patient.medicine_schedule:
        context += f"Medicine Schedule: {patient.medicine_schedule}.\n"

    return context

@chat_bp.route('/ask', methods=['POST'])
@jwt_required()
def ask_bot():
    """
    نقطة النهاية التي سيكلمها الموبايل
    """
    # 1. تحديد المريض من التوكن (أمان 100%)
    current_user_id = get_jwt_identity()
    
    # 2. استقبال السؤال
    data = request.get_json()
    user_question = data.get('message', '')
    
    if not user_question:
        return jsonify({"error": "Message is empty"}), 400

    # 3. جلب سياق المريض (بياناته الخاصة فقط)
    context_data = get_patient_context(current_user_id)
    
    if not context_data:
        return jsonify({"error": "Patient data not found"}), 404

    # 4. تكوين البرومبت (Prompt Engineering)
    system_instruction = f"""
    You are a helpful medical assistant for a patient with Alzheimer's.
    Here is the patient's medical data:
    {context_data}
    
    Instructions:
    - Answer the user's question based ONLY on the data above.
    - Be gentle, clear, and concise.
    - If the user asks something not in the data, say you don't know.
    - Do NOT reveal that you are an AI reading a JSON file.
    """

    # 5. إرسال الطلب لـ Gemini
    try:
        model = genai.GenerativeModel('gemini-pro')
        chat = model.start_chat(history=[])
        
        # دمج التعليمات مع السؤال
        full_prompt = f"{system_instruction}\n\nUser Question: {user_question}"
        
        response = chat.send_message(full_prompt)
        
        return jsonify({
            "reply": response.text,
            "user": current_user_id
        }), 200

    except Exception as e:
        return jsonify({"error": f"AI Error: {str(e)}"}), 500
