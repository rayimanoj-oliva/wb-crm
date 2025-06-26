import re
import json

def fill_placeholders(data, values):
    if isinstance(data, dict):
        return {k: fill_placeholders(v, values) for k, v in data.items()}
    elif isinstance(data, list):
        return [fill_placeholders(item, values) for item in data]
    elif isinstance(data, str):
        # Replace placeholders like {{customer_name}}
        return re.sub(r'\{\{(.*?)\}\}', lambda m: str(values.get(m.group(1).strip(), m.group(0))), data)
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

print(json.dumps(filled_json, indent=2))
print(extract_placeholders(template_json))