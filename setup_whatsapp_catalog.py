#!/usr/bin/env python3
"""
WhatsApp Catalog Setup Script

Run this once to create your WhatsApp Product Catalog via API.
No manual Meta Business Manager access needed!

Requirements:
1. Set WHATSAPP_BUSINESS_ACCOUNT_ID in .env (your WABA ID)
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
    waba_id = os.environ.get("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    wa_token = os.environ.get("WHATSAPP_TOKEN", "")
    
    if not waba_id:
        print("❌ Missing WHATSAPP_BUSINESS_ACCOUNT_ID")
        print()
        print("This is your WABA ID (WhatsApp Business Account ID)")
        print()
        print("How to get it:")
        print("1. Go to: https://business.facebook.com/latest/whatsapp_manager")
        print("2. Select your WhatsApp Business Account")
        print("3. Click Settings → API Setup")
        print("4. Copy 'WhatsApp Business Account ID' (the number at the top)")
        print()
        print("Example: 1108224387960821")
        print()
        print("Add to hip/.env:")
        print("  WHATSAPP_BUSINESS_ACCOUNT_ID=YOUR_WABA_ID")
        print()
        return
    
    if not wa_token:
        print("❌ Missing WHATSAPP_TOKEN")
        print()
        print("Make sure WHATSAPP_TOKEN is set in hip/.env")
        print()
        return
    
    print(f"✅ WABA ID: {waba_id}")
    print(f"✅ Token: {wa_token[:20]}...")
    print()
    
    # Check if catalog already exists
    print("Step 1: Create Catalog in Commerce Manager")
    print("-" * 70)
    print()
    print("WhatsApp catalogs must be created in Meta Commerce Manager first.")
    print()
    print("📋 Quick Steps:")
    print("1. Go to: https://business.facebook.com/commerce/catalogs")
    print("2. Click 'Create Catalog' → Choose 'E-commerce'")
    print("3. Name it: 'Travel Insurance Plans'")
    print("4. After creation, go to catalog settings")
    print("5. Copy the Catalog ID (long number in URL or settings)")
    print()
    
    catalog_id = input("Enter your Catalog ID (or press Enter to skip): ").strip()
    
    if not catalog_id:
        print()
        print("⚠️  No Catalog ID provided.")
        print("Create a catalog first, then run this script again.")
        print()
        return
    
    print()
    print(f"✅ Using Catalog ID: {catalog_id}")
    print()
    
    # Add sample policies
    print("Step 2: Adding Sample Policies")
    print("-" * 70)
    print()
    print("Adding 8 sample insurance policies to your catalog...")
    print()
    
    result_catalog_id = await setup_initial_catalog(catalog_id)
    
    if result_catalog_id:
        print()
        print("="*70)
        print("  ✅ SUCCESS!")
        print("="*70)
        print()
        print(f"📋 Catalog ID: {result_catalog_id}")
        print()
        print("🔧 Next Steps:")
        print()
        print(f"1. Add to hip/.env:")
        print(f"   WHATSAPP_CATALOG_ID={result_catalog_id}")
        print()
        print("2. Restart your server")
        print()
        print("3. Test by asking for travel insurance quotes on WhatsApp")
        print()
        print("✨ Carousel messages are now enabled!")
        print()
        print("📦 8 sample policies added:")
        print("   • Schengen Visa Shield Gold")
        print("   • Europe Premium Guard")
        print("   • Basic Europe Plan")
        print("   • USA Comprehensive Guard")
        print("   • Asia Explorer Plan")
        print("   • Dubai Premium Shield")
        print("   • Worldwide Elite Plan")
        print("   • Student Travel Plan")
        print()
    else:
        print()
        print("="*70)
        print("  ❌ SETUP FAILED")
        print("="*70)
        print()
        print("Common issues:")
        print()
        print("1. Catalog ID is incorrect")
        print("   → Double-check from Commerce Manager catalog settings")
        print()
        print("2. Token doesn't have catalog_management permission")
        print("   → Generate new token with catalog permissions")
        print()
        print("3. Network/API error")
        print("   → Check logs above for details")
        print()


if __name__ == "__main__":
    asyncio.run(main())
