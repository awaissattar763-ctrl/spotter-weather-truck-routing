import os


class CorsMiddleware:
    """CORS for the API.

    Single-service deployments (frontend + API on one origin) do not
    need CORS at all. Local dev (frontend on :5173, API on :8000) does.
    Origins are env-driven: CORS_ALLOWED_ORIGINS="*" (default, dev) or a
    comma-separated allowlist; requests from other origins get no
    Access-Control-Allow-Origin header.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        raw = os.environ.get("CORS_ALLOWED_ORIGINS", "*").strip()
        self.allow_all = raw == "*" or raw == ""
        self.allowed = {
            o.strip() for o in raw.split(",") if o.strip()
        } if not self.allow_all else set()

    def __call__(self, request):
        if request.method == "OPTIONS":
            from django.http import HttpResponse
            resp = HttpResponse()
        else:
            resp = self.get_response(request)
        origin = request.headers.get("Origin")
        if self.allow_all or (origin and origin in self.allowed):
            resp["Access-Control-Allow-Origin"] = origin or "*"
        resp["Access-Control-Allow-Headers"] = "Content-Type"
        resp["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp
