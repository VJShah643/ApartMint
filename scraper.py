import asyncio

import aiohttp
from bs4 import BeautifulSoup
import time 
import json
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


async def get_page(url: str):
    """Get and render page to return full html"""
    print(f"Getting page: {url}")

    try:
        page = await get_static_page(url)
        if not page or not page.get("page_text") or (len(page.get("page_text")) < 500):
            page = await get_dynamic_page(url)
    except Exception as e:
        print(f"Error getting page: {e}")
        # if this is a https page, try http
        if url.startswith("https"):
            new_url = url.replace("https", "http")
            print(f"Error getting page: {e}. Trying http instead: {new_url}")
            try:
                page = await get_page(new_url)
            except Exception as e:
                print(f"Error getting page: {e}")
                page = None
        else:
            print(f"Error getting page: {e}")
            page = None

    return page


async def get_static_page(url: str):
    """Get static page content using requests"""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10, headers=headers) as response:
                text = await response.text()

                # Check for bot blocking
                is_blocked, block_reason = await detect_bot_blocking(
                    text, response.status, url
                )
                if is_blocked:
                    print(f"Bot blocking detected for {url}: {block_reason}")
                    return {
                        "page_text": "",
                        "links": [],
                        "html": "",
                        "status_code": response.status,
                        "blocked": True,
                        "block_reason": block_reason,
                    }

                soup = BeautifulSoup(text, "html.parser")
                links = [a["href"] for a in soup.find_all("a", href=True)]

                return {
                    "page_text": soup.get_text(),
                    "links": list(set(links)),
                    "html": text,
                    "status_code": response.status,
                    "blocked": False,
                }
    except asyncio.TimeoutError:
        print(f"Timeout error in get_static_page for {url}")
    except Exception as e:
        print(f"Error in get_static_page for {url}:", e)
    return None


async def get_dynamic_page(url: str):
    """Get dynamic page content using Selenium with improved error handling, timeouts, and cleanup"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")

    driver = None
    timeout = 15

    try:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
        driver.set_page_load_timeout(timeout)

        print(f"Attempting to load page: {url}")
        await asyncio.get_event_loop().run_in_executor(None, driver.get, url)
        print(f"Successfully loaded page: {url}")

        try:
            await asyncio.get_event_loop().run_in_executor(
    None,
    lambda: WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div, main, section"))
    ),
)
            print("Body element found")
        except TimeoutException:
            print(
                "Body element not found within timeout. "
                "Proceeding with available content."
            )
        await asyncio.get_event_loop().run_in_executor(None, time.sleep, 5)
        main_text, main_links, main_html = await extract_content(driver)

        iframe_text, iframe_links, iframe_html = await asyncio.wait_for(
            get_iframe_content(driver), timeout=5
        )

        main_text += iframe_text
        main_links += iframe_links
        main_html += iframe_html

        return {
            "page_text": main_text,
            "links": list(set(main_links)),
            "html": main_html,
        }

    except asyncio.TimeoutError:
        print(f"Timeout occurred while processing {url}")
    except WebDriverException as e:
        print(f"WebDriver error occurred: {e}")
    except Exception as error:
        print(f"Error in get_dynamic_page for {url}: {error}")

    finally:
        if driver:
            try:
                for handle in driver.window_handles:
                    await asyncio.get_event_loop().run_in_executor(
                        None, driver.switch_to.window, handle
                    )
                    await asyncio.get_event_loop().run_in_executor(None, driver.close)
                await asyncio.get_event_loop().run_in_executor(None, driver.quit)
                print("WebDriver successfully closed and quit.")
            except Exception as e:
                print(f"Error while closing WebDriver: {e}")

    return None


async def extract_content(driver):
    try:
        # Extract text excluding script tags
        text = await asyncio.get_event_loop().run_in_executor(
            None,
            driver.execute_script,
            """
            try {
                return Array.from(document.body.childNodes)
                    .filter(node => node.nodeType === Node.ELEMENT_NODE && node.tagName.toLowerCase() !== 'script')
                    .map(node => node.innerText || '')
                    .join('\\n')
                    .trim();
            } catch (e) {
                return document.body ? document.body.innerText : '';
            }
            """,
        )
        print(f"Extracted text: {len(text)} characters")
    except Exception as e:
        print(f"Error extracting text: {e}")
        text = ""

    try:
        # Extract links
        links = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: [
                element.get_attribute("href")
                for element in driver.find_elements(By.TAG_NAME, "a")
            ],
        )
        # remove all None values AND remove empty strings
        links = list(filter(None, links))
        print(f"Extracted links: {len(links)}")
    except Exception as e:
        print(f"Error extracting links: {e}")
        links = []

    try:
        # Extract HTML excluding script tags
        html = await asyncio.get_event_loop().run_in_executor(
            None,
            driver.execute_script,
            """
            try {
                let clone = document.cloneNode(true);
                let scripts = clone.getElementsByTagName('script');
                while(scripts.length > 0) {
                    scripts[0].parentNode.removeChild(scripts[0]);
                }
                return clone.documentElement.outerHTML;
            } catch (e) {
                return document.documentElement.outerHTML;
            }
            """,
        )
        print(f"Extracted HTML: {len(html)} characters")
    except Exception as e:
        print(f"Error extracting HTML: {e}")
        html = ""

    return text, links, html


async def get_iframe_content(driver):
    iframes = await asyncio.get_event_loop().run_in_executor(
        None, lambda: driver.find_elements(By.TAG_NAME, "iframe")
    )

    iframe_text, iframe_links, iframe_html = "", [], ""

    for i, iframe in enumerate(iframes):
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, driver.switch_to.frame, iframe
            )
            text, links, html = await extract_content(driver)
            iframe_text += text
            iframe_links.extend(links)
            iframe_html += html
            await asyncio.get_event_loop().run_in_executor(
                None, driver.switch_to.default_content
            )
        except Exception as e:
            print(f"Error processing iframe {i+1}: {e}")
            await asyncio.get_event_loop().run_in_executor(
                None, driver.switch_to.default_content
            )

    return iframe_text, iframe_links, iframe_html


async def detect_bot_blocking(response_text, status_code, url):
    """Detect if the scraping request was blocked by anti-bot measures"""

    # Common bot blocking indicators
    blocking_indicators = [
        "cloudflare",
        "captcha",
        "access denied",
        "blocked",
        "bot detected",
        "rate limit",
        "too many requests",
        "verification required",
        "please verify",
        "security check",
        "forbidden",
        "unauthorized access",
    ]

    text_lower = response_text.lower()

    # Check for blocking keywords
    for indicator in blocking_indicators:
        if indicator in text_lower:
            return True, f"Blocked: {indicator} detected"

    # Check HTTP status codes
    blocking_status_codes = [403, 429, 503, 521, 522, 523, 524]
    if status_code in blocking_status_codes:
        return True, f"Blocked: HTTP {status_code}"

    # Check for minimal content (likely a blocking page)
    if len(response_text.strip()) < 100:
        return True, "Blocked: Minimal content returned"

    # Check for common anti-bot services
    if any(service in text_lower for service in ["cloudflare", "incapsula", "distil"]):
        return True, "Blocked: Anti-bot service detected"

    return False, "No blocking detected"
from bs4 import BeautifulSoup

async def extract_apartment_data(url: str):
    """Load the apartment page and extract main details"""
    print(f"Extracting data from: {url}")

    try:
        page = await get_dynamic_page(url)
        if not page or not page.get("html"):
            print("❌ No HTML found for this page.")
            return {"url": url, "error": "No HTML"}

        soup = BeautifulSoup(page["html"], "html.parser")

        # --- Helper: find value in hero section ---
        def get_hero_value(label):
            el = soup.find("span", string=label)
            if el:
                val = el.find_next("strong")
                return val.get_text(strip=True) if val else None
            return None

        # --- Basic Info ---
        title = soup.select_one("h1.ad__hero-title")
        area = soup.select_one("span.ad__hero-area")

        # --- Hero details ---
        rent = get_hero_value("Hyra")
        rooms = get_hero_value("Antal rum")
        size = get_hero_value("Storlek")
        move_in = get_hero_value("Inflyttningsdatum")
        housing_type = get_hero_value("Boendetyp")
        last_date = get_hero_value("Sista anmälningsdag")
        applicants = get_hero_value("Antal sökande")

        # --- Övrig information section ---
        landlord = None
        contract_type = None
        for dt in soup.find_all("dt", class_="ad__property-title"):
            label = dt.get_text(strip=True)
            dd = dt.find_next("dd")
            if not dd:
                continue
            value = dd.get_text(strip=True)
            if "Hyresvärd" in label:
                landlord = value
            elif "Kontraktstyp" in label:
                contract_type = value

        # --- Egenskaper section ---
        floor = None
        year = None
        for dt in soup.find_all("dt", class_="ad__property-title"):
            label = dt.get_text(strip=True)
            dd = dt.find_next("dd")
            if not dd:
                continue
            value = dd.get_text(strip=True)
            if "Våning" in label:
                floor = value
            elif "Byggår" in label:
                year = value

        # --- Descriptions (Bostad & Område) ---
        desc_sections = soup.find_all("div", class_="ad__body")
        description = desc_sections[0].get_text(" ", strip=True) if len(desc_sections) > 0 else None
        area_desc = desc_sections[1].get_text(" ", strip=True) if len(desc_sections) > 1 else None

        # --- Images ---
        images = [img["src"] for img in soup.select("img.ad__carousel-image")]

        data = {
            "url": url,
            "title": title.get_text(strip=True) if title else None,
            "area": area.get_text(strip=True) if area else None,
            "rent": rent,
            "rooms": rooms,
            "size": size,
            "move_in_date": move_in,
            "housing_type": housing_type,
            "last_application_date": last_date,
            "applicants": applicants,
            "landlord": landlord,
            "contract_type": contract_type,
            "floor": floor,
            "year_built": year,
            "description": description,
            "area_description": area_desc,
            "images": images,
        }

        print(f"✅ Extracted data for {data['title'] or url}")
        return data

    except Exception as e:
        print(f"⚠️ Error extracting {url}: {e}")
        # Return a minimal fallback entry so you don't lose the dataset
        return {"url": url, "error": str(e)}


async def extract_apartment_data2(url: str):
    """Extract Heimstaden apartment details."""
    print(f"Extracting data from: {url}")
    page = await get_dynamic_page(url)
    if not page or not page.get("html"):
        print("No HTML found.")
        return None

    soup = BeautifulSoup(page["html"], "html.parser")

    try:
        # --- Basic Header Info ---
        location = soup.select_one(".project-header__eyebrow")
        address = soup.select_one(".project-header__heading")
        rent = soup.select_one(".project-type")

        # --- Facts Table (e.g. size, floor, balcony) ---
        facts = {}
        for tr in soup.select(".project-facts-table tr"):
            th = tr.find("th")
            td = tr.find("td")
            if th and td:
                key = th.get_text(strip=True).replace(":", "")
                val = td.get_text(strip=True)
                facts[key] = val

        # --- Description ---
        description_section = soup.select_one(".project-intro")
        description = (
            description_section.get_text(" ", strip=True)
            if description_section
            else None
        )

        # --- Facilities ---
        facilities = [
            li.get_text(strip=True)
            for li in soup.select(".project-custom-quick-facts li")
        ]

        # --- Contact Info ---
        contact_name = soup.select_one(".project-contact-name")
        contact_email = soup.select_one(
            ".project-contact__option a[href^='mailto:']"
        )

        # --- Images ---
        images = [
            img["src"]
            for img in soup.select(".project-gallery__main-list-item img")
            if img.get("src")
        ]

        data = {
            "url": url,
            "location": location.get_text(strip=True) if location else None,
            "address": address.get_text(strip=True) if address else None,
            "rent": rent.get_text(strip=True) if rent else None,
            "available_from": facts.get("Tillgänglig"),
            "rooms": facts.get("Antal rum"),
            "size": facts.get("Storlek"),
            "floor": facts.get("Våning"),
            "balcony": facts.get("Balkong"),
            "elevator": facts.get("Hiss"),
            "storage": facts.get("Förråd"),
            "building": facts.get("Fastighet"),
            "year_built": facts.get("Byggnadsår"),
            "object_number": facts.get("Objektsnummer"),
            "description": description,
            "facilities": facilities,
            "contact_name": contact_name.get_text(strip=True) if contact_name else None,
            "contact_email": contact_email.get_text(strip=True) if contact_email else None,
            "images": images,
        }

        print(f"Extracted: {data['address'] or 'Unnamed'}")
        return data

    except Exception as e:
        print(f"Error extracting data from {url}: {e}")
        return None

# ---- Run the async task ----

# urls = [
#     "https://www.bostad.uppsala.se/mypages/app/visa/200048546269",
#     # Add more apartment URLs here
# ]

async def Check_Apartment_Data():
    # url = "https://www.bostad.uppsala.se/mypages/app"
    url_2 = "https://heimstaden.com/se/sok-lagenhet/?map_center=60.89163828977962,17.194410500000004&map_zoom=5"
    result = await get_page(url_2)
    results = []
    urls = result.get("links", [])
    for url in urls:
        data = await extract_apartment_data2(url)
        results.append(data)
    return results


if __name__ == "__main__":
    apartments = asyncio.run(Check_Apartment_Data())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"apartments_heimstadin_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(apartments, f, ensure_ascii=False, indent=4)

    print(f"\n Saved {len(apartments)} apartment(s) to {filename}")

