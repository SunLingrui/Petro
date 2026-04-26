import sys
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

sys.modules.setdefault('app', sys.modules[__name__])

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['INFLUX_HOST'] = os.getenv('INFLUX_HOST', 'http://127.0.0.1:8086')
app.config['INFLUX_ORG'] = os.getenv('INFLUX_ORG', 'Patro')
app.config['INFLUX_TOKEN'] = os.getenv('INFLUX_TOKEN', 'ydxUZa7VyfLoc5k8GV2jFCOxZjJUgrkhgW4QXvgAPnnft8Btirv9R1fa-TMjNAOIUrU-2su80D7Yb7W9dR3zuQ==')
app.config['INFLUX_BUCKET'] = os.getenv('INFLUX_BUCKET', 'rto_mock_dev')
app.config['APP_TIMEZONE'] = os.getenv('APP_TIMEZONE', 'Asia/Shanghai')

db = SQLAlchemy(app)


import routes, models
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True)
