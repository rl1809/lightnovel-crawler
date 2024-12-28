# -*- coding: utf-8 -*-
import logging
from concurrent.futures import Future
from typing import List, Optional
from urllib.parse import quote, urlencode

from bs4.element import Tag

from lncrawl.core.crawler import Crawler

logger = logging.getLogger(__name__)

search_url = "https://truyenyy.vip/?s=%s"


class TruyenYY(Crawler):
    has_mtl = True
    base_url = ["https://truyenyy.vip/"]

    @staticmethod
    def __select_value(tag: Tag, css: str, attr: Optional[str] = None):
        possible_item = tag.select_one(css)
        if not isinstance(possible_item, Tag):
            return ""
        if attr:
            return (getattr(possible_item, "attrs") or {}).get(attr)
        else:
            return (getattr(possible_item, "text") or "").strip()

    def search_novel(self, query):
        soup = self.get_soup(search_url % quote(query))

        results = []
        for div in soup.select(".cate-list-books .list-item"):
            a = div.select_one(".truyen-title a")
            if not isinstance(a, Tag):
                continue

            status_info = self.__select_value(div, ".status-info")
            author = self.__select_value(div, ".author")
            latest = self.__select_value(div, ".item-col.text-info a")
            info = [x for x in [latest, author, status_info] if x]

            results.append(
                {
                    "title": a.text.strip(),
                    "url": self.absolute_url(a["href"]),
                    "info": " | ".join(info),
                }
            )

        return results

    def read_novel_info(self):
        logger.debug("Visiting %s", self.novel_url)
        soup = self.get_soup(self.novel_url)

        title = soup.select_one("h1.name")
        self.novel_title = title.text.strip()
        logger.info("Novel title: %s", self.novel_title)

        novel_cover = soup.select_one(".cover img")
        self.novel_cover = novel_cover.get("data-src", novel_cover.get("src"))
        logger.info("Novel cover: %s", novel_cover)

        authors = soup.select('.author a')
        novel_author = ", ".join([x.text for x in authors])
        logger.info("Novel author: %s", novel_author)

        self.novel_description = " ".join([p.text for p in soup.select("section#id_novel_summary p")]) or None

        self.parse_truyenyy_chapters(soup)

    def parse_truyenyy_chapters(self, soup: Tag):
        total_page = 1
        soup = self.get_soup(self.novel_url+'danh-sach-chuong/')
        pagination = soup.select(".pagination li a")
        if len(pagination):
            last_page_url = str(pagination[-2]["href"])
            logger.info("Last page url: %s", last_page_url)
            if "?p=" in last_page_url:
                total_page = int(last_page_url.split('=')[-1])
        logger.info("Total page count = %d", total_page)

        futures: List[(Future, int)] = []
        for page in range(1, total_page):
            url = self.novel_url + f"danh-sach-chuong/?p={page + 1}"
            logger.info("Visiting %s", url)
            f = self.executor.submit(self.get_soup, url)
            futures.append((f,page+1))

        self.parse_all_links(soup.select("tbody tr td"), 1)

        for f in futures:
            soup = f[0].result()
            self.parse_all_links(soup.select("tbody tr td"), f[1])

    def parse_all_links(self, links: List[Tag], page):
        for i, link in enumerate(links):
            if i%3 != 1:
                continue
            if page == 2:
                print("")
            # Calculate the chapter ID and volume ID
            chap_id = 1 + len(self.chapters)
            vol_id = 1 + len(self.chapters) // 100

            # Add a new volume if starting a new one
            if len(self.chapters) % 100 == 0:
                self.volumes.append({"id": vol_id})

            chapter_link_tag = link.select_one("a")
            chapter_link = chapter_link_tag["href"]
            title = chapter_link_tag.text.strip()
            # Extract title and URL
            url = self.absolute_url(chapter_link)

            # Append the chapter
            self.chapters.append(
                {
                    "id": chap_id,
                    "volume": vol_id,
                    "title": title,
                    "url": url,
                }
            )

    def initialize(self) -> None:
        self.cleaner.bad_css = set(
            [
                ".ads-content",
                ".ads-inpage-container",
                ".ads-responsive",
                ".ads-pc",
                ".ads-chapter-box",
                ".incontent-ad",
                ".ads-network",
                ".ads-desktop",
                ".ads-mobile",
                ".ads-holder",
                ".ads-taboola",
                ".ads-middle",
                ".adsbygoogle",
            ]
        )

    def download_chapter_body(self, chapter):
        soup = self.get_soup(chapter["url"])
        contents = soup.select_one(".chap-content")
        return self.cleaner.extract_contents(contents)
