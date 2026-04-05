# Extraction Fields Form — Documentation

## Overview

The new **Extract Fields** feature allows you to manually define extraction fields through an interactive form interface. Instead of uploading a JSON file, you can:

- Add multiple extraction fields dynamically
- Define each field with: **keyName**, **description**, **page**, **value**, **score**
- Export fields as JSON
- Send all fields to the backend in a single request

## Access the Form

1. Navigate to **Extraction** → **Define Fields** in the sidebar
2. Or go directly to: `http://localhost:5173/extract-fields`

## How to Use

### 1. Add Fields
- Click **"Ajouter un champ"** (Add Field) button
- A new field card will appear

### 2. Fill in Field Details
Each field can have:
- **Nom du champ** (Field Name) — **REQUIRED** (e.g., "Loan Number", "Agreement Date")
- **Description / Contexte** — Optional hint text for the LLM
- **Page** — Optional page number where field is located
- **Valeur** — Optional current value
- **Score de confiance** — Optional score (0.0–1.0)

### 3. Manage Fields
- Click the **chevron icon** to expand/collapse field details
- Click the **trash icon** to delete a field

### 4. Submit
- Click **"Envoyer les champs"** (Send Fields) button
- All fields are sent to the backend as a JSON array
- Success message confirms `N champ(s) envoyé(s)`

### 5. Export as JSON (Optional)
- Click **"Exporter JSON"** to download fields as a JSON file
- Can be reused in the standard Upload workflow

## Backend Integration

The form sends a POST request to:
```
POST /api/extraction-fields
```

**Request Body:**
```json
[
  {
    "keyName": "Loan Number",
    "keyNameDescription": "Unique identifier for the loan",
    "page": "1",
    "value": "LN-2025-00123",
    "score": "0.95"
  },
  {
    "keyName": "Agreement Date",
    "keyNameDescription": "Date when agreement was signed",
    "page": "1",
    "value": "2025-03-30",
    "score": "0.87"
  }
]
```

**Response:**
```json
{
  "status": "saved",
  "count": 2,
  "file": "/path/to/extractions/extraction_fields_20250330_120000.json",
  "fields": [...]
}
```

## Files Created

### Frontend
- **`FieldExtractor.jsx`** — Reusable form component
- **`ExtractFields.jsx`** — Page/route for the form
- **Updated `App.jsx`** — Added route `/extract-fields`
- **Updated `Sidebar.jsx`** — Added navigation link

### Backend
- **Updated `routers/documents.py`** — Added `POST /extraction-fields` endpoint

## Data Persistence

Fields submitted to the backend are saved to:
```
backend/uploads/extractions/extraction_fields_YYYYMMDD_HHMMSS.json
backend/uploads/extractions/extraction_fields_latest.json
```

## Features

✅ Add/remove fields dynamically
✅ Expandable field cards for better UX
✅ Full validation on frontend and backend
✅ Export to JSON for reuse
✅ Real-time field count display
✅ Responsive design (works on desktop & mobile)
✅ Toast notifications for user feedback
✅ Authentication required (uses stored JWT token)

## Example Use Cases

1. **Quick Extraction Definition**: Manually list the fields you want extracted
2. **Field Reuse**: Export JSON and use in other documents
3. **Testing & Development**: Test extraction without full document upload
4. **Field Documentation**: Document field definitions for team reference

## Troubleshooting

| Issue | Solution |
|-------|----------|
| *"Session expirée"* | Log out and log back in |
| *"Impossible de contacter le serveur"* | Ensure backend is running on `localhost:8000` |
| *"⚠️ Complétez au moins le nom des champs"* | All fields must have a `keyName` (required) |
| Form not submitting | Check browser console for error messages |

## Next Steps

- Fields are saved to backend  
- Can be retrieved and used in document extraction workflows
- Consider integrating with the main Upload document pipeline
