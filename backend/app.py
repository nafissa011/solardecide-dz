import argparse
import logging
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

sys.path.insert(0, str(Path(__file__).parent))
BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

from config import PARQUET_PATH, CACHE_DIR
from db_models import db


def _ensure_sqlite_schema(app: Flask) -> None:
    """Additive migrations for SQLite databases created by older builds."""
    with app.app_context():
        engine = db.engine
        if engine.dialect.name != "sqlite":
            return

        with engine.begin() as conn:
            user_columns = {
                row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)").fetchall()
            }
            if "name" not in user_columns:
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN name VARCHAR(100) NOT NULL DEFAULT ''"
                )
                # Backfill name from email local-part for existing rows
                conn.exec_driver_sql(
                    """
                    UPDATE users
                    SET name = substr(email, 1, instr(email || '@', '@') - 1)
                    WHERE name = '' OR name IS NULL
                    """
                )
            if "role" not in user_columns:
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"
                )


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.sort_keys = False  # preserve insertion order in API responses

    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{BASE_DIR / 'database.db'}"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
    _ensure_sqlite_schema(app)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    logger = logging.getLogger("solardz")

    # Never use wildcard origins — explicit allowlist only
    is_prod = os.environ.get("FLASK_ENV") == "production"
    allowed = (
        os.environ.get("ALLOWED_ORIGINS", "https://solardz.dz").split(",")
        if is_prod else
        ["http://localhost:3000", "http://localhost:5000",
         "http://127.0.0.1:3000", "http://127.0.0.1:5000"]
    )
    CORS(app,
         resources={r"/api/.*": {"origins": allowed}},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         expose_headers=["Content-Disposition", "X-Report-Id"])

    def get_remote_address_except_options():
        from flask import request
        if request.method == "OPTIONS":
            return None  # OPTIONS must bypass rate limiting (preflight)
        return get_remote_address()

    limiter = Limiter(
        app=app,
        key_func=get_remote_address_except_options,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"
    )
    app.config["LIMITER"] = limiter

    @app.route("/")
    def index():
        return send_from_directory(FRONTEND_DIR, "index.html")

    @app.route("/<path:path>")
    def serve_static(path):
        static_dir = FRONTEND_DIR
        if os.path.exists(os.path.join(static_dir, path)):
            resp = send_from_directory(static_dir, path)
            # Disable caching for all static assets during development
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp
        return send_from_directory(static_dir, "index.html")

    os.makedirs(CACHE_DIR, exist_ok=True)

    from data_engine import DataEngine
    if not Path(PARQUET_PATH).exists():
        logger.warning(
            f"⚠️  Fichier Parquet introuvable : {PARQUET_PATH}\n"
            "   Placer le fichier algeria_solar_communes_REAL.parquet dans backend/data/"
        )
    engine = DataEngine(PARQUET_PATH)
    app.config["DATA_ENGINE"] = engine
    logger.info(f"✅ DataEngine connecté → {PARQUET_PATH}")

    from models.loader import ModelLoader
    model_loader = ModelLoader()
    app.config["MODEL_LOADER"] = model_loader
    logger.info("✅ ModelLoader initialisé (checkpoints chargés à la demande)")

    from preprocessing import SolarPreprocessor
    preprocessor_pkl = Path(__file__).parent / "checkpoints" / "preprocessor.pkl"
    if preprocessor_pkl.exists():
        preprocessor = SolarPreprocessor.load(str(preprocessor_pkl))
        logger.info(f"✅ Preprocessor chargé ← {preprocessor_pkl}")
    else:
        preprocessor = SolarPreprocessor()
        logger.info("ℹ️  Preprocessor non fitté — inférence limitée")
    app.config["PREPROCESSOR"] = preprocessor

    # ML services are optional — ranking/wilaya endpoints must stay up even
    # when torch or model checkpoints are missing.
    try:
        from services import RecommendationService, ForecastingService, ZoneModelService

        model_service = ZoneModelService()
        app.config["ZONE_MODEL_SERVICE"] = model_service

        rec_service = RecommendationService(engine, model_service)
        app.config["RECOMMENDATION_SERVICE"] = rec_service

        forecast_service = ForecastingService(model_loader, preprocessor, engine)
        app.config["FORECASTING_SERVICE"] = forecast_service
        logger.info("✅ ML services initialisés")
    except Exception as exc:
        logger.warning("⚠️ Services ML indisponibles — démarrage en mode dataset/API uniquement: %s", exc)
        app.config["ZONE_MODEL_SERVICE"] = None
        app.config["RECOMMENDATION_SERVICE"] = None
        app.config["FORECASTING_SERVICE"] = None
        model_service = rec_service = forecast_service = None

    # Blueprint registration order matters — Flask matches the first rule that fits.
    # forecast_ml must come before dataset_api so /api/forecast-simple/<wilaya>
    # and /api/long-term-trend/<wilaya> are served by the AI model, not the parquet proxy.
    forecast_ml_bp = None
    try:
        from ml.prevision.forecast_route import bp as forecast_ml_bp  # type: ignore
        logger.info("✅ Blueprint IA forecast (Hybride N-HiTS+LSTM) chargé")
    except Exception as exc:
        logger.warning("⚠️ Blueprint IA forecast_ml indisponible: %s", exc)

    from routes.data_service_api      import bp as data_service_bp
    from routes.plan                  import bp as plan_bp
    from routes.dataset_api           import bp as dataset_api_bp
    from routes.wilayas               import bp as wilayas_bp
    from routes.zones                 import bp as zones_bp
    from routes.roi                   import bp as roi_bp
    from routes.decision              import bp as decision_bp
    from ml.comparaison_wilaya.compare import bp as compare_bp
    from routes.comparaison_phase3    import bp as comparaison_phase3_bp
    from routes.admin                 import bp as admin_bp
    from routes.profile               import bp as profile_bp
    from routes.search                import bp as search_bp
    from routes.misc                  import bp as misc_bp
    from routes.models                import bp as models_bp
    from routes.reports               import bp as reports_bp
    from routes.auth                  import bp as auth_bp
    from routes.analyses              import bp as analyses_bp
    from routes.history               import bp as history_bp

    optional_blueprints = []
    for route_name, import_stmt in (
        ("forecast",       "from routes.forecast       import bp as forecast_bp"),
        ("ranking",        "from routes.ranking        import bp as ranking_bp"),
        ("recommendation", "from routes.recommendation import bp as recommendation_bp"),
    ):
        try:
            ns = {}
            exec(import_stmt, globals(), ns)
            optional_blueprints.append(ns[list(ns.keys())[0]])
            logger.info("✅ Blueprint optionnel chargé: %s", route_name)
        except Exception as exc:
            logger.warning("⚠️ Blueprint optionnel désactivé (%s): %s", route_name, exc)

    ordered_bps = [forecast_ml_bp] if forecast_ml_bp is not None else []

    for blueprint in (
        *ordered_bps,
        data_service_bp, plan_bp, dataset_api_bp,
        wilayas_bp, zones_bp, roi_bp,
        decision_bp, compare_bp, comparaison_phase3_bp,
        admin_bp, profile_bp, search_bp, misc_bp,
        models_bp, reports_bp, auth_bp, analyses_bp, history_bp,
        *optional_blueprints,
    ):
        app.register_blueprint(blueprint, url_prefix="/api")

    @app.get("/api/health")
    def health():
        return jsonify({
            "status": "ok",
            "parquet": Path(PARQUET_PATH).exists(),
            "version": "1.0.0",
            "services": {
                "recommendation": rec_service is not None,
                "forecasting":    forecast_service is not None,
            }
        })

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Ressource introuvable", "status": 404}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Erreur interne du serveur", "status": 500}), 500

    @app.errorhandler(Exception)
    def unhandled(e):
        logger.exception(f"Exception non gérée: {e}")
        # Best-effort: persist to error_logs without breaking the error response
        try:
            from services.admin_service import log_error
            from services.plan_service import get_current_user
            from flask import request as _req
            u = None
            try:
                u = get_current_user()
            except Exception:  # noqa: BLE001
                pass
            log_error(str(e), page=_req.path if _req else "",
                      user_id=(u.id if u else None))
        except Exception:  # noqa: BLE001
            pass
        return jsonify({"error": str(e), "status": 500}), 500

    logger.info("🌞 SolarDZ backend prêt")
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port, debug=True)