from flask import Flask, request, render_template_string, redirect, send_from_directory, session
from werkzeug.utils import secure_filename
import os, json, re, subprocess, threading
from datetime import datetime
from html import escape as html_escape

app = Flask(__name__)
app.secret_key = "slsu_jge_secure_key_2026"
DB_FILE = "data.json"
UPLOAD_FOLDER = "uploads"
ALLOWED_FILE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DEFAULT_ADMINS = {
    "admin": {
        "password": "admin123",
        "school_id": "2022-0001",
        "complete_name": "Main Admin",
        "course": "N/A",
        "year_level": "N/A",
        "role": "admin"
    },
    "registrar_admin": {
        "password": "registrar123",
        "school_id": "2022-0002",
        "complete_name": "Registrar Admin",
        "course": "N/A",
        "year_level": "N/A",
        "role": "registrar_admin"
    },
    "guard_admin": {
        "password": "guard123",
        "school_id": "2022-0003",
        "complete_name": "Guard Admin",
        "course": "N/A",
        "year_level": "N/A",
        "role": "guard_admin"
    },
    "maintenance_admin": {
        "password": "maintenance123",
        "school_id": "2022-0004",
        "complete_name": "Maintenance Admin",
        "course": "N/A",
        "year_level": "N/A",
        "role": "maintenance_admin"
    }
}

COURSES = ["BEED", "BSED", "BSFAS", "BSBA", "BPA", "BSIT"]
MAJORS_BY_COURSE = {
    "BSIT": ["BindTech", "Computer Technology", "Food Tech"],
    "BSBA": ["Marketing Management", "Financial Management"],
    "BSED": ["English", "Math", "Science"]
}
COURSE_MAJOR_ALIASES = {
    "BSINFORMATIONTECHNOLOGY": "BSIT",
    "BACHELOROFSCIENCEININFORMATIONTECHNOLOGY": "BSIT",
    "BSBUSINESSADMINISTRATION": "BSBA",
    "BACHELOROFSCIENCEINBUSINESSADMINISTRATION": "BSBA",
    "BACHELOROFSECONDARYEDUCATION": "BSED"
}


def get_major_course_key(course):
    compact_course = re.sub(r"[^A-Z0-9]", "", str(course or "").upper())
    if compact_course in MAJORS_BY_COURSE:
        return compact_course
    if compact_course in COURSE_MAJOR_ALIASES:
        return COURSE_MAJOR_ALIASES[compact_course]
    for course_key in MAJORS_BY_COURSE:
        if compact_course.startswith(course_key):
            return course_key
    return ""

YEAR_LEVELS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]


def load_data():
    global users, pending_users, maintenance_reports, announcements, grade_requests, notifications, guard_logs, guard_on_duty
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            users = data.get("users", {})
            pending_users = data.get("pending_users", {})
            maintenance_reports = data.get("maintenance_reports", [])
            announcements = data.get("announcements", {
                "registrar": [],
                "guard": [],
                "maintenance": []
            })
            grade_requests = data.get("grade_requests", [])
            notifications = data.get("notifications", {})
            guard_logs = data.get("guard_logs", [])
            guard_on_duty = str(data.get("guard_on_duty", "") or "")
    else:
        users = {}
        pending_users = {}
        maintenance_reports = []
        announcements = {
            "registrar": [],
            "guard": [],
            "maintenance": []
        }
        grade_requests = []
        notifications = {}
        guard_logs = []
        guard_on_duty = ""

    notifications = notifications if isinstance(notifications, dict) else {}
    guard_logs = guard_logs if isinstance(guard_logs, list) else []

    # Rename the old course abbreviation in existing account records.
    for account in list(users.values()) + list(pending_users.values()):
        if isinstance(account, dict) and account.get("course") == "BFAS":
            account["course"] = "BSFAS"

    # Backward compatibility for old maintenance reports.
    for i, report in enumerate(maintenance_reports, start=1):
        if not isinstance(report, dict):
            continue
        report.setdefault("id", i)
        report.setdefault("status", "Pending")
        report.setdefault("reported_by_user", "")
        report.setdefault("date_time", "-")

    for admin_user, admin_data in DEFAULT_ADMINS.items():
        if admin_user not in users:
            users[admin_user] = admin_data

    save_data()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_FILE_EXTENSIONS


def save_data():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "users": users,
            "pending_users": pending_users,
            "maintenance_reports": maintenance_reports,
            "announcements": announcements,
            "grade_requests": grade_requests,
            "notifications": notifications,
            "guard_logs": guard_logs,
            "guard_on_duty": guard_on_duty
        }, f, indent=4)


load_data()


def get_current_user():
    uname = session.get("username")
    return uname if uname in users else None


def can_manage(office):
    uname = get_current_user()
    if not uname:
        return False

    role = users[uname].get("role")

    if role == "admin":
        return True
    if office == "registrar" and role == "registrar_admin":
        return True
    if office == "guard" and role == "guard_admin":
        return True
    if office == "maintenance" and role == "maintenance_admin":
        return True

    return False


def can_view_requests():
    uname = get_current_user()
    if not uname:
        return False

    role = users[uname].get("role")
    return role in ["admin", "registrar_admin"]


def add_notification(targets, message, link="/dashboard", office=None, reference_id=None):
    """Send notifications once per recipient when a stable reference is supplied."""
    if isinstance(targets, str):
        targets = [targets]

    recipients = []
    for target in targets:
        if target in users:
            recipients.append(target)
        else:
            recipients.extend(
                username for username, data in users.items()
                if data.get("role") == target
            )

    for username in dict.fromkeys(recipients):
        notifications.setdefault(username, [])
        if reference_id and any(
            isinstance(item, dict) and item.get("reference_id") == reference_id
            for item in notifications[username]
        ):
            continue
        next_id = max([n.get("id", 0) for n in notifications[username] if isinstance(n, dict)] + [0]) + 1
        notification = {
            "id": next_id,
            "message": message,
            "link": link,
            "office": office,
            "read": False,
            "date_time": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        }
        if reference_id:
            notification["reference_id"] = reference_id
        notifications[username].insert(0, notification)

    save_data()


def backfill_request_notifications():
    """Create missing office and student notices for requests already on file."""
    for req in grade_requests:
        request_id = req.get("id")
        if request_id is None:
            continue
        doc_type = str(req.get("document_type", "document")).upper()
        student_name = req.get("student_name", "Student")
        add_notification(
            ["admin", "registrar_admin"],
            f"📄 New document request from {student_name} — {doc_type} (Request #{request_id}).",
            "/registrar", "registrar_admin", f"request-{request_id}-submitted-office"
        )
        requested_by = req.get("requested_by")
        if requested_by in users:
            add_notification(
                requested_by,
                f"✅ Your {doc_type} request (Request #{request_id}) was submitted to the Registrar Office.",
                "/registrar", "registrar_admin", f"request-{request_id}-submitted-student"
            )


backfill_request_notifications()


def deduplicate_legacy_notifications(items):
    """Hide exact duplicate legacy notifications that have no saved timestamp."""
    result = []
    seen_legacy = set()
    for item in items:
        if item.get("date_time"):
            result.append(item)
            continue
        key = (item.get("message"), item.get("link"), item.get("office"))
        if key in seen_legacy:
            continue
        seen_legacy.add(key)
        result.append(item)
    return result


def get_unread_notifications(username):
    return [
        n for n in deduplicate_legacy_notifications(notifications.get(username, []))
        if not n.get("read", False)
    ]


def mark_notifications_read(username):
    for n in notifications.get(username, []):
        n["read"] = True
    save_data()


@app.route('/logo.png')
def logo():
    return send_from_directory(os.getcwd(), 'logo.png')


@app.route('/bg.jpg')
def bg():
    return send_from_directory(os.getcwd(), 'bg.jpg')


def get_sidebar(active_page):
    uname = get_current_user()
    if not uname:
        return ""

    user_data = users.get(uname, {})
    role = user_data.get("role")
    pending_count = len(pending_users)
    unread = get_unread_notifications(uname)

    def office_badge(office_role):
        count = sum(
            1 for n in unread
            if n.get("office") == office_role
        )
        return f' <span class="badge">{count}</span>' if count else ""

    if role == "admin":
        pages = {
            "dashboard": "Dashboard",
            "pending": f"Pending Accounts ({pending_count})" if pending_count else "Pending Accounts",
            "registered": "Registered Students",
            "registrar": "Registrar Office" + office_badge("registrar_admin"),
            "guard": "Guard Office" + office_badge("guard_admin"),
            "maintenance": "Maintenance Office" + office_badge("maintenance_admin"),
            "profile": "Profile",
            "notifications": "Notifications" + (f' <span class="badge">{len(unread)}</span>' if unread else "")
        }
    elif role == "registrar_admin":
        pages = {
            "dashboard": "Dashboard",
            "registered": "Registered Students",
            "registrar": "Registrar Office" + office_badge("registrar_admin"),
            "profile": "Profile",
            "notifications": "Notifications" + (f' <span class="badge">{len(unread)}</span>' if unread else "")
        }
    elif role == "guard_admin":
        pages = {
            "dashboard": "Dashboard",
            "registered": "Registered Students",
            "guard": "Guard Office" + office_badge("guard_admin"),
            "profile": "Profile",
            "notifications": "Notifications" + (f' <span class="badge">{len(unread)}</span>' if unread else "")
        }
    elif role == "maintenance_admin":
        pages = {
            "dashboard": "Dashboard",
            "registered": "Registered Students",
            "maintenance": "Maintenance Office" + office_badge("maintenance_admin"),
            "profile": "Profile",
            "notifications": "Notifications" + (f' <span class="badge">{len(unread)}</span>' if unread else "")
        }
    else:
        pages = {
            "dashboard": "Dashboard",
            "registrar": "Registrar Office" + office_badge("registrar_admin"),
            "guard": "Guard Office" + office_badge("guard_admin"),
            "maintenance": "Maintenance Office" + office_badge("maintenance_admin"),
            "profile": "Profile",
            "notifications": "Notifications" + (f' <span class="badge">{len(unread)}</span>' if unread else "")
        }

    sidebar_html = ""
    profile_name = pages.pop("profile", "Profile")
    for key, name in pages.items():
        active_class = "active" if active_page == key else ""
        badge = f' <span class="badge">{pending_count}*</span>' if key == "pending" and pending_count > 0 and role == "admin" else ""
        sidebar_html += f'<a href="/{key}"><button class="menu-btn {active_class}">{name}{badge}</button></a>'

    sidebar_html += f'<div class="sidebar-footer"><a href="/profile" class="profile-link"><button class="footer-btn profile-btn">{profile_name}</button></a><a href="/logout" class="logout-link"><button class="footer-btn logout-btn">Log Out</button></a></div>'
    return sidebar_html


def dashboard_template(content, active_page, page_title):
    uname = get_current_user()
    user_data = users.get(uname, {}) if uname else {}
    is_admin = "true" if user_data.get("role") == "admin" else "false"

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLSU-JGE {page_title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}}
:root{{--green:#11c6a6;--deep:#087c72;--ink:#103f42;--muted:#66817f;--line:#d9f0e9;--soft:#e9faf4}}
body{{min-height:100vh;display:flex;background:linear-gradient(135deg,rgba(0,135,112,.40) 0%,rgba(0,210,170,.34) 100%),url('/bg.jpg') center center / cover fixed;color:var(--ink)}}
.sidebar{{width:252px;height:auto;min-height:0;flex:none;background:rgba(178,235,216,.93);padding:18px 16px;display:flex;flex-direction:column;gap:8px;position:fixed;top:68px;bottom:0;left:0;z-index:1002;border-right:1px solid #bceadd;overflow-y:auto;transform:translateX(-105%);transition:transform .22s ease}}
.sidebar{{width:252px;height:auto;min-height:0;flex:none;background:linear-gradient(180deg,#1c527e,#123b60);padding:18px 16px 24px;display:flex;flex-direction:column;gap:8px;position:fixed;top:68px;bottom:0;left:0;z-index:1002;border-right:1px solid #123b60;overflow-y:auto;transform:translateX(-105%);transition:transform .22s ease;color:#fff}}
.sidebar{{width:252px;height:auto;min-height:0;flex:none;background:rgba(178,235,216,.93);padding:18px 16px;display:flex;flex-direction:column;gap:8px;position:fixed;top:68px;bottom:0;left:0;z-index:1002;border-right:1px solid #bceadd;overflow-y:auto;transform:translateX(-105%);transition:transform .22s ease}}
.sidebar.is-open{{transform:translateX(0)}}
.menu-toggle{{position:fixed;top:12px;left:18px;z-index:1004;width:44px;height:44px;border:1px solid #bceadd;border-radius:12px;background:#effff8;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;cursor:pointer;box-shadow:0 3px 12px rgba(9,92,77,.14)}}
.menu-toggle span{{display:block;width:20px;height:2px;border-radius:2px;background:#087c72;transition:transform .18s,opacity .18s}}
.menu-toggle.is-open span:first-child{{transform:translateY(7px) rotate(45deg)}}
.menu-toggle.is-open span:nth-child(2){{opacity:0}}
.menu-toggle.is-open span:last-child{{transform:translateY(-7px) rotate(-45deg)}}
.menu-backdrop{{display:none;position:fixed;inset:68px 0 0;background:rgba(4,69,62,.38);backdrop-filter:blur(2px);z-index:1000}}
.menu-backdrop.is-open{{display:block}}
.sidebar-brand{{height:68px;display:flex;align-items:center;gap:12px;padding:0 8px 13px;border-bottom:1px solid var(--line);margin-bottom:12px}}
.brand-mark{{width:42px;height:42px;display:grid;place-items:center;border-radius:14px;background:#e1fff4;color:var(--deep);font-size:21px}}
.brand-title{{font-size:15px;font-weight:800;color:#103f42;letter-spacing:.3px}}
.brand-subtitle{{font-size:9px;color:#557b73;letter-spacing:1.3px;margin-top:3px}}
.menu-section-label{{font-size:10px;font-weight:800;letter-spacing:1.4px;color:#5d8c7e;padding:9px 12px 4px}}
.sidebar-brand{{height:82px;display:flex;align-items:center;gap:12px;padding:0 8px 14px;border-bottom:1px solid rgba(255,255,255,.2);margin-bottom:12px}}
.brand-mark{{width:42px;height:42px;display:grid;place-items:center;border-radius:14px;background:#ffffff20;color:#fff;font-size:21px}}
.brand-title{{font-size:18px;font-weight:800;color:#fff;letter-spacing:.3px}}
.brand-subtitle{{font-size:10px;color:#d1e6f5;letter-spacing:.5px;margin-top:3px}}
.menu-section-label{{font-size:10px;font-weight:800;letter-spacing:1.4px;color:#b9d6e8;padding:9px 12px 4px}}
.sidebar-brand{{height:68px;display:flex;align-items:center;gap:12px;padding:0 8px 13px;border-bottom:1px solid var(--line);margin-bottom:12px}}
.brand-mark{{width:42px;height:42px;display:grid;place-items:center;border-radius:14px;background:#e1fff4;color:var(--deep);font-size:21px}}
.brand-title{{font-size:15px;font-weight:800;color:#103f42;letter-spacing:.3px}}
.brand-subtitle{{font-size:9px;color:#557b73;letter-spacing:1.3px;margin-top:3px}}
.menu-section-label{{font-size:10px;font-weight:800;letter-spacing:1.4px;color:#5d8c7e;padding:9px 12px 4px}}
.sidebar a{{text-decoration:none}}
.menu-btn{{padding:12px 13px;border:0;border-radius:11px;background:transparent;color:#265d56;font-size:13px;font-weight:500;cursor:pointer;text-align:left;width:100%;display:flex;justify-content:space-between;align-items:center;transition:.15s}}
.menu-btn.active{{background:#83edcf;color:#074e4d;font-weight:700;box-shadow:inset 3px 0 #0a9f8d}}
.menu-btn:hover{{filter:saturate(1.15);transform:translateX(2px)}}
.sidebar a[href="/dashboard"] .menu-btn:not(.active),
.sidebar a[href="/pending"] .menu-btn:not(.active),
.sidebar a[href="/registered"] .menu-btn:not(.active),
.sidebar a[href="/registrar"] .menu-btn:not(.active),
.sidebar a[href="/guard"] .menu-btn:not(.active),
.sidebar a[href="/maintenance"] .menu-btn:not(.active),
.sidebar a[href="/profile"] .menu-btn:not(.active),
.sidebar a[href="/notifications"] .menu-btn:not(.active){{background:#e3f8ee;color:#245b55}}
.sidebar a[href="/pending"] .menu-btn:not(.active){{background:#e3f8ee;color:#245b55}}
.sidebar a .menu-btn.active{{background:#83edcf;color:#074e4d;box-shadow:inset 3px 0 #087c72}}
.menu-btn.logout{{color:#176c63;background:#dff8ed!important;margin-top:auto}}
.sidebar a{{text-decoration:none}}
.menu-btn{{padding:13px 14px;border:0;border-radius:11px;background:transparent;color:#f4f8fc;font-size:14px;font-weight:700;cursor:pointer;text-align:left;width:100%;display:flex;justify-content:space-between;align-items:center;transition:background .15s,color .15s,transform .15s}}
.menu-item-label{{display:flex;align-items:center;gap:12px}}
.menu-icon{{width:24px;text-align:center;font-size:17px}}
.menu-btn.active{{background:#ffd65a;color:#123f67;font-weight:800;box-shadow:none}}
.menu-btn:hover{{background:rgba(255,255,255,.12);transform:translateX(2px)}}
.menu-btn.active:hover{{background:#ffdc6d}}
.menu-btn .badge{{background:#fff;color:#174b73;border-radius:99px;padding:2px 7px;font-size:10px}}
.sidebar-footer{{margin-top:auto;padding-top:16px;border-top:1px solid rgba(255,255,255,.2);display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.menu-btn{{padding:12px 13px;border:0;border-radius:11px;background:#e3f8ee;color:#245b55;font-size:13px;font-weight:500;cursor:pointer;text-align:left;width:100%;display:flex;justify-content:space-between;align-items:center;transition:.15s}}
.menu-btn.active{{background:#83edcf;color:#074e4d;font-weight:700;box-shadow:inset 3px 0 #087c72}}
.menu-btn:hover{{filter:saturate(1.15);transform:translateX(2px)}}
.menu-btn .badge{{background:#fff;color:#087c72;border-radius:99px;padding:2px 7px;font-size:10px}}
.sidebar-footer{{margin-top:auto;padding-top:16px;border-top:1px solid var(--line);display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.profile-link,.logout-link{{min-width:0}}
.footer-btn{{width:100%;min-height:46px;border:0;border-radius:11px;padding:8px 6px;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}}
.profile-btn{{background:#fff;color:#174b73}}
.logout-btn{{background:#ffd04a;color:#143c62}}
.profile-btn:hover{{background:#edf5fb}}
.logout-btn:hover{{background:#ffdc6d}}
.footer-btn{{width:100%;min-height:42px;border:0;border-radius:11px;padding:8px 6px;font-size:12px;font-weight:800;cursor:pointer;white-space:nowrap}}
.profile-btn{{background:#fff;color:#176c63}}
.logout-btn{{background:#dff8ed;color:#176c63}}
.profile-btn:hover,.logout-btn:hover{{filter:saturate(1.15)}}
.main{{flex:1;min-width:0;padding:8px 14px 20px;overflow-y:auto}}
.header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px;color:#f5fffb;text-shadow:0 1px 4px rgba(0,48,43,.72)}}
.header img{{width:42px;height:42px;object-fit:cover;background:#fff;border-radius:13px;padding:2px;box-shadow:0 2px 10px #193f4012}}
.header-text h1{{font-size:24px;font-weight:800;color:#ffffff}}
.header-text p{{font-size:12px;color:#e2fff6;margin-top:4px}}
.header-user{{display:flex;align-items:center;gap:10px;margin-left:auto}}
.header-avatar{{width:40px;height:40px;border-radius:50%;background:#bdf4df;display:grid;place-items:center;color:var(--deep);font-size:12px;font-weight:800}}
.header-user-name{{font-size:12px;font-weight:700;color:#ffffff}}
.header-user-role{{font-size:10px;color:#d8fff3;margin-top:2px}}
.card{{background:rgba(255,255,255,.91);border:1px solid #d9f0e9;border-radius:17px;padding:20px;margin-bottom:16px;box-shadow:0 5px 18px rgba(6,83,75,.09)}}
.card h2{{font-size:17px;color:#164d4b;margin-bottom:10px;font-weight:700}}
.dashboard-crumb{{font-size:11px;color:#effff9;text-shadow:0 1px 4px rgba(0,48,43,.8);margin:0 0 9px 56px;min-height:44px;display:flex;align-items:center}}
.dashboard-hero{{position:relative;overflow:hidden;background:linear-gradient(115deg,#087d72,#16c6a7);border-radius:20px;padding:27px 32px;color:white;margin-bottom:20px;min-height:144px}}
.dashboard-hero:after{{content:' ';position:absolute;width:190px;height:190px;border-radius:50%;right:3%;top:-88px;background:#ffffff12;box-shadow:75px 125px 0 18px #ffffff0d}}
.hero-date{{font-size:10px;letter-spacing:1px;color:#d5fff4}}
.hero-title{{font-size:25px;font-weight:800;margin:12px 0 7px;color:white}}
.hero-subtitle{{font-size:12px;color:#e2fff9;max-width:730px}}
.hero-link{{position:absolute;right:32px;top:50%;transform:translateY(-50%);background:#ffffff22;color:#fff;border:1px solid #ffffff24;border-radius:12px;padding:12px 16px;text-decoration:none;font-size:12px;font-weight:700;z-index:1}}
.dashboard-stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px;margin-bottom:20px}}
.stat-card{{background:rgba(255,255,255,.91);border:1px solid #d9f0e9;border-radius:16px;padding:17px;min-height:112px;box-shadow:0 5px 18px rgba(6,83,75,.08)}}
.stat-card-link{{display:block;color:inherit;text-decoration:none;border-radius:16px;transition:transform .16s ease,box-shadow .16s ease}}
.stat-card-link:hover{{transform:translateY(-3px);box-shadow:0 9px 22px rgba(29,67,81,.12)}}
.stat-top{{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:11px}}
.stat-icon{{width:36px;height:36px;border-radius:12px;display:grid;place-items:center;font-size:17px;background:#e2f7f0}}
.stat-number{{font-size:28px;font-weight:800;color:var(--ink);margin:8px 0 0 45px}}
.dashboard-columns{{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(300px,.95fr);gap:18px}}
.course-chart{{display:flex;align-items:flex-end;gap:clamp(8px,2.4vw,24px);height:176px;padding:20px 10px 0;border-bottom:1px solid var(--line)}}
.course-bar-wrap{{flex:1;height:100%;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:8px;color:#66817f;font-size:10px}}
.course-bar{{width:min(38px,70%);min-height:6px;border-radius:7px 7px 2px 2px;background:#11c6a6}}
.office-hero{{display:flex;align-items:center;gap:18px;min-height:116px;padding:20px 25px;border-radius:18px;background:linear-gradient(115deg,#075e59,#0bb99e);color:#fff;margin-bottom:16px;position:relative;overflow:hidden}}
.office-hero:after{{content:"";position:absolute;right:-35px;top:-90px;width:210px;height:210px;border-radius:50%;background:#fff;opacity:.055}}
.office-hero-brand{{width:68px;height:68px;border-radius:15px;background:#fff;display:grid;place-items:center;flex:none;overflow:hidden}}
.office-hero-brand img{{width:62px;height:62px;object-fit:contain}}
.office-hero-copy{{position:relative;z-index:1}}
.office-kicker{{font-size:9px;letter-spacing:1.2px;color:#d7ead9;font-weight:700}}
.office-hero h2{{font-size:21px;color:#fff;margin:6px 0 4px}}
.office-hero p{{font-size:11px;color:#e0eee4}}
.office-metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:17px}}
.office-metric{{display:flex;align-items:center;gap:11px;background:rgba(255,255,255,.91);border:1px solid #d9f0e9;border-radius:14px;padding:13px 16px;box-shadow:0 5px 18px rgba(6,83,75,.08)}}
.office-metric-icon{{width:36px;height:36px;border-radius:11px;display:grid;place-items:center;background:#c8f5e6;color:#087c72;font-size:15px;font-weight:700}}
.office-metric-icon.gold{{background:#e4faee;color:#167a68}}
.office-metric-icon.sage{{background:#c8f5e6;color:#087c72}}
.office-metric-icon.clay{{background:#d9f7ed;color:#177b70}}
.office-metric-label{{font-size:10px;color:#66817f}}
.office-metric-value{{font-size:19px;font-weight:800;color:#103f42;margin-top:2px}}
.dashboard-notice{{padding:13px;border-radius:12px;margin-top:11px;background:#def8ee}}
.dashboard-notice:nth-of-type(2n){{background:#d5f5ef}}
.dashboard-notice-title{{font-size:12px;font-weight:700;color:#164d4b;margin-bottom:6px}}
.dashboard-notice-text{{font-size:11px;line-height:1.5;color:#5c7a78}}
.notification-date{{display:block;margin-top:6px;color:#66817f;font-size:10px}}
.dashboard-table{{overflow-x:auto}}
.dashboard-table th{{background:#d7f5eb;color:#397b70;font-size:10px;letter-spacing:.4px}}
.dashboard-table th,.dashboard-table td{{padding:10px 9px}}
.table-status{{display:inline-block;padding:5px 9px;border-radius:20px;background:#c9f3e3;color:#087c72;font-weight:700;font-size:10px}}
@media(max-width:1050px){{.sidebar{{width:218px}}.dashboard-stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}.dashboard-columns{{grid-template-columns:1fr}}}}
@media(max-width:680px){{body{{display:block}}.sidebar{{width:min(84vw,290px);height:auto;min-height:0;position:fixed;top:68px;bottom:0;left:0;padding:16px;display:flex;flex-direction:column;flex-wrap:nowrap;border-right:1px solid #eaf0ef;border-bottom:0;transform:translateX(-105%);transition:transform .22s ease}}.sidebar.is-open{{transform:translateX(0)}}.sidebar-brand{{width:100%;height:48px;margin:0;padding-bottom:8px}}.menu-section-label{{display:none}}.sidebar a{{flex:0 0 auto}}.menu-btn{{padding:10px;font-size:11px}}.main{{padding:8px 14px 18px}}.header{{margin-bottom:16px}}.header-text h1{{font-size:19px}}.header-user-role{{display:none}}.dashboard-hero{{padding:22px 19px}}.hero-title{{font-size:21px;max-width:75%}}.hero-link{{position:relative;right:auto;top:auto;transform:none;display:inline-block;margin-top:15px}}.dashboard-stats{{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.stat-card{{padding:13px}}.stat-number{{font-size:24px}}}}
@media(max-width:1050px){{.sidebar{{width:252px}}.dashboard-stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}.dashboard-columns{{grid-template-columns:1fr}}}}
@media(max-width:680px){{body{{display:block}}.sidebar{{width:min(84vw,290px);height:auto;min-height:0;position:fixed;top:68px;bottom:0;left:0;padding:16px;display:flex;flex-direction:column;flex-wrap:nowrap;border-right:1px solid #eaf0ef;border-bottom:0;transform:translateX(-105%);transition:transform .22s ease}}.sidebar.is-open{{transform:translateX(0)}}.sidebar-brand{{width:100%;height:62px;margin:0;padding-bottom:8px}}.menu-section-label{{display:none}}.sidebar-footer{{padding-top:12px}}.footer-btn{{font-size:11px}}.sidebar a{{flex:0 0 auto}}.menu-btn{{padding:10px;font-size:11px}}.main{{padding:8px 14px 18px}}.header{{margin-bottom:16px}}.header-text h1{{font-size:19px}}.header-user-role{{display:none}}.dashboard-hero{{padding:22px 19px}}.hero-title{{font-size:21px;max-width:75%}}.hero-link{{position:relative;right:auto;top:auto;transform:none;display:inline-block;margin-top:15px}}.dashboard-stats{{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.stat-card{{padding:13px}}.stat-number{{font-size:24px}}}}
@media(max-width:680px){{body{{display:block}}.sidebar{{width:min(84vw,290px);height:auto;min-height:0;position:fixed;top:68px;bottom:0;left:0;padding:16px;display:flex;flex-direction:column;flex-wrap:nowrap;border-right:1px solid #eaf0ef;border-bottom:0;transform:translateX(-105%);transition:transform .22s ease}}.sidebar.is-open{{transform:translateX(0)}}.sidebar-brand{{width:100%;height:48px;margin:0;padding-bottom:8px}}.menu-section-label{{display:none}}.sidebar-footer{{padding-top:12px}}.footer-btn{{font-size:11px}}.sidebar a{{flex:0 0 auto}}.menu-btn{{padding:10px;font-size:11px}}.main{{padding:8px 14px 18px}}.header{{margin-bottom:16px}}.header-text h1{{font-size:19px}}.header-user-role{{display:none}}.dashboard-hero{{padding:22px 19px}}.hero-title{{font-size:21px;max-width:75%}}.hero-link{{position:relative;right:auto;top:auto;transform:none;display:inline-block;margin-top:15px}}.dashboard-stats{{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.stat-card{{padding:13px}}.stat-number{{font-size:24px}}}}
.card h2{{font-size:18px;color:#164d4b;margin-bottom:15px;font-weight:700}}
.logout{{background:#dff8ed!important;color:#176c63!important;margin-top:20px}}
a{{text-decoration:none}}
.info-row{{margin-bottom:8px;color:#555}}
.info-row b{{color:#087c72}}
.approve-btn{{background:#11c6a6;color:#fff;padding:8px 12px;border:none;border-radius:8px;cursor:pointer;margin:2px;font-size:13px}}
.reject-btn{{background:#ff4d4d;color:#fff;padding:8px 12px;border:none;border-radius:8px;cursor:pointer;margin:2px;font-size:13px}}
.edit-btn{{background:#0d9e8a;color:#fff;padding:6px 10px;border:none;border-radius:8px;cursor:pointer;font-size:12px;text-decoration:none;display:inline-block;margin:2px}}
.delete-btn{{background:#ff4d4d;color:#fff;padding:6px 10px;border:none;border-radius:8px;cursor:pointer;font-size:12px;text-decoration:none;display:inline-block;margin:2px}}
.submit-btn{{background:#11c6a6;color:#fff;padding:10px 20px;border:none;border-radius:10px;font-weight:700;cursor:pointer}}
.form-group{{margin-bottom:15px}}
.form-group label{{display:block;margin-bottom:5px;color:#164d4b;font-weight:600}}
.form-group input,.form-group textarea,.form-group select{{width:100%;padding:10px;border:1px solid #bfe9db;border-radius:8px;background:#f7fffb}}
.announce{{border-left:4px solid #11c6a6;padding:15px;margin-bottom:12px;background:#e8f9f1;border-radius:8px;position:relative}}
.notification-link{{display:block;color:inherit;text-decoration:none}}
.notification-card{{cursor:pointer;transition:transform .15s,box-shadow .15s}}
.notification-card:hover{{transform:translateY(-2px);box-shadow:0 4px 12px rgba(0,0,0,.12)}}
.announce h4{{margin-bottom:5px;color:#087c72}}
.announce small{{color:#5f7f78}}
.ann-actions{{position:absolute;top:10px;right:10px;display:flex;gap:6px}}
.badge{{background:#ff4d4d;color:#fff;font-size:12px;font-weight:800;padding:3px 8px;border-radius:20px}}
table{{width:100%;border-collapse:collapse;margin-top:10px}}
th,td{{padding:12px 10px;text-align:left;border-bottom:1px solid #eee;font-size:14px}}
th{{background:linear-gradient(90deg,#087c72,#11c6a6);color:#fff}}
.report-item{{border-left:4px solid #11c6a6;padding:15px;margin-bottom:15px;background:#e8f9f1;border-radius:8px}}
.cancel-btn{{background:#d8f4e9;color:#17594f;padding:10px 20px;border:none;border-radius:10px;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}}
.status-pending{{color:#ff9800;font-weight:bold}}
.status-processing{{color:#2196f3;font-weight:bold}}
.status-done{{color:#4caf50;font-weight:bold}}
.status-cancelled{{color:#b42318;font-weight:bold}}
.scanner-tabs{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:15px}}
.scan-tab{{padding:10px 16px;border:1px solid #bfe9db;border-radius:10px;background:#e8f9f1;cursor:pointer;font-weight:700}}
.scan-tab.active{{background:#11c6a6;color:#fff;border-color:#11c6a6}}
.scanner-panel{{padding:15px;border:1px solid #ccebe1;border-radius:15px;background:rgba(245,255,250,.88)}}
.scanner-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.scanner-grid label{{display:block;margin:8px 0 5px;font-weight:700;color:#164d4b}}
.scanner-grid input,.scanner-grid select{{width:100%;padding:11px;border:1px solid #bfe9db;border-radius:8px;margin-bottom:8px;background:#f7fffb}}
.scanner-video{{width:100%;height:260px;background:#111;border-radius:12px;object-fit:cover}}
.scanner-actions{{display:flex;gap:8px;margin:8px 0}}
.scan-status{{font-size:13px;color:#666;margin-top:8px}}
.scan-feedback{{padding:12px 16px;border-radius:12px;margin:10px 0;font-weight:700}}
.scan-success{{background:#dcfce7;border-left:5px solid #16a34a!important;color:#166534}}
.scan-error{{background:#fee2e2;border-left:5px solid #dc2626!important;color:#991b1b}}
.scan-status.scan-success{{display:inline-block;padding:8px 10px;border-radius:8px;background:#dcfce7;color:#166534}}
.scan-status.scan-error{{display:inline-block;padding:8px 10px;border-radius:8px;background:#fee2e2;color:#991b1b}}
@media(max-width:800px){{.scanner-grid{{grid-template-columns:1fr}}}}
</style>
</head>
<body>
<button type="button" id="menuToggle" class="menu-toggle" aria-label="Open menu" aria-expanded="false" title="Open menu"><span></span><span></span><span></span></button>
<div id="menuBackdrop" class="menu-backdrop"></div>
<div class="sidebar" id="appSidebar">
<div class="sidebar-brand"><div class="brand-mark">🎓</div><div><div class="brand-title">SLSU-JGE</div><div class="brand-subtitle">STUDENT PORTAL</div></div></div>
<div class="menu-section-label">MAIN MENU</div>
{get_sidebar(active_page)}
</div>
<div class="main">
<div class="dashboard-crumb">Pages&nbsp; / &nbsp;<b>{page_title}</b></div>
<div class="header">
<div style="display:flex;align-items:center;gap:12px"><img src="/logo.png" alt="SLSU Logo"><div class="header-text"><h1>{page_title}</h1><p>Welcome, {user_data.get('complete_name', 'Guest')}!</p></div></div>
<div class="header-user"><div class="header-avatar">{(user_data.get('complete_name') or 'U')[:2].upper()}</div><div><div class="header-user-name">{user_data.get('complete_name', 'User')}</div><div class="header-user-role">{user_data.get('role', '').replace('_', ' ').title()}</div></div></div>
</div>
{content}
</div>
<div id="contextMenu" style="position:absolute;background:#fff;box-shadow:0 4px 12px rgba(0,0,0,0.15);border-radius:8px;min-width:180px;z-index:1000;display:none">
  <a href="#" id="menuEdit" style="display:block;padding:10px 15px;color:#333;text-decoration:none">✏️ Edit Information</a>
  <a href="#" id="menuDelete" style="display:block;padding:10px 15px;color:#ff4d4d;text-decoration:none">🗑️ Delete Account</a>
</div>
<script>
// Keep the navigation toggle isolated from page-specific scripts so it remains
// usable even if another office page has a JavaScript error.
(() => {{
  const sidebar = document.getElementById('appSidebar');
  const toggle = document.getElementById('menuToggle');
  const backdrop = document.getElementById('menuBackdrop');
  if (!sidebar || !toggle || !backdrop) return;

  const setOpen = (open) => {{
    sidebar.classList.toggle('is-open', open);
    backdrop.classList.toggle('is-open', open);
    toggle.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    toggle.title = open ? 'Close menu' : 'Open menu';
    try {{ localStorage.setItem('slsuMenuOpen', open ? '1' : '0'); }} catch (error) {{}}
  }};

  toggle.addEventListener('click', () => setOpen(!sidebar.classList.contains('is-open')));
  backdrop.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', (event) => {{
    if (event.key === 'Escape') setOpen(false);
  }});
  let shouldOpen = false;
  try {{ shouldOpen = localStorage.getItem('slsuMenuOpen') === '1'; }} catch (error) {{}}
  setOpen(shouldOpen);
}})();
</script>
<script>
const isAdmin = {is_admin};
let selectedUser = null;
const menu = document.getElementById('contextMenu');
document.addEventListener('contextmenu', function(e) {{
  const row = e.target.closest('tr[data-username]');
  if (row && isAdmin) {{
    e.preventDefault();
    selectedUser = row.dataset.username;
    menu.style.left = e.pageX + 'px';
    menu.style.top = e.pageY + 'px';
    menu.style.display = 'block';
  }}
}});
document.addEventListener('click', function() {{ menu.style.display = 'none'; }});
document.getElementById('menuEdit').onclick = function(e) {{
  e.preventDefault();
  if(selectedUser) window.location.href = '/edit/' + selectedUser;
}};
document.getElementById('menuDelete').onclick = function(e) {{
  e.preventDefault();
  if(selectedUser && confirm('Are you sure you want to delete this account?')) {{
    window.location.href = '/delete/' + selectedUser;
  }}
}};
</script>
</body></html>"""



def office_hero(title, subtitle, icon, metrics):
    html = f'''<section class="office-hero"><div class="office-hero-brand"><img src="/logo.png" alt="SLSU logo"></div><div class="office-hero-copy"><span class="office-kicker">SLSU-JGE · OFFICE WORKSPACE</span><h2>{icon} {title}</h2><p>{subtitle}</p></div></section><div class="office-metrics">'''
    for metric_icon, label, value, tone in metrics:
        html += f'''<div class="office-metric"><span class="office-metric-icon {tone}">{metric_icon}</span><div><div class="office-metric-label">{label}</div><div class="office-metric-value">{value}</div></div></div>'''
    return html + '</div>'

def render_login(error_msg=None, success_msg=None):
    error_html = f'<p style="color:#ffeb3b;margin-bottom:10px;font-weight:600;text-shadow:0 1px 2px rgba(0,0,0,0.3)">{error_msg}</p>' if error_msg else ""
    success_html = f'<p style="color:#fff;margin-bottom:10px;font-weight:600;text-shadow:0 1px 2px rgba(0,0,0,0.3)">{success_msg}</p>' if success_msg else ""

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLSU-JGE Login</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}}
body{{height:100vh;display:flex;justify-content:center;align-items:center; background: url('/bg.jpg') no-repeat center fixed; background-size: cover; position: relative;}}
body::before{{content:'';position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(135deg, rgba(0,180,126,0.25) 0%, rgba(0,212,170,0.25) 100%);backdrop-filter:blur(3px)}}
.login-container{{width:400px;padding:40px 30px;text-align:center;position:relative;z-index:1}}
.logo-circle{{width:110px;height:110px;border-radius:50%;margin:0 auto 10px;overflow:hidden;box-shadow:0 4px 15px rgba(0,0,0,0.2)}}
.logo-circle img{{width:100%;height:100%;object-fit:cover}}
.campus-name{{color:#fff;font-size:18px;font-weight:700;margin-bottom:25px;letter-spacing:1px;text-shadow:0 2px 4px rgba(0,0,0,0.4)}}
.input-box{{position:relative;margin-bottom:18px}}
.input-box input[type="password"]{{padding-right:52px}}
.password-toggle{{position:absolute;right:14px;top:50%;transform:translateY(-50%);border:0;background:transparent;color:#fff;font-size:18px;cursor:pointer;padding:5px;line-height:1}}
.input-box input{{width:100%;padding:16px 20px;border:none;border-radius:50px;background:rgba(255,255,255,0.25);backdrop-filter:blur(5px);color:#fff;font-size:16px;outline:none;border:1px solid rgba(255,255,255,0.4)}}
.input-box input::placeholder{{color:rgba(255,255,255,0.9)}}
.btn{{width:100%;padding:16px;border:none;border-radius:50px;background:#fff;color:#00695c;font-size:18px;font-weight:800;cursor:pointer;margin:25px 0;letter-spacing:3px}}
.options{{display:flex;justify-content:space-between;color:#fff;font-size:14px;margin-bottom:10px;font-weight:500;text-shadow:0 1px 2px rgba(0,0,0,0.3)}}
.options a{{color:#fff;text-decoration:none}}
.link{{color:#fff;font-size:14px;text-decoration:underline;margin-top:10px;display:block;text-shadow:0 1px 2px rgba(0,0,0,0.3)}}
</style>
</head>
<body>
<div class="login-container">
<div class="logo-circle"><img src="/logo.png" alt="SLSU Logo"></div>
<h2 class="campus-name">SLSU-JGE TAGKAWAYAN CAMPUS</h2>
{error_html}
{success_html}
<form action="/login" method="POST">
<div class="input-box"><input type="text" name="username" placeholder="Username" required></div>
<div class="input-box"><input type="password" name="password" placeholder="Password" required><button class="password-toggle" type="button" aria-label="Show password" title="Show password" onclick="const p=this.parentElement.querySelector('input'); p.type=p.type==='password'?'text':'password'; this.textContent=p.type==='password'?'👁':'🙈'; this.title=p.type==='password'?'Show password':'Hide password';">👁</button></div>
<div class="options"><label><input type="checkbox"> Remember Me</label><a href="#">Forgot Password?</a></div>
<button type="submit" class="btn">LOGIN</button>
</form>
<a href="/signup" class="link">Don't have an account? Sign Up</a>
</div>
</body>
</html>"""


@app.route('/')
def index():
    if get_current_user():
        return redirect('/dashboard')
    return render_login()


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    if username in users and users[username]["password"] == password:
        session["username"] = username
        return redirect('/dashboard')
    elif username in pending_users:
        return render_login(error_msg="Your account is pending for admin approval.")
    else:
        return render_login(error_msg="Invalid Username or Password")


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        complete_name = request.form.get('complete_name', '').strip()
        school_id = request.form.get('school_id', '').strip()
        course = request.form.get('course', '')
        major = request.form.get('major', '')
        if course not in COURSES:
            return redirect('/signup')
        allowed_majors = MAJORS_BY_COURSE.get(course, [])
        if allowed_majors and major not in allowed_majors:
            return redirect('/signup')
        if not allowed_majors and major not in ['', 'N/A']:
            return redirect('/signup')
        if not allowed_majors:
            major = '' 
        year_level = request.form.get('year_level', '')
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if username in users or username in pending_users:
            course_opts = "".join([f'<option value="{c}">{c}</option>' for c in COURSES])
            year_opts = "".join([f'<option value="{y}">{y}</option>' for y in YEAR_LEVELS])

            return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLSU-JGE Sign Up</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}}
body{{height:100vh;display:flex;justify-content:center;align-items:center; background: url('/bg.jpg') no-repeat center fixed; background-size: cover; position: relative;}}
body::before{{content:'';position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(135deg, rgba(0,180,126,0.25) 0%, rgba(0,212,170,0.25) 100%);backdrop-filter:blur(3px)}}
.login-container{{width:400px;padding:40px 30px;text-align:center;position:relative;z-index:1}}
.logo-circle{{width:110px;height:110px;border-radius:50%;margin:0 auto 10px;overflow:hidden}}
.logo-circle img{{width:100%;height:100%;object-fit:cover}}
.campus-name{{color:#fff;font-size:18px;font-weight:700;margin-bottom:20px;letter-spacing:1px;text-shadow:0 2px 4px rgba(0,0,0,0.4)}}
.input-box{{position:relative;margin-bottom:12px}}
.input-box input[type="password"]{{padding-right:48px}}
.password-toggle{{position:absolute;right:13px;top:50%;transform:translateY(-50%);border:0;background:transparent;color:#fff;font-size:17px;cursor:pointer;padding:5px;line-height:1}}
.input-box input,.input-box select{{width:100%;padding:14px;border:none;border-radius:50px;background:rgba(255,255,255,0.25);backdrop-filter:blur(5px);color:#fff;font-size:15px;outline:none;border:1px solid rgba(255,255,255,0.4);text-align:center}}
.input-box input::placeholder{{color:rgba(255,255,255,0.8)}}
.input-box select option{{color:#222;background:#fff}}
.btn{{width:100%;padding:14px;border:none;border-radius:50px;background:#fff;color:#00695c;font-size:16px;font-weight:700;cursor:pointer;margin-bottom:10px}}
.link{{color:#fff;font-size:14px;text-decoration:underline;text-shadow:0 1px 2px rgba(0,0,0,0.3)}}
.error{{color:#ffeb3b;margin-bottom:10px;font-weight:600;text-shadow:0 1px 2px rgba(0,0,0,0.3)}}
</style>
</head>
<body>
<div class="login-container">
<div class="logo-circle"><img src="/logo.png" alt="SLSU Logo"></div>
<h2 class="campus-name">SLSU-JGE SIGN UP</h2>
<p class="error">Username already exists!</p>
<form action="/signup" method="POST">
<div class="input-box"><input type="text" name="complete_name" placeholder="Ex. Dela Cruz, Juan T." required></div>
<div class="input-box"><input type="text" name="school_id" placeholder="School ID" required></div>
<div class="input-box">
<select name="course" required>
<option value="" disabled selected>Select Course</option>{course_opts}
</select>
</div>
<div class="input-box">
<select name="major" required disabled>
<option value="" disabled selected>Select Major</option>
</select>
</div>
<div class="input-box">
<select name="year_level" required>
<option value="" disabled selected>Select Year Level</option>{year_opts}
</select>
</div>
<div class="input-box"><input type="text" name="username" placeholder="Create Username" required></div>
<div class="input-box"><input type="password" name="password" placeholder="Create Password" required><button class="password-toggle" type="button" aria-label="Show password" title="Show password" onclick="const p=this.parentElement.querySelector('input'); p.type=p.type==='password'?'text':'password'; this.textContent=p.type==='password'?'👁':'🙈'; this.title=p.type==='password'?'Show password':'Hide password';">👁</button></div>
<button type="submit" class="btn">SUBMIT FOR APPROVAL</button>
</form>
<a href="/" class="link">Already have an account? Login</a>
</div>
<script>
const majorsByCourse = {json.dumps(MAJORS_BY_COURSE)};
const courseSelect = document.querySelector('select[name="course"]');
const majorSelect = document.querySelector('select[name="major"]');
courseSelect.addEventListener('change', () => {{
    majorSelect.innerHTML = '<option value="" disabled selected>Select Major</option>';
    (majorsByCourse[courseSelect.value] || []).forEach(major => {{
        const option = document.createElement('option');
        option.value = major;
        option.textContent = major;
        majorSelect.appendChild(option);
    }});
    majorSelect.disabled = !(majorsByCourse[courseSelect.value] || []).length;
}});
</script>
</body>
</html>"""
        else:
            pending_users[username] = {
                "password": password,
                "complete_name": complete_name,
                "school_id": school_id,
                "course": course,
                "major": major,
                "year_level": year_level,
                "role": "student"
            }
            save_data()
            add_notification(
                "admin",
                f"📥 New account approval request from {complete_name} ({username}).",
                "/pending"
            )
            return render_login(success_msg="Account submitted! Wait for admin approval.")

    course_opts = "".join([f'<option value="{c}">{c}</option>' for c in COURSES])
    year_opts = "".join([f'<option value="{y}">{y}</option>' for y in YEAR_LEVELS])

    return f"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLSU-JGE Sign Up</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}}
body{{height:100vh;display:flex;justify-content:center;align-items:center; background: url('/bg.jpg') no-repeat center fixed; background-size: cover; position: relative;}}
body::before{{content:'';position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(135deg, rgba(0,180,126,0.25) 0%, rgba(0,212,170,0.25) 100%);backdrop-filter:blur(3px)}}
.login-container{{width:400px;padding:40px 30px;text-align:center;position:relative;z-index:1}}
.logo-circle{{width:110px;height:110px;border-radius:50%;margin:0 auto 10px;overflow:hidden}}
.logo-circle img{{width:100%;height:100%;object-fit:cover}}
.campus-name{{color:#fff;font-size:18px;font-weight:700;margin-bottom:20px;letter-spacing:1px;text-shadow:0 2px 4px rgba(0,0,0,0.4)}}
.input-box{{position:relative;margin-bottom:12px}}
.input-box input[type="password"]{{padding-right:48px}}
.password-toggle{{position:absolute;right:13px;top:50%;transform:translateY(-50%);border:0;background:transparent;color:#fff;font-size:17px;cursor:pointer;padding:5px;line-height:1}}
.input-box input,.input-box select{{width:100%;padding:14px;border:none;border-radius:50px;background:rgba(255,255,255,0.25);backdrop-filter:blur(5px);color:#fff;font-size:15px;outline:none;border:1px solid rgba(255,255,255,0.4);text-align:center}}
.input-box input::placeholder{{color:rgba(255,255,255,0.8)}}
.input-box select option{{color:#222;background:#fff}}
.btn{{width:100%;padding:14px;border:none;border-radius:50px;background:#fff;color:#00695c;font-size:16px;font-weight:700;cursor:pointer;margin-bottom:10px}}
.link{{color:#fff;font-size:14px;text-decoration:underline;text-shadow:0 1px 2px rgba(0,0,0,0.3)}}
</style>
</head>
<body>
<div class="login-container">
<div class="logo-circle"><img src="/logo.png" alt="SLSU Logo"></div>
<h2 class="campus-name">SLSU-JGE SIGN UP</h2>
<form action="/signup" method="POST">
<div class="input-box"><input type="text" name="complete_name" placeholder="Ex. Dela Cruz, Juan T." required></div>
<div class="input-box"><input type="text" name="school_id" placeholder="School ID" required></div>
<div class="input-box">
<select name="course" required>
<option value="" disabled selected>Select Course</option>{course_opts}
</select>
</div>
<div class="input-box">
<select name="major" required disabled>
<option value="" disabled selected>Select Major</option>
</select>
</div>
<div class="input-box">
<select name="year_level" required>
<option value="" disabled selected>Select Year Level</option>{year_opts}
</select>
</div>
<div class="input-box"><input type="text" name="username" placeholder="Create Username" required></div>
<div class="input-box"><input type="password" name="password" placeholder="Create Password" required><button class="password-toggle" type="button" aria-label="Show password" title="Show password" onclick="const p=this.parentElement.querySelector('input'); p.type=p.type==='password'?'text':'password'; this.textContent=p.type==='password'?'👁':'🙈'; this.title=p.type==='password'?'Show password':'Hide password';">👁</button></div>
<button type="submit" class="btn">SUBMIT FOR APPROVAL</button>
</form>
<a href="/" class="link">Already have an account? Login</a>
</div>
<script>
const majorsByCourse = {json.dumps(MAJORS_BY_COURSE)};
const courseSelect = document.querySelector('select[name="course"]');
const majorSelect = document.querySelector('select[name="major"]');
courseSelect.addEventListener('change', () => {{
    majorSelect.innerHTML = '<option value="" disabled selected>Select Major</option>';
    (majorsByCourse[courseSelect.value] || []).forEach(major => {{
        const option = document.createElement('option');
        option.value = major;
        option.textContent = major;
        majorSelect.appendChild(option);
    }});
    majorSelect.disabled = !(majorsByCourse[courseSelect.value] || []).length;
}});
</script>
</body>
</html>"""


@app.route('/<office>/add', methods=["POST"])
def add_announcement(office):
    if office not in ["registrar", "guard", "maintenance"]:
        return redirect('/dashboard')
    if not can_manage(office):
        return redirect('/' + office)

    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()

    if title and content:
        announcement_id = len(announcements[office]) + 1
        announcements[office].insert(0, {
            "id": announcement_id,
            "title": title,
            "content": content,
            "author": users[get_current_user()]['complete_name'],
            "date_time": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        })
        save_data()

        # Announcement notifications are sent ONLY to students.
        # The three offices have separate announcement channels.
        office_names = {
            "registrar": "Registrar Office",
            "guard": "Guard Office",
            "maintenance": "Maintenance Office"
        }
        office_roles = {
            "registrar": "registrar_admin",
            "guard": "guard_admin",
            "maintenance": "maintenance_admin"
        }
        office_name = office_names.get(office, office.title())
        office_role = office_roles.get(office)

        student_usernames = [
            username for username, data in users.items()
            if data.get("role") == "student"
        ]

        if student_usernames:
            add_notification(
                student_usernames,
                f"📢 New announcement from {office_name}: {title}",
                f"/{office}",
                office_role
            )

    return redirect('/' + office)


@app.route('/<office>/edit/<int:aid>', methods=["POST"])
def edit_announcement(office, aid):
    if office not in ["registrar", "guard", "maintenance"]:
        return redirect('/dashboard')
    if not can_manage(office):
        return redirect('/' + office)

    for ann in announcements[office]:
        if ann["id"] == aid:
            ann["title"] = request.form.get('title', '').strip()
            ann["content"] = request.form.get('content', '').strip()
            save_data()
            break

    return redirect('/' + office)


@app.route('/<office>/delete/<int:aid>')
def delete_announcement(office, aid):
    if office not in ["registrar", "guard", "maintenance"]:
        return redirect('/dashboard')
    if not can_manage(office):
        return redirect('/' + office)

    announcements[office] = [a for a in announcements[office] if a["id"] != aid]
    save_data()
    return redirect('/' + office)


@app.route('/submit-request', methods=["POST"])
def submit_request():
    uname = get_current_user()
    if not uname:
        return redirect('/')
    if users.get(uname, {}).get("role") != "student":
        return redirect('/registrar')

    doc_type = request.form.get('document_type', '')
    purpose = request.form.get('purpose', '').strip()
    cor_file = request.files.get('cor_file')

    # CTC requires a COR file.
    if doc_type == "ctc":
        if not cor_file or not cor_file.filename:
            return redirect('/registrar?error=missing_cor')
        if not allowed_file(cor_file.filename):
            return redirect('/registrar?error=invalid_cor')

    grade_year = request.form.get('grade_year', '') if doc_type == 'grades' else None
    grade_sem = request.form.get('grade_sem', '') if doc_type == 'grades' else None

    if doc_type == "grades" and (not grade_year or not grade_sem):
        return redirect('/registrar?error=missing_grade_fields')

    if doc_type not in ["grades", "tor", "ctc"] or not purpose:
        return redirect('/registrar')

    user_data = users[uname]
    saved_major = str(user_data.get("major") or "").strip()
    if saved_major in {"-", "N/A", "None"}:
        saved_major = ""

    major_course = get_major_course_key(user_data.get("course"))
    allowed_majors = MAJORS_BY_COURSE.get(major_course, [])
    if allowed_majors and user_data.get("role") == "student" and not saved_major:
        submitted_major = request.form.get("major", "").strip()
        if submitted_major not in allowed_majors:
            return redirect('/registrar?error=missing_major')
        saved_major = submitted_major
        user_data["major"] = saved_major
        save_data()
    elif not allowed_majors:
        saved_major = ""

    new_request = {
        "id": len(grade_requests) + 1,
        "student_name": user_data.get('complete_name'),
        "school_id": user_data.get('school_id'),
        "course": user_data.get('course'),
        "department": user_data.get('course'),
        "major": saved_major,
        "year_level": user_data.get('year_level'),
        "document_type": doc_type,
        "purpose": purpose,
        "status": "Pending",
        "requested_by": uname,
        "requested_at": datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    }

    if doc_type == "grades":
        new_request["grade_year"] = grade_year
        new_request["grade_sem"] = grade_sem

    # Save the COR file attached to a CTC request.
    if doc_type == "ctc" and cor_file and cor_file.filename:
        original_name = secure_filename(cor_file.filename)
        stored_name = f"ctc_{new_request['id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{original_name}"
        cor_file.save(os.path.join(UPLOAD_FOLDER, stored_name))
        new_request["cor_file"] = stored_name
        new_request["cor_original_name"] = original_name

    grade_requests.append(new_request)
    save_data()

    add_notification(
        ["admin", "registrar_admin"],
        f"📄 New document request from {user_data.get('complete_name')} — {doc_type.upper()} (Request #{new_request['id']}).",
        "/registrar", "registrar_admin", f"request-{new_request['id']}-submitted-office"
    )
    add_notification(
        uname,
        f"✅ Your {doc_type.upper()} request (Request #{new_request['id']}) was submitted to the Registrar Office.",
        "/registrar", "registrar_admin", f"request-{new_request['id']}-submitted-student"
    )

    return redirect('/registrar?success=1')


@app.route('/update-request/<int:req_id>/<status>')
def update_request(req_id, status):
    if not can_view_requests():
        return redirect('/registrar')

    if status not in ["Pending", "Processing", "Ready", "Completed"]:
        return redirect('/registrar')

    for req in grade_requests:
        if req["id"] == req_id:
            if req.get("status", "Pending") == "Cancelled":
                return redirect('/registrar')
            previous_status = req.get("status", "Pending")
            if previous_status == status:
                break
            req["status"] = status
            save_data()

            requested_by = req.get("requested_by")
            if requested_by in users:
                add_notification(
                    requested_by,
                    f"Request #{req_id}: {req.get('document_type', '').upper()} status updated to {status}.",
                    "/registrar",
                    "registrar_admin",
                    f"request-{req_id}-status-{status}"
                )
            break

    return redirect('/registrar')


@app.route('/delete-request/<int:req_id>')
def delete_request(req_id):
    if not can_view_requests():
        return redirect('/registrar')

    grade_requests[:] = [r for r in grade_requests if r["id"] != req_id]
    save_data()
    return redirect('/registrar')


@app.route('/cancel-request/<int:req_id>', methods=['POST'])
def cancel_request(req_id):
    uname = get_current_user()
    if not uname:
        return redirect('/')

    for req in grade_requests:
        if req.get("id") == req_id and req.get("requested_by") == uname:
            if req.get("status", "Pending") != "Pending":
                return redirect('/registrar?error=cancel_not_allowed')
            req["status"] = "Cancelled"
            save_data()
            add_notification(
                ["admin", "registrar_admin"],
                f"Kinansela ni {users[uname].get('complete_name', uname)} ang {req.get('document_type', '').upper()} request.",
                "/registrar"
            )
            return redirect('/registrar?cancelled=1')

    return redirect('/registrar')


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    uname = get_current_user()
    if not uname:
        return redirect('/')

    role = users.get(uname, {}).get("role")
    if role not in ["admin", "registrar_admin", "maintenance_admin", "student"]:
        return redirect('/dashboard')

    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/registrar')
def registrar():
    uname = get_current_user()
    if not uname:
        return redirect('/')

    user_data = users[uname]
    role = user_data.get("role")
    if role not in ["admin", "registrar_admin", "student"]:
        return redirect('/dashboard')

    can_edit = can_manage("registrar")
    can_see_all = can_view_requests()
    success_msg = request.args.get('success') == '1'
    request_error = request.args.get('error', '')
    cancelled_msg = request.args.get('cancelled') == '1'

    anns = announcements["registrar"]
    department_value = html_escape(str(user_data.get("course") or "-"), quote=True)
    saved_major = str(user_data.get("major") or "").strip()
    if saved_major in {"-", "N/A", "None"}:
        saved_major = ""
    major_course = get_major_course_key(user_data.get("course"))
    major_options = MAJORS_BY_COURSE.get(major_course, [])
    major_group_html = ""
    if major_options:
        if saved_major in major_options:
            major_field_html = f'<input type="text" value="{html_escape(saved_major, quote=True)}" readonly style="background:#e7f8f0;color:#17675e;font-weight:600">'
        else:
            major_option_html = ''.join(f'<option value="{html_escape(option, quote=True)}">{html_escape(option)}</option>' for option in major_options)
            major_field_html = f'<select name="major" required style="background:#e7f8f0;color:#17675e"><option value="">-- Select Major --</option>{major_option_html}</select>'
        major_group_html = f'<div class="form-group"><label>Major:</label>{major_field_html}</div>'
    content = office_hero("Registrar Office", "Document services, student requests, and registrar announcements.", "📄", [("▤", "Document Requests", len(grade_requests), "sage"), ("◷", "Office Announcements", len(anns), "gold"), ("✓", "Accepted Formats", "PDF · JPG · PNG", "")]) + '<div class="card"><h2>📢 Announcements</h2>' 

    if can_edit:
        content += '''
<form method="POST" action="/registrar/add" class="form-group">
<div class="form-group"><label>Title</label><input name="title" required></div>
<div class="form-group"><label>Content / Announcement</label><textarea name="content" rows="4" required></textarea></div>
<button type="submit" class="submit-btn">➕ Post Announcement</button>
</form>
'''

    if not anns:
        content += '<p>No announcements yet.</p>'
    else:
        for a in anns:
            content += f'''
<div class="announce">
<h4>{a['title']}</h4>
<p>{a['content']}</p>
<small>Posted by: {a['author']}</small>
'''
            if can_edit:
                content += f'''
<div class="ann-actions">
<form method="POST" action="/registrar/edit/{a['id']}" style="display:inline">
<input name="title" value="{a['title']}" style="width:150px;padding:4px">
<input name="content" value="{a['content']}" style="width:200px;padding:4px">
<button type="submit" class="edit-btn">✏️ Save</button>
</form>
<a href="/registrar/delete/{a['id']}" class="delete-btn" onclick="return confirm('Are you sure you want to delete this?')">🗑️ Delete</a>
</div>
'''
            content += '</div>'

    content += '</div>'

    content += '<!-- STUDENT_REQUEST_FORM_START --><div class="card"><h2>📄 Request Document</h2>'

    if success_msg:
        content += '<p style="color:green;font-weight:bold;">✅ Request submitted successfully!</p>'
    elif request_error == "missing_cor":
        content += '<p style="color:#d32f2f;font-weight:bold;">⚠️ A COR upload is required for CTC.</p>'
    elif request_error == "invalid_cor":
        content += '<p style="color:#d32f2f;font-weight:bold;">⚠️ Invalid file. COR must be PDF, JPG, JPEG, or PNG.</p>'
    elif request_error == "missing_major":
        content += '<p style="color:#d32f2f;font-weight:bold;">⚠️ Please select your major. It will be saved to your profile for future requests.</p>'

    content += '''
<form method="POST" action="/submit-request" class="form-group" id="requestForm" enctype="multipart/form-data">
<div class="form-group">
<label>Select Document:</label>
<select name="document_type" id="docType" required onchange="toggleGradeFields()">
<option value="">-- Select Document --</option>
<option value="grades">📊 Copy of Grades</option>
<option value="tor">📑 Transcript of Records (TOR)</option>
<option value="ctc">📋 Certified True Copy (CTC)</option>
</select>
</div>
<div class="form-group">
<label>Department / Course:</label>
<input type="text" value="__REQUEST_DEPARTMENT__" readonly style="background:#e7f8f0;color:#17675e;font-weight:600">
</div>
__REQUEST_MAJOR_GROUP__

<div id="gradeExtraFields" style="display:none; padding-left:10px; border-left:3px solid #11c6a6; margin:10px 0;">
<div class="form-group">
<label>Year Level:</label>
<select name="grade_year" id="grade_year">
<option value="">-- Select Year Level --</option>
<option value="1st Year">1st Year</option>
<option value="2nd Year">2nd Year</option>
<option value="3rd Year">3rd Year</option>
<option value="4th Year">4th Year</option>
</select>
</div>
<div class="form-group">
<label>Semester:</label>
<select name="grade_sem" id="grade_sem">
<option value="">-- Select Semester --</option>
<option value="1st Sem">1st Semester</option>
<option value="2nd Sem">2nd Semester</option>

</select>
</div>
</div>

<div id="corFileField" style="display:none; padding:12px; border-left:3px solid #11c6a6; margin:10px 0; background:#e8f9f1; border-radius:8px;">
<div class="form-group">
<label>📎 Add File — COR (Certificate of Registration):</label>
<input type="file" name="cor_file" id="cor_file" accept=".pdf,.jpg,.jpeg,.png">
<small style="display:block;margin-top:5px;color:#666;">Required for CTC. Accepted: PDF, JPG, JPEG, PNG.</small>
</div>
</div>

<div class="form-group">
<label>Purpose:</label>
<textarea name="purpose" id="purposeField" rows="3" placeholder="Enter the purpose of this document request..." required></textarea>
</div>
<button type="submit" class="submit-btn">📤 Submit Request</button>
</form>

<script>
function toggleGradeFields() {
  const docType = document.getElementById('docType').value;
  const extraDiv = document.getElementById('gradeExtraFields');
  const yearField = document.getElementById('grade_year');
  const semField = document.getElementById('grade_sem');
  const corDiv = document.getElementById('corFileField');
  const corFile = document.getElementById('cor_file');

  if (docType === 'ctc') {
    corDiv.style.display = 'block';
    corFile.required = true;
  } else {
    corDiv.style.display = 'none';
    corFile.required = false;
    corFile.value = '';
  }

  if (docType === 'grades') {
    extraDiv.style.display = 'block';
    yearField.required = true;
    semField.required = true;
  } else {
    extraDiv.style.display = 'none';
    yearField.required = false;
    semField.required = false;
    yearField.value = '';
    semField.value = '';
  }
}
</script>
</div><!-- STUDENT_REQUEST_FORM_END -->'''
    if role != "student":
        start = content.find('<!-- STUDENT_REQUEST_FORM_START -->')
        end_marker = '<!-- STUDENT_REQUEST_FORM_END -->'
        end = content.find(end_marker, start)
        if start != -1 and end != -1:
            content = content[:start] + content[end + len(end_marker):]
    content = content.replace('__REQUEST_DEPARTMENT__', department_value).replace('__REQUEST_MAJOR_GROUP__', major_group_html)

    doc_labels = {
        "grades": "Copy of Grades",
        "tor": "Transcript of Records",
        "ctc": "Certified True Copy"
    }

    if can_see_all:
        content += '<div class="card"><h2>📋 All Requests (Admin Only)</h2>'

        if not grade_requests:
            content += '<p>No requests received.</p>'
        else:
            content += '''<table>
<tr>
<th>Student Name</th>
<th>Request Date &amp; Time</th>
<th>School ID</th>
<th>Department / Course</th>
<th>Major</th>
<th>Document</th>
<th>Details</th>
<th>Purpose</th>
<th>Status</th>
<th>Action</th>
</tr>'''

            for req in reversed(grade_requests):
                doc_label = doc_labels.get(req["document_type"], req["document_type"])

                if req["document_type"] == "grades":
                    details = f"{req.get('grade_year', '-')} | {req.get('grade_sem', '-')}"
                elif req["document_type"] == "ctc" and req.get("cor_file"):
                    details = f'<a href="/uploads/{req["cor_file"]}" target="_blank" class="edit-btn">📎 View COR</a>'
                else:
                    details = "-"

                status_class = {
                    "Pending": "status-pending",
                    "Processing": "status-processing",
                    "Ready": "status-done",
                    "Completed": "status-done"
                }.get(req["status"], "")

                content += f'''<tr>
<td>{req["student_name"]}</td>
<td>{req.get("requested_at", "-")}</td>
<td>{req["school_id"]}</td>
<td>{req.get("department", req.get("course", "-"))}</td>
<td>{req.get("major", "-") or "-"}</td>
<td>{doc_label}</td>
<td>{details}</td>
<td>{req["purpose"]}</td>
<td class="{status_class}">{req["status"]}</td>
<td>
<a href="/update-request/{req['id']}/Processing" class="edit-btn">Processing</a>
<a href="/update-request/{req['id']}/Ready" class="approve-btn">Ready</a>
<a href="/update-request/{req['id']}/Completed" class="submit-btn">Done</a>
<a href="/delete-request/{req['id']}" class="delete-btn" onclick="return confirm('Are you sure you want to delete this?')">🗑️</a>
</td>
</tr>'''

            content += '</table>'

        content += '</div>'

    else:
        content += '<div class="card"><h2>📋 My Requests</h2>'
        if cancelled_msg:
            content += '<p style="color:#b42318;font-weight:bold;">✅ Your request has been cancelled.</p>'
        elif request_error == "cancel_not_allowed":
            content += '<p style="color:#d32f2f;font-weight:bold;">This request can no longer be cancelled because it has been processed.</p>'

        my_reqs = [r for r in grade_requests if r["requested_by"] == uname]

        if not my_reqs:
            content += '<p>You have no requests yet.</p>'
        else:
            major_header = '<th>Major</th>' if major_options else ''
            content += f'''<table>
<tr>
<th>Document</th>
<th>Request Date &amp; Time</th>
<th>Department / Course</th>
{major_header}
<th>Details</th>
<th>Purpose</th>
<th>Status</th>
<th>Action</th>
</tr>'''

            for req in reversed(my_reqs):
                doc_label = doc_labels.get(req["document_type"], req["document_type"])

                if req["document_type"] == "grades":
                    details = f"{req.get('grade_year', '-')} | {req.get('grade_sem', '-')}"
                elif req["document_type"] == "ctc" and req.get("cor_file"):
                    details = f'<a href="/uploads/{req["cor_file"]}" target="_blank" class="edit-btn">📎 View COR</a>'
                else:
                    details = "-"

                status_class = {
                    "Pending": "status-pending",
                    "Processing": "status-processing",
                    "Ready": "status-done",
                    "Completed": "status-done",
                    "Cancelled": "status-cancelled"
                }.get(req["status"], "")

                major_cell = f'<td>{req.get("major", "-") or "-"}</td>' if major_options else ''
                cancel_action = (
                    f'<form method="POST" action="/cancel-request/{req["id"]}" onsubmit="return confirm(\'Cancel this document request?\')" style="margin:0"><button type="submit" class="delete-btn">Cancel</button></form>'
                    if req.get("status", "Pending") == "Pending" else '-'
                )

                content += f'''<tr>
<td>{doc_label}</td>
<td>{req.get("requested_at", "-")}</td>
<td>{req.get("department", req.get("course", "-"))}</td>
{major_cell}
<td>{details}</td>
<td>{req["purpose"]}</td>
<td class="{status_class}">{req["status"]}</td>
<td>{cancel_action}</td>
</tr>'''

            content += '</table>'

        content += '</div>'

    return dashboard_template(content, "registrar", "Registrar Office")


@app.route('/guard/log', methods=['POST'])
def guard_log():
    uname = get_current_user()
    if not uname or not can_manage("guard"):
        return redirect('/guard')
    scan_type = request.form.get('scan_type', '').strip().lower()
    if scan_type not in ['id', 'vehicle', 'manual']:
        return redirect('/guard')
    school_id = request.form.get('school_id', '').strip()
    vehicle_plate = request.form.get('vehicle_plate', '').strip().upper()
    visitor_name = request.form.get('visitor_name', '').strip()
    purpose = request.form.get('purpose', '').strip()
    # Guard Office records entries only; clients cannot submit OUT events.
    direction = 'IN'
    student_name = course = year_level = ''
    matched_student = None

    # Resolve scanned QR data against approved/registered students.
    # Student QR JSON with both name and school_id must match both fields.
    qr_identity = None
    if school_id:
        raw_scan = school_id.strip()
        candidates = [raw_scan]
        try:
            qr_data = json.loads(raw_scan)
            if isinstance(qr_data, dict):
                qr_school_id = str(qr_data.get('school_id') or qr_data.get('student_id') or qr_data.get('id') or '').strip()
                qr_name = str(qr_data.get('name') or qr_data.get('complete_name') or '').strip()
                if qr_school_id:
                    candidates.append(qr_school_id)
                if qr_name and qr_school_id:
                    qr_identity = (qr_school_id.casefold(), qr_name.casefold())
        except Exception:
            pass

        label_match = re.search(r'(?:school\s*id|student\s*id)\s*[:#-]?\s*([A-Za-z0-9._-]+)', raw_scan, re.I)
        if label_match:
            candidates.append(label_match.group(1).strip())

        normalized_candidates = {c.casefold() for c in candidates if c}
        for username, data in users.items():
            if data.get('role') != 'student':
                continue
            registered_school_id = str(data.get('school_id', '')).strip().casefold()
            registered_name = str(data.get('complete_name', '')).strip().casefold()
            registered_values = {registered_school_id, str(username).strip().casefold(), registered_name}
            if qr_identity:
                is_match = (registered_school_id, registered_name) == qr_identity
            else:
                is_match = bool(normalized_candidates & registered_values)
            if is_match:
                matched_student = data
                school_id = str(data.get('school_id', '')).strip()
                student_name = data.get('complete_name', '')
                course = data.get('course', '')
                year_level = data.get('year_level', '')
                break
    if scan_type == 'id' and not school_id:
        return redirect('/guard?error=missing_id')
    if scan_type == 'id' and not matched_student:
        return redirect('/guard?error=unregistered_id')
    if scan_type == 'vehicle' and school_id and not matched_student:
        return redirect('/guard?error=unregistered_driver')
    if scan_type == 'vehicle' and not vehicle_plate:
        return redirect('/guard?error=missing_vehicle')
    if scan_type == 'manual' and not (visitor_name or school_id or vehicle_plate):
        return redirect('/guard?error=missing_manual')
    log_id = max([x.get('id', 0) for x in guard_logs if isinstance(x, dict)] + [0]) + 1
    guard_logs.insert(0, {
        'id': log_id, 'scan_type': scan_type, 'school_id': school_id,
        'student_name': student_name or visitor_name, 'course': course,
        'year_level': year_level, 'vehicle_plate': vehicle_plate,
        'purpose': purpose, 'direction': direction,
        'guard': guard_on_duty or users[uname].get('complete_name', uname),
        'date_time': datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')
    })
    save_data()
    return redirect('/guard?success=1')


@app.route('/guard/duty', methods=['POST'])
def set_guard_on_duty():
    global guard_on_duty
    if not can_manage("guard"):
        return redirect('/guard')
    guard_name = request.form.get('guard_on_duty', '').strip()
    if not guard_name:
        return redirect('/guard?error=missing_guard')
    guard_on_duty = guard_name[:100]
    save_data()
    return redirect('/guard?duty_saved=1')

@app.route('/guard/delete-log/<int:log_id>')
def guard_delete_log(log_id):
    if not can_manage("guard"):
        return redirect('/guard')
    guard_logs[:] = [x for x in guard_logs if x.get('id') != log_id]
    save_data()
    return redirect('/guard')

@app.route('/guard')
def guard():
    uname = get_current_user()
    if not uname:
        return redirect('/')
    role = users[uname].get("role")
    if role not in ["admin", "guard_admin", "student"]:
        return redirect('/dashboard')
    can_edit = can_manage("guard")
    anns = announcements["guard"]
    success = request.args.get('success') == '1'
    duty_saved = request.args.get('duty_saved') == '1'
    error = request.args.get('error', '')
    unique_vehicles = {str(log.get("vehicle_plate", "")).strip().upper() for log in guard_logs if log.get("vehicle_plate")}
    content = office_hero("Guard Office", "Campus entry monitoring, ID scanning, and access logs.", "🛡️", [("▣", "Registered Students", sum(1 for account in users.values() if account.get("role") == "student"), "sage"), ("◉", "Access Logs", len(guard_logs), "gold"), ("🚗", "Recorded Vehicles", len(unique_vehicles), "clay")]) + '<div class="card"><h2>📢 Announcements</h2>' 
    if can_edit:
        content += '''<form method="POST" action="/guard/add" class="form-group">
<div class="form-group"><label>Title</label><input name="title" required></div>
<div class="form-group"><label>Content / Announcement</label><textarea name="content" rows="4" required></textarea></div>
<button type="submit" class="submit-btn">➕ Post Announcement</button></form>'''
    if not anns:
        content += '<p>No announcements yet.</p>'
    else:
        for a in anns:
            content += f'''<div class="announce"><h4>{a['title']}</h4><p>{a['content']}</p><small>Posted by: {a['author']}</small>'''
            if can_edit:
                content += f"""<div class="ann-actions"><form method="POST" action="/guard/edit/{a['id']}" style="display:inline">
<input name="title" value="{a['title']}" style="width:150px;padding:4px"><input name="content" value="{a['content']}" style="width:200px;padding:4px">
<button type="submit" class="edit-btn">✏️ Save</button></form><a href="/guard/delete/{a['id']}" class="delete-btn" onclick="return confirm('Are you sure you want to delete this?')">🗑️ Delete</a></div>"""
            content += '</div>'
    content += '</div>'

    if can_edit:
        if duty_saved:
            content += '<div class="card" style="color:#087443;font-weight:700">✅ Guard on duty saved.</div>'
        content += f'''<div class="card"><h2>👮 Guard on Duty</h2>
<form method="POST" action="/guard/duty" class="form-group">
<label>Guard on duty:</label>
<input type="text" name="guard_on_duty" value="{html_escape(guard_on_duty, quote=True)}" maxlength="100" placeholder="Enter the guard name" required>
<button type="submit" class="submit-btn">💾 Save Guard on Duty</button>
</form></div>'''
        if success: content += '<div class="card scan-feedback scan-success">✅ Guard log successfully recorded. Entry verified.</div>'
        if error == 'missing_id': content += '<div class="card scan-feedback scan-error">⚠️ Kailangan ang School ID.</div>'
        elif error == 'unregistered_id': content += '<div class="card scan-feedback scan-error">❌ The name and School ID do not match a registered student.</div>'
        elif error == 'missing_vehicle': content += '<div class="card scan-feedback scan-error">⚠️ Kailangan ang vehicle plate/scan value.</div>'
        elif error == 'unregistered_driver': content += '<div class="card scan-feedback scan-error">❌ The driver School ID is not registered or approved.</div>'
        elif error == 'missing_manual': content += '<div class="card scan-feedback scan-error">⚠️ Enter a name, School ID, or vehicle plate.</div>'
        elif error == 'missing_guard': content += '<div class="card scan-feedback scan-error">⚠️ Enter the name of the guard on duty first.</div>'
        content += '''<div class="card"><h2>🛡️ Guard Entry Scanner</h2>
<p style="color:#666;margin-bottom:15px">Scan the student ID or vehicle QR code/barcode. You can also enter the details manually.</p>
<div class="scanner-tabs"><button type="button" class="scan-tab active" onclick="showScanner('idScanner', this)">🪪 ID Scanner</button>
<button type="button" class="scan-tab" onclick="showScanner('vehicleScanner', this)">🚗 Vehicle Scanner</button>
<button type="button" class="scan-tab" onclick="showScanner('manualScanner', this)">⌨️ Manual Input</button></div>
<div id="idScanner" class="scanner-panel"><form method="POST" action="/guard/log" onsubmit="return prepareIdSubmit()"><input type="hidden" name="scan_type" value="id"><div class="scanner-grid"><div>
<label>Camera ID/QR Scanner</label><div id="idQrReader" class="scanner-video"></div><div class="scanner-actions">
<button type="button" class="edit-btn" onclick="startScanner('id')">📷 Start Scanner</button><button type="button" class="delete-btn" onclick="stopScanner('id')">⏹ Stop</button></div></div><div>
<label>Scanned School ID</label><input id="idValue" name="school_id" placeholder="Scan or enter the School ID"><p id="idScanStatus" class="scan-status">Ready to scan ID.</p>
<label>Direction</label><select name="direction"><option value="IN" selected>IN</option></select>

<label>Purpose</label><input name="purpose" placeholder="e.g. Class / Visitor / Official business"><button type="submit" class="submit-btn">✅ Record ID Entry</button></div></div></form></div>
<div id="vehicleScanner" class="scanner-panel" style="display:none"><form method="POST" action="/guard/log" onsubmit="return prepareVehicleSubmit()"><input type="hidden" name="scan_type" value="vehicle"><div class="scanner-grid"><div>
<label>Camera Vehicle QR/Barcode Scanner</label><div id="vehicleQrReader" class="scanner-video"></div><div class="scanner-actions">
<button type="button" class="edit-btn" onclick="startScanner('vehicle')">📷 Start Scanner</button><button type="button" class="delete-btn" onclick="stopScanner('vehicle')">⏹ Stop</button></div>
<p id="vehicleScanStatus" class="scan-status">Point the QR code or barcode at the camera.</p></div><div>
<label>Vehicle Plate / Scan Value</label><input id="vehicleValue" name="vehicle_plate" placeholder="Hal. ABC-1234"><label>School ID ng Driver (optional)</label><input name="school_id" placeholder="Kung registered student">
<label>Direction</label><select name="direction"><option value="IN" selected>IN</option></select><label>Purpose</label><input name="purpose" placeholder="e.g. Student / Faculty / Delivery / Visitor"><button type="submit" class="submit-btn">🚗 Record Vehicle Entry</button></div></div></form></div>
<div id="manualScanner" class="scanner-panel" style="display:none"><form method="POST" action="/guard/log"><input type="hidden" name="scan_type" value="manual"><div class="scanner-grid"><div>
<label>Visitor / Student Name</label><input name="visitor_name" placeholder="Complete name"><label>School ID (optional)</label><input name="school_id" placeholder="School ID"><label>Vehicle Plate (optional)</label><input name="vehicle_plate" placeholder="Vehicle plate"></div><div>
<label>Direction</label><select name="direction"><option value="IN" selected>IN</option></select><label>Purpose</label><input name="purpose" placeholder="Reason for entry"><button type="submit" class="submit-btn">📝 Save Manual Entry</button></div></div></form></div></div>'''
        content += '''<div class="card"><h2>📋 Guard Access Logs</h2><div style="overflow-x:auto"><table><tr><th>Date & Time</th><th>Method</th><th>Name</th><th>School ID</th><th>Vehicle</th><th>Direction</th><th>Purpose</th><th>Guard</th><th>Action</th></tr>'''
        if not guard_logs:
            content += '<tr><td colspan="9" style="text-align:center">No guard logs yet.</td></tr>'
        else:
            method_labels = {'id':'🪪 ID Scan','vehicle':'🚗 Vehicle Scan','manual':'⌨️ Manual'}
            for log in guard_logs[:200]:
                content += f'''<tr><td>{log.get('date_time','-')}</td><td>{method_labels.get(log.get('scan_type'), log.get('scan_type','-'))}</td><td>{log.get('student_name','-') or '-'}</td><td>{log.get('school_id','-') or '-'}</td><td>{log.get('vehicle_plate','-') or '-'}</td><td><b>{log.get('direction','-')}</b></td><td>{log.get('purpose','-') or '-'}</td><td>{log.get('guard','-')}</td><td><a href="/guard/delete-log/{log.get('id')}" class="delete-btn" onclick="return confirm('Are you sure you want to delete this log?')">🗑️</a></td></tr>'''

        content += '''<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
<script>
let qrScanners={id:null,vehicle:null};
function showScanner(id,btn){
  document.querySelectorAll('.scanner-panel').forEach(p=>p.style.display='none');
  document.getElementById(id).style.display='block';
  document.querySelectorAll('.scan-tab').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
}
function setScanStatus(type,message,state='info'){
  const el=document.getElementById(type==='id'?'idScanStatus':'vehicleScanStatus');
  if(!el) return;
  el.textContent=message;
  el.classList.remove('scan-success','scan-error');
  if(state==='success') el.classList.add('scan-success');
  if(state==='error') el.classList.add('scan-error');
}
async function startScanner(type){
  const readerId=type==='id'?'idQrReader':'vehicleQrReader';
  const field=document.getElementById(type==='id'?'idValue':'vehicleValue');
  try{
    await stopScanner(type);
    if(typeof Html5Qrcode==='undefined'){
      setScanStatus(type,'⚠️ The scanner library could not load. Check your internet connection and refresh.','error'); return;
    }
    if(!window.isSecureContext && location.hostname!=='localhost' && location.hostname!=='127.0.0.1'){
      setScanStatus(type,'⚠️ HTTPS is required to use the camera on a network address.','error'); return;
    }
    setScanStatus(type,'📷 Humihingi ng pahintulot sa camera...');
    const scanner=new Html5Qrcode(readerId);
    qrScanners[type]=scanner;
    const config={fps:10,qrbox:{width:250,height:250},aspectRatio:1.777778,rememberLastUsedCamera:true};
    if(typeof Html5QrcodeSupportedFormats!=='undefined'){
      config.formatsToSupport=[Html5QrcodeSupportedFormats.QR_CODE,Html5QrcodeSupportedFormats.CODE_128,Html5QrcodeSupportedFormats.CODE_39,Html5QrcodeSupportedFormats.EAN_13,Html5QrcodeSupportedFormats.EAN_8,Html5QrcodeSupportedFormats.UPC_A,Html5QrcodeSupportedFormats.UPC_E];
    }
    await scanner.start({facingMode:'environment'},config,async(decodedText)=>{
      const value=(decodedText||'').trim();
      if(!value) return;
      field.value=type==='vehicle'?value.toUpperCase():value;
      setScanStatus(type,'✅ Na-scan: '+value);
      await stopScanner(type);
      if(type==='id'){
        setScanStatus(type,'⏳ Verifying name and School ID...');
        document.querySelector('#idScanner form').requestSubmit();
      }
    },()=>{});
    setScanStatus(type,'✅ Camera ready. Scan the student QR code or ID.','success');
  }catch(err){
    await stopScanner(type);
    let message='⚠️ The camera cannot be accessed.';
    if(err&&err.name==='NotAllowedError') message='⚠️ Camera access was denied. Allow it in your browser settings.';
    else if(err&&err.name==='NotFoundError') message='⚠️ No camera was found on this device.';
    else if(err&&err.name==='NotReadableError') message='⚠️ Ginagamit ng ibang app ang camera. Isara muna ito.';
    else if(err) message='⚠️ Scanner error: '+(err.message||err);
    setScanStatus(type,message,'error');
  }
}
async function stopScanner(type){
  const scanner=qrScanners[type]; qrScanners[type]=null;
  if(scanner){try{await scanner.stop();}catch(e){} try{scanner.clear();}catch(e){}}
}
function prepareIdSubmit(){
  const value=document.getElementById('idValue').value.trim();
  if(!value){alert('Scan the Student ID or enter the School ID first.');return false;} return true;
}
function prepareVehicleSubmit(){
  const value=document.getElementById('vehicleValue').value.trim();
  if(!value){alert('Scan the vehicle QR code/barcode or enter the plate number first.');return false;} return true;
}
window.addEventListener('load',()=>{ if(document.getElementById('idQrReader')) startScanner('id'); });
window.addEventListener('beforeunload',()=>{stopScanner('id');stopScanner('vehicle');});
</script>'''
    return dashboard_template(content, "guard", "Guard Office")


@app.route('/maintenance', methods=["GET", "POST"])
def maintenance():
    uname = get_current_user()
    if not uname:
        return redirect('/')

    role = users[uname].get("role")
    if role not in ["admin", "maintenance_admin", "student"]:
        return redirect('/dashboard')

    if request.method == "POST":
        if role != "student":
            return redirect('/maintenance')
        image_file = request.files.get("maintenance_image")
        image_filename = ""
        if image_file and image_file.filename:
            if request.content_length and request.content_length > 5 * 1024 * 1024:
                return redirect('/maintenance?error=image_too_large')
            safe_name = secure_filename(image_file.filename)
            extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
            if extension not in ALLOWED_IMAGE_EXTENSIONS:
                return redirect('/maintenance?error=invalid_image')
            image_filename = f"maintenance_{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
            image_file.save(os.path.join(UPLOAD_FOLDER, image_filename))

        report_id = max([r.get("id", 0) for r in maintenance_reports if isinstance(r, dict)] + [0]) + 1
        maintenance_reports.append({
            'id': report_id,
            'description': request.form.get('description', '').strip(),
            'location': request.form.get('location', '').strip(),
            'reported_by': request.form.get('reported_by', '').strip(),
            'reported_by_user': uname,
            'image': image_filename,
            'status': 'Pending',
            'date_time': datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
        })
        save_data()

        add_notification(
            ["admin", "maintenance_admin"],
            f"🔧 New maintenance report: {request.form.get('description', '').strip()} — {request.form.get('location', '').strip()}",
            "/maintenance",
            "maintenance_admin"
        )

        return redirect('/maintenance')

    can_edit = can_manage("maintenance")
    anns = announcements["maintenance"]
    open_reports = sum(1 for report in maintenance_reports if report.get("status", "Pending") != "Completed")
    completed_reports = sum(1 for report in maintenance_reports if report.get("status") == "Completed")
    content = office_hero("Maintenance Office", "Facility reports, work status, and maintenance announcements.", "⚙️", [("⚙", "Open Reports", open_reports, "clay"), ("✓", "Completed", completed_reports, "sage"), ("📢", "Announcements", len(anns), "gold")]) + '<div class="card"><h2>📢 Announcements</h2>' 

    if can_edit:
        content += '''
<form method="POST" action="/maintenance/add" class="form-group">
<div class="form-group"><label>Title</label><input name="title" required></div>
<div class="form-group"><label>Content / Announcement</label><textarea name="content" rows="4" required></textarea></div>
<button type="submit" class="submit-btn">➕ Post Announcement</button>
</form>
'''

    if not anns:
        content += '<p>No announcements yet.</p>'
    else:
        for a in anns:
            content += f'''
<div class="announce">
<h4>{a['title']}</h4>
<p>{a['content']}</p>
<small>Posted by: {a['author']}</small>
'''
            if can_edit:
                content += f'''
<div class="ann-actions">
<form method="POST" action="/maintenance/edit/{a['id']}" style="display:inline">
<input name="title" value="{a['title']}" style="width:150px;padding:4px">
<input name="content" value="{a['content']}" style="width:200px;padding:4px">
<button type="submit" class="edit-btn">✏️ Save</button>
</form>
<a href="/maintenance/delete/{a['id']}" class="delete-btn" onclick="return confirm('Are you sure you want to delete this?')">🗑️ Delete</a>
</div>
'''
            content += '</div>'

    content += '</div>'

    if role == "student":
        content += """<div class="card"><h2>🔧 Report a Maintenance Issue</h2>
<form method="POST" enctype="multipart/form-data" class="form-group">
<div class="form-group"><label>*Description - Anong sira</label><textarea name="description" rows="3" required></textarea></div>
<div class="form-group"><label>*Location - Saan</label><input type="text" name="location" required></div>
<div class="form-group"><label>*Reported by - Sino ang nagreport</label><input type="text" name="reported_by" required></div>
<div class="form-group"><label>Larawan ng sira (PNG/JPG, hanggang 5 MB)</label><input type="file" name="maintenance_image" accept="image/png,image/jpeg,.png,.jpg,.jpeg"></div>
<button type="submit" class="submit-btn">Submit Report</button>
</form></div>"""

    image_error = request.args.get("error")
    if image_error == "invalid_image":
        content = '<div class="card" style="color:#b42318">Unsupported image. Only PNG or JPG files are allowed.</div>' + content
    elif image_error == "image_too_large":
        content = '<div class="card" style="color:#b42318">The image exceeds 5 MB. Choose a smaller file.</div>' + content

    content += '<div class="card"><h2>Submitted Reports</h2>'

    if not maintenance_reports:
        content += "<p>No reports submitted.</p>"
    else:
        for report in reversed(maintenance_reports):
            report_id = report.get("id", 0)
            status = report.get("status", "Pending")
            status_class = {
                "Pending": "status-pending",
                "Processing": "status-processing",
                "Completed": "status-done"
            }.get(status, "")

            actions = ""
            if can_edit:
                actions = f"""
<div style="margin-top:10px">
<a href="/update-maintenance/{report_id}/Processing" class="edit-btn">⚙️ Processing</a>
<a href="/update-maintenance/{report_id}/Completed" class="submit-btn" style="text-decoration:none;display:inline-block;padding:6px 10px;font-size:12px">✅ Done</a>
<a href="/delete-maintenance/{report_id}" class="delete-btn" onclick="return confirm('Are you sure you want to delete this maintenance report?')">🗑️ Delete</a>
</div>"""

            image_html = ""
            image_name = report.get("image", "")
            if image_name:
                image_html = f'<p><b>Larawan:</b><br><a href="/uploads/{html_escape(image_name)}" target="_blank"><img src="/uploads/{html_escape(image_name)}" alt="Larawan ng maintenance issue" style="display:block;max-width:min(100%,420px);max-height:280px;object-fit:contain;margin-top:8px;border-radius:10px;border:1px solid #dce6e3"></a></p>'

            content += f"""<div class="report-item">
<p><b>Issue:</b> {report.get('description', '')}</p>
<p><b>Location:</b> {report.get('location', '')}</p>
<p><b>Reported by:</b> {report.get('reported_by', '')}</p>
{image_html}
<p><b>Date & Time:</b> {report.get('date_time', '-')}</p>
<p><b>Status:</b> <span class="{status_class}">{status}</span></p>
{actions}
</div>"""

    content += "</div>"

    return dashboard_template(content, "maintenance", "Maintenance Office")


@app.route('/update-maintenance/<int:report_id>/<status>')
def update_maintenance(report_id, status):
    if not can_manage("maintenance"):
        return redirect('/maintenance')

    if status not in ["Pending", "Processing", "Completed"]:
        return redirect('/maintenance')

    for report in maintenance_reports:
        if report.get("id") == report_id:
            report["status"] = status
            requested_by = report.get("reported_by_user")
            save_data()

            if requested_by in users:
                add_notification(
                    requested_by,
                    f"🔧 Maintenance report mo ay {status.upper()} na.",
                    "/maintenance",
                    "maintenance_admin"
                )
            break

    return redirect('/maintenance')


@app.route('/delete-maintenance/<int:report_id>')
def delete_maintenance(report_id):
    if not can_manage("maintenance"):
        return redirect('/maintenance')

    maintenance_reports[:] = [
        report for report in maintenance_reports
        if report.get("id") != report_id
    ]
    save_data()
    return redirect('/maintenance')


@app.route('/pending')
def pending():
    uname = get_current_user()
    if not uname or users[uname].get("role") != "admin":
        return redirect('/dashboard')

    content = '<div class="card"><h2>Pending Accounts</h2>'

    if not pending_users:
        content += "<p>No pending accounts.</p>"
    else:
        for uname_pend, data in pending_users.items():
            content += f"""<div style='border-bottom:1px solid #eee;padding:10px 0'>
<b>{data['complete_name']}</b> - {data['school_id']}<br>
{data['course']} | {data['year_level']}<br>
Username: {uname_pend}<br>
<a href='/approve/{uname_pend}'><button class='approve-btn'>Approve</button></a>
<a href='/reject/{uname_pend}'><button class='reject-btn'>Reject</button></a>
</div>"""

    content += "</div>"

    return dashboard_template(content, "pending", "Pending Accounts")


@app.route('/approve/<username>')
def approve(username):
    uname = get_current_user()
    if not uname or users[uname].get("role") != "admin":
        return redirect('/dashboard')

    if username in pending_users:
        users[username] = pending_users[username]
        del pending_users[username]
        save_data()

    return redirect('/pending')


@app.route('/reject/<username>')
def reject(username):
    uname = get_current_user()
    if not uname or users[uname].get("role") != "admin":
        return redirect('/dashboard')

    if username in pending_users:
        del pending_users[username]
        save_data()

    return redirect('/pending')


@app.route('/registered')
def registered():
    uname = get_current_user()
    if not uname:
        return redirect('/')

    role = users[uname].get("role")
    if role not in ["admin", "registrar_admin", "guard_admin", "maintenance_admin"]:
        return redirect('/dashboard')

    selected_course = request.args.get('course', 'all')

    course_buttons = '<div style="margin-bottom:20px;display:flex;flex-wrap:wrap;gap:8px;">'
    course_buttons += f'<a href="/registered?course=all"><button style="padding:8px 16px;border:none;border-radius:8px;background:{"#00d4aa" if selected_course=="all" else "#eee"};color:{"#fff" if selected_course=="all" else "#333"};cursor:pointer;font-weight:bold;">All</button></a>'

    for c in COURSES:
        course_buttons += f'<a href="/registered?course={c}"><button style="padding:8px 16px;border:none;border-radius:8px;background:{"#00d4aa" if selected_course==c else "#eee"};color:{"#fff" if selected_course==c else "#333"};cursor:pointer;font-weight:bold;">{c}</button></a>'

    course_buttons += "</div>"

    content = f'<div class="card"><h2>Registered Students</h2>{course_buttons}'
    content += "<p style='margin-bottom:10px;color:#666;font-size:13px;'>💡 Right-click a row (Admin only) to Edit / Delete</p><table><tr><th>School ID</th><th>Complete Name</th><th>Course</th><th>Major</th><th>Year Level</th><th>Username</th><th>Role</th></tr>"

    has_data = False

    for u, data in users.items():
        if data.get("role") == "student":
            if selected_course == "all" or data.get("course") == selected_course:
                has_data = True
                content += f"<tr data-username='{u}'><td>{data['school_id']}</td><td>{data['complete_name']}</td><td>{data['course']}</td><td>{data.get('major', '-')}</td><td>{data['year_level']}</td><td>{u}</td><td>{data['role']}</td></tr>"

    if not has_data:
        content += "<tr><td colspan='7' style='text-align:center;color:#888;padding:15px;'>No students found.</td></tr>"

    content += "</table></div>"

    # Vehicle records are visible only to the main admin and Guard Office.
    if role in ["admin", "guard_admin"]:
        registered_vehicles = {}
        for log in guard_logs:
            plate = (log.get("vehicle_plate") or "").strip().upper()
            if not plate:
                continue
            if plate not in registered_vehicles:
                registered_vehicles[plate] = {
                    "plate": plate,
                    "student_name": log.get("student_name", "") or "-",
                    "school_id": log.get("school_id", "") or "-",
                    "date_time": log.get("date_time", "-")
                }

        content += '<div class="card"><h2>🚗 Registered Vehicles</h2><p style="color:#666;margin-bottom:15px">List of vehicles recorded by the Guard Office.</p><div style="overflow-x:auto"><table><tr><th>Plate Number</th><th>Student / Driver</th><th>School ID</th><th>Last Recorded</th></tr>'
        if not registered_vehicles:
            content += '<tr><td colspan="4" style="text-align:center">No registered or recorded vehicles yet.</td></tr>'
        else:
            for vehicle in registered_vehicles.values():
                content += f"<tr><td><b>{vehicle['plate']}</b></td><td>{vehicle['student_name']}</td><td>{vehicle['school_id']}</td><td>{vehicle['date_time']}</td></tr>"
        content += "</table></div></div>"

    return dashboard_template(content, "registered", "Registered Students")


@app.route('/edit/<username>', methods=["GET", "POST"])
def edit_user(username):
    uname = get_current_user()
    if not uname or users[uname].get("role") != "admin":
        return redirect('/dashboard')

    if username not in users or users[username].get("role") != "student":
        return redirect('/registered')

    if request.method == "POST":
        users[username]['complete_name'] = request.form.get('complete_name', '').strip()
        users[username]['school_id'] = request.form.get('school_id', '').strip()
        users[username]['course'] = request.form.get('course')
        users[username]['major'] = request.form.get('major', users[username].get('major', ''))
        users[username]['year_level'] = request.form.get('year_level')

        if request.form.get('password'):
            users[username]['password'] = request.form.get('password')

        save_data()
        return redirect('/registered')

    data = users[username]

    course_opts = "".join([f'<option value="{c}" {"selected" if data["course"]==c else ""}>{c}</option>' for c in COURSES])
    year_opts = "".join([f'<option value="{y}" {"selected" if data["year_level"]==y else ""}>{y}</option>' for y in YEAR_LEVELS])

    content = f"""<div class="card">
<h2>Edit Information — {username}</h2>
<form method="POST" class="form-group">
<div class="form-group"><label>Complete Name</label><input name="complete_name" value="{data['complete_name']}" required></div>
<div class="form-group"><label>School ID</label><input name="school_id" value="{data['school_id']}" required></div>
<div class="form-group">
    <label>Course</label>
    <select name="course" required>
        {course_opts}
    </select>
</div>
<div class="form-group">
    <label>Year Level</label>
    <select name="year_level" required>
        {year_opts}
    </select>
</div>
<div class="form-group">
    <label>New Password (leave blank to keep the current password)</label>
    <input type="password" name="password" placeholder="Change password">
</div>
<div style="display:flex;gap:10px;margin-top:20px;">
    <button type="submit" class="submit-btn">💾 Save Changes</button>
    <a href="/registered" class="cancel-btn">❌ Cancel</a>
</div>
</form>
</div>"""

    return dashboard_template(content, "registered", "Edit Student Information")


@app.route('/delete/<username>')
def delete_user(username):
    uname = get_current_user()
    if not uname or users[uname].get("role") != "admin":
        return redirect('/dashboard')

    if username in users and users[username].get("role") == "student":
        del users[username]
        save_data()

    return redirect('/registered')


@app.route('/dashboard')
def dashboard():
    uname = get_current_user()
    if not uname:
        return redirect('/')

    user_data = users[uname]
    role = user_data.get("role")
    student_accounts = [(u, d) for u, d in users.items() if d.get("role") == "student"]
    unread = get_unread_notifications(uname)

    content = '<div class="dashboard-hero">'
    content += '<div class="hero-date">SLSU-JGE • STUDENT INFORMATION SYSTEM</div>'
    content += f'<div class="hero-title">Good day, {user_data.get("complete_name", "User").split()[0]}! 👋</div>'
    if role == "student":
        content += '<div class="hero-subtitle">View your information and request school documents.</div>'
        content += '<a class="hero-link" href="/registrar">📄 &nbsp; Document Requests</a></div>'
    else:
        content += '<div class="hero-subtitle">Track students, requests, and campus activity in one place.</div>'
        content += '<a class="hero-link" href="/registered">▤ &nbsp; View Records</a></div>'

    if role == "admin":
        stats = [
            ("♙", "Total Students", len(student_accounts), "#e2f7f0"),
            ("◷", "Pending Accounts", len(pending_users), "#fff2dc"),
            ("▤", "Document Requests", len(grade_requests), "#e8efff"),
            ("⚙", "Maintenance Reports", len(maintenance_reports), "#ffe9e6")
        ]
    elif role == "registrar_admin":
        stats = [("▤", "Total Students", len(student_accounts), "#e2f7f0"), ("📄", "Document Requests", len(grade_requests), "#e8efff"), ("🔔", "Unread Notifications", len(unread), "#fff2dc"), ("📢", "Registrar Announcements", len(announcements.get("registrar", [])), "#ffe9e6")]
    elif role == "guard_admin":
        stats = [("♙", "Total Students", len(student_accounts), "#e2f7f0"), ("🚗", "Guard Logs", len(guard_logs), "#fff2dc"), ("🔔", "Unread Notifications", len(unread), "#e8efff"), ("📢", "Guard Announcements", len(announcements.get("guard", [])), "#ffe9e6")]
    elif role == "maintenance_admin":
        stats = [("⚙", "Maintenance Reports", len(maintenance_reports), "#ffe9e6"), ("🔔", "Unread Notifications", len(unread), "#fff2dc"), ("📢", "Announcements", len(announcements.get("maintenance", [])), "#e2f7f0"), ("♙", "Total Students", len(student_accounts), "#e8efff")]
    else:
        stats = [("📚", "Course", user_data.get("course", "-"), "#e2f7f0"), ("🎓", "Year Level", user_data.get("year_level", "-"), "#e8efff"), ("🔔", "Unread Notifications", len(unread), "#fff2dc"), ("📋", "Document Requests", sum(1 for r in grade_requests if r.get("student_name") == user_data.get("complete_name")), "#ffe9e6")]

    stat_links = {
        "Total Students": "/registered",
        "Pending Accounts": "/pending",
        "Document Requests": "/registrar",
        "Maintenance Reports": "/maintenance",
        "Guard Logs": "/guard",
        "Guard Announcements": "/guard",
        "Registrar Announcements": "/registrar",
        "Announcements": {"maintenance_admin": "/maintenance"}.get(role, "/dashboard"),
        "Unread Notifications": "/notifications",
        "Course": "/profile",
        "Year Level": "/profile"
    }
    content += '<div class="dashboard-stats">'
    for icon, label, value, color in stats:
        stat_href = stat_links.get(label, "/dashboard")
        content += f'<a class="stat-card-link" href="{stat_href}"><div class="stat-card"><div class="stat-top"><span class="stat-icon" style="background:{color}">{icon}</span><span>{label}</span></div><div class="stat-number">{value}</div></div></a>'
    content += '</div><div class="dashboard-columns"><div>'

    course_counts = {course: sum(1 for _, student in student_accounts if student.get("course") == course) for course in COURSES}
    max_count = max(course_counts.values(), default=0) or 1
    content += '<div class="card"><h2>Student Overview</h2><p style="font-size:11px;color:#829597;margin-top:-7px">Enrollment snapshot by course</p><div class="course-chart">'
    for index, (course, count) in enumerate(course_counts.items()):
        height = max(5, round(count / max_count * 130))
        bar_color = "#0ba88f" if index % 2 else "#65cbb3"
        content += f'<div class="course-bar-wrap"><span>{count}</span><div class="course-bar" style="height:{height}px;background:{bar_color}"></div><span>{course}</span></div>'
    content += '</div></div>'

    if role != "student":
        recent_students = list(reversed(student_accounts))[:5]
        content += '<div class="card"><h2>Recently Registered Students</h2><div class="dashboard-table"><table><tr><th>STUDENT</th><th>SCHOOL ID</th><th>COURSE / MAJOR</th><th>YEAR</th></tr>'
        if recent_students:
            for _, student in recent_students:
                content += f'<tr><td>{student.get("complete_name", "-")}</td><td>{student.get("school_id", "-")}</td><td>{student.get("course", "-")} · {student.get("major", "-")}</td><td>{student.get("year_level", "-")}</td></tr>'
        else:
            content += '<tr><td colspan="4" style="text-align:center;color:#829597">No students registered yet.</td></tr>'
        content += '</table></div>'
    content += '</div></div><div><div class="card"><h2>Announcements</h2>'

    role_office = {"registrar_admin": "registrar", "guard_admin": "guard", "maintenance_admin": "maintenance"}.get(role)
    notice_list = announcements.get(role_office, []) if role_office else [item for office_items in announcements.values() if isinstance(office_items, list) for item in office_items]
    if notice_list:
        for notice in list(reversed(notice_list))[:4]:
            content += f'<div class="dashboard-notice"><div class="dashboard-notice-title">📢 {notice.get("title", "Announcement")}</div><div class="dashboard-notice-text">{notice.get("content", "")}</div></div>'
    else:
        content += '<div class="dashboard-notice"><div class="dashboard-notice-title">📢 No announcements yet</div><div class="dashboard-notice-text">The latest updates from the campus office will appear here.</div></div>'

    content += '</div><div class="card"><h2>Notifications</h2>'
    if unread:
        for notice in unread[:4]:
            content += f'<div class="dashboard-notice"><div class="dashboard-notice-title">🔔 {notice.get("message", "Update")}</div><small class="notification-date">{notice.get("date_time", "-")}</small><br><a href="/notification/{notice.get("id", 0)}" style="font-size:10px;color:#0b9e88">Open notification →</a></div>'
    else:
        content += '<div class="dashboard-notice"><div class="dashboard-notice-text">You have no new notifications.</div></div>'
    content += '</div></div></div>'

    return dashboard_template(content, "dashboard", "Dashboard")

@app.route('/notifications')
def notifications_page():
    uname = get_current_user()
    if not uname:
        return redirect('/')

    items = deduplicate_legacy_notifications(notifications.get(uname, []))
    content = '<div class="card"><h2>🔔 Notifications</h2>'

    if not items:
        content += '<p>No notifications yet.</p>'
    else:
        for n in items:
            state = "font-weight:700;" if not n.get("read") else "opacity:0.65;"
            nid = n.get("id", 0)
            content += f'''<div class="announce notification-card" style="{state}">
<a href="/notification/{nid}" class="notification-link"><p><b>{n.get("message", "")}</b></p>
<small>Click the notification to open it.</small></a>
<small class="notification-date">{n.get("date_time", "-")}</small>
<form method="POST" action="/delete-notification/{nid}" style="margin-top:10px" onsubmit="return confirm('Delete this notification?')"><button type="submit" class="delete-btn">Delete</button></form>
</div>'''

    content += '</div>'
    return dashboard_template(content, "notifications", "Notifications")


@app.route('/delete-notification/<int:notification_id>', methods=["POST"])
def delete_notification(notification_id):
    uname = get_current_user()
    if not uname:
        return redirect('/')

    user_items = notifications.get(uname, [])
    notifications[uname] = [item for item in user_items if item.get("id") != notification_id]
    save_data()
    return redirect('/notifications')


@app.route('/notification/<int:notification_id>')
def open_notification(notification_id):
    """Mark one notification as read, then open its target page."""
    uname = get_current_user()
    if not uname:
        return redirect('/')

    user_items = notifications.get(uname, [])
    for n in user_items:
        if n.get("id") == notification_id:
            n["read"] = True
            link = n.get("link") or "/dashboard"
            save_data()
            return redirect(link)

    return redirect('/notifications')


@app.route('/profile')
def profile():
    uname = get_current_user()
    if not uname:
        return redirect('/')

    data = users[uname]
    barcode_html = ""
    if data.get("role") == "student":
        # The guard scanner reads this JSON and verifies both the name and School ID.
        barcode_payload = json.dumps({
            "name": data.get("complete_name", ""),
            "school_id": data.get("school_id", "")
        }, ensure_ascii=False).replace("<", "\\u003c")
        barcode_html = f"""<div class="card student-barcode-card" style="text-align:center">
<h3>🪪 Student QR Barcode</h3>
<p>Show or print this QR code for the Guard to scan.</p>
<div id="studentQrCode" style="display:inline-block;background:#fff;padding:12px;margin:12px auto"></div>
<p><b>{data.get('complete_name')}</b><br>School ID: {data.get('school_id')}</p>
<button type="button" class="submit-btn" onclick="window.print()">🖨️ Print QR Code</button>
<button type="button" class="submit-btn" onclick="downloadStudentQr()">⬇️ Download QR Code</button>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js" crossorigin="anonymous"></script>
<script>
const studentQrPayload = {barcode_payload};
function downloadStudentQr() {{
    const qrContainer = document.getElementById("studentQrCode");
    const canvas = qrContainer.querySelector("canvas");
    const image = qrContainer.querySelector("img");
    const downloadLink = document.createElement("a");
    downloadLink.download = "student-qr-code.png";
    if (canvas) {{
        downloadLink.href = canvas.toDataURL("image/png");
    }} else if (image && image.src) {{
        downloadLink.href = image.src;
    }} else {{
        alert("The QR code is not ready yet. Please wait and try again.");
        return;
    }}
    downloadLink.click();
}}
if (window.QRCode) {{
    new QRCode(document.getElementById("studentQrCode"), {{
        text: JSON.stringify(studentQrPayload), width: 220, height: 220,
        colorDark: "#000000", colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.M
    }});
}} else {{
    document.getElementById("studentQrCode").textContent = "The QR code generator could not load. Try refreshing the page.";
}}
</script>"""

    content = f"""<div class="card">
<h2>👤 My Profile</h2>
<p class="info-row"><b>Name:</b> {data.get('complete_name')}</p>
<p class="info-row"><b>Username:</b> {uname}</p>
<p class="info-row"><b>School ID:</b> {data.get('school_id')}</p>
<p class="info-row"><b>Course:</b> {data.get('course')}</p><p class="info-row"><b>Major:</b> {data.get('major', '-')}</p>
<p class="info-row"><b>Year Level:</b> {data.get('year_level')}</p>
<p class="info-row"><b>Role:</b> {data.get('role', '').replace('_', ' ').title()}</p>
</div>{barcode_html}"""

    return dashboard_template(content, "profile", "My Profile")


def open_in_chrome():
    candidates = [
        os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    chrome = next((path for path in candidates if os.path.isfile(path)), None)
    if chrome:
        subprocess.Popen([chrome, "http://127.0.0.1:5000"])
    else:
        print("Chrome was not found. Open manually: http://127.0.0.1:5000")


if __name__ == '__main__':
    if not os.path.exists('logo.png'):
        print("⚠️  Reminder: Place logo.png in the same folder!")
    if not os.path.exists('bg.jpg'):
        print("⚠️  Reminder: Place bg.jpg in the same folder!")

    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        threading.Timer(1.5, open_in_chrome).start()

    try:
        import cryptography  # Required by Werkzeug for its temporary HTTPS certificate.
        ssl_mode = 'adhoc'
        print('HTTPS enabled. Open: https://127.0.0.1:5000 or https://<computer-IP-address>:5000')
    except ImportError:
        ssl_mode = None
        print('HTTPS certificate dependency is missing. Website will start on HTTP: http://127.0.0.1:5000')
        print('Install cryptography to enable HTTPS for camera access over a LAN: python -m pip install cryptography')

    app.run(debug=True, host='0.0.0.0', port=5000, ssl_context=ssl_mode)