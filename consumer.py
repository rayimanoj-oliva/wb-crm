import pika, json, requests, asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from controllers.web_socket import manager
from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import SessionLocal
from services import customer_service, message_service
from services.whatsapp_service import get_latest_token
from schemas.MessageSchema import MessageCreate


def callback(ch, method, properties, body):
    db: Session = SessionLocal()

    try:
        task = json.loads(body)
        print("📨 Task received:", task)

        template_name = task.get("template_name")
        wa_id = task.get("to")
        parameters = task.get("parameters")

        if not (template_name and wa_id and parameters):
            raise ValueError("Missing one of required fields: template_name, wa_id, parameters")

        # Get WhatsApp token
        token_entry = get_latest_token(db)
        if not token_entry:
            raise Exception("No WhatsApp token available")

        headers = {
            "Authorization": f"Bearer {token_entry.token}",
            "Content-Type": "application/json"
        }

        # Compose payload
        if template_name == "nps_temp1":
            data = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": wa_id,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en"},
                    "components": [
                        {
                            "type": "body",
                            "parameters": parameters
                        }
                    ]
                }
            }

        elif template_name == "nps_zenoti_one":
            data = {
                "messaging_product": "whatsapp",
                "to": wa_id,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en_IN"},
                    "components": [
                        {
                            "type": "header",
                            "parameters": [
                                {
                                    "type": "image",
                                    "image": {
                                        "id": "2499081017126786"
                                    }
                                }
                            ]
                        },
                        {
                            "type": "body",
                            "parameters": parameters
                        },
                        {
                            "type": "button",
                            "sub_type": "url",
                            "index": "0",
                            "parameters": [
                                {
                                    "type": "text",
                                    "text": "t?t=123456"
                                }
                            ]
                        }
                    ]
                }
            }

        else:
            raise Exception(f"Unsupported template: {template_name}")

        # Send request
        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        resp_json = response.json()

        if response.status_code != 200 or "messages" not in resp_json:
            print(f"[❌] Failed to send to {wa_id}:", resp_json)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Save message to DB
        msg = MessageCreate(
            message_id=resp_json["messages"][0]["id"],
            from_wa_id="917729992376",  # your business number
            to_wa_id=wa_id,
            type="template",
            body=template_name,
            timestamp=datetime.now(),
            customer_id=customer_service.get_customer_by_wa_id(db, wa_id)
        )
        message_service.create_message(db, msg)
        print(f"[✅] Sent & saved: {wa_id}")

        # Send over websocket
        asyncio.run(manager.broadcast({
            "from": msg.from_wa_id,
            "to": msg.to_wa_id,
            "type": msg.type,
            "message": msg.body,
            "timestamp": msg.timestamp.isoformat(),
            "media_id": getattr(msg, "media_id", None),
            "caption": getattr(msg, "caption", None),
            "filename": getattr(msg, "filename", None),
            "mime_type": getattr(msg, "mime_type", None)
        }))

    except Exception as e:
        print("[‼️] Error while processing task:", str(e))

    finally:
        db.close()
        try:
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as ack_error:
            print("[‼️] Failed to ack message:", str(ack_error))


# RabbitMQ setup
if __name__ == "__main__":
    conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    ch = conn.channel()
    ch.queue_declare(queue="whatsapp_campaign", durable=True)
    ch.basic_qos(prefetch_count=1)
    ch.basic_consume(queue="whatsapp_campaign", on_message_callback=callback)
    print("📥 Listening for WhatsApp campaign tasks...")
    ch.start_consuming()