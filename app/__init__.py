import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(PROJECT_ROOT, "instance")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")


app = Flask(
    __name__,
    instance_path=INSTANCE_DIR,
    template_folder=TEMPLATES_DIR,
    static_folder=STATIC_DIR,
)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(INSTANCE_DIR, "site.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "your-secret-key")
app.config["INFLUX_HOST"] = os.getenv("INFLUX_HOST", "http://127.0.0.1:8086")
app.config["INFLUX_ORG"] = os.getenv("INFLUX_ORG", "")
app.config["INFLUX_TOKEN"] = os.getenv("INFLUX_TOKEN", "")
app.config["INFLUX_BUCKET"] = os.getenv("INFLUX_BUCKET", "rto_mock_dev")
app.config["APP_TIMEZONE"] = os.getenv("APP_TIMEZONE", "Asia/Shanghai")


os.makedirs(INSTANCE_DIR, exist_ok=True)

db = SQLAlchemy(app)


from . import models, routes  # noqa: E402,F401


with app.app_context():
    db.create_all()
