import boto3
import os

def get_sns_client():
    """تهيئة عميل AWS SNS باستخدام الإعدادات من ملف .env"""
    return boto3.client(
        'sns',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_REGION', 'us-east-1')
    )

def register_device_to_sns(fcm_token: str):
    """إنشاء نقطة اتصال (Endpoint) في AWS SNS للموبايل"""
    try:
        client = get_sns_client()
        app_arn = os.getenv('SNS_PLATFORM_APPLICATION_ARN')
        if not app_arn:
            print("[SNS ERROR] Platform Application ARN not set in .env")
            return None

        response = client.create_platform_endpoint(
            PlatformApplicationArn=app_arn,
            Token=fcm_token
        )
        return response['EndpointArn']
    except Exception as e:
        print(f"[SNS ERROR] Failed to register device: {e}")
        return None

def send_push_notification(endpoint_arn: str, title: str, message: str):
    """إرسال إشعار للموبايل باستخدام الـ Endpoint ARN"""
    try:
        client = get_sns_client()
        client.publish(
            TargetArn=endpoint_arn,
            Message=message,
            Subject=title
        )
        return True
    except Exception as e:
        print(f"[SNS ERROR] Failed to send notification: {e}")
        return False
