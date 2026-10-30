# Migrating QuickRent from Render to Vercel

## Step 1: Remove Render Deployment
1. Go to [Render Dashboard](https://render.com)
2. Select your "quickrent" service
3. Click **Settings** → **Delete Service** 
4. Confirm deletion

## Step 2: Deploy to Vercel

### Option A: Via Vercel Dashboard
1. Go to [Vercel](https://vercel.com) and log in
2. Click **New Project** → **Import Git Repository**
3. Connect your GitHub/GitLab/Bitbucket repo
4. Vercel will auto-detect Python framework
5. Click **Deploy**

### Option B: Via CLI
```bash
vercel login
vercel --prod
```

## Step 3: Add Environment Variables
Go to Vercel Project Settings → **Environment Variables** and add:

| Key | Value |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_KEY` | Your Supabase anon/public key |
| `FLASK_SECRET_KEY` | `quickrent-secret-2026` (or your custom key) |
| `ADMIN_EMAIL` | `admin@quickrent.in` |
| `SENDGRID_API_KEY` | Your SendGrid API key |
| `SENDGRID_FROM_EMAIL` | `renish2024s@gmail.com` |
| `RAZORPAY_KEY_ID` | Your Razorpay key ID |
| `RAZORPAY_KEY_SECRET` | Your Razorpay key secret |

## Step 4: Verify Deployment
- Visit your Vercel URL
- Test login, vehicle bookings, payments
- Check that email notifications work (SendGrid)
- Verify Razorpay payments process

## Notes
- Vercel automatically sets the `PORT` environment variable - the Flask/gunicorn app will use it
- The `vercel.json` I created configures Flask framework detection
- All 8 environment variables from your `.env` must be added to Vercel for full functionality
- The app uses `gunicorn app:app` as the production server (same as Render)