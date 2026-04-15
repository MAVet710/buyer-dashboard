def load_professional_theme():
    return '''
    <style>
    .login-shell {
        min-height: 100vh;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    .login-card {
        max-width: 430px;
        padding: 2rem;
        border-radius: 18px;
        background: rgba(14,14,14,0.80);
        border: 1px solid rgba(255,255,255,0.08);
        backdrop-filter: blur(16px);
        box-shadow: 0 20px 70px rgba(0,0,0,0.45);
        text-align: center;
    }
    .login-title {
        font-size: 1.8rem;
        font-weight: 700;
        color: #fff;
    }
    .login-sub {
        font-size: 0.9rem;
        color: rgba(255,255,255,0.6);
        margin-bottom: 1rem;
    }
    </style>
    '''
