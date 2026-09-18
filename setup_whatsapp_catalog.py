#!/usr/bin/env python3
"""
WhatsApp Catalog Setup Script

Run this once to create your WhatsApp Product Catalog via API.
No manual Meta Business Manager access needed!

Requirements:
1. Set FACEBOOK_BUSINESS_ID in .env (get from Meta Business Settings)
2. Ensure WHATSAPP_TOKEN has catalog_management permission

Usage:
    python setup_whatsapp_catalog.py
"""
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from whatsapp.catalog_manager import setup_initial_catalog, get_catalog_id


async def main():
    print("="*70)
    print("  WhatsApp Product Catalog Setup")
    print("="*70)
    print()
    
    # Check prerequisites
    business_id = os.environ.get("FACEBOOK_BUSINESS_ID", "")
    wa_token = os.environ.get("WHATSAPP_TOKEN", "")
    
    if not business_id:
        print("❌ Missing FACEBOOK_BUSINESS_ID")
        print()
        print("How to get it:")
        print("1. Go to: https://business.facebook.com/settings")
        print("2. Click 'Business Info' in left sidebar")
        print("3. Copy 'Business ID' (long number)")
        print("4. Add to hip/.env: FACEBOOK_BUSINESS_ID=YOUR_BUSINESS_ID")
        print()
        return
    
    if not wa_token:
        print("❌ Missing WHATSAPP_TOKEN")
        print()
        print("Make sure WHATSAPP_TOKEN is set in hip/.env")
        print()
        return
    
    print(f"✅ Business ID: {business_id}")
    print(f"✅ Token: {wa_token[:20]}...")
    print()
    
    # Check if catalog already exists
    print("Checking for existing catalog...")
    existing_catalog = await get_catalog_id()
    
    if existing_catalog:
        print(f"✅ Found existing catalog: {existing_catalog}")
        print()
        print("Do you want to:")
        print("  1. Use this catalog (recommended)")
        print("  2. Create a new catalog")
        print()
        choice = input("Enter choice (1 or 2): ").strip()
        
        if choice == "1":
            print()
            print(f"Using existing catalog: {existing_catalog}")
            print()
            print(f"🔧 Add this to hip/.env:")
            print(f"   WHATSAPP_CATALOG_ID={existing_catalog}")
            print()
            return
    
    # Create new catalog
    print()
    print("Creating new catalog with sample policies...")
    print()
    
    catalog_id = await setup_initial_catalog()
    
    if catalog_id:
        print()
        print("="*70)
        print("  ✅ SUCCESS!")
        print("="*70)
        print()
        print(f"📋 Catalog ID: {catalog_id}")
        print()
        print("🔧 Next Steps:")
        print()
        print(f"1. Add to hip/.env:")
        print(f"   WHATSAPP_CATALOG_ID={catalog_id}")
        print()
        print("2. Restart your server")
        print()
        print("3. Test by sending a message asking for travel insurance quotes")
        print()
        print("✨ Carousel messages are now enabled!")
        print()
    else:
        print()
        print("="*70)
        print("  ❌ SETUP FAILED")
        print("="*70)
        print()
        print("Common issues:")
        print()
        print("1. Token doesn't have catalog_management permission")
        print("   → Generate new token with catalog permissions")
        print()
        print("2. Business ID is incorrect")
        print("   → Double-check from Business Settings")
        print()
        print("3. Network/API error")
        print("   → Check logs above for details")
        print()


if __name__ == "__main__":
    asyncio.run(main())
