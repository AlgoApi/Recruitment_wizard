from typing import Optional, Dict, Any, Callable
import phonenumbers
from email_validator import validate_email, EmailNotValidError
import re
from .definition import Field

ValidatorFn = Callable[[Any], tuple[bool, Optional[str]]]

class ValidatorWizard:
    _VALIDATORS: Dict[str, ValidatorFn] = {}

    def add_validator(self, validator: ValidatorFn, key: str):
        self._VALIDATORS[key] = validator

    def validate_answer(self, field: Field, value: Any) -> tuple[bool, Optional[str]]:
        if (value is None or (isinstance(value, str) and value.strip() == "")) and field.required:
            return False, f"Поле '{field.label}' обязательно"

        vr_list = field.validator
        if vr_list:
            for vr in vr_list:
                if vr.min_length is not None and isinstance(value, str):
                    if len(value) < vr.min_length:
                        return False, f"Минимальная длина {vr.min_length}"
                if vr.max_length is not None and isinstance(value, str):
                    if len(value) > vr.max_length:
                        return False, f"Максимальная длина {vr.max_length}"
                if vr.min_value is not None and isinstance(value, int):
                    if value < vr.min_value:
                        return False, f"Минимальное число {vr.min_value}"
                if vr.max_value is not None and isinstance(value, int):
                    if value > vr.max_value:
                        return False, f"Максимальное число {vr.max_value}"

                if vr.custom:
                    name = vr.custom
                    if name not in self._VALIDATORS:
                        return False, f"Validator '{name}' is not registered"
                    ok, info = self._VALIDATORS[name](value)
                    if not ok:
                        return False, info or "Validation failed"
                    # нормализованное значение, иначе оригинал
                    return True, info if isinstance(info, str) else value

                if vr.regex:
                    if not isinstance(value, str) or not re.match(vr.regex, value):
                        return False, "Value does not match pattern"

        return True, value

def phone_validator(value: str) -> tuple[bool, Optional[str]]:
    if not isinstance(value, str) or value.strip() == "":
        return False, "Номер телефона не должен быть пустым"
    try:
        pn = phonenumbers.parse(value, "RU")
        if not phonenumbers.is_valid_number(pn):
            return False, "Неверно набран номер телефона"
        # Нормализованный формат E.164:
        normalized = phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
        return True, normalized
    except phonenumbers.NumberParseException as e:
        return False, f"Phone parse error: {e}"

def email_validator(value: str):
    try:
        info = validate_email(value)
        return True, info["email"]
    except EmailNotValidError:
        return False, "Неверно набрана электронная почта"

