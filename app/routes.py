from functools import wraps

from flask import flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from . import app, db
from .models import User
from .services.influx_service import (
    InfluxQueryError,
    build_empty_market_price_chart_payload,
    build_empty_optimization_variables_payload,
    build_empty_optimization_target_payload,
    build_empty_price_lab_overview_payload,
    build_empty_raw_product_prices_payload,
    build_empty_variable_detail_payload,
    get_market_price_chart_payload,
    get_optimization_variables_payload,
    get_import_payload,
    get_optimization_target_payload,
    get_price_lab_overview_payload,
    get_raw_product_prices_payload,
    get_variable_detail_payload,
    get_variable_key_by_slug,
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


def render_variable_detail_page(variable_key, page_title, active_page):
    requested_start = request.args.get("start_at")
    requested_end = request.args.get("end_at")
    requested_sample = request.args.get("sample_minutes")

    try:
        payload = get_variable_detail_payload(
            variable_key=variable_key,
            start_local=requested_start,
            end_local=requested_end,
            sample_minutes=requested_sample,
        )
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        payload = build_empty_variable_detail_payload(variable_key=variable_key, error_message=influx_error)

    return render_system_template(
        "variable_detail.html",
        page_title,
        active_page,
        variable_payload=payload,
        monitor_data=payload["monitor_data"],
        monitor_cards=payload["monitor_cards"],
        history_data=payload["history_data"],
        influx_error=influx_error,
    )


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
    try:
        payload = get_optimization_variables_payload()
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        payload = build_empty_optimization_variables_payload(error_message=influx_error)

    return render_system_template(
        "optimization_variables.html",
        "优化变量监测",
        "optimization_variables",
        variable_rows=payload["variable_rows"],
        influx_error=influx_error,
    )


@app.route("/rto/variables/reactor-temperature")
@login_required
def reactor_temperature():
    return render_variable_detail_page("reactor_temperature", "反应温度监测", "reactor_temperature")


@app.route("/rto/variables/catalyst-oil-ratio")
@login_required
def catalyst_oil_ratio():
    return render_variable_detail_page("catalyst_oil_ratio", "剂油比监测", "catalyst_oil_ratio")


@app.route("/rto/variables/regenerator-temperature")
@login_required
def regenerator_temperature():
    return render_variable_detail_page("regenerator_temperature", "再生温度监测", "regenerator_temperature")


@app.route("/rto/variables/feed-preheat-temperature")
@login_required
def feed_preheat_temperature():
    return render_variable_detail_page("feed_preheat_temperature", "原料预热温度监测", "feed_preheat_temperature")


@app.route("/rto/variables/<variable_slug>/data")
@login_required
def variable_detail_data(variable_slug):
    variable_key = get_variable_key_by_slug(variable_slug)
    if not variable_key:
        return jsonify({"error": "未找到对应的优化变量"}), 404

    try:
        payload = get_variable_detail_payload(
            variable_key=variable_key,
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
    except InfluxQueryError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(payload)


@app.route("/analytics/overview")
@login_required
def price_lab_overview():
    try:
        payload = get_price_lab_overview_payload()
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        payload = build_empty_price_lab_overview_payload(error_message=influx_error)

    return render_system_template(
        "price_lab_overview.html",
        "价格与化验分析总览",
        "price_lab_overview",
        overview_tables=payload["overview_tables"],
        influx_error=influx_error,
    )


@app.route("/analytics/raw-product-prices")
@login_required
def raw_product_prices():
    requested_start = request.args.get("start_at")
    requested_end = request.args.get("end_at")
    requested_sample = request.args.get("sample_minutes")

    try:
        payload = get_raw_product_prices_payload(
            start_local=requested_start,
            end_local=requested_end,
            sample_minutes=requested_sample,
        )
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        payload = build_empty_raw_product_prices_payload(error_message=influx_error)

    return render_system_template(
        "raw_product_prices.html",
        "原料和产品价格",
        "raw_product_prices",
        raw_product_payload=payload,
        influx_error=influx_error,
    )


@app.route("/analytics/raw-product-prices/data")
@login_required
def raw_product_prices_data():
    try:
        payload = get_market_price_chart_payload(
            metric_group=request.args.get("group"),
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
    except InfluxQueryError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(payload)


@app.route("/analytics/utilities-prices")
@login_required
def utilities_prices():
    try:
        payload = get_market_price_chart_payload(
            metric_group="utility",
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        payload = build_empty_market_price_chart_payload("utility", error_message=influx_error)

    return render_system_template(
        "utilities_prices.html",
        "公用工程价格",
        "utilities_prices",
        market_payload=payload,
        influx_error=influx_error,
    )


@app.route("/analytics/utilities-prices/data")
@login_required
def utilities_prices_data():
    try:
        payload = get_market_price_chart_payload(
            metric_group="utility",
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
    except InfluxQueryError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(payload)


@app.route("/analytics/lab-analysis")
@login_required
def lab_analysis():
    try:
        payload = {
            "feed_lab": get_market_price_chart_payload(
                metric_group="feed_lab",
                start_local=request.args.get("start_at"),
                end_local=request.args.get("end_at"),
                sample_minutes=request.args.get("sample_minutes"),
            ),
            "product_lab": get_market_price_chart_payload(
                metric_group="product_lab",
                start_local=request.args.get("start_at"),
                end_local=request.args.get("end_at"),
                sample_minutes=request.args.get("sample_minutes"),
            ),
        }
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        payload = {
            "feed_lab": build_empty_market_price_chart_payload("feed_lab", error_message=influx_error),
            "product_lab": build_empty_market_price_chart_payload("product_lab", error_message=influx_error),
        }

    return render_system_template(
        "lab_analysis.html",
        "化验分析数据",
        "lab_analysis",
        lab_payload=payload,
        influx_error=influx_error,
    )


@app.route("/analytics/lab-analysis/data")
@login_required
def lab_analysis_data():
    try:
        payload = get_market_price_chart_payload(
            metric_group=request.args.get("group"),
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
    except InfluxQueryError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(payload)


@app.route("/analytics/cost-prices")
@login_required
def cost_prices():
    try:
        payload = get_market_price_chart_payload(
            metric_group="cost",
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
        influx_error = None
    except InfluxQueryError as exc:
        influx_error = str(exc)
        payload = build_empty_market_price_chart_payload("cost", error_message=influx_error)

    return render_system_template(
        "cost_prices.html",
        "成本价格",
        "cost_prices",
        market_payload=payload,
        influx_error=influx_error,
    )


@app.route("/analytics/cost-prices/data")
@login_required
def cost_prices_data():
    try:
        payload = get_market_price_chart_payload(
            metric_group="cost",
            start_local=request.args.get("start_at"),
            end_local=request.args.get("end_at"),
            sample_minutes=request.args.get("sample_minutes"),
        )
    except InfluxQueryError as exc:
        return jsonify({"error": str(exc)}), 502
    return jsonify(payload)


@app.route("/system/parameter-settings")
@login_required
def parameter_settings():
    return render_system_template("parameter_settings.html", "参数配置", "parameter_settings")
