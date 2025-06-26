import json
import logging
import re
# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def generate_template_curl(template, recipient_wa_id, phone_id, access_token, custom_parameters=None):
    """
    Generate a curl command to send a WhatsApp template message.

    Args:
        template (dict): Template data from WhatsApp API (e.g., nps_zenoti_one, welcome_msg).
        recipient_wa_id (str): Recipient's WhatsApp ID (e.g., '+916304742913').
        phone_id (str): WhatsApp Business API phone ID.
        access_token (str): Bearer token for authentication.
        custom_parameters (dict, optional): Custom values for variables, e.g.,
            {'body': ['Rakesh'], 'buttons': ['t?t=as458fg']}.

    Returns:
        str: Curl command to send the template message.
    """
    try:
        # Extract template details
        template_name = template.get("name")
        language_code = template.get("language")
        parameter_format = template.get("parameter_format", "POSITIONAL")
        components = template.get("components", [])

        # Initialize components for the payload
        payload_components = []

        # Handle custom parameters or use example values
        body_params = []
        button_params = []
        if custom_parameters:
            body_params = (
                custom_parameters.get("body", {})
                if isinstance(custom_parameters.get("body"), dict)
                else custom_parameters.get("body", [])
            )
            button_params = custom_parameters.get("buttons", [])
        else:
            for comp in components:
                if comp["type"] == "BODY" and "example" in comp:
                    if parameter_format == "NAMED" and comp.get("example", {}).get("body_text_named_params"):
                        body_params = {
                            param["param_name"]: param["example"]
                            for param in comp["example"]["body_text_named_params"]
                        }
                    elif comp.get("example", {}).get("body_text"):
                        body_params = comp["example"]["body_text"][0]
                elif comp["type"] == "BUTTONS":
                    for button in comp.get("buttons", []):
                        if button.get("example"):
                            # For URL buttons, extract the dynamic part (e.g., 't?t=as458fg')
                            if button["type"] == "URL":
                                url = button.get("url", "")
                                example_url = button["example"][0]
                                # Extract the part after the base URL
                                base_url = url.replace("{{1}}", "")
                                if example_url.startswith(base_url):
                                    dynamic_part = example_url[len(base_url):]
                                    button_params.append(dynamic_part)
                                else:
                                    button_params.append(example_url)

        # Process components
        body_variable_count = 0
        for comp in components:
            comp_type = comp["type"].upper()
            if comp_type == "BODY":
                # Count variables in body text to validate parameters
                body_text = comp.get("text", "")
                if parameter_format == "NAMED":
                    placeholders = re.findall(r"{{(\w+)}}", body_text)
                    body_variable_count = len(placeholders)
                    if body_params and isinstance(body_params, dict):
                        params = [body_params.get(ph, "") for ph in placeholders]
                    else:
                        params = []
                else:  # POSITIONAL
                    placeholders = re.findall(r"{{\d+}}", body_text)
                    body_variable_count = len(placeholders)
                    params = body_params[:body_variable_count] if body_params else []

                if params:
                    payload_components.append({
                        "type": "body",
                        "parameters": [{"type": "text", "text": str(param)} for param in params]
                    })
                elif body_variable_count > 0:
                    logger.warning(f"Missing {body_variable_count} body parameters for template {template_name}")

            elif comp_type == "HEADER":
                if comp.get("format") == "TEXT" and comp.get("text"):
                    # Handle text header with one variable
                    header_text = comp.get("text", "")
                    placeholders = re.findall(r"{{\d+}}", header_text)
                    if placeholders and body_params:
                        payload_components.append({
                            "type": "header",
                            "parameters": [{"type": "text", "text": str(body_params[0])}]
                        })
                elif comp.get("format") in ["IMAGE", "VIDEO", "DOCUMENT"]:
                    # Handle media headers
                    header_handle = comp.get("example", {}).get("header_handle", [None])[0]
                    if header_handle:
                        media_type = comp["format"].lower()
                        payload_components.append({
                            "type": "header",
                            "parameters": [{"type": media_type, media_type: {"link": header_handle}}]
                        })

            elif comp_type == "BUTTONS":
                buttons = comp.get("buttons", [])
                param_idx = 0
                for index, button in enumerate(buttons):
                    if button["type"] == "URL" and "{{1}}" in button.get("url", ""):
                        if param_idx < len(button_params):
                            payload_components.append({
                                "type": "button",
                                "sub_type": "url",
                                "index": index,
                                "parameters": [
                                    {
                                        "type": "text",
                                        "text": button_params[param_idx]
                                    }
                                ]
                            })
                            param_idx += 1
                    # Skip QUICK_REPLY buttons as they don't need parameters

        # Construct the payload
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient_wa_id,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": payload_components
            }
        }

        # Generate curl command
        curl_command = (
            f"curl --location 'https://graph.facebook.com/v23.0/{phone_id}/messages' \\\n"
            f"--header 'Authorization: Bearer {access_token}' \\\n"
            f"--header 'Content-Type: application/json' \\\n"
            f"--data '{json.dumps(payload, indent=2)}'"
        )

        return curl_command

    except Exception as e:
        logger.error(f"Error generating curl for template {template.get('name', 'unknown')}: {e}")
        return None


# Example usage
if __name__ == "__main__":
    # Example template (nps_temp1)
    template = {
            "name": "welcome_msg",
            "previous_category": "UTILITY",
            "parameter_format": "NAMED",
            "components": [
                {
                    "type": "HEADER",
                    "format": "IMAGE",
                    "example": {
                        "header_handle": [
                            "https://scontent.whatsapp.net/v/t61.29466-34/506841557_711768841552344_4400215025584897919_n.png?ccb=1-7&_nc_sid=8b1bef&_nc_ohc=OUgTiLQOC0cQ7kNvwF6UGEc&_nc_oc=AdkpMWq35te-rF1-I05gpEi09mHmsnenzo4Eqhx0UO7eK2A8LENLyszkH1UzsLTDf0I&_nc_zt=3&_nc_ht=scontent.whatsapp.net&edm=AH51TzQEAAAA&_nc_gid=P_-0pK9Jzf7j3ca61KRWDA&oh=01_Q5Aa1wE-R5wFIzCH2i9vJuc5B1gWQyvHjo9u6hg0ASaVcFVbZQ&oe=68838DAC"
                        ]
                    }
                },
                {
                    "type": "BODY",
                    "text": "Hi {{customer_name}},  \nWelcome to * Oliva Skin & Hair Clinic*\n\nWe’re thrilled to be a part of your skin & hair journey. Feel free to :",
                    "example": {
                        "body_text_named_params": [
                            {
                                "param_name": "customer_name",
                                "example": "Rakesh"
                            }
                        ]
                    }
                },
                {
                    "type": "BUTTONS",
                    "buttons": [
                        {
                            "type": "QUICK_REPLY",
                            "text": "Book Appointment"
                        },
                        {
                            "type": "QUICK_REPLY",
                            "text": "Buy Products"
                        }
                    ]
                }
            ],
            "language": "en",
            "status": "APPROVED",
            "category": "MARKETING",
            "sub_category": "CUSTOM",
            "id": "711768838219011"
        }

    recipient_wa_id = "+916304742913"
    phone_id = "367633743092037"
    access_token = "EAAcbHJk0x70BOyGSMrMulAHKz9ZCtr0i8iOKbOgjp24Kvg4ZCZAzSeogfhH5iUhloDNpAjydOo7Ca4yOQzL23igIM3y898jOO9fN6L0iuCacW2tL53zSocr6KvTxfscej6ZABzBtRExE6PnNvCisIS8ZAiRveZAXhivoJ4hRKegHNMSBQZBjBVf70WqJ8etDZC2bOAZDZD"

    curl_cmd = generate_template_curl(template, recipient_wa_id, phone_id, access_token)
    if curl_cmd:
        print(curl_cmd)