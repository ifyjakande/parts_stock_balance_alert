# Parts Stock Balance Alert

This repository contains a GitHub Actions workflow that monitors Google Sheets for changes in parts weights and sends alerts to Google Space when changes are detected.

## Features

- **Parts Weight Monitoring**: Tracks changes in parts weights inventory

## Setup

1. **Google Service Account**
   - Create a Google service account with access to Google Sheets API
   - Download the service account credentials JSON file
   - Add the service account JSON content as a GitHub secret named `GOOGLE_SHEETS_CREDENTIALS`
   - Share the Google Sheet with the service account email

2. **Google Space Webhook**
   - Create a webhook in your Google Space
   - Add the webhook URL as a GitHub secret named `SPACE_WEBHOOK_URL`

3. **Google Sheet ID**
   - Add your Google Sheet ID as a GitHub secret named `SPREADSHEET_ID`

## How it Works

### Parts Weight Monitoring
- The workflow runs every 30 minutes
- It checks the 'parts' sheet for any changes in parts weights
- If changes are detected, it sends an alert to Google Space
- The alert includes the part type and the change in weight
- Previous state is maintained between runs

## Manual Trigger

You can manually trigger the workflow using the "Actions" tab in GitHub.

## Environment Variables

The following secrets need to be set in GitHub:

- `GOOGLE_SHEETS_CREDENTIALS`: The service account JSON credentials
- `SPACE_WEBHOOK_URL`: The webhook URL for Google Space
- `SPREADSHEET_ID`: The ID of your Google Sheet

## Important Security Note

Never commit service account credentials to the repository. The workflow will create the service account file dynamically during runtime using the GitHub secret. 