"""Security response headers applied to every HTTP response.

Kept in its own module (``app.middleware``) so the header policy can be
reviewed and tested independently of the rate limiter and log scrubbing.
"""
from __future__ import annotations

SECURITY_HEADERS: dict[str, str] = {
    # TLS is terminated at Nginx/CloudFront; HSTS tells browsers to stay on it.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class SecurityHeadersMiddleware:
    """Pure ASGI middleware that adds hardening headers to every response."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                for name, value in SECURITY_HEADERS.items():
                    encoded = name.lower().encode("latin-1")
                    if encoded not in existing:
                        headers.append((encoded, value.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
