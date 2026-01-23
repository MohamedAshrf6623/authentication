import os
from flask import Blueprint, request, jsonify
import google.generativeai as genai
from app.models.patient import Patient
from app.utils.jwt import jwt_required # نستخدم نفس الحماية الموجودة
from app import db

chat_bp = Blueprint('chat', __name__)

# إعداد Gemini API
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def get_patient_context(patient_id):
    """
    جلب بيانات المريض وتنسيقها كنص ليفهمه الذكاء الاصطناعي
    """
    # نفترض أن الـ ID هو patient_id
    patient = Patient.query.filter_by(patient_id=patient_id).first()
    
    if not patient:
        return None
    
    # تجميع البيانات (يمكنك زيادة الحقول هنا حسب الموديل الخاص بك)
    info = (
        f"Patient Name: {patient.name}\n"
        f"Age: {patient.age}\n"
        # تأكد من أن هذه الحقول موجودة في جدول Patient الخاص بك
        f"Medical Condition: {getattr(patient, 'condition', 'Not specified')}\n"
        f"Medicine Schedule: {getattr(patient, 'medicine_schedule', 'No schedule')}\n"
    )
    return info

@chat_bp.route('/ask', methods=['POST'])
@jwt_required() # حماية الرابط (لازم توكن)
def ask_bot():
    # 1. معرفة من هو المريض (من التوكن)
    payload = getattr(request, 'current_user_payload', None)
    if not payload or payload.get('role') != 'patient':
        return jsonify({"error": "Access denied. Patients only."}), 403
    
    patient_id = payload.get('sub')
    
    # 2. استقبال السؤال
    data = request.get_json()
    question = data.get('message')
    
    if not question:
        return jsonify({"error": "Message is required"}), 400

    # 3. جلب بيانات المريض من الداتا بيز
    patient_context = get_patient_context(patient_id)
    if not patient_context:
        return jsonify({"error": "Patient profile not found"}), 404

    # 4. تجهيز الـ Prompt (التعليمات للذكاء الاصطناعي)
    system_prompt = f"""
    You are a caring medical assistant for an Alzheimer's patient.
    
    Here is the patient's profile data:
    {patient_context}
    
    The patient asks: "{question}"
    
    Instructions:
    - Answer strictly based on the provided profile data.
    - Be gentle, short, and clear.
    - If the answer is not in the data, advise them to contact their doctor or caregiver.
    """

    try:
        # 5. إرسال الطلب لـ Gemini
        model = genai.GenerativeModel('gemini-2.0-flash')  
        response = model.generate_content(system_prompt)
        
        return jsonify({
            "response": response.text,
            "source": "Gemini AI (Personalized)"
        }), 200

    except Exception as e:
        print(f"AI Error: {e}")
        return jsonify({"error": "Failed to process request"}), 500
