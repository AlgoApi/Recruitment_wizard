from typing import Optional, List, Any
from pydantic import BaseModel
from enum import Enum

from src.bot.utils.busines_text import agent_desc, operator_desc


class FieldKind(str, Enum):
    TEXT = "text"
    NUMBER = "number"
    CHOICE = "choice"
    FILE = "file"
    BOOL = "bool"

class ValidationRule(BaseModel):
    regex: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    custom: Optional[str] = None

class Field(BaseModel):
    key: str
    label: str
    kind: FieldKind
    required: bool = True
    options: List[str] | None = None
    validator: List[Optional[ValidationRule]] | None = None
    default: Optional[Any] = None

class FormDefinition:
    def __init__(self, id: str, title: str, video: str|None, fields: List[Field], page_size: int = 5):
        self.id = id
        self.title = title
        self.video = video
        self.fields = fields
        self.page_size = page_size

    def pages(self):
        for i in range(0, len(self.fields), self.page_size):
            yield self.fields[i:i+self.page_size]

# Field(key='company', label='Компания, которую представляете', kind=FieldKind.TEXT, validator=[ValidationRule(min_length=2)]),
operator_form = FormDefinition(
    id='operator',
    title=operator_desc + "\n",
    video=None,
    fields=[
        Field(key='first_name', label='Имя', kind=FieldKind.TEXT, validator=[ValidationRule(min_length=2)]),
        Field(key='last_name', label='Фамилия', kind=FieldKind.TEXT, validator=[ValidationRule(min_length=3)]),
        Field(key='age', label='Возраст', kind=FieldKind.NUMBER, validator=[ValidationRule(min_value=18), ValidationRule(max_value=80)]),
        Field(key='eng_level', label='Знание английского языка', kind=FieldKind.TEXT),
        Field(key='cpu', label='Модель процессора ПК', kind=FieldKind.TEXT, validator=[ValidationRule(min_length=5)]),
        Field(key='gpu', label='Модель видеокарты ПК', kind=FieldKind.TEXT, validator=[ValidationRule(min_length=5)]),
        Field(key='ethernet', label='Скорость интернета (Мбит/с)', kind=FieldKind.NUMBER, validator=[ValidationRule(min_value=10)]),
        Field(key='latest_job', label='Место предыдущей работы', kind=FieldKind.TEXT),
        Field(key='phone', label='Номер Телефон (пример: 79991234321):', kind=FieldKind.TEXT, validator=[ValidationRule(custom="phone")]),
        Field(key='tg', label='Telegram (username или номер)', kind=FieldKind.TEXT),
    ],
    page_size=4
)

agent_form = FormDefinition(
    id='agent',
    title=agent_desc + "\n\n",
    video='BAACAgIAAxkBAAIHd2j2j3kw5lUdQe2_VhSvoLWk36FJAAIyjAACwl-xS6MeFIP43Em1HgQ',
    fields=[
        Field(key='first_name', label='Имя', kind=FieldKind.TEXT, validator=[ValidationRule(min_length=2)]),
        Field(key='phone', label='Номер телефона (пример: 79991234321):', kind=FieldKind.TEXT, validator=[ValidationRule(custom="phone")]),
        Field(key='birthday', label='Дата рождения (в формате ДД.ММ.ГГГГ)', kind=FieldKind.TEXT, validator=[ValidationRule(min_length=10)]),
        Field(key='tg', label='Telegram', kind=FieldKind.TEXT),
    ],
    page_size=2
)