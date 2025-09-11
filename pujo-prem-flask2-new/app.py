from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
from datetime import date, datetime, timezone
from supabase import create_client, Client
import humanize
from dateutil.relativedelta import relativedelta

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

@app.template_filter('humanize_datetime')
def humanize_datetime_filter(dt_string):
    dt = datetime.fromisoformat(dt_string).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return humanize.naturaltime(now - dt)

# Supabase connection
SUPABASE_URL = "https://uccwrkpdkheliitelkag.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVjY3dya3Bka2hlbGlpdGVsa2FnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTcwNDM5OTUsImV4cCI6MjA3MjYxOTk5NX0.fHF4N9m2n5FIGQRbhjxdq9YBolFoVkVJJ5VIzRFL3h8"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))

def get_unread_chat_count(user_id):
    """Counts the number of distinct users who have sent an unread message."""
    res = supabase.table("messages").select("sender_id").eq("receiver_id", user_id).eq("is_read", False).execute()
    unique_senders = set(item['sender_id'] for item in res.data)
    return len(unique_senders)

def get_unread_count_per_chat(user_id):
    """
    Counts unread messages for a user, grouped by sender.
    Returns a dictionary like { 'sender_id': count, ... }
    """
    res = supabase.table("messages").select("sender_id").eq("receiver_id", user_id).eq("is_read", False).execute()
    unread_counts = {}
    for message in res.data:
        sender_id = message['sender_id']
        unread_counts[sender_id] = unread_counts.get(sender_id, 0) + 1
    return unread_counts

def mark_messages_as_read(receiver_id, sender_id):
    res = supabase.table("messages") \
    .update({"is_read": True}) \
    .eq("sender_id", sender_id) \
    .eq("receiver_id", receiver_id) \
    .execute()

    print(res)





def add_like(liker_id, liked_id):
    """Insert a like if it doesn't exist already."""
    res = supabase.table("likes").insert({
        "liker_id": liker_id,
        "liked_id": liked_id
    }).execute()
    return res

def remove_like(liker_id, liked_id):
    """Remove an existing like."""
    res = supabase.table("likes").delete() \
        .eq("liker_id", liker_id).eq("liked_id", liked_id).execute()
    return res

def has_liked(liker_id, liked_id):
    """Check if the user already liked the profile."""
    res = supabase.table("likes").select("id") \
        .eq("liker_id", liker_id).eq("liked_id", liked_id).execute()
    return bool(res.data)

def get_likes_count(user_id):
    """Return how many likes this profile has received."""
    res = supabase.table("likes").select("id", count="exact") \
        .eq("liked_id", user_id).execute()
    return res.count or 0

def get_match_count(user_id):
    """Returns the number of mutual likes (matches) for the user."""
    # Find users the current user liked
    liked_by_me = supabase.table("likes").select("liked_id").eq("liker_id", user_id).execute().data
    liked_by_me_ids = [item['liked_id'] for item in liked_by_me]
    
    # Find users who liked the current user
    liked_me = supabase.table("likes").select("liker_id").eq("liked_id", user_id).execute().data
    liked_me_ids = [item['liker_id'] for item in liked_me]

    # Find the intersection (mutual likes)
    matches = set(liked_by_me_ids).intersection(set(liked_me_ids))
    return len(matches)

def get_chat_partners_count(user_id):
    """Returns the number of unique users a profile has chatted with."""
    res = supabase.table("messages").select("sender_id, receiver_id") \
        .or_(f"sender_id.eq.{user_id},receiver_id.eq.{user_id}").execute()
    
    chat_partners = set()
    for message in res.data:
        if message['sender_id'] != user_id:
            chat_partners.add(message['sender_id'])
        if message['receiver_id'] != user_id:
            chat_partners.add(message['receiver_id'])
    return len(chat_partners)
# END: New function

def get_recent_activity(user_id):
    """
    Fetches a list of recent activities for a user, including new likes and messages.
    Combines and sorts them by creation time.
    """
    # Get recent messages sent to the user
    messages_res = supabase.table("messages").select("sender_id, content, created_at").eq("receiver_id", user_id).order("created_at", desc=True).limit(5).execute()
    messages = []
    if messages_res.data:
        # Get profile names for the message senders
        sender_ids = [m['sender_id'] for m in messages_res.data]
        profiles_res = supabase.table("profiles").select("id, name").in_("id", sender_ids).execute()
        profiles_map = {p['id']: p['name'] for p in profiles_res.data}

        for msg in messages_res.data:
            sender_name = profiles_map.get(msg['sender_id'], 'Someone')
            messages.append({
                "type": "message",
                "message": f"New message from {sender_name}",
                "timestamp": msg['created_at']
            })

    # Get recent likes for the user
    likes_res = supabase.table("likes").select("liker_id, created_at").eq("liked_id", user_id).order("created_at", desc=True).limit(5).execute()
    likes = []
    if likes_res.data:
        liker_ids = [l['liker_id'] for l in likes_res.data]
        profiles_res = supabase.table("profiles").select("id, name").in_("id", liker_ids).execute()
        profiles_map = {p['id']: p['name'] for p in profiles_res.data}
        for like in likes_res.data:
            liker_name = profiles_map.get(like['liker_id'], 'Someone')
            likes.append({
                "type": "like",
                "message": f"{liker_name} liked your profile",
                "timestamp": like['created_at']
            })

    # Combine and sort all activities
    all_activities = sorted(messages + likes, key=lambda x: x['timestamp'], reverse=True)
    return all_activities

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
        if user and user["password"] == password:
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
        res = supabase.table("users").select("id").eq("email", email).execute()
        if res.data:
            flash('An account with this email already exists.', 'error')
            return redirect(url_for('signup'))
        res = supabase.table("users").insert({
            "email": email,
            "password": password,
            "is_profile_complete": False
        }).execute()
        user_id = res.data[0]["id"]
        session['user_id'] = user_id
        return redirect(url_for('profile_setup'))
    return render_template('auth.html', mode='signup')

@app.route('/profile-setup', methods=['GET', 'POST'])
def profile_setup():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        user_id = session['user_id']
        dob_str = request.form.get("dateOfBirth")
        age = 0
        if dob_str:
            try:
                born = date.fromisoformat(dob_str)
                age = calculate_age(born)
            except ValueError:
                pass
        uploaded_photos = request.files.getlist("photos")
        photo_urls = []
        if uploaded_photos:
            for photo in uploaded_photos:
                if photo and photo.filename:
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
                    file_name = f"{user_id}_{timestamp}_{photo.filename}"
                    temp_path = os.path.join("uploads", file_name)
                    os.makedirs("uploads", exist_ok=True)
                    photo.save(temp_path)
                    with open(temp_path, "rb") as f:
                        supabase.storage.from_("profile_photos").upload(
                            file_name, f, {"upsert": "true"}
                        )
                    public_url = supabase.storage.from_("profile_photos").get_public_url(file_name)
                    photo_urls.append(public_url)
                    os.remove(temp_path)
        if not photo_urls:
            photo_urls = ["https://images.pexels.com/photos/220453/pexels-photo-220453.jpeg?auto=compress&cs=tinysrgb&w=400&h=400&fit=crop&crop=face"]
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
        supabase.table("users").update({"is_profile_complete": True}).eq("id", user_id).execute()
        return redirect(url_for('dashboard'))
    return render_template('profile_setup.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    res_user = supabase.table("users").select("*").eq("id", user_id).execute()
    res_profile = supabase.table("profiles").select("*").eq("id", user_id).execute()
    user = res_user.data[0] if res_user.data else None
    profile = res_profile.data[0] if res_profile.data else None
    
    if profile and profile['photos'] is None:
        profile['photos'] = []
    
    if not user or not user.get("is_profile_complete"):
        return redirect(url_for('profile_setup'))

    unread_chat_count = get_unread_chat_count(user_id)
    likes_count = get_likes_count(user_id)
    match_count = get_match_count(user_id)
    messages_count = get_chat_partners_count(user_id)
    
    # Fetch dynamic recent activity
    recent_activity = get_recent_activity(user_id)

    session['back_url'] = url_for('dashboard')
    
    return render_template(
        'dashboard.html',
        user=user,
        profile=profile,
        unread_chat_count=unread_chat_count,
        likes_count=likes_count,
        match_count=match_count,
        messages_count=messages_count,
        recent_activity=recent_activity
    )

@app.route('/edit-profile', methods=['GET'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    # Fetch current profile data
    res_profile = supabase.table("profiles").select("*").eq("id", user_id).execute()
    profile = res_profile.data[0] if res_profile.data else None
    
    if not profile:
        flash("Profile not found.", "error")
        return redirect(url_for('dashboard'))
        
    return render_template('edit_profile.html', profile=profile)


# Route for handling the form submission
@app.route('/update-profile', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']

    # Fetch existing photos to merge new ones with
    res = supabase.table("profiles").select("photos").eq("id", user_id).execute()
    existing_photos = res.data[0]['photos'] if res.data and res.data[0]['photos'] else []
    
    # Handle new photo uploads
    uploaded_photos = request.files.getlist("photos")
    photo_urls = []
    
    for photo in uploaded_photos:
        if photo and photo.filename:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            file_name = f"{user_id}_{timestamp}_{photo.filename}"
            
            temp_path = os.path.join("uploads", file_name)
            os.makedirs("uploads", exist_ok=True)
            photo.save(temp_path)
            
            with open(temp_path, "rb") as f:
                supabase.storage.from_("profile_photos").upload(
                    file_name, f, {"upsert": "true"}
                )
            
            public_url = supabase.storage.from_("profile_photos").get_public_url(file_name)
            photo_urls.append(public_url)
            os.remove(temp_path)

    # Combine existing and new photos
    updated_photos = existing_photos + photo_urls
    
    # Calculate age if DOB is provided
    dob_str = request.form.get("dateOfBirth")
    age = None
    if dob_str:
        try:
            born = date.fromisoformat(dob_str)
            age = calculate_age(born)
        except ValueError:
            pass
            
    # Update the profile in the database
    update_data = {
        "name": request.form.get("name"),
        "dob": dob_str,
        "age": age,
        "location": request.form.get("location"),
        "bio": request.form.get("bio"),
        "interests": [i.strip() for i in request.form.get("interests", "").split(',') if i.strip()],
        "photos": updated_photos
    }
    
    supabase.table("profiles").update(update_data).eq("id", user_id).execute()
    
    flash("Profile updated successfully!", "success")
    return redirect(url_for('dashboard'))


@app.route('/add_photos', methods=['POST'])
def add_photos():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    uploaded_photos = request.files.getlist("photos")
    if not uploaded_photos:
        flash('No photos selected.', 'error')
        return redirect(url_for('dashboard'))
    res_profile = supabase.table("profiles").select("photos").eq("id", user_id).execute()
    existing_photos = res_profile.data[0]['photos'] if res_profile.data and res_profile.data[0]['photos'] else []
    new_photo_urls = []
    for photo in uploaded_photos:
        if photo and photo.filename:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            file_name = f"{user_id}_{timestamp}_{photo.filename}"
            temp_path = os.path.join("uploads", file_name)
            os.makedirs("uploads", exist_ok=True)
            photo.save(temp_path)
            with open(temp_path, "rb") as f:
                supabase.storage.from_("profile_photos").upload(
                    file_name, f, {"upsert": "true"}
                )
            public_url = supabase.storage.from_("profile_photos").get_public_url(file_name)
            new_photo_urls.append(public_url)
            os.remove(temp_path)
    if new_photo_urls:
        updated_photos = existing_photos + new_photo_urls
        supabase.table("profiles").update({"photos": updated_photos}).eq("id", user_id).execute()
        flash('Photos uploaded successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/delete_photo', methods=['POST'])
def delete_photo():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    photo_url = request.form.get('photo_url')

    if not photo_url:
        flash('No photo URL provided.', 'error')
        return redirect(url_for('dashboard'))

    # Step 1: Get the current list of photos from the database
    res = supabase.table("profiles").select("photos").eq("id", user_id).execute()
    existing_photos = res.data[0]['photos'] if res.data and res.data[0]['photos'] else []

    # Step 2: Remove the URL from the list
    if photo_url in existing_photos:
        existing_photos.remove(photo_url)

        # Step 3: Update the database with the new list
        supabase.table("profiles").update({"photos": existing_photos}).eq("id", user_id).execute()

        # Step 4: Delete the file from Supabase Storage
        # The filename is the part of the URL after the bucket path.
        # e.g., 'profile_photos/user_123.jpg'
        # Split the URL to get the file name
        path_in_storage = '/'.join(photo_url.split('/')[-2:])
        supabase.storage.from_("profile_photos").remove([path_in_storage])

        flash('Photo deleted successfully.', 'success')
    else:
        flash('Photo not found.', 'error')
    
    return redirect(url_for('dashboard'))


@app.route('/see-other')
def see_other():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user_id = session['user_id']
    res_profiles = supabase.table("profiles").select("*").neq("id", current_user_id).execute()
    profiles = res_profiles.data if res_profiles.data else []
    session['back_url'] = url_for('see_other')
    return render_template("see_other.html", users=profiles)

@app.route('/profile/<user_id>')
def view_profile(user_id):
    res = supabase.table("profiles").select("*").eq("id", user_id).execute()
    profile = res.data[0] if res.data else None
    if not profile:
        return "Profile not found", 404
    if profile and profile['photos'] is None:
        profile['photos'] = []

    # Like info
    messages_count = get_chat_partners_count(user_id)
    match_count = get_match_count(user_id)
    likes_count = get_likes_count(user_id)
    already_liked = False
    if 'user_id' in session:
        already_liked = has_liked(session['user_id'], user_id)

    session['back_url'] = url_for('view_profile', user_id=user_id)
    return render_template("view_profile.html", profile=profile,
                           likes_count=likes_count, already_liked=already_liked,match_count=match_count,messages_count=messages_count)




@app.route('/chat/<receiver_id>', methods=['GET'])
def chat(receiver_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    sender_id = session['user_id']
    receiver_res = supabase.table("profiles").select("name, photos").eq("id", receiver_id).execute()
    if receiver_res.data:
        receiver_name = receiver_res.data[0]['name']
        photos = receiver_res.data[0]['photos'] or []
        # Pick the first photo if available, otherwise use a default
        receiver_profile_url = photos[0] if photos else "https://images.pexels.com/photos/220453/pexels-photo-220453.jpeg?auto=compress&cs=tinysrgb&w=400&h=400&fit=crop&crop=face"
    else:
        receiver_name = 'User'
        receiver_profile_url = "https://images.pexels.com/photos/220453/pexels-photo-220453.jpeg?auto=compress&cs=tinysrgb&w=400&h=400&fit=crop&crop=face"

    
    
    mark_messages_as_read(receiver_id=session['user_id'], sender_id=receiver_id)
    
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
    receiver_res = supabase.table("profiles").select("name").eq("id", receiver_id).execute()
    receiver_name = receiver_res.data[0]['name'] if receiver_res.data else 'User'
    back_url = session.get('back_url', url_for('dashboard'))
    return render_template(
    "chat.html",
    messages=messages,
    receiver_id=receiver_id,
    receiver_name=receiver_name,
    receiver_profile_url=receiver_profile_url,
    sender_id=sender_id,
    SUPABASE_URL="https://uccwrkpdkheliitelkag.supabase.co",
    SUPABASE_KEY=SUPABASE_KEY,
    back_url=back_url
)


@app.route('/read_messages/<sender_id>', methods=['POST'])
def read_messages(sender_id):
    if 'user_id' not in session:
        return jsonify({"success": False}), 401

    receiver_id = session['user_id']  # logged-in user
    mark_messages_as_read(receiver_id=receiver_id, sender_id=sender_id)

    return jsonify({"success": True})

@app.route('/chat_list')
def chat_list():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    current_user_id = session['user_id']
    res_messages = (
        supabase.table("messages")
        .select("sender_id, receiver_id, content, created_at")
        .or_(f"sender_id.eq.{current_user_id},receiver_id.eq.{current_user_id}")
        .order("created_at", desc=True)
        .execute()
    )
    all_messages = res_messages.data if res_messages.data else []
    chat_partners = {}
    for message in all_messages:
        partner_id = message['sender_id'] if message['sender_id'] != current_user_id else message['receiver_id']
        if partner_id not in chat_partners:
            chat_partners[partner_id] = {
                'id': partner_id,
                'last_message': message['content'],
                'created_at': message['created_at']
            }
    chat_partner_ids = list(chat_partners.keys())
    chat_users = []
    if chat_partner_ids:
        res_profiles = supabase.table("profiles").select("*").in_("id", chat_partner_ids).execute()
        profiles_map = {profile['id']: profile for profile in res_profiles.data}
        for partner_id, partner_data in chat_partners.items():
            if partner_id in profiles_map:
                profile = profiles_map[partner_id]
                profile['last_message'] = partner_data['last_message']
                profile['last_message_date'] = partner_data['created_at']
                chat_users.append(profile)
        chat_users.sort(key=lambda x: x['last_message_date'], reverse=True)
    unread_counts = get_unread_count_per_chat(current_user_id)
    session['back_url'] = url_for('chat_list')
    return render_template("chat_list.html", users=chat_users, unread_counts=unread_counts)



@app.route('/like/<string:liked_id>', methods=['POST'])
def like(liked_id):
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    liker_id = session['user_id']
    if liker_id == liked_id:
        return jsonify({"success": False, "error": "Cannot like yourself"}), 400

    if has_liked(liker_id, liked_id):
        # Unlike if already liked
        remove_like(liker_id, liked_id)
        return jsonify({"success": True, "liked": False})
    else:
        add_like(liker_id, liked_id)
        return jsonify({"success": True, "liked": True})


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('landing'))

if __name__ == '__main__':
    app.run(debug=True)