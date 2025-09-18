import re
import json

def _resolve_token(token: str, values: dict) -> str:
    """Resolve a placeholder token with optional fallbacks.

    Supports syntax: {{ name | wa_id | "Customer" | - }}
    - Tries each option from left to right
    - If option matches a key in values and is non-empty, use it
    - If option is a quoted literal (single or double quotes), use the literal if non-empty
    - If option is '-' use '-'
    Default behavior (when only a single var is provided):
      - if empty, fallback to values['wa_id'] if available, else '-'
    """
    parts = [p.strip() for p in token.split("|")]
    # If explicit fallbacks provided
    if len(parts) > 1:
        for part in parts:
            if part in values and values.get(part):
                return str(values.get(part))
            if (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
                literal = part[1:-1]
                if literal:
                    return literal
            if part == "-":
                return "-"
        # Nothing matched, final generic default
        return str(values.get("wa_id") or "-")

    # No explicit fallback, single var token
    var_name = parts[0]
    value = values.get(var_name)
    if value:
        return str(value)
    # Special-case: if name is missing/empty, default to "Client"
    if var_name == "name":
        return "Client"
    # Heuristic defaults
    if values.get("wa_id"):
        return str(values.get("wa_id"))
    return "-"


def fill_placeholders(data, values):
    if isinstance(data, dict):
        return {k: fill_placeholders(v, values) for k, v in data.items()}
    elif isinstance(data, list):
        return [fill_placeholders(item, values) for item in data]
    elif isinstance(data, str):
        # Replace placeholders like {{name}} or with fallbacks {{name | wa_id | "Customer"}}
        return re.sub(r'\{\{(.*?)\}\}', lambda m: _resolve_token(m.group(1).strip(), values), data)
    else:
        return data
def extract_placeholders(data):
    placeholders = set()

    def recurse(item):
        if isinstance(item, dict):
            for value in item.values():
                recurse(value)
        elif isinstance(item, list):
            for value in item:
                recurse(value)
        elif isinstance(item, str):
            found = re.findall(r"\{\{(.*?)\}\}", item)
            placeholders.update(var.strip() for var in found)

    recurse(data)
    return list(placeholders)

# Example Usage
template_json = {
      "name": "welcome_msg",
      "language": {
        "code": "en"
      },
      "components": [
        {
          "type": "header",
          "parameters": [
            {
              "type": "image",
              "image": {
                "link": "{{image_link}}"
              }
            }
          ]
        },
        {
          "type": "body",
          "parameters": [
            {
              "customer_name": {
                "text": "{{name}}",
                "type": "text"
              }
            }
          ]
        },
        {
          "type": "button",
          "index": 0,
          "sub_type": "quick_reply",
          "parameters": []
        },
        {
          "type": "button",
          "index": 1,
          "sub_type": "quick_reply",
          "parameters": []
        }
      ]
    }

values_json = {
      "name": "Manoj",
      "image_link": "www.github.com/spotify.png"
    }

filled_json = fill_placeholders(template_json, values_json)
if __name__ == "__main__":
    print(json.dumps(filled_json, indent=2))
    print(extract_placeholders(template_json))