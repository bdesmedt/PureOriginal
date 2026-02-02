# Pure & Original CFO Dashboard v2.0

🎨 Real-time financieel analytics dashboard voor Pure & Original, gebouwd met Streamlit en verbonden met Odoo ERP.

## Features

| Tab | Functionaliteit |
|-----|----------------|
| 📊 **Overzicht** | YTD omzet, kosten, openstaande debiteuren/crediteuren, maandelijkse grafieken |
| 📈 **Winst & Verlies** | Volledige P&L met opbrengsten en kosten per categorie |
| 📋 **Balans** | Kwadrant layout met Activa, Passiva en Eigen Vermogen |
| 🔄 **Intercompany** | R/C posities tussen P&O BV, P&O International en Mia Colore + reconciliatie check |
| 🧾 **BTW Analyse** | BTW-saldi per entiteit + Belgische BTW risico monitoring |
| 📄 **Facturen** | Drill-down met filters op type, status en betaalstatus |
| 🏦 **Bank** | Banksaldi per entiteit met verdeling grafiek |
| 💹 **Cashflow** | 12-weeks prognose op basis van openstaande posten |
| 📦 **Producten** | Productcategorieën, voorraad en marge-analyse |

## Bedrijfsstructuur

- Pure & Original B.V. (NL820994297B01)
- Pure & Original International B.V. (NL862809095B01)
- Mia Colore B.V. (NL820994327B01)

## Installatie

### Lokaal

```bash
git clone https://github.com/bdesmedt/PureOriginal.git
cd PureOriginal
pip install -r requirements.txt
streamlit run pure_original_dashboard.py
```

### Streamlit Cloud

1. Ga naar [share.streamlit.io](https://share.streamlit.io)
2. Kies repository: `bdesmedt/PureOriginal`
3. Branch: `main`
4. Main file: `pure_original_dashboard.py`
5. Deploy!

## Configuratie

### Via Streamlit Secrets

Maak `.streamlit/secrets.toml`:

```toml
ODOO_API_KEY = "your-api-key-here"
```

Of configureer in Streamlit Cloud via Settings → Secrets.

### Via Sidebar

Bij opstarten kun je de API key direct invoeren via de sidebar.

## Technische Details

- **Framework:** Streamlit
- **Visualisatie:** Plotly
- **Data:** Pandas
- **Backend:** Odoo v16 JSON-RPC API
- **Database:** pureoriginal-main-6280301

## Changelog

### v2.0
- ➕ Winst & Verlies rekening
- ➕ Balans met kwadrant layout
- ➕ Cashflow Prognose (12 weken)
- ➕ Producten & Categorieën met marge-analyse
- 🔧 Verbeterde BTW risico detectie
- 🔧 Intercompany reconciliatie checks

### v1.0
- Initial release
- Financieel overzicht
- Intercompany monitor
- BTW analyse
- Facturen drill-down
- Banksaldi

---

Gebouwd door [FidFinance](https://fidfinance.nl) 💼