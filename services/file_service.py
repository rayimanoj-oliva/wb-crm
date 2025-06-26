from sqlalchemy.orm import Session
from models.models import File

def create_file_record(
    db: Session,
    file_id: str,
    name: str,
    mimetype: str
):
    file_record = File(
        id=file_id,
        name=name,
        mimetype=mimetype
    )
    db.add(file_record)
    db.commit()
    db.refresh(file_record)
    return file_record


def get_all_files(db: Session):
    return db.query(File).order_by(File.created_at.desc()).all()