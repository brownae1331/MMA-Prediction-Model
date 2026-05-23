"""Scrape UFC fight data from event and fight detail pages."""

import re

from bs4 import BeautifulSoup, Tag

from schemas.fight import FightDetail, FightInfo, FightRoundStats, FightStub, JudgeScore
from scrapers.browser_session import BrowserSession, PageResponse


class UFCStatsFightScraper:
    def __init__(self, browser: BrowserSession | None = None):
        self._owns_browser = browser is None
        self.browser = browser or BrowserSession()
        if self._owns_browser:
            self.browser.start()

    def close(self) -> None:
        if self._owns_browser:
            self.browser.close()

    def __enter__(self) -> "UFCStatsFightScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _get(self, url: str) -> PageResponse | None:
        return self.browser.get(url)

    def get_fight_stubs_for_event(self, event_url: str) -> list[FightStub]:
        """Parse the event page fight table into FightStub rows."""
        response = self._get(event_url)
        if response is None:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        container = soup.find("div", class_="b-fight-details") or soup
        rows = container.find_all("tr", class_="js-fight-details-click")
        if not rows:
            return []

        stubs: list[FightStub] = []
        for match_number, row in enumerate(rows, start=1):
            fight_url = row.get("data-link") or ""
            if not fight_url:
                onclick = row.get("onclick", "")
                match = re.search(r"doNav\('([^']+)'\)", onclick)
                if match:
                    fight_url = match.group(1)

            fighter_col = row.find("td", class_="l-page_align_left")
            if not fighter_col:
                continue
            fighter_links = fighter_col.find_all("a", href=re.compile(r"fighter-details"))
            if len(fighter_links) < 2:
                continue

            cols = row.find_all("td", class_="b-fight-details__table-col")
            weight_class = None
            if len(cols) > 6:
                weight_class = cols[6].get_text(" ", strip=True).split("\n")[0].strip() or None

            stubs.append(
                FightStub(
                    url=fight_url.strip(),
                    fighter_1_url=fighter_links[0]["href"].strip(),
                    fighter_2_url=fighter_links[1]["href"].strip(),
                    match_number=match_number,
                    weight_class=weight_class,
                )
            )

        return stubs

    def get_fight_detail(self, fight_url: str, *, progress: str | None = None) -> FightDetail | None:
        """Parse a fight detail page into FightInfo + per-round stats."""
        prefix = progress or "Scraping fight"
        print(f"{prefix}: {fight_url}", flush=True)
        response = self._get(fight_url)
        if response is None:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        fight_info = self._parse_fight_info(soup, fight_url)
        if fight_info is None:
            return None

        round_stats = self._parse_round_stats(soup)
        return FightDetail(fight=fight_info, round_stats=round_stats)

    def get_fights_for_event(self, event_url: str) -> list[FightDetail]:
        """Scrape all fight detail pages for an event."""
        details: list[FightDetail] = []
        stubs = self.get_fight_stubs_for_event(event_url)
        total = len(stubs)
        for i, stub in enumerate(stubs, start=1):
            wc = f" — {stub.weight_class}" if stub.weight_class else ""
            progress = f"[{i}/{total}] Fight #{stub.match_number}{wc}"
            detail = self.get_fight_detail(stub.url, progress=progress)
            if detail:
                if not detail.fight.weight_class and stub.weight_class:
                    detail.fight.weight_class = stub.weight_class
                details.append(detail)
        return details

    @staticmethod
    def _parse_fight_info(soup: BeautifulSoup, fight_url: str) -> FightInfo | None:
        weight_el = soup.find("i", class_="b-fight-details__fight-title")
        weight_class = weight_el.get_text(strip=True) if weight_el else None

        winner_url = None
        for person in soup.find_all("div", class_="b-fight-details__person"):
            status = person.find("i", class_="b-fight-details__person-status")
            link = person.find("a", class_="b-fight-details__person-link")
            if not status or not link:
                continue
            classes = " ".join(status.get("class", []))
            if "green" in classes:
                winner_url = link["href"].strip()

        labels = UFCStatsFightScraper._parse_fight_labels(soup)
        scorecard = UFCStatsFightScraper._parse_scorecard(soup)

        finish_round = labels.get("round")
        if finish_round is not None:
            try:
                finish_round = int(finish_round)
            except ValueError:
                finish_round = None

        return FightInfo(
            url=fight_url,
            weight_class=weight_class,
            winner_url=winner_url,
            method=labels.get("method"),
            finish_round=finish_round,
            finish_time=labels.get("time"),
            time_format=labels.get("time format"),
            referee=labels.get("referee"),
            scorecard=scorecard,
        )

    @staticmethod
    def _parse_fight_labels(soup: BeautifulSoup) -> dict[str, str]:
        labels: dict[str, str] = {}
        fight_box = soup.find("div", class_="b-fight-details__fight")
        if not fight_box:
            return labels

        for item in fight_box.find_all(
            "i",
            class_=lambda c: c
            and ("b-fight-details__text-item" in c or "b-fight-details__text-item_first" in c),
        ):
            label_el = item.find("i", class_="b-fight-details__label")
            if not label_el:
                continue
            key = label_el.get_text(strip=True).rstrip(":").strip().lower()
            if key == "details":
                continue
            value = item.get_text(" ", strip=True).replace(label_el.get_text(strip=True), "", 1).strip()
            if value:
                labels[key] = value
        return labels

    @staticmethod
    def _parse_scorecard(soup: BeautifulSoup) -> list[JudgeScore] | None:
        """Parse the 'Details:' section into a list of judge scores.

        UFCStats renders each judge as `<judge> <f1_score> - <f2_score>.`,
        e.g. "Eric Colon 45 - 50.".
        """
        fight_box = soup.find("div", class_="b-fight-details__fight")
        if not fight_box:
            return None

        score_pattern = re.compile(r"^(.*?)\s+(\d+)\s*-\s*(\d+)\.?$")
        scores: list[JudgeScore] = []
        for item in fight_box.find_all("i", class_="b-fight-details__text-item"):
            if item.find("i", class_="b-fight-details__label"):
                continue
            text = item.get_text(" ", strip=True)
            if not text:
                continue
            match = score_pattern.match(text)
            if not match:
                continue
            scores.append(
                JudgeScore(
                    judge=match.group(1).strip(),
                    fighter_1=int(match.group(2)),
                    fighter_2=int(match.group(3)),
                )
            )

        return scores or None

    def _parse_round_stats(self, soup: BeautifulSoup) -> list[FightRoundStats]:
        """Merge per-round totals and significant-strike breakdown tables."""
        stats_map: dict[tuple[str, int], dict] = {}

        # Per-round tables live inside sections with js-fight-table (hidden in HTML, still parseable)
        for table in soup.find_all("table", class_="js-fight-table"):
            if not table.find("thead", class_="b-fight-details__table-row_type_head"):
                continue
            if self._is_sig_strikes_table(table):
                self._parse_sig_strikes_round_table(table, stats_map)
            else:
                self._parse_totals_round_table(table, stats_map)

        return [
            FightRoundStats(**data)
            for data in sorted(stats_map.values(), key=lambda d: (d["round_number"], d["fighter_url"]))
        ]

    @staticmethod
    def _is_sig_strikes_table(table: Tag) -> bool:
        header_row = table.find("tr", class_="b-fight-details__table-row")
        if not header_row:
            return False
        headers = [th.get_text(strip=True) for th in header_row.find_all("th")]
        return "Head" in headers

    def _parse_totals_round_table(self, table: Tag, stats_map: dict[tuple[str, int], dict]) -> None:
        for thead in table.find_all("thead", class_="b-fight-details__table-row_type_head"):
            round_number = self._parse_round_header(thead)
            if round_number is None:
                continue

            row = thead.find_next("tr", class_="b-fight-details__table-row")
            if not row:
                continue

            cols = row.find_all("td", class_="b-fight-details__table-col")
            if len(cols) < 10:
                continue

            fighter_urls = self._fighter_urls_from_col(cols[0])
            if len(fighter_urls) != 2:
                continue

            for fighter_idx, fighter_url in enumerate(fighter_urls):
                data = self._ensure_round(stats_map, fighter_url, round_number)

                data["knockdowns"] = self._parse_int(self._value_at(cols, 1, fighter_idx))
                landed, attempted = self._parse_landed_attempted(self._value_at(cols, 2, fighter_idx))
                data["sig_strikes_landed"] = landed
                data["sig_strikes_attempted"] = attempted
                landed, attempted = self._parse_landed_attempted(self._value_at(cols, 4, fighter_idx))
                data["total_strikes_landed"] = landed
                data["total_strikes_attempted"] = attempted
                landed, attempted = self._parse_landed_attempted(self._value_at(cols, 5, fighter_idx))
                data["takedowns_landed"] = landed
                data["takedowns_attempted"] = attempted
                data["submission_attempts"] = self._parse_int(self._value_at(cols, 7, fighter_idx))
                data["reversals"] = self._parse_int(self._value_at(cols, 8, fighter_idx))
                data["control_time_seconds"] = self._parse_control_seconds(self._value_at(cols, 9, fighter_idx))

    def _parse_sig_strikes_round_table(self, table: Tag, stats_map: dict[tuple[str, int], dict]) -> None:
        for thead in table.find_all("thead", class_="b-fight-details__table-row_type_head"):
            round_number = self._parse_round_header(thead)
            if round_number is None:
                continue

            row = thead.find_next("tr", class_="b-fight-details__table-row")
            if not row:
                continue

            cols = row.find_all("td", class_="b-fight-details__table-col")
            if len(cols) < 9:
                continue

            fighter_urls = self._fighter_urls_from_col(cols[0])
            if len(fighter_urls) != 2:
                continue

            for fighter_idx, fighter_url in enumerate(fighter_urls):
                data = self._ensure_round(stats_map, fighter_url, round_number)

                landed, attempted = self._parse_landed_attempted(self._value_at(cols, 1, fighter_idx))
                if landed is not None:
                    data["sig_strikes_landed"] = landed
                    data["sig_strikes_attempted"] = attempted

                for field_name, col_idx in (
                    ("sig_head", 3),
                    ("sig_body", 4),
                    ("sig_leg", 5),
                    ("sig_distance", 6),
                    ("sig_clinch", 7),
                    ("sig_ground", 8),
                ):
                    landed, attempted = self._parse_landed_attempted(self._value_at(cols, col_idx, fighter_idx))
                    data[f"{field_name}_landed"] = landed
                    data[f"{field_name}_attempted"] = attempted

    @staticmethod
    def _parse_round_header(thead: Tag) -> int | None:
        th = thead.find("th")
        if not th:
            return None
        match = re.search(r"Round\s+(\d+)", th.get_text(strip=True), re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _fighter_urls_from_col(col: Tag) -> list[str]:
        urls: list[str] = []
        for link in col.find_all("a", href=re.compile(r"fighter-details")):
            href = link.get("href", "").strip()
            if href and href not in urls:
                urls.append(href)
        return urls

    @staticmethod
    def _values_from_col(col: Tag) -> list[str]:
        texts = col.find_all("p", class_="b-fight-details__table-text")
        if texts:
            return [t.get_text(strip=True) for t in texts]
        return [col.get_text(strip=True)] if col.get_text(strip=True) else []

    def _value_at(self, cols: list[Tag], col_idx: int, fighter_idx: int) -> str | None:
        if col_idx >= len(cols):
            return None
        values = self._values_from_col(cols[col_idx])
        if fighter_idx >= len(values):
            return None
        return values[fighter_idx]

    @staticmethod
    def _ensure_round(stats_map: dict[tuple[str, int], dict], fighter_url: str, round_number: int) -> dict:
        key = (fighter_url, round_number)
        if key not in stats_map:
            stats_map[key] = {
                "fighter_url": fighter_url,
                "round_number": round_number,
            }
        return stats_map[key]

    @staticmethod
    def _parse_landed_attempted(value: str | None) -> tuple[int | None, int | None]:
        if not value or value in ("---", "--"):
            return None, None
        match = re.match(r"(\d+)\s+of\s+(\d+)", value.strip())
        if match:
            return int(match.group(1)), int(match.group(2))
        return None, None

    @staticmethod
    def _parse_control_seconds(value: str | None) -> int | None:
        if not value or value in ("---", "--"):
            return None
        parts = value.strip().split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None
        return None

    @staticmethod
    def _parse_int(value: str | None) -> int | None:
        if not value or value in ("---", "--"):
            return None
        try:
            return int(value.strip())
        except ValueError:
            return None
