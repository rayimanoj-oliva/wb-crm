import pika, json, requests
from datetime import datetime
from sqlalchemy.orm import Session

from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import SessionLocal  # your DB session creator
from services import customer_service, message_service
from schemas.MessageSchema import MessageCreate
from services.whatsapp_service import get_latest_token


def callback(ch, method, properties, body):
    task = json.loads(body)
    db: Session = SessionLocal()

    try:
        # Get token
        token_entry = get_latest_token(db)
        if not token_entry:
            raise Exception("No WhatsApp token available")

        headers = {
            "Authorization": f"Bearer {token_entry.token}",
            "Content-Type": "application/json"
        }

        # Compose request
        data = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": task["to"],
            "type": "template",
            "template": {
                "name": task["template_name"],
                "language": {"code": "en"},
                "components": [
                    {
                        "type": "body",
                        "parameters": task["parameters"]
                    }
                ]
            }
        }

        response = requests.post(WHATSAPP_API_URL, headers=headers, json=data)
        resp_json = response.json()

        # Handle failure
        if response.status_code != 200 or 'messages' not in resp_json:
            print(f"[!] Failed to send: {task['to']} ->", resp_json)
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Save to DB
        msg = MessageCreate(
            message_id=resp_json['messages'][0]['id'],
            from_wa_id="917729992376",  # your official sender
            to_wa_id=task["to"],
            type="template",
            body=task["template_name"],
            timestamp=datetime.now(),
            customer_id=customer_service.get_customer_by_wa_id(db, task["to"])
        )

        message_service.create_message(db, msg)
        print(f"[✓] Sent & saved: {task['to']}")

    except Exception as e:
        print("[!!] Error:", str(e))

    finally:
        db.close()
        ch.basic_ack(delivery_tag=method.delivery_tag)


# RabbitMQ setup
conn = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
ch = conn.channel()
ch.queue_declare(queue="whatsapp_campaign", durable=True)
ch.basic_qos(prefetch_count=1)
ch.basic_consume(queue="whatsapp_campaign", on_message_callback=callback)
print("📥 Listening for WhatsApp campaign tasks...")
ch.start_consuming()
