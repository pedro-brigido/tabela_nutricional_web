"""
Security middleware: headers, request logging.
"""

from flask import Flask, request
import logging

logger = logging.getLogger(__name__)


def register_security_headers(app: Flask) -> None:
    """Inject security headers on every response."""

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["X-XSS-Protection"] = "1; mode=block"

        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        csp_parts = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' cdn.tailwindcss.com unpkg.com",
            "style-src 'self' 'unsafe-inline' fonts.googleapis.com cdn.tailwindcss.com",
            "font-src 'self' fonts.gstatic.com",
            "img-src 'self' data: https:",
            "connect-src 'self' accounts.google.com",
            "form-action 'self' accounts.google.com",
            "frame-ancestors 'none'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_parts)

        return response


def register_request_logging(app: Flask) -> None:
    """Log every request for observability."""

    @app.before_request
    def log_request():
        logger.debug(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "ip": request.remote_addr,
            },
        )
