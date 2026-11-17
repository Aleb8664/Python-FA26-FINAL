# Python-FA26-FINAL
Final for 2026 fall class

## Inventory Explorer

This Streamlit app lets you search, filter, add, and remove inventory items by
name and category. On its first run, it loads the sample items from `menu.txt`.
When an item is added or removed, the complete inventory is saved to
`Inventory.json` beside `app.py`. After that file is created, it is the app's
inventory source.

### Run locally

Install the dependencies and start the app from this folder:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

### Deploy on Streamlit Community Cloud

Push this repository to GitHub, then create an app in Streamlit Community Cloud
using this repository, the `main` branch, and `app.py` as the app file.

`Inventory.json` is a local file, not a cloud database. Streamlit Community
Cloud's app filesystem is not a reliable place for persistent user changes, so
edits made in a deployed app can be lost when the app restarts or redeploys.
Use the local app for persistent file-based edits; a hosted database is needed
to reliably share and persist changes online.
