from ..forms.definition import FormDefinition

class FormConversation:
    def __init__(self, form_def: FormDefinition):
        self.form_def = form_def


def format_content(content: dict, form_conv: FormConversation, indent: int = 0) -> str:
    pad = " " * indent
    lines: list[str] = []
    if isinstance(content, dict):
        for k, v in content.items():
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{translate_fields(k, form_conv)}:")
                lines.append(format_content(v, indent=indent + 2, form_conv=form_conv))
            else:
                lines.append(f"{pad}{translate_fields(k, form_conv)}: {v}")
    elif isinstance(content, list):
        for i, v in enumerate(content, 1):
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}- [{i}]")
                lines.append(format_content(v, indent=indent + 2, form_conv=form_conv))
            else:
                lines.append(f"{pad}- {v}")
    else:
        lines.append(f"{pad}{content}")
    return "\n".join(lines)


def translate_fields(key:str, form_conv: FormConversation):
    fields = form_conv.form_def.fields
    for field in fields:
        if field.key == key:
            return field.label
    return key

def translate_role(txt:str) -> str:
    match txt:
        case "agent":
            return "Агента!"
        case "operator":
            return "Оператора!"
    return ""