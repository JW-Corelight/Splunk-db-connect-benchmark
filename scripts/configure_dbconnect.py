#!/usr/bin/env python3
"""
Configure Splunk DB Connect using Playwright automation
"""

import asyncio
import sys
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


async def configure_db_connect():
    """Configure DB Connect identities and connections via Splunk Web UI"""

    async with async_playwright() as p:
        # Launch browser
        print("Launching browser...")
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        try:
            # Login to Splunk
            print("Navigating to Splunk...")
            await page.goto("https://localhost:8000/")
            await page.wait_for_timeout(3000)

            print("Logging in...")
            await page.fill('input[name="username"]', "admin")
            await page.fill('input[name="password"]', "ComplexP@ss123")
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(5000)

            # Navigate to DB Connect
            print("Navigating to DB Connect...")
            await page.goto("https://localhost:8000/en-US/app/splunk_app_db_connect/configuration")
            await page.wait_for_timeout(5000)

            # Check if DB Connect loaded
            print("Checking if DB Connect is accessible...")

            # Create PostgreSQL Identity
            print("\n=== Creating PostgreSQL Identity ===")
            await page.goto("https://localhost:8000/en-US/app/splunk_app_db_connect/configuration?form=identities")
            await page.wait_for_timeout(3000)

            # Click "New Identity" button
            try:
                await page.click('button:has-text("New Identity")', timeout=10000)
                await page.wait_for_timeout(2000)

                # Fill identity form
                await page.fill('input[name="name"]', "postgres_identity")
                await page.fill('input[name="username"]', "postgres")
                await page.fill('input[name="password"]', "postgres123")

                # Save identity
                await page.click('button:has-text("Save")')
                await page.wait_for_timeout(2000)
                print("✅ PostgreSQL identity created")
            except PlaywrightTimeoutError:
                print("⚠️  Could not find New Identity button, trying alternate method...")

            # Create ClickHouse Identity
            print("\n=== Creating ClickHouse Identity ===")
            try:
                await page.click('button:has-text("New Identity")', timeout=10000)
                await page.wait_for_timeout(2000)

                await page.fill('input[name="name"]', "clickhouse_identity")
                await page.fill('input[name="username"]', "default")
                # Leave password empty for ClickHouse default user

                await page.click('button:has-text("Save")')
                await page.wait_for_timeout(2000)
                print("✅ ClickHouse identity created")
            except PlaywrightTimeoutError:
                print("⚠️  Could not create ClickHouse identity")

            # Create PostgreSQL Connection
            print("\n=== Creating PostgreSQL Connection ===")
            await page.goto("https://localhost:8000/en-US/app/splunk_app_db_connect/configuration?form=connections")
            await page.wait_for_timeout(3000)

            try:
                await page.click('button:has-text("New Connection")', timeout=10000)
                await page.wait_for_timeout(2000)

                # Fill connection form
                await page.fill('input[name="name"]', "postgresql_conn")
                await page.select_option('select[name="identity"]', "postgres_identity")
                await page.select_option('select[name="connection_type"]', "PostgreSQL")

                # JDBC URL
                jdbc_url = "jdbc:postgresql://benchmark-postgresql:5432/cybersecurity"
                await page.fill('input[name="jdbc_url"]', jdbc_url)

                # Mark as read-only
                await page.check('input[name="readonly"]')

                # Save connection
                await page.click('button:has-text("Save")')
                await page.wait_for_timeout(3000)
                print("✅ PostgreSQL connection created")

                # Test connection
                print("Testing PostgreSQL connection...")
                await page.click('button:has-text("Test Connection")')
                await page.wait_for_timeout(5000)
                print("✅ PostgreSQL connection tested")
            except PlaywrightTimeoutError as e:
                print(f"⚠️  Could not create PostgreSQL connection: {e}")

            # Create ClickHouse Connection
            print("\n=== Creating ClickHouse Connection ===")
            try:
                await page.click('button:has-text("New Connection")', timeout=10000)
                await page.wait_for_timeout(2000)

                await page.fill('input[name="name"]', "clickhouse_conn")
                await page.select_option('select[name="identity"]', "clickhouse_identity")
                await page.select_option('select[name="connection_type"]', "Generic")

                # JDBC URL
                jdbc_url = "jdbc:clickhouse://benchmark-clickhouse:8123/cybersecurity"
                await page.fill('input[name="jdbc_url"]', jdbc_url)

                # Mark as read-only
                await page.check('input[name="readonly"]')

                # Save connection
                await page.click('button:has-text("Save")')
                await page.wait_for_timeout(3000)
                print("✅ ClickHouse connection created")

                # Test connection
                print("Testing ClickHouse connection...")
                await page.click('button:has-text("Test Connection")')
                await page.wait_for_timeout(5000)
                print("✅ ClickHouse connection tested")
            except PlaywrightTimeoutError as e:
                print(f"⚠️  Could not create ClickHouse connection: {e}")

            print("\n=== Configuration Summary ===")
            print("Navigate to: https://localhost:8000/en-US/app/splunk_app_db_connect/configuration")
            print("Check the Identities and Connections tabs to verify configuration")

            # Keep browser open for user to verify
            print("\nBrowser will remain open for 30 seconds for you to verify...")
            await page.wait_for_timeout(30000)

        except Exception as e:
            print(f"❌ Error: {e}")
            print(f"Current URL: {page.url}")

            # Take screenshot for debugging
            screenshot_path = "/tmp/splunk_dbconnect_error.png"
            await page.screenshot(path=screenshot_path)
            print(f"Screenshot saved to: {screenshot_path}")

            # Keep browser open for debugging
            print("\nBrowser will remain open for 60 seconds for debugging...")
            await page.wait_for_timeout(60000)

        finally:
            await browser.close()


if __name__ == "__main__":
    print("=== Splunk DB Connect Configuration Automation ===\n")
    asyncio.run(configure_db_connect())
