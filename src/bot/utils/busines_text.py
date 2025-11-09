import yaml

with open('busines_text.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

operator_desc = data.get("operator_desc", "")
agent_desc = data.get("agent_desc", "")
operator_reject = data.get("operator_reject", "")
agent_reject = data.get("agent_reject", "")
operator_accept = data.get("operator_accept", "")
agent_accept = data.get("agent_accept", "")
agent_accept_nastavnik = data.get("agent_accept_nastavnik", "")
anketa_sent = data.get("anketa_sent", "")
cooldown_text = data.get("cooldown_text", "")
wait_text = data.get("wait_text", "")
hello_message = data.get("hello_message", "")
base_info = data.get("base_info", "")
request_info = data.get("request_info", "")
trouble = data.get("trouble", "")
help_info = data.get("help_info", "")
message_info = data.get("message_info", "")
partner_info = data.get("partner_info", "")

operator_new_anketa = data.get("operator_new_anketa", "")

operator_deny_reasons = data.get("operator_deny_reasons", [])
operator_deny_reasons_text = data.get("operator_deny_reasons_text", {})

agent_deny_reasons = data.get("agent_deny_reasons", [])
agent_deny_reasons_text = data.get("agent_deny_reasons_text", {})

del data
