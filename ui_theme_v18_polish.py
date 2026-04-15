from ui_branding import BACKGROUND_URL


def load_v18_polished_theme():
    return f'''
    <style>
    .stApp {{
        background:
            linear-gradient(rgba(18, 16, 14, 0.78), rgba(10, 10, 10, 0.88)),
            url('{BACKGROUND_URL}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    [data-testid="stHeader"] {{
        background: rgba(0,0,0,0);
    }}

    [data-testid="stSidebar"] {{
        display: none;
    }}

    .block-container {{
        padding-top: 1.1rem;
        padding-bottom: 1.5rem;
        max-width: 1420px;
    }}

    .top-shell {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 1rem;
        margin-bottom: 1rem;
        padding: 0.25rem 0 0.5rem 0;
    }}

    .hero-card {{
        flex: 1;
        border-radius: 22px;
        padding: 1.15rem 1.25rem;
        background: linear-gradient(135deg, rgba(255,255,255,0.10), rgba(255,255,255,0.04));
        border: 1px solid rgba(255,255,255,0.10);
        backdrop-filter: blur(18px);
        box-shadow: 0 18px 50px rgba(0,0,0,0.30);
    }}

    .hero-kicker {{
        color: #ff9a3c;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.75rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }}

    .hero-title {{
        color: #ffffff;
        font-size: 2rem;
        font-weight: 800;
        line-height: 1.05;
        margin-bottom: 0.3rem;
    }}

    .hero-subtitle {{
        color: rgba(255,255,255,0.76);
        font-size: 0.95rem;
    }}

    .nav-card {{
        width: 320px;
        border-radius: 22px;
        padding: 0.95rem 1rem;
        background: linear-gradient(135deg, rgba(255,154,60,0.18), rgba(255,255,255,0.06));
        border: 1px solid rgba(255,154,60,0.28);
        backdrop-filter: blur(18px);
        box-shadow: 0 18px 50px rgba(0,0,0,0.30);
    }}

    .nav-label {{
        color: rgba(255,255,255,0.72);
        font-size: 0.76rem;
        text-transform: uppercase;
        letter-spacing: 0.16em;
        margin-bottom: 0.35rem;
        font-weight: 700;
    }}

    div[data-baseweb="select"] > div,
    div[data-baseweb="select"] input,
    .stSelectbox label,
    .stTextInput label,
    .stMultiSelect label {{
        color: white !important;
    }}

    .stSelectbox > div > div,
    .stMultiSelect > div > div,
    .stTextInput > div > div > input {{
        background: rgba(16,16,16,0.72) !important;
        border: 1px solid rgba(255,154,60,0.22) !important;
        border-radius: 12px !important;
        color: white !important;
    }}

    .stTabs [data-baseweb="tab-list"] {{
        gap: 0.35rem;
    }}

    .stTabs [data-baseweb="tab"] {{
        border-radius: 12px 12px 0 0;
        background: rgba(255,255,255,0.05);
        color: rgba(255,255,255,0.8);
        padding: 0.55rem 0.9rem;
    }}

    .stTabs [aria-selected="true"] {{
        background: rgba(255,154,60,0.18) !important;
        color: white !important;
    }}

    div[data-testid="stMetric"] {{
        background: rgba(14,14,14,0.72);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 18px;
        padding: 0.8rem 0.95rem;
        backdrop-filter: blur(14px);
        box-shadow: 0 12px 40px rgba(0,0,0,0.24);
    }}

    div[data-testid="stDataFrame"], div[data-testid="stTable"] {{
        background: rgba(14,14,14,0.58);
        border-radius: 18px;
        border: 1px solid rgba(255,255,255,0.06);
        padding: 0.25rem;
    }}

    .login-shell {{
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
    }}

    .login-card {{
        max-width: 430px;
        padding: 2rem;
        border-radius: 20px;
        background: rgba(14,14,14,0.82);
        border: 1px solid rgba(255,154,60,0.22);
        backdrop-filter: blur(16px);
        box-shadow: 0 20px 70px rgba(0,0,0,0.45);
        text-align: center;
    }}

    .login-title {{
        font-size: 1.8rem;
        font-weight: 800;
        color: #fff;
    }}

    .login-sub {{
        font-size: 0.9rem;
        color: rgba(255,255,255,0.62);
        margin-bottom: 1rem;
    }}

    .stButton > button {{
        border-radius: 12px !important;
        border: 1px solid rgba(255,154,60,0.25) !important;
    }}
    </style>
    '''
