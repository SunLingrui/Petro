from functools import wraps

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import app, db
from .models import User
from .services.influx_service import (
    InfluxQueryError,
    build_empty_optimization_target_payload,
    get_import_payload,
    get_optimization_target_payload,
)


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("USERNAME"):
            flash("请先登录后再访问系统页面", "error")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)

    return wrapped_view


def render_system_template(template_name, page_title, active_page, **context):
    return render_template(
        template_name,
        page_title=page_title,
        username=session.get("USERNAME"),
        active_page=active_page,
        **context,
    )


def get_current_user():
    username = session.get("USERNAME")
    if not username:
        return None
    return User.query.filter(User.name == username).first()


@app.route("/")
def root():
    if session.get("USERNAME"):
        return redirect(url_for("main"))
    return redirect(url_for("login"))


@app.route("/main")
@app.route("/index")
@login_required
def main():
    main_data = {
        "today_runs": "85",
        "yesterday_runs": "0",
        "month_runs": "85",
        "total_runs": "85",
        "latest_plan_time": "14:40:00",
        "next_plan_remaining": "1",
        "runtime_days": "1",
        "usage_rate": "100",
        "master_switch_on": True,
        "equipment_status": "稳态",
        "equipment_status_class": "state-good",
        "runtime_status": "正常",
        "runtime_status_class": "state-good",
        "apc_status": "非联动",
        "apc_status_class": "state-danger",
        "program_status": "未开始",
        "program_status_class": "state-danger",
        "execution_rate": "100",
        "price_benefit": "104.9286",
        "cost_benefit": "219.3456",
    }
    return render_system_template("main.html", "系统首页", "main", main_data=main_data)


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("USERNAME"):
        return redirect(url_for("main"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("用户名和密码不能为空", "error")
            return redirect(url_for("login"))

        user_in_db = User.query.filter(User.name == username).first()
        if not user_in_db:
            flash(f"未找到用户名为 {username} 的用户", "error")
            return redirect(url_for("login"))

        if not check_password_hash(user_in_db.password_hash, password):
            flash("密码错误", "error")
            return redirect(url_for("login"))

        session["USERNAME"] = user_in_db.name
        flash("登录成功，已进入实时优化系统", "success")
        return redirect(url_for("main"))

    return render_template("login.html", page_title="系统登录")


@app.route("/logout")
def logout():
    session.pop("USERNAME", None)
    flash("你已退出实时优化系统", "success")
    return redirect(url_for("login"))


@app.route("/profile")
@login_required
def profile():
    user = get_current_user()
    if not user:
        session.pop("USERNAME", None)
        flash("当前登录用户不存在，请重新登录", "error")
        return redirect(url_for("login"))

    return render_system_template(
        "profile.html",
        "个人资料",
        "profile",
        user=user,
    )


@app.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    user = get_current_user()
    if not user:
        session.pop("USERNAME", None)
        flash("当前登录用户不存在，请重新登录", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()

        if not username or not email:
            flash("用户名和邮箱不能为空", "error")
            return redirect(url_for("profile"))

        existing_user = User.query.filter(User.name == username, User.id != user.id).first()
        if existing_user:
            flash("该用户名已存在，请更换用户名", "error")
            return redirect(url_for("profile"))

        existing_email = User.query.filter(User.email == email, User.id != user.id).first()
        if existing_email:
            flash("该邮箱已被注册，请更换邮箱", "error")
            return redirect(url_for("profile"))

        user.name = username
        user.email = email
        db.session.commit()
        session["USERNAME"] = user.name

        flash("个人资料已更新", "success")
        return redirect(url_for("profile"))

    return render_system_template(
        "edit_profile.html",
        "编辑资料",
        "profile",
        user=user,
    )


@app.route("/profile/password", methods=["GET", "POST"])
@login_required
def change_password():
    user = get_current_user()
    if not user:
        session.pop("USERNAME", None)
        flash("当前登录用户不存在，请重新登录", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_password or not new_password or not confirm_password:
            flash("请完整填写密码字段", "error")
            return redirect(url_for("profile"))

        if not check_password_hash(user.password_hash, current_password):
            flash("当前密码错误", "error")
            return redirect(url_for("profile"))

        if new_password != confirm_password:
            flash("两次输入的新密码不一致", "error")
            return redirect(url_for("profile"))

        if len(new_password) < 6:
            flash("新密码长度不能少于 6 位", "error")
            return redirect(url_for("profile"))

        user.password_hash = generate_password_hash(new_password)
        db.session.commit()

        flash("密码已更新", "success")
        return redirect(url_for("profile"))

    return render_system_template(
        "change_password.html",
        "修改密码",
        "profile",
        user=user,
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("USERNAME"):
        return redirect(url_for("main"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if not username or not email or not password or not password2:
            flash("请完整填写所有字段", "error")
            return redirect(url_for("register"))

        if password != password2:
            flash("两次输入的密码不一致", "error")
            return redirect(url_for("register"))

        existing_user = User.query.filter(User.name == username).first()
        if existing_user:
            flash("该用户名已存在，请更换用户名", "error")
            return redirect(url_for("register"))

        existing_email = User.query.filter(User.email == email).first()
        if existing_email:
            flash("该邮箱已被注册，请更换邮箱", "error")
            return redirect(url_for("register"))

        user = User(
            name=username,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()

        flash("注册成功，请登录后进入实时优化系统", "success")
        return redirect(url_for("login"))

    return render_template("register.html", page_title="账号注册")


@app.route("/rto/optimization-target")
@login_required
def optimization_target():
    requested_target = request.args.get("target")
    requested_start = request.args.get("start_at")
    requested_end = request.args.get("end_at")
    requested_sample = request.args.get("sample_minutes")

    try:
        target_payload = get_optimization_target_payload(
            target_key=requested_target,
            start_local=requested_start,
            end_local=requested_end,
            sample_minutes=requested_sample,
        )
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        target_payload = build_empty_optimization_target_payload(
            target_key=requested_target,
            error_message=influx_error,
        )

    return render_system_template(
        "optimization_target.html",
        "优化目标监测",
        "optimization_target",
        target_rows=target_payload["target_rows"],
        target_history=target_payload["target_history"],
        initial_target_payload=target_payload,
        influx_error=influx_error,
    )


@app.route("/rto/optimization-target/import")
@login_required
def optimization_target_import():
    try:
        return jsonify(get_import_payload())
    except InfluxQueryError as exc:
        return jsonify({"error": str(exc)}), 502


@app.route("/rto/optimization-target/data")
@login_required
def optimization_target_data():
    try:
        payload = get_optimization_target_payload(
            target_key=request.args.get("target"),
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
    except InfluxQueryError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(payload)


@app.route("/rto/operation")
@login_required
def rto_operation():
    operation_data = {
        "status": "页面预留",
        "copy": "RTO运行页面先保留为空白占位，后续可在此接入运行状态、启停记录和联锁信息。",
    }
    return render_system_template(
        "rto_operation.html",
        "RTO运行",
        "rto_operation",
        operation_data=operation_data,
    )


@app.route("/rto/optimization-variables")
@login_required
def optimization_variables():
    variable_form = {
        "reactor_temperature": {
            "tag": "150TIC1090",
            "current_value": "520.5126",
            "unit": "℃",
            "upper_optimized_value": "522.25",
            "optimized_value": "520.5274",
            "delta_vs_output": "-1.4318",
            "current_step": "0.3000",
            "max_step": "1.0000",
            "output_setpoint": "521.9592",
            "push_enabled": True,
        },
        "catalyst_oil_ratio": {
            "tag": "150YLYQH",
            "current_value": "8.9275",
            "unit": "",
            "upper_optimized_value": "9.2111",
            "optimized_value": "8.9452",
            "delta_vs_output": "-0.0203",
            "current_step": "0.0500",
            "max_step": "0.3000",
            "output_setpoint": "8.9452",
            "push_enabled": True,
        },
        "regenerator_temperature": {
            "tag": "150TI1082",
            "current_value": "679.6999",
            "unit": "℃",
            "upper_optimized_value": "676.2",
            "optimized_value": "679.5676",
            "delta_vs_output": "0.6676",
            "current_step": "0.3000",
            "max_step": "1.0000",
            "output_setpoint": "679.2",
            "push_enabled": True,
        },
        "feed_preheat_temperature": {
            "tag": "150TIC2006",
            "current_value": "232.2645",
            "unit": "℃",
            "upper_optimized_value": "234.9",
            "optimized_value": "234.9",
            "delta_vs_output": "",
            "current_step": "",
            "max_step": "",
            "output_setpoint": "",
            "push_enabled": False,
        },
    }
    return render_system_template(
        "optimization_variables.html",
        "优化变量监测",
        "optimization_variables",
        variable_form=variable_form,
    )


@app.route("/rto/variables/reactor-temperature")
@login_required
def reactor_temperature():
    monitor_data = {
        "push_enabled": True,
        "apc_status": "未接受",
        "apc_status_class": "state-danger",
        "current_value": "520.3295",
        "optimized_value": "520.5274",
        "model_value": "522.25",
        "feedback_value": "520.5274",
        "output_setpoint": "521.9592",
        "delta_vs_output": "-1.4318",
        "lower_limit": "518.5000",
        "upper_limit": "522.3000",
        "current_step": "0.3000",
        "max_step": "1.0000",
        "apc_lower_limit": "520.5",
        "apc_upper_limit": "522.5",
        "dcs_lower_limit": "0",
        "dcs_upper_limit": "600",
    }
    history_data = {
        "enabled": False,
        "start_date": "2026-04-18",
        "start_time": "14:51:37",
        "end_date": "2026-04-25",
        "end_time": "14:51:45",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "reactor_temperature.html",
        "反应温度监测",
        "reactor_temperature",
        monitor_data=monitor_data,
        history_data=history_data,
    )


@app.route("/rto/variables/catalyst-oil-ratio")
@login_required
def catalyst_oil_ratio():
    monitor_data = {
        "push_enabled": False,
        "apc_status": "null",
        "apc_status_class": "",
        "current_value": "8.9275",
        "optimized_value": "8.9452",
        "model_value": "8.9483",
        "feedback_value": "9.1072",
        "output_setpoint": "8.9655",
        "delta_vs_output": "-0.0203",
        "lower_limit": "8.6000",
        "upper_limit": "9.2000",
        "current_step": "0.0500",
        "max_step": "0.3000",
        "apc_lower_limit": "8.5000",
        "apc_upper_limit": "10.0000",
        "dcs_lower_limit": "0",
        "dcs_upper_limit": "20",
    }
    history_data = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:54:07",
        "end_date": "2026-04-17",
        "end_time": "08:54:07",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "catalyst_oil_ratio.html",
        "剂油比监测",
        "catalyst_oil_ratio",
        monitor_data=monitor_data,
        history_data=history_data,
    )


@app.route("/rto/variables/regenerator-temperature")
@login_required
def regenerator_temperature():
    monitor_data = {
        "push_enabled": True,
        "apc_status": "未接受",
        "apc_status_class": "state-danger",
        "current_value": "679.1437",
        "optimized_value": "679.5676",
        "model_value": "676.2",
        "feedback_value": "679.5676",
        "output_setpoint": "679.2",
        "delta_vs_output": "0.6676",
        "lower_limit": "675.0000",
        "upper_limit": "682.0000",
        "current_step": "0.3000",
        "max_step": "1.0000",
        "apc_lower_limit": "676",
        "apc_upper_limit": "681",
        "dcs_lower_limit": "0",
        "dcs_upper_limit": "1000",
    }
    history_data = {
        "enabled": False,
        "start_date": "2026-04-18",
        "start_time": "14:52:47",
        "end_date": "2026-04-25",
        "end_time": "14:52:47",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "regenerator_temperature.html",
        "再生温度监测",
        "regenerator_temperature",
        monitor_data=monitor_data,
        history_data=history_data,
    )


@app.route("/rto/variables/feed-preheat-temperature")
@login_required
def feed_preheat_temperature():
    monitor_data = {
        "current_value": "0",
        "optimized_value": "0",
        "model_value": "250",
        "feedback_value": "0",
        "lower_limit": "0.0000",
        "upper_limit": "0.0000",
    }
    history_data = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:54:53",
        "end_date": "2026-04-17",
        "end_time": "08:54:53",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "feed_preheat_temperature.html",
        "原料预热温度监测",
        "feed_preheat_temperature",
        monitor_data=monitor_data,
        history_data=history_data,
    )


@app.route("/analytics/overview")
@login_required
def price_lab_overview():
    overview_tables = {
        "raw_materials": [
            {"name": "重油新鲜进料", "value": "3781.0000", "unit": "元/吨"},
            {"name": "重芳烃", "value": "4552.0000", "unit": "元/吨"},
        ],
        "products": [
            {"name": "干气", "value": "1500.0000", "unit": "元/吨"},
            {"name": "液化气", "value": "4359.0000", "unit": "元/吨"},
            {"name": "汽油", "value": "4843.0000", "unit": "元/吨"},
            {"name": "重石脑油", "value": "4456.0000", "unit": "元/吨"},
            {"name": "柴油", "value": "4456.0000", "unit": "元/吨"},
            {"name": "油浆", "value": "2615.0000", "unit": "元/吨"},
        ],
        "utilities": [
            {"name": "中压蒸汽", "value": "248.0000", "unit": "元/吨"},
            {"name": "低压蒸汽", "value": "97.0000", "unit": "元/吨"},
            {"name": "电", "value": "0.5900", "unit": "元/kWh"},
            {"name": "除盐水", "value": "4.8800", "unit": "元/吨"},
            {"name": "循环水", "value": "0.1600", "unit": "元/吨"},
            {"name": "低温热水", "value": "0.5000", "unit": "元/吨"},
            {"name": "污水", "value": "12.5000", "unit": "元/吨"},
        ],
        "feed_lab": [
            {"name": "混合进料密度", "value": "925.0000", "unit": "kg/m³"},
            {"name": "混合进料残炭", "value": "5.7000", "unit": "wt%"},
        ],
        "product_lab": [
            {"name": "汽油产品密度", "value": "725.0000", "unit": "kg/m³"},
            {"name": "汽油产品终馏点", "value": "180.0000", "unit": "℃"},
            {"name": "柴油产品密度", "value": "920.0000", "unit": "kg/m³"},
            {"name": "柴油产品95%点", "value": "360.0000", "unit": "℃"},
        ],
        "costs": [
            {"name": "原料成本", "value": "3815.2000", "unit": "元/吨"},
            {"name": "加工成本", "value": "126.5000", "unit": "元/吨"},
            {"name": "能耗成本", "value": "48.9600", "unit": "元/吨"},
            {"name": "综合成本", "value": "3990.6600", "unit": "元/吨"},
        ],
    }
    return render_system_template(
        "price_lab_overview.html",
        "价格与化验分析总览",
        "price_lab_overview",
        overview_tables=overview_tables,
    )


@app.route("/analytics/raw-product-prices")
@login_required
def raw_product_prices():
    raw_chart_history = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:49:36",
        "end_date": "2026-04-07",
        "end_time": "08:49:42",
        "sample_interval": "30 min",
    }
    product_chart_history = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:49:36",
        "end_date": "2026-04-17",
        "end_time": "08:50:07",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "raw_product_prices.html",
        "原料和产品价格",
        "raw_product_prices",
        raw_chart_history=raw_chart_history,
        product_chart_history=product_chart_history,
    )


@app.route("/analytics/utilities-prices")
@login_required
def utilities_prices():
    history_data = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:51:43",
        "end_date": "2026-04-17",
        "end_time": "08:51:43",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "utilities_prices.html",
        "公用工程价格",
        "utilities_prices",
        history_data=history_data,
    )


@app.route("/analytics/lab-analysis")
@login_required
def lab_analysis():
    feed_history_data = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:52:25",
        "end_date": "2026-04-17",
        "end_time": "08:52:25",
        "sample_interval": "30 min",
    }
    product_history_data = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:52:25",
        "end_date": "2026-04-17",
        "end_time": "08:53:18",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "lab_analysis.html",
        "化验分析数据",
        "lab_analysis",
        feed_history_data=feed_history_data,
        product_history_data=product_history_data,
    )


@app.route("/analytics/cost-prices")
@login_required
def cost_prices():
    history_data = {
        "enabled": True,
        "start_date": "2026-01-01",
        "start_time": "08:55:12",
        "end_date": "2026-04-17",
        "end_time": "08:55:12",
        "sample_interval": "30 min",
    }
    return render_system_template(
        "cost_prices.html",
        "成本价格",
        "cost_prices",
        history_data=history_data,
    )


@app.route("/system/parameter-settings")
@login_required
def parameter_settings():
    return render_system_template("parameter_settings.html", "参数配置", "parameter_settings")
