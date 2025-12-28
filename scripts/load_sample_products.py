#!/usr/bin/env python3
"""
Load sample products into the database with embeddings.

Usage:
    # Set DATABASE_URL and GOOGLE_API_KEY environment variables
    python scripts/load_sample_products.py

This script:
1. Connects to the database
2. Generates embeddings for each product using Gemini
3. Inserts products with embeddings into the products table
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg

# Sample products for testing
SAMPLE_PRODUCTS = [
    {
        "sku": "COMP-0001",
        "name": "Gaming Laptop Pro",
        "description": "High-performance gaming laptop with RTX 4080 graphics, 32GB RAM, 1TB SSD. Perfect for gaming and content creation.",
        "category": "Computing",
        "brand": "TechPro",
        "tags": ["gaming", "laptop", "high-performance"],
        "color": "Black",
        "size": "15.6 inch",
        "price": 1999.99,
    },
    {
        "sku": "COMP-0002",
        "name": "Mechanical Keyboard RGB",
        "description": "Mechanical gaming keyboard with Cherry MX switches, RGB backlight, programmable keys.",
        "category": "Computing",
        "brand": "KeyMaster",
        "tags": ["keyboard", "mechanical", "gaming", "rgb"],
        "color": "Black",
        "size": "Full Size",
        "price": 149.99,
    },
    {
        "sku": "COMP-0003",
        "name": "Wireless Mouse Ergonomic",
        "description": "Ergonomic wireless mouse with 6 programmable buttons, adjustable DPI up to 16000.",
        "category": "Computing",
        "brand": "ErgoTech",
        "tags": ["mouse", "wireless", "ergonomic"],
        "color": "Gray",
        "size": "Standard",
        "price": 79.99,
    },
    {
        "sku": "HOME-0001",
        "name": "Robot Vacuum Cleaner",
        "description": "Smart robot vacuum with automatic cleaning, app control, HEPA filter. Cleans your house automatically.",
        "category": "Home",
        "brand": "CleanBot",
        "tags": ["vacuum", "robot", "smart-home", "automatic"],
        "color": "White",
        "size": "Compact",
        "price": 399.99,
    },
    {
        "sku": "HOME-0002",
        "name": "Smart LED Light Bulb",
        "description": "WiFi smart light bulb with 16 million colors, voice control compatible with Alexa and Google Home.",
        "category": "Home",
        "brand": "LumiSmart",
        "tags": ["lighting", "smart-home", "led", "wifi"],
        "color": "White",
        "size": "E26",
        "price": 24.99,
    },
    {
        "sku": "HOME-0003",
        "name": "Air Purifier HEPA",
        "description": "Air purifier with true HEPA filter, removes 99.97% of particles. Perfect for allergies and clean air.",
        "category": "Home",
        "brand": "PureAir",
        "tags": ["air-purifier", "hepa", "health"],
        "color": "White",
        "size": "Medium Room",
        "price": 199.99,
    },
    {
        "sku": "AUDIO-0001",
        "name": "Wireless Headphones Noise Cancelling",
        "description": "Premium wireless headphones with active noise cancellation, 30-hour battery, comfortable for long sessions.",
        "category": "Audio",
        "brand": "SoundMax",
        "tags": ["headphones", "wireless", "noise-cancelling"],
        "color": "Black",
        "size": "Over-ear",
        "price": 299.99,
    },
    {
        "sku": "AUDIO-0002",
        "name": "Bluetooth Speaker Portable",
        "description": "Waterproof portable Bluetooth speaker with 20-hour battery, deep bass, perfect for outdoors.",
        "category": "Audio",
        "brand": "BassBoost",
        "tags": ["speaker", "bluetooth", "portable", "waterproof"],
        "color": "Blue",
        "size": "Portable",
        "price": 89.99,
    },
    {
        "sku": "OFFICE-0001",
        "name": "Ergonomic Office Chair",
        "description": "Adjustable ergonomic office chair with lumbar support, mesh back, armrests. Work from home professionally.",
        "category": "Office",
        "brand": "ComfortWork",
        "tags": ["chair", "ergonomic", "office", "work-from-home"],
        "color": "Black",
        "size": "Standard",
        "price": 349.99,
    },
    {
        "sku": "OFFICE-0002",
        "name": "Standing Desk Electric",
        "description": "Electric height-adjustable standing desk with memory presets, cable management, spacious surface.",
        "category": "Office",
        "brand": "DeskPro",
        "tags": ["desk", "standing", "electric", "adjustable"],
        "color": "Walnut",
        "size": "60 inch",
        "price": 549.99,
    },
    {
        "sku": "SPORTS-0001",
        "name": "Fitness Tracker Watch",
        "description": "Smart fitness tracker with heart rate monitor, sleep tracking, GPS, water resistant. Track your health.",
        "category": "Sports",
        "brand": "FitLife",
        "tags": ["fitness", "watch", "tracker", "health"],
        "color": "Black",
        "size": "One Size",
        "price": 129.99,
    },
    {
        "sku": "SPORTS-0002",
        "name": "Yoga Mat Premium",
        "description": "Non-slip yoga mat with alignment lines, extra thick cushioning, eco-friendly materials. Exercise at home.",
        "category": "Sports",
        "brand": "ZenFit",
        "tags": ["yoga", "mat", "exercise", "fitness"],
        "color": "Purple",
        "size": "72 x 24 inch",
        "price": 49.99,
    },
    {
        "sku": "KITCHEN-0001",
        "name": "Non-Stick Pan Set",
        "description": "Professional non-stick pan set with ceramic coating, oven safe, dishwasher safe. Cook like a chef.",
        "category": "Kitchen",
        "brand": "ChefPro",
        "tags": ["pan", "cookware", "non-stick", "kitchen"],
        "color": "Gray",
        "size": "3-Piece Set",
        "price": 89.99,
    },
    {
        "sku": "KITCHEN-0002",
        "name": "Coffee Maker Automatic",
        "description": "Automatic drip coffee maker with programmable timer, 12-cup capacity, keep warm function.",
        "category": "Kitchen",
        "brand": "BrewMaster",
        "tags": ["coffee", "maker", "automatic", "kitchen"],
        "color": "Stainless Steel",
        "size": "12 Cup",
        "price": 79.99,
    },
    {
        "sku": "PHONE-0001",
        "name": "Phone Case Protective",
        "description": "Heavy-duty protective phone case with drop protection, slim design. Protect your phone from drops.",
        "category": "Accessories",
        "brand": "ArmorCase",
        "tags": ["phone", "case", "protective", "accessories"],
        "color": "Clear",
        "size": "Universal",
        "price": 29.99,
    },
]


async def generate_embedding(text: str) -> list[float]:
    """Generate embedding using Gemini API."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set")

    client = genai.Client(api_key=api_key)
    resp = client.models.embed_content(
        model="gemini-embedding-001",
        contents=[text],
        config=types.EmbedContentConfig(output_dimensionality=1536),
    )

    if resp.embeddings and resp.embeddings[0].values:
        return list(resp.embeddings[0].values)
    return []


async def load_products():
    """Load sample products into the database."""
    from pgvector.asyncpg import register_vector

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    print("Connecting to database...")
    conn = await asyncpg.connect(database_url)
    await register_vector(conn)  # Register pgvector type
    print("Connected!")

    print(f"\nLoading {len(SAMPLE_PRODUCTS)} products...\n")

    for i, product in enumerate(SAMPLE_PRODUCTS, 1):
        try:
            # Generate embedding from name + description
            embed_text = f"{product['name']} {product['description']}"
            print(f"[{i}/{len(SAMPLE_PRODUCTS)}] {product['sku']}: Generating embedding...")
            embedding = await generate_embedding(embed_text)

            if not embedding:
                print(f"  ⚠ No embedding generated, skipping")
                continue

            # Convert to numpy array for pgvector
            import numpy as np
            embedding_array = np.array(embedding, dtype=np.float32)

            # Insert product
            await conn.execute(
                """
                INSERT INTO test.products (sku, name, description, category, brand, tags, color, size, price, embedding)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (sku) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    brand = EXCLUDED.brand,
                    tags = EXCLUDED.tags,
                    color = EXCLUDED.color,
                    size = EXCLUDED.size,
                    price = EXCLUDED.price,
                    embedding = EXCLUDED.embedding,
                    updated_at = NOW()
                """,
                product["sku"],
                product["name"],
                product["description"],
                product["category"],
                product["brand"],
                product["tags"],
                product["color"],
                product["size"],
                product["price"],
                embedding_array,
            )
            print(f"  ✓ {product['name']}")

        except Exception as e:
            print(f"  ✗ Error: {e}")

    # Verify count
    count = await conn.fetchval("SELECT COUNT(*) FROM test.products")
    print(f"\n✅ Loaded {count} products into test.products")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(load_products())
