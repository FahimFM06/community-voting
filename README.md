# Community Election — browser-only deployment

No terminal, Python installation, or always-on personal computer is required. This version replaces the earlier command-line setup with a protected browser setup wizard. Use a fresh dedicated Supabase project.

## 1. GitHub
Create a repository at https://github.com/new (private recommended). Upload `app.py`, `voting.py`, and `requirements.txt` into the root of the repository using Add file > Upload files, then Commit changes. The README and test file are optional. Do not upload secrets, real names, or generated access codes. If updating the earlier project, replace these files with the new versions; never overwrite an initialized election database.

## 2. Supabase
Create a project at https://supabase.com/dashboard. Choose a nearby region (EU for an EU community, if available) and a strong database password. Open Connect, select the Session pooler connection URI, replace the password placeholder with your actual URL-encoded database password, and append `?sslmode=require` (or `&sslmode=require` if there are already query parameters). Keep the URI private. For stronger TLS authentication use full certificate verification if configured. Do not expose the `community_vote` schema in the public API. The app creates its own tables; no manual SQL is necessary.

## 3. Streamlit Community Cloud
At https://share.streamlit.io/, sign in and connect GitHub. Select Create app / deploy an existing repository. Set repository, branch (usually main), and main file path `app.py`. Under Advanced settings > Secrets enter:

```toml
DATABASE_URL = "postgresql://YOUR_ACTUAL_SESSION_POOLER_URI?sslmode=require"
SETUP_PASSWORD = "REPLACE_WITH_A_NEW_RANDOM_PASSWORD_AT_LEAST_24_CHARACTERS"
```

Use the complete actual Supabase URI, not the placeholder. Generate a long random setup password in a trusted password manager. Do not put either secret into GitHub. Deploy. Make the Streamlit app publicly reachable by link (app settings > sharing), so members can use its own login without a Streamlit account. The repository can remain private if the app sharing configuration permits public viewing. Grant Streamlit access to the repository as required.

## 4. Initialize in the browser
Open the deployed app. Enter the setup password, enter 13 unique voter/candidate names and 3 unique administrator names, one per line. The three administrators may also be among the 13 voters. Generate codes, download the private text file, keep it securely, confirm that you saved it, and initialize. Setup is disabled once initialization succeeds. Do not reload/close the tab before saving and initializing: the draft codes exist only in that browser session. If a setup error occurs, keep the codes and check whether the election was initialized before retrying. Remove SETUP_PASSWORD from Streamlit secrets after setup if desired; the app no longer needs it. Sign in as an administrator, copy the fixed tie-break priority, and share the priority and rules before distributing voting codes.

## 5. Vote
Share the same app URL with the community. Send every member only their individual member code privately, and every administrator their own admin code. Administrators who also vote get two codes. Members rank all 12 other members (12 points for first, down to 1 for last). One final ballot per member; no self-voting or edits. After all 13 ballots, the app shows positions 1–13. Ties: points, first-choice counts, second-choice counts, etc., then the fixed random priority generated before voting. Administrators alone can view individual ballots in the app, only after all votes are received. The hosting/database owner has technical access too. This is confidential, not fully anonymous. Disclose this to every participant and agree on a retention/deletion policy.

The browser setup organizer can see all codes and could impersonate members; use a trusted organizer. There is no code recovery, reset, or early-close UI. If a voter abstains, results stay locked. Test using a separate disposable database first. Supabase keeps data across Streamlit restarts, but free hosting may sleep or pause; check provider availability and resume as needed. Do not upload the private credential file to GitHub. Do not use for legally regulated or high-stakes elections without independent review.

## Verification
Five automated SQLite backend tests passed (including tie resolution, access checks, one-vote enforcement, and setup status); Python source compiled. Live Streamlit UI and PostgreSQL connection have not been tested. Verify deployment with a separate test election before real voting.

Official documentation: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy ; https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management ; https://supabase.com/docs/guides/database/connecting-to-postgres
