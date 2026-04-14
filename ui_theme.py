def load_modern_theme():
    return """
    <style>
    body {background-color:#0b0b0f;color:#fff}
    .stApp {background: radial-gradient(circle at top,#1a1a2e,#0b0b0f)}

    .block-container {
        padding:2rem;
        border-radius:16px;
        background:rgba(15,15,25,0.9);
        box-shadow:0 0 40px rgba(255,0,0,0.15);
    }

    .stButton>button {
        background:linear-gradient(90deg,#ff1e1e,#ff4d4d);
        color:white;
        border:none;
        border-radius:8px;
        font-weight:600;
    }

    .stDataFrame {
        border-radius:10px;
        overflow:hidden;
    }

    h1,h2,h3,h4 {color:#ff4d4d}
    </style>
    """
