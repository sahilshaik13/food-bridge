from app.models import GeminiScan
from app.services.vertex_ai_service import scan_food_with_vertex_ai


def scan_food_with_gemini(image_bytes: bytes, food_type_hint: str = "") -> GeminiScan:
    """Backward-compatible wrapper. Use scan_food_with_vertex_ai for new code."""
    return scan_food_with_vertex_ai(image_bytes=image_bytes, food_type_hint=food_type_hint)
