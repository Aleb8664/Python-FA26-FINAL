# Python-FA26-FINAL

## Inventory Manager

This Streamlit class-demo app is inspired by the original inventory program. It
supports employee accounts, stock issuing, equipment checkouts, returns,
renewals, authorization rules, low-stock warnings, overdue alerts, and checkout
history.

### Run locally

From this folder, install dependencies and start the app:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On the first launch, create the password for the protected owner account
**employee ID `1` / `aleb`**. The app creates sample inventory with randomized
starting quantities and saves all accounts, item data, and transaction history
to `Inventory.json` beside `app.py`. That file is ignored by Git.

### Features

- Employees sign in with their employee ID and password. Passwords are stored
  as salted PBKDF2 hashes, not plaintext.
- The protected owner account can create employee or admin accounts and
  change employee access. Other admins cannot demote or remove the owner.
- Admins can add, edit, deactivate, or permanently delete inventory items;
  configure stock thresholds and checkout limits; and restrict an item to
  selected employees.
- Employees can issue stock/consumables or check out reusable equipment with
  a required reason. Equipment returns restore available quantity.
- Reusable items have configurable due dates and renewal limits. The dashboard
  flags overdue checkouts and items at or below their low-stock threshold.
- Inactive items and historical transactions remain available for auditing.

### Important storage limitation

This is a local class demo, not a production authentication or inventory
system. The JSON file is stored on the computer running Streamlit. Streamlit
Community Cloud does not provide durable writable local storage, and a public
deployment must not be used to protect real accounts or sensitive inventory.
Use a hosted database and a proper authentication provider before relying on
the app online or with real users.

### Tests

```powershell
python -m unittest discover -s tests
```
