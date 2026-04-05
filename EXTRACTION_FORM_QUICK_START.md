# Quick Start Guide — Extraction Fields Form

## 🚀 Getting Started

### Prerequisites
- ✅ Backend running: `uvicorn main:app --reload --port 8000`
- ✅ Frontend running: `npm run dev` (port 5173)
- ✅ Logged in to the application

### Access the Form

**Option 1: Via Sidebar**
1. You'll see a new "**EXTRACTION**" section in the sidebar
2. Click "**Define Fields**"

**Option 2: Direct URL**
- Navigate to: `http://localhost:5173/extract-fields`

---

## 📋 Form Usage

### Add a Field
```
1. Click "+ Ajouter un champ" (Add Field)
2. Click the chevron to expand the card
3. Fill in the details:
   - Nom du champ (required)      ← e.g., "Loan Number"
   - Description (optional)        ← e.g., "Unique loan identifier"
   - Page (optional)               ← e.g., "1" or "page 1"
   - Valeur (optional)             ← e.g., "LN-2025-00123"
   - Score (optional)              ← e.g., "0.95"
4. Click the chevron to collapse
```

### Example Fields to Try

```
Field 1:
  Nom: Loan Number
  Description: Unique loan identifier
  Page: 1
  Valeur: LN-2025-00123
  Score: 0.95

Field 2:
  Nom: Agreement Date
  Description: Date when agreement was signed
  Page: 2
  Valeur: 2025-03-30
  Score: 0.87

Field 3:
  Nom: Program Name
  Description: Name of the lending program
  Page: 1
  Valeur: Small Business Loan
  Score: 0.92
```

---

## 🎯 Actions

| Action | Button | Result |
|--------|--------|--------|
| Add Field | **+ Ajouter un champ** | Creates new empty field |
| Expand | **⌄** (Chevron) | Shows/hides field details |
| Delete | **🗑** (Trash) | Removes field from form |
| Export | **📥 Exporter JSON** | Downloads fields as JSON file |
| Submit | **📤 Envoyer les champs** | Sends to backend |

---

## ✅ Validation Rules

| Field | Required? | Example | Rules |
|-------|-----------|---------|-------|
| `keyName` | **YES** ⭐ | "Loan Number" | Cannot be empty |
| `keyNameDescription` | No | "Unique identifier" | Max 500 chars |
| `page` | No | "1" or "page 1" | Any text format |
| `value` | No | "LN-2025-00123" | Any text |
| `score` | No | "0.95" or "95" | Decimal or percentage |

**Submit Button:** Disabled if any required field is empty

---

## 💾 Data Submission

When you click **"Envoyer les champs"**:

1. **Validation** — Frontend checks all required fields
2. **Formatting** — Removes internal IDs, trims whitespace
3. **Sending** — POST request to backend with JWT token
4. **Success** — Toast notification, fields saved to backend

**Saved Location:**
```
backend/uploads/extractions/
  ├── extraction_fields_20250330_120000.json  (timestamp)
  └── extraction_fields_latest.json           (latest version)
```

---

## 🔧 Export/Reuse

### Export to JSON
1. Click **"Exporter JSON"** button
2. Browser downloads: `extraction_fields_TIMESTAMP.json`
3. Can upload this file in the standard document upload workflow

### JSON Format
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
    "page": "2",
    "value": "2025-03-30",
    "score": "0.87"
  }
]
```

---

## ⚠️ Troubleshooting

### "Session expirée — reconnectez-vous"
**Problem:** Your login session expired
**Solution:** Log out and log back in

### "Impossible de contacter le serveur"
**Problem:** Backend is not running
**Solution:** Start backend with `uvicorn main:app --reload --port 8000`

### "⚠️ Complétez au moins le nom des champs"
**Problem:** Some fields are missing `keyName`
**Solution:** Fill in all `keyName` fields before submitting

### Form data not submitting
**Problem:** Network or validation error
**Solution:** 
1. Check browser console (F12)
2. Verify backend is running
3. Check that all required fields are filled

### Styles look broken
**Problem:** CSS not loaded
**Solution:** 
1. Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)
2. Restart frontend: `npm run dev`

---

## 📊 Sidebar Info Cards

The right sidebar shows you three helpful sections:

### 1. Guide d'utilisation (Usage Guide)
- Step-by-step instructions
- 4 main steps explained

### 2. Format de sortie (Output Format)
- Shows JSON structure
- Example with all 5 fields

### 3. Champs définis (Defined Fields)
- Shows total count
- Shows how many have values/scores
- Only visible when you have fields

---

## 🎨 UI Elements

- **Field Card** — Each field in expandable card format
- **Number Badge** — Shows field position (1, 2, 3, etc.)
- **Chevron** — Click to expand/collapse details
- **Trash Icon** — Delete the field
- **Input Fields** — Text inputs for each field property
- **Textarea** — Description field supports multi-line text
- **Score Input** — Number field with % label

---

## 📱 Responsive Design

The form works great on:
- ✅ Desktop (full width with sidebar)
- ✅ Tablet (responsive layout)
- ✅ Mobile (stacked layout, full width)

---

## 🔐 Authentication

- Backend validates JWT token on every request
- Token stored in `localStorage`
- Automatic redirect to login if expired
- All requests include: `Authorization: Bearer <TOKEN>`

---

## 📝 Notes

- Fields are saved with a **timestamp** for versioning
- A **"latest"** version is always kept for quick reference
- You can submit as many times as you want
- Each submission creates a new file
- Deleted fields are not recoverable unless you have the JSON file

---

## 🎓 Example Workflow

```
1. Navigate to "Define Fields" page
   ↓
2. Add first field (Loan Number)
   ↓
3. Add second field (Agreement Date)
   ↓
4. Click Export JSON (optional, for backup)
   ↓
5. Click "Envoyer les champs"
   ↓
6. See success message ✓
   ↓
7. Fields saved in backend/uploads/extractions/
   ↓
8. Fields are now available for document processing
```

---

## 🆘 Need Help?

Check the detailed documentation:
- **Full Guide:** `Frontend/react-app/src/pages/EXTRACT_FIELDS_README.md`
- **Implementation:** `/EXTRACTION_FORM_IMPLEMENTATION.md`
- **Browser Console:** F12 → Console tab for error messages

---

**Version:** 1.0  
**Last Updated:** March 30, 2026  
**Status:** ✅ Ready to Use
