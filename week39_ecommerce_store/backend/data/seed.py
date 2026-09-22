import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.db import get_db, init_db  # noqa: E402

CATEGORIES = [
    {
        "slug": "keyboards",
        "name": "Mechanical Keyboards",
        "description": (
            "Custom mechanical keyboards, hot-swap boards, and artisan kits."
        ),
    },
    {
        "slug": "audio",
        "name": "Studio Audio",
        "description": (
            "DACs, studio monitors, open-back headphones, and microphones."
        ),
    },
    {
        "slug": "accessories",
        "name": "Desk Accessories",
        "description": ("Ergonomic monitor arms, wool felt desk mats, and organizers."),
    },
    {
        "slug": "apparel",
        "name": "Developer Apparel",
        "description": ("Heavyweight hoodies, minimal caps, and premium cotton tees."),
    },
]

PRODUCTS = [
    {
        "sku": "KB-VORTEX-68",
        "title": "Vortex 68 Wireless Keyboard",
        "slug": "vortex-68-wireless-keyboard",
        "description": (
            "Compact 65% mechanical keyboard with hot-swappable switches "
            "and 2.4GHz wireless."
        ),
        "price_cents": 12900,
        "stock_quantity": 25,
        "category_slug": "keyboards",
        "image_url": "/assets/images/vortex-68.jpg",
        "is_active": 1,
    },
    {
        "sku": "KB-APEX-87",
        "title": "Apex TKL Aluminum Keyboard",
        "slug": "apex-tkl-aluminum-keyboard",
        "description": (
            "CNC aluminum chassis, gasket-mounted plate, and pre-lubed "
            "linear switches."
        ),
        "price_cents": 17900,
        "stock_quantity": 14,
        "category_slug": "keyboards",
        "image_url": "/assets/images/apex-tkl.jpg",
        "is_active": 1,
    },
    {
        "sku": "KB-ERGO-SPLIT",
        "title": "ErgoSplit Low-Profile Keyboard",
        "slug": "ergosplit-low-profile-keyboard",
        "description": (
            "Split ergonomic layout with column-staggered keys and " "choc v2 switches."
        ),
        "price_cents": 21900,
        "stock_quantity": 9,
        "category_slug": "keyboards",
        "image_url": "/assets/images/ergosplit.jpg",
        "is_active": 1,
    },
    {
        "sku": "AUD-MONITOR-X",
        "title": "Reference X Studio Monitors",
        "slug": "reference-x-studio-monitors",
        "description": (
            "Bi-amplified 5-inch active studio monitors for flat " "acoustic precision."
        ),
        "price_cents": 29900,
        "stock_quantity": 8,
        "category_slug": "audio",
        "image_url": "/assets/images/reference-x.jpg",
        "is_active": 1,
    },
    {
        "sku": "AUD-DAC-AMP",
        "title": "SonicStream USB-C DAC & Amp",
        "slug": "sonicstream-usbc-dac-amp",
        "description": (
            "High-res 32-bit/384kHz desktop DAC and headphone amplifier "
            "with balanced output."
        ),
        "price_cents": 8900,
        "stock_quantity": 30,
        "category_slug": "audio",
        "image_url": "/assets/images/sonicstream.jpg",
        "is_active": 1,
    },
    {
        "sku": "AUD-MIC-POD",
        "title": "Broadcast Pro USB Microphone",
        "slug": "broadcast-pro-usb-microphone",
        "description": (
            "Cardioid condenser microphone with internal shock mount "
            "and zero-latency monitoring."
        ),
        "price_cents": 14900,
        "stock_quantity": 18,
        "category_slug": "audio",
        "image_url": "/assets/images/broadcast-pro.jpg",
        "is_active": 1,
    },
    {
        "sku": "ACC-DESK-PAD",
        "title": "Merino Wool Desk Mat (XL)",
        "slug": "merino-wool-desk-mat-xl",
        "description": (
            "Premium 900x400mm high-density natural wool felt desk pad "
            "with non-slip cork base."
        ),
        "price_cents": 4900,
        "stock_quantity": 40,
        "category_slug": "accessories",
        "image_url": "/assets/images/wool-mat.jpg",
        "is_active": 1,
    },
    {
        "sku": "ACC-LIGHT-BAR",
        "title": "Precision Monitor Light Bar",
        "slug": "precision-monitor-light-bar",
        "description": (
            "Asymmetric optical design screen bar with wireless rotary "
            "dial controller."
        ),
        "price_cents": 6900,
        "stock_quantity": 22,
        "category_slug": "accessories",
        "image_url": "/assets/images/light-bar.jpg",
        "is_active": 1,
    },
    {
        "sku": "ACC-STAND-WALNUT",
        "title": "Solid Walnut Dual Monitor Stand",
        "slug": "solid-walnut-dual-monitor-stand",
        "description": (
            "Handcrafted American walnut riser with powder-coated " "aluminum legs."
        ),
        "price_cents": 11900,
        "stock_quantity": 12,
        "category_slug": "accessories",
        "image_url": "/assets/images/walnut-stand.jpg",
        "is_active": 1,
    },
    {
        "sku": "APP-HOODIE-DEV",
        "title": "Syntax Heavyweight Cotton Hoodie",
        "slug": "syntax-heavyweight-cotton-hoodie",
        "description": (
            "450 GSM French terry cotton hoodie with subtle monospaced "
            "chest embroidery."
        ),
        "price_cents": 7500,
        "stock_quantity": 35,
        "category_slug": "apparel",
        "image_url": "/assets/images/syntax-hoodie.jpg",
        "is_active": 1,
    },
    {
        "sku": "APP-TEE-TERMINAL",
        "title": "Null Pointer Organic Cotton Tee",
        "slug": "null-pointer-organic-cotton-tee",
        "description": (
            "Relaxed fit 220 GSM combed organic cotton t-shirt with "
            "screen-printed graphic."
        ),
        "price_cents": 3400,
        "stock_quantity": 50,
        "category_slug": "apparel",
        "image_url": "/assets/images/null-pointer-tee.jpg",
        "is_active": 1,
    },
    {
        "sku": "APP-CAP-VIM",
        "title": ":wq Low-Profile Embroidered Cap",
        "slug": "wq-low-profile-embroidered-cap",
        "description": (
            "Unstructured 6-panel washed cotton twill cap with brass " "buckle strap."
        ),
        "price_cents": 2800,
        "stock_quantity": 20,
        "category_slug": "apparel",
        "image_url": "/assets/images/vim-cap.jpg",
        "is_active": 1,
    },
]


def seed_database(db_path=None):
    if db_path is None:
        from app.config.settings import get_config

        db_path = get_config().DATABASE_PATH

    init_db(db_path=db_path)
    conn = get_db(db_path=db_path)
    cur = conn.cursor()

    for cat in CATEGORIES:
        cur.execute(
            """
            INSERT INTO categories (slug, name, description)
            VALUES (?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                name=excluded.name,
                description=excluded.description
            """,
            (cat["slug"], cat["name"], cat["description"]),
        )

    for prod in PRODUCTS:
        cur.execute(
            """
            INSERT INTO products (
                sku, title, slug, description, price_cents,
                stock_quantity, category_slug, image_url, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(sku) DO UPDATE SET
                title=excluded.title,
                slug=excluded.slug,
                description=excluded.description,
                price_cents=excluded.price_cents,
                stock_quantity=excluded.stock_quantity,
                category_slug=excluded.category_slug,
                image_url=excluded.image_url,
                is_active=excluded.is_active
            """,
            (
                prod["sku"],
                prod["title"],
                prod["slug"],
                prod["description"],
                prod["price_cents"],
                prod["stock_quantity"],
                prod["category_slug"],
                prod["image_url"],
                prod["is_active"],
            ),
        )

    conn.commit()
    conn.close()
    return {"categories": len(CATEGORIES), "products": len(PRODUCTS)}


if __name__ == "__main__":
    result = seed_database()
    print(
        f"Seeded {result['categories']} categories and "
        f"{result['products']} products."
    )
