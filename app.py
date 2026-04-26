from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, FLASK_SECRET_KEY, SENDGRID_API_KEY, SENDGRID_FROM_EMAIL
from functools import wraps
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os, random, string
from datetime import datetime

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ══════════════════════════════════════
# GLOBAL VARIABLES FOR ALL HTML TEMPLATES
# ══════════════════════════════════════
@app.context_processor
def inject_globals():
    return {
        'user': session.get('user'),
        'customer': session.get('customer')
    }

# ══════════════════════════════════════
# AUTH DECORATORS
# ══════════════════════════════════════
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def customer_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'customer' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════
# HELPER FUNCTIONS (Email)
# ══════════════════════════════════════
def send_email(to_email, subject, html_content):
    try:
        if not SENDGRID_API_KEY: return
        sg  = SendGridAPIClient(SENDGRID_API_KEY)
        msg = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        sg.send(msg)
    except Exception as e:
        print(f"Email error: {e}")

def send_booking_confirmation(customer_email, customer_name, booking_ref, vehicle_name, start_date, end_date, amount):
    send_email(
        customer_email,
        f'Booking Confirmed — {booking_ref}',
        f"""
        <div style="font-family:sans-serif;max-width:480px;margin:auto;">
          <h2 style="color:#2563eb;">QuickRent</h2>
          <p>Hi {customer_name},</p>
          <p>Your booking is confirmed!</p>
          <table style="width:100%;border-collapse:collapse;margin:16px 0;">
            <tr><td style="padding:8px;color:#666;">Booking Ref</td><td style="padding:8px;font-weight:bold;">{booking_ref}</td></tr>
            <tr><td style="padding:8px;color:#666;">Vehicle</td><td style="padding:8px;">{vehicle_name}</td></tr>
            <tr><td style="padding:8px;color:#666;">Pick Up</td><td style="padding:8px;">{start_date}</td></tr>
            <tr><td style="padding:8px;color:#666;">Return</td><td style="padding:8px;">{end_date}</td></tr>
            <tr><td style="padding:8px;color:#666;">Total</td><td style="padding:8px;color:#2563eb;font-weight:bold;">₹{amount:,}</td></tr>
          </table>
          <p style="color:#666;font-size:12px;">— QuickRent Team</p>
        </div>"""
    )

# ══════════════════════════════════════
# UNIFIED LOGIN (ADMIN & CUSTOMER)
# ══════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    if 'customer' in session:
        return redirect(url_for('customer_dashboard'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        try:
            response = db.auth.sign_in_with_password({'email': email, 'password': password})
            user_id = response.user.id
            profile = db.table('profiles').select('*').eq('id', user_id).execute()
            
            if not profile.data:
                error = 'Profile not found. Please contact support.'
            else:
                role = profile.data[0]['role']
                
                # ADMIN LOGIN
                if role in ['admin', 'owner']:
                    session['user'] = {'id': user_id, 'email': email}
                    session['access_token'] = response.session.access_token
                    return redirect(url_for('dashboard'))
                    
                # CUSTOMER LOGIN
                elif role == 'customer':
                    customer_id = profile.data[0]['customer_id']
                    customer = db.table('customers').select('*').eq('id', customer_id).execute()
                    
                    if customer.data:
                        session['customer'] = {
                            'id': customer_id,
                            'user_id': user_id,
                            'name': customer.data[0]['name'],
                            'email': customer.data[0]['email']
                        }
                        return redirect(url_for('customer_dashboard'))
                    else:
                        error = 'Customer record missing.'
        except Exception as e:
            error = 'Invalid email or password. Please try again.'

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ══════════════════════════════════════
# CUSTOMER REGISTER & LOGOUT
# ══════════════════════════════════════
@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if 'customer' in session: return redirect(url_for('customer_dashboard'))

    error, success = None, None
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip()
        phone    = request.form.get('phone', '').strip()
        city     = request.form.get('city', '').strip()
        password = request.form.get('password', '').strip()
        confirm  = request.form.get('confirm', '').strip()

        if not all([name, email, password, confirm]):
            error = 'Name, email and password are required.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        else:
            try:
                auth_response = db.auth.sign_up({'email': email, 'password': password})
                user_id = auth_response.user.id

                customer_res = db.table('customers').insert({
                    'name': name, 'email': email, 'phone': phone, 'city': city,
                    'total_rentals': 0, 'total_spent': 0
                }).execute()
                customer_id = customer_res.data[0]['id']

                db.table('profiles').insert({
                    'id': user_id, 'role': 'customer', 'customer_id': customer_id
                }).execute()

                success = 'Account created successfully. You can now log in.'
            except Exception as e:
                error_msg = str(e)
                if 'already registered' in error_msg or 'already exists' in error_msg:
                    error = 'An account with this email already exists.'
                else:
                    error = 'Registration failed. Please try again.'

    return render_template('customer/register.html', error=error, success=success)

@app.route('/customer/logout')
def customer_logout():
    session.pop('customer', None)
    return redirect(url_for('login'))

# ══════════════════════════════════════
# SIDEBAR COMPONENT
# ══════════════════════════════════════
@app.route('/components/sidebar')
@login_required
def sidebar_component():
    return render_template('components/sidebar.html')

# ══════════════════════════════════════
# ADMIN PORTAL PAGES
# ══════════════════════════════════════
@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    try:
        current_month = datetime.now().strftime('%Y-%m')
        vehicles_res = db.table('vehicles').select('*', count='exact').execute()
        active_bookings = db.table('bookings').select('*', count='exact').eq('status', 'active').execute()
        pending_bookings = db.table('bookings').select('*', count='exact').eq('status', 'pending').execute()
        overdue_bookings = db.table('bookings').select('*', count='exact').eq('status', 'overdue').execute()
        available = db.table('vehicles').select('*', count='exact').eq('status', 'available').execute()
        rented = db.table('vehicles').select('*', count='exact').eq('status', 'rented').execute()
        maintenance = db.table('vehicles').select('*', count='exact').eq('status', 'maintenance').execute()

        recent_bookings = db.table('bookings')\
            .select('*, customers(name), vehicles(name, type)')\
            .order('created_at', desc=True).limit(5).execute()

        payments_res = db.table('payments').select('amount, status, created_at').execute()
        total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0
        monthly_revenue = sum(
            p['amount'] for p in payments_res.data
            if p['status'] == 'paid' and p.get('created_at', '')[:7] == current_month
        ) if payments_res.data else 0

        return render_template('dashboard.html',
            total_vehicles=vehicles_res.count or 0, total_revenue=total_revenue, monthly_revenue=monthly_revenue,
            available_vehicles=available.count or 0, rented_vehicles=rented.count or 0, maintenance_vehicles=maintenance.count or 0,
            active_bookings=active_bookings.count or 0, pending_bookings=pending_bookings.count or 0, overdue_bookings=overdue_bookings.count or 0,
            recent_bookings=recent_bookings.data or []
        )
    except Exception as e:
        print('Dashboard error:', e)
        return render_template('dashboard.html')

@app.route('/bookings')
@login_required
def bookings():
    try:
        status_filter = request.args.get('status', 'all')
        query = db.table('bookings').select('*, customers(name, phone), vehicles(name, type)').order('created_at', desc=True)
        if status_filter != 'all': query = query.eq('status', status_filter)
        bookings_res = query.execute()

        counts = {
            'all': db.table('bookings').select('*', count='exact').execute().count or 0,
            'active': db.table('bookings').select('*', count='exact').eq('status', 'active').execute().count or 0,
            'pending': db.table('bookings').select('*', count='exact').eq('status', 'pending').execute().count or 0,
            'overdue': db.table('bookings').select('*', count='exact').eq('status', 'overdue').execute().count or 0,
            'completed': db.table('bookings').select('*', count='exact').eq('status', 'completed').execute().count or 0,
        }
        return render_template('bookings.html', bookings=bookings_res.data or [], counts=counts, active_filter=status_filter)
    except Exception as e:
        return render_template('bookings.html')

@app.route('/vehicles')
@login_required
def vehicles():
    try:
        type_filter = request.args.get('type', 'all')
        query = db.table('vehicles').select('*').order('created_at', desc=True)
        if type_filter in ['car', 'bike']: query = query.eq('type', type_filter)
        elif type_filter == 'unavailable': query = query.neq('status', 'available')
        vehicles_res = query.execute()
        return render_template('vehicles.html', vehicles=vehicles_res.data or [], active_filter=type_filter)
    except Exception as e:
        return render_template('vehicles.html')

@app.route('/customers')
@login_required
def customers():
    try:
        customers_res = db.table('customers').select('*').order('created_at', desc=True).execute()
        counts = {'total': db.table('customers').select('*', count='exact').execute().count or 0}
        return render_template('customers.html', customers=customers_res.data or [], counts=counts)
    except Exception as e:
        return render_template('customers.html')

@app.route('/payments')
@login_required
def payments():
    try:
        status_filter = request.args.get('status', 'all')
        query = db.table('payments').select('*, bookings(booking_ref), customers(name)').order('created_at', desc=True)
        if status_filter != 'all': query = query.eq('status', status_filter)
        payments_res = query.execute()

        all_payments = db.table('payments').select('amount, status').execute()
        total_collected = sum(p['amount'] for p in all_payments.data if p['status'] == 'paid') if all_payments.data else 0
        total_pending = sum(p['amount'] for p in all_payments.data if p['status'] == 'pending') if all_payments.data else 0

        return render_template('payments.html', payments=payments_res.data or [], active_filter=status_filter, total_collected=total_collected, total_pending=total_pending)
    except Exception as e:
        return render_template('payments.html')

@app.route('/analytics')
@login_required
def analytics():
    try:
        vehicles_res = db.table('vehicles').select('*').execute()
        bookings_res = db.table('bookings').select('*').execute()
        customers_res = db.table('customers').select('*').execute()
        payments_res = db.table('payments').select('amount, status, created_at').execute()

        total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0

        monthly = {}
        for p in (payments_res.data or []):
            if p['status'] == 'paid' and p.get('created_at'):
                month = p['created_at'][:7]
                monthly[month] = monthly.get(month, 0) + p['amount']

        sorted_months = sorted(monthly.keys())
        chart_labels = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in sorted_months]
        chart_data = [monthly[m] for m in sorted_months]

        all_bookings = bookings_res.data or []
        bookings_with_vehicles = db.table('bookings').select('*, vehicles(type)').execute()
        type_counts = {'car': 0, 'bike': 0, 'scooter': 0}
        for b in (bookings_with_vehicles.data or []):
            if b.get('vehicles') and b['vehicles'].get('type'):
                t = b['vehicles']['type']
                type_counts[t] = type_counts.get(t, 0) + 1

        avg_booking = int(total_revenue / len(all_bookings)) if all_bookings else 0

        return render_template('analytics.html', total_revenue=total_revenue, total_bookings=len(all_bookings), total_vehicles=len(vehicles_res.data or []), total_customers=len(customers_res.data or []), avg_booking=avg_booking, chart_labels=chart_labels, chart_data=chart_data, type_car=type_counts['car'], type_bike=type_counts['bike'], type_scooter=type_counts['scooter'])
    except Exception as e:
        return render_template('analytics.html')

@app.route('/rentals')
@login_required
def rentals():
    try:
        active = db.table('bookings').select('*, vehicles(name, type), customers(name)').in_('status', ['active', 'pending']).order('created_at', desc=True).execute()
        past = db.table('bookings').select('*, vehicles(name, type), customers(name)').in_('status', ['completed', 'overdue']).order('created_at', desc=True).execute()
        return render_template('rentals.html', active_rentals=active.data or [], past_rentals=past.data or [])
    except Exception as e:
        return render_template('rentals.html')

@app.route('/settings')
@login_required
def settings(): return render_template('settings.html')

@app.route('/notifications')
@login_required
def notifications(): return render_template('notifications.html')

@app.route('/help')
@login_required
def help_page(): return render_template('help.html')

# ══════════════════════════════════════
# ADMIN API ROUTES
# ══════════════════════════════════════
@app.route('/api/vehicles/add', methods=['POST'])
@login_required
def add_vehicle():
    data = request.json
    result = db.table('vehicles').insert({
        'name': data['name'], 'type': data['type'], 'brand': data.get('brand', ''),
        'year': data.get('year'), 'fuel': data.get('fuel', 'Petrol'),
        'daily_rate': data['daily_rate'], 'status': 'available'
    }).execute()
    return jsonify({'success': True, 'vehicle': result.data})

@app.route('/api/customers/add', methods=['POST'])
@login_required
def add_customer():
    data = request.json
    result = db.table('customers').insert({
        'name': data['name'], 'email': data['email'], 'phone': data.get('phone', ''), 'city': data.get('city', '')
    }).execute()
    return jsonify({'success': True, 'customer': result.data})

@app.route('/api/customers/create-with-password', methods=['POST'])
@login_required
def create_customer_with_password():
    data = request.json
    if not data.get('password') or len(data['password']) < 8: return jsonify({'success': False, 'error': 'Password must be at least 8 characters'})
    try:
        auth_response = db.auth.sign_up({'email': data['email'], 'password': data['password']})
        customer_res = db.table('customers').insert({'name': data['name'], 'email': data['email'], 'phone': data.get('phone', ''), 'city': data.get('city', ''), 'total_rentals': 0, 'total_spent': 0}).execute()
        db.table('profiles').insert({'id': auth_response.user.id, 'role': 'customer', 'customer_id': customer_res.data[0]['id']}).execute()
        return jsonify({'success': True, 'customer': customer_res.data[0]})
    except Exception as e:
        return jsonify({'success': False, 'error': 'Account exists or database error.'})

@app.route('/api/bookings/add', methods=['POST'])
@login_required
def add_booking():
    data = request.json
    ref = 'BK-' + ''.join(random.choices(string.digits, k=4))
    result = db.table('bookings').insert({
        'booking_ref': ref, 'customer_id': data['customer_id'], 'vehicle_id': data['vehicle_id'],
        'start_date': data['start_date'], 'end_date': data['end_date'], 'total_amount': data['total_amount'],
        'status': 'pending', 'payment_status': 'pending'
    }).execute()
    db.table('vehicles').update({'status': 'rented'}).eq('id', data['vehicle_id']).execute()
    return jsonify({'success': True, 'booking': result.data})

@app.route('/api/payments/add', methods=['POST'])
@login_required
def add_payment():
    try:
        data = request.json
        ref = '#TXN-' + ''.join(random.choices(string.digits, k=4))
        cust_id = data.get('customer_id') if data.get('customer_id') != '' else None
        result = db.table('payments').insert({
            'transaction_ref': ref, 'booking_id': data['booking_id'], 'customer_id': cust_id,
            'amount': data['amount'], 'method': data['method'], 'status': 'paid'
        }).execute()
        db.table('bookings').update({'payment_status': 'paid', 'payment_method': data['method']}).eq('id', data['booking_id']).execute()
        return jsonify({'success': True, 'payment': result.data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customers/list')
@login_required
def list_customers():
    res = db.table('customers').select('id, name').order('name').execute()
    return jsonify({'customers': res.data or []})

@app.route('/api/vehicles/list')
@login_required
def list_vehicles():
    res = db.table('vehicles').select('id, name, type, daily_rate').eq('status', 'available').order('name').execute()
    return jsonify({'vehicles': res.data or []})

@app.route('/api/vehicles/<vehicle_id>', methods=['GET'])
@login_required
def get_vehicle(vehicle_id):
    res = db.table('vehicles').select('*').eq('id', vehicle_id).execute()
    return jsonify({'vehicle': res.data[0]}) if res.data else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/vehicles/<vehicle_id>/update', methods=['POST'])
@login_required
def update_vehicle(vehicle_id):
    data = request.json
    db.table('vehicles').update({'name': data['name'], 'type': data['type'], 'brand': data.get('brand', ''), 'year': data.get('year'), 'fuel': data.get('fuel', 'Petrol'), 'daily_rate': data['daily_rate'], 'status': data['status']}).eq('id', vehicle_id).execute()
    return jsonify({'success': True})

@app.route('/api/vehicles/<vehicle_id>/delete', methods=['POST'])
@login_required
def delete_vehicle(vehicle_id):
    db.table('bookings').update({'vehicle_id': None}).eq('vehicle_id', vehicle_id).execute()
    db.table('vehicles').delete().eq('id', vehicle_id).execute()
    return jsonify({'success': True})

@app.route('/api/customers/<customer_id>', methods=['GET'])
@login_required
def get_customer(customer_id):
    res = db.table('customers').select('*').eq('id', customer_id).execute()
    if not res.data: return jsonify({'error': 'Not found'}), 404
    bookings = db.table('bookings').select('*, vehicles(name, type)').eq('customer_id', customer_id).order('created_at', desc=True).execute()
    return jsonify({'customer': res.data[0], 'bookings': bookings.data or []})

@app.route('/api/customers/<customer_id>/update', methods=['POST'])
@login_required
def update_customer(customer_id):
    data = request.json
    db.table('customers').update({'name': data['name'], 'email': data['email'], 'phone': data.get('phone', ''), 'city': data.get('city', '')}).eq('id', customer_id).execute()
    return jsonify({'success': True})

@app.route('/api/customers/<customer_id>/delete', methods=['POST'])
@login_required
def delete_customer(customer_id):
    db.table('payments').delete().eq('customer_id', customer_id).execute()
    db.table('bookings').update({'customer_id': None}).eq('customer_id', customer_id).execute()
    db.table('customers').delete().eq('id', customer_id).execute()
    return jsonify({'success': True})

@app.route('/api/bookings/<booking_id>', methods=['GET'])
@login_required
def get_booking(booking_id):
    res = db.table('bookings').select('*, customers(name, phone), vehicles(name, type)').eq('id', booking_id).execute()
    return jsonify({'booking': res.data[0]}) if res.data else (jsonify({'error': 'Not found'}), 404)

@app.route('/api/bookings/<booking_id>/status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    new_status = request.json['status']
    db.table('bookings').update({'status': new_status}).eq('id', booking_id).execute()
    booking = db.table('bookings').select('vehicle_id').eq('id', booking_id).execute()
    if booking.data and booking.data[0].get('vehicle_id'):
        if new_status == 'completed': db.table('vehicles').update({'status': 'available'}).eq('id', booking.data[0]['vehicle_id']).execute()
        if new_status == 'active': db.table('vehicles').update({'status': 'rented'}).eq('id', booking.data[0]['vehicle_id']).execute()
    return jsonify({'success': True})

@app.route('/api/bookings/<booking_id>/delete', methods=['POST'])
@login_required
def delete_admin_booking(booking_id):
    booking = db.table('bookings').select('vehicle_id, status').eq('id', booking_id).execute()
    if booking.data and booking.data[0].get('vehicle_id') and booking.data[0]['status'] in ['active', 'pending']:
        db.table('vehicles').update({'status': 'available'}).eq('id', booking.data[0]['vehicle_id']).execute()
    db.table('payments').delete().eq('booking_id', booking_id).execute()
    db.table('bookings').delete().eq('id', booking_id).execute()
    return jsonify({'success': True})

# ══════════════════════════════════════
# CUSTOMER PORTAL PAGES
# ══════════════════════════════════════
@app.route('/customer/dashboard')
@customer_login_required
def customer_dashboard():
    try:
        customer_id = session['customer']['id']
        bookings = db.table('bookings').select('*, vehicles(name, type, daily_rate, brand, year)').eq('customer_id', customer_id).order('created_at', desc=True).execute()
        active_bookings = [b for b in (bookings.data or []) if b['status'] in ['active', 'pending']]
        past_bookings   = [b for b in (bookings.data or []) if b['status'] in ['completed', 'overdue', 'cancelled']]
        total_spent = sum(b['total_amount'] for b in (bookings.data or []) if b['status'] == 'completed')
        return render_template('customer/dashboard.html', active_bookings=active_bookings, past_bookings=past_bookings, total_spent=total_spent, total_bookings=len(bookings.data or []), current_page='home')
    except Exception as e:
        return render_template('customer/dashboard.html', active_bookings=[], past_bookings=[], total_spent=0, total_bookings=0, current_page='home')

@app.route('/customer/vehicles')
@customer_login_required
def customer_vehicles():
    try:
        type_filter = request.args.get('type', 'all')
        status_filter = request.args.get('status', 'all')
        query = db.table('vehicles').select('*').order('name')
        if type_filter != 'all': query = query.eq('type', type_filter)
        if status_filter == 'available': query = query.eq('status', 'available')
        vehicles_res = query.execute()
        return render_template('customer/vehicles.html', vehicles=vehicles_res.data or [], type_filter=type_filter, status_filter=status_filter, current_page='vehicles')
    except Exception:
        return render_template('customer/vehicles.html', vehicles=[], type_filter='all', status_filter='all', current_page='vehicles')

@app.route('/customer/bookings')
@customer_login_required
def customer_bookings():
    try:
        customer_id = session['customer']['id']
        status = request.args.get('status', 'all')
        query = db.table('bookings').select('*, vehicles(name, type, daily_rate, fuel, year)').eq('customer_id', customer_id).order('created_at', desc=True)
        if status != 'all': query = query.eq('status', status)
        bookings = query.execute()
        return render_template('customer/bookings.html', bookings=bookings.data or [], active_filter=status, current_page='bookings')
    except Exception:
        return render_template('customer/bookings.html', bookings=[], active_filter='all', current_page='bookings')

@app.route('/customer/booking/<booking_id>')
@customer_login_required
def customer_booking_detail(booking_id):
    cid = session['customer']['id']
    booking = db.table('bookings').select('*, vehicles(name,type,daily_rate,fuel,year,brand)').eq('id', booking_id).eq('customer_id', cid).execute()
    if not booking.data: return redirect(url_for('customer_bookings'))
    b = booking.data[0]
    payments = db.table('payments').select('*').eq('booking_id', booking_id).execute()
    
    try:
        days = (datetime.strptime(b['end_date'], '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        if days == 0: days = 1
    except: days = 1
        
    daily = b['vehicles']['daily_rate'] if b.get('vehicles') else 0
    base = daily * days
    tax = round(base * 0.18, 2)
    return render_template('customer/booking_detail.html', booking=b, payments=payments.data or [], days=days, base_rate=base, tax=tax, total=base+tax)

@app.route('/customer/profile', methods=['GET', 'POST'])
@customer_login_required
def customer_profile():
    cid = session['customer']['id']
    if request.method == 'POST':
        data = request.form
        db.table('customers').update({
            'name': data.get('name'), 'phone': data.get('phone'), 'city': data.get('city'),
            'license_number': data.get('license_number'), 'license_expiry': data.get('license_expiry') or None,
            'preferred_payment': data.get('preferred_payment'), 'profile_complete': True
        }).eq('id', cid).execute()
        if data.get('name'):
            session['customer']['name'] = data.get('name')
            session.modified = True
        return redirect(url_for('customer_profile') + '?saved=1')
        
    customer = db.table('customers').select('*').eq('id', cid).execute()
    bookings = db.table('bookings').select('*').eq('customer_id', cid).execute()
    total_spent = sum(b['total_amount'] for b in (bookings.data or []) if b['status'] == 'completed')
    
    return render_template('customer/profile.html', customer=customer.data[0] if customer.data else session['customer'], total_bookings=len(bookings.data or []), total_spent=total_spent, saved=request.args.get('saved'), current_page='profile')

@app.route('/customer/wishlist')
@customer_login_required
def customer_wishlist():
    cid = session['customer']['id']
    wishlist = db.table('wishlists').select('*, vehicles(id,name,type,daily_rate,fuel,year,status)').eq('customer_id', cid).execute()
    all_vehicles = db.table('vehicles').select('*').eq('status', 'available').execute()
    wishlisted_ids = [w['vehicle_id'] for w in (wishlist.data or [])]
    return render_template('customer/wishlist.html', wishlist=wishlist.data or [], all_vehicles=all_vehicles.data or [], wishlisted_ids=wishlisted_ids)

@app.route('/customer/reviews')
@customer_login_required
def customer_reviews():
    cid = session['customer']['id']
    completed = db.table('bookings').select('*, vehicles(id,name,type)').eq('customer_id', cid).eq('status', 'completed').execute()
    existing = db.table('reviews').select('*').eq('customer_id', cid).execute()
    reviewed_booking_ids = [r['booking_id'] for r in (existing.data or [])]
    return render_template('customer/reviews.html', completed=completed.data or [], existing_reviews=existing.data or [], reviewed_booking_ids=reviewed_booking_ids)

@app.route('/customer/invoices')
@customer_login_required
def customer_invoices():
    cid = session['customer']['id']
    bookings = db.table('bookings').select('*, vehicles(name,type)').eq('customer_id', cid).in_('status', ['active', 'completed']).order('created_at', desc=True).execute()
    return render_template('customer/invoices.html', bookings=bookings.data or [])

@app.route('/customer/invoice/<booking_id>/pdf')
@customer_login_required
def download_invoice(booking_id):
    from weasyprint import HTML
    cid = session['customer']['id']
    booking = db.table('bookings').select('*, vehicles(name,type,daily_rate), customers(name,email,phone)').eq('id', booking_id).eq('customer_id', cid).execute()
    if not booking.data: return redirect(url_for('customer_invoices'))
    b = booking.data[0]
    
    try:
        days = (datetime.strptime(b['end_date'], '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        if days == 0: days = 1
    except: days = 1
        
    daily = b['vehicles']['daily_rate'] if b.get('vehicles') else 0
    base = daily * days
    tax = round(base * 0.18, 2)
    html_str = render_template('customer/invoice_pdf.html', booking=b, days=days, base=base, tax=tax, total=base+tax, generated=datetime.now().strftime('%d %b %Y'))
    pdf = HTML(string=html_str).write_pdf()
    return app.response_class(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'attachment; filename=invoice-{b["booking_ref"]}.pdf'})

# ══════════════════════════════════════
# CUSTOMER API ROUTES (Booking, Canceling, etc.)
# ══════════════════════════════════════
@app.route('/api/customer/bookings/create', methods=['POST'])
@customer_login_required
def customer_create_booking():
    try:
        data = request.json
        customer_id = session['customer']['id']
        vehicle = db.table('vehicles').select('status, daily_rate, name').eq('id', data['vehicle_id']).execute()
        
        if not vehicle.data: return jsonify({'success': False, 'error': 'Vehicle not found'}), 404
        if vehicle.data[0]['status'] != 'available': return jsonify({'success': False, 'error': 'Vehicle is no longer available'}), 400

        ref = 'BK-' + ''.join(random.choices(string.digits, k=4))
        db.table('bookings').insert({
            'booking_ref': ref, 'customer_id': customer_id, 'vehicle_id': data['vehicle_id'],
            'start_date': data['start_date'], 'end_date': data['end_date'], 'total_amount': data['total_amount'],
            'status': 'pending', 'payment_status': 'pending'
        }).execute()
        db.table('vehicles').update({'status': 'rented'}).eq('id', data['vehicle_id']).execute()
        return jsonify({'success': True, 'booking_ref': ref})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customer/bookings/<booking_id>/cancel', methods=['POST'])
@customer_login_required
def customer_cancel_booking(booking_id):
    try:
        cid = session['customer']['id']
        booking = db.table('bookings').select('customer_id, vehicle_id, status, start_date, booking_ref').eq('id', booking_id).execute()
        
        if not booking.data: return jsonify({'success': False, 'error': 'Booking not found'}), 404
        b = booking.data[0]
        if b['customer_id'] != cid: return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        if b['status'] in ['completed', 'cancelled']: return jsonify({'success': False, 'error': 'Cannot cancel this booking'}), 400

        db.table('bookings').update({'status': 'cancelled'}).eq('id', booking_id).execute()
        if b.get('vehicle_id'): db.table('vehicles').update({'status': 'available'}).eq('id', b['vehicle_id']).execute()
        
        customer = db.table('customers').select('email,name').eq('id', cid).execute()
        if customer.data:
            send_email(customer.data[0]['email'], 'Booking Cancelled — QuickRent',
                f"<p>Hi {customer.data[0]['name']},</p><p>Your booking <strong>{b['booking_ref']}</strong> has been cancelled.</p><p>If you paid, refund will be processed in 5–7 business days.</p><p>— QuickRent Team</p>")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customer/bookings/<booking_id>/extend', methods=['POST'])
@customer_login_required
def extend_booking(booking_id):
    cid = session['customer']['id']
    data = request.json
    new_end = data.get('new_end_date')
    booking = db.table('bookings').select('*, vehicles(daily_rate)').eq('id', booking_id).eq('customer_id', cid).execute()
    if not booking.data: return jsonify({'success': False, 'error': 'Not found'})
    b = booking.data[0]
    
    try:
        old_days = (datetime.strptime(b['end_date'], '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        new_days = (datetime.strptime(new_end, '%Y-%m-%d') - datetime.strptime(b['start_date'], '%Y-%m-%d')).days
        if new_days <= old_days: return jsonify({'success': False, 'error': 'New date must be after current end date'})
        
        daily = b['vehicles']['daily_rate']
        extra_amount = (new_days - old_days) * daily * 1.18
        new_total = round(b['total_amount'] + extra_amount, 2)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
        
    db.table('bookings').update({'end_date': new_end, 'total_amount': new_total}).eq('id', booking_id).execute()
    return jsonify({'success': True, 'new_total': new_total})

@app.route('/api/customer/wishlist/toggle', methods=['POST'])
@customer_login_required
def toggle_wishlist():
    cid = session['customer']['id']
    vehicle_id = request.json.get('vehicle_id')
    existing = db.table('wishlists').select('id').eq('customer_id', cid).eq('vehicle_id', vehicle_id).execute()
    if existing.data:
        db.table('wishlists').delete().eq('id', existing.data[0]['id']).execute()
        return jsonify({'success': True, 'action': 'removed'})
    db.table('wishlists').insert({'customer_id': cid, 'vehicle_id': vehicle_id}).execute()
    return jsonify({'success': True, 'action': 'added'})

@app.route('/api/customer/review/submit', methods=['POST'])
@customer_login_required
def submit_review():
    cid = session['customer']['id']
    data = request.json
    existing = db.table('reviews').select('id').eq('booking_id', data['booking_id']).eq('customer_id', cid).execute()
    if existing.data: return jsonify({'success': False, 'error': 'Already reviewed'})
    db.table('reviews').insert({'customer_id': cid, 'vehicle_id': data['vehicle_id'], 'booking_id': data['booking_id'], 'rating': int(data['rating']), 'comment': data.get('comment', '')}).execute()
    return jsonify({'success': True})

@app.route('/api/customer/profile/update', methods=['POST'])
@customer_login_required
def customer_update_profile_api():
    try:
        cid = session['customer']['id']
        data = request.json
        db.table('customers').update({'name': data['name'], 'phone': data.get('phone', ''), 'city': data.get('city', '')}).eq('id', cid).execute()
        session['customer']['name'] = data['name']
        session.modified = True
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# RAZORPAY
@app.route('/api/customer/payment/create', methods=['POST'])
@customer_login_required
def create_razorpay_order():
    try:
        import razorpay
        data = request.json
        amount = data['amount']
        rz_key_id = os.environ.get('RAZORPAY_KEY_ID')
        client = razorpay.Client(auth=(rz_key_id, os.environ.get('RAZORPAY_KEY_SECRET')))
        order = client.order.create({'amount': amount * 100, 'currency': 'INR', 'receipt': data['booking_id'][:20], 'payment_capture': 1})
        return jsonify({'success': True, 'order_id': order['id'], 'key_id': rz_key_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/customer/payment/verify', methods=['POST'])
@customer_login_required
def verify_razorpay_payment():
    try:
        import hmac, hashlib
        data = request.json
        rz_key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
        body = data['razorpay_order_id'] + '|' + data['razorpay_payment_id']
        expected = hmac.new(rz_key_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        
        if expected != data['razorpay_signature']: return jsonify({'success': False, 'error': 'Invalid signature'}), 400

        ref = '#TXN-' + ''.join(random.choices(string.digits, k=6))
        db.table('payments').insert({'transaction_ref': ref, 'booking_id': data['booking_id'], 'customer_id': session['customer']['id'], 'amount': data['amount'], 'method': 'Razorpay', 'status': 'paid'}).execute()
        db.table('bookings').update({'payment_status': 'paid', 'payment_method': 'Razorpay'}).eq('id', data['booking_id']).execute()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ══════════════════════════════════════
# ERROR HANDLERS
# ══════════════════════════════════════
@app.errorhandler(404)
def not_found(e): return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e): return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)