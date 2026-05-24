from datetime import date, datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from schemas.fighter import Fighter
from scrapers.browser_session import BrowserSession, PageResponse


class UFCStatsFighterScraper:
    def __init__(self, browser: BrowserSession | None = None):
        self.base_url = "http://ufcstats.com/statistics/fighters"
        self._owns_browser = browser is None
        self.browser = browser or BrowserSession()
        if self._owns_browser:
            self.browser.start()

    def close(self) -> None:
        if self._owns_browser:
            self.browser.close()

    def __enter__(self) -> "UFCStatsFighterScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _get(self, url: str) -> PageResponse | None:
        return self.browser.get(url)

    def get_all_fighters(self) -> list[Fighter]:
        fighters: list[Fighter] = []
        for i in range(ord("a"), ord("z") + 1):
            print(f"Scraping fighters starting with {chr(i)}")
            list_url = urljoin(self.base_url, f"?char={chr(i)}&page=all")
            response = self._get(list_url)
            if response is None:
                continue
            soup = BeautifulSoup(response.text, "html.parser")

            fighter_rows = soup.find_all("tr", class_="b-statistics__table-row")
            for row in fighter_rows:
                cols = row.find_all("td", class_="b-statistics__table-col")
                if len(cols) < 10:
                    continue

                first_link = cols[0].find("a")
                if not first_link or not first_link.get("href"):
                    continue

                fighter_url = first_link["href"]
                fighter = self.get_fighter(fighter_url)
                if fighter:
                    fighters.append(fighter)
                    print(f"Scraped fighter: {fighter.name}")
                else:
                    print(f"Failed to scrape fighter: {fighter_url}")

        return fighters

    def get_fighter(self, fighter_url: str) -> Fighter | None:
        response = self._get(fighter_url)
        if response is None:
            return None
        soup = BeautifulSoup(response.text, "html.parser")

        name_el = soup.find("span", class_="b-content__title-highlight")
        if not name_el:
            return None
        name = name_el.get_text(strip=True)
        if not name:
            return None

        nickname_el = soup.find("p", class_="b-content__Nickname")
        nickname = nickname_el.get_text(strip=True) if nickname_el else None

        stats = self._parse_stat_items(soup)

        career = {
            "SLpM": self._parse_float(stats.get("slpm")),
            "StrAcc": self._parse_float(stats.get("str. acc.")),
            "SApM": self._parse_float(stats.get("sapm")),
            "StrDef": self._parse_float(stats.get("str. def.")),
            "TDAvg": self._parse_float(stats.get("td avg.")),
            "TDAcc": self._parse_float(stats.get("td acc.")),
            "TDDef": self._parse_float(stats.get("td def.")),
            "SubAvg": self._parse_float(stats.get("sub. avg.")),
        }

        if all(value == 0.0 for value in career.values()):
            career = {key: None for key in career.keys()}

        return Fighter(
            url=fighter_url,
            name=name,
            nickname=nickname,
            height=stats.get("height"),
            weight=stats.get("weight"),
            reach=stats.get("reach"),
            stance=stats.get("stance"),
            dob=self._parse_dob(stats.get("dob")),
            **career,
        )

    @staticmethod
    def _parse_stat_items(soup: BeautifulSoup) -> dict[str, str | None]:
        """Parse every `<li>` 'Label: value' pair on the page into one dict."""
        result: dict[str, str | None] = {}
        for item in soup.find_all("li", class_="b-list__box-list-item"):
            title_el = item.find("i", class_="b-list__box-item-title")
            if not title_el:
                continue

            title_text = title_el.get_text(strip=True)
            if not title_text:
                continue

            key = title_text.rstrip(":").strip().lower()
            value = item.get_text(" ", strip=True).replace(title_text, "", 1).strip()
            if not value or value == "--":
                value = None

            result[key] = value
        return result

    @staticmethod
    def _parse_dob(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return datetime.strptime(value, "%b %d, %Y").date()
        except ValueError:
            return None

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        if not value:
            return None
        try:
            return float(value.replace("%", "").strip())
        except ValueError:
            return None

if __name__ == "__main__":
    with UFCStatsFighterScraper() as scraper:
        fighters = scraper.get_all_fighters()
    print(f"Scraped {len(fighters)} fighters")
    for fighter in fighters[:3]:
        print(fighter.model_dump_json())
