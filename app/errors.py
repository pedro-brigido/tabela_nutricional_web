"""
Custom error handlers.
"""

from flask import Flask, jsonify, render_template, request


def _wants_json() -> bool:
    return (
        request.is_json
        or request.accept_mimetypes.best == "application/json"
    )


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(e):
        if _wants_json():
            return jsonify({"error": str(e.description)}), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(403)
    def forbidden(e):
        if _wants_json():
            return jsonify({"error": str(e.description)}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        if _wants_json():
            return jsonify({"error": "Recurso não encontrado."}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(429)
    def too_many_requests(e):
        if _wants_json():
            return (
                jsonify(
                    {
                        "error": "Muitas requisições. Tente novamente em alguns minutos."
                    }
                ),
                429,
            )
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_error(e):
        if _wants_json():
            return jsonify({"error": "Erro interno do servidor."}), 500
        return render_template("errors/500.html"), 500
