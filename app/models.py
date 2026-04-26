from . import db


# User model to represent a user with attributes like name, email, and password hash.
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), nullable=False)
    #user_type = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    #avatar_url = db.Column(db.String(255), nullable=True)  # 添加头像地址字段






