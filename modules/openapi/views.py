from django.http import HttpResponse, JsonResponse

from common.api.base import BaseAPIView


class SchemaView(BaseAPIView):
    def get(self, request):
        from modules.openapi.document import build_schema

        return JsonResponse(build_schema())


class DocsView(BaseAPIView):
    def get(self, request):
        html = """<!doctype html>
<html><head><title>Raksha Setu API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"></head>
<body><div id="swagger"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url:"/api/v1/schema",dom_id:"#swagger"})</script>
</body></html>"""
        return HttpResponse(html)
