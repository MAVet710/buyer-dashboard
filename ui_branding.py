BRAND_NAME = "MAVet710"
APP_TITLE = "DoobieLogic Platform"
APP_SUBTITLE = "Commercial-ready cannabis intelligence system"
LICENSE_FOOTER = "Semper Paratus • Powered by Good Weed and Data"

# Shared DoobieLogic master image used by legacy Streamlit branding surfaces.
PRIMARY_BRAND_IMAGE_URL = "https://raw.githubusercontent.com/MAVet710/buyer-dashboard/main/frontend/public/doobielogic-logo.webp"
FAVICON_URL = PRIMARY_BRAND_IMAGE_URL
BACKGROUND_URL = PRIMARY_BRAND_IMAGE_URL


def brand_header_html() -> str:
    return f"""
    <div class='brand-hero'>
        <div class='brand-hero-inner'>
            <div class='brand-kicker'>{BRAND_NAME}</div>
            <div class='brand-title'>{APP_TITLE}</div>
            <div class='brand-subtitle'>{APP_SUBTITLE}</div>
        </div>
    </div>
    """
