class CorsMiddleware:
    """Minimal CORS for local development (frontend on :5173, API on :8000)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS":
            from django.http import HttpResponse
            resp = HttpResponse()
        else:
            resp = self.get_response(request)
        resp["Access-Control-Allow-Origin"] = "*"
        resp["Access-Control-Allow-Headers"] = "Content-Type"
        resp["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp
