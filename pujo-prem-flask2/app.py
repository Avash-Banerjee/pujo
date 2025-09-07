from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import json
from datetime import date, datetime
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

# Supabase connection
SUPABASE_URL = "https://uccwrkpdkheliitelkag.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVjY3dya3Bka2hlbGlpdGVsa2FnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTcwNDM5OTUsImV4cCI6MjA3MjYxOTk5NX0.fHF4N9m2n5FIGQRbhjxdq9YBolFoVkVJJ5VIzRFL3h8"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


@app.route('/')
def landing():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        res = supabase.table("users").select("*").eq("email", email).execute()
        user = res.data[0] if res.data else None

        if user and user["password"] == password:  # ⚠️ for prod: hash + verify
            session['user_id'] = user["id"]
            if user.get("is_profile_complete"):
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('profile_setup'))
        else:
            flash('Invalid credentials. Please try again.', 'error')
            return redirect(url_for('login'))

    return render_template('auth.html', mode='login')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # check if exists
        res = supabase.table("users").select("id").eq("email", email).execute()
        if res.data:
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('signup'))

        res = supabase.table("users").insert({
            "email": email,
            "password": password,  # ⚠️ hash in real apps
            "is_profile_complete": False
        }).execute()

        user_id = res.data[0]["id"]
        session['user_id'] = user_id
        return redirect(url_for('profile_setup'))

    return render_template('auth.html', mode='signup')


from datetime import date
import os, json
from flask import request, session, redirect, url_for, render_template

@app.route('/profile-setup', methods=['GET', 'POST'])
def profile_setup():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = session['user_id']

        # --- Date of Birth & Age ---
        dob_str = request.form.get("dateOfBirth")
        age = 0
        if dob_str:
            try:
                born = date.fromisoformat(dob_str)
                age = calculate_age(born)
            except ValueError:
                pass

        # --- Handle Photo Upload(s) ---
        uploaded_photos = request.files.getlist("photos")
        photo_urls = []

        if uploaded_photos:
            for photo in uploaded_photos:
                if photo and photo.filename:
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                    file_name = f"{user_id}_{timestamp}_{photo.filename}"

                    # save temporarily before upload
                    temp_path = os.path.join("uploads", file_name)
                    os.makedirs("uploads", exist_ok=True)
                    photo.save(temp_path)

                    # upload to Supabase Storage
                    with open(temp_path, "rb") as f:
                        supabase.storage.from_("profile_photos").upload(
                            file_name, f, {"upsert": "true"}
                        )

                    # ✅ get public URL
                    public_url = supabase.storage.from_("profile_photos").get_public_url(file_name)
                    photo_urls.append(public_url)

                    # cleanup temp file
                    os.remove(temp_path)

        # fallback placeholder
        if not photo_urls:
            photo_urls = [
                "https://images.pexels.com/photos/220453/pexels-photo-220453.jpeg?auto=compress&cs=tinysrgb&w=400&h=400&fit=crop&crop=face"
            ]

        # --- Save profile ---
        supabase.table("profiles").upsert({
            "id": user_id,
            "name": request.form.get("name"),
            "dob": dob_str,
            "age": age,
            "gender": request.form.get("gender"),
            "location": request.form.get("location"),
            "bio": request.form.get("bio"),
            "interests": [i.strip() for i in request.form.get("interests", "").split(',') if i.strip()],
            "photos": photo_urls
        }).execute()

        # ✅ Mark profile as complete
        supabase.table("users").update({"is_profile_complete": True}).eq("id", user_id).execute()

        return redirect(url_for('dashboard'))

    return render_template('profile_setup.html')



@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # ✅ FIX: select, don’t update
    res_user = supabase.table("users").select("*").eq("id", user_id).execute()
    res_profile = supabase.table("profiles").select("*").eq("id", user_id).execute()

    user = res_user.data[0] if res_user.data else None
    profile = res_profile.data[0] if res_profile.data else None
    if profile['photos'] is None:
        profile['photos'] = []

    if not user or not user.get("is_profile_complete"):
        return redirect(url_for('profile_setup'))

    return render_template('dashboard.html', user=user, profile=profile)


@app.route('/add_photos', methods=['POST'])
def add_photos():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    uploaded_photos = request.files.getlist("photos")
    
    if not uploaded_photos:
        flash('No photos selected.', 'error')
        return redirect(url_for('dashboard'))

    # --- Get existing photos ---
    res_profile = supabase.table("profiles").select("photos").eq("id", user_id).execute()
    existing_photos = res_profile.data[0]['photos'] if res_profile.data and res_profile.data[0]['photos'] else []

    # --- Handle Photo Upload(s) ---
    new_photo_urls = []
    for photo in uploaded_photos:
        if photo and photo.filename:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            file_name = f"{user_id}_{timestamp}_{photo.filename}"

            # save temporarily before upload
            temp_path = os.path.join("uploads", file_name)
            os.makedirs("uploads", exist_ok=True)
            photo.save(temp_path)

            # upload to Supabase Storage
            with open(temp_path, "rb") as f:
                supabase.storage.from_("profile_photos").upload(
                    file_name, f, {"upsert": "true"}
                )

            # ✅ get public URL
            public_url = supabase.storage.from_("profile_photos").get_public_url(file_name)
            new_photo_urls.append(public_url)

            # cleanup temp file
            os.remove(temp_path)

    # --- Update profile with new photos ---
    if new_photo_urls:
        updated_photos = existing_photos + new_photo_urls
        supabase.table("profiles").update({"photos": updated_photos}).eq("id", user_id).execute()
        flash('Photos uploaded successfully!', 'success')

    return redirect(url_for('dashboard'))


@app.route('/see-other')
def see_other():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    current_user_id = session['user_id']

    # ✅ Fetch all other profiles (exclude current user)
    res_profiles = supabase.table("profiles").select("*").neq("id", current_user_id).execute()
    profiles = res_profiles.data if res_profiles.data else []

    return render_template("see_other.html", users=profiles)


@app.route('/profile/<user_id>')
def view_profile(user_id):
    # Fetch from Supabase
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    
    profile = res.data[0] if res.data else None
    if profile['photos'] is None:
        profile['photos'] = []

    if not profile:
        return "Profile not found", 404

    return render_template("view_profile.html", profile=profile)

@app.route('/chat/<receiver_id>', methods=['GET', 'POST'])
def chat(receiver_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    sender_id = session['user_id']

    if request.method == 'POST':
        message = request.form.get("message")
        if message:
            supabase.table("messages").insert({
                "sender_id": sender_id,
                "receiver_id": receiver_id,
                "content": message
            }).execute()

    # ✅ Fetch last 50 messages between both users
    query = (
        f"and(sender_id.eq.\"{sender_id}\",receiver_id.eq.\"{receiver_id}\"),"
        f"and(sender_id.eq.\"{receiver_id}\",receiver_id.eq.\"{sender_id}\")"
    )

    res = (
        supabase.table("messages")
        .select("*")
        .or_(query)
        .order("created_at")
        .limit(50)
        .execute()
    )

    messages = res.data if res.data else []

    return render_template(
        "chat.html",
        messages=messages,
        receiver_id=receiver_id,
        sender_id=sender_id,
        SUPABASE_URL="https://uccwrkpdkheliitelkag.supabase.co",
        SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVjY3dya3Bka2hlbGlpdGVsa2FnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTcwNDM5OTUsImV4cCI6MjA3MjYxOTk5NX0.fHF4N9m2n5FIGQRbhjxdq9YBolFoVkVJJ5VIzRFL3h8"
    )



@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('landing'))


if __name__ == '__main__':
    app.run(debug=True)
