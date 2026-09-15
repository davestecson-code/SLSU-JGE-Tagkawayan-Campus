from flask import Flask, request, render_template_string, redirect, send_from_directory
import os, json

app = Flask(__name__)
DATA_FILE = 'data.json'

def load_data():
    global users, pending_users, maintenance_reports
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            users = data.get('users', {})
            pending_users = data.get('pending_users', {})
            maintenance_reports = data.get('maintenance_reports', []) # BAGONG LIST
    else:
        users = {
            "admin": {
                "password": "1234",
                "school_id": "2022-0001",
                "complete_name": "Admin User",
                "course": "BS Information Technology",
                "year_level": "4th Year",
                "role": "admin"
            }
        }
        pending_users = {}
        maintenance_reports = [] # EMPTY LIST

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump({'users': users, 'pending_users': pending_users, 'maintenance_reports': maintenance_reports}, f, indent=4)

load_data()
current_user = ""

@app.route('/logo.png')
def logo():
    return send_from_directory(os.getcwd(), 'logo.png')

@app.route('/bg.jpg')
def bg():
    return send_from_directory(os.getcwd(), 'bg.jpg')

def get_sidebar(active_page):
    user_data = users.get(current_user, {})
    sidebar_html = ""
    pending_count = len(pending_users)
    if user_data.get("role") == "admin":
        pages = {"dashboard": "Dashboard","pending": "Pending Accounts","registered": "Registered Students","registrar": "Registrar Office","guard": "Guard Office","maintenance": "Maintenance Office","profile": "Profile"} # DINAGDAG
    else:
        pages = {"dashboard": "Dashboard","registrar": "Registrar Office","guard": "Guard Office","maintenance": "Maintenance Office","profile": "Profile"} # DINAGDAG
    for key, name in pages.items():
        active_class = "active" if active_page == key else ""
        badge = f' <span class="badge">{pending_count}*</span>' if key == "pending" and pending_count > 0 else ""
        sidebar_html += f'<a href="/{key}"><button class="menu-btn {active_class}">{name}{badge}</button></a>'
    sidebar_html += '<a href="/"><button class="menu-btn logout">Log Out</button></a>'
    return sidebar_html

def dashboard_template(content, active_page, page_title):
    user_data = users.get(current_user, {})
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLSU-JGE {page_title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}}
body{{height:100vh;display:flex;
background: url('/bg.jpg') no-repeat center fixed; background-size: cover; position: relative;}}
body::before{{content:'';position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(135deg, rgba(0,180,126,0.7) 0%, rgba(0,212,170,0.7) 100%);backdrop-filter:blur(8px)}}
.sidebar{{width:230px;background:rgba(255,255,255,0.15);backdrop-filter:blur(10px);padding:20px;border-radius:0 25px 25px 0;display:flex;flex-direction:column;gap:10px;position:relative;z-index:1}}
.menu-btn{{padding:12px 18px;border:none;border-radius:15px;background:transparent;color:#fff;font-size:15px;font-weight:500;cursor:pointer;text-align:left;width:100%;display:flex;justify-content:space-between;align-items:center}}
.menu-btn.active{{background:#fff;color:#00a67e;font-weight:700}}
.menu-btn:hover{{background:rgba(255,255,255,0.2)}}
.main{{flex:1;padding:30px;position:relative;z-index:1;overflow-y:auto}}
.header{{display:flex;align-items:center;gap:15px;color:#fff;margin-bottom:25px}}
.header img{{width:70px;height:70px;background:#fff;border-radius:50%;padding:5px}}
.header-text h1{{font-size:24px;font-weight:800}}
.header-text p{{font-size:14px}}
.card{{background:rgba(255,255,255,0.95);border-radius:20px;padding:20px;margin-bottom:15px;box-shadow:0 4px 15px rgba(0,0,0,0.1)}}
.card h2{{font-size:16px;color:#333;margin-bottom:10px;font-weight:700}}
.logout{{background:rgba(255,77,77,0.9)!important;margin-top:20px}}
a{{text-decoration:none}}
.info-row{{margin-bottom:8px;color:#555}}
.info-row b{{color:#00a67e}}
.approve-btn{{background:#00d4aa;color:#fff;padding:8px 15px;border:none;border-radius:10px;cursor:pointer;margin-right:5px}}
.reject-btn{{background:#ff4d4d;color:#fff;padding:8px 15px;border:none;border-radius:10px;cursor:pointer}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden}}
th,td{{padding:10px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#00d4aa;color:#fff}}
.badge{{background:#ff4d4d;color:#fff;font-size:12px;font-weight:800;padding:3px 8px;border-radius:20px}}
/* MAINTENANCE FORM */
.form-group{{margin-bottom:15px}}
.form-group label{{display:block;margin-bottom:5px;color:#333;font-weight:600}}
.form-group input,.form-group textarea{{width:100%;padding:12px;border:1px solid #ddd;border-radius:10px;font-size:14px}}
.submit-btn{{background:#00d4aa;color:#fff;padding:12px 25px;border:none;border-radius:10px;font-weight:700;cursor:pointer;width:100%}}
.report-item{{border-left:4px solid #00d4aa;padding-left:15px;margin-bottom:15px;background:#f9f9f9;border-radius:5px}}
</style></head>
<body>
<div class="sidebar">{get_sidebar(active_page)}</div>
<div class="main">
  <div class="header">
    <img src="/logo.png" alt="SLSU Logo">
    <div class="header-text">
      <h1>SLSU-JGE {page_title}</h1>
      <p>Welcome, {user_data.get('complete_name', current_user)}!</p>
    </div>
  </div>
  {content}
</div>
</body></html>"""

HTML_LOGIN = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLSU-JGE Login</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}
body{height:100vh;display:flex;justify-content:center;align-items:center;
background: url('/bg.jpg') no-repeat center fixed; background-size: cover; position: relative;}
body::before{content:'';position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(135deg, rgba(0,180,126,0.6) 0%, rgba(0,212,170,0.6) 100%);backdrop-filter:blur(5px)}
.login-container{width:400px;padding:40px 30px;text-align:center;position:relative;z-index:1}
.logo-circle{width:110px;height:110px;border-radius:50%;margin:0 auto 10px;overflow:hidden;box-shadow:0 4px 15px rgba(0,0,0,0.2)}
.logo-circle img{width:100%;height:100%;object-fit:cover}
.campus-name{color:#fff;font-size:18px;font-weight:700;margin-bottom:25px;letter-spacing:1px;text-shadow:0 2px 4px rgba(0,0,0,0.3)}
.input-box{position:relative;margin-bottom:18px}
.input-box input{width:100%;padding:16px 20px;border:none;border-radius:50px;background:rgba(255,255,255,0.15);backdrop-filter:blur(10px);color:#fff;font-size:16px;outline:none;border:1px solid rgba(255,255,255,0.3)}
.input-box input::placeholder{color:rgba(255,255,255,0.9)}
.btn{width:100%;padding:16px;border:none;border-radius:50px;background:#fff;color:#00695c;font-size:18px;font-weight:800;cursor:pointer;margin:25px 0;letter-spacing:3px}
.options{display:flex;justify-content:space-between;color:#fff;font-size:14px;margin-bottom:10px;font-weight:500}
.options a{color:#fff;text-decoration:none}
.options input{margin-right:5px;accent-color:#fff}
.link{color:#fff;font-size:14px;text-decoration:underline;margin-top:10px;display:block}.error{color:#ffeb3b;font-size:14px;margin-bottom:10px;font-weight:600}.success{color:#fff;font-size:14px;margin-bottom:10px;font-weight:600}</style></head>
<body><div class="login-container">
<div class="logo-circle"><img src="/logo.png"></div>
<h2 class="campus-name">SLSU-JGE TAGKAWAYAN CAMPUS</h2>
{% if error %}<p class="error">{{error}}</p>{% endif %}{% if success %}<p class="success">{{success}}</p>{% endif %}
<form action="/login" method="POST">
<div class="input-box"><input type="text" name="username" placeholder="Username" required></div>
<div class="input-box"><input type="password" name="password" placeholder="Password" required></div>
<div class="options"><label><input type="checkbox"> Remember Me</label><a href="#">Forgot Password?</a></div>
<button type="submit" class="btn">LOGIN</button></form><a href="/signup" class="link">Don't have an account? Sign Up</a></div></body></html>"""

HTML_SIGNUP = """<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SLSU-JGE Sign Up</title><style>*{margin:0;padding:0;box-sizing:border-box;font-family:'Segoe UI',sans-serif}
body{height:100vh;display:flex;justify-content:center;align-items:center;
background: url('/bg.jpg') no-repeat center fixed; background-size: cover; position: relative;}
body::before{content:'';position:absolute;top:0;left:0;width:100%;height:100%;background:linear-gradient(135deg, rgba(0,180,126,0.6) 0%, rgba(0,212,170,0.6) 100%);backdrop-filter:blur(5px)}
.login-container{width:400px;padding:40px 30px;text-align:center;position:relative;z-index:1}
.logo-circle{width:110px;height:110px;border-radius:50%;margin:0 auto 10px;overflow:hidden}
.logo-circle img{width:100%;height:100%;object-fit:cover}
.campus-name{color:#fff;font-size:18px;font-weight:700;margin-bottom:20px;letter-spacing:1px;text-shadow:0 2px 4px rgba(0,0,0,0.3)}
.input-box{margin-bottom:12px}.input-box input{width:100%;padding:14px;border:none;border-radius:50px;background:rgba(255,255,255,0.15);backdrop-filter:blur(10px);color:#fff;font-size:15px;outline:none;border:1px solid rgba(255,255,255,0.3);text-align:center}
.input-box input::placeholder{color:rgba(255,255,255,0.8)}
.btn{width:100%;padding:14px;border:none;border-radius:50px;background:#fff;color:#00695c;font-size:16px;font-weight:700;cursor:pointer;margin-bottom:10px}
.link{color:#fff;font-size:14px;text-decoration:underline}.error{color:#ffeb3b;font-size:14px;margin-bottom:10px;font-weight:600}.success{color:#fff;font-size:14px;margin-bottom:10px;font-weight:600}</style></head>
<body><div class="login-container">
<div class="logo-circle"><img src="/logo.png"></div>
<h2 class="campus-name">SLSU-JGE TAGKAWAYAN CAMPUS</h2>
{% if error %}<p class="error">{{error}}</p>{% endif %}{% if success %}<p class="success">{{success}}</p>{% endif %}
<form action="/signup" method="POST">
<div class="input-box"><input type="text" name="complete_name" placeholder="Complete Name" required></div>
<div class="input-box"><input type="text" name="school_id" placeholder="School ID" required></div>
<div class="input-box"><input type="text" name="course" placeholder="Course" required></div>
<div class="input-box"><input type="text" name="year_level" placeholder="Year Level" required></div>
<div class="input-box"><input type="text" name="username" placeholder="Create Username" required></div>
<div class="input-box"><input type="password" name="password" placeholder="Create Password" required></div>
<button type="submit" class="btn">SUBMIT FOR APPROVAL</button></form><a href="/" class="link">Already have an account? Login</a></div></body></html>"""

@app.route('/')
def index():
    return render_template_string(HTML_LOGIN, error=None, success=None)

@app.route("/login", methods=["POST"])
def login():
    global current_user
    username = request.form.get('username')
    password = request.form.get('password')
    if username in users and users[username]["password"] == password:
        current_user = username
        return redirect('/dashboard')
    elif username in pending_users:
        return render_template_string(HTML_LOGIN, error="Your account is pending for admin approval.", success=None)
    else:
        return render_template_string(HTML_LOGIN, error="Invalid Username or Password", success=None)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        complete_name = request.form.get('complete_name')
        school_id = request.form.get('school_id')
        course = request.form.get('course')
        year_level = request.form.get('year_level')
        username = request.form.get('username')
        password = request.form.get('password')
        if username in users or username in pending_users:
            return render_template_string(HTML_SIGNUP, error="Username already exists!", success=None)
        else:
            pending_users[username] = {
                "password": password, "complete_name": complete_name, "school_id": school_id,
                "course": course, "year_level": year_level, "role": "student"
            }
            save_data()
            return render_template_string(HTML_SIGNUP, error=None, success="Account submitted! Wait for admin approval.")
    return render_template_string(HTML_SIGNUP, error=None, success=None)

# BAGONG MAINTENANCE OFFICE ROUTE
@app.route('/maintenance', methods=['GET', 'POST'])
def maintenance():
    if request.method == 'POST':
        description = request.form.get('description')
        location = request.form.get('location')
        reported_by = request.form.get('reported_by')

        maintenance_reports.append({
            'description': description,
            'location': location,
            'reported_by': reported_by
        })
        save_data()
        return redirect('/maintenance')

    content = "<div class='card'><h2>Report a Maintenance Issue</h2>"
    content += """<form method='POST'>
        <div class='form-group'><label>*Description - Anong sira</label><textarea name='description' rows='3' required></textarea></div>
        <div class='form-group'><label>*Location - Saan yung sira</label><input type='text' name='location' required></div>
        <div class='form-group'><label>*Reported by - Sino nag report</label><input type='text' name='reported_by' required></div>
        <button type='submit' class='submit-btn'>Submit Report</button>
    </form></div>"""

    content += "<div class='card'><h2>Submitted Reports</h2>"
    if not maintenance_reports:
        content += "<p>Walang nireport na sira.</p>"
    else:
        for report in reversed(maintenance_reports): # BAGONG REPORT NASA TAAS
            content += f"""<div class='report-item'>
                <p><b>Issue:</b> {report['description']}</p>
                <p><b>Location:</b> {report['location']}</p>
                <p><b>Reported by:</b> {report['reported_by']}</p>
            </div>"""
    content += "</div>"

    return render_template_string(dashboard_template(content, "maintenance", "Maintenance Office"))

@app.route('/pending')
def pending():
    if users.get(current_user, {}).get("role")!= "admin":
        return redirect('/dashboard')
    content = "<div class='card'><h2>Pending Accounts</h2>"
    if not pending_users:
        content += "<p>No pending accounts.</p>"
    else:
        for uname, data in pending_users.items():
            content += f"""<div style='border-bottom:1px solid #eee;padding:10px 0'>
            <b>{data['complete_name']}</b> - {data['school_id']}<br>
            {data['course']} | {data['year_level']}<br>
            Username: {uname}<br>
            <a href='/approve/{uname}'><button class='approve-btn'>Approve</button></a>
            <a href='/reject/{uname}'><button class='reject-btn'>Reject</button></a>
            </div>"""
    content += "</div>"
    return render_template_string(dashboard_template(content, "pending", "Pending Accounts"))

@app.route('/registered')
def registered():
    if users.get(current_user, {}).get("role")!= "admin":
        return redirect('/dashboard')
    content = "<div class='card'><h2>Registered Students</h2><table><tr><th>School ID</th><th>Complete Name</th><th>Course</th><th>Year</th><th>Username</th></tr>"
    for uname, data in users.items():
        if data.get("role") == "student":
            content += f"<tr><td>{data['school_id']}</td><td>{data['complete_name']}</td><td>{data['course']}</td><td>{data['year_level']}</td><td>{uname}</td></tr>"
    content += "</table></div>"
    return render_template_string(dashboard_template(content, "registered", "Registered Students"))

@app.route('/approve/<username>')
def approve(username):
    if users.get(current_user, {}).get("role") == "admin" and username in pending_users:
        users[username] = pending_users.pop(username)
        save_data()
    return redirect('/pending')

@app.route('/reject/<username>')
def reject(username):
    if users.get(current_user, {}).get("role") == "admin" and username in pending_users:
        pending_users.pop(username)
        save_data()
    return redirect('/pending')

@app.route('/dashboard')
def dashboard():
    content = """<div class="card"><h2>Current Subjects</h2><p>IT 101 - Intro to Programming<br>MATH 202 - Calculus<br>ENG 103 - Technical Writing</p></div>"""
    return render_template_string(dashboard_template(content, "dashboard", "Dashboard"))

@app.route('/registrar')
def registrar():
    content = """<div class="card"><h2>Registrar Office</h2><p><b>Services:</b></p>
    <p>📄 Request Transcript of Records<br>📄 Certificate of Enrollment<br>📄 Good Moral Certificate</p></div>"""
    return render_template_string(dashboard_template(content, "registrar", "Registrar"))

@app.route('/guard')
def guard():
    content = """<div class="card"><h2>Guard Office</h2><p><b>Services:</b></p>
    <p>🛡️ Campus Security Assistance<br>🛡️ Lost and Found Items<br>🛡️ Visitor Pass Issuance</p></div>"""
    return render_template_string(dashboard_template(content, "guard", "Guard Office"))

@app.route('/profile')
def profile():
    user_data = users.get(current_user, {})
    content = f"""<div class="card"><h2>My Profile</h2>
    <div class="info-row"><b>Complete Name:</b> {user_data.get('complete_name')}</div>
    <div class="info-row"><b>School ID:</b> {user_data.get('school_id')}</div>
    <div class="info-row"><b>Username:</b> {current_user}</div>
    <div class="info-row"><b>Course:</b> {user_data.get('course')}</div>
    <div class="info-row"><b>Year Level:</b> {user_data.get('year_level')}</div>
    </div>"""
    return render_template_string(dashboard_template(content, "profile", "Profile"))

if __name__ == '__main__':
    app.run(debug=False)
