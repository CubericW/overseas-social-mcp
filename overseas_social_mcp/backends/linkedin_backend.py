"""LinkedIn backend via linkedin_scraper (https://github.com/joeyism/linkedin_scraper).

LinkedIn is the highest-risk platform here: scraping violates its ToS and can
get accounts restricted. This backend is DISABLED by default. Enable only with
a throwaway account, at very low frequency, and at your own risk:

    OSMCP_LINKEDIN_ENABLED=true
    OSMCP_LINKEDIN_EMAIL / OSMCP_LINKEDIN_PASSWORD
    OSMCP_CHROMEDRIVER=/path/to/chromedriver

Given the risk, this backend supports only single-profile / single-company
lookups, not bulk crawling.
"""

from __future__ import annotations

from typing import Any

from ..common import BackendUnavailable, make_item
from ..config import Settings


def _driver_and_creds(settings: Settings):
    if not settings.linkedin_enabled:
        raise BackendUnavailable(
            "LinkedIn backend is disabled. It is high-risk (violates ToS, may "
            "restrict your account). Set OSMCP_LINKEDIN_ENABLED=true and provide "
            "credentials to enable, at your own risk."
        )
    if not (settings.linkedin_email and settings.linkedin_password):
        raise BackendUnavailable(
            "LinkedIn credentials missing. Set OSMCP_LINKEDIN_EMAIL / "
            "OSMCP_LINKEDIN_PASSWORD (use a throwaway account)."
        )
    try:
        from selenium import webdriver  # type: ignore
        from linkedin_scraper import actions  # type: ignore  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise BackendUnavailable(
            "Packages 'linkedin_scraper' and 'selenium' are required. Install "
            "with `pip install --user linkedin_scraper selenium` and provide a "
            "matching chromedriver via OSMCP_CHROMEDRIVER."
        ) from exc

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    if settings.chromedriver_path:
        from selenium.webdriver.chrome.service import Service  # type: ignore

        driver = webdriver.Chrome(service=Service(settings.chromedriver_path), options=options)
    else:
        driver = webdriver.Chrome(options=options)
    return driver


def get_profile(settings: Settings, profile_url: str) -> list[dict[str, Any]]:
    from linkedin_scraper import Person, actions  # type: ignore

    driver = _driver_and_creds(settings)
    try:
        actions.login(driver, settings.linkedin_email, settings.linkedin_password)
        person = Person(profile_url, driver=driver, scrape=True, close_on_complete=False)
        item = make_item(
            id=profile_url,
            author=getattr(person, "name", None),
            content=getattr(person, "about", None) or "",
            url=profile_url,
            extra={
                "job_title": getattr(person, "job_title", None),
                "company": getattr(person, "company", None),
                "experiences": [str(e) for e in getattr(person, "experiences", []) or []],
                "educations": [str(e) for e in getattr(person, "educations", []) or []],
            },
        )
        return [item]
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass


def get_company(settings: Settings, company_url: str) -> list[dict[str, Any]]:
    from linkedin_scraper import Company, actions  # type: ignore

    driver = _driver_and_creds(settings)
    try:
        actions.login(driver, settings.linkedin_email, settings.linkedin_password)
        company = Company(company_url, driver=driver, scrape=True, close_on_complete=False, get_employees=False)
        item = make_item(
            id=company_url,
            author=getattr(company, "name", None),
            content=getattr(company, "about_us", None) or "",
            url=company_url,
            extra={
                "industry": getattr(company, "industry", None),
                "company_size": getattr(company, "company_size", None),
                "headquarters": getattr(company, "headquarters", None),
                "website": getattr(company, "website", None),
            },
        )
        return [item]
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass
