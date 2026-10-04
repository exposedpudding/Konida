# Konida

Order Konica Minolta consumables from portal.konicaminolta.co.uk as a guest, choosing
the quantity of each toner and logging every order against the copier's serial number.

    pip install -r requirements.txt   # browsers: `playwright install chromium` (if not already present)
    cp fleet.example.yaml fleet.yaml
    python -m konida list
    python -m konida order reception-c360i --toner TN-328K=2 TN-328C=1            # dry run
    python -m konida order reception-c360i --toner TN-328K=2 --confirm            # live
    python -m konida history reception-c360i

- Opens a visible browser. The guest login is protected by reCAPTCHA, which this tool
  does not bypass: complete the challenge yourself when prompted.
- Dry run is the default; nothing is submitted without `--confirm`.
- Orders are logged to local `orders.db` (SQLite) with serial, items, status, portal ref.
- **First run:** the order pages were not inspectable without passing the captcha. Run with
  `--discover`, then adjust the `SEL` selectors in `konida/portal.py` using `./discovery/`.

## Windows app (no install)

CI builds `Konida.exe` (GitHub Actions > "Build Windows exe" > artifact `Konida-windows`).
Put it in any folder and double-click. It uses the Microsoft Edge already on Windows,
and keeps `fleet.yaml` and `orders.db` next to the exe (portable, e.g. on a USB stick).
