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
        from datetime import datetime
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

        # All paid payments
        payments_res = db.table('payments').select('amount, status, created_at').execute()
        total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0

        # Monthly revenue — payments created this month
        monthly_revenue = sum(
            p['amount'] for p in payments_res.data
            if p['status'] == 'paid' and p.get('created_at', '')[:7] == current_month
        ) if payments_res.data else 0

        return render_template('dashboard.html',
            total_vehicles=vehicles_res.count or 0,
            total_revenue=total_revenue,
            monthly_revenue=monthly_revenue,
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
            total_vehicles=0, total_revenue=0, monthly_revenue=0,
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
        from datetime import datetime
        vehicles_res = db.table('vehicles').select('*').execute()
        bookings_res = db.table('bookings').select('*').execute()
        customers_res = db.table('customers').select('*').execute()
        payments_res = db.table('payments').select('amount, status, created_at').execute()

        total_revenue = sum(p['amount'] for p in payments_res.data if p['status'] == 'paid') if payments_res.data else 0

        # Monthly revenue breakdown
        monthly = {}
        for p in (payments_res.data or []):
            if p['status'] == 'paid' and p.get('created_at'):
                month = p['created_at'][:7]  # e.g. "2026-04"
                monthly[month] = monthly.get(month, 0) + p['amount']

        # Sort months and prepare for Chart.js
        sorted_months = sorted(monthly.keys())
        chart_labels = [datetime.strptime(m, '%Y-%m').strftime('%b %Y') for m in sorted_months]
        chart_data = [monthly[m] for m in sorted_months]

        # Booking type breakdown
        all_bookings = bookings_res.data or []
        bookings_with_vehicles = db.table('bookings')\
            .select('*, vehicles(type)').execute()
        type_counts = {'car': 0, 'bike': 0, 'scooter': 0}
        for b in (bookings_with_vehicles.data or []):
            if b.get('vehicles') and b['vehicles'].get('type'):
                t = b['vehicles']['type']
                type_counts[t] = type_counts.get(t, 0) + 1

        avg_booking = int(total_revenue / len(all_bookings)) if all_bookings else 0

        return render_template('analytics.html',
            total_revenue=total_revenue,
            total_bookings=len(all_bookings),
            total_vehicles=len(vehicles_res.data or []),
            total_customers=len(customers_res.data or []),
            avg_booking=avg_booking,
            chart_labels=chart_labels,
            chart_data=chart_data,
            type_car=type_counts['car'],
            type_bike=type_counts['bike'],
            type_scooter=type_counts['scooter'],
            user=session.get('user')
        )
    except Exception as e:
        print('Analytics error:', e)
        return render_template('analytics.html',
            total_revenue=0, total_bookings=0, total_vehicles=0,
            total_customers=0, avg_booking=0,
            chart_labels=[], chart_data=[],
            type_car=0, type_bike=0, type_scooter=0,
            user=session.get('user')
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

# ══════════════════════════════════════
# VEHICLE — GET, UPDATE, DELETE
# ══════════════════════════════════════
@app.route('/api/vehicles/<vehicle_id>', methods=['GET'])
@login_required
def get_vehicle(vehicle_id):
    res = db.table('vehicles').select('*').eq('id', vehicle_id).execute()
    if not res.data:
        return jsonify({'error': 'Vehicle not found'}), 404
    return jsonify({'vehicle': res.data[0]})

@app.route('/api/vehicles/<vehicle_id>/update', methods=['POST'])
@login_required
def update_vehicle(vehicle_id):
    data = request.json
    db.table('vehicles').update({
        'name': data['name'],
        'type': data['type'],
        'brand': data.get('brand', ''),
        'year': data.get('year'),
        'fuel': data.get('fuel', 'Petrol'),
        'daily_rate': data['daily_rate'],
        'status': data['status']
    }).eq('id', vehicle_id).execute()
    return jsonify({'success': True})

@app.route('/api/vehicles/<vehicle_id>/delete', methods=['POST'])
@login_required
def delete_vehicle(vehicle_id):
    try:
        # First nullify vehicle_id in any bookings that reference this vehicle
        # This prevents the foreign key constraint error
        db.table('bookings').update({'vehicle_id': None}).eq('vehicle_id', vehicle_id).execute()
        # Now safe to delete the vehicle
        db.table('vehicles').delete().eq('id', vehicle_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        print('Delete vehicle error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ══════════════════════════════════════
# CUSTOMER — GET, UPDATE, DELETE
# ══════════════════════════════════════
@app.route('/api/customers/<customer_id>', methods=['GET'])
@login_required
def get_customer(customer_id):
    res = db.table('customers').select('*').eq('id', customer_id).execute()
    if not res.data:
        return jsonify({'error': 'Customer not found'}), 404
    # Also fetch their booking history
    bookings = db.table('bookings')\
        .select('*, vehicles(name, type)')\
        .eq('customer_id', customer_id)\
        .order('created_at', desc=True)\
        .execute()
    return jsonify({'customer': res.data[0], 'bookings': bookings.data or []})

@app.route('/api/customers/<customer_id>/update', methods=['POST'])
@login_required
def update_customer(customer_id):
    data = request.json
    db.table('customers').update({
        'name': data['name'],
        'email': data['email'],
        'phone': data.get('phone', ''),
        'city': data.get('city', '')
    }).eq('id', customer_id).execute()
    return jsonify({'success': True})

@app.route('/api/customers/<customer_id>/delete', methods=['POST'])
@login_required
def delete_customer(customer_id):
    try:
        # Delete payments linked to this customer first
        db.table('payments').delete().eq('customer_id', customer_id).execute()
        # Then nullify customer_id in bookings
        db.table('bookings').update({'customer_id': None}).eq('customer_id', customer_id).execute()
        # Now safe to delete the customer
        db.table('customers').delete().eq('id', customer_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        print('Delete customer error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ══════════════════════════════════════
# BOOKING — UPDATE STATUS
# ══════════════════════════════════════
@app.route('/api/bookings/<booking_id>/update', methods=['POST'])
@login_required
def update_booking(booking_id):
    data = request.json
    db.table('bookings').update({
        'status': data['status']
    }).eq('id', booking_id).execute()
    if data['status'] == 'completed':
        booking = db.table('bookings').select('vehicle_id').eq('id', booking_id).execute()
        if booking.data:
            db.table('vehicles').update({'status': 'available'})\
                .eq('id', booking.data[0]['vehicle_id']).execute()
    return jsonify({'success': True})


# ══════════════════════════════════════
# BOOKING — GET SINGLE + UPDATE STATUS + DELETE
# ══════════════════════════════════════
@app.route('/api/bookings/<booking_id>', methods=['GET'])
@login_required
def get_booking(booking_id):
    try:
        res = db.table('bookings')\
            .select('*, customers(name, phone), vehicles(name, type)')\
            .eq('id', booking_id)\
            .execute()
        if not res.data:
            return jsonify({'error': 'Booking not found'}), 404
        return jsonify({'booking': res.data[0]})
    except Exception as e:
        print('Get booking error:', e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/bookings/<booking_id>/status', methods=['POST'])
@login_required
def update_booking_status(booking_id):
    try:
        data = request.json
        new_status = data['status']
        db.table('bookings').update({'status': new_status})\
            .eq('id', booking_id).execute()
        # If completed → free up the vehicle
        if new_status == 'completed':
            booking = db.table('bookings')\
                .select('vehicle_id').eq('id', booking_id).execute()
            if booking.data and booking.data[0].get('vehicle_id'):
                db.table('vehicles')\
                    .update({'status': 'available'})\
                    .eq('id', booking.data[0]['vehicle_id']).execute()
        # If active → mark vehicle as rented
        if new_status == 'active':
            booking = db.table('bookings')\
                .select('vehicle_id').eq('id', booking_id).execute()
            if booking.data and booking.data[0].get('vehicle_id'):
                db.table('vehicles')\
                    .update({'status': 'rented'})\
                    .eq('id', booking.data[0]['vehicle_id']).execute()
        return jsonify({'success': True})
    except Exception as e:
        print('Update booking status error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bookings/<booking_id>/delete', methods=['POST'])
@login_required
def delete_booking(booking_id):
    try:
        # Free vehicle first
        booking = db.table('bookings')\
            .select('vehicle_id, status').eq('id', booking_id).execute()
        if booking.data and booking.data[0].get('vehicle_id'):
            if booking.data[0]['status'] in ['active', 'pending']:
                db.table('vehicles')\
                    .update({'status': 'available'})\
                    .eq('id', booking.data[0]['vehicle_id']).execute()
        # Delete payments linked to this booking
        db.table('payments').delete().eq('booking_id', booking_id).execute()
        # Delete booking
        db.table('bookings').delete().eq('id', booking_id).execute()
        return jsonify({'success': True})
    except Exception as e:
        print('Delete booking error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500

# ══════════════════════════════════════
# PAYMENTS — RECORD NEW PAYMENT
# ══════════════════════════════════════
# ══════════════════════════════════════
# PAYMENTS — RECORD NEW PAYMENT
# ══════════════════════════════════════
@app.route('/api/payments/add', methods=['POST'])
@login_required
def add_payment():
    try:
        data = request.json
        import random, string
        ref = '#TXN-' + ''.join(random.choices(string.digits, k=4))
        
        # FIX: Scrub empty strings to None so Supabase doesn't crash
        cust_id = data.get('customer_id')
        if cust_id == '':
            cust_id = None

        result = db.table('payments').insert({
            'transaction_ref': ref,
            'booking_id': data['booking_id'],
            'customer_id': cust_id,
            'amount': data['amount'],
            'method': data['method'],
            'status': 'paid'
        }).execute()
        
        # Update booking payment status
        db.table('bookings').update({'payment_status': 'paid', 'payment_method': data['method']})\
            .eq('id', data['booking_id']).execute()
            
        return jsonify({'success': True, 'payment': result.data})
    except Exception as e:
        print('Add payment error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500

# ══════════════════════════════════════
# CUSTOMER AUTH DECORATOR
# ══════════════════════════════════════
def customer_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'customer' not in session:
            return redirect(url_for('customer_login'))
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════
# CUSTOMER LOGIN
# ══════════════════════════════════════
@app.route('/customer/login', methods=['GET', 'POST'])
def customer_login():
    # If already logged in as customer go to portal
    if 'customer' in session:
        return redirect(url_for('customer_dashboard'))
    # If admin is logged in send to admin dashboard
    if 'user' in session:
        return redirect(url_for('dashboard'))

    error = None

    if request.method == 'POST':
        email    = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        try:
            # Authenticate with Supabase Auth
            response = db.auth.sign_in_with_password({
                'email': email,
                'password': password
            })

            user_id = response.user.id

            # Check their profile role
            profile = db.table('profiles')\
                .select('role, customer_id')\
                .eq('id', user_id)\
                .execute()

            if not profile.data:
                error = 'Account not found. Please register first.'
            elif profile.data[0]['role'] == 'admin':
                # Admin trying to use customer login — redirect to admin login
                error = 'Please use the admin login page.'
            else:
                # Valid customer — get their customer record
                customer_id = profile.data[0]['customer_id']
                customer = db.table('customers')\
                    .select('*')\
                    .eq('id', customer_id)\
                    .execute()

                if not customer.data:
                    error = 'Customer profile not found. Please contact support.'
                else:
                    # Store customer in session
                    session['customer'] = {
                        'id': customer_id,
                        'user_id': user_id,
                        'name': customer.data[0]['name'],
                        'email': customer.data[0]['email']
                    }
                    return redirect(url_for('customer_dashboard'))

        except Exception as e:
            error = 'Invalid email or password. Please try again.'

    return render_template('customer/login.html', error=error)


# ══════════════════════════════════════
# CUSTOMER REGISTER
# ══════════════════════════════════════
@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if 'customer' in session:
        return redirect(url_for('customer_dashboard'))

    error  = None
    success = None

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
                # Create Supabase Auth user
                auth_response = db.auth.sign_up({
                    'email': email,
                    'password': password
                })

                user_id = auth_response.user.id

                # Create customer record in customers table
                customer_res = db.table('customers').insert({
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'city': city,
                    'total_rentals': 0,
                    'total_spent': 0
                }).execute()

                customer_id = customer_res.data[0]['id']

                # Create profile record linking auth user to customer
                db.table('profiles').insert({
                    'id': user_id,
                    'role': 'customer',
                    'customer_id': customer_id
                }).execute()

                success = 'Account created successfully. You can now log in.'

            except Exception as e:
                error_msg = str(e)
                if 'already registered' in error_msg or 'already exists' in error_msg:
                    error = 'An account with this email already exists.'
                else:
                    error = 'Registration failed. Please try again.'

    return render_template('customer/register.html', error=error, success=success)


# ══════════════════════════════════════
# CUSTOMER LOGOUT
# ══════════════════════════════════════
@app.route('/customer/logout')
def customer_logout():
    session.pop('customer', None)
    return redirect(url_for('customer_login'))


# ══════════════════════════════════════
# CUSTOMER DASHBOARD — their bookings
# ══════════════════════════════════════
@app.route('/customer/dashboard')
@customer_login_required
def customer_dashboard():
    try:
        customer_id = session['customer']['id']

        # Fetch all bookings for this customer
        bookings = db.table('bookings')\
            .select('*, vehicles(name, type, daily_rate)')\
            .eq('customer_id', customer_id)\
            .order('created_at', desc=True)\
            .execute()

        # Separate active vs past
        active_bookings = [b for b in (bookings.data or [])
                          if b['status'] in ['active', 'pending']]
        past_bookings   = [b for b in (bookings.data or [])
                          if b['status'] in ['completed', 'overdue']]

        # Stats
        total_spent = sum(b['total_amount'] for b in (bookings.data or [])
                         if b['status'] == 'completed')
        total_bookings = len(bookings.data or [])

        return render_template('customer/dashboard.html',
            customer=session['customer'],
            active_bookings=active_bookings,
            past_bookings=past_bookings,
            total_spent=total_spent,
            total_bookings=total_bookings
        )
    except Exception as e:
        print('Customer dashboard error:', e)
        return render_template('customer/dashboard.html',
            customer=session['customer'],
            active_bookings=[], past_bookings=[],
            total_spent=0, total_bookings=0
        )


# ══════════════════════════════════════
# CUSTOMER RECEIPT PAGE
# ══════════════════════════════════════
@app.route('/customer/booking/<booking_id>')
@customer_login_required
def customer_receipt(booking_id):
    try:
        customer_id = session['customer']['id']

        # Fetch booking — verify it belongs to this customer
        booking = db.table('bookings')\
            .select('*, vehicles(name, type, brand, year, fuel, daily_rate), customers(name, email, phone, city)')\
            .eq('id', booking_id)\
            .eq('customer_id', customer_id)\
            .execute()

        if not booking.data:
            return redirect(url_for('customer_dashboard'))

        # Fetch payment for this booking
        payment = db.table('payments')\
            .select('*')\
            .eq('booking_id', booking_id)\
            .execute()

        return render_template('customer/receipt.html',
            customer=session['customer'],
            booking=booking.data[0],
            payment=payment.data[0] if payment.data else None
        )
    except Exception as e:
        print('Receipt error:', e)
        return redirect(url_for('customer_dashboard'))


# ══════════════════════════════════════
# CUSTOMER — RAZORPAY PAYMENT
# ══════════════════════════════════════
@app.route('/api/customer/payment/create', methods=['POST'])
@customer_login_required
def create_razorpay_order():
    try:
        import razorpay
        data = request.json
        booking_id = data['booking_id']
        amount = data['amount']  # in paise (multiply rupees × 100)

        # Fetch Razorpay keys from environment
        import os
        rz_key_id     = os.environ.get('RAZORPAY_KEY_ID')
        rz_key_secret = os.environ.get('RAZORPAY_KEY_SECRET')

        client = razorpay.Client(auth=(rz_key_id, rz_key_secret))

        order = client.order.create({
            'amount': amount * 100,  # convert to paise
            'currency': 'INR',
            'receipt': booking_id[:20],
            'payment_capture': 1
        })

        return jsonify({'success': True, 'order_id': order['id'], 'key_id': rz_key_id})
    except Exception as e:
        print('Razorpay order error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/customer/payment/verify', methods=['POST'])
@customer_login_required
def verify_razorpay_payment():
    try:
        import razorpay, hmac, hashlib, os
        data = request.json

        rz_key_secret = os.environ.get('RAZORPAY_KEY_SECRET')

        # Verify payment signature
        body = data['razorpay_order_id'] + '|' + data['razorpay_payment_id']
        expected = hmac.new(
            rz_key_secret.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        if expected != data['razorpay_signature']:
            return jsonify({'success': False, 'error': 'Invalid signature'}), 400

        # Record payment in database
        import random, string
        ref = '#TXN-' + ''.join(random.choices(string.digits, k=6))
        customer_id = session['customer']['id']

        db.table('payments').insert({
            'transaction_ref': ref,
            'booking_id': data['booking_id'],
            'customer_id': customer_id,
            'amount': data['amount'],
            'method': 'Razorpay',
            'status': 'paid'
        }).execute()

        # Update booking payment status
        db.table('bookings').update({
            'payment_status': 'paid',
            'payment_method': 'Razorpay'
        }).eq('id', data['booking_id']).execute()

        return jsonify({'success': True})
    except Exception as e:
        print('Razorpay verify error:', e)
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)