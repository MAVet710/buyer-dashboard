from ui_branding import BACKGROUND_URL


def load_professional_theme():
    return f"""
    <style>

    .stApp {{
        background-image: url('{BACKGROUND_URL}');
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    .main-container {{
        background: rgba(0,0,0,0.75);
        border-radius: 16px;
        padding: 2rem;
    }}

    .brand-hero {{
        text-align: center;
        margin-bottom: 2rem;
    }}

    .brand-title {{
        font-size: 2.2rem;
        font-weight: 700;
        color: white;
    }}

    .brand-subtitle {{
        font-size: 1rem;
        opacity: 0.8;
        color: white;
    }}

    .login-card {{
        max-width: 420px;
        margin: 6rem auto;
        padding: 2rem;
        background: rgba(0,0,0,0.85);
        border-radius: 14px;
        text-align: center;
        box-shadow: 0 0 40px rgba(0,0,0,0.5);
    }}

    .login-title {{
        font-size: 1.5rem;
        font-weight: 600;
        margin-bottom: 1rem;
        color: white;
    }}

    .stTextInput > div > div > input {{
        text-align: center;
    }}

    </style>
    """
