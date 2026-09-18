"""
WhatsApp Product Catalog Manager

Programmatically create and manage WhatsApp Product Catalog for policy carousel messages.
Uses Meta Graph API to create catalog, products, and manage inventory.

Requirements:
  - WHATSAPP_TOKEN with catalog_management permission
  - FACEBOOK_BUSINESS_ID (Meta Business Manager ID)
"""
import os
import httpx
import logging
from typing import List, Dict, Optional

logger = logging.getLogger("whatsapp.catalog")

_GRAPH_URL = "https://graph.facebook.com/v19.0"
_WA_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
_BUSINESS_ID = os.environ.get("FACEBOOK_BUSINESS_ID", "")


async def create_catalog(name: str = "Travel Insurance Plans") -> Optional[str]:
    """
    Create a new WhatsApp Product Catalog.
    
    Args:
        name: Catalog name (default: "Travel Insurance Plans")
    
    Returns:
        str: Catalog ID if successful, None otherwise
    """
    if not _BUSINESS_ID or not _WA_TOKEN:
        logger.error("[catalog] FACEBOOK_BUSINESS_ID or WHATSAPP_TOKEN not set")
        return None
    
    url = f"{_GRAPH_URL}/{_BUSINESS_ID}/owned_product_catalogs"
    headers = {
        "Authorization": f"Bearer {_WA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "name": name,
        "vertical": "commerce"  # commerce vertical for WhatsApp Business
    }
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code in (200, 201):
                result = response.json()
                catalog_id = result.get("id")
                logger.info(f"[catalog] Created catalog: {catalog_id}")
                return catalog_id
            else:
                logger.error(f"[catalog] Failed to create catalog: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        logger.error(f"[catalog] Error creating catalog: {e}", exc_info=True)
        return None


async def add_product(
    catalog_id: str,
    product_id: str,
    name: str,
    price: str,
    currency: str = "INR",
    description: str = "",
    image_url: Optional[str] = None,
    availability: str = "in stock"
) -> bool:
    """
    Add a product to the catalog.
    
    Args:
        catalog_id: WhatsApp Catalog ID
        product_id: Unique product identifier (retailer_id)
        name: Product name (policy name)
        price: Price in smallest currency unit (e.g., 385000 for ₹3,850.00)
        currency: Currency code (default: INR)
        description: Product description
        image_url: URL to product image (optional)
        availability: "in stock" or "out of stock"
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not _WA_TOKEN:
        logger.error("[catalog] WHATSAPP_TOKEN not set")
        return False
    
    url = f"{_GRAPH_URL}/{catalog_id}/products"
    headers = {
        "Authorization": f"Bearer {_WA_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Convert price to smallest currency unit (paise for INR)
    # "3850" → 385000 paise
    try:
        price_value = int(float(price.replace(",", "").replace("₹", "").strip()) * 100)
    except ValueError:
        logger.warning(f"[catalog] Invalid price format: {price}, using 0")
        price_value = 0
    
    payload = {
        "retailer_id": product_id,
        "name": name[:100],  # Max 100 chars
        "description": description[:5000] if description else name,
        "price": price_value,
        "currency": currency,
        "availability": availability,
        "condition": "new",
        "visibility": "published"
    }
    
    if image_url:
        payload["image_url"] = image_url
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code in (200, 201):
                logger.info(f"[catalog] Added product: {product_id}")
                return True
            else:
                logger.error(f"[catalog] Failed to add product {product_id}: {response.status_code} - {response.text}")
                return False
    except Exception as e:
        logger.error(f"[catalog] Error adding product: {e}", exc_info=True)
        return False


async def get_catalog_id() -> Optional[str]:
    """
    Get the first available catalog ID for the business.
    
    Returns:
        str: Catalog ID if found, None otherwise
    """
    if not _BUSINESS_ID or not _WA_TOKEN:
        logger.error("[catalog] FACEBOOK_BUSINESS_ID or WHATSAPP_TOKEN not set")
        return None
    
    url = f"{_GRAPH_URL}/{_BUSINESS_ID}/owned_product_catalogs"
    headers = {"Authorization": f"Bearer {_WA_TOKEN}"}
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                catalogs = result.get("data", [])
                if catalogs:
                    catalog_id = catalogs[0]["id"]
                    logger.info(f"[catalog] Found existing catalog: {catalog_id}")
                    return catalog_id
                else:
                    logger.info("[catalog] No catalogs found")
                    return None
            else:
                logger.error(f"[catalog] Failed to get catalogs: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        logger.error(f"[catalog] Error getting catalog: {e}", exc_info=True)
        return None


async def list_products(catalog_id: str) -> List[Dict]:
    """
    List all products in a catalog.
    
    Args:
        catalog_id: WhatsApp Catalog ID
    
    Returns:
        List of product dicts
    """
    if not _WA_TOKEN:
        logger.error("[catalog] WHATSAPP_TOKEN not set")
        return []
    
    url = f"{_GRAPH_URL}/{catalog_id}/products"
    headers = {"Authorization": f"Bearer {_WA_TOKEN}"}
    
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=headers, params={"fields": "id,retailer_id,name,price"})
            
            if response.status_code == 200:
                result = response.json()
                products = result.get("data", [])
                logger.info(f"[catalog] Found {len(products)} products")
                return products
            else:
                logger.error(f"[catalog] Failed to list products: {response.status_code} - {response.text}")
                return []
    except Exception as e:
        logger.error(f"[catalog] Error listing products: {e}", exc_info=True)
        return []


async def sync_policies_to_catalog(policies: List[Dict], catalog_id: Optional[str] = None) -> Optional[str]:
    """
    Sync a list of policies to WhatsApp catalog.
    Creates catalog if doesn't exist, adds missing products.
    
    Args:
        policies: List of policy dicts with keys: name, premium, sum_insured, insurer, etc.
        catalog_id: Existing catalog ID (optional, will create if not provided)
    
    Returns:
        str: Catalog ID if successful, None otherwise
    
    Example:
        policies = [
            {
                "name": "Schengen Visa Shield Gold",
                "insurer": "Care Insurance",
                "premium": "3850",
                "sum_insured": "€50,000",
                "highlights": ["Visa support", "Medical cover"]
            }
        ]
        catalog_id = await sync_policies_to_catalog(policies)
    """
    # Get or create catalog
    if not catalog_id:
        catalog_id = await get_catalog_id()
        if not catalog_id:
            logger.info("[catalog] No catalog found, creating new one...")
            catalog_id = await create_catalog()
            if not catalog_id:
                logger.error("[catalog] Failed to create catalog")
                return None
    
    # Get existing products
    existing_products = await list_products(catalog_id)
    existing_ids = {p.get("retailer_id") for p in existing_products}
    
    # Add missing products
    added_count = 0
    for policy in policies:
        name = policy.get("name") or policy.get("plan_name") or "Travel Plan"
        premium = policy.get("premium") or policy.get("price") or "0"
        cover = policy.get("sum_insured") or policy.get("coverage") or ""
        insurer = policy.get("insurer") or policy.get("provider") or ""
        highlights = policy.get("highlights") or []
        
        # Generate product ID
        product_id = name.lower().replace(" ", "_").replace("-", "_")[:100]
        
        # Skip if already exists
        if product_id in existing_ids:
            logger.debug(f"[catalog] Product already exists: {product_id}")
            continue
        
        # Build description
        desc_parts = [name]
        if insurer:
            desc_parts.append(f"Insurer: {insurer}")
        if cover:
            desc_parts.append(f"Coverage: {cover}")
        if highlights:
            desc_parts.append("Features: " + ", ".join(highlights[:3]))
        description = "\n".join(desc_parts)
        
        # Add product
        success = await add_product(
            catalog_id=catalog_id,
            product_id=product_id,
            name=name,
            price=premium,
            description=description,
            image_url=None  # TODO: Add image URL mapping
        )
        
        if success:
            added_count += 1
    
    logger.info(f"[catalog] Synced {added_count} new products to catalog {catalog_id}")
    return catalog_id


# ── Sample policies for initial catalog setup ─────────────────────────────────

SAMPLE_POLICIES = [
    {
        "name": "Schengen Visa Shield Gold",
        "insurer": "Care Insurance",
        "premium": "3850",
        "sum_insured": "€50,000",
        "highlights": ["Visa approval support", "Medical expenses covered", "Trip cancellation included"]
    },
    {
        "name": "Europe Premium Guard",
        "insurer": "Tata AIG",
        "premium": "4200",
        "sum_insured": "€75,000",
        "highlights": ["Adventure sports cover", "COVID protection", "Baggage protection"]
    },
    {
        "name": "Basic Europe Plan",
        "insurer": "Digit Insurance",
        "premium": "2100",
        "sum_insured": "€30,000",
        "highlights": ["Essential medical cover", "Emergency assistance", "Affordable premium"]
    },
    {
        "name": "USA Comprehensive Guard",
        "insurer": "Tata AIG",
        "premium": "6200",
        "sum_insured": "$250,000",
        "highlights": ["High medical cover", "COVID-19 included", "Adventure sports"]
    },
    {
        "name": "Asia Explorer Plan",
        "insurer": "Digit Insurance",
        "premium": "1800",
        "sum_insured": "$50,000",
        "highlights": ["Budget-friendly", "Medical emergencies", "Lost baggage cover"]
    },
    {
        "name": "Dubai Premium Shield",
        "insurer": "Care Insurance",
        "premium": "2500",
        "sum_insured": "$100,000",
        "highlights": ["UAE specialized", "Medical cover", "Trip delays"]
    },
    {
        "name": "Worldwide Elite Plan",
        "insurer": "HDFC ERGO",
        "premium": "8500",
        "sum_insured": "$500,000",
        "highlights": ["Global coverage", "Adventure sports", "Premium assistance"]
    },
    {
        "name": "Student Travel Plan",
        "insurer": "Bajaj Allianz",
        "premium": "5200",
        "sum_insured": "$100,000",
        "highlights": ["Study visa support", "Extended coverage", "Mental health support"]
    }
]


async def setup_initial_catalog() -> Optional[str]:
    """
    One-time setup: Create catalog and add sample policies.
    Run this once to initialize your WhatsApp catalog.
    
    Returns:
        str: Catalog ID if successful, None otherwise
    """
    logger.info("[catalog] Starting initial catalog setup...")
    catalog_id = await sync_policies_to_catalog(SAMPLE_POLICIES)
    
    if catalog_id:
        logger.info(f"[catalog] ✅ Initial catalog setup complete! Catalog ID: {catalog_id}")
        logger.info(f"[catalog] Add this to your .env file: WHATSAPP_CATALOG_ID={catalog_id}")
        return catalog_id
    else:
        logger.error("[catalog] ❌ Initial catalog setup failed")
        return None


# ── CLI Helper ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    
    async def main():
        print("🛍️ WhatsApp Product Catalog Manager\n")
        print("This will create a catalog and add sample insurance policies.\n")
        
        if not _BUSINESS_ID:
            print("❌ Error: FACEBOOK_BUSINESS_ID not set in environment")
            print("   Get it from: Meta Business Manager → Business Settings → Business Info")
            return
        
        if not _WA_TOKEN:
            print("❌ Error: WHATSAPP_TOKEN not set in environment")
            return
        
        print(f"Business ID: {_BUSINESS_ID}")
        print(f"Token: {_WA_TOKEN[:20]}...")
        print("\nCreating catalog...\n")
        
        catalog_id = await setup_initial_catalog()
        
        if catalog_id:
            print(f"\n✅ Success! Your catalog is ready.")
            print(f"\n📋 Catalog ID: {catalog_id}")
            print(f"\n🔧 Add this to hip/.env:")
            print(f"   WHATSAPP_CATALOG_ID={catalog_id}")
            print(f"\n✨ You can now use carousel messages for policies!")
        else:
            print("\n❌ Setup failed. Check logs for details.")
    
    asyncio.run(main())
