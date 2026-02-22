from pydantic import BaseModel, ConfigDict, model_validator


def validate_payload(model_cls, payload: dict):
    return model_cls.model_validate(payload).model_dump()


class RegisterPatientPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    email: str
    password: str
    doctor_id: str
    care_giver_id: str
    patient_id: str | None = None
    age: int | None = None
    gender: str | None = None
    phone: str | None = None
    chronic_disease: str | None = None
    city: str | None = None
    address: str | None = None
    age_category: str | None = None
    hospital_address: str | None = None


class RegisterDoctorPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    email: str
    password: str
    doctor_id: str | None = None
    gender: str | None = None
    specialization: str | None = None
    age: int | None = None
    phone: str | None = None
    city: str | None = None
    clinic_address: str | None = None


class RegisterCaregiverPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    email: str
    password: str
    care_giver_id: str | None = None
    relation: str | None = None
    phone: str | None = None
    city: str | None = None
    address: str | None = None


class LoginPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: str | None = None
    username: str | None = None
    name: str | None = None
    password: str
    role: str | None = None

    @model_validator(mode='after')
    def check_identifier(self):
        if not (self.email or self.username or self.name):
            raise ValueError('email, username, or name is required')
        return self


class ForgetPasswordPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    email: str
    role: str | None = None


class ResetPasswordPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    token: str | None = None
    password: str
    confirm_password: str | None = None


class UpdateMyPasswordPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    password_current: str | None = None
    current_password: str | None = None
    password: str | None = None
    new_password: str | None = None
    confirm_password: str | None = None

    @model_validator(mode='after')
    def check_fields(self):
        current = self.password_current or self.current_password
        new_pwd = self.password or self.new_password
        if not current:
            raise ValueError('current_password is required')
        if not new_pwd or not self.confirm_password:
            raise ValueError('password and confirm_password are required')
        return self


class UpdateMePayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str | None = None
    email: str | None = None
    age: int | None = None
    gender: str | None = None
    phone: str | None = None
    city: str | None = None
    address: str | None = None
    hospital_address: str | None = None
    age_category: str | None = None
    specialization: str | None = None
    clinic_address: str | None = None
    relation: str | None = None


class ChatAskPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    message: str
