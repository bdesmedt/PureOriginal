"""
Pure & Original Financial Dashboard v2.0
========================================
Uitgebreide versie met:
- 📊 Financieel Overzicht
- 📈 Winst & Verlies
- 📋 Balans
- 🔄 Intercompany Monitor
- 🧾 BTW Analyse
- 📄 Facturen Drill-down
- 🏦 Banksaldi
- 💹 Cashflow Prognose
- 📦 Producten & Categorieën
"""

import subprocess
import sys

def install_packages():
    packages = ['plotly', 'pandas', 'requests']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '-q'])

install_packages()

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta, date
from functools import lru_cache

# =============================================================================
# CONFIGURATIE
# =============================================================================

st.set_page_config(
    page_title="Pure & Original CFO Dashboard",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Odoo configuratie
ODOO_URL = "https://pureoriginal.odoo.com/jsonrpc"
ODOO_DB = "pureoriginal-main-6280301"
ODOO_LOGIN = "f.brandsma@pure-original.nl"
ODOO_UID = 26

def get_api_key():
    try:
        key = st.secrets.get("ODOO_API_KEY", "")
        if key:
            return key
    except:
        pass
    return st.session_state.get("api_key", "")

COMPANIES = {
    1: "Pure & Original B.V.",
    2: "Mia Colore B.V.",
    3: "Pure & Original International B.V."
}

COMPANY_VAT = {
    1: "NL820994297B01",
    2: "NL820994327B01",
    3: "NL862809095B01"
}

# =============================================================================
# ODOO API FUNCTIES
# =============================================================================

def odoo_call(model, method, args, kwargs=None):
    """Voer Odoo JSON-RPC call uit"""
    api_key = get_api_key()
    if not api_key:
        return None
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, ODOO_UID, api_key, model, method, args, kwargs or {}]
        },
        "id": 1
    }
    
    try:
        response = requests.post(ODOO_URL, json=payload, timeout=30)
        result = response.json()
        if "error" in result:
            st.error(f"Odoo Error: {result['error']}")
            return None
        return result.get("result")
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None

@st.cache_data(ttl=300)
def get_companies():
    """Haal bedrijven op"""
    return odoo_call("res.company", "search_read", [[]], {"fields": ["id", "name", "vat", "currency_id"]})

@st.cache_data(ttl=300)
def get_accounts():
    """Haal grootboekrekeningen op"""
    return odoo_call("account.account", "search_read", [[]], 
                     {"fields": ["id", "code", "name", "account_type", "company_id"], "context": {"lang": "nl_NL"}})

@st.cache_data(ttl=300)
def get_invoices(company_id=None, date_from=None, date_to=None, limit=500):
    """Haal facturen op"""
    domain = [("move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"])]
    if company_id:
        domain.append(("company_id", "=", company_id))
    if date_from:
        domain.append(("invoice_date", ">=", date_from))
    if date_to:
        domain.append(("invoice_date", "<=", date_to))
    
    return odoo_call("account.move", "search_read", [domain], 
                     {"fields": ["id", "name", "partner_id", "invoice_date", "invoice_date_due", 
                                "move_type", "state", "amount_total", "amount_residual", 
                                "company_id", "currency_id", "payment_state"],
                      "limit": limit, "order": "invoice_date desc"})

@st.cache_data(ttl=300)
def get_move_lines(domain, fields, limit=50000):
    """Haal boekingsregels op"""
    return odoo_call("account.move.line", "search_read", [domain],
                     {"fields": fields, "limit": limit, "context": {"lang": "nl_NL"}})

@st.cache_data(ttl=300)
def get_account_balances(company_id=None, date_from=None, date_to=None):
    """Haal saldi per rekening op"""
    domain = []
    if company_id:
        domain.append(("company_id", "=", company_id))
    if date_from:
        domain.append(("date", ">=", date_from))
    if date_to:
        domain.append(("date", "<=", date_to))
    
    lines = odoo_call("account.move.line", "search_read", [domain],
                      {"fields": ["account_id", "debit", "credit", "balance", "company_id"],
                       "limit": 50000})
    return lines

@st.cache_data(ttl=300)
def get_products(limit=500):
    """Haal producten op"""
    return odoo_call("product.product", "search_read", [[("sale_ok", "=", True)]],
                     {"fields": ["id", "name", "default_code", "categ_id", "list_price", 
                                "standard_price", "qty_available", "virtual_available",
                                "sales_count", "active"],
                      "limit": limit, "context": {"lang": "nl_NL"}})

@st.cache_data(ttl=300)
def get_product_categories():
    """Haal productcategorieën op"""
    return odoo_call("product.category", "search_read", [[]],
                     {"fields": ["id", "name", "parent_id", "complete_name"],
                      "context": {"lang": "nl_NL"}})

@st.cache_data(ttl=300)
def get_sale_order_lines(date_from=None, date_to=None, limit=5000):
    """Haal verkooporderregels op voor productanalyse"""
    domain = [("state", "in", ["sale", "done"])]
    if date_from:
        domain.append(("order_id.date_order", ">=", date_from))
    if date_to:
        domain.append(("order_id.date_order", "<=", date_to))
    
    return odoo_call("sale.order.line", "search_read", [domain],
                     {"fields": ["product_id", "product_uom_qty", "price_subtotal", 
                                "order_id", "company_id", "create_date"],
                      "limit": limit})

@st.cache_data(ttl=300)
def get_taxes():
    """Haal BTW tarieven op"""
    return odoo_call("account.tax", "search_read", [[]], 
                     {"fields": ["id", "name", "amount", "type_tax_use", "company_id"]})

@st.cache_data(ttl=300)
def get_bank_accounts():
    """Haal bankrekeningen op"""
    journals = odoo_call("account.journal", "search_read", [[("type", "=", "bank")]],
                         {"fields": ["id", "name", "company_id", "default_account_id"]})
    return journals

# =============================================================================
# HELPER FUNCTIES
# =============================================================================

def format_currency(amount, symbol="€"):
    """Formatteer bedrag als valuta"""
    if amount is None:
        return f"{symbol} 0,00"
    if amount < 0:
        return f"{symbol} -{abs(amount):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{symbol} {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_account_type_category(account_type):
    """Categoriseer account type voor balans/P&L"""
    if account_type in ['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed']:
        return 'activa'
    elif account_type in ['liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current']:
        return 'passiva'
    elif account_type in ['equity', 'equity_unaffected']:
        return 'eigen_vermogen'
    elif account_type in ['income', 'income_other']:
        return 'opbrengsten'
    elif account_type in ['expense', 'expense_depreciation', 'expense_direct_cost']:
        return 'kosten'
    else:
        return 'overig'

def calculate_pl(lines_df, accounts_df):
    """Bereken Winst & Verlies"""
    if lines_df.empty or accounts_df.empty:
        return pd.DataFrame()
    
    # Merge met accounts voor type info
    merged = lines_df.merge(accounts_df[['id', 'code', 'name', 'account_type']], 
                            left_on='account_id', right_on='id', how='left', suffixes=('', '_acc'))
    
    # Filter op P&L rekeningen
    pl_types = ['income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost']
    pl_lines = merged[merged['account_type'].isin(pl_types)]
    
    # Groepeer per rekening
    pl_summary = pl_lines.groupby(['code', 'name', 'account_type']).agg({
        'debit': 'sum',
        'credit': 'sum',
        'balance': 'sum'
    }).reset_index()
    
    return pl_summary

def get_invoice_pdf(invoice_id):
    """Haal PDF attachment op voor een factuur"""
    try:
        api_key = get_api_key()
        if not api_key:
            return None
        
        # Zoek attachment voor deze factuur
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "service": "object",
                "method": "execute_kw",
                "args": [
                    ODOO_DB, ODOO_UID, api_key,
                    "ir.attachment",
                    "search_read",
                    [[
                        ["res_model", "=", "account.move"],
                        ["res_id", "=", invoice_id],
                        ["mimetype", "=", "application/pdf"]
                    ]],
                    {"fields": ["name", "datas", "mimetype"], "limit": 1}
                ]
            },
            "id": 1
        }
        
        response = requests.post(ODOO_URL, json=payload, timeout=30)
        result = response.json()
        
        if result.get("result"):
            return result["result"][0]
        return None
    except Exception as e:
        st.error(f"Fout bij ophalen PDF: {e}")
        return None

def calculate_balance_sheet(lines_df, accounts_df):
    """Bereken Balans inclusief resultaat lopend boekjaar"""
    if lines_df.empty or accounts_df.empty:
        return pd.DataFrame()

    # Merge met accounts
    merged = lines_df.merge(accounts_df[['id', 'code', 'name', 'account_type']],
                            left_on='account_id', right_on='id', how='left', suffixes=('', '_acc'))

    # Include ALL account types (balance + P&L accounts) to calculate result of the year
    # The balance sheet needs income/expense to compute "Resultaat Lopend Boekjaar"
    all_types = ['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current',
                 'asset_prepayments', 'asset_fixed', 'liability_payable', 'liability_credit_card',
                 'liability_current', 'liability_non_current', 'equity', 'equity_unaffected',
                 'income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost']
    balance_lines = merged[merged['account_type'].isin(all_types)]

    # Groepeer per rekening
    balance_summary = balance_lines.groupby(['code', 'name', 'account_type']).agg({
        'debit': 'sum',
        'credit': 'sum',
        'balance': 'sum'
    }).reset_index()

    return balance_summary

# =============================================================================
# SIDEBAR
# =============================================================================

def render_sidebar():
    """Render sidebar met filters"""
    st.sidebar.image("https://www.pure-original.com/media/logo/stores/1/Pure_Original_logo.png", width=200)
    st.sidebar.title("🎨 Pure & Original")
    st.sidebar.markdown("---")
    
    # API Key input
    if not get_api_key():
        api_key = st.sidebar.text_input("🔑 Odoo API Key", type="password")
        if api_key:
            st.session_state.api_key = api_key
            st.rerun()
        st.sidebar.warning("Voer je Odoo API key in om te starten")
        return None, None, None
    
    # Company filter
    companies = get_companies()
    if not companies:
        st.sidebar.error("Kan bedrijven niet laden")
        return None, None, None
    
    company_options = {c['id']: c['name'] for c in companies}
    company_options[0] = "Alle entiteiten"
    
    selected_company = st.sidebar.selectbox(
        "🏢 Entiteit",
        options=list(company_options.keys()),
        format_func=lambda x: company_options[x],
        index=0
    )
    
    # Date filters
    st.sidebar.markdown("### 📅 Periode")
    current_year = datetime.now().year
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        date_from = st.date_input("Van", datetime(current_year, 1, 1))
    with col2:
        date_to = st.date_input("Tot", datetime.now())
    
    # Quick date selections
    st.sidebar.markdown("**Snelkeuze:**")
    col1, col2, col3 = st.sidebar.columns(3)
    with col1:
        if st.button("YTD"):
            date_from = datetime(current_year, 1, 1).date()
            date_to = datetime.now().date()
    with col2:
        if st.button("Q4"):
            date_from = datetime(current_year, 10, 1).date()
            date_to = datetime(current_year, 12, 31).date()
    with col3:
        if st.button("2025"):
            date_from = datetime(2025, 1, 1).date()
            date_to = datetime(2025, 12, 31).date()
    
    st.sidebar.markdown("---")
    
    # Refresh button
    if st.sidebar.button("🔄 Ververs Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    return selected_company if selected_company != 0 else None, str(date_from), str(date_to)

# =============================================================================
# TAB: OVERZICHT
# =============================================================================

def render_overview(company_id, date_from, date_to):
    """Render financieel overzicht tab"""
    st.header("📊 Financieel Overzicht")
    
    # Haal data op
    invoices = get_invoices(company_id, date_from, date_to)
    if not invoices:
        st.warning("Geen facturen gevonden voor de geselecteerde periode")
        return
    
    df = pd.DataFrame(invoices)
    
    # Bereken KPIs
    sales_invoices = df[df['move_type'].isin(['out_invoice', 'out_refund'])].copy()
    purchase_invoices = df[df['move_type'].isin(['in_invoice', 'in_refund'])].copy()
    
    revenue = sales_invoices[sales_invoices['move_type'] == 'out_invoice']['amount_total'].sum()
    revenue -= sales_invoices[sales_invoices['move_type'] == 'out_refund']['amount_total'].sum()
    
    costs = purchase_invoices[purchase_invoices['move_type'] == 'in_invoice']['amount_total'].sum()
    costs -= purchase_invoices[purchase_invoices['move_type'] == 'in_refund']['amount_total'].sum()
    
    receivables = sales_invoices['amount_residual'].sum()
    payables = purchase_invoices['amount_residual'].sum()
    
    # Display KPIs
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("💰 Omzet (YTD)", format_currency(revenue))
    with col2:
        st.metric("📉 Kosten (YTD)", format_currency(costs))
    with col3:
        st.metric("📥 Openstaand Debiteuren", format_currency(receivables))
    with col4:
        st.metric("📤 Openstaand Crediteuren", format_currency(payables))
    
    st.markdown("---")
    
    # Grafieken
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Omzet per Maand")
        if not sales_invoices.empty:
            sales_invoices['month'] = pd.to_datetime(sales_invoices['invoice_date'], errors='coerce').dt.to_period('M').astype(str)
            monthly = sales_invoices.groupby('month')['amount_total'].sum().reset_index()
            fig = px.bar(monthly, x='month', y='amount_total', 
                        labels={'month': 'Maand', 'amount_total': 'Omzet (€)'},
                        color_discrete_sequence=['#1f77b4'])
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("🏢 Omzet per Entiteit")
        if not sales_invoices.empty:
            # Extract company ID from [id, name] list format
            sales_invoices['company_id_num'] = sales_invoices['company_id'].apply(
                lambda x: x[0] if isinstance(x, (list, tuple)) and len(x) > 0 else x
            )
            company_rev = sales_invoices.groupby('company_id_num')['amount_total'].sum().reset_index()
            company_rev['company_name'] = company_rev['company_id_num'].apply(
                lambda x: COMPANIES.get(x, 'Onbekend') if x else 'Onbekend'
            )
            fig = px.pie(company_rev, values='amount_total', names='company_name',
                        color_discrete_sequence=px.colors.qualitative.Set2)
            st.plotly_chart(fig, use_container_width=True)
    
    # Openstaande facturen tabel
    st.subheader("⏰ Openstaande Facturen (Top 10)")
    open_invoices = df[df['amount_residual'] > 0].nlargest(10, 'amount_residual')
    if not open_invoices.empty:
        display_df = open_invoices[['name', 'partner_id', 'invoice_date', 'invoice_date_due', 
                                    'amount_total', 'amount_residual', 'move_type']].copy()
        display_df['partner_id'] = display_df['partner_id'].apply(lambda x: x[1] if isinstance(x, list) and len(x) > 1 else 'N/A')
        display_df['move_type'] = display_df['move_type'].map({
            'out_invoice': '📤 Verkoop', 'out_refund': '📤 Credit', 
            'in_invoice': '📥 Inkoop', 'in_refund': '📥 Credit'
        })
        display_df.columns = ['Nummer', 'Klant/Leverancier', 'Datum', 'Vervaldatum', 'Totaal', 'Openstaand', 'Type']
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# =============================================================================
# TAB: WINST & VERLIES
# =============================================================================

def render_profit_loss(company_id, date_from, date_to):
    """Render Winst & Verlies tab"""
    st.header("📈 Winst & Verliesrekening")
    
    # Haal data op
    domain = []
    if company_id:
        domain.append(("company_id", "=", company_id))
    domain.append(("date", ">=", date_from))
    domain.append(("date", "<=", date_to))
    domain.append(("parent_state", "=", "posted"))
    
    lines = get_move_lines(domain, ["account_id", "debit", "credit", "balance", "company_id"])
    accounts = get_accounts()
    
    if not lines or not accounts:
        st.warning("Geen data beschikbaar")
        return
    
    lines_df = pd.DataFrame(lines)
    accounts_df = pd.DataFrame(accounts)
    
    # Extract account_id
    lines_df['account_id'] = lines_df['account_id'].apply(lambda x: x[0] if isinstance(x, list) else x)
    
    # Bereken P&L
    pl = calculate_pl(lines_df, accounts_df)
    
    if pl.empty:
        st.warning("Geen P&L data gevonden")
        return
    
    # Split opbrengsten en kosten
    income_types = ['income', 'income_other']
    expense_types = ['expense', 'expense_depreciation', 'expense_direct_cost']
    
    income_df = pl[pl['account_type'].isin(income_types)].copy()
    expense_df = pl[pl['account_type'].isin(expense_types)].copy()
    
    # Bereken totalen (credit - debit voor opbrengsten, debit - credit voor kosten)
    total_income = income_df['credit'].sum() - income_df['debit'].sum()
    total_expense = expense_df['debit'].sum() - expense_df['credit'].sum()
    net_result = total_income - total_expense
    
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💰 Totaal Opbrengsten", format_currency(total_income))
    with col2:
        st.metric("📉 Totaal Kosten", format_currency(total_expense))
    with col3:
        st.metric("📊 Bruto Marge", f"{(total_income - total_expense) / total_income * 100:.1f}%" if total_income > 0 else "N/A")
    with col4:
        delta_color = "normal" if net_result >= 0 else "inverse"
        st.metric("✨ Netto Resultaat", format_currency(net_result))
    
    st.markdown("---")
    
    # Twee kolommen layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💰 Opbrengsten")
        if not income_df.empty:
            income_df['Saldo'] = income_df['credit'] - income_df['debit']
            income_display = income_df[['code', 'name', 'Saldo']].copy()
            income_display.columns = ['Code', 'Rekening', 'Bedrag']
            income_display = income_display.sort_values('Code')
            income_display['Bedrag'] = income_display['Bedrag'].apply(format_currency)
            st.dataframe(income_display, use_container_width=True, hide_index=True)
            st.markdown(f"**Totaal Opbrengsten: {format_currency(total_income)}**")
    
    with col2:
        st.subheader("📉 Kosten")
        if not expense_df.empty:
            expense_df['Saldo'] = expense_df['debit'] - expense_df['credit']
            expense_display = expense_df[['code', 'name', 'Saldo']].copy()
            expense_display.columns = ['Code', 'Rekening', 'Bedrag']
            expense_display = expense_display.sort_values('Code')
            expense_display['Bedrag'] = expense_display['Bedrag'].apply(format_currency)
            st.dataframe(expense_display, use_container_width=True, hide_index=True)
            st.markdown(f"**Totaal Kosten: {format_currency(total_expense)}**")
    
    # Grafiek
    st.markdown("---")
    st.subheader("📊 Kosten per Categorie")
    
    if not expense_df.empty:
        expense_df['category'] = expense_df['code'].str[:2]
        category_totals = expense_df.groupby('category')['Saldo'].sum().reset_index()
        category_totals = category_totals.nlargest(10, 'Saldo')
        
        fig = px.bar(category_totals, x='category', y='Saldo',
                    labels={'category': 'Categorie', 'Saldo': 'Bedrag (€)'},
                    color='Saldo', color_continuous_scale='Reds')
        st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# TAB: BALANS
# =============================================================================

def render_balance_sheet(company_id, date_from, date_to):
    """Render Balans tab"""
    st.header("📋 Balans")

    # Haal data op (balans tot einde periode) - voor activa/passiva/equity
    domain = []
    if company_id:
        domain.append(("company_id", "=", company_id))
    domain.append(("date", "<=", date_to))
    domain.append(("parent_state", "=", "posted"))

    lines = get_move_lines(domain, ["account_id", "debit", "credit", "balance", "company_id", "date"])
    accounts = get_accounts()

    if not lines or not accounts:
        st.warning("Geen data beschikbaar")
        return

    lines_df = pd.DataFrame(lines)
    accounts_df = pd.DataFrame(accounts)

    # Extract account_id
    lines_df['account_id'] = lines_df['account_id'].apply(lambda x: x[0] if isinstance(x, list) else x)

    # Merge met accounts voor account_type
    merged = lines_df.merge(accounts_df[['id', 'code', 'name', 'account_type']],
                            left_on='account_id', right_on='id', how='left', suffixes=('', '_acc'))

    # Categoriseer
    activa_types = ['asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed']
    passiva_types = ['liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current']
    equity_types = ['equity', 'equity_unaffected']
    income_types = ['income', 'income_other']
    expense_types = ['expense', 'expense_depreciation', 'expense_direct_cost']

    # Alle balansrekeningen (cumulatief tot date_to)
    balance_types = activa_types + passiva_types + equity_types
    balance_lines = merged[merged['account_type'].isin(balance_types)]

    # Groepeer balansrekeningen per code
    balance = balance_lines.groupby(['code', 'name', 'account_type']).agg({
        'debit': 'sum',
        'credit': 'sum',
        'balance': 'sum'
    }).reset_index()

    if balance.empty:
        st.warning("Geen balansdata gevonden")
        return

    # Aparte berekening voor income/expense - alleen huidige boekjaar (date_from tot date_to)
    date_from_str = str(date_from)
    pl_lines = merged[(merged['account_type'].isin(income_types + expense_types)) &
                      (merged['date'] >= date_from_str)]

    activa_df = balance[balance['account_type'].isin(activa_types)].copy()
    passiva_df = balance[balance['account_type'].isin(passiva_types)].copy()
    equity_df = balance[balance['account_type'].isin(equity_types)].copy()

    # P&L voor huidige boekjaar
    income_lines = pl_lines[pl_lines['account_type'].isin(income_types)]
    expense_lines = pl_lines[pl_lines['account_type'].isin(expense_types)]

    # Bereken saldi (activa = debit - credit, passiva/equity = credit - debit)
    total_activa = activa_df['debit'].sum() - activa_df['credit'].sum()
    total_passiva = passiva_df['credit'].sum() - passiva_df['debit'].sum()
    total_equity = equity_df['credit'].sum() - equity_df['debit'].sum()

    # Bereken resultaat lopend boekjaar (income - expenses) - alleen van date_from tot date_to
    total_income = income_lines['credit'].sum() - income_lines['debit'].sum()
    total_expense = expense_lines['debit'].sum() - expense_lines['credit'].sum()
    result_year = total_income - total_expense
    
    # KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📈 Totaal Activa", format_currency(total_activa))
    with col2:
        st.metric("📉 Totaal Passiva", format_currency(total_passiva))
    with col3:
        st.metric("💎 Eigen Vermogen", format_currency(total_equity))
    with col4:
        if result_year >= 0:
            st.metric("📊 Resultaat", format_currency(result_year), delta="Winst")
        else:
            st.metric("📊 Resultaat", format_currency(result_year), delta="Verlies")
    with col5:
        # Balans check: Activa = Passiva + EV + Resultaat
        balance_check = total_activa - total_passiva - total_equity - result_year
        if abs(balance_check) < 1:
            st.metric("✅ Balans Check", "Sluit")
        else:
            st.metric("⚠️ Verschil", format_currency(balance_check))
    
    st.markdown("---")
    
    # Kwadrant layout
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 ACTIVA")
        
        # Vaste activa
        fixed_types = ['asset_fixed', 'asset_non_current']
        fixed = activa_df[activa_df['account_type'].isin(fixed_types)].copy()
        if not fixed.empty:
            st.markdown("**Vaste Activa**")
            fixed['Saldo'] = fixed['debit'] - fixed['credit']
            fixed_display = fixed[['code', 'name', 'Saldo']].sort_values('code')
            fixed_display.columns = ['Code', 'Rekening', 'Bedrag']
            fixed_display['Bedrag'] = fixed_display['Bedrag'].apply(format_currency)
            st.dataframe(fixed_display, use_container_width=True, hide_index=True)
        
        # Vlottende activa
        current_types = ['asset_receivable', 'asset_cash', 'asset_current', 'asset_prepayments']
        current = activa_df[activa_df['account_type'].isin(current_types)].copy()
        if not current.empty:
            st.markdown("**Vlottende Activa**")
            current['Saldo'] = current['debit'] - current['credit']
            current_display = current[['code', 'name', 'Saldo']].sort_values('code')
            current_display.columns = ['Code', 'Rekening', 'Bedrag']
            current_display['Bedrag'] = current_display['Bedrag'].apply(format_currency)
            st.dataframe(current_display, use_container_width=True, hide_index=True)
        
        st.markdown(f"### Totaal Activa: {format_currency(total_activa)}")
    
    with col2:
        st.subheader("📉 PASSIVA")
        
        # Eigen vermogen
        if not equity_df.empty:
            st.markdown("**Eigen Vermogen**")
            equity_df['Saldo'] = equity_df['credit'] - equity_df['debit']
            equity_display = equity_df[['code', 'name', 'Saldo']].sort_values('code')
            equity_display.columns = ['Code', 'Rekening', 'Bedrag']
            equity_display['Bedrag'] = equity_display['Bedrag'].apply(format_currency)
            st.dataframe(equity_display, use_container_width=True, hide_index=True)
        
        # Resultaat lopend boekjaar
        st.markdown("**Resultaat Lopend Boekjaar**")
        result_color = "green" if result_year >= 0 else "red"
        st.markdown(f"<span style='font-size:1.1em'>Resultaat: <b style='color:{result_color}'>{format_currency(result_year)}</b></span>", unsafe_allow_html=True)
        
        # Schulden
        if not passiva_df.empty:
            st.markdown("**Schulden**")
            passiva_df['Saldo'] = passiva_df['credit'] - passiva_df['debit']
            passiva_display = passiva_df[['code', 'name', 'Saldo']].sort_values('code')
            passiva_display.columns = ['Code', 'Rekening', 'Bedrag']
            passiva_display['Bedrag'] = passiva_display['Bedrag'].apply(format_currency)
            st.dataframe(passiva_display, use_container_width=True, hide_index=True)
        
        st.markdown(f"### Totaal Passiva: {format_currency(total_passiva + total_equity + result_year)}")

# =============================================================================
# TAB: INTERCOMPANY
# =============================================================================

def render_intercompany(company_id, date_from, date_to):
    """Render Intercompany Monitor tab"""
    st.header("🔄 Intercompany Monitor")
    
    # Haal IC rekeningen op (126xxx) - gebruik =like voor pattern matching
    # Voor IC posities halen we ALLE boekingen t/m einddatum (geen startdatum filter)
    domain = [("account_id.code", "=like", "126%"), ("parent_state", "=", "posted")]
    if company_id:
        domain.append(("company_id", "=", company_id))
    domain.append(("date", "<=", date_to))
    
    lines = get_move_lines(domain, ["account_id", "partner_id", "debit", "credit", "balance", 
                                     "date", "name", "ref", "company_id", "move_id"])
    
    if not lines:
        st.info("Geen intercompany boekingen gevonden")
        return
    
    df = pd.DataFrame(lines)
    
    # Extract IDs
    df['account_code'] = df['account_id'].apply(lambda x: x[1].split()[0] if isinstance(x, list) and len(x) > 1 else 'N/A')
    df['account_name'] = df['account_id'].apply(lambda x: ' '.join(x[1].split()[1:]) if isinstance(x, list) and len(x) > 1 else 'N/A')
    df['partner_name'] = df['partner_id'].apply(lambda x: x[1] if isinstance(x, list) and len(x) > 1 else 'Niet ingevuld')
    df['company_name'] = df['company_id'].apply(lambda x: COMPANIES.get(x[0] if isinstance(x, list) else x, 'Onbekend'))
    
    # Samenvatting per rekening
    summary = df.groupby(['company_name', 'account_code', 'account_name']).agg({
        'debit': 'sum',
        'credit': 'sum',
        'balance': 'sum'
    }).reset_index()
    
    # KPIs
    st.subheader("📊 IC Posities per Entiteit")
    
    for company in summary['company_name'].unique():
        company_data = summary[summary['company_name'] == company]
        net_position = company_data['balance'].sum()
        
        with st.expander(f"🏢 {company} - Netto: {format_currency(net_position)}", expanded=True):
            display_df = company_data[['account_code', 'account_name', 'debit', 'credit', 'balance']].copy()
            display_df.columns = ['Code', 'Rekening', 'Debet', 'Credit', 'Saldo']
            display_df['Debet'] = display_df['Debet'].apply(format_currency)
            display_df['Credit'] = display_df['Credit'].apply(format_currency)
            display_df['Saldo'] = display_df['Saldo'].apply(format_currency)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Reconciliatie check
    st.markdown("---")
    st.subheader("⚠️ Reconciliatie Check")
    
    # Groepeer per IC relatie
    total_po_bv = summary[summary['company_name'] == 'Pure & Original B.V.']['balance'].sum()
    total_po_int = summary[summary['company_name'] == 'Pure & Original International B.V.']['balance'].sum()
    total_mia = summary[summary['company_name'] == 'Mia Colore B.V.']['balance'].sum()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("P&O B.V.", format_currency(total_po_bv))
    with col2:
        st.metric("P&O International", format_currency(total_po_int))
    with col3:
        st.metric("Mia Colore", format_currency(total_mia))
    
    total_all = total_po_bv + total_po_int + total_mia
    if abs(total_all) > 100:
        st.error(f"⚠️ **WAARSCHUWING:** IC posities sluiten niet aan! Verschil: {format_currency(total_all)}")
    else:
        st.success("✅ IC posities sluiten aan")
    
    # Detail transacties
    st.markdown("---")
    st.subheader("📋 Recente IC Transacties")
    
    recent = df.sort_values('date', ascending=False).head(20)[['date', 'company_name', 'account_code', 'partner_name', 'name', 'debit', 'credit']].copy()
    recent.columns = ['Datum', 'Entiteit', 'Rekening', 'Partner', 'Omschrijving', 'Debet', 'Credit']
    recent['Debet'] = recent['Debet'].apply(format_currency)
    recent['Credit'] = recent['Credit'].apply(format_currency)
    st.dataframe(recent, use_container_width=True, hide_index=True)

# =============================================================================
# TAB: BTW ANALYSE
# =============================================================================

def render_vat_analysis(company_id, date_from, date_to):
    """Render BTW Analyse tab"""
    st.header("🧾 BTW Analyse")
    
    # Haal BTW rekeningen op (alleen 15xxxx reeks) - gebruik =like voor pattern matching
    domain = [("account_id.code", "=like", "15%"), ("parent_state", "=", "posted")]
    if company_id:
        domain.append(("company_id", "=", company_id))
    domain.append(("date", ">=", date_from))
    domain.append(("date", "<=", date_to))
    
    lines = get_move_lines(domain, ["account_id", "debit", "credit", "balance", "company_id", "date"])
    
    if not lines:
        st.info("Geen BTW boekingen gevonden")
        return
    
    df = pd.DataFrame(lines)
    
    # Extract account info
    df['account_code'] = df['account_id'].apply(lambda x: x[1].split()[0] if isinstance(x, list) and len(x) > 1 else 'N/A')
    df['account_name'] = df['account_id'].apply(lambda x: ' '.join(x[1].split()[1:]) if isinstance(x, list) and len(x) > 1 else 'N/A')
    df['company_name'] = df['company_id'].apply(lambda x: COMPANIES.get(x[0] if isinstance(x, list) else x, 'Onbekend'))
    
    # Categoriseer BTW (15xxxx reeks)
    def categorize_vat(code):
        # 1500xx = Af te dragen BTW (omzet)
        # 1510xx = Overige BTW posities
        # 1520xx = Voorbelasting
        # 1530xx = Overige voorbelasting / oninbaar
        # 1540xx = Af te dragen diensten
        if code.startswith('1500') or code.startswith('1501') or code.startswith('1502') or code.startswith('1503') or code.startswith('1504') or code.startswith('1505') or code.startswith('1506') or code.startswith('1507') or code.startswith('1508') or code.startswith('1509'):
            return 'Af te dragen'
        elif code.startswith('1510') or code.startswith('1511') or code.startswith('1512') or code.startswith('1513') or code.startswith('1514') or code.startswith('1515') or code.startswith('1516') or code.startswith('1517') or code.startswith('1518') or code.startswith('1519'):
            return 'Af te dragen EU/buiten EU'
        elif code.startswith('152'):
            return 'Voorbelasting'
        elif code.startswith('153'):
            return 'Overig/correcties'
        elif code.startswith('154'):
            return 'Af te dragen diensten'
        else:
            return 'Overig'
    
    df['vat_category'] = df['account_code'].apply(categorize_vat)
    
    # Summary
    summary = df.groupby(['company_name', 'vat_category']).agg({
        'debit': 'sum',
        'credit': 'sum',
        'balance': 'sum'
    }).reset_index()
    
    # KPIs per entiteit
    st.subheader("📊 BTW Overzicht per Entiteit")
    
    for company in df['company_name'].unique():
        company_data = df[df['company_name'] == company]
        
        voorbelasting = company_data[company_data['vat_category'] == 'Voorbelasting']['debit'].sum()
        af_te_dragen = company_data[company_data['vat_category'] == 'Af te dragen']['credit'].sum()
        netto = voorbelasting - af_te_dragen
        
        with st.expander(f"🏢 {company}", expanded=True):
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📥 Voorbelasting", format_currency(voorbelasting))
            with col2:
                st.metric("📤 Af te dragen", format_currency(af_te_dragen))
            with col3:
                if netto >= 0:
                    st.metric("💰 Te vorderen", format_currency(netto))
                else:
                    st.metric("💸 Te betalen", format_currency(abs(netto)))
            
            # Detail tabel
            detail = company_data.groupby(['account_code', 'account_name']).agg({
                'debit': 'sum',
                'credit': 'sum'
            }).reset_index()
            detail['Saldo'] = detail['debit'] - detail['credit']
            detail.columns = ['Code', 'Rekening', 'Debet', 'Credit', 'Saldo']
            detail['Debet'] = detail['Debet'].apply(format_currency)
            detail['Credit'] = detail['Credit'].apply(format_currency)
            detail['Saldo'] = detail['Saldo'].apply(format_currency)
            st.dataframe(detail.sort_values('Code'), use_container_width=True, hide_index=True)
    
    # BTW Risico's
    st.markdown("---")
    st.subheader("⚠️ BTW Risico Signalering")
    
    # Check voor Belgische BTW
    be_vat = df[df['account_name'].str.contains('BE|Belg', case=False, na=False)]
    if not be_vat.empty:
        be_total = be_vat['debit'].sum()
        st.warning(f"""
        🇧🇪 **Belgische BTW Gedetecteerd**
        
        Er is {format_currency(be_total)} aan Belgische BTW geboekt als voorbelasting.
        
        **Risico:** Belgische BTW is mogelijk niet aftrekbaar in NL zonder Belgische BTW-registratie.
        
        **Actie:** Controleer of P&O International een actieve Belgische BTW-registratie heeft.
        """)
    
    # Check voor grote afwijkingen
    for company in df['company_name'].unique():
        company_data = df[df['company_name'] == company]
        voorbelasting = company_data[company_data['vat_category'] == 'Voorbelasting']['debit'].sum()
        af_te_dragen = company_data[company_data['vat_category'] == 'Af te dragen']['credit'].sum()
        
        if voorbelasting > 0 and af_te_dragen > 0:
            ratio = voorbelasting / af_te_dragen
            if ratio > 0.5:
                st.info(f"ℹ️ **{company}**: Voorbelasting/Afdracht ratio = {ratio:.1%} - Mogelijk veel inkoop of investeringen")

# =============================================================================
# TAB: FACTUREN
# =============================================================================

@st.dialog("📄 Factuur PDF", width="large")
def show_invoice_pdf_dialog(invoice_id, invoice_name):
    """Toon factuur PDF in een popup dialog"""
    import base64
    import streamlit.components.v1 as components

    st.write(f"**Factuur:** {invoice_name}")

    with st.spinner("PDF laden..."):
        attachment = get_invoice_pdf(invoice_id)

        if attachment and attachment.get('datas'):
            # PDF data is al base64 encoded vanuit Odoo
            pdf_base64 = attachment['datas']
            pdf_bytes = base64.b64decode(pdf_base64)

            # Download knop bovenaan voor snelle toegang
            st.download_button(
                label="⬇️ Download PDF",
                data=pdf_bytes,
                file_name=f"{invoice_name}.pdf",
                mime="application/pdf",
                type="primary"
            )

            st.divider()

            # Toon PDF met pdf.js voor betere browser compatibiliteit
            pdf_viewer_html = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ margin: 0; padding: 0; }}
                    #pdf-container {{ width: 100%; height: 650px; }}
                    #pdf-canvas {{ width: 100%; }}
                    .pdf-controls {{
                        padding: 10px;
                        background: #f0f2f6;
                        border-radius: 8px 8px 0 0;
                        display: flex;
                        justify-content: center;
                        gap: 10px;
                        align-items: center;
                    }}
                    .pdf-controls button {{
                        padding: 8px 16px;
                        border: none;
                        background: #ff4b4b;
                        color: white;
                        border-radius: 4px;
                        cursor: pointer;
                        font-size: 14px;
                    }}
                    .pdf-controls button:hover {{ background: #ff3333; }}
                    .pdf-controls span {{ font-size: 14px; }}
                    #pdf-viewer {{
                        width: 100%;
                        height: 600px;
                        border: 1px solid #ddd;
                        border-radius: 0 0 8px 8px;
                        overflow: auto;
                        background: #525659;
                    }}
                    canvas {{ display: block; margin: 10px auto; }}
                </style>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
            </head>
            <body>
                <div id="pdf-container">
                    <div class="pdf-controls">
                        <button onclick="prevPage()">◀ Vorige</button>
                        <span>Pagina <span id="page-num">1</span> / <span id="page-count">-</span></span>
                        <button onclick="nextPage()">Volgende ▶</button>
                        <button onclick="zoomOut()">−</button>
                        <span id="zoom-level">100%</span>
                        <button onclick="zoomIn()">+</button>
                    </div>
                    <div id="pdf-viewer">
                        <canvas id="pdf-canvas"></canvas>
                    </div>
                </div>
                <script>
                    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

                    let pdfDoc = null;
                    let pageNum = 1;
                    let scale = 1.5;
                    const canvas = document.getElementById('pdf-canvas');
                    const ctx = canvas.getContext('2d');

                    // Laad PDF vanuit base64
                    const pdfData = atob("{pdf_base64}");
                    const pdfArray = new Uint8Array(pdfData.length);
                    for (let i = 0; i < pdfData.length; i++) {{
                        pdfArray[i] = pdfData.charCodeAt(i);
                    }}

                    pdfjsLib.getDocument({{data: pdfArray}}).promise.then(function(pdf) {{
                        pdfDoc = pdf;
                        document.getElementById('page-count').textContent = pdf.numPages;
                        renderPage(pageNum);
                    }}).catch(function(error) {{
                        document.getElementById('pdf-viewer').innerHTML = '<p style="color: white; text-align: center; padding: 20px;">Fout bij laden PDF: ' + error.message + '</p>';
                    }});

                    function renderPage(num) {{
                        pdfDoc.getPage(num).then(function(page) {{
                            const viewport = page.getViewport({{scale: scale}});
                            canvas.height = viewport.height;
                            canvas.width = viewport.width;
                            page.render({{canvasContext: ctx, viewport: viewport}});
                            document.getElementById('page-num').textContent = num;
                        }});
                    }}

                    function prevPage() {{
                        if (pageNum <= 1) return;
                        pageNum--;
                        renderPage(pageNum);
                    }}

                    function nextPage() {{
                        if (pageNum >= pdfDoc.numPages) return;
                        pageNum++;
                        renderPage(pageNum);
                    }}

                    function zoomIn() {{
                        scale += 0.25;
                        document.getElementById('zoom-level').textContent = Math.round(scale / 1.5 * 100) + '%';
                        renderPage(pageNum);
                    }}

                    function zoomOut() {{
                        if (scale <= 0.5) return;
                        scale -= 0.25;
                        document.getElementById('zoom-level').textContent = Math.round(scale / 1.5 * 100) + '%';
                        renderPage(pageNum);
                    }}
                </script>
            </body>
            </html>
            '''

            components.html(pdf_viewer_html, height=700, scrolling=False)
        else:
            st.warning("Geen PDF gevonden voor deze factuur. Mogelijk is de factuur nog niet gegenereerd of is deze handmatig verwijderd.")
            st.info("💡 Tip: Open de factuur in Odoo en klik op 'Afdrukken' om de PDF te genereren.")

def render_invoices(company_id, date_from, date_to):
    """Render Facturen drill-down tab"""
    st.header("📄 Facturen Drill-down")
    
    invoices = get_invoices(company_id, date_from, date_to, limit=1000)
    if not invoices:
        st.warning("Geen facturen gevonden")
        return
    
    df = pd.DataFrame(invoices)
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        move_types = st.multiselect(
            "Type",
            options=['out_invoice', 'out_refund', 'in_invoice', 'in_refund'],
            default=['out_invoice', 'in_invoice'],
            format_func=lambda x: {'out_invoice': '📤 Verkoopfactuur', 'out_refund': '📤 Creditnota verkoop',
                                   'in_invoice': '📥 Inkoopfactuur', 'in_refund': '📥 Creditnota inkoop'}[x]
        )
    
    with col2:
        states = st.multiselect(
            "Status",
            options=['draft', 'posted', 'cancel'],
            default=['posted'],
            format_func=lambda x: {'draft': 'Concept', 'posted': 'Geboekt', 'cancel': 'Geannuleerd'}[x]
        )
    
    with col3:
        payment_states = st.multiselect(
            "Betaalstatus",
            options=['not_paid', 'partial', 'paid', 'in_payment', 'reversed'],
            default=['not_paid', 'partial', 'paid'],
            format_func=lambda x: {'not_paid': 'Niet betaald', 'partial': 'Deels betaald', 
                                   'paid': 'Betaald', 'in_payment': 'In betaling', 'reversed': 'Teruggedraaid'}.get(x, x)
        )
    
    # Filter data
    filtered = df[
        (df['move_type'].isin(move_types)) &
        (df['state'].isin(states)) &
        (df['payment_state'].isin(payment_states))
    ]
    
    # Stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📋 Aantal facturen", len(filtered))
    with col2:
        st.metric("💰 Totaal bedrag", format_currency(filtered['amount_total'].sum()))
    with col3:
        st.metric("📥 Openstaand", format_currency(filtered['amount_residual'].sum()))
    with col4:
        paid_pct = (1 - filtered['amount_residual'].sum() / filtered['amount_total'].sum()) * 100 if filtered['amount_total'].sum() > 0 else 0
        st.metric("✅ Betaald %", f"{paid_pct:.1f}%")
    
    st.markdown("---")
    
    # PDF Viewer sectie
    st.subheader("🔍 Factuur bekijken")
    
    if not filtered.empty:
        # Maak een selectbox met factuurnummers
        invoice_options = {f"{row['name']} - {row['partner_id'][1] if isinstance(row['partner_id'], list) else 'N/A'} ({format_currency(row['amount_total'])})": row['id'] 
                          for _, row in filtered.iterrows()}
        
        col1, col2 = st.columns([3, 1])
        with col1:
            selected_invoice = st.selectbox(
                "Selecteer factuur om te bekijken:",
                options=list(invoice_options.keys()),
                index=None,
                placeholder="Kies een factuur..."
            )
        
        with col2:
            st.write("")  # Spacer
            st.write("")  # Spacer
            if selected_invoice:
                invoice_id = invoice_options[selected_invoice]
                invoice_name = selected_invoice.split(" - ")[0]
                if st.button("📄 Bekijk PDF", type="primary", use_container_width=True):
                    show_invoice_pdf_dialog(invoice_id, invoice_name)
        
        st.markdown("---")
        st.subheader("📋 Facturenoverzicht")
        
        # Tabel
        display = filtered[['name', 'partner_id', 'invoice_date', 'invoice_date_due', 
                           'move_type', 'amount_total', 'amount_residual', 'payment_state']].copy()
        display['partner_id'] = display['partner_id'].apply(lambda x: x[1] if isinstance(x, list) and len(x) > 1 else 'N/A')
        display['move_type'] = display['move_type'].map({
            'out_invoice': '📤 Verkoop', 'out_refund': '📤 Credit',
            'in_invoice': '📥 Inkoop', 'in_refund': '📥 Credit'
        })
        display['payment_state'] = display['payment_state'].map({
            'not_paid': '🔴 Niet betaald', 'partial': '🟡 Deels', 
            'paid': '🟢 Betaald', 'in_payment': '🔵 In betaling', 'reversed': '⚪ Teruggedraaid'
        })
        display.columns = ['Nummer', 'Relatie', 'Datum', 'Vervaldatum', 'Type', 'Totaal', 'Openstaand', 'Status']
        
        st.dataframe(display, use_container_width=True, hide_index=True)

# =============================================================================
# TAB: BANK
# =============================================================================

def render_bank(company_id, date_from, date_to):
    """Render Bank saldi tab"""
    st.header("🏦 Banksaldi")

    # Haal closing balance (t/m einddatum)
    domain_closing = [("account_id.account_type", "=", "asset_cash")]
    if company_id:
        domain_closing.append(("company_id", "=", company_id))
    domain_closing.append(("date", "<=", date_to))
    domain_closing.append(("parent_state", "=", "posted"))

    lines_closing = get_move_lines(domain_closing, ["account_id", "debit", "credit", "balance", "company_id", "date"])

    # Haal opening balance (vóór startdatum)
    domain_opening = [("account_id.account_type", "=", "asset_cash")]
    if company_id:
        domain_opening.append(("company_id", "=", company_id))
    domain_opening.append(("date", "<", date_from))
    domain_opening.append(("parent_state", "=", "posted"))

    lines_opening = get_move_lines(domain_opening, ["account_id", "debit", "credit", "balance", "company_id"])

    if not lines_closing:
        st.info("Geen bankgegevens gevonden")
        return

    df_closing = pd.DataFrame(lines_closing)

    # Extract info
    df_closing['account_name'] = df_closing['account_id'].apply(lambda x: x[1] if isinstance(x, list) and len(x) > 1 else 'N/A')
    df_closing['company_name'] = df_closing['company_id'].apply(lambda x: COMPANIES.get(x[0] if isinstance(x, list) else x, 'Onbekend'))

    # Closing balance per bank per entiteit
    summary_closing = df_closing.groupby(['company_name', 'account_name']).agg({
        'debit': 'sum',
        'credit': 'sum'
    }).reset_index()
    summary_closing['Eindsaldo'] = summary_closing['debit'] - summary_closing['credit']

    # Opening balance
    if lines_opening:
        df_opening = pd.DataFrame(lines_opening)
        df_opening['account_name'] = df_opening['account_id'].apply(lambda x: x[1] if isinstance(x, list) and len(x) > 1 else 'N/A')
        df_opening['company_name'] = df_opening['company_id'].apply(lambda x: COMPANIES.get(x[0] if isinstance(x, list) else x, 'Onbekend'))
        summary_opening = df_opening.groupby(['company_name', 'account_name']).agg({
            'debit': 'sum',
            'credit': 'sum'
        }).reset_index()
        summary_opening['Beginsaldo'] = summary_opening['debit'] - summary_opening['credit']
    else:
        summary_opening = pd.DataFrame(columns=['company_name', 'account_name', 'Beginsaldo'])

    # Merge opening en closing
    summary = summary_closing[['company_name', 'account_name', 'Eindsaldo']].merge(
        summary_opening[['company_name', 'account_name', 'Beginsaldo']],
        on=['company_name', 'account_name'],
        how='left'
    )
    summary['Beginsaldo'] = summary['Beginsaldo'].fillna(0)
    summary['Mutatie'] = summary['Eindsaldo'] - summary['Beginsaldo']

    # Totalen
    total_opening = summary['Beginsaldo'].sum()
    total_closing = summary['Eindsaldo'].sum()
    total_movement = summary['Mutatie'].sum()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📅 Beginsaldo", format_currency(total_opening))
    with col2:
        st.metric("📈 Mutatie periode", format_currency(total_movement),
                  delta="Positief" if total_movement >= 0 else "Negatief")
    with col3:
        st.metric("💰 Eindsaldo", format_currency(total_closing))

    st.markdown("---")

    # Per entiteit
    for company in summary['company_name'].unique():
        company_data = summary[summary['company_name'] == company]
        company_total = company_data['Eindsaldo'].sum()

        with st.expander(f"🏢 {company} - {format_currency(company_total)}", expanded=True):
            display = company_data[['account_name', 'Beginsaldo', 'Mutatie', 'Eindsaldo']].copy()
            display.columns = ['Bankrekening', 'Beginsaldo', 'Mutatie', 'Eindsaldo']
            display['Beginsaldo'] = display['Beginsaldo'].apply(format_currency)
            display['Mutatie'] = display['Mutatie'].apply(format_currency)
            display['Eindsaldo'] = display['Eindsaldo'].apply(format_currency)
            st.dataframe(display, use_container_width=True, hide_index=True)

    # Grafiek
    st.markdown("---")
    st.subheader("📊 Verdeling Liquide Middelen (Eindsaldo)")

    fig = px.pie(summary, values='Eindsaldo', names='company_name',
                color_discrete_sequence=px.colors.qualitative.Set2,
                title="Per Entiteit")
    st.plotly_chart(fig, use_container_width=True)

# =============================================================================
# TAB: CASHFLOW PROGNOSE
# =============================================================================

def render_cashflow(company_id, date_from, date_to):
    """Render Cashflow Prognose tab"""
    st.header("💹 Cashflow Overzicht")

    # Bepaal of historische of toekomstige view
    today = datetime.now().date()
    start_date = date_from if isinstance(date_from, date) else date_from.date() if hasattr(date_from, 'date') else today
    end_date = date_to if isinstance(date_to, date) else date_to.date() if hasattr(date_to, 'date') else today

    # Haal alle facturen op (niet alleen openstaande)
    all_invoices = get_invoices(company_id, limit=10000)
    if not all_invoices:
        st.warning("Geen factuurdata beschikbaar")
        return

    df = pd.DataFrame(all_invoices)

    # Huidig banksaldo (t/m vandaag)
    domain = [("account_id.account_type", "=", "asset_cash"), ("parent_state", "=", "posted")]
    if company_id:
        domain.append(("company_id", "=", company_id))

    bank_lines = get_move_lines(domain, ["debit", "credit", "date"])
    current_balance = sum(l['debit'] - l['credit'] for l in bank_lines) if bank_lines else 0

    # Bereken banksaldo op startdatum (voor historische view)
    if bank_lines:
        start_date_str = start_date.strftime('%Y-%m-%d')
        balance_at_start = sum(
            l['debit'] - l['credit']
            for l in bank_lines
            if l['date'] < start_date_str
        )
    else:
        balance_at_start = 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("🏦 Huidig Banksaldo", format_currency(current_balance))
    with col2:
        st.metric("📅 Saldo op startdatum", format_currency(balance_at_start))

    st.markdown("---")

    # Converteer data (errors='coerce' converts invalid values to NaT)
    df['invoice_date'] = pd.to_datetime(df['invoice_date'], errors='coerce')
    df['invoice_date_due'] = pd.to_datetime(df['invoice_date_due'], errors='coerce')

    # Remove rows with invalid dates
    df = df.dropna(subset=['invoice_date'])

    if df.empty:
        st.warning("Geen facturen met geldige datums gevonden")
        return

    # Categoriseer als inkomend of uitgaand
    df['type'] = df['move_type'].apply(
        lambda x: 'Inkomend' if x in ['out_invoice'] else 'Uitgaand' if x in ['in_invoice'] else 'Overig'
    )

    # Filter relevante facturen
    df = df[df['type'].isin(['Inkomend', 'Uitgaand'])]

    # Bereken aantal weken tussen start en eind
    weeks_diff = max(1, (end_date - start_date).days // 7 + 1)
    weeks_diff = min(weeks_diff, 52)  # Max 52 weken

    # Cashflow per week
    weeks = []
    running_balance = balance_at_start

    for i in range(weeks_diff):
        week_start = start_date + timedelta(weeks=i)
        week_end = week_start + timedelta(days=7)

        week_start_dt = pd.Timestamp(week_start)
        week_end_dt = pd.Timestamp(week_end)

        # Voor historische periodes: kijk naar betaalde facturen (amount_total - amount_residual)
        # Voor toekomstige periodes: kijk naar verwachte betalingen op due date

        if week_end <= today:
            # Historisch: gebruik factuurdatum en bekijk betaalde bedragen
            week_incoming = df[
                (df['type'] == 'Inkomend') &
                (df['invoice_date'] >= week_start_dt) &
                (df['invoice_date'] < week_end_dt)
            ]['amount_total'].sum()

            week_outgoing = df[
                (df['type'] == 'Uitgaand') &
                (df['invoice_date'] >= week_start_dt) &
                (df['invoice_date'] < week_end_dt)
            ]['amount_total'].sum()

            week_label = f"{week_start.strftime('%d-%m')}"
        else:
            # Toekomst: gebruik vervaldatum en openstaande bedragen
            open_invoices = df[df['amount_residual'] > 0]

            week_incoming = open_invoices[
                (open_invoices['type'] == 'Inkomend') &
                (open_invoices['invoice_date_due'] >= week_start_dt) &
                (open_invoices['invoice_date_due'] < week_end_dt)
            ]['amount_residual'].sum()

            week_outgoing = open_invoices[
                (open_invoices['type'] == 'Uitgaand') &
                (open_invoices['invoice_date_due'] >= week_start_dt) &
                (open_invoices['invoice_date_due'] < week_end_dt)
            ]['amount_residual'].sum()

            week_label = f"{week_start.strftime('%d-%m')} *"

        netto = week_incoming - week_outgoing
        running_balance += netto

        weeks.append({
            'Periode': week_label,
            'Start': week_start.strftime('%d-%m-%Y'),
            'Inkomend': week_incoming,
            'Uitgaand': -week_outgoing,
            'Netto': netto,
            'Cumulatief': running_balance
        })

    weeks_df = pd.DataFrame(weeks)

    # Grafiek
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=weeks_df['Periode'],
        y=weeks_df['Inkomend'],
        name='Inkomend',
        marker_color='green'
    ))

    fig.add_trace(go.Bar(
        x=weeks_df['Periode'],
        y=weeks_df['Uitgaand'],
        name='Uitgaand',
        marker_color='red'
    ))

    fig.add_trace(go.Scatter(
        x=weeks_df['Periode'],
        y=weeks_df['Cumulatief'],
        name='Cumulatief Saldo',
        line=dict(color='blue', width=3),
        mode='lines+markers'
    ))

    fig.update_layout(
        title=f'Cashflow Overzicht ({start_date.strftime("%d-%m-%Y")} - {end_date.strftime("%d-%m-%Y")})',
        barmode='relative',
        yaxis_title='Bedrag (€)',
        legend=dict(orientation='h', yanchor='bottom', y=1.02)
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption("* = Toekomstige weken (prognose op basis van openstaande facturen)")

    # Tabel
    st.subheader("📋 Cashflow Detail")
    display_df = weeks_df.copy()
    for col in ['Inkomend', 'Uitgaand', 'Netto', 'Cumulatief']:
        display_df[col] = display_df[col].apply(format_currency)
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Waarschuwingen
    min_balance = weeks_df['Cumulatief'].min()
    if min_balance < 0:
        st.error(f"⚠️ **Let op:** Negatief saldo van {format_currency(min_balance)} in de geselecteerde periode!")
    elif current_balance > 0 and min_balance < current_balance * 0.2:
        st.warning(f"⚠️ Laagste saldo: {format_currency(min_balance)} - plan voor liquiditeit")

# =============================================================================
# TAB: PRODUCTEN
# =============================================================================

def render_products(company_id, date_from, date_to):
    """Render Producten & Categorieën tab"""
    st.header("📦 Producten & Categorieën")
    
    # Haal producten op
    products = get_products(limit=1000)
    categories = get_product_categories()
    
    if not products:
        st.warning("Geen productdata beschikbaar")
        return
    
    products_df = pd.DataFrame(products)
    
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📦 Totaal Producten", len(products_df))
    with col2:
        active = len(products_df[products_df['active'] == True])
        st.metric("✅ Actieve Producten", active)
    with col3:
        total_stock = products_df['qty_available'].sum()
        st.metric("📊 Totale Voorraad", f"{total_stock:,.0f}")
    with col4:
        avg_price = products_df['list_price'].mean()
        st.metric("💰 Gem. Verkoopprijs", format_currency(avg_price))
    
    st.markdown("---")
    
    # Categorieën
    st.subheader("📂 Productcategorieën")
    
    if categories:
        cat_df = pd.DataFrame(categories)
        
        # Tel producten per categorie
        products_df['category_name'] = products_df['categ_id'].apply(
            lambda x: x[1] if isinstance(x, list) and len(x) > 1 else 'Geen categorie'
        )
        
        cat_counts = products_df.groupby('category_name').agg({
            'id': 'count',
            'qty_available': 'sum',
            'list_price': 'mean'
        }).reset_index()
        cat_counts.columns = ['Categorie', 'Aantal Producten', 'Voorraad', 'Gem. Prijs']
        cat_counts = cat_counts.sort_values('Aantal Producten', ascending=False)
        
        # Grafiek
        fig = px.bar(cat_counts.head(15), x='Categorie', y='Aantal Producten',
                    title='Top 15 Productcategorieën',
                    color='Voorraad', color_continuous_scale='Blues')
        fig.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabel
        cat_counts['Gem. Prijs'] = cat_counts['Gem. Prijs'].apply(format_currency)
        st.dataframe(cat_counts, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Top producten
    st.subheader("🏆 Top Producten (op basis van voorraad)")
    
    top_products = products_df.nlargest(20, 'qty_available')[
        ['default_code', 'name', 'category_name', 'list_price', 'standard_price', 'qty_available']
    ].copy()
    
    top_products.columns = ['Code', 'Naam', 'Categorie', 'Verkoopprijs', 'Kostprijs', 'Voorraad']
    top_products['Verkoopprijs'] = top_products['Verkoopprijs'].apply(format_currency)
    top_products['Kostprijs'] = top_products['Kostprijs'].apply(format_currency)
    
    st.dataframe(top_products, use_container_width=True, hide_index=True)
    
    # Marge analyse
    st.markdown("---")
    st.subheader("💹 Marge Analyse")
    
    products_df['margin'] = products_df['list_price'] - products_df['standard_price']
    products_df['margin_pct'] = (products_df['margin'] / products_df['list_price'] * 100).fillna(0)
    
    # Filter producten met prijs > 0
    margin_df = products_df[products_df['list_price'] > 0].copy()
    
    if not margin_df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            avg_margin = margin_df['margin_pct'].mean()
            st.metric("📊 Gemiddelde Marge %", f"{avg_margin:.1f}%")
            
            # Marge distributie
            fig = px.histogram(margin_df, x='margin_pct', nbins=20,
                             title='Verdeling Margepercentage',
                             labels={'margin_pct': 'Marge %'})
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            # Laagste marges
            st.markdown("**⚠️ Producten met Laagste Marge:**")
            low_margin = margin_df.nsmallest(10, 'margin_pct')[['name', 'list_price', 'standard_price', 'margin_pct']]
            low_margin.columns = ['Product', 'Verkoopprijs', 'Kostprijs', 'Marge %']
            low_margin['Verkoopprijs'] = low_margin['Verkoopprijs'].apply(format_currency)
            low_margin['Kostprijs'] = low_margin['Kostprijs'].apply(format_currency)
            low_margin['Marge %'] = low_margin['Marge %'].apply(lambda x: f"{x:.1f}%")
            st.dataframe(low_margin, use_container_width=True, hide_index=True)

# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main dashboard functie"""
    
    # Render sidebar en krijg filters
    company_id, date_from, date_to = render_sidebar()
    
    if not get_api_key():
        st.title("🎨 Pure & Original CFO Dashboard")
        st.info("👈 Voer je Odoo API key in via de sidebar om te starten")
        return
    
    # Tabs
    tabs = st.tabs([
        "📊 Overzicht",
        "📈 Winst & Verlies", 
        "📋 Balans",
        "🔄 Intercompany",
        "🧾 BTW Analyse",
        "📄 Facturen",
        "🏦 Bank",
        "💹 Cashflow",
        "📦 Producten"
    ])
    
    with tabs[0]:
        render_overview(company_id, date_from, date_to)
    
    with tabs[1]:
        render_profit_loss(company_id, date_from, date_to)
    
    with tabs[2]:
        render_balance_sheet(company_id, date_from, date_to)
    
    with tabs[3]:
        render_intercompany(company_id, date_from, date_to)
    
    with tabs[4]:
        render_vat_analysis(company_id, date_from, date_to)
    
    with tabs[5]:
        render_invoices(company_id, date_from, date_to)
    
    with tabs[6]:
        render_bank(company_id, date_from, date_to)
    
    with tabs[7]:
        render_cashflow(company_id, date_from, date_to)
    
    with tabs[8]:
        render_products(company_id, date_from, date_to)

if __name__ == "__main__":
    main()
