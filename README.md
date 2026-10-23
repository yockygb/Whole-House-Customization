# Whole-House Customization Quotation Studio 1.1

A bilingual English/Chinese quotation application for whole-house cabinetry. This source edition includes the quotation workspace, category and material management, drawing-image recognition, local quote history, and Excel/PDF exports.

## Run on Windows

1. Install Python 3.11 or newer.
2. Double-click `Setup.cmd` once to create the local virtual environment and install dependencies.
3. Double-click `Start.cmd` to start the application in your browser.

The application runs locally. Its database, uploaded images, editable price list, and exports are stored in `workspace-data/` and `exports/` beside the source. Those folders are ignored by Git. Back up `workspace-data/` to preserve your own settings and quotes.

## Public defaults and privacy

The published factory configuration contains no company logo, contact details, or price amounts. The workbook reference file preserves layout only. Configure your own catalogue, prices, and company details from the management page after starting the app. Do not commit `data/pricing.json`, `workspace-data/`, uploaded files, or exported customer documents.

## Tests

Run `Run-tests.cmd` or `python tools/public_data.py` followed by `python tools/run_tests.py`.

## Source contents

`app.py`, `core/`, `server/`, `web/`, and `export/` are the application source. `assets/white_models/` contains generic cabinet illustrations. `templates/quotation-reference.xlsx` is a sanitized layout reference with no quotation values or embedded logos.
