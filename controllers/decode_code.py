from typing import Optional
from utils import extract_template_id, fetch_vn_template


def decode_code_controller(code: str):
    try:
        if not code:
            return {
                "code": 400,
                "msg": "invalid input",
                "error_msg": "code is required"
            }

        code = code.strip()

        # ─────────────────────────────
        # Extract template ID
        # ─────────────────────────────
        template_id: Optional[str] = None
        id_type: str = "id"

        if "template?id=" in code or "template?uuid=" in code:
            # Full QR string — handle cases like: "VN://template?id=123 Flow://..."
            code = code.split(" ")[0]
            template_id, id_type = extract_template_id(code)
        else:
            # Bare numeric ID passed directly
            template_id = code
            id_type = "id"
        if not template_id:
            return {
                "code": 404,
                "msg": "template not found",
                "error_msg": ""
            }

        # ─────────────────────────────
        # Fetch from VN API
        # ─────────────────────────────
        vn_data = fetch_vn_template(template_id, id_type=id_type)
        if not vn_data:
            return {
                "code": 404,
                "msg": "template not found",
            }

        return {
            "code": 1,
            "msg": "success",
            "data": vn_data
        }

    except Exception as e:
        return {
            "code": 500,
            "msg": "internal error",
            "error_msg": str(e)
        }

