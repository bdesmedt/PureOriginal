"""
Pure & Original Financial Dashboard v1
======================================
CFO Dashboard voor Pure & Original met:
- Financieel overzicht YTD per entiteit
- Intercompany posities en reconciliatie
- BTW-analyse met BE BTW risico monitoring
- Banksaldi
- Factuur drill-down
- Cashflow prognose
- Balans
- AI Chat assistent

Bedrijven:
- Pure & Original B.V. (ID: 1) - NL820994297B01
- Pure & Original International B.V. (ID: 3) - NL862809095B01
- Mia Colore B.V. (ID: 2) - NL820994327B01
"""

import subprocess
import sys

def install_packages():
    packages = ['plotly', 'pandas', 'requests', 'streamlit']
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
from datetime import datetime, timedelta
from functools import lru_cache

# =============================================================================
# CONFIGURATIE
# =============================================================================

st.set_page_config(
    page_title="Pure & Original Dashboard",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Odoo configuratie
ODOO_URL = "https://pureoriginal.odoo.com/jsonrpc"
ODOO_DB = "pureoriginal-main-6280301"
ODOO_LOGIN = "f.brandsma@pure-original.nl"

# API Key - probeer secrets, anders gebruik session state
def get_api_key():
    try:
        key = st.secrets.get("ODOO_API_KEY", "")
        if key:
            return key
    except:
        pass
    return st.session_state.get("api_key", "")

# Bedrijven configuratie
COMPANIES = {
    1: {"name": "Pure & Original B.V.", "vat": "NL820994297B01", "short": "P&O BV"},
    3: {"name": "Pure & Original International B.V.", "vat": "NL862809095B01", "short": "P&O Int"},
    2: {"name": "Mia Colore B.V.", "vat": "NL820994327B01", "short": "Mia Colore"}
}

# Intercompany partner IDs (te bepalen uit data)
INTERCOMPANY_PARTNERS = []  # Wordt dynamisch gevuld

# R/C rekeningen voor intercompany
IC_ACCOUNTS = {
    "126100": "R/C Pure & Original International B.V.",
    "126200": "R/C Mia Colore B.V.",
    "126300": "R/C P&O BV (vanuit Int)",
    "126400": "R/C P&O BV (vanuit Mia)"
}

# =============================================================================
# ODOO API HELPERS
# =============================================================================

def get_uid():
    """Authenticate and get user ID"""
    api_key = get_api_key()
    if not api_key:
        return None
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "common",
            "method": "authenticate",
            "args": [ODOO_DB, ODOO_LOGIN, api_key, {}]
        },
        "id": 1
    }
    
    try:
        response = requests.post(ODOO_URL, json=payload, timeout=30)
        result = response.json()
        return result.get("result")
    except Exception as e:
        st.error(f"Auth error: {e}")
        return None

def odoo_call(model, method, domain, fields, limit=None, timeout=120):
    """Generieke Odoo JSON-RPC call"""
    api_key = get_api_key()
    uid = get_uid()
    if not api_key or not uid:
        return []

    args = [ODOO_DB, uid, api_key, model, method, [domain]]
    kwargs = {"fields": fields, "context": {"lang": "nl_NL"}}
    if limit:
        kwargs["limit"] = limit
    args.append(kwargs)

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": args
        },
        "id": 1
    }

    try:
        response = requests.post(ODOO_URL, json=payload, timeout=timeout)
        result = response.json()
        if "error" in result:
            st.error(f"Odoo error: {result['error']}")
            return []
        return result.get("result", [])
    except requests.exceptions.Timeout:
        st.error("⏱️ Timeout - probeer een kortere periode")
        return []
    except Exception as e:
        st.error(f"Connection error: {e}")
        return []

def odoo_read_group(model, domain, fields, groupby, timeout=120):
    """Odoo read_group voor server-side aggregatie"""
    api_key = get_api_key()
    uid = get_uid()
    if not api_key or not uid:
        return []

    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, uid, api_key, model, "read_group",
                    [domain], {
                        "fields": fields,
                        "groupby": groupby,
                        "lazy": False,
                        "context": {"active_test": False, "lang": "nl_NL"}
                    }]
        },
        "id": 1
    }

    try:
        response = requests.post(ODOO_URL, json=payload, timeout=timeout)
        result = response.json()
        if "error" in result:
            st.error(f"Odoo read_group error: {result['error']}")
            return []
        return result.get("result", [])
    except Exception as e:
        st.error(f"Read group error: {e}")
        return []

# =============================================================================
# DATA FUNCTIES
# =============================================================================

@st.cache_data(ttl=300)
def get_bank_balances():
    """Haal alle banksaldi op per rekening"""
    journals = odoo_call(
        "account.journal", "search_read",
        [["type", "=", "bank"]],
        ["name", "company_id", "default_account_id", "current_statement_balance", "code"]
    )
    return journals

@st.cache_data(ttl=3600)
def get_revenue_aggregated(year, company_id=None):
    """Server-side geaggregeerde omzetdata"""
    domain = [
        ("account_id.code", ">=", "800000"),
        ("account_id.code", "<", "900000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))

    result = odoo_read_group("account.move.line", domain, ["balance:sum"], ["date:month"])
    return result

@st.cache_data(ttl=3600)
def get_cost_aggregated(year, company_id=None):
    """Server-side geaggregeerde kostendata"""
    # 4* rekeningen (personeelskosten etc)
    domain_4 = [
        ("account_id.code", ">=", "400000"),
        ("account_id.code", "<", "500000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain_4.append(("company_id", "=", company_id))

    # 7* rekeningen (kostprijs verkopen)
    domain_7 = [
        ("account_id.code", ">=", "700000"),
        ("account_id.code", "<", "800000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain_7.append(("company_id", "=", company_id))

    result_4 = odoo_read_group("account.move.line", domain_4, ["balance:sum"], ["date:month"])
    result_7 = odoo_read_group("account.move.line", domain_7, ["balance:sum"], ["date:month"])

    # Combineer
    monthly = {}
    for r in result_4 + result_7:
        month = r.get("date:month", "Unknown")
        if month not in monthly:
            monthly[month] = 0
        monthly[month] += r.get("balance", 0)

    return [{"date:month": k, "balance": v} for k, v in monthly.items()]

@st.cache_data(ttl=300)
def get_intercompany_balances():
    """Haal R/C intercompany saldi op"""
    domain = [
        ("account_id.code", "like", "126%"),
        ("parent_state", "=", "posted")
    ]
    
    result = odoo_read_group(
        "account.move.line",
        domain,
        ["balance:sum", "debit:sum", "credit:sum"],
        ["account_id", "company_id"]
    )
    return result

@st.cache_data(ttl=300)
def get_vat_balances(year, company_id=None):
    """Haal BTW-saldi op per rekening"""
    domain = [
        ("account_id.code", "like", "15%"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    result = odoo_read_group(
        "account.move.line",
        domain,
        ["balance:sum", "debit:sum", "credit:sum"],
        ["account_id", "company_id"]
    )
    return result

@st.cache_data(ttl=300)
def get_belgian_vat_transactions(year):
    """Haal Belgische BTW transacties op (BE 21% tarief)"""
    # Zoek naar transacties met BE BTW
    domain = [
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted"),
        ("tax_ids.name", "ilike", "BE%")
    ]
    
    result = odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "name", "debit", "credit", "balance", "account_id", "company_id", "partner_id", "tax_ids"],
        limit=500
    )
    return result

@st.cache_data(ttl=300)
def get_receivables_payables(company_id=None):
    """Haal debiteuren en crediteuren saldi op"""
    # Debiteuren
    rec_domain = [
        ["account_id.account_type", "=", "asset_receivable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0]
    ]
    if company_id:
        rec_domain.append(["company_id", "=", company_id])

    receivables = odoo_call(
        "account.move.line", "search_read",
        rec_domain,
        ["company_id", "amount_residual", "partner_id", "date_maturity"],
        limit=5000
    )

    # Crediteuren
    pay_domain = [
        ["account_id.account_type", "=", "liability_payable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0]
    ]
    if company_id:
        pay_domain.append(["company_id", "=", company_id])

    payables = odoo_call(
        "account.move.line", "search_read",
        pay_domain,
        ["company_id", "amount_residual", "partner_id", "date_maturity"],
        limit=5000
    )

    return receivables, payables

@st.cache_data(ttl=300)
def get_invoices(year, company_id=None, invoice_type=None, state=None):
    """Haal facturen op"""
    domain = [
        ["invoice_date", ">=", f"{year}-01-01"],
        ["invoice_date", "<=", f"{year}-12-31"]
    ]

    if company_id:
        domain.append(["company_id", "=", company_id])

    if invoice_type == "verkoop":
        domain.append(["move_type", "in", ["out_invoice", "out_refund"]])
    elif invoice_type == "inkoop":
        domain.append(["move_type", "in", ["in_invoice", "in_refund"]])
    else:
        domain.append(["move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]])

    if state:
        domain.append(["state", "=", state])

    return odoo_call(
        "account.move", "search_read",
        domain,
        ["name", "partner_id", "invoice_date", "amount_total", "amount_residual",
         "state", "move_type", "company_id", "ref", "payment_state"],
        limit=500
    )

@st.cache_data(ttl=3600)
def get_balance_sheet_data(company_id=None, date=None):
    """Haal balanspositie op"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    # Activa (0*, 1*, 3* rekeningen)
    # Passiva (2*, 4* t/m 9* voor resultaat)
    
    domain = [
        ("parent_state", "=", "posted"),
        ("date", "<=", date)
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    result = odoo_read_group(
        "account.move.line",
        domain,
        ["balance:sum"],
        ["account_id"]
    )
    return result

# =============================================================================
# DISPLAY HELPERS
# =============================================================================

def format_currency(amount):
    """Format bedrag als EUR"""
    if amount is None:
        return "€0"
    return f"€{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_company_name(company_id):
    """Haal bedrijfsnaam op"""
    if company_id in COMPANIES:
        return COMPANIES[company_id]["short"]
    return f"Company {company_id}"

# =============================================================================
# TABS
# =============================================================================

def render_overview_tab(year, company_filter):
    """Render het overzichtstab"""
    st.header("📊 Financieel Overzicht")
    
    company_id = None if company_filter == "Alle entiteiten" else [k for k, v in COMPANIES.items() if v["name"] == company_filter][0]
    
    # Haal data op
    with st.spinner("Data ophalen..."):
        revenue_data = get_revenue_aggregated(year, company_id)
        cost_data = get_cost_aggregated(year, company_id)
        receivables, payables = get_receivables_payables(company_id)
    
    # Bereken totalen
    total_revenue = -sum(r.get("balance", 0) for r in revenue_data)  # Omzet is negatief in Odoo
    total_costs = sum(c.get("balance", 0) for c in cost_data)
    total_profit = total_revenue - total_costs
    total_receivables = sum(r.get("amount_residual", 0) for r in receivables)
    total_payables = sum(abs(p.get("amount_residual", 0)) for p in payables)
    
    # KPI cards
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("💰 Omzet YTD", format_currency(total_revenue))
    with col2:
        st.metric("📉 Kosten YTD", format_currency(total_costs))
    with col3:
        delta_color = "normal" if total_profit >= 0 else "inverse"
        st.metric("📈 Resultaat YTD", format_currency(total_profit), 
                  delta=f"{(total_profit/total_revenue*100):.1f}% marge" if total_revenue > 0 else None)
    with col4:
        st.metric("📥 Debiteuren", format_currency(total_receivables))
    with col5:
        st.metric("📤 Crediteuren", format_currency(total_payables))
    
    st.divider()
    
    # Maandelijkse omzet grafiek
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Maandelijkse Omzet")
        if revenue_data:
            df_rev = pd.DataFrame(revenue_data)
            df_rev["omzet"] = -df_rev["balance"]  # Converteer naar positief
            df_rev = df_rev.sort_values("date:month")
            
            fig = px.bar(df_rev, x="date:month", y="omzet",
                        labels={"date:month": "Maand", "omzet": "Omzet (€)"},
                        color_discrete_sequence=["#1f77b4"])
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Geen omzetdata beschikbaar")
    
    with col2:
        st.subheader("Maandelijkse Kosten")
        if cost_data:
            df_cost = pd.DataFrame(cost_data)
            df_cost = df_cost.sort_values("date:month")
            
            fig = px.bar(df_cost, x="date:month", y="balance",
                        labels={"date:month": "Maand", "balance": "Kosten (€)"},
                        color_discrete_sequence=["#d62728"])
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Geen kostendata beschikbaar")

def render_intercompany_tab(year):
    """Render intercompany analyse tab"""
    st.header("🔄 Intercompany Posities")
    
    with st.spinner("IC data ophalen..."):
        ic_balances = get_intercompany_balances()
    
    if not ic_balances:
        st.warning("Geen intercompany data gevonden")
        return
    
    # Toon IC posities per bedrijf
    st.subheader("R/C Posities per Entiteit")
    
    # Maak een overzichtstabel
    ic_data = []
    for item in ic_balances:
        account = item.get("account_id", [None, "Onbekend"])
        company = item.get("company_id", [None, "Onbekend"])
        ic_data.append({
            "Entiteit": get_company_name(company[0]) if company else "Onbekend",
            "Rekening": account[1] if account else "Onbekend",
            "Saldo": item.get("balance", 0),
            "Debet": item.get("debit", 0),
            "Credit": item.get("credit", 0)
        })
    
    df_ic = pd.DataFrame(ic_data)
    
    # Format als valuta
    for col in ["Saldo", "Debet", "Credit"]:
        df_ic[col] = df_ic[col].apply(format_currency)
    
    st.dataframe(df_ic, use_container_width=True)
    
    # Waarschuwing als posities niet aansluiten
    st.divider()
    st.subheader("⚠️ Reconciliatie Check")
    
    # Groepeer per rekening type
    totals_by_account = {}
    for item in ic_balances:
        account = item.get("account_id", [None, ""])[1] if item.get("account_id") else ""
        if "126" in str(account):
            if account not in totals_by_account:
                totals_by_account[account] = 0
            totals_by_account[account] += item.get("balance", 0)
    
    # Check totalen
    total_ic = sum(totals_by_account.values())
    if abs(total_ic) > 0.01:
        st.error(f"❌ **IC posities sluiten niet aan!** Verschil: {format_currency(total_ic)}")
        st.info("De R/C posities tussen de entiteiten moeten optellen tot €0. Controleer de boekingen.")
    else:
        st.success("✅ IC posities sluiten aan")

def render_vat_tab(year, company_filter):
    """Render BTW analyse tab"""
    st.header("🧾 BTW Analyse")
    
    company_id = None if company_filter == "Alle entiteiten" else [k for k, v in COMPANIES.items() if v["name"] == company_filter][0]
    
    with st.spinner("BTW data ophalen..."):
        vat_data = get_vat_balances(year, company_id)
        be_vat = get_belgian_vat_transactions(year)
    
    # BTW overzicht
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("BTW Saldi per Rekening")
        if vat_data:
            vat_records = []
            for item in vat_data:
                account = item.get("account_id", [None, "Onbekend"])
                company = item.get("company_id", [None, "Onbekend"])
                vat_records.append({
                    "Entiteit": get_company_name(company[0]) if company else "Onbekend",
                    "Rekening": account[1] if account else "Onbekend",
                    "Saldo": item.get("balance", 0)
                })
            
            df_vat = pd.DataFrame(vat_records)
            df_vat["Saldo_fmt"] = df_vat["Saldo"].apply(format_currency)
            st.dataframe(df_vat[["Entiteit", "Rekening", "Saldo_fmt"]], use_container_width=True)
        else:
            st.info("Geen BTW data beschikbaar")
    
    with col2:
        st.subheader("🇧🇪 Belgische BTW Risico")
        if be_vat:
            total_be_vat = sum(abs(t.get("balance", 0)) for t in be_vat)
            st.error(f"""
            **⚠️ KRITIEK BTW RISICO**
            
            Er zijn **{len(be_vat)} transacties** met Belgisch BTW-tarief gevonden.
            
            Totaal bedrag: **{format_currency(total_be_vat)}**
            
            **Risico:** Belgische BTW kan mogelijk niet als voorbelasting worden afgetrokken in Nederland 
            tenzij er een actieve BTW-registratie in België is.
            
            **Actie vereist:** Controleer of Pure & Original International B.V. een Belgische BTW-registratie heeft.
            """)
            
            # Toon details
            with st.expander("Bekijk Belgische BTW transacties"):
                be_records = []
                for t in be_vat[:50]:  # Max 50 tonen
                    be_records.append({
                        "Datum": t.get("date", ""),
                        "Omschrijving": t.get("name", ""),
                        "Bedrag": format_currency(abs(t.get("balance", 0))),
                        "Partner": t.get("partner_id", [None, ""])[1] if t.get("partner_id") else ""
                    })
                st.dataframe(pd.DataFrame(be_records), use_container_width=True)
        else:
            st.success("✅ Geen Belgische BTW transacties gevonden")
    
    st.divider()
    
    # BTW-risico samenvatting
    st.subheader("📋 BTW Aandachtspunten")
    
    risks = []
    
    # Check voorbelasting buitenland
    for item in vat_data:
        account_name = item.get("account_id", [None, ""])[1] if item.get("account_id") else ""
        if "verlegd" in account_name.lower() or "EU" in account_name:
            risks.append({
                "Type": "🟡 Aandacht",
                "Onderwerp": "BTW Verlegging EU",
                "Details": f"Actieve rekening: {account_name}",
                "Actie": "Controleer ICP-opgave"
            })
        if "import" in account_name.lower() or "buiten" in account_name.lower():
            risks.append({
                "Type": "🟡 Aandacht", 
                "Onderwerp": "Import BTW",
                "Details": f"Actieve rekening: {account_name}",
                "Actie": "Controleer artikel 23 vergunning"
            })
    
    if be_vat:
        risks.insert(0, {
            "Type": "🔴 Kritiek",
            "Onderwerp": "Belgische BTW",
            "Details": f"{len(be_vat)} transacties met BE 21%",
            "Actie": "Verifieer BE BTW-registratie"
        })
    
    if risks:
        df_risks = pd.DataFrame(risks)
        st.dataframe(df_risks, use_container_width=True)
    else:
        st.success("Geen specifieke BTW-risico's geïdentificeerd")

def render_invoices_tab(year, company_filter):
    """Render facturen tab"""
    st.header("📄 Facturen")
    
    company_id = None if company_filter == "Alle entiteiten" else [k for k, v in COMPANIES.items() if v["name"] == company_filter][0]
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        invoice_type = st.selectbox("Type", ["Alle", "verkoop", "inkoop"])
    with col2:
        state = st.selectbox("Status", ["Alle", "posted", "draft"])
    with col3:
        payment_filter = st.selectbox("Betaalstatus", ["Alle", "Openstaand", "Betaald"])
    
    # Haal facturen op
    with st.spinner("Facturen ophalen..."):
        invoices = get_invoices(
            year, 
            company_id, 
            None if invoice_type == "Alle" else invoice_type,
            None if state == "Alle" else state
        )
    
    if not invoices:
        st.info("Geen facturen gevonden")
        return
    
    # Filter op betaalstatus
    if payment_filter == "Openstaand":
        invoices = [i for i in invoices if i.get("amount_residual", 0) != 0]
    elif payment_filter == "Betaald":
        invoices = [i for i in invoices if i.get("amount_residual", 0) == 0]
    
    # Maak tabel
    inv_data = []
    for inv in invoices:
        inv_data.append({
            "Nummer": inv.get("name", ""),
            "Partner": inv.get("partner_id", [None, ""])[1] if inv.get("partner_id") else "",
            "Datum": inv.get("invoice_date", ""),
            "Totaal": inv.get("amount_total", 0),
            "Openstaand": inv.get("amount_residual", 0),
            "Status": inv.get("payment_state", ""),
            "Entiteit": get_company_name(inv.get("company_id", [None])[0]) if inv.get("company_id") else "",
            "Type": "Verkoop" if inv.get("move_type", "").startswith("out") else "Inkoop"
        })
    
    df_inv = pd.DataFrame(inv_data)
    
    # Statistieken
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Aantal facturen", len(df_inv))
    with col2:
        st.metric("Totaal bedrag", format_currency(df_inv["Totaal"].sum()))
    with col3:
        st.metric("Openstaand", format_currency(df_inv["Openstaand"].sum()))
    with col4:
        st.metric("% Betaald", f"{(1 - df_inv['Openstaand'].sum() / max(df_inv['Totaal'].sum(), 1)) * 100:.1f}%")
    
    # Format bedragen
    df_inv["Totaal"] = df_inv["Totaal"].apply(format_currency)
    df_inv["Openstaand"] = df_inv["Openstaand"].apply(format_currency)
    
    st.dataframe(df_inv, use_container_width=True)

def render_bank_tab():
    """Render banksaldi tab"""
    st.header("🏦 Banksaldi")
    
    with st.spinner("Banksaldi ophalen..."):
        bank_data = get_bank_balances()
    
    if not bank_data:
        st.warning("Geen bankrekeningen gevonden")
        return
    
    # Groepeer per entiteit
    bank_by_company = {}
    total_balance = 0
    
    for bank in bank_data:
        company = bank.get("company_id", [None, "Onbekend"])
        company_name = get_company_name(company[0]) if company else "Onbekend"
        balance = bank.get("current_statement_balance", 0) or 0
        
        if company_name not in bank_by_company:
            bank_by_company[company_name] = []
        
        bank_by_company[company_name].append({
            "Rekening": bank.get("name", ""),
            "Saldo": balance
        })
        total_balance += balance
    
    # Totaal KPI
    st.metric("💰 Totaal Banksaldo", format_currency(total_balance))
    
    st.divider()
    
    # Per entiteit
    for company, accounts in bank_by_company.items():
        company_total = sum(a["Saldo"] for a in accounts)
        
        with st.expander(f"**{company}** - {format_currency(company_total)}", expanded=True):
            df = pd.DataFrame(accounts)
            df["Saldo"] = df["Saldo"].apply(format_currency)
            st.dataframe(df, use_container_width=True)

def render_cashflow_tab(year, company_filter):
    """Render cashflow prognose tab"""
    st.header("💹 Cashflow Prognose")
    
    company_id = None if company_filter == "Alle entiteiten" else [k for k, v in COMPANIES.items() if v["name"] == company_filter][0]
    
    with st.spinner("Data ophalen voor cashflow..."):
        bank_data = get_bank_balances()
        receivables, payables = get_receivables_payables(company_id)
    
    # Huidig banksaldo
    if company_id:
        current_balance = sum(
            b.get("current_statement_balance", 0) or 0 
            for b in bank_data 
            if b.get("company_id", [None])[0] == company_id
        )
    else:
        current_balance = sum(b.get("current_statement_balance", 0) or 0 for b in bank_data)
    
    # Groepeer receivables/payables per week
    today = datetime.now().date()
    weeks = []
    
    for i in range(12):  # 12 weken vooruit
        week_start = today + timedelta(weeks=i)
        week_end = week_start + timedelta(days=6)
        
        # Verwachte ontvangsten
        expected_in = sum(
            r.get("amount_residual", 0)
            for r in receivables
            if r.get("date_maturity") and week_start <= datetime.strptime(r["date_maturity"], "%Y-%m-%d").date() <= week_end
        )
        
        # Verwachte betalingen
        expected_out = sum(
            abs(p.get("amount_residual", 0))
            for p in payables
            if p.get("date_maturity") and week_start <= datetime.strptime(p["date_maturity"], "%Y-%m-%d").date() <= week_end
        )
        
        weeks.append({
            "Week": f"Week {i+1}",
            "Start": week_start.strftime("%d-%m"),
            "Ontvangsten": expected_in,
            "Betalingen": expected_out,
            "Netto": expected_in - expected_out
        })
    
    # Bereken cumulatief saldo
    running_balance = current_balance
    for w in weeks:
        running_balance += w["Netto"]
        w["Saldo"] = running_balance
    
    df_cf = pd.DataFrame(weeks)
    
    # KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Huidig saldo", format_currency(current_balance))
    with col2:
        st.metric("Verwachte ontvangsten", format_currency(df_cf["Ontvangsten"].sum()))
    with col3:
        st.metric("Verwachte betalingen", format_currency(df_cf["Betalingen"].sum()))
    with col4:
        min_balance = df_cf["Saldo"].min()
        st.metric("Laagste saldo", format_currency(min_balance), 
                  delta="⚠️ Negatief!" if min_balance < 0 else None)
    
    st.divider()
    
    # Grafiek
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Ontvangsten", x=df_cf["Week"], y=df_cf["Ontvangsten"], marker_color="green"))
    fig.add_trace(go.Bar(name="Betalingen", x=df_cf["Week"], y=-df_cf["Betalingen"], marker_color="red"))
    fig.add_trace(go.Scatter(name="Saldo", x=df_cf["Week"], y=df_cf["Saldo"], mode="lines+markers", line=dict(color="blue", width=3)))
    
    fig.update_layout(
        title="12-Weeks Cashflow Prognose",
        barmode="relative",
        yaxis_title="Bedrag (€)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02)
    )
    st.plotly_chart(fig, use_container_width=True)
    
    # Detail tabel
    with st.expander("📋 Wekelijks detail"):
        df_display = df_cf.copy()
        for col in ["Ontvangsten", "Betalingen", "Netto", "Saldo"]:
            df_display[col] = df_display[col].apply(format_currency)
        st.dataframe(df_display, use_container_width=True)

# =============================================================================
# MAIN APP
# =============================================================================

def main():
    # Sidebar
    st.sidebar.image("https://pure-original.com/wp-content/uploads/2021/03/PO_logo_black.png", width=200)
    st.sidebar.title("Pure & Original")
    st.sidebar.caption("CFO Dashboard")
    
    # API Key input
    if not get_api_key():
        st.sidebar.divider()
        api_key = st.sidebar.text_input("🔑 Odoo API Key", type="password")
        if api_key:
            st.session_state["api_key"] = api_key
            st.rerun()
        else:
            st.warning("⚠️ Voer je Odoo API key in de sidebar in om te beginnen")
            st.stop()
    
    # Jaar selectie
    current_year = datetime.now().year
    year = st.sidebar.selectbox("📅 Jaar", [current_year, current_year - 1, current_year - 2], index=0)
    
    # Entiteit filter
    company_options = ["Alle entiteiten"] + [v["name"] for v in COMPANIES.values()]
    company_filter = st.sidebar.selectbox("🏢 Entiteit", company_options)
    
    st.sidebar.divider()
    
    # Refresh button
    if st.sidebar.button("🔄 Data vernieuwen"):
        st.cache_data.clear()
        st.rerun()
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overzicht", 
        "🔄 Intercompany", 
        "🧾 BTW Analyse",
        "📄 Facturen",
        "🏦 Bank",
        "💹 Cashflow"
    ])
    
    with tab1:
        render_overview_tab(year, company_filter)
    
    with tab2:
        render_intercompany_tab(year)
    
    with tab3:
        render_vat_tab(year, company_filter)
    
    with tab4:
        render_invoices_tab(year, company_filter)
    
    with tab5:
        render_bank_tab()
    
    with tab6:
        render_cashflow_tab(year, company_filter)
    
    # Footer
    st.sidebar.divider()
    st.sidebar.caption(f"Dashboard v1.0 | {datetime.now().strftime('%d-%m-%Y %H:%M')}")

if __name__ == "__main__":
    main()
