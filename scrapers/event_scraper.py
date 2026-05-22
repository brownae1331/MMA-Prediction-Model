from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from schemas.event import Event
from scrapers.browser_session import BrowserSession


class UFCStatsEventScraper:
    def __init__(self, browser: BrowserSession | None = None):
        self.base_url = "http://ufcstats.com/statistics/events/"
        self._owns_browser = browser is None
        self.browser = browser or BrowserSession()
        if self._owns_browser:
            self.browser.start()

    def close(self) -> None:
        if self._owns_browser:
            self.browser.close()

    def __enter__(self) -> "UFCStatsEventScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def parse_events_from_page(self, page_path: str) -> list[Event]:
        url = urljoin(self.base_url, page_path)
        response = self.browser.get(url)
        if response is None:
            return []
        soup = BeautifulSoup(response.text, "html.parser")

        events = []
        event_containers = soup.find_all("tr", class_="b-statistics__table-row")
        for event in event_containers:
            left_container = event.find("td", class_="b-statistics__table-col")
            if not left_container:
                continue
            right_container = event.find("td", class_="b-statistics__table-col b-statistics__table-col_style_big-top-padding")
            if not right_container:
                continue

            url = left_container.find("a")["href"]
            title = left_container.find("a").text.strip()
            date_str = left_container.find("span", class_="b-statistics__date").text.strip()
            date = datetime.strptime(date_str, "%B %d, %Y")
            location = right_container.get_text(strip=True)
            
            events.append(Event(
                url=url,
                title=title,
                date=date,
                location=location,
                organizer="UFC",
            ))

        return events
    
    @staticmethod
    def get_ufc_1() -> Event:
        """Doesn't show up in the completed events page, so we need to add it manually."""
        return Event(
            url="http://ufcstats.com/event-details/6420efac0578988b",
            title="UFC 1: The Beginning",
            date=datetime(1993, 11, 12),
            location="Denver, Colorado, USA",
            organizer="UFC",
        )

    def get_upcoming_events(self) -> list[Event]:
        return self.parse_events_from_page("upcoming?page=all")

    def get_all_events(self) -> list[Event]:
        events = self.parse_events_from_page("completed?page=all")
        events.extend(self.parse_events_from_page("upcoming?page=all"))
        events.append(self.get_ufc_1())
        return events

if __name__ == "__main__":
    with UFCStatsEventScraper() as scraper:
        events = scraper.get_all_events()
    print(f"Scraped {len(events)} events")
    for event in events[:3]:
        print(event.model_dump_json())