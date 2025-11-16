# Google Calendar Integration Setup Guide

This guide will help you set up Google Calendar integration for your ego_proxy personal assistant. Once configured, you'll be able to create calendar events using natural language like "add meeting with John tomorrow at 3pm to my calendar".

## Prerequisites

- A Google account with Google Calendar access
- Python 3.10+ installed
- ego_proxy project set up and running

## Step 1: Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top of the page
3. Click "New Project"
4. Enter a project name (e.g., "ego-proxy-calendar")
5. Click "Create"
6. Wait for the project to be created (you'll see a notification)

## Step 2: Enable the Google Calendar API

1. Make sure your new project is selected in the project dropdown
2. Go to the [Google Calendar API page](https://console.cloud.google.com/apis/library/calendar-json.googleapis.com)
   - Or navigate to: APIs & Services → Library → Search for "Google Calendar API"
3. Click "Enable"
4. Wait for the API to be enabled

## Step 3: Configure OAuth Consent Screen

1. Go to [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent)
   - Or navigate to: APIs & Services → OAuth consent screen
2. Choose "External" as the User Type (unless you have a Google Workspace account)
3. Click "Create"
4. Fill in the required fields:
   - **App name**: ego_proxy Calendar Assistant
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
5. Click "Save and Continue"
6. On the "Scopes" page, click "Save and Continue" (no additional scopes needed)
7. On the "Test users" page:
   - Click "Add Users"
   - Add your Google account email address
   - Click "Save and Continue"
8. Review the summary and click "Back to Dashboard"

## Step 4: Create OAuth 2.0 Credentials

1. Go to [Credentials](https://console.cloud.google.com/apis/credentials)
   - Or navigate to: APIs & Services → Credentials
2. Click "Create Credentials" → "OAuth client ID"
3. Choose "Desktop app" as the Application type
4. Enter a name (e.g., "ego_proxy Desktop Client")
5. Click "Create"
6. You'll see a dialog with your credentials - click "Download JSON"
7. **Important**: Save this file as `credentials.json` in your ego_proxy project root directory

## Step 5: Configure ego_proxy

1. Open or create your `.env` file in the ego_proxy root directory:
   ```bash
   cp .env.example .env
   ```

2. Edit the `.env` file and ensure this line is present:
   ```
   GOOGLE_CREDENTIALS_PATH=credentials.json
   ```

3. Make sure your `credentials.json` file is in the project root (same directory as `.env`)

## Step 6: Install Dependencies

Install the required Google Calendar dependencies:

```bash
pip install -r requirements.txt
```

Or install them individually:

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client cryptography python-dateutil
```

## Step 7: First-Time Authentication

1. Start the assistant:
   ```bash
   ./assistant.sh
   ```

2. The first time you use a calendar feature, you'll be prompted to authenticate:
   - A browser window will open automatically
   - Sign in with your Google account (must be a test user you added)
   - Click "Continue" when warned that the app isn't verified (this is normal for test apps)
   - Grant the requested calendar permissions
   - You should see "The authentication flow has completed" in the browser
   - Return to your terminal

3. Your authentication token will be securely encrypted and stored in the database
4. Future sessions will use the stored token automatically (no re-authentication needed)

## Usage Examples

Once set up, you can create calendar events using natural language:

```
You: Add meeting with Sarah tomorrow at 3pm to my calendar
Assistant: ✅ Calendar event created:
   📅 Meeting with Sarah
   🕐 2025-11-17 at 03:00 PM
   🔗 https://calendar.google.com/...

You: Schedule a team standup next Monday at 10am
Assistant: ✅ Calendar event created:
   📅 Team standup
   🕐 2025-11-20 at 10:00 AM
   🔗 https://calendar.google.com/...

You: Add dentist appointment on my agenda for next Friday at 2pm
Assistant: ✅ Calendar event created:
   📅 Dentist appointment
   🕐 2025-11-24 at 02:00 PM
   🔗 https://calendar.google.com/...
```

## Supported Phrases

The assistant recognizes various calendar-related phrases:
- "add to my calendar"
- "add on my calendar"
- "add to my agenda"
- "add on my agenda"
- "schedule"
- "create event"
- "add event"
- "put on my calendar"
- "set up a meeting"
- "book a meeting"
- "add appointment"
- "create appointment"

## Time/Date Recognition

The assistant understands natural language dates and times:
- **Relative dates**: "tomorrow", "today", "next week", "next Monday"
- **Specific times**: "at 3pm", "at 10:30am", "at 14:00"
- **Combined**: "tomorrow at 3pm", "next Friday at 2:30pm"

## Troubleshooting

### "Credentials file not found"
- Make sure `credentials.json` is in your project root directory
- Check that `GOOGLE_CREDENTIALS_PATH` in `.env` points to the correct file

### "Access blocked: This app's request is invalid"
- Make sure you added your email as a test user in the OAuth consent screen
- Verify the OAuth consent screen is properly configured

### "Calendar integration not available"
- Check that you've installed all required dependencies: `pip install -r requirements.txt`
- Verify the Google Calendar API is enabled in your Google Cloud project
- Check the logs for detailed error messages: `./assistant.sh --verbose`

### "Token expired" or authentication errors
- The assistant should automatically refresh expired tokens
- If issues persist, delete the calendar credentials from the database:
  ```bash
  sqlite3 assistant_memory.db "DELETE FROM calendar_credentials;"
  ```
- Restart the assistant and re-authenticate

### Calendar events not being created
- Verify the assistant detected the calendar intent by checking for the green confirmation panel
- Check that your internet connection is working
- Try with verbose mode to see detailed logs: `./assistant.sh --verbose`

## Security Notes

1. **Credentials**: Keep `credentials.json` secure and never commit it to version control
2. **Tokens**: Calendar tokens are encrypted and stored in your local SQLite database
3. **Encryption Key**: An encryption key is generated at `~/.ego_proxy/calendar_key.bin` - keep this file safe
4. **Permissions**: The assistant only requests calendar read/write permissions (no other Google services)

## Publishing Your App (Optional)

The setup above uses "test mode" which limits access to test users. To make it available to anyone:

1. Complete the OAuth consent screen verification process
2. Submit your app for Google's verification (required for accessing user data)
3. This process can take several weeks and requires privacy policy, terms of service, etc.

For personal use, test mode is sufficient and recommended.

## Additional Resources

- [Google Calendar API Documentation](https://developers.google.com/calendar/api/guides/overview)
- [Google Cloud Console](https://console.cloud.google.com/)
- [OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)

## Support

If you encounter issues:
1. Run the assistant with verbose mode: `./assistant.sh --verbose`
2. Check the error messages in the terminal
3. Verify all setup steps were completed correctly
4. Ensure your Google account has calendar access

---

**Note**: This integration is designed for personal use. The calendar events are created in your primary Google Calendar. Always verify the event details before confirming creation.
