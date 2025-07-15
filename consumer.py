from datetime import datetime, time

import pika, json, requests
from sqlalchemy.orm import Session
from controllers.whatsapp_controller import WHATSAPP_API_URL
from database.db import get_db
from models.models import Template, JobStatus
from services import whatsapp_service
from services.template_service import union_dict
from utils.json_placeholder import fill_placeholders



from sqlalchemy import func
from models.models import Job  # ⬅️ Import Job model

def callback(ch, method, properties, body):
    db: Session = next(get_db())
    task = json.loads(body)
    customer = task['customer']
    job_id = task['job_id']
    campaign_id = task['campaign_id']

    start_time = time.time()  # ⏱ Start timing

    try:
        token_obj = whatsapp_service.get_latest_token(db)
        if not token_obj:
            raise Exception("Token not available")

        token = token_obj.token
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        if task['type'] != "template":
            payload = {
                "messaging_product": "whatsapp",
                "to": customer['wa_id'],
                "recipient_type": "individual",
                "type": task['type'],
                task['type']: task['content']
            }
        else:
            template_name = task['content']['template_name']
            template = db.query(Template).filter(Template.template_name == template_name).first()

            extra = {
                "customer_id": customer['id'],
                "customer_name": customer['name'],
                "customer_phone": customer['wa_id'],
            }

            new_vars = union_dict(extra, template.template_vars)
            new_body = fill_placeholders(template.template_body, new_vars)

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": extra["customer_phone"],
                "type": "template",
                "template": new_body
            }

        # ✅ Send message
        res = requests.post(WHATSAPP_API_URL, json=payload, headers=headers)
        status = "success" if res.status_code == 200 else "failure"

    except Exception as e:
        print(f"Error sending to {customer['wa_id']}: {e}")
        status = "failure"

    end_time = time.time()
    duration = round(end_time - start_time, 2)

    # ✅ Update JobStatus
    job_status = db.query(JobStatus).filter_by(
        job_id=job_id,
        customer_id=customer['id']
    ).first()

    if job_status:
        job_status.status = status

    # ✅ Count completed vs total customers for this job
    total_customers = db.query(JobStatus).filter_by(job_id=job_id).count()
    completed_customers = db.query(JobStatus).filter(
        JobStatus.job_id == job_id,
        JobStatus.status.in_(["success", "failure"])
    ).count()

    # ✅ If all customers done, update job.last_triggered_time
    if completed_customers == total_customers:
        job = db.query(Job).filter_by(id=job_id).first()
        if job:
            job.last_triggered_time = datetime.utcnow()
            db.commit()
            print(f"Job {job_id} completed. Total time: {duration:.2f}s")

    else:
        db.commit()

    print(f"[{status.upper()}] {customer['wa_id']} - {duration}s")
    ch.basic_ack(delivery_tag=method.delivery_tag)



def start_worker():
    connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
    channel = connection.channel()
    channel.queue_declare(queue="campaign_queue", durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue="campaign_queue", on_message_callback=callback)
    print("Worker started. Waiting for messages...")
    channel.start_consuming()


if __name__ == "__main__":
    start_worker()
