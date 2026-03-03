import logging
from typing import Optional, Dict, Any, Callable
import phonenumbers
from email_validator import validate_email, EmailNotValidError
import re
from .definition import Field

logger = logging.getLogger(__name__)

ValidatorFn = Callable[[Any], tuple[bool, Optional[str]]]

class ValidatorWizard:
    _VALIDATORS: Dict[str, ValidatorFn] = {}

    def add_validator(self, validator: ValidatorFn, key: str):
        self._VALIDATORS[key] = validator

    def validate_answer(self, field: Field, value: Any) -> tuple[bool, Optional[str]]:
        if (value is None or (isinstance(value, str) and value.strip() == "")) and field.required:
            logger.info(f"field req {value}")
            return False, f"Поле '{field.label}' обязательно"

        vr_list = field.validator
        if vr_list:
            for vr in vr_list:
                if vr.min_length is not None and isinstance(value, str):
                    if len(value) < vr.min_length:
                        logger.info(f"min len check fail {value} < {vr.min_value}")
                        return False, f"Минимальная длина {vr.min_length}"
                if vr.max_length is not None and isinstance(value, str):
                    if len(value) > vr.max_length:
                        logger.info(f"max len check fail {value} < {vr.min_value}")
                        return False, f"Максимальная длина {vr.max_length}"
                if vr.min_value is not None and isinstance(value, int):
                    if value < vr.min_value:
                        logger.info(f"min value check fail {value} < {vr.min_value}")
                        return False, f"Минимальное число {vr.min_value}"
                if vr.max_value is not None and isinstance(value, int):
                    if value > vr.max_value:
                        logger.info(f"max value check fail {value} > {vr.max_value}")
                        return False, f"Максимальное число {vr.max_value}"

                if vr.custom:
                    name = vr.custom
                    if name not in self._VALIDATORS:
                        logger.info(f"Validator '{name}' is not registered")
                        return False, f"Validator '{name}' is not registered"
                    ok, info = self._VALIDATORS[name](value)
                    if not ok:
                        logger.info(f"Validator '{name}' validation failed")
                        logger.debug(f"Validator '{name}' validation failed -> {info}")
                        return False, info or "всё как будто смазано, попробуй ещё раз"
                    # нормализованное значение, иначе оригинал
                    return True, info if isinstance(info, str) else value

                if vr.regex:
                    if not isinstance(value, str) or not re.match(vr.regex, value):
                        logger.info(f"Value does not match pattern {value}")
                        logger.debug(f"Value does not match pattern {value} !~ {vr.regex}")
                        return False, "Value does not match pattern"
        logger.info(f"Validator passed")
        logger.debug(f"Validator passed - {value}")
        return True, value

def phone_validator(value: str) -> tuple[bool, Optional[str]]:
    if value == "79991234321" or value == "+79991234321":
        return False, "Пример не подходит. Если боитесь давать свой личный номер телефона, оформите eSIM или виртуальный номер — он нужен только для внесения записи в CRM. Личные данные не требуются"
    if not isinstance(value, str) or value.strip() == "":
        logger.info(f"Phone number check fail")
        return False, "номер телефона не должен быть пустым"
    try:
        pn = phonenumbers.parse(value, "RU")
        if not phonenumbers.is_valid_number(pn):
            logger.info(f"Phone number check fail")
            return False, "неверно набран номер телефона"
        # Нормализованный формат E.164:
        normalized = phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
        logger.info(f"Phone number check passed")
        return True, normalized
    except phonenumbers.NumberParseException as e:
        logger.info(f"Phone number check fail")
        return False, f"это не похоже на номер телефона"

def email_validator(value: str):
    try:
        info = validate_email(value)
        logger.info(f"Phone number check passed")
        return True, info["email"]
    except EmailNotValidError:
        logger.info(f"Phone number check fail")
        return False, "неверно набрана электронная почта"

