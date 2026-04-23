from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY, FLASK_SECRET_KEY
from functools import wraps

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

db: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════
# AUTH DECORATOR
# ══════════════════════════════════════
# @login_required is placed above any route that needs protection.
# wraps(f) preserves the original function name — required by Flask.
# If session has no 'user' key, redirect to login page.
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════
# LOGIN
# ══════════════════════════════════════
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in send straight to dashboard
    if 'user' in session:
        return redirect(url_for('dashboard'))

    error = None

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        try:
            # sign_in_with_password sends credentials to Supabase Auth
            # On success it returns a session with user details
            response = db.auth.sign_in_with_password({
                'email': email,
                'password': password
            })

            # Store user info in Flask session
            # session is a dictionary that persists across requests
            # It is encrypted using your FLASK_SECRET_KEY
            session['user'] = {
                'id': response.user.id,
                'email': response.user.email
            }
            session['access_token'] = response.session.access_token

            return redirect(url_for('dashboard'))

        except Exception as e:
            # Supabase raises an exception for wrong credentials
            error = 'Invalid email or password. Please try again.'

    return render_template('login.html', error=error)


# ══════════════════════════════════════
# LOGOUT
# ══════════════════════════════════════
@app.route('/logout')
def logout():
    # clear() removes everything from the session dictionary
    session.clear()
    return redirect(url_for('login'))


# ══════════════════════════════════════
# SIDEBAR COMPONENT
# ══════════════════════════════════════
@app.route('/components/sidebar')
@login_required
def sidebar_component():
    return render_template('components/sidebar.html')


# ══════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════
@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    try:
        vehicles_res = db.table('vehicles').select('*', count='exact').execute()
        active_bookings = db.table('bookings').select('*', count='exact').eq('status', 'active').execute()
        pending_bookings = db.table('bookings').select('*', count='exact').eq('status', 'pending').execute()
        overdue_bookings = db.table('bookings').select('*', count='exact').eq('status', 'overdue').execute()
        available = db.table('vehicles').select('*', count='exact').eq('status', 'available').execute()
        rented = db.table('vehicles').select('*', count='exact').eq('status', 'rented').execute()
        maintenance = db.table('vehicles').select('*', count='exact').eq('status', 'maintenance').execute()

        recent_bookings = db.table('bookings')\
            .select('*, customers(name), vehicles(name, type)')\
            .order('created_at', desc=True)\
            .limit(5)\
            .execute()

        payments_res = db.table('payments').select('amount').eq('status', 'paid').execute()
        total_revenue = sum(p['amount'] for p in payments_res.data) if payments_res.data else 0

        return render_template('dashboard.html',
            total_vehicles=vehicles_res.count or 0,
            total_revenue=total_revenue,
            available_vehicles=available.count or 0,
            rented_vehicles=rented.count or 0,
            maintenance_vehicles=maintenance.count or 0,
            active_bookings=active_bookings.count or 0,
            pending_bookings=pending_bookings.count or 0,
            overdue_bookings=overdue_bookings.count or 0,
            recent_bookings=recent_bookings.data or [],
            user=session.get('user')
        )
    except Exception as e:
        print('Dashboard error:', e)
        return render_template('dashboard.html',
            total_vehicles=0, total_revenue=0,
            available_vehicles=0, rented_vehicles=0, maintenance_vehicles=0,
            active_bookings=0, pending_bookings=0, overdue_bookings=0,
            recent_bookings=[], user=session.get('user')
        )


# ══════════════════════════════════════
# BOOKINGS
# ══════════════════════════════════════
@app.route('/bookings')
@login_required
def bookings():
    try:
        status_filter = request.args.get('status', 'all')
        query = db.table('bookings')\
            .select('*, customers(name, phone), vehicles(name, type)')\
            .order('created_at', desc=True)
        if status_filter != 'all':
            query = query.eq('status', status_filter)
        bookings_res = query.execute()

        counts = {
            'all': db.table('bookings').select('*', count='exact').execute().count or 0,
            'active': db.table('bookings').select('*', count='exact').eq('status', 'active').execute().count or 0,
            'pending': db.table('bookings').select('*', count='exact').eq('status', 'pending').execute().count or 0,
            'overdue': db.table('bookings').select('*', count='exact').eq('status', 'overdue').execute().count or 0,
            'completed': db.table('bookings').select('*', count='exact').eq('status', 'completed').execute().count or 0,
        }
        return render_template('bookings.html',
            bookings=bookings_res.data or [],
            counts=counts,
            active_filter=status_filter,
            user=session.get('user')
        )
    except Exception as e:
        print('Bookings error:', e)
        return render_template('bookings.html',
            bookings=[], counts={'all':0,'active':0,'pending':0,'overdue':0,'completed':0},
            active_filter='all', user=session.get('user')
        )


# ══════════════════════════════════════
# VEHICLES
# ══════════════════════════════════════
@app.route('/vehicles')
@login_required
def vehicles():
    try:
        type_filter = request.args.get('type', 'all')
        query = db.table('vehicles').select('*').order('created_at', desc=True)
        if type_filter == 'car':
            query = query.eq('type', 'car')
        elif type_filter == 'bike':
            query = query.eq('type', 'bike')
        elif type_filter == 'unavailable':
            query = query.neq('status', 'available')
        vehicles_res = query.execute()
        return render_template('vehicles.html',
            vehicles=vehicles_res.data or [],
            active_filter=type_filter,
            user=session.get('user')
        )
    except Exception as e:
        print('Vehicles error:', e)
        return render_template('vehicles.html',
            vehicles=[], active_filter='all', user=session.get('user')
        )


# ══════════════════════════════════════
# CUSTOMERS
# ══════════════════════════════════════
@app.route('/customers')
@login_required
def customers():
    try:
        customers_res = db.table('customers').select('*').order('created_at', desc=True).execute()
        counts = {'total': db.table('customers').select('*', count='exact').execute().count or 0}
        return render_template('customers.html',
            customers=customers_res.data or [],
            counts=counts,
            user=session.get('user')
        )
    except Exception as e:
        print('Customers error:', e)
        return render_template('customers.html',
            customers=[], counts={'total':0}, user=session.get('user')
        )


# ══════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════
@app.route('/payments')
@login_required
def payments():
    try:
        status_filter = request.args.get('status', 'all')
        query = db.table('payments')\
            .select('*, bookings(booking_ref), customers(name)')\
            .order('created_at', desc=True)
        if status_filter != 'all':
            query = query.eq('status', status_filter)
        payments_res = query.execute()

        all_payments = db.table('payments').select('amount, status').execute()
        total_collected = sum(p['amount'] for p in all_payments.data if p['status'] == 'paid') if all_payments.data else 0
        total_pending = sum(p['amount'] for p in all_payments.data if p['status'] == 'pending') if all_payments.data else 0

        return render_template('payments.html',
            payments=payments_res.data or [],
            active_filter=status_filter,
            total_collected=total_collected,
            total_pending=total_pending,
            user=session.get('user')
        )
    except Exception as e:
        print('Payments error:', e)
        return render_template('payments.html',
            payments=[], active_filter='all',
            total_collected=0, total_pending=0, user=session.get('user')
        )


# ══════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════
@app.route('/analytics')
@login_required
def analytics():
    try:
        vehicles_res = db.table('vehicles').select('*').execute()
        bookings_res = db.table('bookings').select('*').execute()
        customers_res = db.table('customers').select('*').execute()
        payments_res = db.table('payments').select('amount, status').execute()
        total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0
        return render_template('analytics.html',
            total_revenue=total_revenue,
            total_bookings=len(bookings_res.data or []),
            total_vehicles=len(vehicles_res.data or []),
            total_customers=len(customers_res.data or []),
            user=session.get('user')
        )
    except Exception as e:
        print('Analytics error:', e)
        return render_template('analytics.html',
            total_revenue=0, total_bookings=0,
            total_vehicles=0, total_customers=0, user=session.get('user')
        )


# ══════════════════════════════════════
# REMAINING PAGES
# ══════════════════════════════════════
@app.route('/rentals')
@login_required
def rentals():
    try:
        active = db.table('bookings').select('*, vehicles(name, type), customers(name)')\
            .in_('status', ['active', 'pending']).order('created_at', desc=True).execute()
        past = db.table('bookings').select('*, vehicles(name, type), customers(name)')\
            .in_('status', ['completed', 'overdue']).order('created_at', desc=True).execute()
        return render_template('rentals.html',
            active_rentals=active.data or [],
            past_rentals=past.data or [],
            user=session.get('user')
        )
    except Exception as e:
        print('Rentals error:', e)
        return render_template('rentals.html',
            active_rentals=[], past_rentals=[], user=session.get('user')
        )

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html', user=session.get('user'))

@app.route('/notifications')
@login_required
def notifications():
    return render_template('notifications.html', user=session.get('user'))

@app.route('/help')
@login_required
def help_page():
    return render_template('help.html', user=session.get('user'))


# ══════════════════════════════════════
# API ROUTES
# ══════════════════════════════════════
@app.route('/api/vehicles/add', methods=['POST'])
@login_required
def add_vehicle():
    data = request.json
    result = db.table('vehicles').insert({
        'name': data['name'], 'type': data['type'],
        'brand': data.get('brand', ''), 'year': data.get('year'),
        'fuel': data.get('fuel', 'Petrol'),
        'daily_rate': data['daily_rate'], 'status': 'available'
    }).execute()
    return jsonify({'success': True, 'vehicle': result.data})

@app.route('/api/customers/add', methods=['POST'])
@login_required
def add_customer():
    data = request.json
    result = db.table('customers').insert({
        'name': data['name'], 'email': data['email'],
        'phone': data.get('phone', ''), 'city': data.get('city', '')
    }).execute()
    return jsonify({'success': True, 'customer': result.data})

@app.route('/api/bookings/add', methods=['POST'])
@login_required
def add_booking():
    data = request.json
    import random, string
    ref = 'BK-' + ''.join(random.choices(string.digits, k=4))
    result = db.table('bookings').insert({
        'booking_ref': ref,
        'customer_id': data['customer_id'],
        'vehicle_id': data['vehicle_id'],
        'start_date': data['start_date'],
        'end_date': data['end_date'],
        'total_amount': data['total_amount'],
        'status': 'pending', 'payment_status': 'pending'
    }).execute()
    db.table('vehicles').update({'status': 'rented'}).eq('id', data['vehicle_id']).execute()
    return jsonify({'success': True, 'booking': result.data})

@app.route('/api/bookings/status', methods=['POST'])
@login_required
def update_booking_status():
    data = request.json
    db.table('bookings').update({'status': data['status']}).eq('id', data['booking_id']).execute()
    if data['status'] == 'completed':
        booking = db.table('bookings').select('vehicle_id').eq('id', data['booking_id']).execute()
        if booking.data:
            db.table('vehicles').update({'status': 'available'}).eq('id', booking.data[0]['vehicle_id']).execute()
    return jsonify({'success': True})

@app.route('/api/customers/list')
@login_required
def list_customers():
    res = db.table('customers').select('id, name').order('name').execute()
    return jsonify({'customers': res.data or []})

@app.route('/api/vehicles/list')
@login_required
def list_vehicles():
    res = db.table('vehicles').select('id, name, type, daily_rate')\
        .eq('status', 'available').order('name').execute()
    return jsonify({'vehicles': res.data or []})

if __name__ == '__main__':
    app.run(debug=True, port=5000)