from sqlalchemy.dialects.postgresql import ENUM

reply_material_type_enum = ENUM(
    "text", "image", "template", "document", "video", "audio", name="reply_material_type_enum", create_type=False
)

keyword_matching_enum = ENUM(
    "exact", "fuzzy", "contains", name="keyword_matching_enum", create_type=False
)

routing_type_enum = ENUM("user", "team", name="routing_type_enum", create_type=False) 