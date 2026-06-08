# Vercel + Supabase Free Deployment

This repository includes a Vercel-compatible hosted experience for OnCallAI.

## Stack

- Frontend: Vercel Hobby
- API: Vercel serverless functions
- Durable storage: Supabase Free Postgres

## What gets stored

When the hosted app is connected to Supabase, each scenario run stores:

- `incidents`: the alert/incident record
- `incident_steps`: the workflow timeline
- `incident_reports`: the generated operator output

If Supabase environment variables are missing, the app falls back to local preview storage in `.local/vercel-runs.json` for development only.

## 1. Create Supabase project

1. Go to [Supabase](https://supabase.com/).
2. Create a free project.
3. Open the SQL editor.
4. Run the contents of [supabase/schema.sql](/Users/deepti.r.kumar/Desktop/Documents/Projects/OnCallAI/supabase/schema.sql).

## 2. Collect environment variables

From the Supabase project:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Reference file:
- [.env.vercel.example](/Users/deepti.r.kumar/Desktop/Documents/Projects/OnCallAI/.env.vercel.example)

## 3. Import into Vercel

1. Go to [Vercel](https://vercel.com/).
2. Import the GitHub repository.
3. Leave the framework preset as `Other`.
4. Set the root directory to the repo root.
5. Add the two Supabase environment variables.
6. Deploy.

## 4. How the hosted app behaves

- `/` serves the product website from `vercel_demo/`
- `/api/health` reports whether durable storage is connected
- `/api/run-scenario` creates and stores a live scenario run
- `/api/incidents` loads recent stored runs for the UI

## 5. Interview-safe live demo flow

1. Open the hosted site.
2. Click `Try Product`.
3. Choose `Database outage` or `Bad deploy`.
4. Click `Run Analysis`.
5. Show:
   - storage mode
   - live processing log
   - recent runs list
   - walkthrough and operator output sections

If Supabase is connected, you can honestly say the runs are being durably stored in Postgres on the free tier.
